#!/usr/bin/env python3
"""Successor R2 auditor for LCL-R2-20260906-01 supplement A/B/C.

This is not a full PIT certificate and does not rewrite the v1 auditor or
its original report.  Exit 0 means the declared successor checks completed
and wrote JSON; assertion statuses live in the report.

G1–G5 fixes versus v1:
- digest_row never changes convention after a raw miss
- JSON canonical is recomputed from the body, not trusted from the file
- OT1/OT2 parent gates consume finite-support and stored-state comparisons
- empty P6.1 evaluation fails when labelled inference rows exist
- missing DataHub sampling cannot make the parent check pass
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ATOL = 1.0e-6
RTOL = 1.0e-5
HORIZON = 20
CLOCKS = (("14:30", "1430"), ("14:45", "1445"))
CLOUD_SELECTION_RAW = {
    "1430": "sha256:cd5d7ed8ad65938b89652a1cb66d272463b4067f35f8467d6be2d9bbd3b08c00",
    "1445": "sha256:fffcd456bd204df28b38abc6b5f809257a8f7c20271bfb36775327d68d0ee345",
}
MARKET = "orthogonal_market_cloudridge_v1"
SIZE = "orthogonal_size_small_minus_large_v1"
CONSUMED_VARIANTS = tuple(f"crossfit_fold_{fold}" for fold in range(5))
PREFIX_CUTOFF = "2016-12-31"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _theme_src() -> Path:
    return Path(__file__).resolve().parents[1] / "src"


def canonical_digest(payload: dict[str, Any]) -> str:
    src = str(_theme_src())
    if src not in sys.path:
        sys.path.insert(0, src)
    from factor_lab.governance.canonicalization import canonical_digest as impl

    body = {key: value for key, value in payload.items() if key != "canonical_digest"}
    return impl(body)


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
    """Bind one file under a predeclared convention. Never rewrite the convention."""

    if convention not in {"raw_sha256", "canonical_digest"}:
        raise ValueError(f"unsupported_digest_convention:{convention}")
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
        return row
    if convention == "raw_sha256":
        row["status"] = "byte_match" if row["raw_sha256"] == expected else "byte_mismatch"
        return row
    if path.suffix != ".json":
        row["status"] = "byte_mismatch"
        row["detail"] = "canonical_digest_requires_json"
        return row
    payload = load_json(path)
    recomputed = canonical_digest(payload)
    row["recomputed_canonical_digest"] = recomputed
    row["embedded_canonical_digest"] = payload.get("canonical_digest")
    row["embedded_matches_recomputed"] = payload.get("canonical_digest") == recomputed
    row["status"] = "byte_match" if recomputed == expected else "byte_mismatch"
    return row


def relative_to(path: str, root: Path) -> str:
    text = str(Path(path))
    prefix = str(root.resolve())
    if text.startswith(prefix):
        return text[len(prefix) :].lstrip("/")
    return text


def export_a_rows(original_rows: list[dict[str, Any]], factorlab: Path) -> list[dict[str, Any]]:
    exported: list[dict[str, Any]] = []
    for source in original_rows:
        path = Path(source["path"])
        row = {
            "relative_path": relative_to(source["path"], factorlab),
            "original_expected": source.get("expected"),
            "original_declared_convention": source.get("convention"),
            "original_raw_sha256": source.get("raw_sha256"),
            "original_status": source.get("status"),
            "original_embedded_canonical_digest": source.get("embedded_canonical_digest"),
            "size_bytes": source.get("size_bytes"),
            "identity_reused_from_original_raw": True,
        }
        if path.name == "selected_family_tools.json" and path.exists():
            payload = load_json(path)
            recomputed = canonical_digest(payload)
            current_raw = sha256_file(path)
            clock = "1430" if "/1430/" in str(path) else "1445"
            row.update(
                {
                    "identity_reused_from_original_raw": False,
                    "successor_convention": "canonical_digest",
                    "recomputed_canonical_digest": recomputed,
                    "embedded_canonical_digest": payload.get("canonical_digest"),
                    "current_raw_sha256": current_raw,
                    "cloud_published_raw_sha256": CLOUD_SELECTION_RAW[clock],
                    "raw_matches_cloud_published": current_raw == CLOUD_SELECTION_RAW[clock],
                    "raw_matches_original_recorded": current_raw == source.get("raw_sha256"),
                    "recomputed_matches_embedded": recomputed == payload.get("canonical_digest"),
                    "recomputed_matches_original_expected": recomputed == source.get("expected"),
                    "successor_status": (
                        "byte_match"
                        if recomputed == source.get("expected")
                        and current_raw == CLOUD_SELECTION_RAW[clock]
                        else "byte_mismatch"
                    ),
                }
            )
        else:
            raw_ok = source.get("raw_sha256") == source.get("expected")
            row["successor_convention"] = "raw_sha256"
            row["successor_status"] = (
                "byte_match"
                if source.get("status") == "byte_match" and raw_ok
                else (
                    "needs_raw_rebind"
                    if source.get("convention") != "raw_sha256"
                    else source.get("status")
                )
            )
        exported.append(row)
    return exported


def rejudge_existing_report(report: dict[str, Any]) -> dict[str, Any]:
    checks = report["checks"]
    b = checks["B"]
    clocks = {}
    b_ok = True
    for clock, item in b["clocks"].items():
        labelled = int(item["inference_rows"]) - int(item["inference_without_future"])
        evaluation_empty = int(item["evaluation_rows"]) == 0
        eval_ok = (not evaluation_empty or labelled == 0) and bool(
            item["evaluation_is_finite_future_subset"]
        )
        history_ok = check_ok(item["history"])
        future_ok = check_ok(item["future"])
        clock_ok = bool(item["clock_order_passed"]) and history_ok and future_ok and eval_ok
        clocks[clock] = {
            "history_ok": history_ok,
            "future_ok": future_ok,
            "evaluation_ok": eval_ok,
            "labelled_inference_rows": labelled,
            "evaluation_rows": item["evaluation_rows"],
            "clock_order_passed": item["clock_order_passed"],
            "passed": clock_ok,
        }
        b_ok = b_ok and clock_ok
    sample = b["datahub_sample"]
    sample_ok = sample.get("status") == "passed"
    b_ok = (
        b_ok
        and sample_ok
        and bool(b["axis"]["calendar_unique"])
        and bool(b["axis"]["symbols_unique"])
        and bool(b["axis"]["decision_unique_sorted"])
    )
    c_rows = {}
    for key in ("C_1430", "C_1445"):
        item = checks[key]
        hist_ok = check_ok(item["history_on_stored_support"])
        fut_ok = check_ok(item["future_on_stored_support"])
        passed = (
            hist_ok
            and fut_ok
            and (not item["uses_future_any"])
            and bool(item["fit_end_is_calendar_day_minus_1"])
            and bool(item["fold_is_symbol_position_mod_5"])
            and item["ols_spot"]["status"] == "passed"
        )
        c_rows[key] = {
            "history_ok": hist_ok,
            "future_ok": fut_ok,
            "passed": passed,
            "original_status": item["status"],
        }
    d_rows = {}
    for key in ("D_1430", "D_1445"):
        item = checks[key]
        prefix_ok = True
        details = []
        for row in item["prefix"]:
            stored_ok = check_ok(row["recomputed_vs_stored"])
            stable = bool(row["prefix_stable"]) and stored_ok
            prefix_ok = prefix_ok and stable
            details.append(
                {
                    "family": row["family"],
                    "prefix_stable": row["prefix_stable"],
                    "stored_ok": stored_ok,
                    "passed": stable,
                }
            )
        passed = (
            prefix_ok
            and bool(item["transport_clock_match"])
            and item["selection_clock"].get("fresh_oos_claimed") is False
        )
        d_rows[key] = {
            "passed": passed,
            "original_status": item["status"],
            "prefix": details,
        }
    rejudge_ok = (
        b_ok
        and all(row["passed"] for row in c_rows.values())
        and all(row["passed"] for row in d_rows.values())
    )
    return {
        "check_id": "A_B_C_D_rejudge_existing_statistics",
        "status": "passed" if rejudge_ok else "failed",
        "rescanned_price_or_residual_arrays": False,
        "B": {
            "passed": b_ok,
            "original_status": b["status"],
            "datahub_sample_status": sample.get("status"),
            "datahub_required_exact_passed": sample_ok,
            "clocks": clocks,
        },
        "C": c_rows,
        "D_full_reference_only": d_rows,
        "note": (
            "Rejudged published v1 statistics with G2–G5 parent gates. "
            "D here remains the original full_reference prefix, not the K1 consumed folds."
        ),
    }


def _ensure_factorlab_src(factorlab: Path) -> None:
    src = str(factorlab / "src")
    if src in sys.path:
        sys.path.remove(src)
    sys.path.insert(0, src)


def _family_for_factor(factor_id: str) -> str:
    if factor_id == MARKET:
        return "market"
    if factor_id == SIZE:
        return "size"
    return "industry"


def audit_k1_consumed_branch(factorlab: Path, clock: str, suffix: str) -> dict[str, Any]:
    _ensure_factorlab_src(factorlab)
    from factor_lab.factor_rotation.orthogonal_factor_timing_state_v1 import (  # noqa: I001
        family_naked_state,
        family_tool_state,
        pseudo_log_level,
    )
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
        IntradayK1InputStore,
        build_exposure_store,
        build_state_store,
    )

    ot = factorlab / f"output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal/{suffix}"
    k1 = factorlab / f"output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal/{suffix}"
    store = IntradayK1InputStore.load(k1)
    tools = load_json(ot / "ot2/selected_family_tools.json")
    states = pd.read_parquet(ot / "ot2/selected_factor_states.parquet")
    hist_basis = pd.read_parquet(ot / "ot1/factor_basis_history.parquet")
    exposures = pd.read_parquet(ot / "ot1/d5_stock_exposures.parquet")
    industries = pd.read_parquet(ot / "ot1/d5_stock_industry_exposures.parquet")
    rebuilt_state, rebuilt_available = build_state_store(
        states, np.asarray(store.calendar), store.factor_ids
    )
    rebuilt_beta, rebuilt_rel, rebuilt_mask = build_exposure_store(
        exposures=exposures,
        industry_exposures=industries,
        calendar=np.asarray(store.calendar),
        symbol_count=len(store.symbols),
        factor_ids=store.factor_ids,
        decision_positions=np.asarray(store.exposure_decision_positions),
    )
    store_identity = {
        "state_values": finite_err(rebuilt_state, np.asarray(store.state_values)),
        "state_available": finite_err(
            rebuilt_available.astype(np.float32),
            np.asarray(store.state_available, dtype=np.float32),
        ),
        "stock_factor_exposures": finite_err(
            rebuilt_beta, np.asarray(store.stock_factor_exposures)
        ),
        "exposure_reliability": finite_err(
            rebuilt_rel, np.asarray(store.exposure_reliability)
        ),
        "exposure_available": finite_err(
            rebuilt_mask.astype(np.float32),
            np.asarray(store.exposure_available, dtype=np.float32),
        ),
    }
    store_ok = all(check_ok(err) for err in store_identity.values())
    variants = load_json(k1 / "variant_ids.json")["variant_ids"]
    mapping = {
        "assemble_inputs_variant_index": "symbol_position % 5 + 1",
        "variant_ids": variants,
        "full_reference_index": 0,
        "consumed_variant_indices": [1, 2, 3, 4, 5],
        "consumed_variant_ids": list(CONSUMED_VARIANTS),
        "full_reference_consumed_by_k1": False,
        "ot3_enters_k1_features": False,
        "ot3_role": (
            "P6.1 lineage lists strictly_prior_OT3_feature_support as a P6.1 "
            "inference filter. K1 materialize_store reads OT1 residuals/exposures "
            "and OT2 selected states only; OT3 transport is a bypass for this K1."
        ),
    }
    tool_by_family = {row["economic_family_id"]: row["tool_id"] for row in tools["selections"]}
    cutoff = pd.Timestamp(PREFIX_CUTOFF)
    prefix_rows: list[dict[str, Any]] = []
    uncovered: list[dict[str, Any]] = []
    for variant in CONSUMED_VARIANTS:
        for factor in store.factor_ids:
            family = _family_for_factor(factor)
            tool = tool_by_family[family]
            series = (
                hist_basis.loc[
                    hist_basis["variant_id"].eq(variant) & hist_basis["factor_id"].eq(factor)
                ]
                .set_index("trading_day")["orthogonal_return"]
                .sort_index()
                .astype(float)
            )
            if series.empty:
                uncovered.append({"variant": variant, "factor": factor, "reason": "no_history_basis"})
                continue
            if str(tool).startswith("naked"):
                full_state = family_naked_state(series, family)
                prefix_state = family_naked_state(series.loc[:cutoff], family)
            else:
                full_state = family_tool_state(pseudo_log_level(series), series, tool, family)
                pref = series.loc[:cutoff]
                prefix_state = family_tool_state(pseudo_log_level(pref), pref, tool, family)
            common = prefix_state.index.intersection(full_state.index)
            prefix_err = finite_err(
                prefix_state.reindex(common).to_numpy(dtype=float),
                full_state.reindex(common).to_numpy(dtype=float),
            )
            stored = states.loc[
                states["variant_id"].eq(variant)
                & states["factor_id"].eq(factor)
                & states["economic_family_id"].eq(family)
            ]
            if stored.empty:
                uncovered.append({"variant": variant, "factor": factor, "reason": "no_stored_state"})
                continue
            stored_s = stored.set_index("decision_date")["timing_state"].sort_index().astype(float)
            vs_store = finite_err(
                full_state.reindex(stored_s.index).to_numpy(dtype=float),
                stored_s.to_numpy(dtype=float),
            )
            prefix_rows.append(
                {
                    "variant": variant,
                    "family": family,
                    "tool": tool,
                    "factor": factor,
                    "prefix_cutoff": PREFIX_CUTOFF,
                    "prefix_vs_full": prefix_err,
                    "recomputed_vs_stored": vs_store,
                    "passed": bool(check_ok(prefix_err) and check_ok(vs_store)),
                }
            )
    infer = np.asarray(store.inference_rows)
    spot_rows = []
    for date, symbol_pos in (
        ("2015-01-06", 0),
        ("2018-01-08", 1),
        ("2018-01-08", 14),
        ("2020-12-31", 2),
    ):
        day = int(np.flatnonzero(store.calendar.astype("datetime64[D]") == np.datetime64(date))[0])
        variant_index = int(symbol_pos % 5 + 1)
        hits = np.flatnonzero((infer[:, 0] == day) & (infer[:, 1] == symbol_pos))
        decision_positions = np.asarray(store.exposure_decision_positions)
        exposure_any = False
        if day in set(decision_positions.tolist()):
            exposure_any = bool(
                np.asarray(store.exposure_available)[
                    np.searchsorted(decision_positions, day),
                    symbol_pos,
                ].any()
            )
        spot_rows.append(
            {
                "date": date,
                "symbol": str(store.symbols[symbol_pos]),
                "symbol_position": symbol_pos,
                "variant_index": variant_index,
                "variant_id": variants[variant_index],
                "inference_row_present": bool(len(hits)),
                "state_available": [
                    int(store.state_available[variant_index, day, factor])
                    for factor in range(len(store.factor_ids))
                ],
                "exposure_available_any": exposure_any,
            }
        )
    prefix_ok = bool(prefix_rows) and all(row["passed"] for row in prefix_rows) and not uncovered
    passed = store_ok and prefix_ok
    return {
        "check_id": f"B_k1_consumed_{suffix}",
        "clock": clock,
        "status": "passed" if passed else "failed",
        "tolerance": {"atol": ATOL, "rtol": RTOL},
        "coverage": {
            "consumed_variants": list(CONSUMED_VARIANTS),
            "factor_ids": list(store.factor_ids),
            "prefix_combinations_checked": len(prefix_rows),
            "uncovered": uncovered,
            "selection_years_consumed": sorted(int(year) for year in tools["annual_receipt_digests"]),
            "fresh_oos_claimed": tools.get("fresh_oos"),
            "state_value_check_separated_from_tool_selection_clock": True,
        },
        "mapping": mapping,
        "store_identity_vs_ot_rebuild": store_identity,
        "store_identity_passed": store_ok,
        "consumed_variant_prefix": prefix_rows,
        "consumed_variant_prefix_passed": prefix_ok,
        "assemble_spots": spot_rows,
        "authority": "selection_is_consumed_development_material_not_fresh_oos",
    }


def collect_timestamp_contract(factorlab: Path, datahub: Path) -> dict[str, Any]:
    p61 = factorlab / "src/factor_lab/factor_rotation/reaka_intraday_target_fill_v1.py"
    lineage = load_json(
        factorlab / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal/lineage.json"
    )
    sample_day = "2009-01-07"
    sample_symbol = "000001"
    partition = datahub / "instrument_type=stock" / "trading_month=2009-01" / "data_0.parquet"
    example: dict[str, Any] = {"status": "missing_partition", "path": str(partition)}
    if partition.exists():
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq

        table = pq.ParquetFile(partition).read(
            columns=["symbol", "trading_day", "timestamp", "open", "close", "available_at"]
        )
        if pa.types.is_temporal(table["trading_day"].type):
            wanted = pa.scalar(
                np.datetime64(sample_day, "D").astype("datetime64[ms]").astype("O"),
                type=table["trading_day"].type,
            )
        else:
            wanted = pa.scalar(sample_day, type=table["trading_day"].type)
        table = table.filter(pc.equal(table["trading_day"], wanted))
        table = table.filter(pc.equal(table["symbol"], pa.scalar(sample_symbol)))
        frame = table.to_pandas()
        frame["time"] = frame["timestamp"].astype(str).str.slice(11, 16)
        hit = frame.loc[frame["time"].eq("14:30")]
        row = hit.iloc[0] if len(hit) else frame.iloc[0]
        raw_ts = str(row["timestamp"])
        example = {
            "status": "example_extracted",
            "symbol": sample_symbol,
            "trading_day": sample_day,
            "raw_timestamp": raw_ts,
            "suffix": raw_ts[-1] if raw_ts else None,
            "p61_slice": raw_ts[11:16],
            "interpreted_as": "Asia/Shanghai session wall-clock spelling, Z is a suffix not a UTC conversion",
            "decision_use_if_14_30": (
                "select_clock_coordinates keeps close when time<=14:30; this 14:30 label is the decision close proxy"
            ),
            "entry_open_is_later_bar": "first time>14:30 same day",
            "available_at": str(row["available_at"]) if "available_at" in frame.columns else None,
            "available_at_equals_timestamp": (
                str(row["available_at"])[:19] == raw_ts[:19] if "available_at" in frame.columns else None
            ),
        }
    p61_text = p61.read_text(encoding="utf-8") if p61.exists() else ""
    return {
        "check_id": "C_timestamp_contract_evidence",
        "status": "label_proxy_reproducible_event_availability_unverified",
        "source_code": {
            "p61": str(p61),
            "uses_timestamp_slice_11_16": 'str.slice(11, 16)' in p61_text
            or 'utf8_slice_codeunits(table["timestamp"], 11, 16)' in p61_text,
            "afternoon_window": "13:00-15:00 inclusive",
            "decision_rule": "time <= clock and finite positive close",
            "entry_rule": "time > clock and time <= 15:00 and finite positive open",
        },
        "datahub_contract_ids_present_in_docs": [
            "cn_a_session_end_label_no_noon_partial_v2",
            "session_end_label_v2",
        ],
        "lineage_price_words": {
            "decision_price": lineage.get("decision_price"),
            "entry_fill": lineage.get("entry_fill"),
            "future_target_literal": lineage.get("future_target"),
            "future_target_resolved_meaning": "(entry_open[t+20] / entry_open[t]) - 1",
        },
        "example": example,
        "distinctions": {
            "bar_label": "end-label proxy inferred from 09:30-15:00, missing 13:00, present 13:01/15:00",
            "close_first_readable": "not independently evidenced; no vendor publish/latency ledger",
            "entry_open_event": "open of the first later labelled minute; not proven executable or later than order-send",
            "available_at": "ingest/materialization time, not 2009-2020 knowledge time",
        },
        "event_availability": "not_verified",
        "tradeability": "not_verified",
        "timezone_proof_limit": (
            "Existing 1m strings carry a Z suffix while HH:MM values fall on the CN-A session. "
            "P6.1 and the local auditor consume [11:16] as session wall clock. "
            "This is a conversion convention in current code, not a UTC-to-Shanghai transform receipt."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorlab-root", type=Path, required=True)
    parser.add_argument("--datahub-root", type=Path, required=True)
    parser.add_argument("--original-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    factorlab = args.factorlab_root.resolve()
    datahub = args.datahub_root.resolve()
    original = load_json(args.original_report)
    started = datetime.now(UTC).isoformat()
    a_rows = export_a_rows(original["checks"]["A"]["rows"], factorlab)
    selection_ok = all(
        row.get("successor_status") == "byte_match"
        for row in a_rows
        if row["relative_path"].endswith("selected_family_tools.json")
    )
    other_ok = all(
        row.get("successor_status") == "byte_match"
        for row in a_rows
        if not row["relative_path"].endswith("selected_family_tools.json")
    )
    rejudge = rejudge_existing_report(original)
    consumed = {suffix: audit_k1_consumed_branch(factorlab, clock, suffix) for clock, suffix in CLOCKS}
    clock_contract = collect_timestamp_contract(factorlab, datahub)
    report = {
        "schema_id": "factorlab.reaka_r2_local_audit@1.1",
        "task": "LCL-R2-20260906-01",
        "successor_of": "scripts/reaka_r2_local_audit_v1.py",
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "factorlab_root": str(factorlab),
        "datahub_root": str(datahub),
        "original_report": str(args.original_report.resolve()),
        "tolerance": {"rule": "abs(a-b) <= atol + rtol*abs(reference)", "atol": ATOL, "rtol": RTOL},
        "full_pit_certified": False,
        "automatic_retraining_required": False,
        "checks": {
            "A_identity": {
                "check_id": "A_strict_identity_export_and_selection_canonical",
                "status": "passed" if selection_ok and other_ok else "failed",
                "counts": {
                    "rows": len(a_rows),
                    "successor_byte_match": sum(row.get("successor_status") == "byte_match" for row in a_rows),
                    "successor_mismatch_or_other": sum(
                        row.get("successor_status") != "byte_match" for row in a_rows
                    ),
                },
                "rows": a_rows,
            },
            "A_rejudge": rejudge,
            "B_1430": consumed["1430"],
            "B_1445": consumed["1445"],
            "C_timestamp": clock_contract,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    summary = {
        key: {"id": val.get("check_id"), "status": val.get("status")}
        for key, val in report["checks"].items()
        if isinstance(val, dict)
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
