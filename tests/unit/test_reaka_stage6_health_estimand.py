"""The residual health gate must distinguish a conditional mean from a distribution."""

from __future__ import annotations

from dataclasses import replace

from factor_lab.factor_rotation.reaka_stage6_daily_engine import (
    Stage6TrainingHealth,
    evaluate_stage6_health_certificate,
)
from factor_lab.governance.reaka_residual_certificate import (
    FORMAL_CROSS_ARM_IDS,
    Stage6FormalArmResidualEvidence,
    build_formal_cross_arm_residual_certificate,
)


def _health(*, median_ratio: float = 0.1, q95_ratio: float = 0.1) -> Stage6TrainingHealth:
    return Stage6TrainingHealth(
        first_epoch_losses={"total_loss": 1.0},
        last_epoch_losses={"total_loss": 0.5},
        loss_improvement_fraction={"total_loss": 0.5},
        minimum_loss_improvement_fraction=0.05,
        active_module_gradient_norms={},
        shared_encoder_gradient_angles={},
        soft_operator_occupancy={"0": 1.0},
        n_observations=100,
        n_k_eff={"total": 100.0},
        n_k_eff_over_d_squared={"total": 100.0},
        operator_condition_numbers={"0": 1.0},
        perturbed_score_rank_correlation=1.0,
        perturbed_operator_assignment_agreement=1.0,
        residual_energy={"ratio_true_over_advanced": 1.0},
        predicted_to_true_residual_median_ratio=median_ratio,
        predicted_to_true_residual_q95_ratio=q95_ratio,
        residual_tail_ratio_q95_over_median=1.1,
        input_ood_fraction=0.0,
        gate_mean=0.5,
        deterministic_replay_max_abs_delta=0.0,
        common_support_digest="sha256:" + "a" * 64,
        four_residual_common_support={},
    )


def _certificate(mode: str, health: Stage6TrainingHealth | None = None):
    return evaluate_stage6_health_certificate(
        fit_label="synthetic_no_training",
        health=health or _health(),
        operator_count=1,
        residual_mode=mode,
        require_four_residual=False,
    )


def test_optimal_small_conditional_mean_is_not_rejected_for_missing_noise_amplitude() -> None:
    # R = 0.1 Z + epsilon; all four independent +/-1 outcomes are represented.
    residual = [0.1 * z + noise for z in (-1.0, 1.0) for noise in (-1.0, 1.0)]
    conditional_mean = [0.1 * z for z in (-1.0, 1.0) for _ in (-1.0, 1.0)]
    mean_error = sum((r - mean) ** 2 for r, mean in zip(residual, conditional_mean, strict=True)) / 4
    zero_error = sum(r**2 for r in residual) / 4
    assert mean_error < zero_error
    assert max(abs(value) for value in conditional_mean) / max(abs(value) for value in residual) < 0.5

    certificate = _certificate("mlp")
    for key in ("predicted_to_true_residual_median_ratio", "predicted_to_true_residual_q95_ratio"):
        gate = certificate.per_gate[key]
        assert gate["blocked"] is False
        assert gate["reason"] == "not_applicable_conditional_mean"
        assert gate["value"] == 0.1
    # This counterexample is not a certificate for an actual fitted model.
    assert certificate.status == "blocked"
    assert certificate.per_gate["conditional_mean_validation"]["reason"] == "conditional_mean_validation_missing"


def test_mlp_amplitude_matching_cannot_substitute_for_mean_error_validation() -> None:
    certificate = _certificate("mlp", _health(median_ratio=1.0, q95_ratio=1.0))
    assert certificate.status == "blocked"
    assert certificate.per_gate["conditional_mean_validation"]["blocked"] is True
    assert certificate.blocker_count == 1


def test_marginal_residual_energies_do_not_establish_prediction_error() -> None:
    residual = [-1.0, 1.0]
    good = [-0.1, 0.1]
    bad = [0.1, -0.1]
    assert sum(value**2 for value in good) == sum(value**2 for value in bad)
    assert sum((r - p) ** 2 for r, p in zip(residual, good, strict=True)) < sum(
        (r - p) ** 2 for r, p in zip(residual, bad, strict=True)
    )
    health = replace(_health(), residual_energy={"ratio_true_over_advanced": 1.0, "estimated": 0.01, "true": 1.01})
    assert _certificate("mlp", health).per_gate["conditional_mean_validation"]["blocked"] is True


def test_no_residual_arm_remains_exempt_from_residual_estimation_gates() -> None:
    certificate = _certificate("none", _health(median_ratio=0.0, q95_ratio=0.0))
    assert certificate.status == "passed"
    assert "conditional_mean_validation" not in certificate.per_gate
    assert certificate.per_gate["predicted_to_true_residual_q95_ratio"]["reason"] == "not_applicable_no_residual_arm"


def test_diffusion_retains_scale_gates_and_requires_separate_distribution_evidence() -> None:
    certificate = _certificate("diffusion")
    assert certificate.status == "blocked"
    for key in ("predicted_to_true_residual_median_ratio", "predicted_to_true_residual_q95_ratio"):
        gate = certificate.per_gate[key]
        assert gate["blocked"] is True
        assert gate["estimand"] == "conditional_residual_distribution"
        assert gate["history_only_distribution_validation_required"] is True
        assert gate["measurement_source"] == "legacy_teacher_forced_training_objective"


def test_conditional_mean_change_preserves_unrelated_health_failures() -> None:
    certificate = _certificate("mlp", replace(_health(), input_ood_fraction=0.25))
    assert certificate.per_gate["conditional_mean_validation"]["blocked"] is True
    assert certificate.per_gate["input_ood_fraction"]["blocked"] is True
    assert certificate.blocker_count == 2


def _current_identity() -> dict[str, object]:
    return {
        "task_id": "current_h20", "sequence_length": 10, "latent_dim": 8,
        "operator_count": 1, "seed": 11, "train_years": [2010, 2011],
        "validation_year": 2012, "support_digest": "sha256:" + "a" * 64,
    }


def _formal_certificate(**changes: object) -> dict[str, object]:
    identity = {**_current_identity(), **changes}
    identity["train_years"] = tuple(identity["train_years"])
    positive = {"energy": 1.0, "median_abs": 0.5, "q95_abs": 2.0, "tail_ratio": 4.0}
    zero = {"energy": 0.0, "median_abs": 0.0, "q95_abs": 0.0, "tail_ratio": None}
    return build_formal_cross_arm_residual_certificate(tuple(
        Stage6FormalArmResidualEvidence(
            arm_id=arm_id, **identity,
            model_state_digest="sha256:" + "b" * 64,
            checkpoint_digest="sha256:" + "c" * 64,
            health_certificate_digest="sha256:" + "d" * 64,
            health_certificate_status="passed",
            true_residual=positive,
            estimated_residual=zero if arm_id == "without_drc" else positive,
            evidence_source="forecast_history_only",
            selector_mode="argmax_hard",
            reference_residual_source="hard_selector_next_latent_minus_advanced",
            history_only_inputs=True,
        ) for arm_id in FORMAL_CROSS_ARM_IDS
    ))


def _bound_health_certificate(
    artifact: dict[str, object],
    current: dict[str, object] | None,
    health: Stage6TrainingHealth | None = None,
):
    return evaluate_stage6_health_certificate(
        fit_label="current_run", health=health or _health(), operator_count=1,
        residual_mode="none", require_four_residual=True,
        formal_cross_arm_certificate=artifact, expected_comparison_identity=current,
    )


def test_cross_arm_health_consumer_requires_current_context() -> None:
    artifact = _formal_certificate()
    assert _bound_health_certificate(artifact, _current_identity()).status == "passed"
    missing = _bound_health_certificate(artifact, None)
    assert missing.status == "blocked"
    assert missing.per_gate["formal_cross_arm_residual_certificate"]["reason"] == "formal_cross_arm_current_identity_missing"
    assert _bound_health_certificate(artifact, _current_identity(), replace(_health(), common_support_digest=None)).status == "blocked"


def test_cross_task_support_and_operator_count_transplants_are_blocked() -> None:
    for changes in (
        {"task_id": "another_task"},
        {"support_digest": "sha256:" + "e" * 64},
        {"operator_count": 2},
    ):
        artifact = _formal_certificate(**changes)
        assert artifact["status"] == "passed"  # Structurally valid for a different run.
        assert _bound_health_certificate(artifact, _current_identity()).status == "blocked"


def test_claimed_context_must_match_health_support_and_explicit_operator_count() -> None:
    for changes in ({"operator_count": 2}, {"support_digest": "sha256:" + "e" * 64}):
        artifact = _formal_certificate(**changes)
        asserted_context = {**_current_identity(), **changes}
        result = _bound_health_certificate(artifact, asserted_context)
        assert result.status == "blocked"
        assert result.per_gate["formal_cross_arm_residual_certificate"]["reason"] == "formal_cross_arm_current_identity_mismatch"
