"""Execution-surface gates for factor middle-platform consumers.

The gate is intentionally small: strategy code supplies evidence refs, and this
module decides whether a factor/mining/model/production entry may proceed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Final, Literal, cast

from factor_lab.core.errors import ValidationError
from factor_lab.governance.evidence_resolver import EvidenceCatalog
from factor_lab.governance.factor_usage_integration import (
    resolve_governance_artifact,
    resolve_strategy_integration_claim,
    validate_authoritative_rich_cutover_execution_context,
)
from factor_lab.governance.strategy_family_registry import (
    GOVERNED_STRATEGY_FAMILIES,
    canonical_strategy_family_id,
)
from factor_lab.governance.temporal_governance_repository import (
    TemporalGovernanceRepository,
)

StrategyFamilyId = Literal[
    "t0",
    "factor_rotation",
    "risk_off",
    "filter_timing",
    "etf_lof_l0",
]
IntendedUse = Literal[
    "factor_candidate",
    "mining_candidate",
    "model_candidate",
    "production_candidate",
]

VALID_STRATEGY_FAMILIES: Final[tuple[str, ...]] = GOVERNED_STRATEGY_FAMILIES

VALID_INTENDED_USES: Final[tuple[str, ...]] = (
    "factor_candidate",
    "mining_candidate",
    "model_candidate",
    "production_candidate",
)

BOOSTED_RANKER_ROUTES: Final[frozenset[str]] = frozenset(
    {"lightgbm_ranker", "xgboost_ranker"}
)


def _empty_metadata() -> Mapping[str, object]:
    return {}


@dataclass(frozen=True, slots=True)
class ExecutionSurfaceEvidence:
    """Evidence refs required before a strategy entry consumes factor infra."""

    strategy_family: str
    intended_use: str
    strategy_id: str | None = None
    feature_readiness: str | None = None
    candidate_review_package_ref: str | None = None
    candidate_asset_ref: str | None = None
    validation_claim_ref: str | None = None
    effective_factor_ref: str | None = None
    admitted_factor_ref: str | None = None
    genetic_mining_status: str | None = None
    technology_selection_status: str | None = None
    model_route: str | None = None
    production_gate_ref: str | None = None
    temporal_integrity_ref: str | None = None
    temporal_integrity_status: str | None = None
    temporal_integrity_stage: str | None = None
    strategy_usage_version: str | None = None
    strategy_integration_receipt_ref: str | None = None
    strategy_usage_execution_receipt_ref: str | None = None
    strategy_usage_cutover_mode: str | None = None
    candidate_fingerprint: str | None = None
    explicit_blocked_reason: str | None = None
    metadata: Mapping[str, object] = field(default_factory=_empty_metadata)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["metadata"] = dict(self.metadata)
        return data


def _present(value: str | None) -> bool:
    return bool(value and value.strip())


def _append_missing(blockers: list[str], condition: bool, blocker: str) -> None:
    if not condition:
        blockers.append(blocker)


def _required_refs_for(intended_use: str) -> list[str]:
    if intended_use == "factor_candidate":
        return ["feature_readiness", "candidate_review_package_ref"]
    if intended_use == "mining_candidate":
        return [
            "genetic_mining_status",
            "candidate_review_package_ref_or_candidate_asset_ref",
        ]
    if intended_use == "model_candidate":
        return [
            "technology_selection_status",
            "model_route",
            "candidate_review_package_ref_or_candidate_asset_ref",
        ]
    if intended_use == "production_candidate":
        return [
            "candidate_asset_ref",
            "validation_claim_ref",
            "effective_factor_ref",
            "admitted_factor_ref",
            "production_gate_ref",
            "temporal_integrity_ref",
            "temporal_integrity_status=eligible",
            "temporal_integrity_stage=lockbox",
        ]
    return []


def evaluate_execution_surface_enforcement(
    evidence: ExecutionSurfaceEvidence | Mapping[str, object],
) -> dict[str, object]:
    """Return a hard-gate report for strategy execution-surface consumers."""

    if not isinstance(evidence, ExecutionSurfaceEvidence):
        evidence = ExecutionSurfaceEvidence(
            strategy_family=str(evidence.get("strategy_family", "")),
            intended_use=str(evidence.get("intended_use", "")),
            strategy_id=_optional_str(evidence.get("strategy_id")),
            feature_readiness=_optional_str(evidence.get("feature_readiness")),
            candidate_review_package_ref=_optional_str(
                evidence.get("candidate_review_package_ref")
            ),
            candidate_asset_ref=_optional_str(evidence.get("candidate_asset_ref")),
            validation_claim_ref=_optional_str(evidence.get("validation_claim_ref")),
            effective_factor_ref=_optional_str(evidence.get("effective_factor_ref")),
            admitted_factor_ref=_optional_str(evidence.get("admitted_factor_ref")),
            genetic_mining_status=_optional_str(evidence.get("genetic_mining_status")),
            technology_selection_status=_optional_str(
                evidence.get("technology_selection_status")
            ),
            model_route=_optional_str(evidence.get("model_route")),
            production_gate_ref=_optional_str(evidence.get("production_gate_ref")),
            temporal_integrity_ref=_optional_str(
                evidence.get("temporal_integrity_ref")
            ),
            temporal_integrity_status=_optional_str(
                evidence.get("temporal_integrity_status")
            ),
            temporal_integrity_stage=_optional_str(
                evidence.get("temporal_integrity_stage")
            ),
            strategy_usage_version=_optional_str(
                evidence.get("strategy_usage_version")
            ),
            strategy_integration_receipt_ref=_optional_str(
                evidence.get("strategy_integration_receipt_ref")
            ),
            strategy_usage_execution_receipt_ref=_optional_str(
                evidence.get("strategy_usage_execution_receipt_ref")
            ),
            strategy_usage_cutover_mode=_optional_str(
                evidence.get("strategy_usage_cutover_mode")
            ),
            candidate_fingerprint=_optional_str(evidence.get("candidate_fingerprint")),
            explicit_blocked_reason=_optional_str(
                evidence.get("explicit_blocked_reason")
            ),
            metadata=_mapping_or_empty(evidence.get("metadata")),
        )

    blockers: list[str] = []
    warnings: list[str] = []

    canonical_family = canonical_strategy_family_id(evidence.strategy_family)

    if canonical_family not in VALID_STRATEGY_FAMILIES:
        blockers.append("unknown_strategy_family")
    if evidence.intended_use not in VALID_INTENDED_USES:
        blockers.append("unknown_intended_use")
    if _present(evidence.explicit_blocked_reason):
        blockers.append("explicit_blocked_reason_supplied")

    if evidence.intended_use == "factor_candidate":
        _append_missing(
            blockers,
            evidence.feature_readiness == "ready_for_candidate_review",
            "feature_library_not_ready_for_candidate_review",
        )
        _append_missing(
            blockers,
            _present(evidence.candidate_review_package_ref),
            "candidate_review_package_ref_required",
        )

    if evidence.intended_use == "mining_candidate":
        _append_missing(
            blockers,
            evidence.genetic_mining_status == "available",
            "genetic_factor_mining_readiness_required",
        )
        _append_missing(
            blockers,
            _present(evidence.candidate_review_package_ref)
            or _present(evidence.candidate_asset_ref),
            "mining_candidate_lineage_ref_required",
        )

    if evidence.intended_use == "model_candidate":
        _append_missing(
            blockers,
            evidence.technology_selection_status == "available",
            "technology_selection_available_report_required",
        )
        _append_missing(
            blockers,
            _present(evidence.model_route),
            "model_route_required",
        )
        _append_missing(
            blockers,
            _present(evidence.candidate_review_package_ref)
            or _present(evidence.candidate_asset_ref),
            "model_candidate_factor_lineage_ref_required",
        )
        if evidence.model_route in BOOSTED_RANKER_ROUTES:
            warnings.append(
                "boosted_ranker_is_research_or_ranking_route_not_unified_ml_family"
            )

    if evidence.intended_use == "production_candidate":
        _append_missing(
            blockers,
            _present(evidence.candidate_asset_ref),
            "candidate_asset_ref_required",
        )
        _append_missing(
            blockers,
            _present(evidence.validation_claim_ref),
            "validation_claim_ref_required",
        )
        _append_missing(
            blockers,
            _present(evidence.effective_factor_ref),
            "effective_factor_ref_required",
        )
        _append_missing(
            blockers,
            _present(evidence.admitted_factor_ref),
            "admitted_factor_ref_required",
        )
        _append_missing(
            blockers,
            _present(evidence.production_gate_ref),
            "production_gate_ref_required",
        )
        _append_missing(
            blockers,
            _present(evidence.temporal_integrity_ref),
            "temporal_integrity_ref_required",
        )
        _append_missing(
            blockers,
            evidence.temporal_integrity_status == "eligible",
            "eligible_temporal_integrity_report_required",
        )
        _append_missing(
            blockers,
            evidence.temporal_integrity_stage == "lockbox",
            "one_shot_lockbox_temporal_stage_required",
        )

    status = "available" if not blockers else "blocked"
    return {
        "report_type": "execution_surface_enforcement_v1",
        "status": status,
        "strategy_family": canonical_family,
        "reported_strategy_family": evidence.strategy_family,
        "intended_use": evidence.intended_use,
        "required_middle_platform_refs": _required_refs_for(evidence.intended_use),
        "blockers": blockers,
        "warnings": warnings,
        "production_authority": False,
        "boosted_ranker_route": evidence.model_route in BOOSTED_RANKER_ROUTES,
        "evidence": evidence.to_dict(),
    }


def evaluate_execution_surface_enforcement_v2(
    evidence: ExecutionSurfaceEvidence | Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None = None,
    admitted_factor_loader: Callable[[str], Mapping[str, object]] | None = None,
    governance_repository: TemporalGovernanceRepository | None = None,
) -> dict[str, object]:
    """Return execution eligibility only; never grant production authority."""

    report = evaluate_execution_surface_enforcement(evidence)
    blockers = list(_string_items(report.get("blockers")))
    evidence_payload = _mapping_or_empty(report.get("evidence"))
    reported_strategy_id = str(evidence_payload.get("strategy_id", "")).strip()
    authoritative_cutover: Mapping[str, object] = {}
    if governance_repository is not None and reported_strategy_id:
        authoritative_cutover = (
            governance_repository.get_strategy_usage_cutover_snapshot(
                reported_strategy_id
            )
        )
    authoritative_v2 = authoritative_cutover.get("mode") == "required" or (
        authoritative_cutover.get("required_history") is True
    )
    usage_v2 = (
        str(evidence_payload.get("strategy_usage_version", "")) == "v2"
        or str(evidence_payload.get("strategy_usage_cutover_mode", "")) == "required"
        or bool(evidence_payload.get("strategy_integration_receipt_ref"))
        or bool(evidence_payload.get("strategy_usage_execution_receipt_ref"))
        or authoritative_v2
    )
    usage_resolution: dict[str, object] = {}
    if usage_v2:
        integration_report = resolve_governance_artifact(
            evidence_payload.get("strategy_integration_receipt_ref"),
            evidence_catalog=evidence_catalog,
            expected_artifact_type="strategy_integration_resolution_receipt",
            expected_candidate_fingerprint=_optional_str(
                evidence_payload.get("candidate_fingerprint")
            ),
        )
        execution_report = resolve_governance_artifact(
            evidence_payload.get("strategy_usage_execution_receipt_ref"),
            evidence_catalog=evidence_catalog,
            expected_artifact_type="strategy_usage_execution_receipt",
            expected_candidate_fingerprint=_optional_str(
                evidence_payload.get("candidate_fingerprint")
            ),
        )
        usage_resolution = {
            "integration": integration_report,
            "execution": execution_report,
        }
        if integration_report.get("status") != "resolved":
            blockers.append("resolver_backed_integration_receipt_required")
        if execution_report.get("status") != "resolved":
            blockers.append("resolver_backed_execution_receipt_required")
        integration_payload = _mapping_or_empty(integration_report.get("payload"))
        execution_payload = _mapping_or_empty(execution_report.get("payload"))
        claim_ref = str(integration_payload.get("claim_ref", "")).strip()
        execution_claim_ref = str(
            execution_payload.get("integration_claim_ref", "")
        ).strip()
        if not claim_ref or execution_claim_ref != claim_ref:
            blockers.append("strategy_usage_receipt_claim_ref_mismatch")
        live_resolution = resolve_strategy_integration_claim(
            claim_ref=claim_ref,
            evidence_catalog=evidence_catalog,
            admitted_factor_loader=admitted_factor_loader,
            governance_repository=governance_repository,
            require_authoritative_claim=True,
        )
        usage_resolution["live_claim_resolution"] = live_resolution
        if live_resolution.get("status") != "resolved":
            blockers.append("live_strategy_integration_claim_not_resolved")
        if live_resolution.get("receipt_digest") != integration_payload.get(
            "receipt_digest"
        ):
            blockers.append("integration_receipt_not_current_resolver_output")
        if governance_repository is None:
            blockers.append("authoritative_cutover_repository_required")
            live_cutover: Mapping[str, object] = {}
            preserved_rollback = False
        else:
            live_cutover = governance_repository.get_strategy_usage_cutover_snapshot(
                str(live_resolution.get("strategy_id", ""))
            )
            if not reported_strategy_id:
                blockers.append("execution_surface_strategy_id_required")
            elif reported_strategy_id != str(live_resolution.get("strategy_id", "")):
                blockers.append("execution_surface_strategy_id_mismatch")
            resolution_reports = _mapping_or_empty(
                live_resolution.get("resolution_reports")
            )
            claim_report = _mapping_or_empty(resolution_reports.get("claim"))
            resolved_claim = _mapping_or_empty(claim_report.get("payload"))
            claim_id = str(resolved_claim.get("claim_id", ""))
            preserved_rollback = (
                live_cutover.get("mode") == "shadow_audit"
                and live_cutover.get("required_history") is True
                and execution_payload.get("preserved_authorized_claim") is True
                and claim_id
                in set(_string_items(live_cutover.get("authorized_claim_ids")))
            )
            if live_cutover.get("mode") != "required" and not preserved_rollback:
                blockers.append("live_cutover_required_for_v2_execution_surface")
            reported_mode = str(evidence_payload.get("strategy_usage_cutover_mode", ""))
            if reported_mode and reported_mode != str(live_cutover.get("mode", "")):
                blockers.append("reported_strategy_usage_cutover_mode_not_live")
            if preserved_rollback:
                blockers.extend(
                    _preserved_rollback_blockers(
                        repository=governance_repository,
                        live_cutover=live_cutover,
                        claim_id=claim_id,
                        claim_ref=claim_ref,
                        binding_ref=str(live_resolution.get("binding_ref", "")),
                        candidate_fingerprint=str(
                            live_resolution.get("candidate_fingerprint", "")
                        ),
                        current_execution_receipt=execution_payload,
                        evidence_catalog=evidence_catalog,
                    )
                )
            blockers.extend(
                _rich_cutover_identity_blockers(
                    live_cutover=live_cutover,
                    live_resolution=live_resolution,
                    strategy_family=str(report.get("strategy_family", "")),
                    preserved_rollback=preserved_rollback,
                    evidence_catalog=evidence_catalog,
                )
            )
            for receipt_field, expected_value in (
                ("cutover_version", live_cutover.get("version")),
                ("cutover_digest", live_cutover.get("rich_cutover_digest")),
                (
                    "cutover_transition_digest",
                    live_cutover.get("latest_transition_digest"),
                ),
            ):
                reported_value = str(execution_payload.get(receipt_field, ""))
                if not expected_value or reported_value != str(expected_value):
                    blockers.append(
                        f"execution_receipt_{receipt_field}_not_authoritative"
                    )
        if integration_payload.get("integration_eligible") is not True:
            blockers.append("resolved_integration_receipt_not_eligible")
        if execution_payload.get("execution_eligible") is not True:
            blockers.append("resolved_execution_receipt_not_eligible")
        if integration_payload.get("production_authority") is not False:
            blockers.append("integration_receipt_must_not_grant_production")
        if execution_payload.get("production_authority") is not False:
            blockers.append("execution_receipt_must_not_grant_production")
        for payload_name, payload in (
            ("integration", integration_payload),
            ("execution", execution_payload),
        ):
            receipt_family = str(payload.get("strategy_family", ""))
            if receipt_family and receipt_family != str(report.get("strategy_family")):
                blockers.append(f"{payload_name}_receipt_strategy_family_mismatch")
        for field in (
            "strategy_family",
            "strategy_id",
            "candidate_fingerprint",
            "admitted_factor_ref",
            "binding_ref",
            "action_id",
            "usage_signature_hash",
        ):
            expected_value = str(live_resolution.get(field, ""))
            if (
                not expected_value
                or str(execution_payload.get(field, "")) != expected_value
            ):
                blockers.append(f"execution_receipt_{field}_mismatch")
        expected_execution_mode = str(live_cutover.get("mode", "required"))
        if str(execution_payload.get("mode", "")) != expected_execution_mode:
            blockers.append("execution_receipt_live_cutover_mode_mismatch")
        if (
            execution_payload.get("preserved_authorized_claim") is True
            and not preserved_rollback
        ):
            blockers.append("execution_receipt_preserved_claim_not_live")
        embedded_resolution = _mapping_or_empty(
            execution_payload.get("integration_resolution")
        )
        if embedded_resolution.get("receipt_digest") != live_resolution.get(
            "receipt_digest"
        ):
            blockers.append("execution_receipt_integration_resolution_mismatch")
        execution_evidence = execution_payload.get("execution_evidence")
        if (
            not isinstance(execution_evidence, Sequence)
            or isinstance(execution_evidence, (str, bytes))
            or not execution_evidence
        ):
            blockers.append("execution_receipt_resolved_evidence_required")
        else:
            for index, entry in enumerate(execution_evidence):
                report_entry = _mapping_or_empty(entry)
                evidence_ref = str(report_entry.get("evidence_ref", "")).strip()
                fresh_report = resolve_governance_artifact(
                    evidence_ref,
                    evidence_catalog=evidence_catalog,
                    expected_artifact_type="strategy_execution_evidence",
                    expected_candidate_fingerprint=_optional_str(
                        evidence_payload.get("candidate_fingerprint")
                    ),
                )
                if fresh_report.get("status") != "resolved":
                    blockers.append(f"execution_evidence_not_resolved:{index}")
                    continue
                fresh_payload = _mapping_or_empty(fresh_report.get("payload"))
                for digest_field in ("recorded_digest", "recomputed_digest"):
                    if str(report_entry.get(digest_field, "")) != str(
                        fresh_report.get(digest_field, "")
                    ):
                        blockers.append(
                            f"execution_evidence_{digest_field}_mismatch:{index}"
                        )
                if fresh_report.get("recorded_digest") != fresh_report.get(
                    "recomputed_digest"
                ):
                    blockers.append(f"execution_evidence_digest_not_canonical:{index}")
                if fresh_payload.get("execution_eligible") is not True:
                    blockers.append(f"execution_evidence_not_eligible:{index}")
                if str(fresh_payload.get("integration_claim_ref", "")) != claim_ref:
                    blockers.append(f"execution_evidence_claim_ref_mismatch:{index}")
                if str(fresh_payload.get("binding_ref", "")) != str(
                    live_resolution.get("binding_ref", "")
                ):
                    blockers.append(f"execution_evidence_binding_ref_mismatch:{index}")
                for field in ("action_id", "usage_signature_hash"):
                    expected_value = str(live_resolution.get(field, ""))
                    if (
                        not expected_value
                        or str(fresh_payload.get(field, "")) != expected_value
                    ):
                        blockers.append(f"execution_evidence_{field}_mismatch:{index}")
        admitted_ref = str(evidence_payload.get("admitted_factor_ref", ""))
        resolved_admitted_ref = str(integration_payload.get("admitted_factor_ref", ""))
        if admitted_ref and resolved_admitted_ref != admitted_ref:
            blockers.append("integration_receipt_admitted_factor_ref_mismatch")
    status = "eligible" if not blockers else "blocked"
    return {
        **report,
        "report_type": "execution_surface_enforcement_v2",
        "status": status,
        "execution_eligible": status == "eligible",
        "production_authority": False,
        "strategy_usage_v2": usage_v2,
        "strategy_usage_resolution": usage_resolution,
        "blockers": sorted(set(blockers)),
    }


def _rich_cutover_identity_blockers(
    *,
    live_cutover: Mapping[str, object],
    live_resolution: Mapping[str, object],
    strategy_family: str,
    preserved_rollback: bool,
    evidence_catalog: EvidenceCatalog | None,
) -> list[str]:
    """Bind execution to the exact resolver-backed cutover artifact in state."""

    blockers = validate_authoritative_rich_cutover_execution_context(
        live_cutover,
        integration_resolution=live_resolution,
        evidence_catalog=evidence_catalog,
    )
    rich_cutover = _mapping_or_empty(live_cutover.get("rich_cutover"))
    if not rich_cutover:
        return blockers
    if str(rich_cutover.get("strategy_family_id", "")) != strategy_family:
        blockers.append("authoritative_rich_cutover_strategy_family_id_mismatch")
    if not preserved_rollback:
        if str(rich_cutover.get("mode", "")) != str(live_cutover.get("mode", "")):
            blockers.append("authoritative_rich_cutover_mode_mismatch")
        if int(str(rich_cutover.get("version", 0))) != int(
            str(live_cutover.get("version", 0))
        ):
            blockers.append("authoritative_rich_cutover_version_mismatch")
    return blockers


def _preserved_rollback_blockers(
    *,
    repository: TemporalGovernanceRepository,
    live_cutover: Mapping[str, object],
    claim_id: str,
    claim_ref: str,
    binding_ref: str,
    candidate_fingerprint: str,
    current_execution_receipt: Mapping[str, object],
    evidence_catalog: EvidenceCatalog | None,
) -> list[str]:
    """Re-resolve the immutable authorization snapshot for a rollback claim."""

    blockers: list[str] = []
    transitions = repository.get_strategy_usage_cutover_transitions(
        str(live_cutover.get("strategy_id", ""))
    )
    latest = transitions[-1] if transitions else {}
    if (
        latest.get("expected_prior_state") != "required"
        or latest.get("next_state") != "shadow_audit"
        or str(latest.get("transition_id", ""))
        != str(live_cutover.get("latest_transition_id", ""))
        or not str(latest.get("rollback_snapshot_ref", ""))
    ):
        blockers.append("authoritative_rollback_transition_required")
    snapshot_ref = str(live_cutover.get("rollback_snapshot_ref", ""))
    snapshot_digest = str(live_cutover.get("rollback_snapshot_digest", ""))
    snapshot_report = resolve_governance_artifact(
        snapshot_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_usage_required_snapshot",
        expected_digest=snapshot_digest or None,
        expected_candidate_fingerprint=candidate_fingerprint or None,
    )
    if snapshot_report.get("status") != "resolved":
        blockers.extend(
            f"preserved_snapshot:{item}"
            for item in _string_items(snapshot_report.get("blockers"))
        )
    snapshot = _mapping_or_empty(snapshot_report.get("payload"))
    if str(snapshot.get("strategy_id", "")) != str(live_cutover.get("strategy_id", "")):
        blockers.append("preserved_snapshot_strategy_id_mismatch")
    if claim_id in set(_string_items(snapshot.get("revoked_claim_ids"))):
        blockers.append("preserved_claim_revoked")
    authorized_entries = [
        _mapping_or_empty(item)
        for item in _object_items(snapshot.get("authorized_claims"))
    ]
    matching = [
        entry
        for entry in authorized_entries
        if str(entry.get("claim_id", "")) == claim_id
    ]
    if len(matching) != 1:
        blockers.append("preserved_claim_authorization_snapshot_entry_required")
        return blockers
    entry = matching[0]
    for identity_field, expected in (
        ("claim_ref", claim_ref),
        ("binding_ref", binding_ref),
        ("candidate_fingerprint", candidate_fingerprint),
    ):
        if str(entry.get(identity_field, "")) != expected:
            blockers.append(f"preserved_snapshot_{identity_field}_mismatch")
    prior_execution_ref = str(entry.get("prior_execution_receipt_ref", ""))
    prior_execution_digest = str(entry.get("prior_execution_receipt_digest", ""))
    if not prior_execution_ref or not prior_execution_digest:
        blockers.append("preserved_prior_execution_receipt_required")
    prior_execution_report = resolve_governance_artifact(
        prior_execution_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_usage_execution_receipt",
        expected_digest=prior_execution_digest or None,
        expected_candidate_fingerprint=candidate_fingerprint or None,
    )
    if prior_execution_report.get("status") != "resolved":
        blockers.extend(
            f"preserved_prior_execution:{item}"
            for item in _string_items(prior_execution_report.get("blockers"))
        )
    prior_execution = _mapping_or_empty(prior_execution_report.get("payload"))
    if (
        prior_execution.get("status") != "eligible"
        or prior_execution.get("execution_eligible") is not True
    ):
        blockers.append("preserved_prior_execution_not_eligible")
    if prior_execution.get("mode") != "required":
        blockers.append("preserved_prior_execution_not_required_mode")
    if prior_execution.get("production_authority") is not False:
        blockers.append("preserved_prior_execution_grants_authority")
    for identity_field, expected in (
        ("strategy_id", str(live_cutover.get("strategy_id", ""))),
        ("integration_claim_ref", claim_ref),
        ("binding_ref", binding_ref),
        ("candidate_fingerprint", candidate_fingerprint),
    ):
        if str(prior_execution.get(identity_field, "")) != expected:
            blockers.append(f"preserved_prior_execution_{identity_field}_mismatch")
    prior_cutover_version = entry.get("prior_required_cutover_version", "")
    prior_transition_digest = str(
        entry.get("prior_required_transition_digest", "")
    )
    prior_rich_digest = str(entry.get("prior_rich_cutover_digest", ""))
    for receipt_field, expected in (
        ("cutover_version", prior_cutover_version),
        ("cutover_digest", prior_rich_digest),
        ("cutover_transition_digest", prior_transition_digest),
    ):
        if not str(expected) or str(prior_execution.get(receipt_field, "")) != str(
            expected
        ):
            blockers.append(
                f"preserved_prior_execution_{receipt_field}_mismatch"
            )
    for snapshot_field, expected in (
        ("required_cutover_version", prior_cutover_version),
        ("required_transition_digest", prior_transition_digest),
        ("rich_cutover_digest", prior_rich_digest),
    ):
        if str(live_cutover.get(snapshot_field, "")) != str(expected):
            blockers.append(f"preserved_snapshot_{snapshot_field}_mismatch")
    if (
        current_execution_receipt.get("prior_execution_receipt_ref")
        != prior_execution_ref
        or current_execution_receipt.get("prior_execution_receipt_digest")
        != prior_execution_digest
    ):
        blockers.append("preserved_current_receipt_prior_execution_mismatch")
    authorization_ref = str(entry.get("production_authorization_ref", ""))
    authorization_digest = str(entry.get("production_authorization_digest", ""))
    if not authorization_ref or not authorization_digest:
        blockers.append("preserved_production_authorization_required")
    authorization_report = resolve_governance_artifact(
        authorization_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="project_production_authorization",
        expected_digest=authorization_digest or None,
        expected_candidate_fingerprint=candidate_fingerprint or None,
    )
    if authorization_report.get("status") != "resolved":
        blockers.extend(
            f"preserved_authorization:{item}"
            for item in _string_items(authorization_report.get("blockers"))
        )
    authorization = _mapping_or_empty(authorization_report.get("payload"))
    if authorization.get("production_authority") is not True:
        blockers.append("preserved_claim_real_authorization_required")
    if authorization.get("revoked") is not False:
        blockers.append("preserved_claim_unrevoked_authorization_required")
    for identity_field, expected in (
        ("strategy_id", str(live_cutover.get("strategy_id", ""))),
        ("claim_ref", claim_ref),
        ("binding_ref", binding_ref),
        ("candidate_fingerprint", candidate_fingerprint),
        ("cutover_version", prior_cutover_version),
        ("cutover_digest", prior_rich_digest),
        ("cutover_transition_digest", prior_transition_digest),
    ):
        if str(authorization.get(identity_field, "")) != str(expected):
            blockers.append(f"preserved_authorization_{identity_field}_mismatch")
    if (
        current_execution_receipt.get("preserved_production_authorization_ref")
        != authorization_ref
        or current_execution_receipt.get(
            "preserved_production_authorization_digest"
        )
        != authorization_digest
    ):
        blockers.append("preserved_current_receipt_authorization_mismatch")
    return blockers


def require_execution_surface_enforcement(
    evidence: ExecutionSurfaceEvidence | Mapping[str, object],
) -> dict[str, object]:
    """Raise ValidationError unless the execution-surface gate is available."""

    report = evaluate_execution_surface_enforcement(evidence)
    if report["status"] != "available":
        blocker_items = _string_items(report.get("blockers"))
        blockers = ", ".join(blocker_items)
        raise ValidationError(
            f"Execution surface gate blocked: {blockers}",
            details={
                "report_type": "execution_surface_enforcement_v1",
                "blockers": list(blocker_items),
            },
        )
    return report


def require_execution_surface_enforcement_v2(
    evidence: ExecutionSurfaceEvidence | Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None = None,
    admitted_factor_loader: Callable[[str], Mapping[str, object]] | None = None,
    governance_repository: TemporalGovernanceRepository | None = None,
) -> dict[str, object]:
    """Raise ValidationError unless execution v2 reports eligible."""

    report = evaluate_execution_surface_enforcement_v2(
        evidence,
        evidence_catalog=evidence_catalog,
        admitted_factor_loader=admitted_factor_loader,
        governance_repository=governance_repository,
    )
    if report["status"] != "eligible":
        blocker_items = _string_items(report.get("blockers"))
        blockers = ", ".join(blocker_items)
        raise ValidationError(
            f"Execution surface v2 gate blocked: {blockers}",
            details={
                "report_type": "execution_surface_enforcement_v2",
                "blockers": list(blocker_items),
            },
        )
    return report


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        raw_mapping = cast(Mapping[object, object], value)
        return {str(key): item for key, item in raw_mapping.items()}
    return dict[str, object]()


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


def _object_items(value: object) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(value)


__all__ = [
    "BOOSTED_RANKER_ROUTES",
    "ExecutionSurfaceEvidence",
    "VALID_INTENDED_USES",
    "VALID_STRATEGY_FAMILIES",
    "evaluate_execution_surface_enforcement",
    "evaluate_execution_surface_enforcement_v2",
    "require_execution_surface_enforcement",
    "require_execution_surface_enforcement_v2",
]
