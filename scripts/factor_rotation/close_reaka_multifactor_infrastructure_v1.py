#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    CURRENT_MANIFEST_PATH,
    SEMANTIC_INVARIANTS,
    STAGE3_CORRECTION_PATH,
    canonical_valid,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/ops/evidence/reaka_multifactor_infrastructure_v1_20260904"


def main() -> int:
    validation = read_json(EVIDENCE / "validation_report.json")
    manifest = read_json(CURRENT_MANIFEST_PATH)
    correction = read_json(STAGE3_CORRECTION_PATH)
    if not all(canonical_valid(item) for item in (validation, manifest, correction)):
        raise PermissionError("reaka_multifactor_close_input_digest_invalid")
    if validation.get("status") != "passed":
        raise PermissionError("reaka_multifactor_infrastructure_not_validated")
    acceptance = write_json(
        EVIDENCE / "controller_acceptance.json",
        {
            "schema_id": "factorlab.reaka_multifactor_infrastructure_controller_acceptance@1.0",
            "status": "accepted_current_normative_closure_waiting_user_stage4_checkpoint",
            "validation_digest": validation["canonical_digest"],
            "manifest_digest": manifest["canonical_digest"],
            "stage3_correction_digest": correction["canonical_digest"],
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "next_legal_action": "user_review_then_freeze_stage4_contract",
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    old_round = read_json(ROOT / "docs/ops/reaka_strategy_round_registry@1.1.json")
    round_registry = write_json(
        ROOT / "docs/ops/reaka_strategy_round_registry@1.2.json",
        {
            "schema_id": "factorlab.reaka_strategy_round_registry@1.2",
            "status": "v2_observable_stage3_measurement_retained_semantics_repaired",
            "supersedes": "docs/ops/reaka_strategy_round_registry@1.1.json",
            "supersedes_digest": old_round["canonical_digest"],
            "current_version_id": "REAKA_STRATEGY_V2_STATE_WEIGHTED_ORTHOGONAL_14",
            "current_stage": "infrastructure_semantic_repair_waiting_user_before_stage4",
            "current_manifest": "docs/ops/reaka_multifactor_current_manifest@1.0.json",
            "current_handoff": "docs/user/reaka_strategy_v2_external_ai_handoff_v2.md",
            "stage3_raw_measurement_retained": True,
            "stage3_operator_inference_authority": False,
            "operator_count_selection_stage": "stage6_model_training_and_operator_capacity",
            "next_checkpoint": "user_review_then_result_free_stage4_contract",
            "model_training_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    old_authority = read_json(ROOT / "docs/ops/reaka_strategy_authority_registry@110.0.json")
    authority = write_json(
        ROOT / "docs/ops/reaka_strategy_authority_registry@111.0.json",
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@111.0",
            "status": "REAKA_multifactor_infrastructure_semantics_repaired_waiting_user",
            "supersedes": {
                "path": "docs/ops/reaka_strategy_authority_registry@110.0.json",
                "canonical_digest": old_authority["canonical_digest"],
                "revoked_claim": "S_obs_episode_support_decides_discrete_K_authority",
            },
            "round_registry": "docs/ops/reaka_strategy_round_registry@1.2.json",
            "round_registry_digest": round_registry["canonical_digest"],
            "current_manifest": "docs/ops/reaka_multifactor_current_manifest@1.0.json",
            "current_manifest_digest": manifest["canonical_digest"],
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "next_legal_action": "user_review_then_freeze_stage4_contract",
            "stage3_operator_count_decision_authority": False,
            "stage4_execution_allowed": False,
            "stage5_execution_allowed": False,
            "stage6_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "strategy_pointer_change_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    old_succession = read_json(ROOT / "docs/ops/reaka_controller_succession_audit@271.0.json")
    succession = write_json(
        ROOT / "docs/ops/reaka_controller_succession_audit@272.0.json",
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@272.0",
            "status": "multifactor_current_closure_repaired_waiting_user_stage4_checkpoint",
            "supersedes": "docs/ops/reaka_controller_succession_audit@271.0.json",
            "supersedes_digest": old_succession["canonical_digest"],
            "authority_registry_digest": authority["canonical_digest"],
            "round_registry_digest": round_registry["canonical_digest"],
            "manifest_digest": manifest["canonical_digest"],
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "stage3_measurement_status": "retained_as_S_obs_description_only",
            "stage3_operator_inference_status": "revoked",
            "next_legal_action": "user_review_then_freeze_stage4_contract",
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    if not all(canonical_valid(item) for item in (acceptance, round_registry, authority, succession)):
        raise ValueError("reaka_multifactor_close_output_digest_invalid")
    if succession["authority_registry_digest"] != authority["canonical_digest"]:
        raise ValueError("reaka_multifactor_close_authority_chain_invalid")
    if authority["round_registry_digest"] != round_registry["canonical_digest"]:
        raise ValueError("reaka_multifactor_close_round_chain_invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
