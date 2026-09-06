#!/usr/bin/env python3
"""Controller closeout for the passed P6.1 intraday target/fill step."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_target_fill_v1 import (
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_target_fill@1.0.json"
MODEL = ROOT / "docs/ops/reaka_residual_only_model@1.5.json"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_target_fill_v1_20260831"
REPORT = EVIDENCE / "validation_report.json"
ACCEPTANCE = EVIDENCE / "controller_acceptance.json"
REGISTRY = ROOT / "docs/ops/reaka_strategy_authority_registry@8.0.json"
PROGRESSIVE = ROOT / "docs/ops/reaka_current_strategy_progressive_index@8.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@145.0.json"


def main() -> None:
    contract = read_json(CONTRACT)
    report = read_json(REPORT)
    model = read_json(MODEL)
    if report.get("status") != "passed" or report.get("blockers") != []:
        raise RuntimeError("reaka_intraday_closeout_requires_passed_validation")
    acceptance = write_json(
        ACCEPTANCE,
        {
            "schema_id": ("factorlab.reaka_intraday_target_fill_controller_acceptance@1.0"),
            "status": "passed_P6_1_waiting_intraday_OT1_successor",
            "issue_ref": "bd://fl-eginj.1",
            "contract_digest": contract["canonical_digest"],
            "validation_report_digest": report["canonical_digest"],
            "accepted_findings": [
                "1430_and_1445_raw_1m_coordinates_materialized_separately",
                "decision_mark_is_known_at_clock",
                "entry_fill_is_first_tradable_bar_after_clock",
                "history_and_future_target_price_coordinates_are_separate",
                "inference_support_does_not_read_future_target_or_entry",
                "D5_H20_R5_four_phases_are_preserved",
                "formal_and_isolated_trees_are_byte_identical",
            ],
            "residual_target_status": ("not_built_next_step_is_intraday_OT1_orthogonalization"),
            "next_legal_action": ("user_checkpoint_before_freezing_intraday_OT1_successor"),
            "model_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    registry = write_json(
        REGISTRY,
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@8.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_strategy_id": "REAKA_ORTHOGONAL_RESIDUAL_ONLY_V1",
            "current_model": "docs/ops/reaka_residual_only_model@1.5.json",
            "current_model_digest": model["canonical_digest"],
            "intraday_target_fill_contract_digest": contract["canonical_digest"],
            "intraday_target_fill_acceptance_digest": acceptance["canonical_digest"],
            "current_stage": "P6_1_complete_waiting_intraday_OT1_successor",
            "scientific_status": "infrastructure_or_measurement_gap",
            "deployment_candidate": False,
            "production_pointer_changed": False,
            "production_authority": False,
        },
    )
    progressive = write_json(
        PROGRESSIVE,
        {
            "schema_id": "factorlab.reaka_current_strategy_progressive_index@8.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_model_digest": model["canonical_digest"],
            "current_acceptance_digest": acceptance["canonical_digest"],
            "scientific_status": "infrastructure_or_measurement_gap",
            "completed_phase": "P6_1_intraday_target_fill",
            "next_legal_action": "user_checkpoint_before_intraday_OT1_successor",
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@145.0",
            "status": "P6_1_intraday_target_fill_complete_waiting_user",
            "issue_ref": "bd://fl-eginj.1",
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "authority_registry_digest": registry["canonical_digest"],
            "progressive_index_digest": progressive["canonical_digest"],
            "next_legal_action": "wait_user_before_intraday_OT1_successor",
            "model_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    print(
        json.dumps(
            {
                "acceptance_digest": acceptance["canonical_digest"],
                "registry_digest": registry["canonical_digest"],
                "progressive_digest": progressive["canonical_digest"],
                "succession_digest": succession["canonical_digest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
