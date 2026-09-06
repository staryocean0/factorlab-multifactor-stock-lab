#!/usr/bin/env python3
"""Controller closeout for the passed P6.2 intraday OT1--OT3 step."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json"
MODEL = ROOT / "docs/ops/reaka_residual_only_model@1.5.json"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831"
REPORT = EVIDENCE / "validation_report.json"
ACCEPTANCE = EVIDENCE / "controller_acceptance.json"
REGISTRY = ROOT / "docs/ops/reaka_strategy_authority_registry@9.0.json"
PROGRESSIVE = ROOT / "docs/ops/reaka_current_strategy_progressive_index@9.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@147.0.json"


def main() -> None:
    contract = read_json(CONTRACT)
    report = read_json(REPORT)
    model = read_json(MODEL)
    if report.get("status") != "passed" or report.get("blockers") != []:
        raise RuntimeError("reaka_intraday_OT_closeout_requires_passed_validation")
    acceptance = write_json(
        ACCEPTANCE,
        {
            "schema_id": "factorlab.reaka_intraday_OT1_OT3_controller_acceptance@1.0",
            "status": "passed_P6_2_waiting_K1_input_contract",
            "issue_ref": "bd://fl-eginj.2",
            "contract_digest": contract["canonical_digest"],
            "validation_report_digest": report["canonical_digest"],
            "accepted_findings": [
                "1430_and_1445_OT1_histories_and_targets_are_separate",
                "all_factor_and_stock_fits_end_strictly_at_t_minus_1",
                "five_fold_carriers_exclude_the_stock_fold",
                "OT2_used_D5_future_H20_mean_not_daily_overlap_sum",
                "twelve_natural_year_receipts_are_digest_chained",
                "OT2_selected_exactly_one_tool_or_control_per_family_per_clock",
                "OT3_preserves_three_unsummed_stock_transport_columns",
                "formal_and_isolated_trees_are_byte_identical",
            ],
            "next_legal_action": "user_checkpoint_before_K1_input_contract",
            "model_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    registry = write_json(
        REGISTRY,
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@9.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_strategy_id": "REAKA_ORTHOGONAL_RESIDUAL_ONLY_V1",
            "current_model": "docs/ops/reaka_residual_only_model@1.5.json",
            "current_model_digest": model["canonical_digest"],
            "intraday_OT_contract_digest": contract["canonical_digest"],
            "intraday_OT_acceptance_digest": acceptance["canonical_digest"],
            "current_stage": "P6_2_complete_waiting_K1_input_contract",
            "scientific_status": "infrastructure_or_measurement_gap",
            "deployment_candidate": False,
            "production_pointer_changed": False,
            "production_authority": False,
        },
    )
    progressive = write_json(
        PROGRESSIVE,
        {
            "schema_id": "factorlab.reaka_current_strategy_progressive_index@9.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_model_digest": model["canonical_digest"],
            "current_acceptance_digest": acceptance["canonical_digest"],
            "scientific_status": "infrastructure_or_measurement_gap",
            "completed_phase": "P6_2_intraday_OT1_OT3",
            "next_legal_action": "user_checkpoint_before_K1_input_contract",
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@147.0",
            "status": "P6_2_intraday_OT1_OT3_complete_waiting_user",
            "issue_ref": "bd://fl-eginj.2",
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "authority_registry_digest": registry["canonical_digest"],
            "progressive_index_digest": progressive["canonical_digest"],
            "next_legal_action": "wait_user_before_K1_input_contract",
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
