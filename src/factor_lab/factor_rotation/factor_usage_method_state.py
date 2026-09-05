"""Open three-layer state contract for factor-usage methods.

This module sits above the method router.  A method can be a fixed allocator,
a router, an overlay, or a fallback baseline.  The state machine's job is to
decide whether the method is allowed to be primary, fallback, blocked, or only
kept on watch; it does not force switching when a fixed method is the best
verified choice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, cast

from factor_lab.core.errors import ValidationError
from factor_lab.governance.production_authorization import (
    evaluate_project_production_authorization,
)

FACTOR_USAGE_METHOD_STATE_SCHEMA_VERSION: Final[str] = (
    "factor_usage_method_state@1.0"
)
FACTOR_USAGE_METHOD_PIT_POLICY: Final[str] = (
    "train_only_factor_usage_method_state"
)

MethodFamily = Literal[
    "baseline_fallback",
    "profile_allocator",
    "method_router",
    "overlay",
    "diagnostic",
]
MethodLifecycleStatus = Literal["draft", "active", "deprecated", "blocked"]
LayerAction = Literal[
    "use_as_primary",
    "fallback_to_p3",
    "block",
    "watchlist",
    "diagnostic_only",
]
LayerState = Literal[
    "active_primary",
    "fallback",
    "blocked",
    "watchlist",
    "diagnostic",
]

METHOD_FAMILIES: Final[tuple[str, ...]] = (
    "baseline_fallback",
    "profile_allocator",
    "method_router",
    "overlay",
    "diagnostic",
)
METHOD_LIFECYCLE_STATUSES: Final[tuple[str, ...]] = (
    "draft",
    "active",
    "deprecated",
    "blocked",
)
DEFAULT_MAX_PRIMARY_TOP_K: Final[int] = 40
DEFAULT_MIN_SEGMENT_PASS_RATE: Final[float] = 0.5
DEFAULT_MIN_LOCAL_SURFACE_NOHARM_RATE: Final[float] = 0.5

VALID_CUTOVER_MODES_FOR_METHOD_STATE: Final[frozenset[str]] = frozenset(
    {"legacy_read", "shadow_audit", "required"}
)
PRODUCTION_BLOCKING_CUTOVER_MODES: Final[frozenset[str]] = frozenset(
    {"shadow_audit", "required"}
)


def validate_method_state_cutover_mode(
    *,
    cutover_mode: str,
    authorize_production: bool = False,
) -> list[str]:
    """Return blockers if the cutover mode violates method state contract.

    S3 migration: in ``shadow_audit`` or ``required``, ``authorize_production``
    must not be used to create production authority.
    """

    blockers: list[str] = []
    if cutover_mode not in VALID_CUTOVER_MODES_FOR_METHOD_STATE:
        blockers.append(f"invalid_cutover_mode:{cutover_mode}")
    if (
        authorize_production
        and cutover_mode in PRODUCTION_BLOCKING_CUTOVER_MODES
    ):
        blockers.append(
            f"authorize_production_forbidden_in_method_state:{cutover_mode}"
        )
    return blockers


@dataclass(frozen=True, slots=True)
class FactorUsageMethodSpec:
    """Static declaration for one way of using factors."""

    method_id: str
    method_family: MethodFamily
    description: str
    source_uri: str
    requires_p3_fallback: bool = True
    lookback_days: int | None = None
    top_k: int | None = None
    usage_mode: str | None = None
    status: MethodLifecycleStatus = "active"
    pit_policy: str = FACTOR_USAGE_METHOD_PIT_POLICY
    schema_version: str = FACTOR_USAGE_METHOD_STATE_SCHEMA_VERSION
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.method_id, "method_id")
        _require_known(self.method_family, METHOD_FAMILIES, "method_family")
        _require_text(self.description, "description")
        _require_text(self.source_uri, "source_uri")
        _require_known(self.status, METHOD_LIFECYCLE_STATUSES, "status")
        _validate_pit_policy(self.pit_policy)
        if self.lookback_days is not None and self.lookback_days <= 0:
            raise ValidationError("lookback_days must be positive when provided")
        if self.top_k is not None and self.top_k <= 0:
            raise ValidationError("top_k must be positive when provided")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method_id": self.method_id,
            "method_family": self.method_family,
            "description": self.description,
            "source_uri": self.source_uri,
            "requires_p3_fallback": self.requires_p3_fallback,
            "lookback_days": self.lookback_days,
            "top_k": self.top_k,
            "usage_mode": self.usage_mode,
            "status": self.status,
            "pit_policy": self.pit_policy,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class FactorUsageMethodEvidence:
    """No-harm and robustness evidence for one factor-usage method."""

    annualized_excess_return: float
    p3_annualized_excess_return: float
    excess_sharpe_ratio: float
    p3_excess_sharpe_ratio: float
    max_excess_drawdown: float
    p3_max_excess_drawdown: float
    segment_pass_rate: float
    local_surface_noharm_rate: float
    evidence_uri: str
    segment_count: int | None = None
    segment_pass_count: int | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.evidence_uri, "evidence_uri")
        _require_rate(self.segment_pass_rate, "segment_pass_rate")
        _require_rate(self.local_surface_noharm_rate, "local_surface_noharm_rate")
        if self.segment_count is not None and self.segment_count <= 0:
            raise ValidationError("segment_count must be positive when provided")
        if self.segment_pass_count is not None and self.segment_pass_count < 0:
            raise ValidationError("segment_pass_count must be non-negative")
        if (
            self.segment_count is not None
            and self.segment_pass_count is not None
            and self.segment_pass_count > self.segment_count
        ):
            raise ValidationError("segment_pass_count cannot exceed segment_count")

    def beats_p3_no_harm(self) -> bool:
        return (
            self.annualized_excess_return > self.p3_annualized_excess_return
            and self.excess_sharpe_ratio > self.p3_excess_sharpe_ratio
            and self.max_excess_drawdown >= self.p3_max_excess_drawdown
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "annualized_excess_return": self.annualized_excess_return,
            "p3_annualized_excess_return": self.p3_annualized_excess_return,
            "excess_sharpe_ratio": self.excess_sharpe_ratio,
            "p3_excess_sharpe_ratio": self.p3_excess_sharpe_ratio,
            "max_excess_drawdown": self.max_excess_drawdown,
            "p3_max_excess_drawdown": self.p3_max_excess_drawdown,
            "segment_pass_rate": self.segment_pass_rate,
            "local_surface_noharm_rate": self.local_surface_noharm_rate,
            "evidence_uri": self.evidence_uri,
            "segment_count": self.segment_count,
            "segment_pass_count": self.segment_pass_count,
            "notes": list(self.notes),
            "beats_p3_no_harm": self.beats_p3_no_harm(),
        }


@dataclass(frozen=True, slots=True)
class FactorUsageMethodDecision:
    """L2 state-machine decision for one factor-usage method."""

    method_id: str
    layer_state: LayerState
    layer_action: LayerAction
    reasons: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    schema_version: str = FACTOR_USAGE_METHOD_STATE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method_id": self.method_id,
            "layer_state": self.layer_state,
            "layer_action": self.layer_action,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
        }


def build_p3_fallback_method_spec() -> FactorUsageMethodSpec:
    """Canonical P3 fallback method declaration."""

    return FactorUsageMethodSpec(
        method_id="p3_equal_weight_113",
        method_family="baseline_fallback",
        description="Production-authorized P3 equal-weight 113-factor baseline.",
        source_uri="factor_lab/output/factor-rotation/combined_strategy_20260702_p3",
        requires_p3_fallback=False,
        status="active",
        metadata={
            "role": "production_authorized_baseline",
            "state_machine_layer": "L2_portfolio_action",
        },
    )


def build_v6_narrow_method_spec() -> FactorUsageMethodSpec:
    """Canonical current research champion discovered before production review."""

    return FactorUsageMethodSpec(
        method_id="v6_narrow_profile_allocator_lb60_tk20_usage_none",
        method_family="profile_allocator",
        description=(
            "Fixed V6 profile allocator using 60-day train-only profile, "
            "top-20 factors, and no usage overlay."
        ),
        source_uri=(
            "factor_lab/output/factor-rotation/"
            "v6_narrow_method_state_candidate"
        ),
        lookback_days=60,
        top_k=20,
        usage_mode="none",
        status="active",
        metadata={
            "role": "active_primary_research_candidate",
            "state_machine_layer": "factor_usage_method",
        },
    )


def classify_factor_usage_method(
    spec: FactorUsageMethodSpec,
    *,
    evidence: FactorUsageMethodEvidence | None = None,
    preferred_primary_method_id: str | None = None,
    max_primary_top_k: int = DEFAULT_MAX_PRIMARY_TOP_K,
    min_segment_pass_rate: float = DEFAULT_MIN_SEGMENT_PASS_RATE,
    min_local_surface_noharm_rate: float = DEFAULT_MIN_LOCAL_SURFACE_NOHARM_RATE,
) -> FactorUsageMethodDecision:
    """Classify one method into the open three-layer action contract."""

    if max_primary_top_k <= 0:
        raise ValidationError("max_primary_top_k must be positive")
    _require_rate(min_segment_pass_rate, "min_segment_pass_rate")
    _require_rate(min_local_surface_noharm_rate, "min_local_surface_noharm_rate")

    if spec.method_family == "baseline_fallback":
        return FactorUsageMethodDecision(
            method_id=spec.method_id,
            layer_state="fallback",
            layer_action="fallback_to_p3",
            reasons=("baseline_fallback_is_always_available",),
        )

    if spec.method_family == "diagnostic":
        return FactorUsageMethodDecision(
            method_id=spec.method_id,
            layer_state="diagnostic",
            layer_action="diagnostic_only",
            reasons=("diagnostic_methods_do_not_trade",),
        )

    if spec.status == "blocked":
        return FactorUsageMethodDecision(
            method_id=spec.method_id,
            layer_state="blocked",
            layer_action="block",
            reasons=("method_lifecycle_status_blocked",),
            blockers=("method_status_blocked",),
        )

    width_blockers = _width_blockers(spec, max_primary_top_k)
    if width_blockers:
        return FactorUsageMethodDecision(
            method_id=spec.method_id,
            layer_state="blocked",
            layer_action="block",
            reasons=("method_width_pollution_guard_triggered",),
            blockers=tuple(width_blockers),
        )

    if evidence is None:
        return FactorUsageMethodDecision(
            method_id=spec.method_id,
            layer_state="watchlist",
            layer_action="watchlist",
            reasons=("missing_no_harm_evidence",),
            blockers=("missing_evidence",),
        )

    evidence_blockers = _evidence_blockers(
        evidence,
        min_segment_pass_rate=min_segment_pass_rate,
        min_local_surface_noharm_rate=min_local_surface_noharm_rate,
    )
    if evidence_blockers:
        return FactorUsageMethodDecision(
            method_id=spec.method_id,
            layer_state="watchlist",
            layer_action="watchlist",
            reasons=("evidence_not_strong_enough_for_primary",),
            blockers=tuple(evidence_blockers),
        )

    if spec.method_id == preferred_primary_method_id:
        return FactorUsageMethodDecision(
            method_id=spec.method_id,
            layer_state="active_primary",
            layer_action="use_as_primary",
            reasons=(
                "preferred_primary_passes_p3_no_harm",
                "fixed_method_is_valid_state_machine_action",
            ),
        )

    return FactorUsageMethodDecision(
        method_id=spec.method_id,
        layer_state="watchlist",
        layer_action="watchlist",
        reasons=("method_passes_evidence_but_is_not_preferred_primary",),
    )


def build_factor_usage_method_state_report(
    method_specs: tuple[FactorUsageMethodSpec, ...],
    evidence_by_method_id: dict[str, FactorUsageMethodEvidence],
    *,
    primary_method_id: str,
    fallback_method_id: str,
    max_primary_top_k: int = DEFAULT_MAX_PRIMARY_TOP_K,
) -> dict[str, object]:
    """Build the formal L0/L1/L2 method-state report."""

    specs_by_id = {spec.method_id: spec for spec in method_specs}
    if len(specs_by_id) != len(method_specs):
        raise ValidationError("method_specs contains duplicate method_id values")
    if fallback_method_id not in specs_by_id:
        raise ValidationError("fallback_method_id must exist in method_specs")
    if primary_method_id not in specs_by_id:
        raise ValidationError("primary_method_id must exist in method_specs")
    if specs_by_id[fallback_method_id].method_family != "baseline_fallback":
        raise ValidationError("fallback method must use baseline_fallback family")

    decisions = [
        classify_factor_usage_method(
            spec,
            evidence=evidence_by_method_id.get(spec.method_id),
            preferred_primary_method_id=primary_method_id,
            max_primary_top_k=max_primary_top_k,
        )
        for spec in method_specs
    ]
    decisions_by_id = {decision.method_id: decision for decision in decisions}
    primary_decision = decisions_by_id[primary_method_id]
    fallback_decision = decisions_by_id[fallback_method_id]
    blockers: list[str] = []
    if primary_decision.layer_action != "use_as_primary":
        blockers.append("primary_method_not_authorized")
    if fallback_decision.layer_action != "fallback_to_p3":
        blockers.append("p3_fallback_not_available")

    return {
        "report_type": "factor_usage_method_state_report_v1",
        "schema_version": FACTOR_USAGE_METHOD_STATE_SCHEMA_VERSION,
        "status": "pass" if not blockers else "blocked",
        "production_authorized": False,
        "primary_method_id": primary_method_id,
        "fallback_method_id": fallback_method_id,
        "pit_policy": FACTOR_USAGE_METHOD_PIT_POLICY,
        "layer_contract": {
            "L0": "method_object_presence_and_p3_fallback_availability",
            "L1": "method_no_harm_and_walk_forward_evidence_state",
            "L2": "primary_fallback_watchlist_block_diagnostic_action",
        },
        "method_specs": [spec.to_dict() for spec in method_specs],
        "evidence": {
            method_id: evidence.to_dict()
            for method_id, evidence in sorted(evidence_by_method_id.items())
        },
        "decisions": [decision.to_dict() for decision in decisions],
        "blockers": blockers,
        "notes": [
            "A fixed factor-usage method is a valid state-machine action.",
            (
                "The state machine must not force overlay or switching when "
                "evidence is worse."
            ),
            (
                "P3 remains the fallback until a separate production gate "
                "authorizes replacement."
            ),
        ],
    }


def build_factor_usage_method_production_gate_report(
    method_state_report: dict[str, object],
    *,
    authorize_production: bool = False,
    temporal_evaluation_contract: Mapping[str, object] | None = None,
    execution_surface_evidence: Mapping[str, object] | None = None,
    min_segment_count: int = 5,
    min_segment_pass_count: int = 4,
    min_local_surface_noharm_rate: float = DEFAULT_MIN_LOCAL_SURFACE_NOHARM_RATE,
) -> dict[str, object]:
    """Build a production gate verdict from a method-state report.

    This gate can grant a mechanical pass.  It only grants production
    authorization when the caller explicitly passes authorize_production=True.
    """

    if min_segment_count <= 0:
        raise ValidationError("min_segment_count must be positive")
    if min_segment_pass_count < 0:
        raise ValidationError("min_segment_pass_count must be non-negative")
    if min_segment_pass_count > min_segment_count:
        raise ValidationError("min_segment_pass_count cannot exceed min_segment_count")
    _require_rate(min_local_surface_noharm_rate, "min_local_surface_noharm_rate")

    blockers: list[str] = []
    warnings: list[str] = []
    if method_state_report.get("status") != "pass":
        blockers.append("method_state_report_not_passed")
        blockers.extend(_string_items(method_state_report.get("blockers", [])))

    primary_method_id = str(method_state_report.get("primary_method_id", ""))
    fallback_method_id = str(method_state_report.get("fallback_method_id", ""))
    decisions = {
        str(item.get("method_id", "")): item
        for item in _dict_items(method_state_report.get("decisions", []))
    }
    primary_decision = decisions.get(primary_method_id, {})
    fallback_decision = decisions.get(fallback_method_id, {})
    if primary_decision.get("layer_action") != "use_as_primary":
        blockers.append("primary_method_not_use_as_primary")
    if fallback_decision.get("layer_action") != "fallback_to_p3":
        blockers.append("p3_fallback_not_available")

    evidence_by_id: dict[str, dict[str, object]] = {
        str(method_id): _string_keyed_mapping(cast(object, payload))
        for method_id, payload in _mapping_items(
            method_state_report.get("evidence", {})
        )
        if isinstance(payload, dict)
    }
    primary_evidence = evidence_by_id.get(primary_method_id, {})
    observed_segment_count = _optional_int(primary_evidence.get("segment_count"))
    observed_pass_count = _optional_int(primary_evidence.get("segment_pass_count"))
    observed_surface_rate = _optional_float(
        primary_evidence.get("local_surface_noharm_rate")
    )
    observed_no_harm = bool(primary_evidence.get("beats_p3_no_harm", False))

    if not primary_evidence:
        blockers.append("primary_method_evidence_missing")
    if not observed_no_harm:
        blockers.append("primary_method_does_not_beat_p3_no_harm")
    if observed_segment_count is None:
        blockers.append("walk_forward_segment_count_missing")
    elif observed_segment_count < min_segment_count:
        blockers.append("insufficient_walk_forward_segments")
    if observed_pass_count is None:
        blockers.append("walk_forward_pass_count_missing")
    elif observed_pass_count < min_segment_pass_count:
        blockers.append("walk_forward_pass_count_below_threshold")
    if observed_surface_rate < min_local_surface_noharm_rate:
        blockers.append("local_parameter_surface_not_stable")

    mechanical_pass = not blockers
    authorization_report = evaluate_project_production_authorization(
        strategy_family="factor_rotation",
        manual_authorization_requested=authorize_production,
        temporal_evaluation_contract=temporal_evaluation_contract,
        execution_surface_evidence=execution_surface_evidence,
    )
    production_authorized = bool(
        mechanical_pass and authorization_report["production_authority"]
    )
    if authorize_production and not production_authorized:
        blockers.extend(
            f"project_authorization:{item}"
            for item in _string_items(authorization_report.get("blockers"))
        )
    gate_pass = mechanical_pass and (not authorize_production or production_authorized)
    if production_authorized:
        verdict = "PRODUCTION_AUTHORIZED"
        publication_state = "production_authorized"
    elif mechanical_pass:
        verdict = "PRODUCTION_CANDIDATE_REQUIRES_REVIEW"
        publication_state = "research_preview_not_production"
        warnings.append("mechanical_pass_but_manual_authorization_required")
    else:
        verdict = "NOT_READY_FOR_PRODUCTION"
        publication_state = "research_preview_not_production"

    return {
        "report_type": "factor_usage_method_production_gate_report_v1",
        "schema_version": FACTOR_USAGE_METHOD_STATE_SCHEMA_VERSION,
        "status": "pass" if gate_pass else "blocked",
        "verdict": verdict,
        "publication_state": publication_state,
        "production_authorized": production_authorized,
        "mechanical_pass": bool(mechanical_pass),
        "project_production_authorization": authorization_report,
        "primary_method_id": primary_method_id,
        "fallback_method_id": fallback_method_id,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "requirements": {
            "min_segment_count": int(min_segment_count),
            "min_segment_pass_count": int(min_segment_pass_count),
            "min_local_surface_noharm_rate": float(min_local_surface_noharm_rate),
            "p3_fallback_required": True,
            "manual_authorization_required": True,
        },
        "observed": {
            "segment_count": observed_segment_count,
            "segment_pass_count": observed_pass_count,
            "local_surface_noharm_rate": observed_surface_rate,
            "beats_p3_no_harm": observed_no_harm,
            "primary_action": str(primary_decision.get("layer_action", "")),
            "fallback_action": str(fallback_decision.get("layer_action", "")),
        },
        "pit_policy": "production_gate_consumes_only_prior_method_state_artifacts",
    }


def _evidence_blockers(
    evidence: FactorUsageMethodEvidence,
    *,
    min_segment_pass_rate: float,
    min_local_surface_noharm_rate: float,
) -> list[str]:
    blockers: list[str] = []
    if not evidence.beats_p3_no_harm():
        blockers.append("does_not_beat_p3_no_harm")
    if evidence.segment_pass_rate < min_segment_pass_rate:
        blockers.append("walk_forward_segment_pass_rate_too_low")
    if evidence.local_surface_noharm_rate < min_local_surface_noharm_rate:
        blockers.append("local_parameter_surface_not_stable")
    return blockers


def _dict_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [
        _string_keyed_mapping(cast(object, item))
        for item in cast(list[object], value)
        if isinstance(item, dict)
    ]


def _mapping_items(value: object) -> list[tuple[object, object]]:
    if not isinstance(value, dict):
        return []
    return list(cast(dict[object, object], value).items())


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def _string_keyed_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in cast(dict[object, object], value).items()
    }


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float:
    if value is None:
        return 0.0
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _width_blockers(
    spec: FactorUsageMethodSpec,
    max_primary_top_k: int,
) -> list[str]:
    blockers: list[str] = []
    if spec.top_k is not None and spec.top_k > max_primary_top_k:
        blockers.append("top_k_exceeds_width_pollution_guard")
    if spec.metadata.get("pollution_risk") == "wide_pool_edge_dilution":
        blockers.append("wide_pool_edge_dilution")
    return blockers


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")


def _require_known(value: str, allowed: tuple[str, ...], field_name: str) -> None:
    if value not in allowed:
        raise ValidationError(f"{field_name} must be one of {allowed}")


def _require_rate(value: float, field_name: str) -> None:
    if value < 0.0 or value > 1.0:
        raise ValidationError(f"{field_name} must be in [0, 1]")


def _validate_pit_policy(pit_policy: str) -> None:
    _require_text(pit_policy, "pit_policy")
    if "train_only" not in pit_policy:
        raise ValidationError("pit_policy must declare train_only semantics")
