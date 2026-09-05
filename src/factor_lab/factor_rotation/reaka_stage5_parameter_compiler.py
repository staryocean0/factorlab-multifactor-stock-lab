"""Compile a financial REAKA intent into a closed Stage5 math contract."""

# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false, reportUnnecessaryComparison=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from collections.abc import Mapping

from factor_lab.factor_rotation.reaka_parameter_governance import (
    INITIAL_FACTORLAB_TRAINING_BLOCKERS,
    parameter_scope_gate,
    validate_parameter_catalog,
)
from factor_lab.governance.canonicalization import canonical_digest

FINANCIAL_INTENT_FIELDS = (
    "target",
    "horizon_trading_days",
    "decision_cadence_trading_days",
    "input_arm",
    "factor_identity_count",
    "approved_context_state_count",
    "universe",
    "execution_contract",
)


def _parameter_values(identity: Mapping[str, object]) -> dict[str, object]:
    latent_dim = int(identity["latent_dimension"])
    operator_count = int(identity["entry_operator_count"])
    residual_mode = str(identity["entry_residual_mode"])
    diffusion_active = residual_mode == "diffusion"
    latent_k1_residual = residual_mode == "paper_latent_k1_residual"
    hidden_values = [latent_dim * ratio for ratio in (1, 2, 4)]
    return {
        "data.stock_universe": identity["universe"],
        "encoder.layer_count": 1,
        "network.hidden_dimension": {
            "candidate_values": hidden_values,
            "selection": "smallest_within_one_HAC_SE_of_best_inner_target_metric",
        },
        "koopman.initialization": "training_prefix_regularized_DMD_projected_to_declared_stability_class",
        "selector.gumbel_temperature": (
            "not_applicable_operator_count_1" if operator_count == 1 else "bisection_to_median_entropy_0p5_logK_after_logit_normalization"
        ),
        "selector.gumbel_schedule": ("not_applicable_operator_count_1" if operator_count == 1 else "constant_at_compiled_temperature"),
        "selector.straight_through": False,
        "residual.target_gradient_attachment": ("latent_one_step_residual_may_be_negative" if latent_k1_residual else "stop_gradient"),
        "residual.denoiser_architecture": (
            "not_applicable_diffusion_not_authorized"
            if not diffusion_active
            else {
                "family": "conditional_MLP",
                "widths": [latent_dim, latent_dim * 2, latent_dim * 4],
                "depths": [1, 2],
                "selection": "smallest_within_one_SE_and_no_rank_harm",
            }
        ),
        "residual.time_embedding_dimension": ("not_applicable_diffusion_not_authorized" if not diffusion_active else latent_dim),
        "residual.x0_mapping": ("paper_latent_residual_R_equals_Z_next_minus_Ks_Z" if latent_k1_residual else "identity"),
        "decoder.architecture": {
            "family": "shared_pointwise_one_hidden_layer_MLP",
            "input_dimension": latent_dim,
            "hidden_width_follows": "network.hidden_dimension",
            "output_dimension": 1,
        },
        "loss.scale_normalization": {
            "reduction": "per_observation_per_element_mean",
            "lrec": "two_window_means_summed",
            "coefficients": {"rec": 1.0, "koop": 1.0, "diff": 1.0},
        },
        "optimizer.family": "Adam",
        "optimizer.learning_rate": {
            "calibration_values": [0.0001, 0.0003, 0.001],
            "selection": "largest_stable_step_then_one_SE_target_metric",
        },
        "optimizer.weight_decay": 0.0,
        "training.coverage_budget": {
            "checkpoints_full_cycles": [4, 8, 12],
            "maximum_full_cycles": 12,
        },
        "training.early_stopping": "health_gates_then_inner_rank_metric_one_SE_plateau",
        "training.gradient_clip_norm": "disabled_for_unclipped_preflight_then_tail_quantile_if_required",
        "training.general_initialization": {
            "input_affine": "activation_aware_Xavier",
            "recurrent": "orthogonal",
            "forget_bias": "log_T_minus_1_chrono",
            "koopman": "compiled_DMD_rule",
        },
        "portfolio.rebalance_frequency": {
            "decision_interval_trading_days": identity["decision_cadence_trading_days"],
            "execution": "next_trading_day_open",
            "between_decisions": "carry_shares",
        },
        "portfolio.weighting": "equal_weight_target_subject_to_forced_carry_and_buyability_backfill",
    }


def compile_stage5_calibration_contract(
    catalog: Mapping[str, object],
    root_receipt: Mapping[str, object],
) -> dict[str, object]:
    identity = dict(root_receipt["prediction_identity"])
    values = _parameter_values(identity)
    hidden_values = values["network.hidden_dimension"]["candidate_values"]
    learning_rates = values["optimizer.learning_rate"]["calibration_values"]
    calibration_trials = [
        {
            "trial_id": f"h{hidden}_lr{str(rate).replace('.', 'p')}",
            "hidden_dimension": hidden,
            "learning_rate": rate,
            "operator_count": identity["entry_operator_count"],
            "residual_mode": identity["entry_residual_mode"],
            "gradient_clip": "disabled_measurement",
        }
        for hidden in hidden_values
        for rate in learning_rates
    ]
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage5_parameter_calibration_contract@1.0",
        "status": "stage5_math_compilation_frozen",
        "catalog_digest": catalog["canonical_digest"],
        "root_resolution_digest": root_receipt["canonical_digest"],
        "financial_intent": {key: identity[key] for key in FINANCIAL_INTENT_FIELDS},
        "financial_intent_only_input": True,
        "user_math_inputs_required": [],
        "parameter_values": values,
        "parameter_count": len(values),
        "calibration_preregistration": {
            "trial_count": len(calibration_trials),
            "trials": calibration_trials,
            "screening_seed": 11,
            "confirmation_seeds": [11, 29, 47],
            "all_attempts_count_toward_multiplicity": True,
            "selection_rule": "per_hidden_largest_stable_lr_then_smallest_hidden_within_one_HAC_SE",
            "outer_year_may_select": False,
        },
        "stage5_evidence_bindings": {
            "effective_rank": "docs/ops/reaka_stage6_temporal_coordinate@2.0.json",
            "state_episode_authority": "docs/ops/evidence/reaka_stage3_episode_atlas_v1_20260825/validation_report.json",
            "state_factor_freeze": "docs/ops/evidence/reaka_stage5_context_freeze_v1_20260825/validation_report.json",
            "portfolio_execution_contract": "docs/ops/reaka_stage6_portfolio_execution@1.0.json",
            "root_resolution": "docs/ops/reaka_prediction_root_routing@1.0.json",
        },
        "calibration_generated_receipts": [
            "capacity_ablation",
            "gradient_scale_audit",
            "learning_rate_range_test",
            "solver_health_preflight",
            "unclipped_gradient_distribution",
            "coverage_convergence_receipt",
            "initialization_variance_receipt",
            "dmd_initialization_receipt",
        ],
        "next_stage": (
            "stage6_parameter_calibration_preflight_for_paper_latent_k1_residual"
            if identity.get("entry_residual_mode") == "paper_latent_k1_residual"
            else "stage6_parameter_calibration_preflight"
        ),
        "old_stage6_checkpoints": "historical_only_not_continuable",
        "stage7": "closed",
        "fresh_oos": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def validate_stage5_calibration_contract(
    catalog: Mapping[str, object],
    root_receipt: Mapping[str, object],
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers: list[str] = []
    catalog_validation = validate_parameter_catalog(catalog)
    root_gate = parameter_scope_gate(
        catalog,
        scope="new_factorlab_neural_training",
        root_resolution_receipt=root_receipt,
    )
    if catalog_validation["status"] != "passed":
        blockers.append("catalog_invalid")
    if root_gate["status"] != "passed":
        blockers.append("root_gate_not_resolved")
    if payload.get("catalog_digest") != catalog.get("canonical_digest"):
        blockers.append("stage5_catalog_digest_mismatch")
    if payload.get("root_resolution_digest") != root_receipt.get("canonical_digest"):
        blockers.append("stage5_root_digest_mismatch")
    values = dict(payload.get("parameter_values", {}))
    if tuple(values) != INITIAL_FACTORLAB_TRAINING_BLOCKERS:
        blockers.append("stage5_parameter_identity_or_order_drift")
    if int(payload.get("parameter_count", -1)) != 22:
        blockers.append("stage5_parameter_count_not_22")
    if payload.get("user_math_inputs_required") != []:
        blockers.append("stage5_still_requires_user_math_input")
    if payload.get("financial_intent_only_input") is not True:
        blockers.append("stage5_not_financial_intent_compiled")
    financial_intent = dict(payload.get("financial_intent", {}))
    if tuple(financial_intent) != FINANCIAL_INTENT_FIELDS:
        blockers.append("stage5_financial_intent_identity_drift")
    forbidden_user_math_fields = {
        "latent_dimension",
        "entry_operator_count",
        "entry_residual_mode",
        "hidden_dimension",
        "gumbel_temperature",
        "optimizer",
        "learning_rate",
        "epochs",
    }
    if forbidden_user_math_fields & set(financial_intent):
        blockers.append("stage5_user_input_contains_math_parameter")
    forbidden_fragments = ("historical_default", "current_h20_value")
    serialized = str(values)
    if any(fragment in serialized for fragment in forbidden_fragments):
        blockers.append("stage5_historical_default_leaked")
    trials = dict(payload.get("calibration_preregistration", {}))
    if trials.get("trial_count") != 9 or len(trials.get("trials", [])) != 9:
        blockers.append("stage5_calibration_matrix_not_frozen")
    if trials.get("outer_year_may_select") is not False:
        blockers.append("stage5_outer_year_selection_not_forbidden")
    digest_payload = dict(payload)
    actual_digest = str(digest_payload.pop("canonical_digest", ""))
    if actual_digest != canonical_digest(digest_payload):
        blockers.append("stage5_parameter_contract_digest_mismatch")
    result: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage5_parameter_calibration_validation@1.0",
        "status": "passed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "compiled_parameter_count": len(values),
        "user_math_question_count": len(payload.get("user_math_inputs_required", [])),
        "next_stage": (payload.get("next_stage") if not blockers else None),
        "production_authority": False,
    }
    result["canonical_digest"] = canonical_digest(result)
    return result


__all__ = [
    "FINANCIAL_INTENT_FIELDS",
    "compile_stage5_calibration_contract",
    "validate_stage5_calibration_contract",
]
