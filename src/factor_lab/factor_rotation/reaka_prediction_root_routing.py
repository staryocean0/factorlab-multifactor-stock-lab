"""Route target-dependent REAKA roots and the earliest stage that must reopen."""

# pyright: reportArgumentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportUnnecessaryComparison=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false

from __future__ import annotations

from collections.abc import Mapping, Sequence

from factor_lab.governance.canonicalization import canonical_digest

ROOT_IDS = (
    "network.hidden_dimension",
    "selector.gumbel_temperature",
    "residual.denoiser_architecture",
)

STAGE_RESET_FIELDS: dict[str, tuple[str, ...]] = {
    "stage1_or_2_materials": (
        "prediction.target_definition",
        "prediction.horizon_days",
        "prediction.return_clock",
        "prediction.universe",
        "prediction.feature_identity",
    ),
    "stage3_state_observability": (
        "prediction.state_definitions",
        "prediction.state_sampling_step",
    ),
    "stage4_pairing": (
        "prediction.factor_state_mechanisms",
        "prediction.pairing_multiplicity_family",
    ),
    "stage5_parameter_closure": (
        "prediction.training_prefix",
        "model.latent_dimension",
        "model.operator_count",
        "model.residual_mode",
        "model.root_policy_version",
        "numerics.hardware_or_precision",
    ),
}


def current_h20_prediction_identity() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_prediction_identity@1.0",
        "target": "next_nonoverlapping_h20_period_return",
        "horizon_trading_days": 20,
        "physical_transition_trading_days": 20,
        "decision_cadence_trading_days": 5,
        "sequence_points": 10,
        "input_arm": "CORE_SPATIAL_H20_plus_approved_transparent_context",
        "factor_identity_count": 48,
        "approved_context_state_count": 2,
        "universe": "full_A_effective_dated_PIT_tradable",
        "execution_contract": "factorlab.reaka_stage6_portfolio_execution@1.0",
        "latent_dimension": 8,
        "entry_operator_count": 1,
        "entry_residual_mode": "disabled_until_authorized",
        "transparent_anchor_coefficient": 1.0,
        "development_material": "2009_2020_consumed",
        "post_2020_rows_authorized": 0,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def paper_latent_k1_residual_identity() -> dict[str, object]:
    payload = current_h20_prediction_identity()
    payload.pop("canonical_digest", None)
    payload["schema_id"] = "factorlab.reaka_prediction_identity@1.1"
    payload["entry_residual_mode"] = "paper_latent_k1_residual"
    payload["transparent_anchor_coefficient"] = "not_applied_to_latent_residual"
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def earliest_stage_for_prediction_change(
    changed_fields: Sequence[str],
    *,
    frozen_stage2_material_already_contains_new_target: bool = False,
) -> str:
    changed = set(changed_fields)
    if not changed:
        return "no_stage_reset"
    if changed & set(STAGE_RESET_FIELDS["stage1_or_2_materials"]):
        return "stage3_state_observability" if frozen_stage2_material_already_contains_new_target else "stage1_or_2_materials"
    if changed & set(STAGE_RESET_FIELDS["stage3_state_observability"]):
        return "stage3_state_observability"
    if changed & set(STAGE_RESET_FIELDS["stage4_pairing"]):
        return "stage4_pairing"
    if changed & set(STAGE_RESET_FIELDS["stage5_parameter_closure"]):
        return "stage5_parameter_closure"
    raise ValueError("reaka_prediction_change_field_unregistered")


def build_current_root_resolution_receipt(
    *,
    catalog_digest: str,
    identity: Mapping[str, object] | None = None,
) -> dict[str, object]:
    resolved = dict(identity) if identity is not None else current_h20_prediction_identity()
    root_resolutions = [
        {
            "parameter_id": "network.hidden_dimension",
            "status": "active_target_conditioned_router",
            "selection_policy": "nested_h_over_d_[1,2,4]_smallest_within_one_HAC_SE_of_best_inner_target_metric",
            "candidate_family": {
                "hidden_to_latent_ratios": [1, 2, 4],
                "minimum_recurrent_layers": 1,
                "decoder_hidden_width_follows_selected_h": True,
            },
            "recompute_when": [
                "target_or_horizon_changes",
                "input_effective_rank_changes",
                "training_prefix_or_effective_sample_changes",
            ],
        },
        {
            "parameter_id": "selector.gumbel_temperature",
            "status": "inactive_for_current_k1",
            "selection_policy": (
                "K1_implies_alpha_1_equals_1_for_every_positive_tau; if_K_ge_2_"
                "choose_tau_by_bisection_to_median_entropy_0p5_logK_after_"
                "logit_normalization"
            ),
            "current_value": "not_applicable_operator_count_1",
            "recompute_when": [
                "operator_count_changes_to_two_or_more",
                "state_episode_identifiability_changes",
                "target_or_horizon_changes",
            ],
        },
        {
            "parameter_id": "residual.denoiser_architecture",
            "status": "inactive_until_residual_authorization",
            "selection_policy": (
                "nested_conditional_MLP_width_[d,2d,4d]_depth_[1,2]_smallest_"
                "within_one_SE_of_best_cross_fitted_diffusion_loss_and_no_rank_harm"
            ),
            "current_value": (
                "paper_latent_k1_residual_no_diffusion"
                if resolved.get("entry_residual_mode") == "paper_latent_k1_residual"
                else "not_applicable_diffusion_not_authorized"
            ),
            "recompute_when": [
                "residual_mode_activated",
                "cross_fitted_residual_SNR_changes",
                "target_or_horizon_changes",
            ],
        },
    ]
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_root_resolution_receipt@1.0",
        "status": "approved_mathematical_root_routes",
        "catalog_digest": catalog_digest,
        "prediction_identity": resolved,
        "prediction_identity_digest": resolved["canonical_digest"],
        "resolved_root_ids": list(ROOT_IDS),
        "root_resolutions": root_resolutions,
        "current_stage_reset": {
            "trigger": (
                "residual_mode_changed_to_paper_latent_k1"
                if resolved.get("entry_residual_mode") == "paper_latent_k1_residual"
                else "root_policy_governance_upgrade_with_prediction_identity_unchanged"
            ),
            "earliest_stage_to_reopen": "stage5_parameter_closure",
            "stages_preserved": ["stage0", "stage1", "stage2", "stage3", "stage4"],
            "stage5_action": "rebuild_parameter_root_and_run_instantiation_closure",
            "stage6_action": "restart_neural_parameter_calibration_preflight_from_scratch",
            "old_stage6_checkpoints": "historical_only_not_continuable",
            "transparent_context_baseline": "preserved_as_consumed_comparator",
            "stage7": "closed",
        },
        "current_next_legal_action": (
            "stage5_compile_paper_latent_k1_residual_then_stage6_preflight"
            if resolved.get("entry_residual_mode") == "paper_latent_k1_residual"
            else "stage5_run_instantiation_then_stage6_calibration_preflight"
        ),
        "fresh_oos": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def validate_root_resolution_receipt(
    payload: Mapping[str, object],
    *,
    expected_catalog_digest: str,
) -> dict[str, object]:
    blockers: list[str] = []
    if payload.get("schema_id") != "factorlab.reaka_root_resolution_receipt@1.0":
        blockers.append("root_resolution_schema_invalid")
    if payload.get("status") != "approved_mathematical_root_routes":
        blockers.append("root_resolution_status_invalid")
    if payload.get("catalog_digest") != expected_catalog_digest:
        blockers.append("root_resolution_catalog_digest_mismatch")
    if tuple(payload.get("resolved_root_ids", [])) != ROOT_IDS:
        blockers.append("root_resolution_identity_drift")
    rows = list(payload.get("root_resolutions", []))
    if tuple(str(row.get("parameter_id", "")) for row in rows) != ROOT_IDS:
        blockers.append("root_resolution_rows_incomplete")
    if any(not str(row.get("selection_policy", "")) for row in rows):
        blockers.append("root_resolution_selection_policy_missing")
    stage_reset = dict(payload.get("current_stage_reset", {}))
    if stage_reset.get("earliest_stage_to_reopen") != "stage5_parameter_closure":
        blockers.append("current_stage_reset_not_stage5")
    digest_payload = dict(payload)
    actual_digest = str(digest_payload.pop("canonical_digest", ""))
    if actual_digest != canonical_digest(digest_payload):
        blockers.append("root_resolution_digest_mismatch")
    result: dict[str, object] = {
        "schema_id": "factorlab.reaka_root_resolution_validation@1.0",
        "status": "passed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "production_authority": False,
    }
    result["canonical_digest"] = canonical_digest(result)
    return result


__all__ = [
    "ROOT_IDS",
    "STAGE_RESET_FIELDS",
    "build_current_root_resolution_receipt",
    "current_h20_prediction_identity",
    "paper_latent_k1_residual_identity",
    "earliest_stage_for_prediction_change",
    "validate_root_resolution_receipt",
]
