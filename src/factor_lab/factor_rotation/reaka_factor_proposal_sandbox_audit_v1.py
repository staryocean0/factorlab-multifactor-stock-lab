"""Five-in-one audit for the provisional REAKA factor proposal sandbox."""

from __future__ import annotations

from collections.abc import Mapping

from factor_lab.governance.canonicalization import canonical_digest


def build_sandbox_infrastructure_audit(
    *,
    surfaces: Mapping[str, Mapping[str, object]],
    pilot_acceptance: Mapping[str, object],
) -> dict[str, object]:
    required = {"documents", "whitepaper_contract", "code", "tests", "workflow", "scripts", "pilot_evidence"}
    blockers: list[str] = []
    for name in sorted(required):
        surface = surfaces.get(name)
        if not isinstance(surface, Mapping):
            blockers.append(f"factor_sandbox_surface_missing:{name}")
        elif surface.get("status") != "passed":
            blockers.append(f"factor_sandbox_surface_failed:{name}")
    if pilot_acceptance.get("status") != "passed_pilot":
        blockers.append("factor_sandbox_pilot_acceptance_failed")
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_factor_proposal_sandbox_infrastructure_audit@0.1",
        "status": "passed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "surfaces": {name: dict(value) for name, value in surfaces.items()},
        "pilot_acceptance_digest": pilot_acceptance.get("canonical_digest"),
        "pilot_terminal_status": pilot_acceptance.get("pilot_terminal_status"),
        "workflow_handles_negative_terminal": (
            pilot_acceptance.get("workflow_behavior")
            == "passed_negative_terminal_and_stopped_without_formula_change"
        ),
        "parallel_execution_authorized": False,
        "factor_admission_authority": False,
        "successor_training_allowed": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def validate_sandbox_infrastructure_audit(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body):
        blockers.append("factor_sandbox_audit_digest_mismatch")
    if payload.get("status") != "passed":
        blockers.append("factor_sandbox_audit_not_passed")
    if payload.get("workflow_handles_negative_terminal") is not True:
        blockers.append("factor_sandbox_negative_terminal_not_proven")
    for field in ("parallel_execution_authorized", "factor_admission_authority", "successor_training_allowed"):
        if payload.get(field) is not False:
            blockers.append(f"factor_sandbox_audit_authority_invalid:{field}")
    return blockers


__all__ = ["build_sandbox_infrastructure_audit", "validate_sandbox_infrastructure_audit"]
