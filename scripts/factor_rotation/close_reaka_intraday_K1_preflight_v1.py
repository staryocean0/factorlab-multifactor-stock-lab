#!/usr/bin/env python3
"""Controller closeout for passed P6.3 K1/r0 input and preflight."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import read_json, write_json

ROOT = Path(__file__).resolve().parents[2]
ISSUE_REF = "bd://fl-eginj.3"
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_preflight@1.0.json"
MODEL = ROOT / "docs/ops/reaka_residual_only_model@1.5.json"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831"
REPORT = EVIDENCE / "validation_report.json"
ACCEPTANCE = EVIDENCE / "controller_acceptance.json"
REGISTRY = ROOT / "docs/ops/reaka_strategy_authority_registry@10.0.json"
PROGRESSIVE = ROOT / "docs/ops/reaka_current_strategy_progressive_index@10.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@149.0.json"


def main() -> None:
    contract = read_json(CONTRACT)
    report = read_json(REPORT)
    model = read_json(MODEL)
    if report.get("status") != "passed" or report.get("blockers") != []:
        raise RuntimeError("reaka_intraday_K1_closeout_requires_passed_validation")
    acceptance = write_json(
        ACCEPTANCE,
        {
            "schema_id": "factorlab.reaka_intraday_K1_preflight_controller_acceptance@1.0",
            "status": "passed_P6_3_waiting_formal_K1_r0_training_checkpoint",
            "issue_ref": ISSUE_REF,
            "contract_digest": contract["canonical_digest"],
            "validation_report_digest": report["canonical_digest"],
            "clock_reports": report["clock_reports"],
            "accepted_findings": [
                "1430_and_1445_inputs_are_independent_and_byte_replayable",
                "inference_rows_are_not_filtered_by_future_target_or_entry",
                "D5_four_phase_anchor_is_global_2008_12_01",
                "K1_r0_71_dimension_feature_identity_is_closed",
                "compatibility_capacity_LR_gradient_and_backend_gates_pass",
                "all_22_current_parameters_are_explicit_without_user_math_input",
            ],
            "next_legal_action": "user_checkpoint_before_formal_K1_r0_training",
            "formal_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    registry = write_json(
        REGISTRY,
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@10.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_strategy_id": "REAKA_ORTHOGONAL_RESIDUAL_ONLY_V1",
            "current_model": "docs/ops/reaka_residual_only_model@1.5.json",
            "current_model_digest": model["canonical_digest"],
            "intraday_K1_preflight_contract_digest": contract["canonical_digest"],
            "intraday_K1_preflight_acceptance_digest": acceptance["canonical_digest"],
            "current_stage": "P6_3_complete_waiting_formal_K1_r0_training_checkpoint",
            "scientific_status": "infrastructure_or_measurement_gap",
            "deployment_candidate": False,
            "production_pointer_changed": False,
            "production_authority": False,
        },
    )
    progressive = write_json(
        PROGRESSIVE,
        {
            "schema_id": "factorlab.reaka_current_strategy_progressive_index@10.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_model_digest": model["canonical_digest"],
            "current_acceptance_digest": acceptance["canonical_digest"],
            "scientific_status": "infrastructure_or_measurement_gap",
            "completed_phase": "P6_3_intraday_K1_input_and_preflight",
            "next_legal_action": "user_checkpoint_before_formal_K1_r0_training",
            "formal_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@149.0",
            "status": "P6_3_intraday_K1_input_and_preflight_complete_waiting_user",
            "issue_ref": ISSUE_REF,
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "authority_registry_digest": registry["canonical_digest"],
            "progressive_index_digest": progressive["canonical_digest"],
            "next_legal_action": "wait_user_before_formal_K1_r0_training",
            "formal_training_allowed": False,
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
