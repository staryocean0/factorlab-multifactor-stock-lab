"""The residual health gate must distinguish a conditional mean from a distribution."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from factor_lab.factor_rotation.reaka_stage6_daily_engine import (
    ROW_WIDTH,
    Stage6FitConfig,
    Stage6FitResult,
    Stage6TrainingHealth,
    _train_residual_evidence_probes,
    evaluate_stage6_health_certificate,
    evaluate_stage6r_integrity_certificate,
    fit_stage6_arm,
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
    assert certificate.per_gate["conditional_distribution_validation"]["blocked"] is True


def test_teacher_forced_diffusion_scale_match_cannot_pass_individual_arm_health() -> None:
    certificate = _certificate("diffusion", _health(median_ratio=1.0, q95_ratio=1.0))
    assert certificate.per_gate["predicted_to_true_residual_median_ratio"]["pass"] is True
    assert certificate.per_gate["predicted_to_true_residual_q95_ratio"]["pass"] is True
    assert certificate.status == "blocked"
    assert certificate.blocker_count == 1
    assert certificate.per_gate["conditional_distribution_validation"]["reason"] == "conditional_distribution_validation_missing"


def test_equal_marginal_distributions_do_not_establish_conditional_predictions() -> None:
    # Both sample vectors have exactly the observed marginal distribution;
    # only one respects the sign learned from the available condition.
    realized = np.array([-2.0, -1.0, 1.0, 2.0])
    good = realized.copy()
    wrong_condition = -realized
    np.testing.assert_array_equal(np.sort(good), np.sort(wrong_condition))
    assert np.mean((realized - good) ** 2) < np.mean((realized - wrong_condition) ** 2)
    certificate = _certificate("diffusion", _health(median_ratio=1.0, q95_ratio=1.0))
    assert certificate.per_gate["conditional_distribution_validation"]["blocked"] is True


@pytest.mark.parametrize("mode", ["unknown", "MLP", ""])
def test_unknown_residual_mode_is_rejected(mode: str) -> None:
    with pytest.raises(ValueError, match="stage6_residual_mode_unknown"):
        _certificate(mode)


@pytest.mark.parametrize("operator_count", [0, -1, True, 1.5])
def test_invalid_operator_count_cannot_inherit_single_operator_exemption(operator_count: object) -> None:
    with pytest.raises(ValueError, match="stage6_operator_count_must_be_positive_integer"):
        evaluate_stage6_health_certificate(
            fit_label="synthetic_no_training", health=_health(),
            operator_count=operator_count, residual_mode="none", require_four_residual=False,
        )


def test_passed_legacy_health_has_no_scientific_or_residual_acceptance_authority() -> None:
    payload = _certificate("none").as_dict()
    assert payload["status"] == "passed"
    assert payload["threshold_authority"] == "historical_project_policy_not_mathematical_identity"
    assert payload["scientific_acceptance_authority"] is False
    assert payload["formal_residual_acceptance_authority"] is False


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


def _current_arm_bindings() -> dict[str, dict[str, str]]:
    # Frozen independently of the certificate received by the consumer.
    return {arm_id: {
        "model_state_digest": "sha256:" + "b" * 64,
        "checkpoint_digest": "sha256:" + "c" * 64,
        "health_certificate_digest": "sha256:" + "d" * 64,
    } for arm_id in FORMAL_CROSS_ARM_IDS}


def _formal_certificate(*, checkpoint_digest: str = "sha256:" + "c" * 64, **changes: object) -> dict[str, object]:
    identity = {**_current_identity(), **changes}
    identity["train_years"] = tuple(identity["train_years"])
    positive = {"energy": 1.0, "median_abs": 0.5, "q95_abs": 2.0, "tail_ratio": 4.0}
    zero = {"energy": 0.0, "median_abs": 0.0, "q95_abs": 0.0, "tail_ratio": None}
    return build_formal_cross_arm_residual_certificate(tuple(
        Stage6FormalArmResidualEvidence(
            arm_id=arm_id, **identity,
            model_state_digest="sha256:" + "b" * 64,
            checkpoint_digest=checkpoint_digest,
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
        expected_arm_bindings=_current_arm_bindings(),
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


def test_same_task_and_support_from_another_checkpoint_is_blocked() -> None:
    artifact = _formal_certificate(checkpoint_digest="sha256:" + "e" * 64)
    assert artifact["status"] == "passed"
    result = _bound_health_certificate(artifact, _current_identity())
    assert result.status == "blocked"
    assert result.per_gate["formal_cross_arm_residual_certificate"]["reason"] == "formal_cross_arm_certificate_missing_blocked_or_binding_mismatch"


def test_health_consumer_cannot_use_certificate_as_its_own_checkpoint_registry() -> None:
    result = evaluate_stage6_health_certificate(
        fit_label="current_run", health=_health(), operator_count=1,
        residual_mode="none", require_four_residual=True,
        formal_cross_arm_certificate=_formal_certificate(),
        expected_comparison_identity=_current_identity(),
    )
    assert result.status == "blocked"
    assert result.per_gate["formal_cross_arm_residual_certificate"]["reason"] == "formal_cross_arm_expected_arm_bindings_missing"


def test_claimed_context_must_match_health_support_and_explicit_operator_count() -> None:
    for changes in ({"operator_count": 2}, {"support_digest": "sha256:" + "e" * 64}):
        artifact = _formal_certificate(**changes)
        asserted_context = {**_current_identity(), **changes}
        result = _bound_health_certificate(artifact, asserted_context)
        assert result.status == "blocked"
        assert result.per_gate["formal_cross_arm_residual_certificate"]["reason"] == "formal_cross_arm_current_identity_mismatch"


def test_valid_cross_arm_summary_cannot_close_missing_conditional_distribution_validation() -> None:
    result = evaluate_stage6_health_certificate(
        fit_label="current_run", health=_health(median_ratio=1.0, q95_ratio=1.0),
        operator_count=1, residual_mode="diffusion", require_four_residual=True,
        formal_cross_arm_certificate=_formal_certificate(),
        expected_comparison_identity=_current_identity(),
        expected_arm_bindings=_current_arm_bindings(),
    )
    assert result.per_gate["formal_cross_arm_residual_certificate"]["pass"] is True
    assert result.per_gate["conditional_distribution_validation"]["blocked"] is True
    assert result.status == "blocked"


def _integrity_certificate() -> dict[str, object]:
    return evaluate_stage6r_integrity_certificate(
        fit_label="synthetic_no_training",
        health=replace(_health(), active_module_gradient_norms={"encoder": 0.1}),
        validation_learning_curve=({"coverage_cycle": 1, "total_loss": 0.5},),
        model_parameters_finite=True,
    )


def _diagnostic_result(certificate: dict[str, object]) -> Stage6FitResult:
    return Stage6FitResult(
        config=Stage6FitConfig(
            arm_id="reaka", task_id="daily::h20", sequence_length=10,
            latent_dim=8, operator_count=1, seed=11,
            train_years=(2009, 2010, 2011), validation_year=2012,
        ),
        first_epoch_losses={"total_loss": 1.0}, last_epoch_losses={"total_loss": 0.5},
        epoch_count=1, stopped_early=False, health=_health(),
        validation_score_rows=np.zeros((1, ROW_WIDTH), dtype=np.int64),
        validation_scores=np.array([0.1]), operator_ids=np.array([0]),
        diagnostic_rows=np.zeros((0, ROW_WIDTH), dtype=np.int64),
        diagnostic_scores=np.array([]), diagnostic_cross_year_count=0,
        train_row_count=4, validation_row_count=1, diagnostic_row_count=0,
        peak_rss_mib=1.0, elapsed_seconds=0.0, model_state_digest="sha256:" + "b" * 64,
        checkpoint_path="diagnostic-only.pt", health_certificate=certificate,
        adjudication_mode="stage6r_integrity_only",
    )


def test_numerical_integrity_pass_is_explicitly_diagnostic() -> None:
    certificate = _integrity_certificate()
    assert certificate["status"] == "passed"
    assert certificate["scientific_role"] == "execution_integrity_only"
    assert certificate["health_acceptance_authority"] is False
    assert certificate["scientific_acceptance_authority"] is False
    assert certificate["formal_residual_acceptance_authority"] is False
    result = _diagnostic_result(certificate).as_dict()
    assert result["validation_score_row_count"] == 1  # Research diagnostics remain usable.
    assert result["adjudication_mode"] == "stage6r_integrity_only"
    assert result["formal_arm_residual_evidence"] is None
    assert result["formal_residual_acceptance_authority"] is False


@pytest.mark.parametrize("relabel_certificate", [False, True])
def test_integrity_mode_cannot_emit_formal_residual_evidence(relabel_certificate: bool) -> None:
    certificate = _integrity_certificate()
    if relabel_certificate:
        # The execution mode is independently bound to the fit result.
        certificate = {**certificate, "schema_id": "claimed_formal", "scientific_role": "claimed_formal"}
    result = replace(_diagnostic_result(certificate), formal_arm_residual_evidence={"status": "passed"})
    with pytest.raises(ValueError, match="stage6_integrity_only_result_contains_formal_residual_evidence"):
        result.as_dict()


def test_legacy_integrity_schema_cannot_gain_authority_by_omitting_role() -> None:
    certificate = {"schema_id": "factorlab.reaka_stage6r_integrity_certificate@1.0", "status": "passed"}
    result = replace(
        _diagnostic_result(certificate), adjudication_mode="legacy_fail_closed",
        formal_arm_residual_evidence={"status": "passed"},
    )
    with pytest.raises(ValueError, match="stage6_integrity_only_result_contains_formal_residual_evidence"):
        result.as_dict()


@pytest.mark.parametrize("mode", ["legacy_fail_closed", "stage6r_integrity_only"])
def test_frozen_fit_blocks_before_config_data_or_checkpoint_access(mode: str, tmp_path) -> None:
    # None would fail immediately on config/data access if the current
    # foundation gate were reached too late.  No model or market data run.
    checkpoint_dir = tmp_path / "checkpoints"
    with pytest.raises(PermissionError, match="REAKA"):
        fit_stage6_arm(
            shared=None, spec=None, rows_by_year=None, config=None,
            adjudication_mode=mode, checkpoint_dir=checkpoint_dir,
        )
    assert list(tmp_path.iterdir()) == []


def test_frozen_residual_probes_block_before_tensor_or_optimizer_access() -> None:
    with pytest.raises(PermissionError, match="REAKA"):
        _train_residual_evidence_probes(
            train_latent=None, train_residual=None, latent=None,
            true_residual=None, model_config=None, device=None, seed=11,
        )
