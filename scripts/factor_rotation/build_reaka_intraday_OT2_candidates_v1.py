#!/usr/bin/env python3
# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false
# pyright: reportGeneralTypeIssues=false
"""Build result-free intraday OT2 candidate states for one tree/clock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    CLOCK_SUFFIX,
    ELIGIBLE_TOOL_IDS,
    NAKED_BASELINE_ID,
    build_candidate_states,
    file_digest,
    read_json,
    validate_contract,
    write_json,
    write_parquet,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json"
OUTPUT_ROOT = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
EVIDENCE_ROOT = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    parser.add_argument("--clock", choices=("14:30", "14:45"), required=True)
    args = parser.parse_args()
    suffix = CLOCK_SUFFIX[args.clock]
    contract = read_json(CONTRACT)
    blockers = validate_contract(contract)
    if blockers:
        raise RuntimeError(f"reaka_intraday_OT_contract_blocked:{blockers}")
    root = OUTPUT_ROOT / args.tree / suffix
    ot1 = root / "ot1"
    output = root / "ot2"
    evidence = EVIDENCE_ROOT / args.tree / suffix / "ot2"
    if output.exists():
        raise FileExistsError(f"reaka_intraday_OT2_output_exists:{output}")
    history = pd.read_parquet(ot1 / "factor_basis_history.parquet")
    states = build_candidate_states(history, decision_clock=args.clock)
    output.mkdir(parents=True)
    evidence.mkdir(parents=True, exist_ok=True)
    write_parquet(
        states,
        output / "candidate_states.parquet",
        ["economic_family_id", "factor_id", "tool_id", "decision_date"],
    )
    manifest = write_json(
        output / "candidate_manifest.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT2_candidate_manifest@1.0",
            "contract_digest": contract["canonical_digest"],
            "decision_clock": args.clock,
            "candidate_states_digest": file_digest(output / "candidate_states.parquet"),
            "factor_count": int(states["factor_id"].nunique()),
            "tool_or_control_count": int(states["tool_id"].nunique()),
            "state_row_count": len(states),
            "uses_forward_outcome": False,
            "production_authority": False,
        },
    )
    validation_blockers: list[str] = []
    finite = states.loc[states["available"], "timing_state"].to_numpy(float)
    if not set(np.unique(finite)).issubset({-1.0, 0.0, 1.0}):
        validation_blockers.append("intraday_OT2_state_domain_invalid")
    if states["tool_id"].nunique() != len(ELIGIBLE_TOOL_IDS) + 1:
        validation_blockers.append("intraday_OT2_candidate_count_invalid")
    if NAKED_BASELINE_ID not in set(states["tool_id"]):
        validation_blockers.append("intraday_OT2_control_missing")
    if states["uses_forward_outcome"].any():
        validation_blockers.append("intraday_OT2_state_reads_forward")
    validation = write_json(
        evidence / "candidate_validation.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT2_candidate_validation@1.0",
            "status": "passed" if not validation_blockers else "blocked",
            "blockers": validation_blockers,
            "manifest_digest": manifest["canonical_digest"],
            "decision_clock": args.clock,
            "forward_outcomes_read": 0,
            "model_training_run": False,
            "production_authority": False,
        },
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if validation_blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
