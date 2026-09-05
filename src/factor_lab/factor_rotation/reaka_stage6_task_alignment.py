"""Pre-fit factor-evidence to Stage 6 task alignment.

The old Stage 6 runner accepted any frozen tensor task requested by a
controller.  It did not prove that the input factors were discovered at the
same prediction horizon.  This successor module makes that relationship an
input identity: mixed-horizon material is split before model construction,
and an unavailable exact horizon fails closed instead of falling back to a
shorter target.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

from factor_lab.factor_rotation.reaka_stage6_daily_engine import (
    ROW_WIDTH,
    Stage6SharedTensor,
    Stage6TaskSpec,
    Stage6TicketChannel,
    sha256_file,
)
from factor_lab.governance.canonicalization import canonical_digest

InputMode = Literal["raw", "spatial", "follow"]


@dataclass(frozen=True, slots=True)
class FactorEvidenceIdentity:
    """One immutable factor identity at one empirically supported horizon."""

    factor_id: str
    horizon_days: int
    candidate_id: str
    input_mode: InputMode
    descriptor_id: str = ""
    quantile_bins: tuple[int, ...] = ()

    def validate(self) -> None:
        if not self.factor_id or not self.candidate_id:
            raise ValueError("stage6_alignment_factor_identity_empty")
        if self.horizon_days <= 0:
            raise ValueError("stage6_alignment_horizon_nonpositive")
        if self.input_mode == "spatial":
            if not self.descriptor_id or not self.quantile_bins:
                raise ValueError("stage6_alignment_spatial_identity_incomplete")
            if any(value < 0 or value > 4 for value in self.quantile_bins):
                raise ValueError("stage6_alignment_spatial_bin_invalid")
        elif self.descriptor_id or self.quantile_bins:
            raise ValueError("stage6_alignment_nonspatial_mask_present")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "factor_id": self.factor_id,
            "horizon_days": self.horizon_days,
            "candidate_id": self.candidate_id,
            "input_mode": self.input_mode,
            "descriptor_id": self.descriptor_id,
            "quantile_bins": list(self.quantile_bins),
        }


@dataclass(frozen=True, slots=True)
class AlignedInputArm:
    """Horizon-pure input arm frozen before predictions are read."""

    arm_id: str
    evidence_horizon_days: int
    cadence_id: str
    sequence_length: int
    identities: tuple[FactorEvidenceIdentity, ...]
    common_support_factor_ids: tuple[str, ...]

    def validate(self) -> None:
        if not self.arm_id or not self.identities:
            raise ValueError("stage6_alignment_arm_empty")
        if any(
            item.horizon_days != self.evidence_horizon_days
            for item in self.identities
        ):
            raise ValueError("stage6_alignment_mixed_horizon_arm")
        expected = task_parameters_for_horizon(self.evidence_horizon_days)
        if (self.cadence_id, self.sequence_length) != expected:
            raise ValueError("stage6_alignment_task_parameter_mismatch")
        factor_ids = [item.factor_id for item in self.identities]
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("stage6_alignment_factor_emitted_more_than_once")
        if not self.common_support_factor_ids:
            raise ValueError("stage6_alignment_common_support_empty")
        if not set(self.common_support_factor_ids).issubset(factor_ids):
            raise ValueError("stage6_alignment_common_support_not_in_arm")
        for item in self.identities:
            item.validate()

    @property
    def task_id(self) -> str:
        return f"{self.cadence_id}::h{self.evidence_horizon_days}"

    def as_dict(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = {
            "arm_id": self.arm_id,
            "evidence_horizon_days": self.evidence_horizon_days,
            "task_id": self.task_id,
            "cadence_id": self.cadence_id,
            "sequence_length": self.sequence_length,
            "factor_count": len(self.identities),
            "factor_identities": [item.as_dict() for item in self.identities],
            "common_support_factor_ids": list(self.common_support_factor_ids),
            "horizon_fallback_allowed": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


HORIZON_TASK_PARAMETERS: Final[Mapping[int, tuple[str, int]]] = {
    5: ("daily", 10),
    20: ("weekly", 40),
    60: ("biweekly", 120),
}


def task_parameters_for_horizon(horizon_days: int) -> tuple[str, int]:
    """Return the preregistered lowest-capacity task for an evidence scale."""

    try:
        return HORIZON_TASK_PARAMETERS[int(horizon_days)]
    except KeyError as exc:
        raise ValueError(
            f"stage6_alignment_horizon_has_no_parameter_contract:{horizon_days}"
        ) from exc


def split_horizon_pure(
    identities: Iterable[FactorEvidenceIdentity],
) -> dict[int, tuple[FactorEvidenceIdentity, ...]]:
    """Split mixed evidence into deterministic, horizon-pure groups."""

    groups: dict[int, list[FactorEvidenceIdentity]] = {}
    for item in identities:
        item.validate()
        groups.setdefault(item.horizon_days, []).append(item)
    return {
        horizon: tuple(sorted(items, key=lambda value: value.factor_id))
        for horizon, items in sorted(groups.items())
    }


def validate_tensor_task_available(
    *,
    arm: AlignedInputArm,
    available_task_sequences: Mapping[str, Sequence[int]],
) -> None:
    """Fail closed when the exact target/sequence tensor is unavailable."""

    arm.validate()
    sequences = tuple(int(value) for value in available_task_sequences.get(arm.task_id, ()))
    if arm.sequence_length not in sequences:
        raise ValueError(
            "stage6_alignment_exact_tensor_unavailable:"
            f"{arm.task_id}:L{arm.sequence_length}"
        )


def build_aligned_task_spec(
    *,
    base_spec: Stage6TaskSpec,
    shared: Stage6SharedTensor,
    arm: AlignedInputArm,
) -> Stage6TaskSpec:
    """Project a verified shared tensor onto one exact structured input arm."""

    arm.validate()
    if base_spec.task_id != arm.task_id:
        raise ValueError("stage6_alignment_base_task_mismatch")
    if arm.sequence_length not in base_spec.sequence_length_candidates:
        raise ValueError("stage6_alignment_sequence_not_in_base_task")
    factor_index = {value: index for index, value in enumerate(shared.factor_ids)}
    descriptor_index = {
        value.removeprefix("descriptor:"): index
        for index, value in enumerate(shared.descriptor_ids)
    }
    channels: list[Stage6TicketChannel] = []
    for identity in arm.identities:
        if identity.factor_id not in factor_index:
            raise ValueError(
                f"stage6_alignment_factor_not_in_tensor:{identity.factor_id}"
            )
        descriptor = identity.descriptor_id.removeprefix("descriptor:")
        descriptor_position = -1
        pathway = "long_term_main_effect"
        scope = "pool"
        bins = (0, 1, 2, 3, 4)
        if identity.input_mode == "spatial":
            pathway = "spatial_specialist"
            descriptor_position = descriptor_index.get(descriptor, -1)
            if descriptor_position < 0:
                raise ValueError(
                    f"stage6_alignment_descriptor_not_in_tensor:{descriptor}"
                )
            bins = identity.quantile_bins
            scope = f"{descriptor}::bins_{'_'.join(map(str, bins))}"
        elif identity.input_mode == "follow":
            raise ValueError("stage6_alignment_follow_requires_h60_tensor_successor")
        channels.append(
            Stage6TicketChannel(
                usage_ticket_id=f"aligned::{arm.arm_id}::{identity.candidate_id}",
                factor_id=identity.factor_id,
                factor_index=factor_index[identity.factor_id],
                pathway_id=pathway,
                descriptor_index=descriptor_position,
                quantile_bins=bins,
                follow_ticket_index=-1,
                mechanism_vote_weight=1.0,
                scope_or_context_id=scope,
            )
        )
    arm_digest = str(arm.as_dict()["canonical_digest"])
    return Stage6TaskSpec(
        task_id=base_spec.task_id,
        cadence_id=base_spec.cadence_id,
        horizon_days=base_spec.horizon_days,
        sequence_length_candidates=(arm.sequence_length,),
        state_duration_candidate_days=base_spec.state_duration_candidate_days,
        channels=tuple(channels),
        tensor_digest=base_spec.tensor_digest,
        tickets_csv_digest=arm_digest,
        freeze_root_digest=base_spec.freeze_root_digest,
    )


def common_support_rows(
    *,
    shared: Stage6SharedTensor,
    rows_by_year: Mapping[int, NDArray[np.int64]],
    factor_ids: Sequence[str],
) -> dict[int, NDArray[np.int64]]:
    """Keep rows with at least one common-root factor observable at decision time."""

    positions = {value: index for index, value in enumerate(shared.factor_ids)}
    try:
        factor_indices = np.asarray(
            [positions[value] for value in factor_ids], dtype=np.int64
        )
    except KeyError as exc:
        raise ValueError(f"stage6_alignment_support_factor_missing:{exc.args[0]}") from exc
    result: dict[int, NDArray[np.int64]] = {}
    for year, raw in rows_by_year.items():
        rows = np.asarray(raw, dtype=np.int64)
        if rows.ndim != 2 or rows.shape[1] != ROW_WIDTH:
            raise ValueError("stage6_alignment_rows_shape_invalid")
        observed = shared.base_available[
            rows[:, 0, None], rows[:, 1, None], factor_indices[None, :]
        ].any(axis=1)
        kept = rows[observed]
        if kept.size:
            result[int(year)] = kept
    if not result:
        raise ValueError("stage6_alignment_common_support_has_no_rows")
    return result


def load_supplemented_shared_tensor(
    *,
    base: Stage6SharedTensor,
    supplement_root: Path,
) -> Stage6SharedTensor:
    """Verify and append a factor-only immutable supplement to shared tensors."""

    manifest_path = supplement_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observed = str(manifest.pop("canonical_digest", ""))
    if canonical_digest(manifest) != observed:
        raise RuntimeError("stage6_alignment_supplement_manifest_digest_mismatch")
    manifest["canonical_digest"] = observed
    if manifest.get("schema_id") != "factorlab.reaka_stage6_factor_supplement@1.0":
        raise RuntimeError("stage6_alignment_supplement_schema_mismatch")
    if manifest.get("base_tensor_manifest_digest") != base.manifest_digest:
        raise RuntimeError("stage6_alignment_supplement_base_digest_mismatch")
    artifacts = dict(manifest["artifact_digests"])
    for name, expected in artifacts.items():
        if sha256_file(supplement_root / name) != expected:
            raise RuntimeError(
                f"stage6_alignment_supplement_artifact_digest_mismatch:{name}"
            )
    factor_ids = tuple(str(value) for value in manifest["factor_ids"])
    if set(factor_ids) & set(base.factor_ids):
        raise RuntimeError("stage6_alignment_supplement_factor_overlap")
    values = np.load(
        supplement_root / "base_rank_centered.npz", allow_pickle=False
    )["arr"]
    availability = np.load(
        supplement_root / "base_available.npz", allow_pickle=False
    )["arr"]
    expected_shape = (base.day_count, base.symbol_count, len(factor_ids))
    if values.shape != expected_shape or availability.shape != expected_shape:
        raise RuntimeError("stage6_alignment_supplement_shape_mismatch")
    combined_values = np.concatenate(
        (base.base_rank_centered, values.astype(np.float32, copy=False)), axis=2
    )
    combined_availability = np.concatenate(
        (base.base_available, availability.astype(np.uint8, copy=False)), axis=2
    )
    identity = {
        "base_tensor_manifest_digest": base.manifest_digest,
        "supplement_manifest_digest": observed,
        "factor_ids": [*base.factor_ids, *factor_ids],
    }
    return replace(
        base,
        base_rank_centered=combined_values,
        base_available=combined_availability,
        factor_ids=(*base.factor_ids, *factor_ids),
        manifest_digest=canonical_digest(identity),
    )


__all__ = [
    "AlignedInputArm",
    "FactorEvidenceIdentity",
    "HORIZON_TASK_PARAMETERS",
    "build_aligned_task_spec",
    "common_support_rows",
    "load_supplemented_shared_tensor",
    "split_horizon_pure",
    "task_parameters_for_horizon",
    "validate_tensor_task_available",
]
