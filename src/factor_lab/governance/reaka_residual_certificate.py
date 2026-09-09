"""Inference residual evidence validation without neural-runtime dependencies.

This certificate verifies declared provenance, numeric summaries and identities.
It does not read checkpoint files or establish their declared provenance.
It never establishes predictive improvement, financial success or permission to
train.  Historical teacher-forced outputs remain diagnostic only.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass
from typing import Final, cast

STAGE6_FORMAL_CROSS_ARM_SCHEMA_ID: Final = (
    "factorlab.reaka_stage6_formal_cross_arm_residual_certificate@1.2"
)
FORMAL_ARM_BINDING_KEYS: Final = frozenset({
    "model_state_digest", "checkpoint_digest", "health_certificate_digest",
})
STAGE6_FORMAL_ARM_SCHEMA_ID: Final = "factorlab.reaka_stage6_formal_arm_residual_evidence@1.1"
LEGACY_FORMAL_ARM_SCHEMA_ID: Final = "factorlab.reaka_stage6_formal_arm_residual_evidence@1.0"


def canonical_digest(payload: object) -> str:
    """Preserve the existing Stage6 UTF-8 canonical JSON byte convention."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class Stage6FormalArmResidualEvidence:
    """Actual residual output from one independently trained frozen arm.

    Unlike the auxiliary probes, this evidence is emitted by the fitted arm
    itself on the shared validation support and binds the model/checkpoint.
    """

    arm_id: str
    task_id: str
    sequence_length: int
    latent_dim: int
    operator_count: int
    seed: int
    train_years: tuple[int, ...]
    validation_year: int
    support_digest: str
    model_state_digest: str
    checkpoint_digest: str
    health_certificate_digest: str
    health_certificate_status: str
    true_residual: dict[str, float | None]
    estimated_residual: dict[str, float | None]
    # Legacy objects remain readable, but cannot silently acquire inference
    # evidence authority.  Training x0 reconstruction observes the true
    # residual and is a different experiment from historical-only sampling.
    evidence_source: str = "unspecified_legacy"
    selector_mode: str = "unspecified_legacy"
    reference_residual_source: str = "unspecified_legacy"
    history_only_inputs: bool = False

    @property
    def comparison_identity(self) -> tuple[object, ...]:
        return (
            self.task_id,
            self.sequence_length,
            self.latent_dim,
            self.operator_count,
            self.seed,
            self.train_years,
            self.validation_year,
            self.support_digest,
        )

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_id": STAGE6_FORMAL_ARM_SCHEMA_ID,
            "arm_id": self.arm_id,
            "task_id": self.task_id,
            "sequence_length": self.sequence_length,
            "latent_dim": self.latent_dim,
            "operator_count": self.operator_count,
            "seed": self.seed,
            "train_years": list(self.train_years),
            "validation_year": self.validation_year,
            "support_digest": self.support_digest,
            "model_state_digest": self.model_state_digest,
            "checkpoint_digest": self.checkpoint_digest,
            "health_certificate_digest": self.health_certificate_digest,
            "health_certificate_status": self.health_certificate_status,
            "true_residual": dict(self.true_residual),
            "estimated_residual": dict(self.estimated_residual),
            "evidence_source": self.evidence_source,
            "selector_mode": self.selector_mode,
            "reference_residual_source": self.reference_residual_source,
            "history_only_inputs": self.history_only_inputs,
            "authority": "formal_frozen_arm_output",
            "production_authority": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> Stage6FormalArmResidualEvidence:
        if payload.get("schema_id") not in {STAGE6_FORMAL_ARM_SCHEMA_ID, LEGACY_FORMAL_ARM_SCHEMA_ID}:
            raise ValueError("stage6_formal_arm_evidence_schema_mismatch")
        legacy = payload.get("schema_id") == LEGACY_FORMAL_ARM_SCHEMA_ID
        declared = str(payload.get("canonical_digest", ""))
        recomputed = canonical_digest(
            {key: value for key, value in payload.items() if key != "canonical_digest"}
        )
        if declared != recomputed:
            raise ValueError("stage6_formal_arm_evidence_digest_mismatch")
        if payload.get("authority") != "formal_frozen_arm_output":
            raise ValueError("stage6_formal_arm_evidence_authority_mismatch")
        return cls(
            arm_id=str(payload["arm_id"]),
            task_id=str(payload["task_id"]),
            sequence_length=int(payload["sequence_length"]),
            latent_dim=int(payload["latent_dim"]),
            operator_count=int(payload["operator_count"]),
            seed=int(payload["seed"]),
            train_years=tuple(int(year) for year in cast(list[object], payload["train_years"])),
            validation_year=int(payload["validation_year"]),
            support_digest=str(payload["support_digest"]),
            model_state_digest=str(payload["model_state_digest"]),
            checkpoint_digest=str(payload["checkpoint_digest"]),
            health_certificate_digest=str(payload["health_certificate_digest"]),
            health_certificate_status=str(payload["health_certificate_status"]),
            true_residual={
                str(key): cast(float | None, value)
                for key, value in cast(dict[object, object], payload["true_residual"]).items()
            },
            estimated_residual={
                str(key): cast(float | None, value)
                for key, value in cast(dict[object, object], payload["estimated_residual"]).items()
            },
            evidence_source="unspecified_legacy" if legacy else str(payload.get("evidence_source", "unspecified_legacy")),
            selector_mode="unspecified_legacy" if legacy else str(payload.get("selector_mode", "unspecified_legacy")),
            reference_residual_source=(
                "unspecified_legacy" if legacy else str(payload.get("reference_residual_source", "unspecified_legacy"))
            ),
            history_only_inputs=not legacy and payload.get("history_only_inputs") is True,
        )


FORMAL_CROSS_ARM_IDS: Final = (
    "without_drc",
    "residual_mlp",
    "reaka",
)


def _formal_residual_digest_valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _formal_residual_summary_blockers(
    summary: dict[str, float | None],
    *,
    label: str,
    zero_control: bool = False,
) -> list[str]:
    """Validate measured nonnegative summaries, allowing an undefined zero tail."""

    blockers: list[str] = []
    for key in ("energy", "median_abs", "q95_abs", "tail_ratio"):
        if key not in summary:
            blockers.append(f"formal_residual_summary_missing:{label}:{key}")
            continue
        value = summary[key]
        if key == "tail_ratio" and value is None:
            # q95 / median is undefined when the median is exactly zero.
            if summary.get("median_abs") != 0.0:
                blockers.append(f"formal_residual_summary_invalid:{label}:{key}")
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0.0
        ):
            blockers.append(f"formal_residual_summary_invalid:{label}:{key}")
    if blockers:
        return blockers
    median = cast(float, summary["median_abs"])
    q95 = cast(float, summary["q95_abs"])
    tail = summary["tail_ratio"]
    # A zero mean squared magnitude cannot accompany an ordinary positive
    # absolute quantile.  Restrict this necessary-condition check to normal
    # float64 squares so legitimate squared-value/mean underflow remains
    # diagnostic instead of being rejected by an arbitrary epsilon.
    if summary["energy"] == 0.0 and any(value * value >= sys.float_info.min for value in (median, q95)):
        blockers.append(f"formal_residual_zero_energy_nonzero_quantile:{label}")
    if q95 < median:
        blockers.append(f"formal_residual_quantile_order_invalid:{label}")
    if median == 0.0 and tail is not None:
        blockers.append(f"formal_residual_zero_median_tail_must_be_undefined:{label}")
    if median > 0.0 and not math.isclose(cast(float, tail), q95 / median, rel_tol=1e-6, abs_tol=1e-12):
        blockers.append(f"formal_residual_tail_ratio_inconsistent:{label}")
    if zero_control and (any(summary[key] != 0.0 for key in ("energy", "median_abs", "q95_abs")) or tail is not None):
        blockers.append(f"formal_residual_zero_control_nonzero:{label}")
    return blockers


def build_formal_cross_arm_residual_certificate(
    evidences: tuple[Stage6FormalArmResidualEvidence, ...],
) -> dict[str, object]:
    """Bind real no-residual/MLP/diffusion arm outputs on one support.

    Missing arms, mixed configurations, invalid summaries, and incomplete
    inference provenance fail closed.  Teacher-forced x0 estimates and legacy
    evidence are readable diagnostic materials, never inference acceptance.
    """

    by_arm = {evidence.arm_id: evidence for evidence in evidences}
    blockers: list[str] = []
    if len(by_arm) != len(evidences):
        blockers.append("duplicate_formal_arm_evidence")
    for arm_id in by_arm:
        if arm_id not in FORMAL_CROSS_ARM_IDS:
            blockers.append(f"unexpected_formal_arm:{arm_id}")
    for arm_id in FORMAL_CROSS_ARM_IDS:
        if arm_id not in by_arm:
            blockers.append(f"missing_formal_arm:{arm_id}")
    selected = [by_arm[arm_id] for arm_id in FORMAL_CROSS_ARM_IDS if arm_id in by_arm]
    if selected:
        identity = selected[0].comparison_identity
        for evidence in selected[1:]:
            if evidence.comparison_identity != identity:
                blockers.append(f"formal_arm_comparison_identity_mismatch:{evidence.arm_id}")
        for evidence in selected:
            for label, digest in (
                ("support", evidence.support_digest),
                ("checkpoint", evidence.checkpoint_digest),
                ("model", evidence.model_state_digest),
                ("health", evidence.health_certificate_digest),
            ):
                if not _formal_residual_digest_valid(digest):
                    blockers.append(f"formal_arm_{label}_digest_invalid:{evidence.arm_id}")
            if evidence.health_certificate_status != "passed":
                blockers.append(f"formal_arm_health_not_passed:{evidence.arm_id}")
            if (
                not evidence.task_id
                or evidence.sequence_length < 2
                or evidence.latent_dim < 1
                or evidence.operator_count < 1
                or not evidence.train_years
                or tuple(sorted(set(evidence.train_years))) != evidence.train_years
                or max(evidence.train_years) >= evidence.validation_year
            ):
                blockers.append(f"formal_arm_configuration_invalid:{evidence.arm_id}")
            if (
                evidence.evidence_source != "forecast_history_only"
                or evidence.selector_mode != "argmax_hard"
                or evidence.reference_residual_source != "hard_selector_next_latent_minus_advanced"
                or evidence.history_only_inputs is not True
            ):
                blockers.append(f"formal_arm_inference_provenance_missing:{evidence.arm_id}")
            blockers.extend(_formal_residual_summary_blockers(evidence.true_residual, label=f"{evidence.arm_id}:true"))
            blockers.extend(_formal_residual_summary_blockers(
                evidence.estimated_residual,
                label=f"{evidence.arm_id}:estimated",
                zero_control=evidence.arm_id == "without_drc",
            ))
    arm_payloads = {evidence.arm_id: evidence.as_dict() for evidence in selected}
    payload: dict[str, object] = {
        "schema_id": STAGE6_FORMAL_CROSS_ARM_SCHEMA_ID,
        "status": "blocked" if blockers else "passed",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "required_arms": list(FORMAL_CROSS_ARM_IDS),
        "comparison_identity": (
            {
                "task_id": selected[0].task_id,
                "sequence_length": selected[0].sequence_length,
                "latent_dim": selected[0].latent_dim,
                "operator_count": selected[0].operator_count,
                "seed": selected[0].seed,
                "train_years": list(selected[0].train_years),
                "validation_year": selected[0].validation_year,
                "support_digest": selected[0].support_digest,
            }
            if selected
            else None
        ),
        "arms": arm_payloads,
        "residual_layers": {
            "linear_zero": arm_payloads.get("without_drc", {}).get("estimated_residual"),
            "mlp": arm_payloads.get("residual_mlp", {}).get("estimated_residual"),
            "diffusion": arm_payloads.get("reaka", {}).get("estimated_residual"),
        },
        "latent_coordinate_policy": "within_arm_only_unless_explicit_alignment",
        "acceptance_scope": "declared_numeric_and_metadata_consistency_only",
        "scientific_acceptance_authority": False,
        "checkpoint_file_bytes_verified": False,
        "financial_success_claimed": False,
        "authority": "declared_evidence_consistency_only" if not blockers else "none",
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def formal_cross_arm_residual_certificate_valid(
    payload: object,
    *,
    expected_comparison_identity: dict[str, object] | None = None,
    expected_arm_bindings: dict[str, dict[str, str]] | None = None,
) -> bool:
    """Validate internal evidence and, when supplied, the caller's current identity.

    A consumer must construct both expectations from its own frozen registry,
    not copy them from the artifact being checked.  Every required arm must
    independently bind its model state, checkpoint and health certificate
    digests as well as the shared task/configuration/support.  Supplying only
    one expectation or a partial map fails closed.  Omitting both performs
    only a structural check, never current-run binding.  Matching declarations
    still do not verify physical checkpoint bytes or actual PIT provenance.
    """

    if not isinstance(payload, dict) or payload.get("schema_id") != STAGE6_FORMAL_CROSS_ARM_SCHEMA_ID:
        return False
    arms = payload.get("arms")
    if not isinstance(arms, dict) or set(arms) != set(FORMAL_CROSS_ARM_IDS):
        return False
    try:
        evidences = []
        for arm_id in FORMAL_CROSS_ARM_IDS:
            arm_payload = arms[arm_id]
            if not isinstance(arm_payload, dict) or arm_payload.get("arm_id") != arm_id:
                return False
            evidences.append(Stage6FormalArmResidualEvidence.from_dict(arm_payload))
        rebuilt = build_formal_cross_arm_residual_certificate(tuple(evidences))
        if expected_comparison_identity is not None or expected_arm_bindings is not None:
            if (
                not isinstance(expected_comparison_identity, dict)
                or canonical_digest(expected_comparison_identity) != canonical_digest(rebuilt["comparison_identity"])
                or not isinstance(expected_arm_bindings, dict)
                or set(expected_arm_bindings) != set(FORMAL_CROSS_ARM_IDS)
            ):
                return False
            for evidence in evidences:
                expected = expected_arm_bindings[evidence.arm_id]
                if not isinstance(expected, dict) or set(expected) != FORMAL_ARM_BINDING_KEYS:
                    return False
                if any(
                    not _formal_residual_digest_valid(expected[key])
                    or expected[key] != getattr(evidence, key)
                    for key in FORMAL_ARM_BINDING_KEYS
                ):
                    return False
        actual_digest = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
        return (
            rebuilt["status"] == "passed"
            and payload.get("canonical_digest") == actual_digest
            and actual_digest == rebuilt["canonical_digest"]
        )
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return False
