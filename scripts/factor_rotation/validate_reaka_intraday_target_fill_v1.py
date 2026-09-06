#!/usr/bin/env python3
# pyright: reportAny=false, reportArgumentType=false
"""Validate formal/isolated P6.1 intraday materializations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import numpy as np

from factor_lab.factor_rotation.reaka_intraday_target_fill_v1 import (
    ARTIFACT_NAMES,
    CLOCK_SUFFIX,
    HORIZON_DAYS,
    INTRADAY_TARGET_FILL_VALIDATION_SCHEMA_ID,
    canonical_valid,
    file_digest,
    read_json,
    validate_contract,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_target_fill@1.0.json"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"
FORMAL = OUTPUT / "formal"
ISOLATED = OUTPUT / "isolated"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_target_fill_v1_20260831"
REPORT = EVIDENCE / "validation_report.json"


def _formula_errors(root: Path, suffix: str) -> dict[str, object]:
    decision = np.load(root / f"decision_close_{suffix}.npy", mmap_mode="r")
    entry = np.load(root / f"entry_open_{suffix}.npy", mmap_mode="r")
    history = np.load(root / f"history_h20_raw_{suffix}.npy", mmap_mode="r")
    future = np.load(root / f"future_h20_raw_{suffix}.npy", mmap_mode="r")
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        expected_history = decision[HORIZON_DAYS:] / decision[:-HORIZON_DAYS] - 1.0
        expected_future = entry[HORIZON_DAYS:] / entry[:-HORIZON_DAYS] - 1.0
    history_actual = history[HORIZON_DAYS:]
    future_actual = future[:-HORIZON_DAYS]
    history_mask = np.isfinite(expected_history) & np.isfinite(history_actual)
    future_mask = np.isfinite(expected_future) & np.isfinite(future_actual)
    history_max = float(np.max(np.abs(expected_history[history_mask] - history_actual[history_mask])))
    future_max = float(np.max(np.abs(expected_future[future_mask] - future_actual[future_mask])))
    history_nan_mismatch = int(np.count_nonzero(np.isfinite(expected_history) != np.isfinite(history_actual)))
    future_nan_mismatch = int(np.count_nonzero(np.isfinite(expected_future) != np.isfinite(future_actual)))
    return {
        "history_max_abs_error": history_max,
        "future_max_abs_error": future_max,
        "history_finite_mask_mismatch": history_nan_mismatch,
        "future_finite_mask_mismatch": future_nan_mismatch,
    }


def _clock_checks(root: Path, clock: str, suffix: str) -> dict[str, object]:
    decision_minute = np.load(root / f"decision_minute_{suffix}.npy", mmap_mode="r")
    entry_minute = np.load(root / f"entry_minute_{suffix}.npy", mmap_mode="r")
    rows = np.load(root / f"inference_rows_{suffix}.npy", mmap_mode="r")
    evaluation = np.load(root / f"evaluation_row_indices_{suffix}.npy", mmap_mode="r")
    future = np.load(root / f"future_h20_raw_{suffix}.npy", mmap_mode="r")
    threshold = 14 * 60 + int(clock[-2:])
    decision_valid = decision_minute >= 0
    entry_valid = entry_minute >= 0
    duplicate_count = len(rows) - len(np.unique(rows[:, :2], axis=0))
    evaluation_valid = bool(
        (evaluation >= 0).all() and (evaluation < len(rows)).all() and np.isfinite(future[rows[evaluation, 0], rows[evaluation, 1]]).all()
    )
    years = np.load(root / "calendar.npy", mmap_mode="r")[rows[:, 0]].astype("datetime64[Y]").astype(int) + 1970
    return {
        "decision_after_clock_count": int(np.count_nonzero(decision_valid & (decision_minute > threshold))),
        "entry_not_after_clock_count": int(np.count_nonzero(entry_valid & (entry_minute <= threshold))),
        "entry_after_session_count": int(np.count_nonzero(entry_valid & (entry_minute > 15 * 60))),
        "inference_duplicate_count": duplicate_count,
        "evaluation_index_valid": evaluation_valid,
        "inference_year_min": int(years.min()),
        "inference_year_max": int(years.max()),
        "phase_ids": sorted(np.unique(rows[:, 3]).astype(int).tolist()),
        "inference_without_future_label_count": int(len(rows) - len(evaluation)),
        **_formula_errors(root, suffix),
    }


def main() -> None:
    contract = read_json(CONTRACT)
    formal_manifest = read_json(FORMAL / "manifest.json")
    isolated_manifest = read_json(ISOLATED / "manifest.json")
    blockers = validate_contract(contract)
    for name, payload in (
        ("formal_manifest", formal_manifest),
        ("isolated_manifest", isolated_manifest),
    ):
        if not canonical_valid(payload):
            blockers.append(f"{name}_canonical_invalid")
        if payload.get("contract_digest") != contract.get("canonical_digest"):
            blockers.append(f"{name}_contract_digest_mismatch")
        if payload.get("post_2020_rows_read") != 0:
            blockers.append(f"{name}_post2020_read")
        if payload.get("training_run") is not False:
            blockers.append(f"{name}_training_run_invalid")
        if payload.get("score_run") is not False:
            blockers.append(f"{name}_score_run_invalid")
        if payload.get("account_run") is not False:
            blockers.append(f"{name}_account_run_invalid")
    files = (*ARTIFACT_NAMES, "manifest.json")
    replay_mismatches = [name for name in files if file_digest(FORMAL / name) != file_digest(ISOLATED / name)]
    if replay_mismatches:
        blockers.append("formal_isolated_byte_mismatch")
    closure = cast(dict[str, str], contract.get("source_closure", {}))
    source_drift = [
        relative for relative, expected in closure.items() if not (ROOT / relative).is_file() or file_digest(ROOT / relative) != expected
    ]
    if source_drift:
        blockers.append("source_closure_drift")
    clock_checks = {clock: _clock_checks(FORMAL, clock, suffix) for clock, suffix in CLOCK_SUFFIX.items()}
    for clock, checks in clock_checks.items():
        for key in (
            "decision_after_clock_count",
            "entry_not_after_clock_count",
            "entry_after_session_count",
            "inference_duplicate_count",
            "history_finite_mask_mismatch",
            "future_finite_mask_mismatch",
        ):
            if checks[key] != 0:
                blockers.append(f"{clock}_{key}")
        if checks["evaluation_index_valid"] is not True:
            blockers.append(f"{clock}_evaluation_index_invalid")
        if checks["inference_year_max"] != 2020:
            blockers.append(f"{clock}_inference_year_max_invalid")
        if checks["phase_ids"] != [0, 1, 2, 3]:
            blockers.append(f"{clock}_phase_ids_invalid")
        if float(checks["history_max_abs_error"]) != 0.0:
            blockers.append(f"{clock}_history_formula_error")
        if float(checks["future_max_abs_error"]) != 0.0:
            blockers.append(f"{clock}_future_formula_error")
    report = write_json(
        REPORT,
        {
            "schema_id": INTRADAY_TARGET_FILL_VALIDATION_SCHEMA_ID,
            "status": "passed" if not blockers else "blocked",
            "issue_ref": "bd://fl-eginj.1",
            "blockers": blockers,
            "contract_digest": contract["canonical_digest"],
            "formal_manifest_digest": formal_manifest["canonical_digest"],
            "isolated_manifest_digest": isolated_manifest["canonical_digest"],
            "byte_replay_file_count": len(files),
            "byte_replay_mismatches": replay_mismatches,
            "source_closure_drift": source_drift,
            "clock_checks": clock_checks,
            "next_open_used": False,
            "future_target_used_in_inference_support": False,
            "post_decision_entry_used_in_inference_support": False,
            "post_2020_rows_read": 0,
            "training_run": False,
            "score_run": False,
            "account_run": False,
            "production_authority": False,
        },
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
