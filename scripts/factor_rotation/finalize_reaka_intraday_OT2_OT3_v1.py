#!/usr/bin/env python3
# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false
# pyright: reportGeneralTypeIssues=false
"""Finalize intraday OT2 selections and OT3 transports for one tree/clock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    CLOCK_SUFFIX,
    NAKED_BASELINE_ID,
    build_intraday_transport,
    build_selected_states,
    file_digest,
    json_records,
    read_json,
    select_one_tool_per_family,
    write_json,
    write_parquet,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json"
OUTPUT_ROOT = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
P6_ROOT = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    parser.add_argument("--clock", choices=("14:30", "14:45"), required=True)
    args = parser.parse_args()
    suffix = CLOCK_SUFFIX[args.clock]
    contract = read_json(CONTRACT)
    annual_frames: list[pd.DataFrame] = []
    receipt_digests: dict[str, str] = {}
    for year in range(2009, 2021):
        root = EVIDENCE / "annual_sessions" / str(year)
        receipt = read_json(root / "receipt.json")
        receipt_digests[str(year)] = str(receipt["canonical_digest"])
        metrics = pd.read_csv(root / "metrics.csv")
        annual_frames.append(metrics.loc[metrics["decision_clock"].eq(args.clock)])
    annual = pd.concat(annual_frames, ignore_index=True)
    selected = select_one_tool_per_family(annual)
    if set(selected["economic_family_id"]) != {"market", "size", "industry"}:
        raise RuntimeError("reaka_intraday_OT2_selection_family_missing")
    root = OUTPUT_ROOT / args.tree / suffix
    ot1 = root / "ot1"
    ot2 = root / "ot2"
    ot3 = root / "ot3"
    history = pd.read_parquet(ot1 / "factor_basis_history.parquet")
    states = build_selected_states(
        history_basis=history,
        selections=selected,
        decision_clock=args.clock,
    )
    write_parquet(
        annual,
        ot2 / "annual_candidate_metrics.parquet",
        ["year", "economic_family_id", "tool_id"],
    )
    write_parquet(
        states,
        ot2 / "selected_factor_states.parquet",
        ["variant_id", "economic_family_id", "factor_id", "decision_date"],
    )
    selection = write_json(
        ot2 / "selected_family_tools.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT2_selected_tools@1.0",
            "contract_digest": contract["canonical_digest"],
            "decision_clock": args.clock,
            "annual_receipt_digests": receipt_digests,
            "selections": json_records(selected),
            "exact_one_state_per_family": True,
            "fresh_oos": False,
            "model_training_run": False,
            "production_authority": False,
        },
    )
    ot2_manifest = write_json(
        ot2 / "manifest.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT2_manifest@1.0",
            "selected_states_digest": file_digest(ot2 / "selected_factor_states.parquet"),
            "annual_metrics_digest": file_digest(ot2 / "annual_candidate_metrics.parquet"),
            "selection_digest": selection["canonical_digest"],
            "selected_state_rows": len(states),
            "production_authority": False,
        },
    )
    exposures = pd.read_parquet(ot1 / "d5_stock_exposures.parquet")
    industries = pd.read_parquet(ot1 / "d5_stock_industry_exposures.parquet")
    calendar = np.load(P6_ROOT / args.tree / "calendar.npy", mmap_mode="r")
    decisions = np.load(P6_ROOT / args.tree / "decision_positions.npy", mmap_mode="r")
    transport = build_intraday_transport(
        exposures=exposures,
        industry_exposures=industries,
        selected_states=states,
        decision_positions=decisions,
        calendar=calendar,
        decision_clock=args.clock,
    )
    ot3.mkdir(parents=True, exist_ok=True)
    write_parquet(
        transport,
        ot3 / "d5_stock_timing_transport.parquet",
        ["asof_date", "symbol"],
    )
    ot3_manifest = write_json(
        ot3 / "manifest.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT3_manifest@1.0",
            "contract_digest": contract["canonical_digest"],
            "decision_clock": args.clock,
            "transport_digest": file_digest(ot3 / "d5_stock_timing_transport.parquet"),
            "transport_rows": len(transport),
            "decision_count": int(transport["asof_date"].nunique()),
            "pre_sum_column_present": False,
            "production_authority": False,
        },
    )
    blockers: list[str] = []
    if len(selected) != 3:
        blockers.append("intraday_OT2_not_exactly_three_family_selections")
    if states.groupby("economic_family_id")["selected_tool_id"].nunique().gt(1).any():
        blockers.append("intraday_OT2_multiple_tools_per_family")
    if states["uses_forward_outcome"].any():
        blockers.append("intraday_OT2_selected_state_reads_forward")
    if transport.duplicated(["asof_date", "symbol"]).any():
        blockers.append("intraday_OT3_duplicate_coordinate")
    if any(
        column not in transport
        for column in (
            "market_timing_transport",
            "size_timing_transport",
            "industry_timing_transport",
        )
    ):
        blockers.append("intraday_OT3_three_columns_missing")
    validation = write_json(
        EVIDENCE / args.tree / suffix / "ot2_ot3_validation.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT2_OT3_validation@1.0",
            "status": "passed" if not blockers else "blocked",
            "blockers": blockers,
            "decision_clock": args.clock,
            "selected_tools": json_records(selected),
            "transparent_fallback_count": int(selected["tool_id"].eq(NAKED_BASELINE_ID).sum()),
            "OT2_manifest_digest": ot2_manifest["canonical_digest"],
            "OT3_manifest_digest": ot3_manifest["canonical_digest"],
            "transport_rows": len(transport),
            "model_training_run": False,
            "score_run": False,
            "account_run": False,
            "production_authority": False,
        },
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
