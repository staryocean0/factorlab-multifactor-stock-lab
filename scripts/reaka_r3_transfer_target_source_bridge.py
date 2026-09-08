#!/usr/bin/env python3
"""Build bounded P6-style entry-open targets for 2021--2025; no model access.

Accepted P6 future H20 is entry_open[t+20] / entry_open[t] - 1.  entry_open
is the first positive finite one-minute open strictly after the decision clock
and no later than 15:00 under the historical timestamp[11:16] wall-clock
convention.  The accepted 2007--2020 prefix is reused.  Only selected old
anchor dates and 2021--2025 DataHub month partitions are read; no 2026 target
partition is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

FACTORLAB_ROOT = Path(os.environ.get(
    "FACTORLAB_ROOT",
    "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab",
))
DATAHUB_ROOT = Path(os.environ.get(
    "DATAHUB_BARS_ROOT",
    "/home/starryocean/桌面/量化/unified_datahub/.runtime/live/lake/bars/"
    "dataset_version=bars_cn_a_1m_raw_canonical_4ceca170a851",
))
P6_REL = "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal"
CACHE_REL = "output/factor-rotation/reaka_current_generation_blackbox_gpu_cache_v2_2007_2026"
TASK = "LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01"
CLOCKS = {"1430": "14:30", "1445": "14:45"}
HORIZON = 20
END = np.datetime64("2025-12-31", "D")
TAIL_START = np.datetime64("2021-01-01", "D")
TARGET_ATOL = 1e-7
PRICE_ATOL = 1e-6
PRICE_RTOL = 1e-5


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def write_json(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(body, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def future_h20_from_entry_open(entry_open: np.ndarray, horizon: int = HORIZON) -> np.ndarray:
    values = np.asarray(entry_open, dtype=np.float32)
    if values.ndim != 2 or horizon <= 0 or len(values) <= horizon:
        raise ValueError("invalid entry_open/horizon")
    out = np.full(values.shape, np.nan, dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out[:-horizon] = values[horizon:] / values[:-horizon] - 1.0
    out[~np.isfinite(out)] = np.nan
    return out


def structural_mature_anchors(decisions: np.ndarray, calendar: np.ndarray, count: int = 5) -> np.ndarray:
    d = np.asarray(decisions, dtype=np.int64)
    cal = np.asarray(calendar).astype("datetime64[D]")
    if d.ndim != 1 or cal.ndim != 1 or (d < 0).any() or (d >= len(cal)).any():
        raise ValueError("invalid anchor axes")
    years = cal.astype("datetime64[Y]").astype(int) + 1970
    eligible = d[(years[d] >= 2018) & (years[d] <= 2020) & (d + HORIZON < len(cal))]
    if len(eligible) < count:
        raise ValueError("insufficient structurally mature anchors")
    picks = np.unique(np.linspace(0, len(eligible) - 1, count, dtype=np.int64))
    if len(picks) != count:
        raise ValueError("anchor quantiles collapsed")
    return eligible[picks]


def maxdiff(reference: np.ndarray, candidate: np.ndarray, *, atol: float = TARGET_ATOL) -> dict[str, Any]:
    a, b = np.asarray(reference), np.asarray(candidate)
    if a.shape != b.shape:
        raise ValueError("shape drift")
    fa, fb = np.isfinite(a), np.isfinite(b)
    mismatch = int(np.count_nonzero(fa != fb))
    both = fa & fb
    err = np.abs(a[both].astype(np.float64) - b[both].astype(np.float64))
    return {
        "support_mismatches": mismatch,
        "finite_cells_compared": int(both.sum()),
        "max_abs_error": float(err.max()) if len(err) else 0.0,
        "above_tolerance": int(np.count_nonzero(err > atol)),
        "passed": mismatch == 0 and not bool((err > atol).any()),
    }


def price_diff(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    a, b = np.asarray(reference), np.asarray(candidate)
    if a.shape != b.shape:
        raise ValueError("price shape drift")
    fa, fb = np.isfinite(a), np.isfinite(b)
    mismatch = int(np.count_nonzero(fa != fb))
    both = fa & fb
    err = np.abs(a[both].astype(np.float64) - b[both].astype(np.float64))
    lim = PRICE_ATOL + PRICE_RTOL * np.abs(a[both].astype(np.float64))
    return {
        "support_mismatches": mismatch,
        "finite_cells_compared": int(both.sum()),
        "max_abs_error": float(err.max()) if len(err) else 0.0,
        "violations": int(np.count_nonzero(err > lim)),
        "passed": mismatch == 0 and not bool((err > lim).any()),
    }


def minute_of_day(text: pd.Series) -> np.ndarray:
    hour = pd.to_numeric(text.str.slice(0, 2), errors="raise").to_numpy(np.int16)
    minute = pd.to_numeric(text.str.slice(3, 5), errors="raise").to_numpy(np.int16)
    return (hour * 60 + minute).astype(np.int16)


def select_entry_open(
    frame: pd.DataFrame,
    *,
    clock: str,
    wanted_days: set[pd.Timestamp],
    symbol_position: dict[str, int],
) -> pd.DataFrame:
    required = {"symbol", "trading_day", "timestamp", "open"}
    if not required.issubset(frame.columns):
        raise ValueError(f"minute columns missing: {sorted(required - set(frame.columns))}")
    local = frame.loc[:, ["symbol", "trading_day", "timestamp", "open"]].copy()
    local["symbol"] = local["symbol"].astype(str)
    local["trading_day"] = pd.to_datetime(local["trading_day"]).dt.normalize()
    local = local.loc[
        local["trading_day"].isin(wanted_days) & local["symbol"].isin(symbol_position)
    ].copy()
    if local.empty:
        return pd.DataFrame(columns=["trading_day", "symbol", "symbol_position", "entry_open", "entry_minute"])
    local["time"] = local["timestamp"].astype(str).str.slice(11, 16)
    local["open_num"] = pd.to_numeric(local["open"], errors="coerce")
    local = local.loc[
        local["time"].gt(clock)
        & local["time"].le("15:00")
        & np.isfinite(local["open_num"])
        & local["open_num"].gt(0.0)
    ].copy()
    if local.empty:
        return pd.DataFrame(columns=["trading_day", "symbol", "symbol_position", "entry_open", "entry_minute"])
    dup = local.duplicated(["trading_day", "symbol", "timestamp"], keep=False)
    if dup.any():
        conflict = (
            local.loc[dup]
            .groupby(["trading_day", "symbol", "timestamp"], sort=False)["open_num"]
            .nunique(dropna=False)
        )
        if (conflict > 1).any():
            raise ValueError("ambiguous duplicate minute open")
    local = local.sort_values("timestamp", kind="mergesort")
    first = local.drop_duplicates(["trading_day", "symbol"], keep="first").copy()
    first["symbol_position"] = first["symbol"].map(symbol_position).astype(np.int64)
    first["entry_open"] = first["open_num"].to_numpy(np.float32)
    first["entry_minute"] = minute_of_day(first["time"])
    return first[["trading_day", "symbol", "symbol_position", "entry_open", "entry_minute"]]


def month_path(root: Path, month: str) -> Path:
    return root / "instrument_type=stock" / f"trading_month={month}" / "data_0.parquet"


def load_month(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    before = path.stat()
    table = pq.ParquetFile(path).read(columns=["symbol", "trading_day", "timestamp", "open"])
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise RuntimeError(f"DataHub partition changed while reading: {path}")
    return table.to_pandas(), {
        "path": str(path),
        "size_bytes": int(after.st_size),
        "mtime_ns": int(after.st_mtime_ns),
        "content_sha256_recorded": False,
    }


def extract_dates(
    datahub_root: Path,
    calendar: np.ndarray,
    symbols: np.ndarray,
    wanted_positions: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], list[dict[str, Any]]]:
    cal = np.asarray(calendar).astype("datetime64[D]")
    pos = np.asarray(wanted_positions, dtype=np.int64)
    if pos.ndim != 1 or (pos < 0).any() or (pos >= len(cal)).any():
        raise ValueError("invalid wanted positions")
    unique_pos = np.unique(pos)
    wanted_days = {pd.Timestamp(str(cal[p])) for p in unique_pos}
    symbol_position = {str(s): int(i) for i, s in enumerate(np.asarray(symbols).astype(str))}
    opens = {s: np.full((len(cal), len(symbols)), np.nan, dtype=np.float32) for s in CLOCKS}
    minutes = {s: np.full((len(cal), len(symbols)), -1, dtype=np.int16) for s in CLOCKS}
    partitions: list[dict[str, Any]] = []
    months = sorted({str(cal[p].astype("datetime64[M]")) for p in unique_pos})
    day_position = {pd.Timestamp(str(day)): i for i, day in enumerate(cal)}
    for month in months:
        path = month_path(datahub_root, month)
        frame, receipt = load_month(path)
        month_days = {day for day in wanted_days if day.strftime("%Y-%m") == month}
        for suffix, clock in CLOCKS.items():
            selected = select_entry_open(
                frame, clock=clock, wanted_days=month_days, symbol_position=symbol_position
            )
            for row in selected.itertuples(index=False):
                di = day_position[pd.Timestamp(row.trading_day)]
                si = int(row.symbol_position)
                opens[suffix][di, si] = np.float32(row.entry_open)
                minutes[suffix][di, si] = np.int16(row.entry_minute)
        receipt["month"] = month
        partitions.append(receipt)
    return opens, minutes, partitions


def bounded_calendar(cache_calendar: np.ndarray) -> np.ndarray:
    days = np.asarray(cache_calendar).astype("datetime64[D]")
    if END not in days:
        raise ValueError("extended calendar missing 2025-12-31")
    end = int(np.flatnonzero(days == END)[-1])
    out = days[: end + 1]
    if out[-1] != END or (out >= np.datetime64("2026-01-01", "D")).any():
        raise ValueError("calendar bound failure")
    return out


def anchor_checks(
    *, datahub_root: Path, old_calendar: np.ndarray, symbols: np.ndarray,
    decisions: np.ndarray, p6_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    anchors = structural_mature_anchors(decisions, old_calendar, 5)
    needed = np.unique(np.concatenate((anchors, anchors + HORIZON)))
    opens, minutes, partitions = extract_dates(datahub_root, old_calendar, symbols, needed)
    body: dict[str, Any] = {
        "schema_id": "factorlab.r3_transfer_entry_open_anchor_checks@1.0",
        "selection_rule": "five_equal_index_quantiles_of_structurally_mature_2018_2020_old_D5",
        "anchors": [{"day_position": int(d), "date": str(old_calendar[int(d)])} for d in anchors],
        "clocks": {}, "passed": True,
    }
    for suffix in CLOCKS:
        old_open = np.load(p6_root / f"entry_open_{suffix}.npy", mmap_mode="r")
        old_min = np.load(p6_root / f"entry_minute_{suffix}.npy", mmap_mode="r")
        old_future = np.load(p6_root / f"future_h20_raw_{suffix}.npy", mmap_mode="r")
        open_rows, future_rows = [], []
        minute_mismatches = 0
        for d in anchors:
            for q in (int(d), int(d + HORIZON)):
                row = price_diff(np.asarray(old_open[q]), np.asarray(opens[suffix][q]))
                row.update({"day_position": q, "date": str(old_calendar[q])})
                open_rows.append(row)
                active = np.isfinite(np.asarray(old_open[q])) | np.isfinite(np.asarray(opens[suffix][q]))
                minute_mismatches += int(np.count_nonzero(np.asarray(old_min[q])[active] != minutes[suffix][q][active]))
            with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                candidate = opens[suffix][int(d + HORIZON)] / opens[suffix][int(d)] - 1.0
            candidate = candidate.astype(np.float32)
            candidate[~np.isfinite(candidate)] = np.nan
            row = maxdiff(np.asarray(old_future[int(d)]), candidate, atol=TARGET_ATOL)
            row.update({"day_position": int(d), "date": str(old_calendar[int(d)])})
            future_rows.append(row)
        passed = all(r["passed"] for r in open_rows) and minute_mismatches == 0 and all(r["passed"] for r in future_rows)
        body["clocks"][suffix] = {
            "entry_open_rows": open_rows,
            "entry_minute_mismatches": minute_mismatches,
            "future_h20_rows": future_rows,
            "passed": bool(passed),
        }
        body["passed"] &= bool(passed)
    return body, partitions


def run(output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    p6 = FACTORLAB_ROOT / P6_REL
    cache = FACTORLAB_ROOT / CACHE_REL
    old_calendar = np.load(p6 / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    symbols = np.load(p6 / "symbols.npy", allow_pickle=False).astype(str)
    decisions = np.load(p6 / "decision_positions.npy", allow_pickle=False).astype(np.int64)
    ext_calendar = bounded_calendar(np.load(cache / "calendar.npy", allow_pickle=False))
    ext_symbols = np.load(cache / "symbols.npy", allow_pickle=False).astype(str)
    if not np.array_equal(ext_calendar[: len(old_calendar)], old_calendar):
        raise ValueError("extended calendar prefix drift")
    if not np.array_equal(ext_symbols[: len(symbols)], symbols):
        raise ValueError("extended symbol prefix drift")
    anchors, anchor_partitions = anchor_checks(
        datahub_root=DATAHUB_ROOT, old_calendar=old_calendar, symbols=symbols,
        decisions=decisions, p6_root=p6,
    )
    if not anchors["passed"]:
        raise ValueError("DataHub entry-open rule does not reproduce accepted P6 anchors")
    tail_pos = np.flatnonzero(ext_calendar >= TAIL_START).astype(np.int64)
    tail_open, tail_minute, tail_partitions = extract_dates(DATAHUB_ROOT, ext_calendar, symbols, tail_pos)
    output_root.mkdir(parents=True, exist_ok=False)
    np.save(output_root / "calendar.npy", ext_calendar.astype("datetime64[ns]"), allow_pickle=False)
    np.save(output_root / "symbols.npy", symbols, allow_pickle=False)
    for suffix in CLOCKS:
        old_open = np.load(p6 / f"entry_open_{suffix}.npy", mmap_mode="r")
        old_min = np.load(p6 / f"entry_minute_{suffix}.npy", mmap_mode="r")
        old_future = np.load(p6 / f"future_h20_raw_{suffix}.npy", mmap_mode="r")
        entry = np.full((len(ext_calendar), len(symbols)), np.nan, dtype=np.float32)
        emin = np.full((len(ext_calendar), len(symbols)), -1, dtype=np.int16)
        entry[: len(old_calendar)] = np.asarray(old_open, dtype=np.float32)
        emin[: len(old_calendar)] = np.asarray(old_min, dtype=np.int16)
        entry[len(old_calendar):] = tail_open[suffix][len(old_calendar):]
        emin[len(old_calendar):] = tail_minute[suffix][len(old_calendar):]
        calc = future_h20_from_entry_open(entry)
        target = np.full_like(entry, np.nan, dtype=np.float32)
        target[: len(old_calendar)] = np.asarray(old_future, dtype=np.float32)
        target[len(old_calendar):] = calc[len(old_calendar):]
        tail_check = maxdiff(target[len(old_calendar):], calc[len(old_calendar):])
        if not tail_check["passed"]:
            raise ValueError(f"{suffix}: internal tail target formula mismatch")
        if np.isfinite(target[-HORIZON:]).any():
            raise ValueError(f"{suffix}: last H20 positions must remain unlabelled")
        np.save(output_root / f"entry_open_{suffix}.npy", entry, allow_pickle=False)
        np.save(output_root / f"entry_minute_{suffix}.npy", emin, allow_pickle=False)
        np.save(output_root / f"future_h20_raw_{suffix}.npy", target, allow_pickle=False)
    write_json(output_root / "anchor_checks.json", anchors)
    unique = {(p["path"], p["mtime_ns"]): p for p in anchor_partitions + tail_partitions}
    write_json(output_root / "source_receipt.json", {
        "schema_id": "factorlab.r3_transfer_entry_open_source@1.0",
        "datahub_root": str(DATAHUB_ROOT),
        "historical_event_rule": "first_positive_finite_open_with_timestamp_wall_clock_strictly_after_decision_and_le_15_00",
        "timestamp_convention": "timestamp_string_[11:16]_session_wall_clock_as_in_R2_audit_not_timezone_transform_receipt",
        "tail_start": "2021-01-01", "calendar_end": "2025-12-31",
        "raw_partition_content_hashes_recorded": False,
        "partitions": list(unique.values()), "PIT_certified": False,
    })
    names = [
        "calendar.npy", "symbols.npy", "anchor_checks.json", "source_receipt.json",
        "entry_open_1430.npy", "entry_minute_1430.npy", "future_h20_raw_1430.npy",
        "entry_open_1445.npy", "entry_minute_1445.npy", "future_h20_raw_1445.npy",
    ]
    bundle = {
        "schema_id": "factorlab.r3_transfer_entry_open_target_source@1.0",
        "task_id": TASK, "status": "bounded_entry_open_targets_prepared",
        "target_definition": "entry_open_t_plus_20_div_entry_open_t_minus_1",
        "horizon_trading_positions": HORIZON,
        "historical_prefix_origin": "reused_accepted_P6_arrays",
        "tail_origin": "bounded_DataHub_1m_entry_open_rule",
        "calendar_end": "2025-12-31", "contains_2026_target": False,
        "anchor_checks_passed": True, "new_model_fits": 0, "model_scores": 0,
        "checkpoint_reload": 0,
        "artifact_digests": {name: sha_file(output_root / name) for name in names},
        "fresh_oos": False, "PIT_certified": False, "production_authority": False,
    }
    write_json(output_root / "bundle.json", bundle)
    return bundle


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, required=True)
    args = p.parse_args()
    try:
        body = run(args.output_root.resolve())
        print(json.dumps({"status": body["status"], "task_id": TASK}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
