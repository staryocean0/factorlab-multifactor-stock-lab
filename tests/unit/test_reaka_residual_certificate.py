"""Residual evidence counterexamples; these tests never construct or train a model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from factor_lab.governance.reaka_residual_certificate import (
    FORMAL_CROSS_ARM_IDS,
    LEGACY_FORMAL_ARM_SCHEMA_ID,
    Stage6FormalArmResidualEvidence,
    build_formal_cross_arm_residual_certificate,
    canonical_digest,
    formal_cross_arm_residual_certificate_valid,
)


def _evidence(arm_id: str) -> Stage6FormalArmResidualEvidence:
    positive = {"energy": 1.0, "median_abs": 0.5, "q95_abs": 2.0, "tail_ratio": 4.0}
    zero = {"energy": 0.0, "median_abs": 0.0, "q95_abs": 0.0, "tail_ratio": None}
    return Stage6FormalArmResidualEvidence(
        arm_id=arm_id,
        task_id="synthetic_h20",
        sequence_length=10,
        latent_dim=8,
        operator_count=2,
        seed=11,
        train_years=(2010, 2011),
        validation_year=2012,
        support_digest="sha256:" + "a" * 64,
        model_state_digest="sha256:" + "b" * 64,
        checkpoint_digest="sha256:" + "c" * 64,
        health_certificate_digest="sha256:" + "d" * 64,
        health_certificate_status="passed",
        true_residual=dict(positive),
        estimated_residual=dict(zero if arm_id == "without_drc" else positive),
        evidence_source="forecast_history_only",
        selector_mode="argmax_hard",
        reference_residual_source="hard_selector_next_latent_minus_advanced",
        history_only_inputs=True,
    )


def _arms() -> tuple[Stage6FormalArmResidualEvidence, ...]:
    return tuple(_evidence(arm_id) for arm_id in FORMAL_CROSS_ARM_IDS)


def _current_identity() -> dict[str, object]:
    return {
        "task_id": "synthetic_h20", "sequence_length": 10, "latent_dim": 8,
        "operator_count": 2, "seed": 11, "train_years": [2010, 2011],
        "validation_year": 2012, "support_digest": "sha256:" + "a" * 64,
    }


def _current_arm_bindings() -> dict[str, dict[str, str]]:
    # Independent fixture registry, never copied from the received certificate.
    return {arm_id: {
        "model_state_digest": "sha256:" + "b" * 64,
        "checkpoint_digest": "sha256:" + "c" * 64,
        "health_certificate_digest": "sha256:" + "d" * 64,
    } for arm_id in FORMAL_CROSS_ARM_IDS}


def _replace_last(**changes: object) -> tuple[Stage6FormalArmResidualEvidence, ...]:
    arms = _arms()
    return (*arms[:-1], replace(arms[-1], **changes))


def _resign(payload: dict[str, object]) -> None:
    payload["canonical_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})


def test_valid_history_only_evidence_passes_identity_check_without_financial_claim() -> None:
    result = build_formal_cross_arm_residual_certificate(_arms())
    assert result["status"] == "passed"
    assert formal_cross_arm_residual_certificate_valid(result)
    assert result["financial_success_claimed"] is False
    assert result["acceptance_scope"] == "declared_numeric_and_metadata_consistency_only"
    assert result["scientific_acceptance_authority"] is False
    assert result["checkpoint_file_bytes_verified"] is False
    assert result["authority"] == "declared_evidence_consistency_only"
    assert result["latent_coordinate_policy"] == "within_arm_only_unless_explicit_alignment"


@pytest.mark.parametrize("field", ["true_residual", "estimated_residual"])
@pytest.mark.parametrize("key", ["energy", "median_abs", "q95_abs", "tail_ratio"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, True, "1.0"])
def test_all_residual_summary_values_require_finite_nonnegative_numbers(field: str, key: str, bad: object) -> None:
    summary = dict(getattr(_evidence("reaka"), field))
    summary[key] = bad
    result = build_formal_cross_arm_residual_certificate(_replace_last(**{field: summary}))
    assert result["status"] == "blocked"
    assert result["authority"] == "none"


@pytest.mark.parametrize("field", ["true_residual", "estimated_residual"])
@pytest.mark.parametrize("key", ["energy", "median_abs", "q95_abs", "tail_ratio"])
def test_missing_summary_field_is_rejected(field: str, key: str) -> None:
    summary = dict(getattr(_evidence("reaka"), field))
    del summary[key]
    result = build_formal_cross_arm_residual_certificate(_replace_last(**{field: summary}))
    assert result["status"] == "blocked"


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_source": "teacher_forced_training_objective"},
        {"evidence_source": "unspecified_legacy"},
        {"selector_mode": "gumbel_soft"},
        {"reference_residual_source": "training_next_latent_minus_soft_advanced"},
        {"history_only_inputs": False},
    ],
)
def test_teacher_forced_or_unverified_provenance_cannot_receive_formal_authority(changes: dict[str, object]) -> None:
    result = build_formal_cross_arm_residual_certificate(_replace_last(**changes))
    assert result["status"] == "blocked"
    assert "formal_arm_inference_provenance_missing:reaka" in result["blockers"]


def test_legacy_payload_remains_readable_but_cannot_claim_inference_provenance() -> None:
    payload = _evidence("reaka").as_dict()
    payload["schema_id"] = LEGACY_FORMAL_ARM_SCHEMA_ID
    # Even added source strings cannot retroactively change a v1.0 receipt.
    _resign(payload)
    legacy = Stage6FormalArmResidualEvidence.from_dict(payload)
    assert legacy.evidence_source == "unspecified_legacy"
    assert legacy.history_only_inputs is False
    result = build_formal_cross_arm_residual_certificate((*_arms()[:-1], legacy))
    assert result["status"] == "blocked"


@pytest.mark.parametrize("field", ["support_digest", "checkpoint_digest", "model_state_digest", "health_certificate_digest"])
@pytest.mark.parametrize("bad", ["", "sha256:", "sha256:" + "g" * 64])
def test_complete_sha256_binding_required(field: str, bad: str) -> None:
    result = build_formal_cross_arm_residual_certificate(_replace_last(**{field: bad}))
    assert result["status"] == "blocked"


def test_missing_duplicate_unexpected_and_mismatched_arms_are_rejected() -> None:
    arms = _arms()
    candidates = (
        arms[:-1],
        (*arms, arms[-1]),
        (*arms, replace(arms[-1], arm_id="auxiliary_probe")),
        (*arms[:-1], replace(arms[-1], latent_dim=16)),
    )
    for candidate in candidates:
        assert build_formal_cross_arm_residual_certificate(candidate)["status"] == "blocked"


def test_zero_control_and_summary_consistency_are_checked() -> None:
    arms = _arms()
    bad_control = replace(arms[0], estimated_residual=dict(arms[-1].estimated_residual))
    assert build_formal_cross_arm_residual_certificate((bad_control, *arms[1:]))["status"] == "blocked"
    for summary in (
        {"energy": 1.0, "median_abs": 2.0, "q95_abs": 1.0, "tail_ratio": 0.5},
        {"energy": 1.0, "median_abs": 0.5, "q95_abs": 2.0, "tail_ratio": 3.0},
        {"energy": 1.0, "median_abs": 0.5, "q95_abs": 2.0, "tail_ratio": None},
        {"energy": 0.0, "median_abs": 0.0, "q95_abs": 0.0, "tail_ratio": 0.0},
    ):
        assert build_formal_cross_arm_residual_certificate(_replace_last(estimated_residual=summary))["status"] == "blocked"


def test_zero_median_with_nonzero_tail_quantile_allows_undefined_ratio() -> None:
    summary = {"energy": 1.0, "median_abs": 0.0, "q95_abs": 2.0, "tail_ratio": None}
    result = build_formal_cross_arm_residual_certificate(_replace_last(estimated_residual=summary))
    assert result["status"] == "passed"


def test_consumer_rejects_self_reported_pass_and_rehashed_teacher_forced_evidence() -> None:
    assert not formal_cross_arm_residual_certificate_valid({"status": "passed", "authority": "formal_cross_arm_acceptance_authority"})
    result = build_formal_cross_arm_residual_certificate(_replace_last(evidence_source="teacher_forced_training_objective"))
    result["status"] = "passed"
    result["authority"] = "formal_cross_arm_acceptance_authority"
    result["blockers"] = []
    result["blocker_count"] = 0
    _resign(result)
    assert not formal_cross_arm_residual_certificate_valid(result)


def test_consumer_rejects_nested_tamper_even_if_outer_digest_is_recomputed() -> None:
    result = deepcopy(build_formal_cross_arm_residual_certificate(_arms()))
    result["arms"]["reaka"]["estimated_residual"]["energy"] = 9.0
    _resign(result)
    assert not formal_cross_arm_residual_certificate_valid(result)


def test_consumer_binds_arm_keys_and_rejects_noncurrent_schema() -> None:
    result = build_formal_cross_arm_residual_certificate(_arms())
    result["arms"]["reaka"], result["arms"]["residual_mlp"] = result["arms"]["residual_mlp"], result["arms"]["reaka"]
    _resign(result)
    assert not formal_cross_arm_residual_certificate_valid(result)
    current = build_formal_cross_arm_residual_certificate(_arms())
    current["schema_id"] = "factorlab.reaka_stage6_formal_cross_arm_residual_certificate@1.0"
    _resign(current)
    assert not formal_cross_arm_residual_certificate_valid(current)


@pytest.mark.parametrize("field,bad", [
    ("task_id", "another_task"),
    ("support_digest", "sha256:" + "e" * 64),
    ("operator_count", 4),
    ("seed", 29),
])
def test_valid_certificate_cannot_be_transplanted_to_another_current_identity(field: str, bad: object) -> None:
    current_identity = _current_identity()
    certificate = build_formal_cross_arm_residual_certificate(_arms())
    assert formal_cross_arm_residual_certificate_valid(
        certificate, expected_comparison_identity=current_identity, expected_arm_bindings=_current_arm_bindings(),
    )
    current_identity[field] = bad
    assert not formal_cross_arm_residual_certificate_valid(
        certificate, expected_comparison_identity=current_identity, expected_arm_bindings=_current_arm_bindings(),
    )


def test_partial_comparison_identity_does_not_bind_a_current_run() -> None:
    certificate = build_formal_cross_arm_residual_certificate(_arms())
    assert not formal_cross_arm_residual_certificate_valid(
        certificate, expected_comparison_identity={"operator_count": 2, "support_digest": "sha256:" + "a" * 64},
        expected_arm_bindings=_current_arm_bindings(),
    )


@pytest.mark.parametrize("field", ["checkpoint_digest", "model_state_digest", "health_certificate_digest"])
def test_same_task_and_support_with_different_arm_identity_is_not_current(field: str) -> None:
    certificate = build_formal_cross_arm_residual_certificate(_replace_last(**{field: "sha256:" + "e" * 64}))
    assert formal_cross_arm_residual_certificate_valid(certificate)  # Valid declared metadata for another arm.
    assert not formal_cross_arm_residual_certificate_valid(
        certificate, expected_comparison_identity=_current_identity(), expected_arm_bindings=_current_arm_bindings(),
    )


@pytest.mark.parametrize("missing", ["all_arms", "one_arm", "one_digest", "comparison"])
def test_partial_independent_bindings_cannot_establish_current_run(missing: str) -> None:
    certificate = build_formal_cross_arm_residual_certificate(_arms())
    identity = _current_identity()
    bindings = _current_arm_bindings()
    if missing == "all_arms":
        bindings = None
    elif missing == "one_arm":
        del bindings["reaka"]
    elif missing == "one_digest":
        del bindings["reaka"]["checkpoint_digest"]
    else:
        identity = None
    assert not formal_cross_arm_residual_certificate_valid(
        certificate, expected_comparison_identity=identity, expected_arm_bindings=bindings,
    )


@pytest.mark.parametrize("field", ["true_residual", "estimated_residual"])
def test_zero_energy_cannot_have_nonzero_representable_absolute_quantiles(field: str) -> None:
    summary = {"energy": 0.0, "median_abs": 0.5, "q95_abs": 2.0, "tail_ratio": 4.0}
    result = build_formal_cross_arm_residual_certificate(_replace_last(**{field: summary}))
    assert result["status"] == "blocked"
    assert f"formal_residual_zero_energy_nonzero_quantile:reaka:{'true' if field == 'true_residual' else 'estimated'}" in result["blockers"]


def test_underflow_scale_zero_energy_is_not_rejected_by_an_arbitrary_epsilon() -> None:
    summary = {"energy": 0.0, "median_abs": 1e-200, "q95_abs": 2e-200, "tail_ratio": 2.0}
    result = build_formal_cross_arm_residual_certificate(_replace_last(estimated_residual=summary))
    assert result["status"] == "passed"
