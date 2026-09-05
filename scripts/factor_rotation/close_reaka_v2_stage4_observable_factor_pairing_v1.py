#!/usr/bin/env python3
from __future__ import annotations

from typing import cast

from factor_lab.factor_rotation.reaka_v2_stage4_observable_factor_pairing_v1 import (
    CONTRACT,
    EVIDENCE_ROOT,
    OUTPUT_ROOT,
    ROOT,
)
from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    SEMANTIC_INVARIANTS,
    canonical_valid,
    file_digest,
    read_json,
    write_json,
)

MANIFEST = ROOT / "docs/ops/reaka_multifactor_current_manifest@1.2.json"


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
    validation = read_json(EVIDENCE_ROOT / "validation_report.json")
    contract = read_json(CONTRACT)
    result = read_json(OUTPUT_ROOT / "formal/result.json")
    if not all(canonical_valid(item) for item in (validation, contract, result)):
        raise PermissionError("stage4_close_input_digest_invalid")
    acceptance = write_json(
        EVIDENCE_ROOT / "controller_acceptance.json",
        {
            "schema_id": "factorlab.reaka_v2_stage4_observable_factor_pairing_controller_acceptance@1.0",
            "status": "machine_evidence_accepted_waiting_user_financial_review",
            "validation_digest": validation["canonical_digest"],
            "contract_digest": contract["canonical_digest"],
            "result_digest": result["canonical_digest"],
            "review_request_digest": validation["review_request_digest"],
            "advisor_interpretation_receipt_present": False,
            "next_legal_action": "user_financial_review_of_stage4_evidence",
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    base = read_json(ROOT / "docs/ops/reaka_multifactor_current_manifest@1.1.json")
    roots = [dict(cast(dict[str, object], item)) for item in cast(list[object], base["normative_roots"])]
    for entry in roots:
        if entry["role"] == "current_entry":
            entry.update(
                _entry(
                    "current_entry",
                    "docs/user/reaka_multifactor_current_workflow_v1_2.md",
                    "financial_review_entry_after_stage4_machine_evidence",
                )
            )
            entry["required_first_read"] = True
    roots.extend(
        [
            _entry(
                "current_stage4_whitepaper",
                "docs/ops/reaka_v2_stage4_observable_factor_pairing_whitepaper.md",
                "stage4_method_and_financial_boundary",
            ),
            _entry(
                "current_stage4_workflow",
                "docs/user/reaka_v2_stage4_observable_factor_pairing_workflow.md",
                "stage4_execution_and_review_stop",
            ),
            _entry(
                "current_stage4_contract",
                "docs/ops/reaka_v2_stage4_observable_factor_pairing@1.0.json",
                "frozen_hypotheses_inputs_statistics_and_authority",
            ),
            _entry(
                "current_stage4_validation",
                "docs/ops/evidence/reaka_v2_stage4_observable_factor_pairing_v1_20260905/validation_report.json",
                "machine_evidence_validation",
            ),
            _entry(
                "current_stage4_review_request",
                ("docs/ops/evidence/reaka_v2_stage4_observable_factor_pairing_v1_20260905/advisor_interpretation_request.md"),
                "user_financial_review_surface",
            ),
        ]
    )
    manifest = write_json(
        MANIFEST,
        {
            "schema_id": "factorlab.reaka_multifactor_current_manifest@1.2",
            "status": "stage4_machine_evidence_waiting_user_financial_review",
            "supersedes": "docs/ops/reaka_multifactor_current_manifest@1.1.json",
            "supersedes_digest": base["canonical_digest"],
            "strategy_scope": base["strategy_scope"],
            "default_unlisted_classification": base["default_unlisted_classification"],
            "first_read_sequence": [
                "docs/user/reaka_multifactor_current_workflow_v1_2.md",
                "docs/ops/reaka_multifactor_semantic_ontology@1.0.json",
                "docs/ops/reaka_multifactor_current_manifest@1.2.json",
                "docs/ops/reaka_v2_stage4_observable_factor_pairing@1.0.json",
                "docs/ops/evidence/reaka_v2_stage4_observable_factor_pairing_v1_20260905/advisor_interpretation_request.md",
            ],
            "normative_roots": roots,
            "revoked_current_normative_paths": [
                *cast(list[str], base["revoked_current_normative_paths"]),
                "docs/user/reaka_multifactor_current_workflow_v1_1.md",
                "docs/ops/reaka_multifactor_current_manifest@1.1.json",
            ],
            "current_handoff": base["current_handoff"],
            "current_stage_contract": "docs/ops/reaka_v2_stage4_observable_factor_pairing@1.0.json",
            "current_financial_review": (
                "docs/ops/evidence/reaka_v2_stage4_observable_factor_pairing_v1_20260905/advisor_interpretation_request.md"
            ),
            "next_legal_action": "user_financial_review_of_stage4_evidence",
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "base_source_closure": base.get("base_source_closure", base.get("source_closure")),
            "stage4_source_closure": contract["source_closure"],
        },
    )
    if len({str(item["role"]) for item in roots}) != len(roots):
        raise ValueError("stage4_manifest_duplicate_role")
    old_round = read_json(ROOT / "docs/ops/reaka_strategy_round_registry@1.3.json")
    round_registry = write_json(
        ROOT / "docs/ops/reaka_strategy_round_registry@1.4.json",
        {
            "schema_id": "factorlab.reaka_strategy_round_registry@1.4",
            "status": "v2_stage4_machine_evidence_waiting_user_financial_review",
            "supersedes": "docs/ops/reaka_strategy_round_registry@1.3.json",
            "supersedes_digest": old_round["canonical_digest"],
            "current_version_id": "REAKA_STRATEGY_V2_STATE_WEIGHTED_ORTHOGONAL_14",
            "current_stage": "stage4_observable_context_factor_pairing_user_review",
            "current_manifest": "docs/ops/reaka_multifactor_current_manifest@1.2.json",
            "next_checkpoint": "user_financial_review_of_five_frozen_hypotheses",
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "production_authority": False,
        },
    )
    old_authority = read_json(ROOT / "docs/ops/reaka_strategy_authority_registry@112.0.json")
    authority = write_json(
        ROOT / "docs/ops/reaka_strategy_authority_registry@113.0.json",
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@113.0",
            "status": "REAKA_V2_stage4_waiting_user_financial_review",
            "supersedes": {
                "path": "docs/ops/reaka_strategy_authority_registry@112.0.json",
                "canonical_digest": old_authority["canonical_digest"],
            },
            "round_registry": "docs/ops/reaka_strategy_round_registry@1.4.json",
            "round_registry_digest": round_registry["canonical_digest"],
            "current_manifest": "docs/ops/reaka_multifactor_current_manifest@1.2.json",
            "current_manifest_digest": manifest["canonical_digest"],
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "next_legal_action": "user_financial_review_of_stage4_evidence",
            "advisor_interpretation_receipt_present": False,
            "stage5_execution_allowed": False,
            "stage6_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "strategy_pointer_change_allowed": False,
            "production_authority": False,
        },
    )
    old_succession = read_json(ROOT / "docs/ops/reaka_controller_succession_audit@273.0.json")
    succession = write_json(
        ROOT / "docs/ops/reaka_controller_succession_audit@274.0.json",
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@274.0",
            "status": "stage4_machine_evidence_complete_waiting_user_financial_review",
            "supersedes": "docs/ops/reaka_controller_succession_audit@273.0.json",
            "supersedes_digest": old_succession["canonical_digest"],
            "authority_registry_digest": authority["canonical_digest"],
            "round_registry_digest": round_registry["canonical_digest"],
            "manifest_digest": manifest["canonical_digest"],
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "next_legal_action": "user_financial_review_of_stage4_evidence",
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    if not all(canonical_valid(item) for item in (acceptance, manifest, round_registry, authority, succession)):
        raise ValueError("stage4_close_output_digest_invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
