#!/usr/bin/env python3
# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false
"""Run exactly one digest-chained P6.2 OT2 natural-year review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    CLOCK_SUFFIX,
    evaluate_annual_tools,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json"
OUTPUT_ROOT = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
P6_FORMAL = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    year = args.year
    if year not in range(2009, 2021):
        raise ValueError("reaka_intraday_OT2_year_must_be_2009_2020")
    contract = read_json(CONTRACT)
    annual_root = EVIDENCE / "annual_sessions"
    if year == 2009:
        predecessor_digest = contract["canonical_digest"]
    else:
        predecessor_digest = read_json(annual_root / str(year - 1) / "receipt.json")["canonical_digest"]
    for later in range(year + 1, 2021):
        if (annual_root / str(later) / "receipt.json").exists():
            raise RuntimeError(f"reaka_intraday_OT2_out_of_order_future_receipt:{later}")
    calendar = pd.DatetimeIndex(pd.to_datetime(__import__("numpy").load(P6_FORMAL / "calendar.npy", mmap_mode="r")))
    positions = __import__("numpy").load(P6_FORMAL / "decision_positions.npy", mmap_mode="r")
    decision_dates = calendar[positions]
    metrics_parts: list[pd.DataFrame] = []
    replay_mismatches: list[str] = []
    for clock, suffix in CLOCK_SUFFIX.items():
        tree_metrics: dict[str, pd.DataFrame] = {}
        for tree in ("formal", "isolated"):
            root = OUTPUT_ROOT / tree / suffix
            states = pd.read_parquet(root / "ot2/candidate_states.parquet")
            future = pd.read_parquet(root / "ot1/factor_basis_future.parquet")
            tree_metrics[tree] = evaluate_annual_tools(
                candidate_states=states,
                future_basis=future,
                decision_dates=decision_dates,
                year=year,
            )
        formal = tree_metrics["formal"]
        isolated = tree_metrics["isolated"]
        try:
            pd.testing.assert_frame_equal(formal, isolated, check_exact=True)
        except AssertionError:
            replay_mismatches.append(clock)
        local = formal.copy()
        local.insert(0, "decision_clock", clock)
        metrics_parts.append(local)
    metrics = pd.concat(metrics_parts, ignore_index=True)
    year_root = annual_root / str(year)
    year_root.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(year_root / "metrics.csv", index=False)
    receipt = write_json(
        year_root / "receipt.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT2_annual_session@1.0",
            "year": year,
            "status": ("completed" if len(metrics) and not replay_mismatches else "inconclusive_or_blocked"),
            "predecessor_digest": predecessor_digest,
            "contract_digest": contract["canonical_digest"],
            "metric_row_count": len(metrics),
            "supported_metric_count": int(metrics["supported"].sum()) if len(metrics) else 0,
            "formal_isolated_mismatches": replay_mismatches,
            "post_year_rows_read": 0,
            "candidate_formula_changed": False,
            "selection_performed": False,
            "fresh_oos": False,
            "model_training_run": False,
            "production_authority": False,
        },
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if replay_mismatches:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
