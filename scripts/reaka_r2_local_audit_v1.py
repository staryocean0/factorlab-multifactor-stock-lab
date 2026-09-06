#!/usr/bin/env python3
"""Independent local R2 auditor for REAKA P6.1 / OT / K1 consumption.

This is not a one-click PIT certificate.  Residual and H20 identities are
recomputed from stored prices/coefficients without calling the original
materializers.  Exit 0 means the declared checks completed and wrote JSON;
individual assertion statuses live in the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ATOL = 1.0e-6
RTOL = 1.0e-5
HORIZON = 20
MARKET = "orthogonal_market_cloudridge_v1"
SIZE = "orthogonal_size_small_minus_large_v1"
CLOCKS = (("14:30", "1430", 870, 871), ("14:45", "1445", 885, 886))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def finite_err(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(left) & np.isfinite(right)
    only_left = int((np.isfinite(left) & ~np.isfinite(right)).sum())
    only_right = int((~np.isfinite(left) & np.isfinite(right)).sum())
    if not mask.any():
        return {
            "compared": 0,
            "only_left_finite": only_left,
            "only_right_finite": only_right,
            "max_abs": None,
            "p99_abs": None,
            "violations": 0,
        }
    delta = np.abs(left[mask].astype(np.float64) - right[mask].astype(np.float64))
    scale = np.abs(right[mask].astype(np.float64))
    violations = int((delta > (ATOL + RTOL * scale)).sum())
    return {
        "compared": int(mask.sum()),
        "only_left_finite": only_left,
        "only_right_finite": only_right,
        "max_abs": float(delta.max()),
        "p99_abs": float(np.quantile(delta, 0.99)),
        "violations": violations,
    }


def check_ok(err: dict[str, Any]) -> bool:
    return (
        err["compared"] > 0
        and err["only_left_finite"] == 0
        and err["only_right_finite"] == 0
        and err["violations"] == 0
    )


def digest_row(path: Path, expected: str | None, convention: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": str(path),
        "expected": expected,
        "convention": convention,
    }
    if not path.exists():
        row["status"] = "missing"
        return row
    row["size_bytes"] = path.stat().st_size
    row["raw_sha256"] = sha256_file(path)
    if expected is None:
        row["status"] = "present_unbound"
    elif convention == "raw_sha256":
        if row["raw_sha256"] == expected:
            row["status"] = "byte_match"
        elif path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            canonical = payload.get("canonical_digest")
            row["embedded_canonical_digest"] = canonical
            if canonical == expected:
                row["status"] = "byte_match"
                row["convention"] = "canonical_digest"
            else:
                row["status"] = "byte_mismatch"
        else:
            row["status"] = "byte_mismatch"
    else:
        row["raw_matches_recorded"] = row["raw_sha256"] == expected
        row["status"] = "present_unbound"
    return row


def audit_binding(factorlab: Path) -> dict[str, Any]:
    p61 = factorlab / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal"
    manifest = load_json(p61 / "manifest.json")
    rows = [
        digest_row(
            p61 / "manifest.json",
            "sha256:82f57a1aba896c1e31a0030dcc6677bc0b74eb45eefa478ed5d4321d306aab0f",
            "raw_sha256",
        )
    ]
    for name, expected in manifest["artifact_digests"].items():
        rows.append(digest_row(p61 / name, expected, "raw_sha256"))
    ot_expected = {
        "1430/ot1/manifest.json": "sha256:e564d6dc818de9891eb7a8d83cd1fe62bb1490995857b5cb31518d6067970558",
        "1445/ot1/manifest.json": "sha256:abcdaca494be21418798caef71d6b50a02e77fdf361f49b0210224e96b5855c2",
        "1430/ot2/manifest.json": "sha256:25308d2a42b03583c14dc49fadc9854940dbef77ad61f7996a1a830f6201fd8a",
        "1445/ot2/manifest.json": "sha256:203ede4d3a82ef6f1d80c823b2b93b83e18ffad57554b5d25d45464b78be416b",
        "1430/ot3/manifest.json": "sha256:86d40e3cb1fd306800f27b81c1a2a24654dd8efa52672183fa6e366e936a83fa",
        "1445/ot3/manifest.json": "sha256:7f6324a337a78440d8d2a21aba8cc41a442e2c45bf4bac955eff8cdc3c77d348",
    }
    ot_root = factorlab / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal"
    for rel, expected in ot_expected.items():
        rows.append(digest_row(ot_root / rel, expected, "raw_sha256"))
        payload = load_json(ot_root / rel)
        files = payload.get("files", {})
        if isinstance(files, dict):
            for name, digest in files.items():
                rows.append(digest_row((ot_root / rel).parent / name, digest, "raw_sha256"))
        for field, filename in (
            ("selected_states_digest", "selected_factor_states.parquet"),
            ("annual_metrics_digest", "annual_candidate_metrics.parquet"),
            ("selection_digest", "selected_family_tools.json"),
            ("transport_digest", "d5_stock_timing_transport.parquet"),
        ):
            if field in payload:
                rows.append(digest_row((ot_root / rel).parent / filename, payload[field], "raw_sha256"))
    k1_root = factorlab / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal"
    for clock, expected_manifest in (
        ("1430", "sha256:7b8050270c72894ff2e6c67f1fb4a5a5513ca46e8cc0b8c02ed7e0ce3523dfd3"),
        ("1445", "sha256:e979fce98e3a6e67f6e5b2bef2701f100d2b174fcdef4539e417ba3aa0c9a7e7"),
    ):
        manifest_path = k1_root / clock / "manifest.json"
        rows.append(digest_row(manifest_path, expected_manifest, "raw_sha256"))
        payload = load_json(manifest_path)
        for name, digest in payload["artifact_digests"].items():
            rows.append(digest_row(k1_root / clock / name, digest, "raw_sha256"))
    counts = {
        key: sum(row["status"] == key for row in rows)
        for key in ("byte_match", "byte_mismatch", "present_unbound", "missing")
    }
    return {
        "check_id": "A_source_binding",
        "status": "passed" if counts["byte_mismatch"] == 0 and counts["missing"] == 0 else "failed",
        "counts": counts,
        "rows": rows,
        "note": "OT/K1 large files are bound to their own manifests; recovery_request still marks P6.2 convention unbound.",
    }


def audit_p61(factorlab: Path, datahub: Path) -> dict[str, Any]:
    root = factorlab / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal"
    calendar = np.load(root / "calendar.npy")
    symbols = np.load(root / "symbols.npy").astype(str)
    decisions = np.load(root / "decision_positions.npy")
    lineage = load_json(root / "lineage.json")
    axis = {
        "calendar_unique": bool(len(np.unique(calendar)) == len(calendar) and np.all(calendar[1:] > calendar[:-1])),
        "symbols_unique": bool(len(np.unique(symbols)) == len(symbols)),
        "decision_unique_sorted": bool(
            len(np.unique(decisions)) == len(decisions) and np.all(decisions[1:] > decisions[:-1])
        ),
        "calendar_days": int(len(calendar)),
        "symbol_count": int(len(symbols)),
        "decision_count": int(len(decisions)),
        "calendar_start": str(calendar[0].astype("datetime64[D]")),
        "calendar_end": str(calendar[-1].astype("datetime64[D]")),
        "first_decision": str(calendar[int(decisions[0])].astype("datetime64[D]")),
        "last_decision": str(calendar[int(decisions[-1])].astype("datetime64[D]")),
        "interval_unique": [int(v) for v in np.unique(np.diff(decisions)).tolist()],
    }
    clocks: dict[str, Any] = {}
    for clock, suffix, close_max, open_min in CLOCKS:
        close = np.load(root / f"decision_close_{suffix}.npy")
        open_ = np.load(root / f"entry_open_{suffix}.npy")
        dmin = np.load(root / f"decision_minute_{suffix}.npy")
        emin = np.load(root / f"entry_minute_{suffix}.npy")
        hist = np.load(root / f"history_h20_raw_{suffix}.npy")
        fut = np.load(root / f"future_h20_raw_{suffix}.npy")
        infer = np.load(root / f"inference_rows_{suffix}.npy")
        ev = np.load(root / f"evaluation_row_indices_{suffix}.npy")
        recon_h = np.full(close.shape, np.nan, dtype=np.float64)
        recon_f = np.full(open_.shape, np.nan, dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            recon_h[HORIZON:] = close[HORIZON:].astype(np.float64) / close[:-HORIZON].astype(np.float64) - 1.0
            recon_f[:-HORIZON] = open_[HORIZON:].astype(np.float64) / open_[:-HORIZON].astype(np.float64) - 1.0
        recon_h[~np.isfinite(recon_h)] = np.nan
        recon_f[~np.isfinite(recon_f)] = np.nan
        hist_err = finite_err(recon_h.astype(np.float32), hist)
        fut_err = finite_err(recon_f.astype(np.float32), fut)
        valid_d = dmin >= 0
        valid_e = emin >= 0
        clock_ok = bool(
            (not valid_d.any() or int(dmin[valid_d].max()) <= close_max)
            and (not valid_e.any() or int(emin[valid_e].min()) >= open_min)
            and (not (valid_d & valid_e).any() or bool(np.all(dmin[valid_d & valid_e] < emin[valid_d & valid_e])))
        )
        infer_future = np.isfinite(fut[infer[:, 0], infer[:, 1]]) if len(infer) else np.zeros(0, dtype=bool)
        eval_ok = bool(
            len(ev) == 0
            or (int(ev.max()) < len(infer) and bool(np.array_equal(np.sort(ev), np.flatnonzero(infer_future))))
        )
        clocks[clock] = {
            "history": hist_err,
            "future": fut_err,
            "history_passed": check_ok(hist_err),
            "future_passed": check_ok(fut_err),
            "clock_order_passed": clock_ok,
            "decision_minute_max": int(dmin[valid_d].max()) if valid_d.any() else None,
            "entry_minute_min": int(emin[valid_e].min()) if valid_e.any() else None,
            "inference_rows": int(len(infer)),
            "evaluation_rows": int(len(ev)),
            "inference_without_future": int((~infer_future).sum()) if len(infer) else 0,
            "evaluation_is_finite_future_subset": eval_ok,
        }
    sample = sample_datahub(datahub, calendar, symbols, decisions, root)
    lineage_note = {
        "lineage_future_formula": lineage.get("future_target"),
        "implemented_and_independently_checked": "entry_open[t+20] / entry_open[t] - 1",
        "detail": (
            "lineage.json writes entry_open_t_plus_20_div_entry_open_t_minus_1; "
            "stored arrays and code use entry[t+20]/entry[t]-1."
        ),
    }
    passed = (
        all(
            item["history_passed"]
            and item["future_passed"]
            and item["clock_order_passed"]
            and item["evaluation_is_finite_future_subset"]
            for item in clocks.values()
        )
        and axis["calendar_unique"]
        and axis["symbols_unique"]
        and axis["decision_unique_sorted"]
        and sample["status"] != "failed"
    )
    return {
        "check_id": "B_p61_clock_price_label",
        "status": "passed" if passed else "failed",
        "tolerance": {"atol": ATOL, "rtol": RTOL},
        "axis": axis,
        "clocks": clocks,
        "lineage": lineage_note,
        "datahub_sample": sample,
        "tradeability": "not_verified_price_time_only",
    }


def _minute(series: pd.Series) -> np.ndarray:
    hour = pd.to_numeric(series.str.slice(0, 2), errors="raise").to_numpy(np.int16)
    minute = pd.to_numeric(series.str.slice(3, 5), errors="raise").to_numpy(np.int16)
    return (hour * 60 + minute).astype(np.int16)


def sample_datahub(
    datahub: Path,
    calendar: np.ndarray,
    symbols: np.ndarray,
    decisions: np.ndarray,
    root: Path,
) -> dict[str, Any]:
    dataset = datahub / "instrument_type=stock"
    if not dataset.exists():
        return {"status": "blocked_missing_dependency", "detail": str(dataset)}
    years = calendar.astype("datetime64[Y]").astype(int) + 1970
    picks: list[int] = []
    for year in (2009, 2015, 2018, 2020):
        local = decisions[(years[decisions] == year)]
        if len(local):
            picks.append(int(local[0 if year != 2020 else -1]))
    close1430 = np.load(root / "decision_close_1430.npy")
    nan_days = [int(day) for day in decisions if np.isnan(close1430[day]).any()]
    if nan_days:
        picks.append(nan_days[len(nan_days) // 2])
    picks = sorted(set(picks))
    symbol_pos = [p for p in (0, 14, 100, 500) if p < len(symbols)]
    names = [str(symbols[p]) for p in symbol_pos]
    stored = {
        suffix: {
            "close": np.load(root / f"decision_close_{suffix}.npy"),
            "open": np.load(root / f"entry_open_{suffix}.npy"),
            "dmin": np.load(root / f"decision_minute_{suffix}.npy"),
            "emin": np.load(root / f"entry_minute_{suffix}.npy"),
        }
        for _, suffix, _, _ in CLOCKS
    }
    rows: list[dict[str, Any]] = []
    mismatches = 0
    for day in picks:
        month = str(calendar[day].astype("datetime64[M]"))
        path = dataset / f"trading_month={month}" / "data_0.parquet"
        if not path.exists():
            rows.append({"day": str(calendar[day].astype("datetime64[D]")), "status": "missing_partition", "path": str(path)})
            mismatches += 1
            continue
        wanted = str(calendar[day].astype("datetime64[D]"))
        table = pq.ParquetFile(path).read(
            columns=["symbol", "trading_day", "timestamp", "open", "close", "available_at"]
        )
        day_col = table["trading_day"]
        if pa.types.is_temporal(day_col.type):
            wanted_scalar = pa.scalar(np.datetime64(wanted, "D").astype("datetime64[ms]").astype("O"), type=day_col.type)
        else:
            wanted_scalar = pa.scalar(wanted, type=day_col.type)
        table = table.filter(pc.equal(day_col, wanted_scalar))
        table = table.filter(pc.is_in(table["symbol"], value_set=pa.array(names)))
        frame = table.to_pandas()
        if frame.empty:
            rows.append({"day": wanted, "status": "empty_join", "path": str(path)})
            mismatches += 1
            continue
        frame["time"] = frame["timestamp"].astype(str).str.slice(11, 16)
        times = sorted(set(frame["time"].tolist()))
        rows.append(
            {
                "day": wanted,
                "bar_time_min": times[0] if times else None,
                "bar_time_max": times[-1] if times else None,
                "has_13_00": "13:00" in times,
                "has_13_01": "13:01" in times,
                "has_14_59": "14:59" in times,
                "has_15_00": "15:00" in times,
                "timestamp_suffix_sample": str(frame["timestamp"].iloc[0]) if len(frame) else None,
                "bar_label_inference": (
                    "end_label_tdx_style"
                    if ("13:00" not in times and "13:01" in times and "15:00" in times)
                    else "unresolved"
                ),
            }
        )
        frame = frame.loc[frame["time"].between("13:00", "15:00", inclusive="both")].copy()
        if "available_at" in frame.columns:
            same = (
                frame["available_at"].astype(str).str.slice(0, 19) == frame["timestamp"].astype(str).str.slice(0, 19)
            ).mean()
            rows.append({"day": wanted, "available_at_equals_timestamp_share": float(same)})
        for clock, suffix, _, _ in CLOCKS:
            stored_close = stored[suffix]["close"]
            stored_open = stored[suffix]["open"]
            stored_dmin = stored[suffix]["dmin"]
            stored_emin = stored[suffix]["emin"]
            before = frame.loc[
                frame["time"].le(clock)
                & np.isfinite(pd.to_numeric(frame["close"], errors="coerce"))
                & pd.to_numeric(frame["close"], errors="coerce").gt(0.0)
            ]
            after = frame.loc[
                frame["time"].gt(clock)
                & frame["time"].le("15:00")
                & np.isfinite(pd.to_numeric(frame["open"], errors="coerce"))
                & pd.to_numeric(frame["open"], errors="coerce").gt(0.0)
            ]
            for name, pos in zip(names, symbol_pos, strict=True):
                dec = before.loc[before["symbol"].eq(name)]
                ent = after.loc[after["symbol"].eq(name)]
                got_close = float(dec.sort_values("timestamp").iloc[-1]["close"]) if len(dec) else math.nan
                got_open = float(ent.sort_values("timestamp").iloc[0]["open"]) if len(ent) else math.nan
                got_dmin = (
                    int(_minute(pd.Series([str(dec.sort_values("timestamp").iloc[-1]["timestamp"])[11:16]]))[0])
                    if len(dec)
                    else -1
                )
                got_emin = (
                    int(_minute(pd.Series([str(ent.sort_values("timestamp").iloc[0]["timestamp"])[11:16]]))[0])
                    if len(ent)
                    else -1
                )
                exp_close = float(stored_close[day, pos])
                exp_open = float(stored_open[day, pos])
                close_ok = (not np.isfinite(exp_close) and not np.isfinite(got_close)) or (
                    np.isfinite(exp_close)
                    and np.isfinite(got_close)
                    and abs(got_close - exp_close) <= ATOL + RTOL * abs(exp_close)
                )
                open_ok = (not np.isfinite(exp_open) and not np.isfinite(got_open)) or (
                    np.isfinite(exp_open)
                    and np.isfinite(got_open)
                    and abs(got_open - exp_open) <= ATOL + RTOL * abs(exp_open)
                )
                minute_ok = got_dmin == int(stored_dmin[day, pos]) and got_emin == int(stored_emin[day, pos])
                if not (close_ok and open_ok and minute_ok):
                    mismatches += 1
                rows.append(
                    {
                        "day": wanted,
                        "clock": clock,
                        "symbol": name,
                        "datahub_close": got_close,
                        "stored_close": exp_close,
                        "datahub_open": got_open,
                        "stored_open": exp_open,
                        "datahub_decision_minute": got_dmin,
                        "stored_decision_minute": int(stored_dmin[day, pos]),
                        "datahub_entry_minute": got_emin,
                        "stored_entry_minute": int(stored_emin[day, pos]),
                        "match": bool(close_ok and open_ok and minute_ok),
                    }
                )
    return {
        "status": "passed" if mismatches == 0 else "failed",
        "predeclared_days": [str(calendar[d].astype("datetime64[D]")) for d in picks],
        "symbols": names,
        "mismatches": mismatches,
        "rows": rows,
        "timestamp_convention_note": (
            "selection uses timestamp[11:16]; available_at compared when present. "
            "Bar start vs end is reported, not assumed."
        ),
    }


def _basis_cube(frame: pd.DataFrame, factor_ids: list[str], n_days: int) -> np.ndarray:
    cube = np.full((5, n_days, len(factor_ids)), np.nan, dtype=np.float64)
    index = {fid: i for i, fid in enumerate(factor_ids)}
    local = frame.loc[frame["variant_id"].astype(str).str.startswith("crossfit_fold_")].copy()
    fold = local["variant_id"].astype(str).str.rsplit("_", n=1).str[-1].astype(int).to_numpy()
    day = local["day_position"].to_numpy(np.int64)
    col = local["factor_id"].map(index).to_numpy()
    val = local["orthogonal_return"].to_numpy(np.float64)
    ok = np.isfinite(col)
    cube[fold[ok], day[ok], col[ok].astype(int)] = val[ok]
    return cube


def audit_ot1(factorlab: Path, clock: str, suffix: str) -> dict[str, Any]:
    p61 = factorlab / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal"
    ot = factorlab / f"output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal/{suffix}/ot1"
    calendar = np.load(p61 / "calendar.npy")
    symbols = np.load(p61 / "symbols.npy").astype(str)
    decisions = np.load(p61 / "decision_positions.npy")
    history_r = np.load(p61 / f"history_h20_raw_{suffix}.npy")
    future_r = np.load(p61 / f"future_h20_raw_{suffix}.npy")
    residual = np.load(ot / "stock_residual_surfaces.npz")
    eps_h = residual["epsilon_history"]
    eps_f = residual["epsilon_future"]
    residual_cal_ok = bool(
        np.array_equal(residual["calendar"].astype("datetime64[ns]"), calendar.astype("datetime64[ns]"))
    )
    residual_sym_ok = bool(np.array_equal(residual["symbols"].astype(str), symbols))
    exposures = pd.read_parquet(ot / "d5_stock_exposures.parquet")
    industry = pd.read_parquet(ot / "d5_stock_industry_exposures.parquet")
    hist_basis = pd.read_parquet(ot / "factor_basis_history.parquet")
    fut_basis = pd.read_parquet(ot / "factor_basis_future.parquet")
    extra = sorted({fid for fid in hist_basis["factor_id"].astype(str) if fid not in {MARKET, SIZE}})
    factor_ids = [MARKET, SIZE, *extra]
    hist_cube = _basis_cube(hist_basis, factor_ids, len(calendar))
    fut_cube = _basis_cube(fut_basis, factor_ids, len(calendar))
    fold_ok = bool(
        np.array_equal(
            exposures["crossfit_fold"].to_numpy(np.int64),
            exposures["symbol_position"].to_numpy(np.int64) % 5,
        )
    )
    uses_future = bool(exposures["uses_future"].any() or industry["uses_future"].any())
    day_map = {pd.Timestamp(value): index for index, value in enumerate(calendar)}
    asof = pd.to_datetime(exposures["asof_date"]).map(day_map)
    fit_end = pd.to_datetime(exposures["fit_end_date"])
    fit_check = True
    if asof.notna().any():
        expected_fit = pd.to_datetime(calendar[asof.dropna().astype(int).to_numpy() - 1])
        fit_check = bool(np.array_equal(fit_end.loc[asof.notna()].to_numpy(), expected_fit.to_numpy()))
    next_day = {
        int(decisions[i]): int(decisions[i + 1] if i + 1 < len(decisions) else len(calendar))
        for i in range(len(decisions))
    }
    recon_h = np.full_like(eps_h, np.nan, dtype=np.float64)
    recon_f = np.full_like(eps_f, np.nan, dtype=np.float64)
    covered = 0
    for asof_ts, group in exposures.groupby("asof_date", sort=False):
        day = day_map.get(pd.Timestamp(asof_ts))
        if day is None or day not in next_day:
            continue
        apply = np.arange(day, next_day[day], dtype=np.int64)
        if not len(apply):
            continue
        local_ind = industry.loc[industry["asof_date"].eq(asof_ts)]
        for fold, stocks in group.groupby("crossfit_fold", sort=False):
            fold_i = int(fold)
            pos = stocks["symbol_position"].to_numpy(np.int64)
            intercept = stocks["intercept"].to_numpy(np.float64)
            beta = np.zeros((len(stocks), len(factor_ids)), dtype=np.float64)
            beta[:, 0] = stocks["beta_market"].to_numpy(np.float64)
            beta[:, 1] = stocks["beta_size"].to_numpy(np.float64)
            if len(local_ind):
                sub = local_ind.loc[local_ind["symbol_position"].isin(pos)]
                if len(sub):
                    pos_index = {int(p): i for i, p in enumerate(pos)}
                    fid_index = {fid: i for i, fid in enumerate(factor_ids)}
                    for rec in sub.itertuples(index=False):
                        si = pos_index.get(int(rec.symbol_position))
                        fi = fid_index.get(str(rec.industry_factor_id))
                        if si is None or fi is None:
                            continue
                        beta[si, fi] = float(rec.beta_industry)
            xh = hist_cube[fold_i, apply]
            xf = fut_cube[fold_i, apply]
            pred_h = intercept[None, :] + xh @ beta.T
            pred_f = intercept[None, :] + xf @ beta.T
            recon_h[np.ix_(apply, pos)] = history_r[np.ix_(apply, pos)].astype(np.float64) - pred_h
            recon_f[np.ix_(apply, pos)] = future_r[np.ix_(apply, pos)].astype(np.float64) - pred_f
            covered += int(len(pos) * len(apply))
    stored_h = np.isfinite(eps_h)
    stored_f = np.isfinite(eps_f)
    hist_stored = finite_err(
        np.where(stored_h, recon_h, np.nan).astype(np.float32),
        np.where(stored_h, eps_h, np.nan),
    )
    fut_stored = finite_err(
        np.where(stored_f, recon_f, np.nan).astype(np.float32),
        np.where(stored_f, eps_f, np.nan),
    )
    ols = _ols_spot(
        calendar,
        symbols,
        history_r,
        hist_cube,
        exposures,
        industry,
        factor_ids,
        day_map,
    )
    passed = (
        residual_cal_ok
        and residual_sym_ok
        and fold_ok
        and (not uses_future)
        and fit_check
        and hist_stored["violations"] == 0
        and fut_stored["violations"] == 0
        and hist_stored["compared"] > 0
        and fut_stored["compared"] > 0
        and ols["status"] == "passed"
    )
    return {
        "check_id": f"C_ot1_{suffix}",
        "clock": clock,
        "status": "passed" if passed else "failed",
        "residual_calendar_match": residual_cal_ok,
        "residual_symbol_match": residual_sym_ok,
        "fold_is_symbol_position_mod_5": fold_ok,
        "uses_future_any": uses_future,
        "fit_end_is_calendar_day_minus_1": fit_check,
        "apply_cells_covered": covered,
        "history_on_stored_support": hist_stored,
        "future_on_stored_support": fut_stored,
        "exposure_rows": int(len(exposures)),
        "industry_rows": int(len(industry)),
        "formula": "epsilon = stock_return - intercept - factor_returns @ betas",
        "return_source": "P6.1 history_h20_raw / future_h20_raw",
        "coefficient_source": "ot1 d5_stock_exposures + industry exposures",
        "factor_source": "ot1 factor_basis_* orthogonal_return by crossfit_fold",
        "ols_spot": ols,
    }


def _ols_spot(
    calendar: np.ndarray,
    symbols: np.ndarray,
    history_r: np.ndarray,
    hist_cube: np.ndarray,
    exposures: pd.DataFrame,
    industry: pd.DataFrame,
    factor_ids: list[str],
    day_map: dict[pd.Timestamp, int],
) -> dict[str, Any]:
    lookback = 120
    min_obs = 96
    dates = ("2009-01-07", "2015-01-06", "2018-01-08", "2020-12-31")
    positions = [pos for pos in (0, 14, 100, 500) if pos < len(symbols)]
    rows: list[dict[str, Any]] = []
    mismatches = 0
    compared = 0
    asof = pd.to_datetime(exposures["asof_date"])
    ind_asof = pd.to_datetime(industry["asof_date"])
    for date in dates:
        day = day_map.get(pd.Timestamp(date))
        if day is None or day < lookback:
            rows.append({"date": date, "status": "day_unmapped"})
            continue
        window = np.arange(day - lookback, day, dtype=np.int64)
        for pos in positions:
            stock = exposures.loc[asof.eq(pd.Timestamp(date)) & exposures["symbol_position"].eq(pos)]
            if stock.empty:
                rows.append({"date": date, "symbol": str(symbols[pos]), "status": "no_exposure"})
                continue
            rec = stock.iloc[0]
            fold = int(rec.crossfit_fold)
            ind = industry.loc[ind_asof.eq(pd.Timestamp(date)) & industry["symbol_position"].eq(pos)]
            stored = [float(rec.intercept), float(rec.beta_market), float(rec.beta_size)]
            cols = [0, 1]
            for fid in factor_ids[2:]:
                hit = ind.loc[ind["industry_factor_id"].astype(str).eq(fid)]
                if len(hit):
                    cols.append(factor_ids.index(fid))
                    stored.append(float(hit.iloc[0]["beta_industry"]))
            x = hist_cube[fold, window][:, cols]
            y = history_r[window, pos].astype(np.float64)
            common = np.isfinite(x).all(axis=1) & np.isfinite(y)
            if int(common.sum()) < min_obs:
                rows.append({"date": date, "symbol": str(symbols[pos]), "status": "insufficient_window"})
                mismatches += 1
                continue
            design = np.column_stack([np.ones(int(common.sum())), x[common]])
            coeff, *_ = np.linalg.lstsq(design, y[common], rcond=None)
            err = finite_err(np.asarray(coeff, dtype=np.float64), np.asarray(stored, dtype=np.float64))
            compared += 1
            ok = err["violations"] == 0 and err["compared"] == len(stored)
            if not ok:
                mismatches += 1
            rows.append(
                {
                    "date": date,
                    "symbol": str(symbols[pos]),
                    "fold": fold,
                    "n_obs": int(common.sum()),
                    "n_beta": len(stored),
                    "error": err,
                    "match": ok,
                }
            )
    return {
        "status": "passed" if compared > 0 and mismatches == 0 else "failed",
        "predeclared_dates": list(dates),
        "symbol_positions": positions,
        "compared": compared,
        "mismatches": mismatches,
        "rows": rows,
        "note": "Independent lstsq on [t-120,t) history window vs stored intercept/betas. Not a refit of the production model.",
    }


def audit_ot2(factorlab: Path, clock: str, suffix: str) -> dict[str, Any]:
    src = str(factorlab / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from factor_lab.factor_rotation.orthogonal_factor_timing_state_v1 import (
        family_naked_state,
        family_tool_state,
        pseudo_log_level,
    )

    ot = factorlab / f"output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal/{suffix}"
    tools = load_json(ot / "ot2/selected_family_tools.json")
    annual = pd.read_parquet(ot / "ot2/annual_candidate_metrics.parquet")
    states = pd.read_parquet(ot / "ot2/selected_factor_states.parquet")
    hist_basis = pd.read_parquet(ot / "ot1/factor_basis_history.parquet")
    transport = pd.read_parquet(ot / "ot3/d5_stock_timing_transport.parquet")
    selection_years = sorted(int(year) for year in tools["annual_receipt_digests"])
    selection_used_future = {
        "evaluate_annual_tools_multiplies_state_by_future_factor_return": True,
        "selected_status": [row["selection_status"] for row in tools["selections"]],
        "years_consumed_for_selection": selection_years,
        "fresh_oos_claimed": tools.get("fresh_oos"),
        "note": (
            "Tool identity was chosen from 2009-2020 future-factor-return evaluations. "
            "States themselves are rebuilt from history_basis only."
        ),
    }
    prefix_rows = []
    full = hist_basis.loc[hist_basis["variant_id"].eq("full_reference")]
    cutoff = pd.Timestamp("2016-12-31")
    first_industry = (
        full.loc[full["factor_id"].astype(str).str.startswith("L1_FACTOR_CORE")]["factor_id"].astype(str).iloc[0]
    )
    for row in tools["selections"]:
        family = row["economic_family_id"]
        tool = row["tool_id"]
        factor = MARKET if family == "market" else SIZE if family == "size" else first_industry
        series = (
            full.loc[full["factor_id"].eq(factor)]
            .set_index("trading_day")["orthogonal_return"]
            .sort_index()
            .astype(float)
        )
        if str(tool).startswith("naked"):
            full_state = family_naked_state(series, family)
            prefix_state = family_naked_state(series.loc[:cutoff], family)
        else:
            full_state = family_tool_state(pseudo_log_level(series), series, tool, family)
            pref = series.loc[:cutoff]
            prefix_state = family_tool_state(pseudo_log_level(pref), pref, tool, family)
        common = prefix_state.index.intersection(full_state.index)
        err = finite_err(prefix_state.reindex(common).to_numpy(dtype=float), full_state.reindex(common).to_numpy(dtype=float))
        stored = states.loc[
            (states["economic_family_id"].eq(family))
            & (states["factor_id"].eq(factor))
            & (states["variant_id"].eq("full_reference"))
        ]
        stored_s = stored.set_index("decision_date")["timing_state"].sort_index().astype(float)
        vs_store = finite_err(full_state.reindex(stored_s.index).to_numpy(dtype=float), stored_s.to_numpy(dtype=float))
        prefix_rows.append(
            {
                "family": family,
                "tool": tool,
                "factor": factor,
                "prefix_cutoff": str(cutoff.date()),
                "prefix_vs_full": err,
                "prefix_stable": err["violations"] == 0 and err["only_left_finite"] == 0 and err["only_right_finite"] == 0,
                "recomputed_vs_stored": vs_store,
            }
        )
    transport_clock = bool((transport["decision_clock"] == clock).all()) if "decision_clock" in transport.columns else False
    passed = all(item["prefix_stable"] for item in prefix_rows) and transport_clock and tools.get("fresh_oos") is False
    return {
        "check_id": f"D_ot2_{suffix}",
        "clock": clock,
        "status": "passed" if passed else "failed",
        "selection_clock": selection_used_future,
        "prefix": prefix_rows,
        "transport_clock_match": transport_clock,
        "transport_rows": int(len(transport)),
        "annual_metrics_present": "incremental_net_vs_naked" in annual.columns,
        "authority": "selection_is_consumed_development_material_not_fresh_oos",
    }


def audit_k1(factorlab: Path, clock: str, suffix: str) -> dict[str, Any]:
    p61 = factorlab / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal"
    ot = factorlab / f"output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal/{suffix}/ot1"
    k1 = factorlab / f"output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal/{suffix}"
    calendar = np.load(p61 / "calendar.npy")
    symbols = np.load(p61 / "symbols.npy").astype(str)
    decisions = np.load(p61 / "decision_positions.npy")
    residual = np.load(ot / "stock_residual_surfaces.npz")
    k1_cal = np.load(k1 / "calendar.npy")
    k1_sym = np.load(k1 / "symbols.npy").astype(str)
    k1_h = np.load(k1 / "epsilon_history.npy")
    k1_f = np.load(k1 / "epsilon_future.npy")
    k1_dec = np.load(k1 / "exposure_decision_positions.npy")
    infer = np.load(k1 / "inference_rows.npy")
    labelled = np.load(k1 / "labelled_row_indices.npy")
    hist_err = finite_err(k1_h, residual["epsilon_history"])
    fut_err = finite_err(k1_f, residual["epsilon_future"])
    infer_future = np.isfinite(k1_f[infer[:, 0], infer[:, 1]])
    label_ok = bool(np.array_equal(np.sort(labelled), np.flatnonzero(infer_future)))
    years = infer[:, 2]
    binding = {
        "calendar_match_p61": bool(np.array_equal(k1_cal.astype("datetime64[ns]"), calendar.astype("datetime64[ns]"))),
        "symbol_match_p61": bool(np.array_equal(k1_sym, symbols)),
        "decision_match_p61": bool(np.array_equal(k1_dec, decisions)),
        "epsilon_history_vs_ot1": hist_err,
        "epsilon_future_vs_ot1": fut_err,
        "labelled_is_finite_future_subset": label_ok,
        "inference_without_label": int((~infer_future).sum()),
        "inference_year_min": int(years.min()) if len(years) else None,
        "inference_year_max": int(years.max()) if len(years) else None,
        "p61_inference_count": int(len(np.load(p61 / f"inference_rows_{suffix}.npy"))),
        "k1_inference_count": int(len(infer)),
        "note": (
            "K1 inference uses epsilon-history completeness plus exposure support, "
            "not the P6.1 history+OT3 filter. Counts may differ."
        ),
    }
    passed = (
        binding["calendar_match_p61"]
        and binding["symbol_match_p61"]
        and binding["decision_match_p61"]
        and check_ok(hist_err)
        and check_ok(fut_err)
        and label_ok
    )
    return {
        "check_id": f"E_k1_bind_{suffix}",
        "clock": clock,
        "status": "passed" if passed else "failed",
        "binding": binding,
    }


def audit_frozen_inference(factorlab: Path) -> dict[str, Any]:
    src = str(factorlab / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import torch
    from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import FIXED_CONFIG
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import IntradayK1InputStore
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import (
        build_model,
        load_state_tree,
        score_rows,
        split_indices,
    )

    store_root = factorlab / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal/1430"
    ckpt = (
        factorlab
        / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal/1430/checkpoints/seed_11"
    )
    scores_path = (
        factorlab
        / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal/1430/review_scores_seed_11.npy"
    )
    normalizer_path = (
        factorlab / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight/1430/normalizer.json"
    )
    if not ckpt.exists() or not scores_path.exists() or not normalizer_path.exists():
        return {"check_id": "E_frozen_inference_1430_seed11", "status": "blocked_missing_dependency"}
    store = IntradayK1InputStore.load(store_root)
    normalizer = load_json(normalizer_path)
    stored = np.load(scores_path)
    review = split_indices(store)["review"]
    take = np.unique(np.concatenate([review[:256], review[-256:]]))
    device = torch.device("cpu")
    model = build_model(FIXED_CONFIG, seed=11).to(device)
    load_state_tree(model, ckpt)
    scores, _, _, _ = score_rows(model, store=store, normalizer=normalizer, indices=take, device=device)
    review_index = {int(idx): pos for pos, idx in enumerate(review.tolist())}
    stored_take = np.asarray([stored[review_index[int(idx)]] for idx in take], dtype=np.float64)
    err = finite_err(scores, stored_take)
    return {
        "check_id": "E_frozen_inference_1430_seed11",
        "status": "passed" if err["violations"] == 0 and err["compared"] == len(take) else "failed",
        "clock": "14:30",
        "seed": 11,
        "predeclared_slice": "first_256_and_last_256_labelled_2017_review_rows",
        "n": int(len(take)),
        "stored_review_len": int(len(stored)),
        "review_len": int(len(review)),
        "checkpoint": str(ckpt),
        "normalizer": str(normalizer_path),
        "error": err,
        "retrained": False,
        "scope": "small_slice_not_full_review",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorlab-root", type=Path, required=True)
    parser.add_argument("--datahub-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    factorlab = args.factorlab_root.resolve()
    datahub = args.datahub_root.resolve()
    report: dict[str, Any] = {
        "schema_id": "factorlab.reaka_r2_local_audit@1.0",
        "task": "LCL-R2-20260906-01",
        "started_at": datetime.now(UTC).isoformat(),
        "factorlab_root": str(factorlab),
        "datahub_root": str(datahub),
        "tolerance": {"rule": "abs(a-b) <= atol + rtol*abs(reference)", "atol": ATOL, "rtol": RTOL},
        "checks": {},
    }
    report["checks"]["A"] = audit_binding(factorlab)
    report["checks"]["B"] = audit_p61(factorlab, datahub)
    for clock, suffix, _, _ in CLOCKS:
        report["checks"][f"C_{suffix}"] = audit_ot1(factorlab, clock, suffix)
        report["checks"][f"D_{suffix}"] = audit_ot2(factorlab, clock, suffix)
        report["checks"][f"E_bind_{suffix}"] = audit_k1(factorlab, clock, suffix)
    report["checks"]["E_infer"] = audit_frozen_inference(factorlab)
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["full_pit_certified"] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: {"id": val.get("check_id"), "status": val.get("status")} for key, val in report["checks"].items()},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
