"""Project-level production authorization composed from temporal and lineage gates."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from factor_lab.core.errors import ValidationError
from factor_lab.governance.evidence_resolver import (
    EvidenceCatalog,
    resolve_evidence_ref,
    validate_manual_authorization_decision,
)
from factor_lab.governance.execution_surface_enforcement import (
    ExecutionSurfaceEvidence,
    evaluate_execution_surface_enforcement,
    evaluate_execution_surface_enforcement_v2,
)
from factor_lab.governance.factor_usage_integration import resolve_governance_artifact
from factor_lab.governance.temporal_governance_repository import (
    TemporalGovernanceRepository,
    canonical_digest,
)
from factor_lab.governance.temporal_integrity import (
    validate_temporal_evaluation_contract,
    validate_temporal_evaluation_contract_v5,
)


def evaluate_project_production_authorization(
    *,
    strategy_family: str,
    manual_authorization_requested: object,
    temporal_evaluation_contract: Mapping[str, object] | None,
    execution_surface_evidence: ExecutionSurfaceEvidence | Mapping[str, object] | None,
) -> dict[str, object]:
    """Return a fail-closed project authorization report."""

    blockers: list[str] = []
    if temporal_evaluation_contract is None:
        temporal_report: dict[str, object] = {}
        blockers.append("temporal_evaluation_contract_required")
    else:
        temporal_report = validate_temporal_evaluation_contract(
            temporal_evaluation_contract
        )
        if not (
            temporal_report.get("status") == "eligible"
            and temporal_report.get("stage") == "lockbox"
            and temporal_report.get("production_claim") == "review_required"
        ):
            blockers.append("eligible_one_shot_lockbox_required")
            blockers.extend(
                f"temporal:{item}"
                for item in _string_items(temporal_report.get("blockers"))
            )

    if execution_surface_evidence is None:
        execution_report: dict[str, object] = {}
        blockers.append("execution_surface_evidence_required")
    else:
        if isinstance(execution_surface_evidence, ExecutionSurfaceEvidence):
            surface_payload = execution_surface_evidence.to_dict()
        else:
            surface_payload = dict(execution_surface_evidence)
        if surface_payload.get("strategy_family") != strategy_family:
            blockers.append("execution_surface_strategy_family_mismatch")
        surface_payload["strategy_family"] = strategy_family
        surface_payload["temporal_integrity_status"] = temporal_report.get(
            "status", "blocked"
        )
        surface_payload["temporal_integrity_stage"] = temporal_report.get(
            "stage", "missing"
        )
        execution_report = evaluate_execution_surface_enforcement(surface_payload)
        if execution_report.get("status") != "available":
            blockers.append("execution_surface_gate_not_available")
            blockers.extend(
                f"execution:{item}"
                for item in _string_items(execution_report.get("blockers"))
            )
        elif execution_report.get("production_authority") is not True:
            blockers.append("execution_surface_production_authority_required")

    if not isinstance(manual_authorization_requested, bool):
        blockers.append("manual_authorization_requested_must_be_boolean")
    elif not manual_authorization_requested:
        blockers.append("manual_authorization_not_requested")
    blockers.append("production_authorization_v1_legacy_cannot_grant_production")
    production_authority = False
    return {
        "report_type": "project_production_authorization_v1",
        "status": "blocked",
        "strategy_family": strategy_family,
        "production_authority": production_authority,
        "manual_authorization_requested": manual_authorization_requested,
        "blockers": sorted(set(blockers)),
        "temporal_integrity": temporal_report,
        "execution_surface": execution_report,
    }


def evaluate_project_production_authorization_v2(
    *,
    strategy_family: str,
    manual_authorization_ref: str | None,
    temporal_evaluation_contract: Mapping[str, object] | None,
    execution_surface_evidence: ExecutionSurfaceEvidence | Mapping[str, object] | None,
    evidence_catalog: EvidenceCatalog | None = None,
    admitted_factor_loader: Callable[[str], Mapping[str, object]] | None = None,
    governance_repository: TemporalGovernanceRepository | None = None,
) -> dict[str, object]:
    """Return v2 production authorization from resolved evidence only."""

    blockers: list[str] = []
    surface_payload: dict[str, object] = {}
    usage_resolution: object = {}
    approval_report = resolve_evidence_ref(
        manual_authorization_ref,
        catalog=evidence_catalog,
        expected_artifact_type="manual_authorization_decision",
    )
    if approval_report.get("status") != "resolved":
        blockers.append("manual_authorization_decision_ref_not_resolved")
        blockers.extend(
            f"approval:{item}"
            for item in _string_items(approval_report.get("blockers"))
        )
    approval_payload = _mapping_or_empty(approval_report.get("payload"))
    blockers.extend(
        f"approval:{item}"
        for item in validate_manual_authorization_decision(approval_payload)
    )
    approved_strategy_id = str(approval_payload.get("strategy_id", "")).strip()
    if not approved_strategy_id:
        blockers.append("manual_authorization_strategy_id_required")
    live_cutover: Mapping[str, object] = {}
    authoritative_v2 = False
    if governance_repository is None:
        blockers.append("authoritative_cutover_repository_required")
    elif approved_strategy_id:
        live_cutover = governance_repository.get_strategy_usage_cutover_snapshot(
            approved_strategy_id
        )
        live_mode = str(live_cutover.get("mode", ""))
        authoritative_v2 = live_mode == "required" or (
            live_cutover.get("required_history") is True
        )
        if live_mode == "legacy_read":
            blockers.append("legacy_read_new_production_authorization_forbidden")
        elif live_mode != "required":
            # A rollback preserves only the already-frozen authorization in
            # its snapshot.  The new-authorization entry point must not mint a
            # replacement while the strategy is back in shadow audit.
            blockers.append("non_required_new_production_authorization_forbidden")
    if temporal_evaluation_contract is None:
        temporal_report: dict[str, object] = {}
        blockers.append("temporal_evaluation_contract_required")
    else:
        temporal_report = validate_temporal_evaluation_contract_v5(
            temporal_evaluation_contract,
            evidence_catalog=evidence_catalog,
        )
        if not (
            temporal_report.get("status") == "eligible"
            and temporal_report.get("stage") == "lockbox"
            and temporal_report.get("production_claim") == "review_required"
        ):
            blockers.append("eligible_at5_one_shot_lockbox_required")
            blockers.extend(
                f"temporal:{item}"
                for item in _string_items(temporal_report.get("blockers"))
            )

    if execution_surface_evidence is None:
        execution_report: dict[str, object] = {}
        blockers.append("execution_surface_evidence_required")
    else:
        if isinstance(execution_surface_evidence, ExecutionSurfaceEvidence):
            surface_payload = execution_surface_evidence.to_dict()
        else:
            surface_payload = dict(execution_surface_evidence)
        if surface_payload.get("strategy_family") != strategy_family:
            blockers.append("execution_surface_strategy_family_mismatch")
        surface_payload["strategy_family"] = strategy_family
        reported_strategy_id = str(surface_payload.get("strategy_id", "")).strip()
        if reported_strategy_id and reported_strategy_id != approved_strategy_id:
            blockers.append("execution_surface_strategy_id_mismatch")
        surface_payload["strategy_id"] = approved_strategy_id
        reported_cutover_mode = str(
            surface_payload.get("strategy_usage_cutover_mode", "")
        ).strip()
        if authoritative_v2:
            if reported_cutover_mode and reported_cutover_mode != str(
                live_cutover.get("mode", "")
            ):
                blockers.append("execution_surface_cutover_mode_not_authoritative")
            if surface_payload.get("strategy_usage_version") not in {None, "", "v2"}:
                blockers.append("execution_surface_strategy_usage_version_not_v2")
            surface_payload["strategy_usage_version"] = "v2"
            surface_payload["strategy_usage_cutover_mode"] = live_cutover.get(
                "mode", ""
            )
        surface_payload["temporal_integrity_status"] = temporal_report.get(
            "status", "blocked"
        )
        surface_payload["temporal_integrity_stage"] = temporal_report.get(
            "stage", "missing"
        )
        execution_report = evaluate_execution_surface_enforcement_v2(
            surface_payload,
            evidence_catalog=evidence_catalog,
            admitted_factor_loader=admitted_factor_loader,
            governance_repository=governance_repository,
        )
        if execution_report.get("execution_eligible") is not True:
            blockers.append("execution_surface_v2_not_eligible")
            blockers.extend(
                f"execution:{item}"
                for item in _string_items(execution_report.get("blockers"))
            )
        if execution_report.get("production_authority") is True:
            blockers.append("execution_surface_v2_must_not_grant_production")
        if authoritative_v2 or (
            surface_payload.get("strategy_usage_cutover_mode") == "required"
            or surface_payload.get("strategy_usage_version") == "v2"
        ):
            usage_resolution = execution_report.get("strategy_usage_resolution")
            if not isinstance(usage_resolution, Mapping) or not usage_resolution:
                blockers.append("resolver_backed_strategy_usage_receipts_required")
            else:
                typed_resolution = cast(Mapping[str, object], usage_resolution)
                integration_receipt = typed_resolution.get("integration")
                execution_receipt = typed_resolution.get("execution")
                if not (
                    isinstance(integration_receipt, Mapping)
                    and cast(Mapping[str, object], integration_receipt).get("status")
                    == "resolved"
                    and isinstance(execution_receipt, Mapping)
                    and cast(Mapping[str, object], execution_receipt).get("status")
                    == "resolved"
                ):
                    blockers.append("resolver_backed_strategy_usage_receipts_required")
                else:
                    for prefix, artifact_type, receipt_report, surface_ref_field in (
                        (
                            "integration",
                            "strategy_integration_resolution_receipt",
                            cast(Mapping[str, object], integration_receipt),
                            "strategy_integration_receipt_ref",
                        ),
                        (
                            "execution",
                            "strategy_usage_execution_receipt",
                            cast(Mapping[str, object], execution_receipt),
                            "strategy_usage_execution_receipt_ref",
                        ),
                    ):
                        live_ref = str(
                            surface_payload.get(surface_ref_field, "")
                        ).strip()
                        live_digest = str(
                            receipt_report.get("recorded_digest", "")
                        ).strip()
                        if (
                            not live_ref
                            or str(
                                approval_payload.get(f"{prefix}_receipt_ref", "")
                            )
                            != live_ref
                        ):
                            blockers.append(
                                f"manual_authorization_{prefix}_receipt_ref_mismatch"
                            )
                        if (
                            not live_digest
                            or str(
                                approval_payload.get(f"{prefix}_receipt_digest", "")
                            )
                            != live_digest
                        ):
                            blockers.append(
                                f"manual_authorization_{prefix}_receipt_digest_mismatch"
                            )
                        approved_digest = str(
                            approval_payload.get(f"{prefix}_receipt_digest", "")
                        ).strip()
                        fresh_receipt = resolve_governance_artifact(
                            live_ref,
                            evidence_catalog=evidence_catalog,
                            expected_artifact_type=artifact_type,
                            expected_digest=approved_digest or None,
                            expected_candidate_fingerprint=str(
                                surface_payload.get("candidate_fingerprint", "")
                            )
                            or None,
                        )
                        if fresh_receipt.get("status") != "resolved":
                            blockers.append(
                                f"manual_authorization_{prefix}_receipt_not_resolved"
                            )
                            blockers.extend(
                                f"{prefix}_receipt:{item}"
                                for item in _string_items(
                                    fresh_receipt.get("blockers")
                                )
                            )
                        if str(fresh_receipt.get("recorded_digest", "")) != (
                            live_digest
                        ):
                            blockers.append(
                                f"manual_authorization_{prefix}_receipt_replaced"
                            )

    temporal_fingerprint = str(
        (temporal_evaluation_contract or {}).get("candidate_fingerprint", "")
    )
    surface_fingerprint = str(surface_payload.get("candidate_fingerprint", ""))
    if not temporal_fingerprint or temporal_fingerprint != surface_fingerprint:
        blockers.append("temporal_execution_candidate_fingerprint_mismatch")
    for field, expected in (
        ("strategy_family", strategy_family),
        ("strategy_id", approved_strategy_id),
        ("candidate_fingerprint", surface_fingerprint),
    ):
        if not expected or str(approval_payload.get(field, "")) != expected:
            blockers.append(f"manual_authorization_{field}_mismatch")
    usage_resolution = execution_report.get("strategy_usage_resolution")
    if isinstance(usage_resolution, Mapping) and usage_resolution:
        typed_usage_resolution = _string_mapping(
            cast(Mapping[object, object], usage_resolution)
        )
        live_resolution = typed_usage_resolution.get("live_claim_resolution")
        if isinstance(live_resolution, Mapping):
            typed_live_resolution = _string_mapping(
                cast(Mapping[object, object], live_resolution)
            )
            for field in ("strategy_id", "claim_ref", "binding_ref"):
                expected = str(typed_live_resolution.get(field, ""))
                if not expected or str(approval_payload.get(field, "")) != expected:
                    blockers.append(f"manual_authorization_{field}_mismatch")

    cutover_version = int(str(live_cutover.get("version", 0))) if live_cutover else 0
    cutover_digest = str(live_cutover.get("latest_transition_digest", ""))
    rich_cutover_digest = str(live_cutover.get("rich_cutover_digest", ""))
    if authoritative_v2:
        if not cutover_digest:
            blockers.append("authoritative_strategy_usage_cutover_digest_required")
        if str(approval_payload.get("cutover_version", "")) != str(cutover_version):
            blockers.append("manual_authorization_cutover_version_mismatch")
        if not rich_cutover_digest or str(
            approval_payload.get("cutover_digest", "")
        ) != rich_cutover_digest:
            blockers.append("manual_authorization_cutover_digest_mismatch")
        if str(approval_payload.get("cutover_transition_digest", "")) != (
            cutover_digest
        ):
            blockers.append("manual_authorization_cutover_transition_digest_mismatch")

    production_authority = not blockers
    resolved_identity: Mapping[str, object] = {}
    if isinstance(usage_resolution, Mapping):
        candidate_resolution = _string_mapping(
            cast(Mapping[object, object], usage_resolution)
        ).get("live_claim_resolution")
        if isinstance(candidate_resolution, Mapping):
            resolved_identity = _string_mapping(
                cast(Mapping[object, object], candidate_resolution)
            )
    report: dict[str, object] = {
        "artifact_type": "project_production_authorization",
        "report_type": "project_production_authorization_v2",
        "status": "available" if production_authority else "blocked",
        "strategy_family": strategy_family,
        "production_authority": production_authority,
        "manual_authorization_ref": manual_authorization_ref,
        "blockers": sorted(set(blockers)),
        "temporal_integrity": temporal_report,
        "execution_surface": execution_report,
        "manual_authorization": approval_report,
        "candidate_fingerprint": (
            surface_payload.get("candidate_fingerprint", "")
            if execution_surface_evidence is not None
            else ""
        ),
        "strategy_id": resolved_identity.get("strategy_id", ""),
        "claim_ref": resolved_identity.get("claim_ref", ""),
        "binding_ref": resolved_identity.get("binding_ref", ""),
        "strategy_usage_cutover_version": cutover_version,
        "strategy_usage_cutover_digest": cutover_digest,
        "strategy_usage_rich_cutover_digest": rich_cutover_digest,
        "cutover_version": cutover_version,
        "cutover_digest": rich_cutover_digest,
        "cutover_transition_digest": cutover_digest,
        "revoked": False,
    }
    report["checksum"] = canonical_digest(report)
    return report


def require_project_production_authorization(
    *,
    strategy_family: str,
    temporal_evaluation_contract: Mapping[str, object],
    execution_surface_evidence: ExecutionSurfaceEvidence | Mapping[str, object],
) -> dict[str, object]:
    """Raise unless all project-level production evidence is available."""

    report = evaluate_project_production_authorization(
        strategy_family=strategy_family,
        manual_authorization_requested=True,
        temporal_evaluation_contract=temporal_evaluation_contract,
        execution_surface_evidence=execution_surface_evidence,
    )
    if report["status"] != "available":
        raise ValidationError(
            "Project production authorization blocked: "
            + ", ".join(_string_items(report.get("blockers")))
        )
    return report


def require_project_production_authorization_v2(
    *,
    strategy_family: str,
    manual_authorization_ref: str,
    temporal_evaluation_contract: Mapping[str, object],
    execution_surface_evidence: ExecutionSurfaceEvidence | Mapping[str, object],
    evidence_catalog: EvidenceCatalog | None = None,
    admitted_factor_loader: Callable[[str], Mapping[str, object]] | None = None,
    governance_repository: TemporalGovernanceRepository | None = None,
) -> dict[str, object]:
    """Raise unless v2 project-level authorization is available."""

    report = evaluate_project_production_authorization_v2(
        strategy_family=strategy_family,
        manual_authorization_ref=manual_authorization_ref,
        temporal_evaluation_contract=temporal_evaluation_contract,
        execution_surface_evidence=execution_surface_evidence,
        evidence_catalog=evidence_catalog,
        admitted_factor_loader=admitted_factor_loader,
        governance_repository=governance_repository,
    )
    if report["status"] != "available":
        raise ValidationError(
            "Project production authorization v2 blocked: "
            + ", ".join(_string_items(report.get("blockers")))
        )
    return report


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


def _string_mapping(value: Mapping[object, object]) -> Mapping[str, object]:
    return {str(key): item for key, item in value.items()}


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return _string_mapping(cast(Mapping[object, object], value))


__all__ = [
    "evaluate_project_production_authorization",
    "evaluate_project_production_authorization_v2",
    "require_project_production_authorization",
    "require_project_production_authorization_v2",
]
