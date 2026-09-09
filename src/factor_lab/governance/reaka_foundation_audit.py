"""Read-only audit of the bounded REAKA current@1.2 evidence closure.

This is an audit, not a controller acceptance or permission to train. Missing
historical bytes are reported separately from contradictory available bytes.
"""

from __future__ import annotations

import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from factor_lab.governance.canonicalization import canonical_digest

CURRENT_MANIFEST = "docs/ops/reaka_multifactor_current_manifest@1.2.json"
CURRENT_ENTRY = "docs/user/reaka_multifactor_current_workflow_v1_2.md"
STAGE4_ROOT = "output/factor-rotation/reaka_v2_stage4_observable_factor_pairing_v1_2011_2025"
STATE_ROOT = "output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025"
FACTOR_ROOT = "output/factor-rotation/reaka_k1_only_factor_kline_selector_v1_2011_2025"
SEMANTICS = {
    "observable_state_equals_latent_operator_state": False,
    "user_supplies_operator_count": False,
    "model_learns_operator_matrices": True,
    "model_learns_operator_assignments": True,
    "stage3_may_select_operator_count": False,
    "effective_operator_count_is_post_training_evidence": True,
    "portfolio_top_k_is_operator_count": False,
}
CLOSED_FLAGS = (
    "stage5_execution_allowed", "model_training_allowed",
    "account_execution_allowed", "production_authority",
)
STAGE4_FILES = {
    "pairing_panel.csv", "annual_dispersion.csv", "episode_dispersion.csv",
    "hypothesis_summary.csv", "advisor_interpretation_request.json",
}


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return "sha256:" + hashlib.file_digest(handle, "sha256").hexdigest()


class _Audit:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.findings: list[dict[str, str]] = []
        self.checks = 0

    def add(self, severity: str, code: str, path: str, detail: str) -> None:
        finding = {"severity": severity, "code": code, "path": path, "detail": detail}
        if finding not in self.findings:
            self.findings.append(finding)

    def path(self, relative: str) -> Path | None:
        path = (self.root / relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(self.root):
            self.add("error", "path_outside_package", relative, "Expected a repository-relative path.")
            return None
        return path

    def hashed(self, relative: str, expected: Any, *, historical: bool = False) -> bool:
        path = self.path(relative)
        if path is None:
            return False
        self.checks += 1
        if not path.is_file():
            self.add("gap" if historical else "error", "missing_frozen_file", relative,
                     "The recorded bytes are unavailable; no historical replay is certified.")
            return False
        if file_digest(path) != expected:
            self.add("gap" if historical else "error", "frozen_digest_mismatch", relative,
                     "Available bytes differ from the recorded SHA-256; frozen receipts were not rewritten.")
            return False
        return True

    def json(self, relative: str, *, missing_is_gap: bool = False) -> dict[str, Any] | None:
        path = self.path(relative)
        if path is None:
            return None
        if not path.is_file():
            self.add("gap" if missing_is_gap else "error", "missing_json", relative,
                     "Required evidence is not shipped or is missing.")
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
        except (ValueError, OSError) as exc:
            self.add("error", "invalid_json", relative, str(exc))
            return None
        body = dict(payload)
        expected = body.pop("canonical_digest", None)
        self.checks += 1
        if expected != canonical_digest(body):
            self.add("error", "canonical_digest_mismatch", relative, "Canonical JSON digest is invalid or missing.")
        return payload

    def equal(self, actual: Any, expected: Any, code: str, path: str) -> None:
        self.checks += 1
        # Booleans must not pass as the equal integers 0 and 1.
        if actual != expected or (isinstance(expected, bool) and actual is not expected):
            self.add("error", code, path, f"Expected {expected!r}; found {actual!r}.")

    def semantic(self, payload: dict[str, Any], path: str) -> None:
        self.equal(payload.get("semantic_invariants"), SEMANTICS, "semantic_invariants_mismatch", path)
        for key, expected in SEMANTICS.items():
            self.equal(payload.get("semantic_invariants", {}).get(key), expected, "semantic_invariant_type", path)

    def closed(self, payload: dict[str, Any], path: str, flags: tuple[str, ...] = CLOSED_FLAGS) -> None:
        for flag in flags:
            self.equal(payload.get(flag), False, "downstream_authority_not_closed", f"{path}:{flag}")

    def historical_closure(self, payload: dict[str, Any]) -> None:
        for key in ("source_closure", "base_source_closure", "stage4_source_closure"):
            closure = payload.get(key, {})
            if not isinstance(closure, dict):
                self.add("error", "invalid_source_closure", key, "Expected a path-to-digest object.")
                continue
            for relative, expected in closure.items():
                self.hashed(relative, expected, historical=True)

    def run(self) -> dict[str, Any]:
        manifest = self.json(CURRENT_MANIFEST)
        if manifest is None:
            return self.report()
        self.semantic(manifest, CURRENT_MANIFEST)
        self.closed(manifest, CURRENT_MANIFEST)
        self.equal(manifest.get("next_legal_action"), "user_financial_review_of_stage4_evidence",
                   "current_action_mismatch", CURRENT_MANIFEST)
        self.equal(manifest.get("default_unlisted_classification"),
                   "historical_or_specialized_no_current_normative_authority", "default_authority_mismatch", CURRENT_MANIFEST)
        roots = manifest.get("normative_roots", [])
        if not isinstance(roots, list):
            self.add("error", "invalid_normative_roots", CURRENT_MANIFEST, "Expected a list.")
            return self.report()
        roles: dict[str, str] = {}
        seen_paths: set[str] = set()
        payloads: dict[str, dict[str, Any]] = {}
        for item in roots:
            if not isinstance(item, dict) or not isinstance(item.get("role"), str) or not isinstance(item.get("path"), str):
                self.add("error", "invalid_normative_root", CURRENT_MANIFEST, "Each root needs a role and relative path.")
                continue
            role, relative = item["role"], item["path"]
            if role in roles or relative in seen_paths:
                self.add("error", "duplicate_normative_owner", relative, "Roles and paths must each be unique.")
            roles[role] = relative
            seen_paths.add(relative)
            if relative in manifest.get("revoked_current_normative_paths", []):
                self.add("error", "revoked_root_is_current", relative, "Revoked files cannot be current normative roots.")
            self.hashed(relative, item.get("file_digest"))
            if relative.endswith(".json"):
                payload = self.json(relative)
                if payload is not None:
                    payloads[role] = payload
                    if "canonical_digest" in item:
                        self.equal(payload.get("canonical_digest"), item["canonical_digest"], "root_identity_mismatch", relative)
                    if "semantic_invariants" in payload:
                        # Older specialized contracts have their own invariant
                        # vocabulary. Only shared names may be compared there.
                        invariants = payload["semantic_invariants"]
                        if role in {"semantic_ontology_contract", "six_surface_contract", "observable_context_state_machine"}:
                            self.semantic(payload, relative)
                        elif isinstance(invariants, dict):
                            for key in set(invariants) & set(SEMANTICS):
                                self.equal(invariants[key], SEMANTICS[key], "semantic_invariant_mismatch", f"{relative}:{key}")
                        else:
                            self.add("error", "invalid_semantic_invariants", relative, "Expected an object.")
                    self.historical_closure(payload)
        self.historical_closure(manifest)
        self.equal(roles.get("current_entry"), CURRENT_ENTRY, "current_entry_version_mismatch", CURRENT_MANIFEST)
        entry = self.path(CURRENT_ENTRY)
        if entry is not None and entry.is_file() and CURRENT_MANIFEST not in entry.read_text(encoding="utf-8"):
            self.add("error", "entry_manifest_reference_missing", CURRENT_ENTRY, "Current workflow must name manifest@1.2.")
        handoff_ref = roles.get("current_handoff")
        if handoff_ref:
            handoff = self.path(handoff_ref)
            if handoff is not None and handoff.is_file():
                text = handoff.read_text(encoding="utf-8")
                for key, expected in SEMANTICS.items():
                    if f"{key} = {str(expected).lower()}" not in text:
                        self.add("error", "handoff_semantic_checksum_missing", handoff_ref, key)
                if CURRENT_MANIFEST not in text or CURRENT_ENTRY not in text:
                    self.add("gap", "frozen_handoff_version_conflict", handoff_ref,
                             "Current manifest retains a frozen handoff that names an older current entry; use the bounded entry overlay.")
        contract = payloads.get("current_stage4_contract")
        validation = payloads.get("current_stage4_validation")
        if contract is None or validation is None:
            self.add("error", "stage4_normative_roots_missing", CURRENT_MANIFEST, "Stage4 contract and validation are required.")
        else:
            self.stage4(contract, validation, roles)
        return self.report()

    def stage4(self, contract: dict[str, Any], validation: dict[str, Any], roles: dict[str, str]) -> None:
        contract_ref = roles["current_stage4_contract"]
        validation_ref = roles["current_stage4_validation"]
        self.closed(contract.get("authority", {}), contract_ref)
        self.closed(validation, validation_ref)
        self.equal(contract.get("fresh_oos"), False, "fresh_oos_claim", contract_ref)
        self.equal(validation.get("contract_digest"), contract.get("canonical_digest"), "validation_contract_mismatch", validation_ref)
        self.equal(validation.get("advisor_interpretation_receipt_present"), False, "financial_receipt_forged", validation_ref)
        self.equal(set(contract.get("output_inventory", [])), STAGE4_FILES | {"result.json"}, "output_inventory_mismatch", contract_ref)
        review_ref = roles.get("current_stage4_review_request")
        if review_ref:
            self.hashed(review_ref, validation.get("review_request_digest"))
        for tree in ("formal", "isolated"):
            tree_ref = f"{STAGE4_ROOT}/{tree}"
            # These records belong to an old execution, not to this audit run.
            for name, input_root in (("state_months.csv", STATE_ROOT), ("monthly_selector_panel.csv", FACTOR_ROOT)):
                expected = contract.get("input_digests", {}).get(tree, {}).get(name)
                if expected is None:
                    self.add("error", "input_digest_missing", contract_ref, f"{tree}/{name}")
                else:
                    relative = f"{input_root}/{tree}/{name}"
                    path = self.path(relative)
                    self.hashed(relative, expected, historical=path is not None and not path.exists())
            result_ref = f"{tree_ref}/result.json"
            result = self.json(result_ref, missing_is_gap=True)
            if result is None:
                continue
            self.closed(result, result_ref)
            self.equal(result.get("advisor_interpretation_receipt_present"), False, "financial_receipt_forged", result_ref)
            self.equal(result.get("contract_digest"), contract.get("canonical_digest"), "result_contract_mismatch", result_ref)
            self.equal(result.get("canonical_digest"), validation.get(f"{tree}_result_digest"), "validation_result_mismatch", result_ref)
            outputs = result.get("output_digests", {})
            self.equal(set(outputs), STAGE4_FILES, "result_output_inventory_mismatch", result_ref)
            for name, expected in outputs.items():
                if name not in STAGE4_FILES:
                    continue
                self.hashed(f"{tree_ref}/{name}", expected)
            request_ref = f"{tree_ref}/advisor_interpretation_request.json"
            request = self.json(request_ref)
            if request is not None:
                self.semantic(request, request_ref)
                self.closed(request, request_ref, ("stage5_execution_allowed", "production_authority"))
                self.equal(request.get("advisor_interpretation_receipt_present"), False, "financial_receipt_forged", request_ref)
                self.equal(result.get("advisor_request_digest"), request.get("canonical_digest"), "advisor_request_identity_mismatch", result_ref)
            summary = self.path(f"{tree_ref}/hypothesis_summary.csv")
            if summary is not None and summary.is_file():
                with summary.open(encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                if not rows or any(row.get("financial_verdict") != "waiting_user_review" for row in rows):
                    self.add("error", "summary_financial_verdict_invalid", str(summary.relative_to(self.root)),
                             "The bounded evidence must not contain a signed financial verdict.")
            panel_ref = f"{tree_ref}/pairing_panel.csv"
            panel = self.path(panel_ref)
            if panel is not None and panel.is_file():
                with panel.open(encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    fields = set(reader.fieldnames or [])
                    rows = list(reader)
                key_fields = ("data_role", "decision_clock", "period")
                if not set(key_fields + ("source_period",)) <= fields:
                    self.add("error", "pairing_schema_missing", panel_ref,
                             "Expected data_role, decision_clock, period, and source_period.")
                else:
                    counts = Counter(tuple(row[field] for field in key_fields) for row in rows)
                    duplicates = {str(key): count for key, count in sorted(counts.items()) if count > 1}
                    if duplicates:
                        self.add("error", "duplicate_condition_month", panel_ref,
                                 "Monthly observations are not unique by (data_role, decision_clock, period): "
                                 + json.dumps(duplicates, sort_keys=True)
                                 + ". Row counts cannot be reported as independent month counts; frozen data were not deduplicated.")
                    for row in rows:
                        try:
                            source_year, source_month = map(int, row["source_period"].split("-"))
                            year, month = map(int, row["period"].split("-"))
                            valid = (
                                1 <= source_month <= 12 and 1 <= month <= 12
                                and year * 12 + month == source_year * 12 + source_month + 1
                            )
                        except (AttributeError, TypeError, ValueError):
                            valid = False
                        if not valid:
                            self.add("error", "state_is_not_prior_month", panel_ref,
                                     "Every decision month must use the immediately previous calendar month's observable state.")
                            break
        for name in STAGE4_FILES | {"result.json"}:
            formal = self.path(f"{STAGE4_ROOT}/formal/{name}")
            isolated = self.path(f"{STAGE4_ROOT}/isolated/{name}")
            if formal is not None and isolated is not None and formal.is_file() and isolated.is_file():
                self.equal(file_digest(formal), file_digest(isolated), "formal_isolated_mismatch", name)

    def report(self) -> dict[str, Any]:
        errors = sum(row["severity"] == "error" for row in self.findings)
        gaps = sum(row["severity"] == "gap" for row in self.findings)
        return {
            "schema_id": "factorlab.reaka_foundation_readonly_audit@1.0",
            "status": "failed" if errors else "incomplete" if gaps else "passed",
            "audit_execution_completed": True,
            "foundation_readiness": "blocked" if errors or gaps else "available_evidence_integrity_verified",
            "foundation_ready": not errors and not gaps,
            "manifest": CURRENT_MANIFEST,
            "verified_checks": self.checks,
            "hard_error_count": errors,
            "evidence_gap_count": gaps,
            "findings": self.findings,
            "model_training_executed": False,
            "account_execution_performed": False,
            "financial_receipt_signed": False,
            "controller_acceptance_created": False,
            "scientific_result_validated": False,
            "fresh_oos": False,
            "production_authority": False,
        }


def audit_foundation(root: Path) -> dict[str, Any]:
    """Inspect available bytes without modifying files or invoking old workflows."""
    return _Audit(root).run()
