#!/usr/bin/env python3
from __future__ import annotations

from typing import cast

from factor_lab.factor_rotation.reaka_v2_stage3_observable_context_v2 import (
    CONTRACT,
    OUTPUT_ROOT,
    ROOT,
)
from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    SEMANTIC_INVARIANTS,
    canonical_valid,
    file_digest,
    read_json,
    validate_current_manifest,
    write_json,
)

EVIDENCE = ROOT / "docs/ops/evidence/reaka_v2_stage3_observable_context_v2_20260904"
MANIFEST_V1_1 = ROOT / "docs/ops/reaka_multifactor_current_manifest@1.1.json"


def _entry(role: str, relative: str, scope: str) -> dict[str, object]:
    path = ROOT / relative
    result: dict[str, object] = {
        "role": role,
        "path": relative,
        "scope": scope,
        "required_first_read": False,
        "file_digest": file_digest(path),
    }
    if path.suffix == ".json":
        result["canonical_digest"] = read_json(path)["canonical_digest"]
    return result


def main() -> int:
    validation = read_json(EVIDENCE / "validation_report.json")
    contract = read_json(CONTRACT)
    result = read_json(OUTPUT_ROOT / "formal/result.json")
    certificate = read_json(OUTPUT_ROOT / "formal/observable_context_support_certificate.json")
    if not all(canonical_valid(payload) for payload in (validation, contract, result, certificate)):
        raise PermissionError("stage3_v2_close_input_digest_invalid")
    if validation.get("status") != "passed":
        raise PermissionError("stage3_v2_validation_not_passed")
    acceptance = write_json(
        EVIDENCE / "controller_acceptance.json",
        {
            "schema_id": "factorlab.reaka_v2_stage3_observable_context_controller_acceptance@2.0",
            "status": "accepted_stage3_observable_context_waiting_user_stage4_checkpoint",
            "validation_digest": validation["canonical_digest"],
            "contract_digest": contract["canonical_digest"],
            "result_digest": result["canonical_digest"],
            "certificate_digest": certificate["canonical_digest"],
            "operator_decision_out_of_scope": True,
            "next_legal_action": "user_review_then_freeze_stage4_contract",
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    base_manifest = read_json(ROOT / "docs/ops/reaka_multifactor_current_manifest@1.0.json")
    roots = [dict(cast(dict[str, object], item)) for item in cast(list[object], base_manifest["normative_roots"])]
    for entry in roots:
        if entry["role"] == "current_entry":
            entry.update(
                _entry(
                    "current_entry",
                    "docs/user/reaka_multifactor_current_workflow_v1_1.md",
                    "reading_order_and_stop_points_after_stage3_v2",
                )
            )
            entry["required_first_read"] = True
    roots.extend(
        [
            _entry(
                "current_stage3_whitepaper",
                "docs/ops/reaka_v2_stage3_observable_context_whitepaper.md",
                "S_obs_stage3_method_and_claim_boundary",
            ),
            _entry(
                "current_stage3_workflow",
                "docs/user/reaka_v2_stage3_observable_context_workflow.md",
                "stage3_v2_execution_and_stop_point",
            ),
            _entry(
                "current_stage3_contract",
                "docs/ops/reaka_v2_stage3_observable_context@2.0.json",
                "stage3_v2_identity_inputs_outputs_and_authority",
            ),
            _entry(
                "current_stage3_acceptance",
                "docs/ops/evidence/reaka_v2_stage3_observable_context_v2_20260904/controller_acceptance.json",
                "stage3_v2_validated_terminal",
            ),
        ]
    )
    manifest = write_json(
        MANIFEST_V1_1,
        {
            "schema_id": "factorlab.reaka_multifactor_current_manifest@1.1",
            "status": "stage3_v2_current_normative_closure",
            "supersedes": "docs/ops/reaka_multifactor_current_manifest@1.0.json",
            "supersedes_digest": base_manifest["canonical_digest"],
            "strategy_scope": base_manifest["strategy_scope"],
            "default_unlisted_classification": base_manifest["default_unlisted_classification"],
            "first_read_sequence": [
                "docs/user/reaka_multifactor_current_workflow_v1_1.md",
                "docs/ops/reaka_multifactor_semantic_ontology@1.0.json",
                "docs/ops/reaka_multifactor_current_manifest@1.1.json",
                "docs/ops/state_factor_research_state_machine@2.0.json",
                "docs/ops/reaka_v2_stage3_observable_context@2.0.json",
                "docs/ops/reaka_operator_identifiability@1.0.json",
            ],
            "normative_roots": roots,
            "revoked_current_normative_paths": [
                *cast(list[str], base_manifest["revoked_current_normative_paths"]),
                "docs/user/reaka_multifactor_current_workflow.md",
                "docs/ops/reaka_multifactor_current_manifest@1.0.json",
                "docs/ops/reaka_v2_stage3_state_episode_atlas@1.0.json",
            ],
            "current_handoff": base_manifest["current_handoff"],
            "current_stage_contract": "docs/ops/reaka_v2_stage3_observable_context@2.0.json",
            "current_stage_acceptance": "docs/ops/evidence/reaka_v2_stage3_observable_context_v2_20260904/controller_acceptance.json",
            "next_legal_action": "user_review_then_freeze_stage4_contract",
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "base_source_closure": base_manifest["source_closure"],
            "stage3_source_closure": contract["source_closure"],
        },
    )
    validate_current_manifest(manifest)
    old_round = read_json(ROOT / "docs/ops/reaka_strategy_round_registry@1.2.json")
    round_registry = write_json(
        ROOT / "docs/ops/reaka_strategy_round_registry@1.3.json",
        {
            "schema_id": "factorlab.reaka_strategy_round_registry@1.3",
            "status": "v2_stage3_observable_context_complete_waiting_stage4",
            "supersedes": "docs/ops/reaka_strategy_round_registry@1.2.json",
            "supersedes_digest": old_round["canonical_digest"],
            "current_version_id": "REAKA_STRATEGY_V2_STATE_WEIGHTED_ORTHOGONAL_14",
            "current_stage": "stage3_observable_context_support_complete",
            "current_manifest": "docs/ops/reaka_multifactor_current_manifest@1.1.json",
            "current_contract": "docs/ops/reaka_v2_stage3_observable_context@2.0.json",
            "operator_count_decision_stage": "stage6_model_training_and_operator_capacity",
            "next_checkpoint": "user_review_then_result_free_stage4_contract",
            "model_training_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    old_authority = read_json(ROOT / "docs/ops/reaka_strategy_authority_registry@111.0.json")
    authority = write_json(
        ROOT / "docs/ops/reaka_strategy_authority_registry@112.0.json",
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@112.0",
            "status": "REAKA_V2_stage3_observable_context_complete_waiting_user",
            "supersedes": {
                "path": "docs/ops/reaka_strategy_authority_registry@111.0.json",
                "canonical_digest": old_authority["canonical_digest"],
            },
            "round_registry": "docs/ops/reaka_strategy_round_registry@1.3.json",
            "round_registry_digest": round_registry["canonical_digest"],
            "current_manifest": "docs/ops/reaka_multifactor_current_manifest@1.1.json",
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
    old_succession = read_json(ROOT / "docs/ops/reaka_controller_succession_audit@272.0.json")
    succession = write_json(
        ROOT / "docs/ops/reaka_controller_succession_audit@273.0.json",
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@273.0",
            "status": "stage3_v2_complete_waiting_user_stage4_checkpoint",
            "supersedes": "docs/ops/reaka_controller_succession_audit@272.0.json",
            "supersedes_digest": old_succession["canonical_digest"],
            "authority_registry_digest": authority["canonical_digest"],
            "round_registry_digest": round_registry["canonical_digest"],
            "manifest_digest": manifest["canonical_digest"],
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "stage3_terminal": "observable_context_ready_for_stage4",
            "operator_decision_out_of_scope": True,
            "next_legal_action": "user_review_then_freeze_stage4_contract",
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    if not all(canonical_valid(payload) for payload in (acceptance, manifest, round_registry, authority, succession)):
        raise ValueError("stage3_v2_close_output_digest_invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
