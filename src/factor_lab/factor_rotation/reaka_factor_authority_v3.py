"""REAKA V3 authority split between the paper core and optional factors."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID: Final = "factorlab.reaka_factor_authority@3.0"
ISSUE_REF: Final = "bd://fl-we85n"

STAGES: Final[tuple[str, ...]] = (
    "step5_paper_core_baseline_freeze",
    "step6_paper_core_neural_fidelity",
    "optional_factor_admission",
    "step7_koopman_capacity",
)


def build_authority_correction_receipt() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_context_authority_correction@1.0",
        "issue_ref": ISSUE_REF,
        "status": "passed",
        "correction_reason": "user_policy_was_factorized_not_mandatory_reference",
        "historical_receipts_immutable": True,
        "superseded_authority": [
            {
                "path": "docs/ops/evidence/reaka_stage5_context_freeze_v1_20260825/financial_review_receipt.json",
                "revoked_fields": [
                    "approved_for_bounded_stage6_research",
                    "stage6_context_transparent_open",
                ],
            },
            {
                "path": "docs/ops/evidence/reaka_joint_core_freeze_review_v1_20260826/financial_review_receipt.json",
                "revoked_fields": [
                    "reviewed_scope.transparent_core_frozen_as_neural_fidelity_reference",
                    "authority.joint_core_freeze_allowed",
                    "authority.neural_fidelity_successor_contract_creation_allowed",
                ],
            },
        ],
        "preserved_user_policy": {
            "useful_factor_may_be_admitted": True,
            "ineffective_factor_must_be_rejected": True,
            "factor_may_express_industry_size_style_or_context_tilt": True,
            "factor_may_become_system_constraint": False,
            "factor_failure_may_block_paper_core": False,
        },
        "paper_boundary": {
            "external_transparent_context_required_by_paper": False,
            "paper_inputs": ["historical_return_sequence", "stock_feature_sequence"],
            "paper_internal_state": "learned_latent_state_and_adaptive_operator_selector",
            "project_context_role": "optional_factor_or_feature_interaction_only",
        },
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def build_factor_authority_contract() -> dict[str, object]:
    correction = build_authority_correction_receipt()
    payload: dict[str, object] = {
        "schema_id": SCHEMA_ID,
        "issue_ref": ISSUE_REF,
        "status": "step5_paper_core_baseline_rebuild_required",
        "supersedes_current_authority": [
            "factorlab.reaka_state_factor_pair_workflow@2.0",
            "factorlab.reaka_neural_fidelity_successor@1.0",
            "factorlab.reaka_step6_controller_first_run@2.0",
            "factorlab.reaka_step6_controller_first_run@2.1",
            "factorlab.reaka_step6_controller_first_run@2.2",
        ],
        "historical_evidence_remains_read_only": True,
        "authority_correction_digest": correction["canonical_digest"],
        "assembly": [
            {
                "stage": "step5_paper_core_baseline_freeze",
                "purpose": "freeze_generic_paper_input_and_transparent_baseline_without_optional_context",
            },
            {
                "stage": "step6_paper_core_neural_fidelity",
                "purpose": "test_neural_carrier_against_paper_core_baseline_only",
            },
            {
                "stage": "step7_koopman_capacity",
                "purpose": "study_internal_latent_dynamics_after_core_carrier_passes",
            },
            {
                "stage": "residual_simple_to_paper_drc",
                "purpose": "open_only_after_operator_capacity_passes",
            },
        ],
        "paper_core": {
            "input_arm_id": "CORE_SPATIAL_H20",
            "factor_identity_count": 48,
            "transparent_teacher": "baseline_score",
            "optional_context_read_allowed": False,
            "status": "step5_rebuild_required",
            "neural_fidelity_status": "not_started",
        },
        "step6_paper_core_fidelity_gate": {
            "role": "engineering_carrier_fidelity_not_factor_effectiveness",
            "primary_years": [2019, 2020],
            "fixed_seeds": [11, 29, 47],
            "minimum_daily_spearman_mean_per_seed": 0.95,
            "minimum_top_jaccard_mean_per_seed": 0.75,
            "minimum_bottom_jaccard_mean_per_seed": 0.75,
            "maximum_gate_near_zero_fraction": 0.01,
            "maximum_gate_near_one_fraction": 0.01,
            "checkpoint_selection_allowed": False,
            "factor_increment_or_context_preservation_required": False,
            "scientific_claim_increment": 0,
        },
        "optional_factor_candidates": [
            {
                "candidate_id": "transparent_context_v1",
                "candidate_type": "state_conditioned_factor_interaction",
                "status": "rejected_no_stable_incremental_transport",
                "may_modify_paper_core_identity": False,
                "may_block_paper_core": False,
                "may_block_koopman_capacity": False,
                "route_authority": False,
            }
        ],
        "rollback": {
            "preserve_through": "step4_factor_identity_and_task_alignment",
            "restart_at": "step5_paper_core_baseline_freeze",
            "rerun_step0_to_step4": False,
            "rerun_step5": True,
            "rerun_step6": True,
            "reason": "context_was_promoted_during_step5_input_assembly_not_during_data_or_factor_identity_construction",
            "preserved_surfaces": [
                "PIT_and_temporal_integrity",
                "CORE_SPATIAL_H20_48_factor_identities",
                "H20_task_alignment",
                "parameter_governance",
                "teacher_aligned_mmap_cache",
                "accelerator_and_bundle_validation_infrastructure",
            ],
            "invalidated_surfaces": [
                "mandatory_transparent_context_reference",
                "context_increment_as_step6_pass_gate",
                "context_failure_as_step7_blocker",
            ],
        },
        "authority": {
            "controller_execution_only": True,
            "external_execution_authorized": False,
            "step5_paper_core_baseline_rebuild_allowed": True,
            "step6_paper_core_neural_fidelity_allowed": False,
            "optional_context_rerun_allowed": False,
            "step7_koopman_capacity_allowed": False,
            "residual_allowed": False,
            "production_authority": False,
        },
        "data_boundary": {
            "development_and_repeat_audit": "2009_2020_consumed_history",
            "post_2020_rows_authorized": 0,
            "fresh_oos": False,
        },
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def build_factor_authority_state(
    *,
    paper_core_status: str = "step5_rebuild_required",
    baseline_freeze_digest: str | None = None,
    neural_fidelity_status: str = "not_started",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_factor_authority_state@3.0",
        "contract_schema_id": SCHEMA_ID,
        "paper_core": {
            "status": paper_core_status,
            "baseline_freeze_digest": baseline_freeze_digest,
            "neural_fidelity_status": neural_fidelity_status,
        },
        "optional_factor_candidates": {
            "transparent_context_v1": "rejected_no_stable_incremental_transport",
        },
        "step7_allowed": neural_fidelity_status == "passed",
        "residual_allowed": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def _digest_matches(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def validate_factor_authority_contract(payload: Mapping[str, object]) -> dict[str, object]:
    blockers: list[str] = []
    if not _digest_matches(payload):
        blockers.append("factor_authority_digest_mismatch")
    if payload.get("schema_id") != SCHEMA_ID:
        blockers.append("factor_authority_schema_mismatch")
    paper_core = payload.get("paper_core")
    if not isinstance(paper_core, Mapping):
        blockers.append("paper_core_missing")
    else:
        if paper_core.get("optional_context_read_allowed") is not False:
            blockers.append("paper_core_optional_context_must_be_false")
        if paper_core.get("transparent_teacher") != "baseline_score":
            blockers.append("paper_core_teacher_must_be_baseline_score")
    candidates = payload.get("optional_factor_candidates")
    if not isinstance(candidates, list) or not candidates:
        blockers.append("optional_factor_candidates_missing")
    else:
        for item in candidates:
            if not isinstance(item, Mapping):
                blockers.append("optional_factor_candidate_invalid")
                continue
            candidate_id = str(item.get("candidate_id", "unknown"))
            if item.get("may_modify_paper_core_identity") is not False:
                blockers.append(f"optional_factor_may_modify_core:{candidate_id}")
            if item.get("may_block_paper_core") is not False:
                blockers.append(f"optional_factor_may_block_core:{candidate_id}")
            if item.get("may_block_koopman_capacity") is not False:
                blockers.append(f"optional_factor_may_block_capacity:{candidate_id}")
    fidelity = payload.get("step6_paper_core_fidelity_gate")
    if not isinstance(fidelity, Mapping):
        blockers.append("paper_core_fidelity_gate_missing")
    else:
        if fidelity.get("factor_increment_or_context_preservation_required") is not False:
            blockers.append("paper_core_fidelity_must_not_require_optional_factor")
        if fidelity.get("checkpoint_selection_allowed") is not False:
            blockers.append("paper_core_fidelity_checkpoint_selection_forbidden")
    rollback = payload.get("rollback")
    if not isinstance(rollback, Mapping) or rollback.get("restart_at") != "step5_paper_core_baseline_freeze":
        blockers.append("rollback_must_restart_at_step5")
    authority = payload.get("authority")
    if not isinstance(authority, Mapping):
        blockers.append("factor_authority_flags_missing")
    else:
        if authority.get("external_execution_authorized") is not False:
            blockers.append("external_execution_must_remain_closed")
        if authority.get("step7_koopman_capacity_allowed") is not False:
            blockers.append("step7_must_remain_closed_before_new_step6")
        if authority.get("residual_allowed") is not False:
            blockers.append("residual_must_remain_closed")
    result: dict[str, object] = {
        "schema_id": "factorlab.reaka_factor_authority_validation@3.0",
        "status": "passed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "rollback_restart_at": "step5_paper_core_baseline_freeze",
        "base_contract_step7_allowed": False,
        "current_state_required_for_step7": True,
        "production_authority": False,
    }
    result["canonical_digest"] = canonical_digest(result)
    return result


def evaluate_stage_request(
    payload: Mapping[str, object],
    *,
    requested_stage: str,
    state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if requested_stage not in STAGES:
        raise ValueError(f"reaka_factor_authority_unknown_stage:{requested_stage}")
    validation = validate_factor_authority_contract(payload)
    blockers = list(cast(list[str], validation["blockers"]))
    paper_core = payload.get("paper_core")
    if state is not None:
        state_body = dict(state)
        stored = state_body.pop("canonical_digest", None)
        if stored != canonical_digest(state_body):
            blockers.append("factor_authority_state_digest_mismatch")
        state_core = state.get("paper_core")
        if isinstance(state_core, Mapping):
            paper_core = state_core
        else:
            blockers.append("factor_authority_state_paper_core_missing")
    authority = payload.get("authority")
    if not isinstance(paper_core, Mapping) or not isinstance(authority, Mapping):
        blockers.append("factor_authority_state_missing")
    elif requested_stage == "step5_paper_core_baseline_freeze":
        if authority.get("step5_paper_core_baseline_rebuild_allowed") is not True:
            blockers.append("step5_paper_core_rebuild_not_allowed")
    elif requested_stage == "step6_paper_core_neural_fidelity":
        if paper_core.get("status") != "frozen_baseline_only":
            blockers.append("step5_paper_core_baseline_not_frozen")
    elif requested_stage == "optional_factor_admission":
        candidates = cast(list[Mapping[str, object]], payload.get("optional_factor_candidates", []))
        if not any(item.get("status") == "passed_optional_factor" for item in candidates):
            blockers.append("no_optional_factor_candidate_passed")
    elif requested_stage == "step7_koopman_capacity":
        if paper_core.get("neural_fidelity_status") != "passed":
            blockers.append("paper_core_neural_fidelity_not_passed")
    result: dict[str, object] = {
        "schema_id": "factorlab.reaka_factor_authority_stage_gate@3.0",
        "requested_stage": requested_stage,
        "status": "allowed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "optional_factor_failure_blocks_paper_core": False,
        "production_authority": False,
    }
    result["canonical_digest"] = canonical_digest(result)
    return result


__all__ = [
    "ISSUE_REF",
    "SCHEMA_ID",
    "STAGES",
    "build_authority_correction_receipt",
    "build_factor_authority_contract",
    "build_factor_authority_state",
    "evaluate_stage_request",
    "validate_factor_authority_contract",
]
