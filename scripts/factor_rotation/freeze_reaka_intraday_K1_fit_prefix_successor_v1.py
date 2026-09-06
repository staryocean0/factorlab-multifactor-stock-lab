#!/usr/bin/env python3
"""Freeze the audited fixed fit-prefix K1 successor."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import (
    FIXED_CONFIG,
    SCHEMA_ID,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    file_digest,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/ops/reaka_financial_paper_math_alignment@1.0.json"
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_fit_prefix_successor@1.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@163.0.json"
SOURCE_PATHS = (
    "docs/ops/reaka_intraday_K1_fit_prefix_successor_whitepaper.md",
    "docs/user/reaka_intraday_K1_fit_prefix_successor_workflow.md",
    "src/factor_lab/factor_rotation/reaka_intraday_k1_fit_prefix_successor_v1.py",
    "scripts/factor_rotation/freeze_reaka_intraday_K1_fit_prefix_successor_v1.py",
    "scripts/factor_rotation/run_reaka_intraday_K1_fit_prefix_successor_v1.py",
    "scripts/factor_rotation/validate_close_reaka_intraday_K1_fit_prefix_successor_v1.py",
    "tests/unit/test_reaka_intraday_k1_fit_prefix_successor_v1.py",
)


def main() -> None:
    audit = read_json(AUDIT)
    if audit.get("blockers") != []:
        raise RuntimeError("fit_prefix_successor_alignment_not_passed")
    contract = write_json(
        CONTRACT,
        {
            "schema_id": SCHEMA_ID,
            "status": "frozen_execution_authorized",
            "issue_ref": "bd://fl-eginj.7",
            "alignment_audit_digest": audit["canonical_digest"],
            "fixed_config": FIXED_CONFIG,
            "checkpoint_rule": "per_seed_earliest_minimum_fit_prefix_canonical_loss_over_max3_complete_cycles",
            "checkpoint_selection_reads_2017": False,
            "review_year": 2017,
            "closed_years": [2018, 2019, 2020],
            "source_closure": {relative: file_digest(ROOT / relative) for relative in SOURCE_PATHS},
            "formal_training_allowed": True,
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@163.0",
            "status": "P6_4_4_fit_prefix_K1_successor_open",
            "contract_digest": contract["canonical_digest"],
            "next_legal_action": "run_both_clocks_formal_isolated_then_close",
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )
    print(json.dumps({"contract": contract["canonical_digest"], "succession": succession["canonical_digest"]}, indent=2))


if __name__ == "__main__":
    main()
