"""Stage 0-6 governance for state learnability and expert fusion."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

from factor_lab.governance.canonicalization import canonical_digest


class StateScope(StrEnum):
    GLOBAL = "global_market"
    SECTOR = "sector"
    ASSET = "asset_specific"


class StateFrequencyClass(StrEnum):
    RARE = "rare_less_than_one_independent_episode_per_year"
    LOW = "low_one_to_four_independent_episodes_per_year"
    MEDIUM = "medium_four_to_twelve_independent_episodes_per_year"
    HIGH = "high_at_least_twelve_independent_episodes_per_year"


class LearnabilityRoute(StrEnum):
    DATA_BLOCKED = "data_blocked"
    FINANCIAL_REVIEW_PENDING = "financial_review_pending"
    DIAGNOSTIC_ONLY = "diagnostic_only"
    SLOW_CONTEXT_MODULATOR = "slow_context_low_rank_modulator"
    CONTINUOUS_CONTEXT = "continuous_context_shared_dynamics"
    HIGH_FREQUENCY_EXPERT = "high_frequency_independent_expert"
    DISCRETE_OPERATOR_EXPERT = "identified_discrete_operator_expert"


class ResearchStage(StrEnum):
    STAGE0_COORDINATE_FREEZE = "stage0_coordinate_and_authority_freeze"
    STAGE1_FACTOR_PROFILE = "stage1_factor_effectiveness_profile"
    STAGE2_THREE_PATHWAY = "stage2_three_pathway_factor_routing"
    STAGE3_STATE_EPISODE_ATLAS = "stage3_state_episode_atlas"
    STAGE4_PAIRING = "stage4_state_factor_pairing_and_coverage"
    STAGE5_EXPERT_FREEZE = "stage5_learnability_and_expert_freeze"
    STAGE6_MODEL_CHALLENGE = "stage6_model_training_and_challenge"


STAGE_ORDER: Final = tuple(ResearchStage)


@dataclass(frozen=True, slots=True)
class LearnabilityPolicy:
    """Versioned research policy, not a universal statistical theorem."""

    rare_episode_rate_per_year: float = 1.0
    medium_episode_rate_per_year: float = 4.0
    high_episode_rate_per_year: float = 12.0
    minimum_independent_episodes_for_discrete_state: int = 8
    minimum_factor_active_episodes: int = 4
    comfortable_effective_transitions_per_degree: float = 5.0
    maximum_slow_context_rank: int = 2

    def validate(self) -> None:
        if not (
            0
            < self.rare_episode_rate_per_year
            < self.medium_episode_rate_per_year
            < self.high_episode_rate_per_year
        ):
            raise ValueError("state_learnability_frequency_policy_invalid")
        if (
            self.minimum_independent_episodes_for_discrete_state < 2
            or self.minimum_factor_active_episodes < 2
            or self.comfortable_effective_transitions_per_degree <= 0
            or self.maximum_slow_context_rank < 1
        ):
            raise ValueError("state_learnability_capacity_policy_invalid")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            **asdict(self),
            "authority": "versioned_research_routing_policy_not_universal_law",
        }


OperatorParameterization = Literal["full", "diagonal", "low_rank"]


@dataclass(frozen=True, slots=True)
class StateEpisodeProfile:
    state_id: str
    scope: StateScope
    history_years: float
    prevalence: float
    independent_episode_count: int
    effective_transition_count: float
    observed_transition_count: int
    state_switch_count: int
    factor_active_episode_count: int
    median_duration_steps: float
    cross_sectional_row_count: int
    latent_dim: int
    proposed_operator_count: int
    operator_parameterization: OperatorParameterization
    low_rank_rank: int = 1
    financial_mechanism_approved: bool = False
    data_ready: bool = True

    def validate(self) -> None:
        if not self.state_id:
            raise ValueError("state_learnability_state_id_empty")
        if self.history_years <= 0 or not 0 <= self.prevalence <= 1:
            raise ValueError("state_learnability_history_or_prevalence_invalid")
        counts = (
            self.independent_episode_count,
            self.observed_transition_count,
            self.state_switch_count,
            self.factor_active_episode_count,
            self.cross_sectional_row_count,
            self.latent_dim,
            self.proposed_operator_count,
            self.low_rank_rank,
        )
        if any(value < 0 for value in counts[:5]) or any(
            value <= 0 for value in counts[5:]
        ):
            raise ValueError("state_learnability_count_or_capacity_invalid")
        if self.effective_transition_count < 0 or self.median_duration_steps < 0:
            raise ValueError("state_learnability_transition_or_duration_invalid")
        if self.operator_parameterization == "low_rank" and (
            self.low_rank_rank > self.latent_dim
        ):
            raise ValueError("state_learnability_low_rank_exceeds_latent")

    @property
    def episodes_per_year(self) -> float:
        return self.independent_episode_count / self.history_years

    @property
    def frequency_class(self) -> StateFrequencyClass:
        rate = self.episodes_per_year
        if rate < 1.0:
            return StateFrequencyClass.RARE
        if rate < 4.0:
            return StateFrequencyClass.LOW
        if rate < 12.0:
            return StateFrequencyClass.MEDIUM
        return StateFrequencyClass.HIGH

    @property
    def parameter_degrees_per_operator(self) -> int:
        d = self.latent_dim
        if self.operator_parameterization == "full":
            return d * d
        if self.operator_parameterization == "diagonal":
            return d
        return d + 2 * d * self.low_rank_rank

    @property
    def incremental_operator_degrees(self) -> int:
        return max(self.proposed_operator_count - 1, 1) * (
            self.parameter_degrees_per_operator
        )

    @property
    def effective_transitions_per_degree(self) -> float:
        return self.effective_transition_count / max(
            self.incremental_operator_degrees, 1
        )


@dataclass(frozen=True, slots=True)
class StateLearnabilityCertificate:
    profile: StateEpisodeProfile
    route: LearnabilityRoute
    frequency_class: StateFrequencyClass
    discrete_operator_expert_allowed: bool
    unshrunk_full_matrix_allowed: bool
    standalone_rank_expert_allowed: bool
    allowed_parameterizations: tuple[str, ...]
    fusion_role: str
    blockers: tuple[str, ...]
    diagnostics: dict[str, float | int | str]

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_id": "factorlab.state_learnability_certificate@1.0",
            "profile": {
                **asdict(self.profile),
                "scope": self.profile.scope.value,
            },
            "route": self.route.value,
            "frequency_class": self.frequency_class.value,
            "discrete_operator_expert_allowed": self.discrete_operator_expert_allowed,
            "unshrunk_full_matrix_allowed": self.unshrunk_full_matrix_allowed,
            "standalone_rank_expert_allowed": self.standalone_rank_expert_allowed,
            "allowed_parameterizations": list(self.allowed_parameterizations),
            "fusion_role": self.fusion_role,
            "blockers": list(self.blockers),
            "diagnostics": dict(self.diagnostics),
            "cross_sectional_rows_do_not_multiply_global_episode_count": True,
            "oversampling_does_not_increase_event_information": True,
            "fresh_oos": False,
            "production_authority": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


def classify_state_learnability(
    profile: StateEpisodeProfile,
    *,
    policy: LearnabilityPolicy | None = None,
) -> StateLearnabilityCertificate:
    profile.validate()
    rules = policy or LearnabilityPolicy()
    rules.validate()
    rate = profile.episodes_per_year
    if rate < rules.rare_episode_rate_per_year:
        frequency = StateFrequencyClass.RARE
    elif rate < rules.medium_episode_rate_per_year:
        frequency = StateFrequencyClass.LOW
    elif rate < rules.high_episode_rate_per_year:
        frequency = StateFrequencyClass.MEDIUM
    else:
        frequency = StateFrequencyClass.HIGH
    blockers: list[str] = []
    diagnostics: dict[str, float | int | str] = {
        "episodes_per_year": profile.episodes_per_year,
        "independent_episode_count": profile.independent_episode_count,
        "factor_active_episode_count": profile.factor_active_episode_count,
        "effective_transition_count": profile.effective_transition_count,
        "state_switch_count": profile.state_switch_count,
        "parameter_degrees_per_operator": profile.parameter_degrees_per_operator,
        "incremental_operator_degrees": profile.incremental_operator_degrees,
        "effective_transitions_per_degree": (
            profile.effective_transitions_per_degree
        ),
        "cross_sectional_row_count": profile.cross_sectional_row_count,
    }
    if not profile.data_ready:
        route = LearnabilityRoute.DATA_BLOCKED
        blockers.append("state_data_not_ready")
    elif not profile.financial_mechanism_approved:
        route = LearnabilityRoute.FINANCIAL_REVIEW_PENDING
        blockers.append("financial_mechanism_review_missing")
    elif (
        profile.independent_episode_count < 2
        or profile.observed_transition_count < 2
        or profile.factor_active_episode_count < 2
    ):
        route = LearnabilityRoute.DIAGNOSTIC_ONLY
        blockers.append("independent_episode_or_transition_support_absent")
    else:
        comfortable = (
            profile.effective_transitions_per_degree
            >= rules.comfortable_effective_transitions_per_degree
        )
        enough_episodes = (
            profile.independent_episode_count
            >= rules.minimum_independent_episodes_for_discrete_state
            and profile.factor_active_episode_count
            >= rules.minimum_factor_active_episodes
        )
        if frequency == StateFrequencyClass.RARE:
            route = LearnabilityRoute.SLOW_CONTEXT_MODULATOR
            blockers.append("rare_state_cannot_own_standalone_full_operator")
        elif comfortable and enough_episodes:
            route = LearnabilityRoute.DISCRETE_OPERATOR_EXPERT
        elif frequency == StateFrequencyClass.HIGH:
            route = LearnabilityRoute.HIGH_FREQUENCY_EXPERT
            blockers.append("full_operator_underidentified_use_shrunk_expert")
        else:
            route = LearnabilityRoute.CONTINUOUS_CONTEXT
            blockers.append("discrete_state_underidentified_use_continuous_context")
    discrete_allowed = route == LearnabilityRoute.DISCRETE_OPERATOR_EXPERT
    unshrunk_full_allowed = (
        discrete_allowed and profile.operator_parameterization == "full"
    )
    standalone = route in {
        LearnabilityRoute.DISCRETE_OPERATOR_EXPERT,
        LearnabilityRoute.HIGH_FREQUENCY_EXPERT,
    }
    if route == LearnabilityRoute.SLOW_CONTEXT_MODULATOR:
        parameterizations = (
            "shared_base_operator",
            f"low_rank_deviation_rank_at_most_{rules.maximum_slow_context_rank}",
            "bounded_continuous_weight_modulation",
        )
        fusion_role = "slow_context_modulates_expert_weights_or_risk_only"
    elif route == LearnabilityRoute.CONTINUOUS_CONTEXT:
        parameterizations = (
            "shared_base_operator",
            "continuous_context_conditioning",
            "diagonal_or_low_rank_deviation",
        )
        fusion_role = "continuous_context_modulates_fast_expert"
    elif route == LearnabilityRoute.HIGH_FREQUENCY_EXPERT:
        parameterizations = (
            "diagonal_operator",
            "low_rank_operator",
            "regularized_rank_expert",
        )
        fusion_role = "standalone_fast_rank_expert_after_cross_fit"
    elif route == LearnabilityRoute.DISCRETE_OPERATOR_EXPERT:
        parameterizations = (
            profile.operator_parameterization,
            "same_support_k1_comparator_required",
        )
        fusion_role = "standalone_rank_expert_after_cross_fit"
    else:
        parameterizations = ()
        fusion_role = "no_strategy_score_authority"
    return StateLearnabilityCertificate(
        profile=profile,
        route=route,
        frequency_class=frequency,
        discrete_operator_expert_allowed=discrete_allowed,
        unshrunk_full_matrix_allowed=unshrunk_full_allowed,
        standalone_rank_expert_allowed=standalone,
        allowed_parameterizations=parameterizations,
        fusion_role=fusion_role,
        blockers=tuple(blockers),
        diagnostics=diagnostics,
    )


def build_state_episode_profile(
    *,
    state_id: str,
    scope: StateScope,
    state_probability: NDArray[np.float64],
    factor_active: NDArray[np.bool_],
    history_years: float,
    cross_sectional_row_count: int,
    latent_dim: int,
    proposed_operator_count: int,
    operator_parameterization: OperatorParameterization,
    activation_threshold: float = 0.5,
    minimum_episode_duration_steps: int = 1,
    low_rank_rank: int = 1,
    financial_mechanism_approved: bool = False,
    data_ready: bool = True,
) -> StateEpisodeProfile:
    """Create an episode atlas from a PIT probability series, not prose."""

    probability = np.asarray(state_probability, dtype=np.float64)
    factor = np.asarray(factor_active, dtype=bool)
    if (
        probability.ndim != 1
        or factor.shape != probability.shape
        or probability.size < 3
        or not np.isfinite(probability).all()
        or bool(((probability < 0) | (probability > 1)).any())
    ):
        raise ValueError("state_episode_probability_or_factor_series_invalid")
    if not 0 < activation_threshold < 1 or minimum_episode_duration_steps < 1:
        raise ValueError("state_episode_activation_policy_invalid")
    active = probability >= activation_threshold
    changes = np.flatnonzero(np.diff(active.astype(np.int8)) != 0) + 1
    bounds = np.concatenate(([0], changes, [active.size]))
    episodes: list[tuple[int, int]] = []
    for start, stop in zip(bounds[:-1], bounds[1:], strict=True):
        if active[start] and stop - start >= minimum_episode_duration_steps:
            episodes.append((int(start), int(stop)))
    retained_active = np.zeros(active.shape, dtype=bool)
    for start, stop in episodes:
        retained_active[start:stop] = True
    # A state-conditioned operator uses every transition whose origin is in
    # the state.  The next point may stay in the state or exit it; excluding
    # exits would incorrectly give a one-step episode zero observations.
    observed_transition_count = 0
    effective = 0.0
    for start, stop in episodes:
        transition_stop = min(stop, active.size - 1)
        transition_weights = probability[start:transition_stop]
        observed_transition_count += int(transition_weights.size)
        if not transition_weights.size:
            continue
        weight_sum = float(transition_weights.sum())
        squared_sum = float(np.square(transition_weights).sum())
        kish = weight_sum * weight_sum / squared_sum if squared_sum > 0 else 0.0
        serial_adjustment = 1.0
        if transition_weights.size >= 3:
            left = transition_weights[:-1]
            right = transition_weights[1:]
            if float(left.std()) > 1e-12 and float(right.std()) > 1e-12:
                rho = float(np.corrcoef(left, right)[0, 1])
                if math.isfinite(rho):
                    serial_adjustment = (
                        1.0
                        if rho <= -1.0 + 1e-12
                        else min(max((1.0 - rho) / (1.0 + rho), 0.0), 1.0)
                    )
        effective += kish * serial_adjustment
    profile = StateEpisodeProfile(
        state_id=state_id,
        scope=scope,
        history_years=history_years,
        prevalence=float(retained_active.mean()),
        independent_episode_count=len(episodes),
        effective_transition_count=effective,
        observed_transition_count=observed_transition_count,
        state_switch_count=int(np.sum(retained_active[1:] != retained_active[:-1])),
        factor_active_episode_count=sum(
            bool(factor[start:stop].any()) for start, stop in episodes
        ),
        median_duration_steps=(
            float(np.median([stop - start for start, stop in episodes]))
            if episodes
            else 0.0
        ),
        cross_sectional_row_count=cross_sectional_row_count,
        latent_dim=latent_dim,
        proposed_operator_count=proposed_operator_count,
        operator_parameterization=operator_parameterization,
        low_rank_rank=low_rank_rank,
        financial_mechanism_approved=financial_mechanism_approved,
        data_ready=data_ready,
    )
    profile.validate()
    return profile


def _day_equal_zscore(
    values: NDArray[np.float64], date_codes: NDArray[np.int64]
) -> NDArray[np.float64]:
    result = np.zeros(values.shape[0], dtype=np.float64)
    for date in np.unique(date_codes):
        mask = date_codes == date
        current = values[mask]
        finite = np.isfinite(current)
        if finite.sum() < 2:
            continue
        mean = float(current[finite].mean())
        scale = float(current[finite].std())
        if scale < 1e-12:
            continue
        normalized = np.zeros(current.shape[0], dtype=np.float64)
        normalized[finite] = (current[finite] - mean) / scale
        result[mask] = normalized
    return result


@dataclass(frozen=True, slots=True)
class ExpertFusionContract:
    expert_ids: tuple[str, ...]
    frozen_weights: tuple[float, ...]
    slow_context_ids: tuple[str, ...] = ()
    context_modulation_targets: tuple[tuple[str, str], ...] = ()
    minimum_context_multiplier: float = 0.5
    maximum_context_multiplier: float = 1.5
    residualize_later_experts: bool = True

    def validate(self) -> None:
        if not self.expert_ids or len(self.expert_ids) != len(self.frozen_weights):
            raise ValueError("state_expert_fusion_identity_or_weight_mismatch")
        if len(set(self.expert_ids)) != len(self.expert_ids):
            raise ValueError("state_expert_fusion_duplicate_expert")
        if any(value < 0 for value in self.frozen_weights) or not math.isclose(
            sum(self.frozen_weights), 1.0, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("state_expert_fusion_weights_invalid")
        if set(self.slow_context_ids) & set(self.expert_ids):
            raise ValueError("state_expert_fusion_context_cannot_be_rank_expert")
        if len(set(self.slow_context_ids)) != len(self.slow_context_ids):
            raise ValueError("state_expert_fusion_duplicate_context")
        for context_id, expert_id in self.context_modulation_targets:
            if context_id not in self.slow_context_ids or expert_id not in self.expert_ids:
                raise ValueError("state_expert_fusion_unknown_context_target")
        if not (
            0
            < self.minimum_context_multiplier
            <= 1
            <= self.maximum_context_multiplier
        ):
            raise ValueError("state_expert_fusion_context_bounds_invalid")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = {
            **asdict(self),
            "weights_frozen_before_evaluation": True,
            "per_date_normalization": "cross_sectional_zscore",
            "later_expert_residualization_fit_on_training_prefix_only": (
                self.residualize_later_experts
            ),
            "slow_context_direct_stock_rank_forbidden": True,
            "production_authority": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


def fuse_expert_scores(
    *,
    expert_scores: Mapping[str, NDArray[np.float64]],
    date_codes: NDArray[np.int64],
    contract: ExpertFusionContract,
    context_multipliers: Mapping[str, NDArray[np.float64]] | None = None,
    training_mask: NDArray[np.bool_] | None = None,
) -> NDArray[np.float64]:
    """Deterministic score-layer fusion; experts never share training labels."""

    contract.validate()
    if set(expert_scores) != set(contract.expert_ids):
        raise ValueError("state_expert_fusion_score_identity_mismatch")
    length = date_codes.shape[0]
    if any(np.asarray(values).shape != (length,) for values in expert_scores.values()):
        raise ValueError("state_expert_fusion_score_shape_mismatch")
    multipliers = context_multipliers or {}
    if set(multipliers) - set(contract.slow_context_ids):
        raise ValueError("state_expert_fusion_context_identity_mismatch")
    if training_mask is None:
        training_mask = np.ones(length, dtype=bool)
    training_mask = np.asarray(training_mask, dtype=bool)
    if training_mask.shape != (length,) or training_mask.sum() < 2:
        raise ValueError("state_expert_fusion_training_mask_invalid")
    fused = np.zeros(length, dtype=np.float64)
    total_weight = np.zeros(length, dtype=np.float64)
    normalized_experts: list[NDArray[np.float64]] = []
    for expert_id, base_weight in zip(
        contract.expert_ids, contract.frozen_weights, strict=True
    ):
        weight = np.full(length, base_weight, dtype=np.float64)
        targeted_contexts = [
            context_id
            for context_id, target_id in contract.context_modulation_targets
            if target_id == expert_id
        ]
        for context_id in targeted_contexts:
            if context_id not in multipliers:
                continue
            modulation = np.clip(
                np.asarray(multipliers[context_id], dtype=np.float64),
                contract.minimum_context_multiplier,
                contract.maximum_context_multiplier,
            )
            weight *= modulation
        score = _day_equal_zscore(
            np.asarray(expert_scores[expert_id], dtype=np.float64), date_codes
        )
        if contract.residualize_later_experts and normalized_experts:
            design = np.column_stack(normalized_experts)
            coefficients = np.linalg.lstsq(
                design[training_mask],
                score[training_mask],
                rcond=None,
            )[0]
            score = _day_equal_zscore(
                score - design @ coefficients,
                date_codes,
            )
        normalized_experts.append(score)
        fused += weight * score
        total_weight += weight
    positive = total_weight > 0
    fused[positive] /= total_weight[positive]
    return _day_equal_zscore(fused, date_codes)


@dataclass(frozen=True, slots=True)
class StageReceipt:
    stage: ResearchStage
    status: str
    artifact_digest: str
    financial_review_status: str
    mathematical_gate_status: str
    learnability_route: LearnabilityRoute | None = None

    def validate(self) -> None:
        if not self.artifact_digest.startswith("sha256:"):
            raise ValueError("state_machine_stage_digest_invalid")
        if self.financial_review_status not in {
            "not_required",
            "pending",
            "approved",
            "revision_requested",
            "rejected",
        }:
            raise ValueError("state_machine_financial_review_status_invalid")
        if self.mathematical_gate_status not in {
            "passed",
            "blocked",
            "diagnostic_only",
        }:
            raise ValueError("state_machine_mathematical_gate_status_invalid")


def validate_stage0_to6_receipts(
    receipts: Sequence[StageReceipt],
) -> dict[str, object]:
    blockers: list[str] = []
    observed_stages = tuple(receipt.stage for receipt in receipts)
    expected_prefix = STAGE_ORDER[: len(receipts)]
    if observed_stages != expected_prefix:
        blockers.append("stage_order_missing_duplicated_or_skipped")
    for receipt in receipts:
        try:
            receipt.validate()
        except ValueError as exc:
            blockers.append(str(exc))
    by_stage = {receipt.stage: receipt for receipt in receipts}
    stage3 = by_stage.get(ResearchStage.STAGE3_STATE_EPISODE_ATLAS)
    if stage3 is not None and stage3.learnability_route is None:
        blockers.append("stage3_state_learnability_certificate_missing")
    stage5 = by_stage.get(ResearchStage.STAGE5_EXPERT_FREEZE)
    if stage5 is not None and stage5.financial_review_status != "approved":
        blockers.append("stage5_financial_expert_freeze_not_approved")
    stage6 = by_stage.get(ResearchStage.STAGE6_MODEL_CHALLENGE)
    if stage6 is not None:
        if stage5 is None or stage5.mathematical_gate_status != "passed":
            blockers.append("stage6_opened_without_stage5_math_gate")
        if stage5 is not None and stage5.learnability_route in {
            LearnabilityRoute.DIAGNOSTIC_ONLY,
            LearnabilityRoute.SLOW_CONTEXT_MODULATOR,
            LearnabilityRoute.CONTINUOUS_CONTEXT,
        }:
            blockers.append("stage6_standalone_model_forbidden_for_context_route")
    payload: dict[str, object] = {
        "schema_id": "factorlab.state_factor_stage0_6_validation@1.0",
        "status": "passed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "receipt_count": len(receipts),
        "next_stage": (
            STAGE_ORDER[len(receipts)].value
            if len(receipts) < len(STAGE_ORDER) and not blockers
            else None
        ),
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


__all__ = [
    "ExpertFusionContract",
    "LearnabilityPolicy",
    "LearnabilityRoute",
    "ResearchStage",
    "STAGE_ORDER",
    "StageReceipt",
    "StateEpisodeProfile",
    "StateFrequencyClass",
    "StateLearnabilityCertificate",
    "StateScope",
    "classify_state_learnability",
    "build_state_episode_profile",
    "fuse_expert_scores",
    "validate_stage0_to6_receipts",
]
