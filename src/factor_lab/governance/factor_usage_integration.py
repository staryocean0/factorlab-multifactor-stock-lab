"""Frozen strategy-factor integration and cutover contracts.

This module deliberately stops at execution eligibility.  It never grants
factor admission, admitted-factor status, or project production authority.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import ParseResult, unquote, urlparse

from factor_lab.core.settings import PROJECT_ROOT, get_artifacts_dir
from factor_lab.governance.evidence_resolver import (
    EvidenceCatalog,
    resolve_evidence_ref,
    validate_manual_authorization_decision,
)
from factor_lab.governance.factor_family_usage_governance import (
    SCHEMA_ID as FACTOR_FAMILY_USAGE_GOVERNANCE_SCHEMA_ID,
)
from factor_lab.governance.factor_family_usage_governance import (
    validate_factor_family_usage_governance,
)
from factor_lab.governance.factor_usage_discovery import (
    validate_factor_usage_campaign_receipt,
    validate_factor_usage_hypothesis,
    validate_factor_usage_lifecycle_event,
    validate_factor_usage_trial_evidence,
    validate_search_scope_dimension_manifest,
    validate_strategy_factor_action_space,
    validate_strategy_factor_information_evidence,
)
from factor_lab.governance.selection_freeze_manifest import (
    validate_selection_freeze_manifest_v2,
    validate_strategy_usage_candidate_fingerprint,
)
from factor_lab.governance.temporal_governance_repository import (
    TemporalGovernanceRepository,
    canonical_digest,
)

FROZEN_BINDING_SCHEMA_ID = "frozen_strategy_factor_binding@1.0"
INTEGRATION_EVIDENCE_SCHEMA_ID = "strategy_integration_evidence@1.0"
INTEGRATION_REVIEW_SCHEMA_ID = "strategy_integration_review_package@1.0"
INTEGRATION_CLAIM_SCHEMA_ID = "strategy_integration_claim@1.0"
INTEGRATION_REVIEW_EVENT_SCHEMA_ID = "strategy_integration_review_event@1.0"
INTEGRATION_DECISION_EVENT_SCHEMA_ID = "strategy_integration_decision_event@1.0"
INTEGRATION_METRIC_CONTRACT_SCHEMA_ID = "strategy_integration_metric_contract@1.0"
INTEGRATION_NO_HARM_CONTRACT_SCHEMA_ID = "strategy_integration_no_harm_contract@1.0"
USAGE_DISCOVERY_CUTOVER_SCHEMA_ID = "usage_discovery_cutover@1.0"
STRATEGY_USAGE_CUTOVER_SCHEMA_ID = "strategy_usage_cutover@1.0"
CUTOVER_TRANSITION_SCHEMA_ID = "strategy_usage_cutover_transition_receipt@1.0"
CANONICALIZATION_VERSION = "factorlab_canonical_json@1"

_INTEGRATION_STAGES = frozenset({"validation", "prospective", "lockbox"})
_INTEGRATION_OUTCOMES = frozenset(
    {"supported", "inconclusive", "rejected", "invalid_evidence"}
)
_REVIEW_READINESS = frozenset({"ready_for_integration_review", "blocked"})
_CUTOVER_MODES = frozenset({"legacy_read", "shadow_audit", "required"})
_STRICT_INTEGRATION_STAGES = frozenset({"validation", "prospective", "lockbox"})
_NESTED_SCHEMA_IDS: dict[str, frozenset[str]] = {
    "dataset_manifest": frozenset({"dataset_manifest@1.0"}),
    "temporal_policy": frozenset({"temporal_policy@1.0"}),
    "temporal_policy_manifest": frozenset({"temporal_policy_manifest@1.0"}),
    "strategy_temporal_policy": frozenset({"strategy_temporal_policy@1.0"}),
    "window_contract": frozenset({"window_contract@1.0"}),
    "strategy_usage_window_contract": frozenset({"strategy_usage_window_contract@1.0"}),
    "strategy_integration_window_contract": frozenset(
        {"strategy_integration_window_contract@1.0"}
    ),
    "fold_contract": frozenset({"fold_contract@1.0"}),
    "strategy_usage_fold_contract": frozenset({"strategy_usage_fold_contract@1.0"}),
    "strategy_integration_fold_contract": frozenset(
        {"strategy_integration_fold_contract@1.0"}
    ),
}


def _is_sha256_digest(value: object) -> bool:
    """Return whether ``value`` is one complete lowercase SHA-256 digest."""

    text = str(value).strip()
    return (
        len(text) == 71
        and text.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in text[7:])
    )


def _legacy_compatibility_digest(label: str) -> str:
    """Create an explicit, valid digest for unresolved historical metadata."""

    return canonical_digest({"legacy_unresolved": label})


def _catalog_payload(
    ref: str,
    catalog: EvidenceCatalog | None,
    *,
    expected_artifact_type: str | None = None,
) -> tuple[dict[str, object] | None, str | None, bool]:
    """Load one governance payload without letting a catalog shadow a file.

    A file-shaped ``artifact://`` reference beneath a governed artifact root
    names the file, not a same-key catalog entry.  The catalog may supplement
    immutable checksum/path metadata, but any semantic disagreement is a
    fail-closed condition.
    """

    parsed = urlparse(ref)
    catalog_payload: Mapping[str, object] | None = None
    if catalog is not None:
        key = (
            f"{parsed.netloc}{parsed.path}"
            if parsed.netloc
            else parsed.path.lstrip("/")
        )
        catalog_payload = catalog.get(ref) or catalog.get(key)
    if parsed.scheme != "artifact":
        return (
            (dict(catalog_payload) if catalog_payload is not None else None),
            None,
            False,
        )
    path, blocker = _governance_artifact_file_path(parsed)
    if blocker:
        return (
            (dict(catalog_payload) if catalog_payload is not None else None),
            blocker,
            False,
        )
    if path is None or not path.is_file():
        return (
            (dict(catalog_payload) if catalog_payload is not None else None),
            None,
            False,
        )
    try:
        loaded = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "governance_artifact_file_invalid", True
    if not isinstance(loaded, dict):
        return None, "governance_artifact_file_invalid", True
    raw = cast(Mapping[object, object], loaded)
    file_payload = {str(key): value for key, value in raw.items()}
    if catalog_payload is None:
        return file_payload, None, True

    artifact_type = expected_artifact_type or _first_text(file_payload, "artifact_type")
    own_digest_field = _digest_field(artifact_type, file_payload)
    metadata_fields = {
        "checksum",
        "sha256",
        "path",
        "resolved_path_or_uri",
        own_digest_field,
    }
    merged = dict(file_payload)
    for key, value in catalog_payload.items():
        key_text = str(key)
        if key_text not in metadata_fields:
            if key_text not in file_payload or file_payload[key_text] != value:
                return (
                    file_payload,
                    "governance_artifact_catalog_file_semantic_mismatch",
                    True,
                )
            continue
        if key_text in file_payload and file_payload[key_text] != value:
            return (
                file_payload,
                "governance_artifact_catalog_file_metadata_mismatch",
                True,
            )
        _ = merged.setdefault(key_text, value)
    return merged, None, True


def _governance_artifact_file_path(
    parsed: ParseResult,
) -> tuple[Path | None, str | None]:
    """Resolve a file URI only beneath explicitly governed artifact roots."""

    netloc = unquote(parsed.netloc)
    path_text = unquote(parsed.path)
    if "\x00" in netloc or "\x00" in path_text:
        return None, "governance_artifact_path_not_allowed"
    raw_parts = Path(netloc, path_text.lstrip("/")).parts
    if ".." in raw_parts:
        return None, "governance_artifact_parent_traversal_forbidden"

    roots = _governance_artifact_roots()
    if netloc:
        relative = Path(netloc, path_text.lstrip("/"))
        escaped_root = False
        for root in roots:
            relative_for_root = (
                Path(*relative.parts[1:])
                if relative.parts and relative.parts[0] == root.name
                else relative
            )
            candidate = (root / relative_for_root).resolve(strict=False)
            if candidate.is_file() and not candidate.is_relative_to(root):
                escaped_root = True
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate, None
        blocker = "governance_artifact_path_not_allowed" if escaped_root else None
        return None, blocker

    candidate = Path(path_text).resolve(strict=False)
    if not any(candidate.is_relative_to(root) for root in roots):
        return None, "governance_artifact_path_not_allowed"
    return candidate, None


def _governance_artifact_roots() -> tuple[Path, ...]:
    configured = get_artifacts_dir().resolve(strict=False)
    project = (PROJECT_ROOT / "artifacts").resolve(strict=False)
    return tuple(dict.fromkeys((configured, project)))


def _blocked_governance_resolution(ref: str, blocker: str | None) -> dict[str, object]:
    blockers = ["evidence_artifact_not_resolved"]
    if blocker:
        blockers.append(blocker)
    return {
        "status": "blocked",
        "evidence_ref": ref,
        "artifact_type": "",
        "schema_id": "",
        "schema_version": "",
        "checksum_status": "not_checked",
        "fingerprint_status": "not_checked",
        "lineage_status": "not_checked",
        "resolved_path_or_uri": "",
        "blockers": blockers,
        "warnings": [],
        "canonical_digest": "",
    }


def resolve_governance_artifact(
    ref: object,
    *,
    evidence_catalog: EvidenceCatalog | None,
    expected_artifact_type: str,
    expected_digest: str | None = None,
    expected_candidate_fingerprint: str | None = None,
) -> dict[str, object]:
    """Resolve a typed artifact and recompute its immutable payload digest."""

    ref_text = str(ref or "").strip()
    payload, file_blocker, file_backed = _catalog_payload(
        ref_text,
        evidence_catalog,
        expected_artifact_type=expected_artifact_type,
    )
    resolver_payload = dict(payload or {})
    if payload is not None and not (payload.get("checksum") or payload.get("sha256")):
        semantic_digest = str(
            payload.get(_digest_field(expected_artifact_type, payload), "")
        ).strip()
        if semantic_digest:
            resolver_payload = {
                **payload,
                "checksum": semantic_digest,
                "computed_checksum": semantic_digest,
            }
    if payload is None:
        base = _blocked_governance_resolution(ref_text, file_blocker)
    else:
        safe_ref = "artifact://factor-lab-governance-resolver/payload"
        # The generic evidence resolver supports legacy file checks through a
        # payload ``path`` field. Governance payloads have already crossed the
        # root-containment gate above, so never let untrusted metadata trigger
        # a second filesystem read.
        _ = resolver_payload.pop("path", None)
        _ = resolver_payload.pop("resolved_path_or_uri", None)
        base = resolve_evidence_ref(
            safe_ref,
            catalog={safe_ref: resolver_payload},
            expected_artifact_type=expected_artifact_type,
            expected_candidate_fingerprint=expected_candidate_fingerprint,
        )
        base["evidence_ref"] = ref_text
        base["resolved_path_or_uri"] = ref_text
    blockers = list(_strings(base.get("blockers")))
    if file_blocker:
        blockers.append(file_blocker)
    recomputed = ""
    recorded = ""
    if payload is None:
        blockers.append("governance_artifact_payload_not_resolved")
    else:
        digest_field = _digest_field(expected_artifact_type, payload)
        recorded = str(payload.get(digest_field, "")).strip()
        digest_payload = dict(payload)
        _ = digest_payload.pop(digest_field, None)
        _ = digest_payload.pop("checksum", None)
        _ = digest_payload.pop("sha256", None)
        _ = digest_payload.pop("computed_checksum", None)
        _ = digest_payload.pop("path", None)
        _ = digest_payload.pop("resolved_path_or_uri", None)
        for excluded_field in _digest_excluded_fields(expected_artifact_type):
            _ = digest_payload.pop(excluded_field, None)
        recomputed = canonical_digest(digest_payload)
        if not recorded:
            blockers.append("governance_artifact_digest_missing")
        elif recorded != recomputed:
            blockers.append("governance_artifact_digest_mismatch")
        if expected_digest and recorded != expected_digest:
            blockers.append("governance_artifact_expected_digest_mismatch")
    if base.get("status") != "resolved":
        blockers.append("governance_artifact_base_resolution_failed")
    status = "resolved" if not blockers else "blocked"
    response_payload = payload or {}
    if file_backed and status == "blocked":
        response_payload = {}
        base["resolved_path_or_uri"] = ""
    return {
        **base,
        "status": status,
        "payload": response_payload,
        "recorded_digest": recorded,
        "recomputed_digest": recomputed,
        "blockers": sorted(set(blockers)),
    }


def _digest_field(artifact_type: str, payload: Mapping[str, object]) -> str:
    preferred = {
        "strategy_factor_information_evidence": "canonical_digest",
        "strategy_factor_action_space": "canonical_digest",
        "factor_usage_hypothesis": "definition_digest",
        "search_scope_dimension_manifest": "manifest_digest",
        "factor_usage_trial_evidence": "trial_digest",
        "factor_usage_campaign_receipt": "receipt_digest",
        "factor_usage_lifecycle_event": "event_digest",
        "strategy_usage_candidate_fingerprint": "artifact_digest",
        "selection_freeze_manifest": "manifest_checksum",
        "frozen_strategy_factor_binding": "binding_digest",
        "strategy_integration_evidence": "evidence_digest",
        "strategy_integration_review_package": "package_digest",
        "strategy_integration_claim": "claim_digest",
        "strategy_integration_review_event": "event_digest",
        "strategy_integration_decision_event": "event_digest",
        "strategy_integration_metric_contract": "contract_digest",
        "strategy_integration_no_harm_contract": "contract_digest",
        "strategy_integration_resolution_receipt": "receipt_digest",
        "strategy_usage_execution_receipt": "receipt_digest",
        "strategy_usage_cutover_transition_receipt": "receipt_digest",
    }.get(artifact_type)
    if preferred and preferred in payload:
        return preferred
    return "checksum"


def _digest_excluded_fields(artifact_type: str) -> tuple[str, ...]:
    if artifact_type == "factor_usage_hypothesis":
        return ("usage_signature_hash",)
    return ()


def resolve_factor_usage_campaign_dependencies(
    receipt: Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None,
    governance_repository: TemporalGovernanceRepository | None = None,
    expected_candidate_fingerprint: str | None = None,
) -> dict[str, object]:
    """Resolve the campaign's immutable evidence graph, not only its envelope."""

    blockers: list[str] = []
    reports: dict[str, object] = {}
    resolved_payloads: dict[str, Mapping[str, object]] = {}
    _extend_validation_blockers(
        blockers,
        "campaign",
        validate_factor_usage_campaign_receipt(receipt),
    )
    campaign_id = _first_text(receipt, "campaign_id")
    strategy_id = _first_text(receipt, "strategy_id")
    factor_ref = _first_text(receipt, "factor_ref")
    single_specs = (
        (
            "information_evidence",
            "factor_information_evidence_ref",
            "strategy_factor_information_evidence",
            "",
        ),
        (
            "factor_family_governance",
            "factor_family_governance_ref",
            "factor_family_governance",
            "",
        ),
        (
            "baseline",
            "baseline_artifact_ref",
            "strategy_baseline",
            _first_text(receipt, "baseline_digest"),
        ),
        (
            "action_space",
            "action_space_ref",
            "strategy_factor_action_space",
            "",
        ),
        (
            "dimension_manifest",
            "dimension_manifest_ref",
            "search_scope_dimension_manifest",
            "",
        ),
        (
            "selection_event",
            "selection_event_ref",
            "factor_usage_lifecycle_event",
            "",
        ),
    )
    for name, field, artifact_type, expected_digest in single_specs:
        report = resolve_governance_artifact(
            receipt.get(field),
            evidence_catalog=evidence_catalog,
            expected_artifact_type=artifact_type,
            expected_digest=expected_digest or None,
        )
        reports[name] = report
        blockers.extend(_prefixed_blockers(name, report))
        payload = _mapping(report.get("payload"))
        resolved_payloads[name] = payload
        if name == "information_evidence":
            _extend_validation_blockers(
                blockers,
                name,
                validate_strategy_factor_information_evidence(payload),
            )
            _require_same(blockers, "strategy_id", strategy_id, payload, name)
            _require_same(blockers, "factor_ref", factor_ref, payload, name)
        elif name == "factor_family_governance":
            _extend_validation_blockers(
                blockers,
                name,
                validate_factor_family_usage_governance(payload),
            )
            if _first_text(payload, "schema_id") != (
                FACTOR_FAMILY_USAGE_GOVERNANCE_SCHEMA_ID
            ):
                blockers.append("factor_governance_schema_id_invalid")
            _require_same(blockers, "strategy_id", strategy_id, payload, name)
            _require_same(blockers, "factor_ref", factor_ref, payload, name)
            if _first_text(payload, "parent_multiplicity_family_id") != _first_text(
                receipt, "parent_multiplicity_family_id"
            ):
                blockers.append("factor_governance_multiplicity_family_mismatch")
            if _first_text(payload, "owner_layer") != "factor_identity":
                blockers.append("factor_governance_owner_layer_invalid")
            factor_dimensions = set(
                _strings(payload.get("factor_identity_dimension_ids"))
            )
            if not factor_dimensions:
                blockers.append("factor_governance_dimension_ids_required")
            if any(
                not item.startswith("factor_identity:") for item in factor_dimensions
            ):
                blockers.append("factor_governance_dimension_namespace_invalid")
        elif name == "baseline":
            _require_same(blockers, "strategy_id", strategy_id, payload, name)
        elif name == "action_space":
            _extend_validation_blockers(
                blockers,
                name,
                validate_strategy_factor_action_space(payload),
            )
            _require_same(blockers, "strategy_id", strategy_id, payload, name)
            _require_same_ref(
                blockers,
                "action_space_baseline_ref",
                _first_text(receipt, "baseline_artifact_ref"),
                _first_text(payload, "baseline_artifact_ref"),
            )
            if _first_text(payload, "baseline_digest") != _first_text(
                receipt, "baseline_digest"
            ):
                blockers.append("action_space_baseline_digest_mismatch")
        elif name == "dimension_manifest":
            _extend_validation_blockers(
                blockers,
                name,
                validate_search_scope_dimension_manifest(payload),
            )
            _require_same(blockers, "campaign_id", campaign_id, payload, name)
            if _first_text(payload, "parent_multiplicity_family_id") != _first_text(
                receipt, "parent_multiplicity_family_id"
            ):
                blockers.append("dimension_manifest_multiplicity_family_mismatch")
        elif name == "selection_event":
            _extend_validation_blockers(
                blockers,
                name,
                validate_factor_usage_lifecycle_event(payload),
            )

    hypothesis_reports: list[dict[str, object]] = []
    hypotheses_by_ref: dict[str, Mapping[str, object]] = {}
    hypothesis_refs = _strings(receipt.get("registered_hypothesis_refs"))
    registered_signatures = _strings(receipt.get("registered_usage_signature_hashes"))
    for index, ref in enumerate(hypothesis_refs):
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type="factor_usage_hypothesis",
        )
        hypothesis_reports.append(report)
        blockers.extend(_prefixed_blockers(f"hypothesis:{index}", report))
        payload = _mapping(report.get("payload"))
        hypotheses_by_ref[ref] = payload
        _extend_validation_blockers(
            blockers,
            f"hypothesis:{index}",
            validate_factor_usage_hypothesis(payload),
        )
        _campaign_identity_blockers(
            blockers,
            payload=payload,
            prefix=f"hypothesis:{index}",
            campaign_id=campaign_id,
            strategy_id=strategy_id,
            factor_ref=factor_ref,
        )
        signature = _first_text(payload, "usage_signature_hash")
        if (
            index >= len(registered_signatures)
            or signature != registered_signatures[index]
        ):
            blockers.append(f"hypothesis_registered_signature_mismatch:{index}")
        for field in (
            "baseline_artifact_ref",
            "baseline_digest",
            "factor_information_evidence_ref",
            "action_space_ref",
            "search_scope_registry_id",
            "data_usage_registry_id",
            "parent_multiplicity_family_id",
        ):
            if _first_text(payload, field) != _first_text(receipt, field):
                blockers.append(f"hypothesis_campaign_{field}_mismatch:{index}")
        action_space = resolved_payloads.get("action_space", {})
        if _first_text(payload, "action_space_digest") != _first_text(
            action_space, "canonical_digest"
        ):
            blockers.append(f"hypothesis_action_space_digest_mismatch:{index}")
        action_id = _first_text(payload, "action_id")
        if action_id not in set(_strings(action_space.get("action_ids"))):
            blockers.append(f"hypothesis_action_id_not_registered:{index}")
        if action_id in set(_strings(action_space.get("forbidden_actions"))):
            blockers.append(f"hypothesis_action_id_forbidden:{index}")
    reports["hypotheses"] = hypothesis_reports
    dimension_payload = resolved_payloads.get("dimension_manifest", {})
    candidate_dependencies = _resolve_dimension_candidate_dependencies(
        dimension_payload,
        evidence_catalog=evidence_catalog,
    )
    reports["dimension_candidate_dependencies"] = candidate_dependencies
    blockers.extend(
        _prefixed_blockers("dimension_candidate_dependencies", candidate_dependencies)
    )
    combinations = {
        _first_text(_mapping(item), "hypothesis_ref"): _mapping(item)
        for item in _sequence(dimension_payload.get("explicit_sparse_combinations"))
    }
    for index, ref in enumerate(hypothesis_refs):
        combination = combinations.get(ref, {})
        hypothesis = hypotheses_by_ref.get(ref, {})
        if not combination:
            blockers.append(f"hypothesis_sparse_combination_missing:{index}")
            continue
        if _first_text(combination, "hypothesis_definition_digest") != _first_text(
            hypothesis, "definition_digest"
        ):
            blockers.append(f"hypothesis_sparse_definition_digest_mismatch:{index}")
        if _first_text(combination, "usage_signature_hash") != _first_text(
            hypothesis, "usage_signature_hash"
        ):
            blockers.append(f"hypothesis_sparse_usage_signature_mismatch:{index}")

    trial_reports: list[dict[str, object]] = []
    for index, ref in enumerate(_strings(receipt.get("trial_refs"))):
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type="factor_usage_trial_evidence",
        )
        trial_reports.append(report)
        blockers.extend(_prefixed_blockers(f"trial:{index}", report))
        payload = _mapping(report.get("payload"))
        _extend_validation_blockers(
            blockers,
            f"trial:{index}",
            validate_factor_usage_trial_evidence(payload),
        )
        _campaign_identity_blockers(
            blockers,
            payload=payload,
            prefix=f"trial:{index}",
            campaign_id=campaign_id,
            strategy_id=strategy_id,
            factor_ref=factor_ref,
        )
        if _first_text(payload, "hypothesis_ref") not in hypothesis_refs:
            blockers.append(f"trial_hypothesis_not_registered:{index}")
        if (
            _first_text(payload, "registered_usage_signature_hash")
            not in registered_signatures
        ):
            blockers.append(f"trial_usage_signature_not_registered:{index}")
        hypothesis = hypotheses_by_ref.get(_first_text(payload, "hypothesis_ref"), {})
        if _first_text(payload, "hypothesis_definition_digest") != _first_text(
            hypothesis, "definition_digest"
        ):
            blockers.append(f"trial_hypothesis_definition_digest_mismatch:{index}")
        if _first_text(payload, "registered_usage_signature_hash") != _first_text(
            hypothesis, "usage_signature_hash"
        ):
            blockers.append(f"trial_hypothesis_signature_pair_mismatch:{index}")
        if _first_text(payload, "search_scope_manifest_ref") != _first_text(
            receipt, "dimension_manifest_ref"
        ):
            blockers.append(f"trial_dimension_manifest_ref_mismatch:{index}")
        combination = combinations.get(_first_text(payload, "hypothesis_ref"), {})
        if _strings(payload.get("dimension_ids")) != _strings(
            combination.get("dimension_ids")
        ):
            blockers.append(f"trial_sparse_combination_dimensions_mismatch:{index}")
        for field in (
            "baseline_artifact_ref",
            "baseline_digest",
            "search_scope_registry_id",
            "data_usage_registry_id",
            "parent_multiplicity_family_id",
        ):
            if _first_text(payload, field) != _first_text(receipt, field):
                blockers.append(f"trial_campaign_{field}_mismatch:{index}")
    reports["trials"] = trial_reports

    information_dependencies = _resolve_campaign_nested_refs(
        resolved_payloads.get("information_evidence", {}),
        specs=(
            ("dataset_manifest_ref", {"dataset_manifest"}),
            (
                "temporal_policy_ref",
                {
                    "temporal_policy",
                    "temporal_policy_manifest",
                    "strategy_temporal_policy",
                },
            ),
        ),
        sequence_field="evidence_refs",
        evidence_catalog=evidence_catalog,
        campaign_id=campaign_id,
        strategy_id=strategy_id,
    )
    reports["information_dependencies"] = information_dependencies
    blockers.extend(
        _prefixed_blockers("information_dependencies", information_dependencies)
    )

    trial_dependency_reports: list[dict[str, object]] = []
    for index, report in enumerate(trial_reports):
        trial_dependencies = _resolve_campaign_nested_refs(
            _mapping(report.get("payload")),
            specs=(
                ("dataset_manifest_ref", {"dataset_manifest"}),
                (
                    "window_contract_ref",
                    {
                        "window_contract",
                        "strategy_usage_window_contract",
                        "strategy_integration_window_contract",
                    },
                ),
                (
                    "fold_contract_ref",
                    {
                        "fold_contract",
                        "strategy_usage_fold_contract",
                        "strategy_integration_fold_contract",
                    },
                ),
            ),
            sequence_field="artifact_refs",
            evidence_catalog=evidence_catalog,
            campaign_id=campaign_id,
            strategy_id=strategy_id,
        )
        trial_dependency_reports.append(trial_dependencies)
        blockers.extend(
            _prefixed_blockers(f"trial_dependencies:{index}", trial_dependencies)
        )
    reports["trial_dependencies"] = trial_dependency_reports

    attempt_reports: list[dict[str, object]] = []
    ledger_trial_refs: set[str] = set()
    ledger_attempt_ids: set[str] = set()
    for index, ref in enumerate(_strings(receipt.get("attempt_ledger_refs"))):
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type="factor_usage_attempt_ledger",
        )
        attempt_reports.append(report)
        blockers.extend(_prefixed_blockers(f"attempt_ledger:{index}", report))
        payload = _mapping(report.get("payload"))
        _campaign_identity_blockers(
            blockers,
            payload=payload,
            prefix=f"attempt_ledger:{index}",
            campaign_id=campaign_id,
            strategy_id=strategy_id,
            factor_ref=factor_ref,
        )
        if _first_text(payload, "dimension_manifest_ref") != _first_text(
            receipt, "dimension_manifest_ref"
        ):
            blockers.append(f"attempt_ledger_dimension_manifest_mismatch:{index}")
        ledger_trial_refs.update(_strings(payload.get("recorded_trial_refs")))
        ledger_attempt_ids.update(_strings(payload.get("recorded_attempt_ids")))
    reports["attempt_ledgers"] = attempt_reports

    selected = _first_text(receipt, "selected_hypothesis_ref")
    if selected and selected not in hypothesis_refs:
        blockers.append("selected_hypothesis_not_registered")
    trial_payloads = [_mapping(report.get("payload")) for report in trial_reports]
    trial_refs = set(_strings(receipt.get("trial_refs")))
    if ledger_trial_refs != trial_refs:
        blockers.append("attempt_ledger_trial_refs_mismatch")
    trial_attempt_ids = {_first_text(trial, "attempt_id") for trial in trial_payloads}
    if ledger_attempt_ids != trial_attempt_ids:
        blockers.append("attempt_ledger_attempt_ids_mismatch")
    if selected and not any(
        _first_text(trial, "hypothesis_ref") == selected
        and _first_text(trial, "stage") == "selection"
        and _first_text(trial, "verdict") == "promising_for_selection"
        for trial in trial_payloads
    ):
        blockers.append("selected_hypothesis_supported_selection_trial_required")
    dimension = resolved_payloads.get("dimension_manifest", {})
    factor_governance = resolved_payloads.get("factor_family_governance", {})
    factor_dimensions = set(
        _strings(factor_governance.get("factor_identity_dimension_ids"))
    )
    strategy_dimensions = {
        _first_text(_mapping(item), "dimension_id")
        for item in _sequence(dimension.get("dimensions"))
    }
    if factor_dimensions & strategy_dimensions:
        blockers.append("factor_strategy_dimension_namespace_overlap")
    for item in _sequence(dimension.get("dimensions")):
        dimension_item = _mapping(item)
        dimension_id = _first_text(dimension_item, "dimension_id")
        owner = _first_text(dimension_item, "owner_layer")
        if dimension_id.startswith("factor_identity:") or owner == "factor_identity":
            blockers.append("strategy_manifest_claims_factor_identity_dimension")
    if set(_strings(dimension.get("registered_usage_signature_hashes"))) != set(
        registered_signatures
    ):
        blockers.append("dimension_campaign_registered_signatures_mismatch")
    manifest_dimensions = {
        _first_text(_mapping(item), "dimension_id"): _mapping(item)
        for item in _sequence(dimension.get("dimensions"))
    }
    for index, trial in enumerate(trial_payloads):
        unknown_dimensions = set(_strings(trial.get("dimension_ids"))) - set(
            manifest_dimensions
        )
        if unknown_dimensions:
            blockers.append(f"trial_dimension_not_registered:{index}")
    for dimension_id, dimension_payload in manifest_dimensions.items():
        observed_attempt_ids = {
            _first_text(trial, "attempt_id")
            for trial in trial_payloads
            if dimension_id in set(_strings(trial.get("dimension_ids")))
        }
        if int(str(dimension_payload.get("actual_attempt_count", 0))) != len(
            observed_attempt_ids
        ):
            blockers.append(f"dimension_actual_attempt_count_mismatch:{dimension_id}")
    selection_event = resolved_payloads.get("selection_event", {})
    if selected:
        if _first_text(selection_event, "subject_ref") != selected:
            blockers.append("selection_event_subject_mismatch")
        if _first_text(selection_event, "evidence_ref") not in set(
            _strings(receipt.get("trial_refs"))
        ):
            blockers.append("selection_event_trial_evidence_mismatch")
        if _first_text(selection_event, "event_type") != "selected_for_binding":
            blockers.append("selection_event_type_mismatch")
    authority = _resolve_campaign_registry_authority(
        receipt,
        information=resolved_payloads.get("information_evidence", {}),
        trials=trial_payloads,
        dimension_manifest=resolved_payloads.get("dimension_manifest", {}),
        evidence_catalog=evidence_catalog,
        governance_repository=governance_repository,
        expected_candidate_fingerprint=expected_candidate_fingerprint,
    )
    reports["registry_authority"] = authority
    blockers.extend(_prefixed_blockers("registry_authority", authority))
    return {
        "artifact_type": "factor_usage_campaign_dependency_resolution",
        "status": "resolved" if not blockers else "blocked",
        "campaign_id": campaign_id,
        "strategy_id": strategy_id,
        "factor_ref": factor_ref,
        "reports": reports,
        "blockers": sorted(set(blockers)),
    }


def _resolve_dimension_candidate_dependencies(
    dimension_manifest: Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None,
) -> dict[str, object]:
    """Resolve every declared SearchScope candidate rather than trusting labels."""

    blockers: list[str] = []
    reports: list[dict[str, object]] = []
    for dimension_index, raw_dimension in enumerate(
        _sequence(dimension_manifest.get("dimensions"))
    ):
        dimension = _mapping(raw_dimension)
        for candidate_index, raw_candidate in enumerate(
            _sequence(dimension.get("candidate_definitions"))
        ):
            candidate = _mapping(raw_candidate)
            ref = _first_text(candidate, "ref")
            digest = _first_text(candidate, "digest")
            payload, _, _ = _catalog_payload(ref, evidence_catalog)
            artifact_type = _first_text(_mapping(payload), "artifact_type")
            if not artifact_type:
                report = _blocked_governance_resolution(
                    ref, "dimension_candidate_artifact_type_required"
                )
            else:
                report = resolve_governance_artifact(
                    ref,
                    evidence_catalog=evidence_catalog,
                    expected_artifact_type=artifact_type,
                    expected_digest=digest or None,
                )
            reports.append(
                {
                    "dimension_id": _first_text(dimension, "dimension_id"),
                    "candidate_ref": ref,
                    "candidate_digest": digest,
                    **report,
                }
            )
            blockers.extend(
                _prefixed_blockers(
                    f"candidate:{dimension_index}:{candidate_index}", report
                )
            )
    return {
        "artifact_type": "search_scope_dimension_candidate_resolution",
        "status": "resolved" if not blockers else "blocked",
        "reports": reports,
        "blockers": sorted(set(blockers)),
    }


def _resolve_campaign_nested_refs(
    payload: Mapping[str, object],
    *,
    specs: Sequence[tuple[str, set[str]]],
    sequence_field: str,
    evidence_catalog: EvidenceCatalog | None,
    campaign_id: str,
    strategy_id: str,
) -> dict[str, object]:
    """Resolve the nested evidence graph of information/trial artifacts."""

    blockers: list[str] = []
    reports: dict[str, object] = {}
    for field, allowed_types in specs:
        report = _resolve_campaign_nested_ref(
            payload.get(field),
            evidence_catalog=evidence_catalog,
            allowed_types=allowed_types,
            campaign_id=campaign_id,
            strategy_id=strategy_id,
            source_payload=payload,
        )
        reports[field] = report
        blockers.extend(_prefixed_blockers(field, report))
    blockers.extend(
        _window_fold_containment_blockers(
            _mapping(_mapping(reports.get("window_contract_ref")).get("payload")),
            _mapping(_mapping(reports.get("fold_contract_ref")).get("payload")),
            prefix="nested_fold_contract",
        )
    )
    sequence_reports: list[dict[str, object]] = []
    refs = _strings(payload.get(sequence_field))
    if not refs:
        blockers.append(f"{sequence_field}_required")
    for index, ref in enumerate(refs):
        report = _resolve_campaign_nested_ref(
            ref,
            evidence_catalog=evidence_catalog,
            allowed_types=None,
            campaign_id=campaign_id,
            strategy_id=strategy_id,
            source_payload=payload,
        )
        sequence_reports.append(report)
        blockers.extend(_prefixed_blockers(f"{sequence_field}:{index}", report))
    reports[sequence_field] = sequence_reports
    return {
        "artifact_type": "factor_usage_campaign_nested_dependency_resolution",
        "status": "resolved" if not blockers else "blocked",
        "reports": reports,
        "blockers": sorted(set(blockers)),
    }


def _resolve_campaign_nested_ref(
    ref: object,
    *,
    evidence_catalog: EvidenceCatalog | None,
    allowed_types: set[str] | None,
    campaign_id: str,
    strategy_id: str,
    source_payload: Mapping[str, object],
) -> dict[str, object]:
    ref_text = str(ref or "").strip()
    if not ref_text:
        return _blocked_governance_resolution(ref_text, "nested_evidence_ref_required")
    payload, source_blocker, _ = _catalog_payload(ref_text, evidence_catalog)
    artifact_type = _first_text(_mapping(payload), "artifact_type")
    if not artifact_type:
        return _blocked_governance_resolution(
            ref_text, source_blocker or "nested_evidence_artifact_type_required"
        )
    expected_type = artifact_type
    type_blocker = ""
    if allowed_types is not None and artifact_type not in allowed_types:
        expected_type = sorted(allowed_types)[0]
        type_blocker = "nested_evidence_artifact_type_invalid"
    report = resolve_governance_artifact(
        ref_text,
        evidence_catalog=evidence_catalog,
        expected_artifact_type=expected_type,
    )
    blockers = list(_strings(report.get("blockers")))
    if source_blocker:
        blockers.append(source_blocker)
    if type_blocker:
        blockers.append(type_blocker)
    if allowed_types is not None:
        blockers.extend(
            _nested_campaign_contract_blockers(
                _mapping(report.get("payload")),
                artifact_type=artifact_type,
                campaign_id=campaign_id,
                strategy_id=strategy_id,
                source_payload=source_payload,
            )
        )
    return {
        **report,
        "status": "resolved" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
    }


def _nested_campaign_contract_blockers(
    payload: Mapping[str, object],
    *,
    artifact_type: str,
    campaign_id: str,
    strategy_id: str,
    source_payload: Mapping[str, object],
) -> list[str]:
    """Reject checksum-valid but semantically empty campaign dependencies."""

    blockers: list[str] = []
    for field in ("schema_id", "canonicalization_version"):
        if not _first_text(payload, field):
            blockers.append(f"nested_{artifact_type}_{field}_required")
    if _first_text(payload, "canonicalization_version") != CANONICALIZATION_VERSION:
        blockers.append(f"nested_{artifact_type}_canonicalization_invalid")
    allowed_schema_ids = _NESTED_SCHEMA_IDS.get(artifact_type, frozenset())
    if _first_text(payload, "schema_id") not in allowed_schema_ids:
        blockers.append(f"nested_{artifact_type}_schema_id_invalid")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append(f"nested_{artifact_type}_field_labels_zh_required")
    if not _is_sha256_digest(payload.get("checksum")):
        blockers.append(f"nested_{artifact_type}_checksum_invalid")

    if artifact_type == "dataset_manifest":
        for field in ("dataset_id", "version", "source_vintage_ref", "available_at"):
            if not _first_text(payload, field):
                blockers.append(f"dataset_manifest_{field}_required")
        if _parse_timestamp(_first_text(payload, "available_at")) is None:
            blockers.append("dataset_manifest_available_at_invalid")
    elif artifact_type in {
        "temporal_policy",
        "temporal_policy_manifest",
        "strategy_temporal_policy",
    }:
        for field in (
            "observation_time_field",
            "available_time_field",
            "decision_time_field",
            "execution_time_field",
        ):
            if not _first_text(payload, field):
                blockers.append(f"temporal_policy_{field}_required")
        expected_order = (
            "observation_time",
            "available_time",
            "decision_time",
            "execution_time",
        )
        if _strings(payload.get("ordering")) != expected_order:
            blockers.append("temporal_policy_ordering_invalid")
    elif artifact_type in {
        "window_contract",
        "strategy_usage_window_contract",
        "strategy_integration_window_contract",
        "fold_contract",
        "strategy_usage_fold_contract",
        "strategy_integration_fold_contract",
    }:
        for field, expected in (
            ("campaign_id", campaign_id),
            ("strategy_id", strategy_id),
            (
                "dataset_manifest_ref",
                _first_text(source_payload, "dataset_manifest_ref"),
            ),
        ):
            actual = _first_text(payload, field)
            if not actual:
                blockers.append(f"nested_{artifact_type}_{field}_required")
            elif actual != expected:
                blockers.append(f"nested_{artifact_type}_{field}_mismatch")
        start = _parse_timestamp(_first_text(payload, "start_at"))
        end = _parse_timestamp(_first_text(payload, "end_at"))
        if start is None or end is None:
            blockers.append(f"nested_{artifact_type}_bounds_invalid")
        elif start >= end:
            blockers.append(f"nested_{artifact_type}_bounds_not_ordered")
        if "fold_contract" in artifact_type:
            expected_window = _first_text(source_payload, "window_contract_ref")
            if _first_text(payload, "window_contract_ref") != expected_window:
                blockers.append("nested_fold_contract_window_ref_mismatch")
    return blockers


def _window_fold_containment_blockers(
    window: Mapping[str, object],
    fold: Mapping[str, object],
    *,
    prefix: str,
) -> list[str]:
    if not window or not fold:
        return []
    window_start = _parse_timestamp(_first_text(window, "start_at"))
    window_end = _parse_timestamp(_first_text(window, "end_at"))
    fold_start = _parse_timestamp(_first_text(fold, "start_at"))
    fold_end = _parse_timestamp(_first_text(fold, "end_at"))
    if (
        window_start is None
        or window_end is None
        or fold_start is None
        or fold_end is None
    ):
        return []
    if fold_start < window_start or fold_end > window_end:
        return [f"{prefix}_outside_window"]
    return []


def _resolve_campaign_registry_authority(
    receipt: Mapping[str, object],
    *,
    information: Mapping[str, object],
    trials: Sequence[Mapping[str, object]],
    dimension_manifest: Mapping[str, object],
    evidence_catalog: EvidenceCatalog | None,
    governance_repository: TemporalGovernanceRepository | None,
    expected_candidate_fingerprint: str | None,
) -> dict[str, object]:
    """Match selected-campaign source identities to the SQLite authority."""

    if _first_text(receipt, "campaign_outcome") != "selected":
        return {
            "artifact_type": "factor_usage_campaign_registry_authority",
            "status": "not_required",
            "blockers": [],
        }
    if governance_repository is None:
        return {
            "artifact_type": "factor_usage_campaign_registry_authority",
            "status": "blocked",
            "blockers": ["authoritative_governance_repository_required"],
        }

    campaign_id = _first_text(receipt, "campaign_id")
    runs = governance_repository.get_search_scope_runs(campaign_id)
    events = governance_repository.get_data_usage_events()
    blockers: list[str] = []
    authority_reports: list[dict[str, object]] = []
    combinations = _sequence(dimension_manifest.get("explicit_sparse_combinations"))
    unique_attempt_ids = {_first_text(trial, "attempt_id") for trial in trials if trial}
    coverage = _mapping(receipt.get("coverage_claim"))
    parameter_count = _non_negative_integer(coverage.get("parameter_config_count"))
    protocol_count = _non_negative_integer(coverage.get("protocol_count"))
    if parameter_count is None:
        blockers.append("coverage_parameter_config_count_required")
    if protocol_count is None:
        blockers.append("coverage_protocol_count_required")
    sources = (("information", information),) + tuple(
        (f"trial:{index}", trial) for index, trial in enumerate(trials)
    )
    for prefix, source in sources:
        search_scope_id = _first_text(source, "search_scope_registry_id")
        data_usage_id = _first_text(source, "data_usage_registry_id")
        dataset_ref = _first_text(source, "dataset_manifest_ref")
        window_ref = _first_text(source, "window_contract_ref")
        fold_ref = _first_text(source, "fold_contract_ref")
        temporal_ref = _first_text(source, "temporal_policy_ref")
        dataset_payload, _, _ = _catalog_payload(dataset_ref, evidence_catalog)
        window_payload, _, _ = _catalog_payload(window_ref, evidence_catalog)
        fold_payload, _, _ = _catalog_payload(fold_ref, evidence_catalog)
        temporal_payload, _, _ = _catalog_payload(temporal_ref, evidence_catalog)
        matching_runs = tuple(
            run for run in runs if _first_text(run, "run_id") == search_scope_id
        )
        matching_events = tuple(
            event
            for event in events
            if _first_text(event, "access_event_id") == data_usage_id
        )
        local_blockers: list[str] = []
        if len(matching_runs) != 1:
            local_blockers.append("authoritative_search_scope_registration_missing")
        else:
            run = matching_runs[0]
            if _first_text(run, "dataset_ref") != dataset_ref:
                local_blockers.append("authoritative_search_scope_dataset_mismatch")
            if window_ref and _first_text(run, "window_ref") != window_ref:
                local_blockers.append("authoritative_search_scope_window_mismatch")
            if _first_text(run, "status") != "registered":
                local_blockers.append("authoritative_search_scope_status_invalid")
            if _first_text(run, "search_space_hash") != _first_text(
                dimension_manifest, "search_space_hash"
            ):
                local_blockers.append("authoritative_search_scope_hash_mismatch")
            for field, expected_count in (
                ("candidate_count", len(combinations)),
                ("attempted_evaluation_count", len(unique_attempt_ids)),
                ("parameter_config_count", parameter_count),
                ("protocol_count", protocol_count),
            ):
                if (
                    expected_count is not None
                    and _non_negative_integer(run.get(field)) != expected_count
                ):
                    local_blockers.append(
                        f"authoritative_search_scope_{field}_mismatch"
                    )
            local_blockers.extend(
                _authority_metadata_blockers(
                    _mapping(run.get("metadata")),
                    strategy_id=_first_text(receipt, "strategy_id"),
                    campaign_id=campaign_id,
                    dataset=_mapping(dataset_payload),
                    temporal_policy_ref=temporal_ref,
                    temporal_policy=_mapping(temporal_payload),
                    window_contract_ref=window_ref,
                    fold_contract_ref=fold_ref,
                    window=_mapping(window_payload),
                    fold=_mapping(fold_payload),
                )
            )
        if len(matching_events) != 1:
            local_blockers.append("authoritative_data_usage_registration_missing")
        else:
            event = matching_events[0]
            if _first_text(event, "artifact_type") != "data_usage_receipt":
                local_blockers.append("authoritative_data_usage_type_invalid")
            if _first_text(event, "dataset_ref") != dataset_ref:
                local_blockers.append("authoritative_data_usage_dataset_mismatch")
            if window_ref and _first_text(event, "window_ref") != window_ref:
                local_blockers.append("authoritative_data_usage_window_mismatch")
            stage = _first_text(source, "stage")
            if stage and _first_text(event, "usage_stage") != stage:
                local_blockers.append("authoritative_data_usage_stage_mismatch")
            if (
                expected_candidate_fingerprint
                and _first_text(event, "candidate_fingerprint")
                != expected_candidate_fingerprint
            ):
                local_blockers.append(
                    "authoritative_data_usage_candidate_fingerprint_mismatch"
                )
            local_blockers.extend(
                _authority_metadata_blockers(
                    _mapping(event.get("metadata")),
                    strategy_id=_first_text(receipt, "strategy_id"),
                    campaign_id=campaign_id,
                    dataset=_mapping(dataset_payload),
                    temporal_policy_ref=temporal_ref,
                    temporal_policy=_mapping(temporal_payload),
                    window_contract_ref=window_ref,
                    fold_contract_ref=fold_ref,
                    window=_mapping(window_payload),
                    fold=_mapping(fold_payload),
                )
            )
        blockers.extend(f"{prefix}:{item}" for item in local_blockers)
        authority_reports.append(
            {
                "source": prefix,
                "search_scope_registry_id": search_scope_id,
                "data_usage_registry_id": data_usage_id,
                "search_scope_records": list(matching_runs),
                "data_usage_records": list(matching_events),
                "status": "resolved" if not local_blockers else "blocked",
                "blockers": local_blockers,
            }
        )
    return {
        "artifact_type": "factor_usage_campaign_registry_authority",
        "status": "resolved" if not blockers else "blocked",
        "reports": authority_reports,
        "blockers": sorted(set(blockers)),
    }


def _authority_metadata_blockers(
    metadata: Mapping[str, object],
    *,
    strategy_id: str,
    campaign_id: str,
    dataset: Mapping[str, object],
    temporal_policy_ref: str,
    temporal_policy: Mapping[str, object],
    window_contract_ref: str,
    fold_contract_ref: str,
    window: Mapping[str, object],
    fold: Mapping[str, object],
) -> list[str]:
    expected = {
        "strategy_id": strategy_id,
        "campaign_id": campaign_id,
        "dataset_id": _first_text(dataset, "dataset_id"),
        "dataset_version": _first_text(dataset, "version"),
        "source_vintage_ref": _first_text(dataset, "source_vintage_ref"),
        "dataset_available_at": _first_text(dataset, "available_at"),
        "dataset_digest": _first_text(dataset, "checksum"),
        "temporal_policy_ref": temporal_policy_ref,
        "temporal_policy_digest": _first_text(temporal_policy, "checksum"),
        "window_contract_ref": window_contract_ref,
        "window_contract_digest": _first_text(window, "checksum"),
        "window_start_at": _first_text(window, "start_at"),
        "window_end_at": _first_text(window, "end_at"),
        "fold_contract_ref": fold_contract_ref,
        "fold_contract_digest": _first_text(fold, "checksum"),
        "fold_start_at": _first_text(fold, "start_at"),
        "fold_end_at": _first_text(fold, "end_at"),
    }
    blockers: list[str] = []
    for field, expected_value in expected.items():
        if not expected_value:
            continue
        actual = _first_text(metadata, field)
        if not actual:
            blockers.append(f"authoritative_metadata_{field}_required")
        elif actual != expected_value:
            blockers.append(f"authoritative_metadata_{field}_mismatch")
    return blockers


def _extend_validation_blockers(
    blockers: list[str],
    prefix: str,
    report: Mapping[str, object],
) -> None:
    if report.get("status") not in {"valid", "eligible"}:
        blockers.extend(_prefixed_blockers(f"{prefix}_contract", report))


def _campaign_identity_blockers(
    blockers: list[str],
    *,
    payload: Mapping[str, object],
    prefix: str,
    campaign_id: str,
    strategy_id: str,
    factor_ref: str,
) -> None:
    for field, expected in (
        ("campaign_id", campaign_id),
        ("strategy_id", strategy_id),
        ("factor_ref", factor_ref),
    ):
        actual = _first_text(payload, field)
        if not expected or not actual:
            blockers.append(f"{prefix}:{field}_required")
        elif actual != expected:
            blockers.append(f"{prefix}:{field}_mismatch")


def resolve_strategy_integration_claim(
    *,
    claim_ref: str,
    evidence_catalog: EvidenceCatalog | None,
    required_stages: Sequence[str] = ("validation", "prospective", "lockbox"),
    admitted_factor_loader: Callable[[str], Mapping[str, object]] | None = None,
    governance_repository: TemporalGovernanceRepository | None = None,
    require_authoritative_claim: bool = False,
) -> dict[str, object]:
    """Resolve the complete frozen strategy-integration claim DAG.

    This is the promotion-capable resolver.  It deliberately does not trust a
    claim's own ``execution_eligible`` flag and never creates factor assets.
    """

    blockers: list[str] = []
    reports: dict[str, object] = {}
    claim_report = resolve_governance_artifact(
        claim_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_integration_claim",
    )
    reports["claim"] = claim_report
    blockers.extend(_prefixed_blockers("claim", claim_report))
    claim = _mapping(claim_report.get("payload"))
    _extend_validation_blockers(
        blockers,
        "claim",
        validate_strategy_integration_claim(claim),
    )
    strategy_id = _first_text(claim, "strategy_id")
    strategy_family = _first_text(claim, "strategy_family_id", "strategy_family")
    fingerprint = _first_text(claim, "candidate_fingerprint")
    binding_ref = _first_text(claim, "frozen_binding_ref", "usage_binding_ref")
    binding_digest = _first_text(claim, "binding_digest")
    if not strategy_id:
        blockers.append("claim_strategy_id_required")
    if not fingerprint:
        blockers.append("claim_candidate_fingerprint_required")
    if not binding_ref:
        blockers.append("claim_frozen_binding_ref_required")

    binding_report = resolve_governance_artifact(
        binding_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="frozen_strategy_factor_binding",
        expected_digest=binding_digest or None,
        expected_candidate_fingerprint=fingerprint or None,
    )
    reports["binding"] = binding_report
    blockers.extend(_prefixed_blockers("binding", binding_report))
    binding = _mapping(binding_report.get("payload"))
    _extend_validation_blockers(
        blockers,
        "binding",
        validate_frozen_strategy_factor_binding(binding),
    )
    _require_same(blockers, "strategy_id", strategy_id, binding)
    _require_same(blockers, "candidate_fingerprint", fingerprint, binding)

    if governance_repository is not None:
        binding_id = _first_text(binding, "binding_id", "usage_binding_id")
        authoritative_binding = (
            governance_repository.get_frozen_strategy_factor_binding(
                strategy_id, binding_id
            )
            if strategy_id and binding_id
            else None
        )
        if authoritative_binding is None:
            blockers.append("authoritative_frozen_binding_not_registered")
        elif dict(authoritative_binding) != dict(binding):
            blockers.append("authoritative_frozen_binding_payload_mismatch")
        claim_id = _first_text(claim, "claim_id")
        authoritative_claim = (
            governance_repository.get_strategy_integration_claim(strategy_id, claim_id)
            if strategy_id and claim_id
            else None
        )
        if authoritative_claim is None:
            if require_authoritative_claim:
                blockers.append("authoritative_integration_claim_not_registered")
        elif dict(authoritative_claim) != dict(claim):
            blockers.append("authoritative_integration_claim_payload_mismatch")

    child_specs = (
        (
            "campaign_receipt",
            "usage_campaign_receipt_ref",
            "usage_campaign_receipt_digest",
            "factor_usage_campaign_receipt",
        ),
        (
            "freeze_manifest",
            "selection_freeze_manifest_ref",
            "selection_freeze_manifest_digest",
            "selection_freeze_manifest",
        ),
        (
            "action_space",
            "action_space_ref",
            "action_space_digest",
            "strategy_factor_action_space",
        ),
        (
            "adapter",
            "execution_adapter_ref",
            "adapter_digest",
            "strategy_factor_execution_adapter",
        ),
        (
            "baseline",
            "baseline_artifact_ref",
            "baseline_digest",
            "strategy_baseline",
        ),
        (
            "admitted_factor",
            "admitted_factor_asset_ref",
            "admitted_factor_digest",
            "admitted_factor",
        ),
    )
    children: dict[str, Mapping[str, object]] = {}
    for name, ref_field, digest_field, artifact_type in child_specs:
        ref = _first_text(binding, ref_field)
        expected_digest = _first_text(binding, digest_field)
        if not ref:
            blockers.append(f"binding_{ref_field}_required")
            continue
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type=artifact_type,
            expected_digest=expected_digest or None,
            expected_candidate_fingerprint=(
                fingerprint if name in {"freeze_manifest", "admitted_factor"} else None
            ),
        )
        reports[name] = report
        blockers.extend(_prefixed_blockers(name, report))
        children[name] = _mapping(report.get("payload"))

    campaign = children.get("campaign_receipt", {})
    _require_same(blockers, "strategy_id", strategy_id, campaign, "campaign")
    _require_same(
        blockers,
        "factor_ref",
        _first_text(binding, "factor_ref"),
        campaign,
        "campaign",
    )
    _require_same_ref(
        blockers,
        "campaign_action_space_ref",
        _first_text(binding, "action_space_ref"),
        _first_text(campaign, "action_space_ref"),
    )
    campaign_dependencies = resolve_factor_usage_campaign_dependencies(
        campaign,
        evidence_catalog=evidence_catalog,
        governance_repository=governance_repository,
        expected_candidate_fingerprint=fingerprint or None,
    )
    reports["campaign_dependencies"] = campaign_dependencies
    blockers.extend(_prefixed_blockers("campaign_dependencies", campaign_dependencies))
    blockers.extend(_strings(campaign_dependencies.get("blockers")))
    information_payload, _, _ = _catalog_payload(
        _first_text(campaign, "factor_information_evidence_ref"), evidence_catalog
    )
    temporal_policy_ref = _first_text(
        _mapping(information_payload), "temporal_policy_ref"
    )
    temporal_policy_payload, _, _ = _catalog_payload(
        temporal_policy_ref, evidence_catalog
    )
    freeze = children.get("freeze_manifest", {})
    if _first_text(freeze, "schema_id") == "selection_freeze_manifest@2.0":
        _extend_validation_blockers(
            blockers,
            "freeze",
            validate_selection_freeze_manifest_v2(freeze),
        )
    else:
        blockers.append("selection_freeze_manifest_v2_required")
    fingerprint_report = resolve_governance_artifact(
        freeze.get("candidate_fingerprint_ref"),
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_usage_candidate_fingerprint",
        expected_candidate_fingerprint=fingerprint or None,
    )
    reports["candidate_fingerprint"] = fingerprint_report
    blockers.extend(_prefixed_blockers("candidate_fingerprint", fingerprint_report))
    fingerprint_payload = _mapping(fingerprint_report.get("payload"))
    _extend_validation_blockers(
        blockers,
        "candidate_fingerprint",
        validate_strategy_usage_candidate_fingerprint(
            fingerprint_payload,
            evidence_catalog=evidence_catalog,
        ),
    )
    factor_asset_report = resolve_governance_artifact(
        fingerprint_payload.get("factor_asset_ref"),
        evidence_catalog=evidence_catalog,
        expected_artifact_type="factor_asset",
        expected_digest=_first_text(fingerprint_payload, "factor_asset_digest") or None,
    )
    reports["factor_asset"] = factor_asset_report
    blockers.extend(_prefixed_blockers("factor_asset", factor_asset_report))
    factor_asset = _mapping(factor_asset_report.get("payload"))
    if _first_text(factor_asset, "factor_ref") != _first_text(binding, "factor_ref"):
        blockers.append("factor_asset_binding_factor_ref_mismatch")
    for field, expected in (
        ("strategy_family_id", strategy_family),
        ("strategy_id", strategy_id),
        ("baseline_artifact_ref", _first_text(binding, "baseline_artifact_ref")),
        ("baseline_digest", _first_text(binding, "baseline_digest")),
        ("usage_signature_hash", _first_text(binding, "usage_signature_hash")),
        ("execution_adapter_ref", _first_text(binding, "execution_adapter_ref")),
        ("adapter_digest", _first_text(binding, "adapter_digest")),
    ):
        if _first_text(fingerprint_payload, field) != expected:
            blockers.append(f"candidate_fingerprint_{field}_mismatch")
    code_digests = {
        _first_text(_mapping(item), "digest")
        for item in _sequence(fingerprint_payload.get("code_definition_digests"))
    }
    if _first_text(binding, "code_digest") not in code_digests:
        blockers.append("candidate_fingerprint_code_digest_mismatch")
    data_refs = {
        _first_text(_mapping(item), "ref")
        for item in _sequence(fingerprint_payload.get("data_definition_digests"))
    }
    if not set(_strings(binding.get("dataset_refs"))).issubset(data_refs):
        blockers.append("candidate_fingerprint_dataset_refs_mismatch")
    candidate_definition_report = resolve_governance_artifact(
        freeze.get("candidate_definition_ref"),
        evidence_catalog=evidence_catalog,
        expected_artifact_type="factor_usage_hypothesis",
        expected_digest=_first_text(freeze, "candidate_definition_digest") or None,
    )
    reports["candidate_definition"] = candidate_definition_report
    blockers.extend(
        _prefixed_blockers("candidate_definition", candidate_definition_report)
    )
    candidate_definition = _mapping(candidate_definition_report.get("payload"))
    if _first_text(fingerprint_payload, "factor_asset_ref") != _first_text(
        candidate_definition, "factor_asset_ref"
    ):
        blockers.append("candidate_fingerprint_factor_asset_ref_mismatch")
    if _first_text(binding, "factor_asset_ref") != _first_text(
        fingerprint_payload, "factor_asset_ref"
    ):
        blockers.append("binding_factor_asset_ref_mismatch")
    if _first_text(campaign, "selected_hypothesis_ref") != _first_text(
        freeze, "candidate_definition_ref"
    ):
        blockers.append("freeze_selected_hypothesis_ref_mismatch")
    if _first_text(binding, "usage_hypothesis_ref") != _first_text(
        freeze, "candidate_definition_ref"
    ):
        blockers.append("binding_usage_hypothesis_ref_mismatch")
    if _first_text(binding, "hypothesis_definition_digest") != _first_text(
        freeze, "candidate_definition_digest"
    ):
        blockers.append("binding_hypothesis_definition_digest_mismatch")
    if _first_text(binding, "selection_event_ref") != _first_text(
        campaign, "selection_event_ref"
    ):
        blockers.append("binding_selection_event_ref_mismatch")
    if _first_text(candidate_definition, "usage_signature_hash") != _first_text(
        binding, "usage_signature_hash"
    ):
        blockers.append("freeze_usage_signature_mismatch")
    if _first_text(candidate_definition, "action_id") != _first_text(
        binding, "action_id"
    ):
        blockers.append("freeze_action_id_mismatch")
    _require_same(blockers, "strategy_id", strategy_id, freeze, "freeze")
    _require_same(blockers, "candidate_fingerprint", fingerprint, freeze, "freeze")
    _require_same_ref(
        blockers,
        "freeze_action_space_ref",
        _first_text(binding, "action_space_ref"),
        _first_text(freeze, "action_space_ref"),
    )
    _require_same(
        blockers,
        "code_digest",
        _first_text(binding, "code_digest"),
        freeze,
        "freeze",
    )
    if set(_strings(binding.get("dataset_refs"))) != set(
        _strings(freeze.get("dataset_refs"))
    ):
        blockers.append("freeze_dataset_refs_mismatch")
    admitted_factor = children.get("admitted_factor", {})
    if _first_text(admitted_factor, "factor_ref") != _first_text(binding, "factor_ref"):
        blockers.append("admitted_factor_binding_factor_ref_mismatch")
    for field in (
        "admitted_factor_id",
        "effective_factor_id",
        "candidate_factor_id",
        "validation_claim_id",
        "evaluation_run_id",
        "dataset_version",
    ):
        if not _first_text(admitted_factor, field):
            blockers.append(f"admitted_factor_{field}_required")
    if _first_text(admitted_factor, "admission_status") != "admitted":
        blockers.append("admitted_factor_not_active_admitted")
    admitted_factor_id = _first_text(admitted_factor, "admitted_factor_id")
    if admitted_factor_loader is None:
        try:
            from factor_lab.candidate_assets.services.candidate_asset_service import (
                candidate_asset_service,
            )

            admitted_factor_loader = candidate_asset_service.get_admitted_factor
        except ImportError:
            admitted_factor_loader = None
    if admitted_factor_loader is None:
        blockers.append("authoritative_admitted_factor_loader_required")
    else:
        try:
            authoritative_admitted = admitted_factor_loader(admitted_factor_id)
        except Exception as exc:
            blockers.append(
                f"authoritative_admitted_factor_not_resolved:{type(exc).__name__}"
            )
        else:
            for field in (
                "admitted_factor_id",
                "effective_factor_id",
                "candidate_factor_id",
                "validation_claim_id",
                "evaluation_run_id",
                "dataset_version",
                "admission_status",
            ):
                if str(authoritative_admitted.get(field, "")) != _first_text(
                    admitted_factor, field
                ):
                    blockers.append(f"authoritative_admitted_factor_{field}_mismatch")

    for field in (
        "baseline_artifact_ref",
        "baseline_digest",
        "admitted_factor_asset_ref",
        "admitted_factor_digest",
        "usage_signature_hash",
    ):
        _require_same(blockers, field, _first_text(binding, field), claim, "claim")

    review_ref = _first_text(
        claim, "strategy_integration_review_package_ref", "review_package_ref"
    )
    review_digest = _first_text(claim, "review_package_digest")
    review_report = resolve_governance_artifact(
        review_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_integration_review_package",
        expected_digest=review_digest or None,
        expected_candidate_fingerprint=fingerprint or None,
    )
    reports["review_package"] = review_report
    blockers.extend(_prefixed_blockers("review_package", review_report))
    review = _mapping(review_report.get("payload"))
    _extend_validation_blockers(
        blockers,
        "review",
        validate_strategy_integration_review_package(review),
    )
    _require_same_ref(
        blockers,
        "review_binding_ref",
        binding_ref,
        _first_text(review, "frozen_binding_ref", "binding_ref"),
    )
    _require_same(blockers, "binding_digest", binding_digest, review, "review")
    _require_same(blockers, "strategy_id", strategy_id, review, "review")
    _require_same(blockers, "candidate_fingerprint", fingerprint, review, "review")
    for field in (
        "admitted_factor_asset_ref",
        "admitted_factor_digest",
        "baseline_artifact_ref",
        "baseline_digest",
    ):
        _require_same(blockers, field, _first_text(binding, field), review, "review")
    if _first_text(review, "readiness") != "ready_for_integration_review":
        blockers.append("strategy_integration_review_not_eligible")
    if _first_text(review, "recommendation") == "not_eligible":
        blockers.append("strategy_integration_review_not_eligible")
    resolver_report_ref = _first_text(review, "resolver_report_ref")
    resolver_report = resolve_governance_artifact(
        resolver_report_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_integration_resolver_report",
        expected_digest=_first_text(review, "resolver_report_digest") or None,
        expected_candidate_fingerprint=fingerprint or None,
    )
    reports["review_resolver_report"] = resolver_report
    blockers.extend(_prefixed_blockers("review_resolver_report", resolver_report))
    resolver_payload = _mapping(resolver_report.get("payload"))
    if _first_text(resolver_payload, "status") != "resolved":
        blockers.append("review_resolver_report_status_not_resolved")
    if resolver_payload.get("integration_eligible") is not True:
        blockers.append("review_resolver_report_not_integration_eligible")
    if _strings(resolver_payload.get("blockers")):
        blockers.append("review_resolver_report_has_blockers")
    for field, expected in (
        ("strategy_family_id", strategy_family),
        ("strategy_id", strategy_id),
        ("frozen_binding_ref", binding_ref),
        ("binding_digest", binding_digest),
        ("candidate_fingerprint", fingerprint),
        ("action_id", _first_text(binding, "action_id")),
    ):
        if _first_text(resolver_payload, field) != expected:
            blockers.append(f"review_resolver_report_{field}_mismatch")
    claim_evidence_refs = {
        _first_text(_mapping(entry), "ref", "evidence_ref")
        for entry in _sequence(claim.get("integration_evidence_refs"))
    }
    review_evidence_refs = {
        _first_text(_mapping(entry), "ref", "evidence_ref")
        for entry in _sequence(review.get("integration_evidence_refs"))
    }
    if claim_evidence_refs != review_evidence_refs:
        blockers.append("claim_review_integration_evidence_refs_mismatch")
    claim_evidence_entries = {
        _first_text(_mapping(entry), "ref", "evidence_ref"): _mapping(entry)
        for entry in _sequence(claim.get("integration_evidence_refs"))
    }
    review_evidence_entries = {
        _first_text(_mapping(entry), "ref", "evidence_ref"): _mapping(entry)
        for entry in _sequence(review.get("integration_evidence_refs"))
    }
    for ref in claim_evidence_refs & review_evidence_refs:
        for field in ("stage", "artifact_type", "schema_id", "evidence_digest"):
            if _first_text(claim_evidence_entries[ref], field) != _first_text(
                review_evidence_entries[ref], field
            ):
                blockers.append(
                    f"claim_review_integration_evidence_{field}_mismatch:{ref}"
                )

    evidence_entries = claim.get("integration_evidence_refs") or review.get(
        "integration_evidence_refs"
    )
    evidence_entry_refs = {
        _first_text(_mapping(entry), "ref", "evidence_ref")
        for entry in _sequence(evidence_entries)
    }
    downstream_refs = {
        claim_ref,
        review_ref,
        _first_text(claim, "review_event_ref"),
        _first_text(claim, "decision_event_ref"),
        *evidence_entry_refs,
    }
    for immutable_entry in _sequence(binding.get("immutable_artifact_refs")):
        if _first_text(_mapping(immutable_entry), "ref") in downstream_refs:
            blockers.append("integration_artifact_cycle_detected")
    stages: set[str] = set()
    promotion_data_identities: list[str] = []
    evidence_reports: list[dict[str, object]] = []
    for index, entry in enumerate(_sequence(evidence_entries)):
        entry_map = _mapping(entry)
        ref = str(entry_map.get("ref") or entry_map.get("evidence_ref") or entry)
        expected_digest = _first_text(entry_map, "evidence_digest", "digest")
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type="strategy_integration_evidence",
            expected_digest=expected_digest or None,
            expected_candidate_fingerprint=fingerprint or None,
        )
        evidence_reports.append(report)
        blockers.extend(_prefixed_blockers(f"integration_evidence:{index}", report))
        evidence = _mapping(report.get("payload"))
        evidence_validation = validate_strategy_integration_evidence(evidence)
        _extend_validation_blockers(
            blockers,
            f"integration_evidence:{index}",
            evidence_validation,
        )
        blockers.extend(_strings(evidence_validation.get("blockers")))
        _require_same_ref(
            blockers,
            f"integration_evidence_binding_ref:{index}",
            binding_ref,
            _first_text(evidence, "frozen_binding_ref", "binding_ref"),
        )
        _require_same(
            blockers,
            "binding_digest",
            binding_digest,
            evidence,
            f"integration_evidence:{index}",
        )
        _require_same(
            blockers,
            "strategy_id",
            strategy_id,
            evidence,
            f"integration_evidence:{index}",
        )
        for field in ("baseline_artifact_ref", "baseline_digest"):
            _require_same(
                blockers,
                field,
                _first_text(binding, field),
                evidence,
                f"integration_evidence:{index}",
            )
        _require_same(
            blockers,
            "candidate_fingerprint",
            fingerprint,
            evidence,
            f"integration_evidence:{index}",
        )
        for field in ("action_id", "usage_signature_hash"):
            _require_same(
                blockers,
                field,
                _first_text(binding, field),
                evidence,
                f"integration_evidence:{index}",
            )
        stage = _first_text(evidence, "integration_stage", "stage")
        if _first_text(entry_map, "stage") != stage:
            blockers.append(f"integration_evidence_entry_stage_mismatch:{index}")
        if _first_text(entry_map, "artifact_type") != _first_text(
            evidence, "artifact_type"
        ):
            blockers.append(
                f"integration_evidence_entry_artifact_type_mismatch:{index}"
            )
        if _first_text(entry_map, "schema_id") != _first_text(evidence, "schema_id"):
            blockers.append(f"integration_evidence_entry_schema_id_mismatch:{index}")
        if stage:
            if stage in stages:
                blockers.append(f"duplicate_integration_stage:{stage}")
            stages.add(stage)
        if _first_text(evidence, "evidence_verdict", "outcome") != "supported":
            blockers.append(f"integration_evidence_not_supported:{index}")
        internal_refs = {
            _first_text(evidence, field)
            for field in (
                "dataset_manifest_ref",
                "window_contract_ref",
                "fold_contract_ref",
                "data_usage_receipt_ref",
                "lockbox_receipt_ref",
                "execution_artifact_ref",
                "claim_schema_ref",
                "no_harm_schema_ref",
            )
        } | set(_strings(evidence.get("evidence_refs")))
        if internal_refs & downstream_refs:
            blockers.append("integration_artifact_cycle_detected")
        dependency_resolution = _resolve_integration_evidence_dependencies(
            evidence,
            evidence_catalog=evidence_catalog,
            candidate_fingerprint=fingerprint,
            strategy_family=strategy_family,
            campaign_id=_first_text(campaign, "campaign_id"),
            temporal_policy_ref=temporal_policy_ref,
            temporal_policy=_mapping(temporal_policy_payload),
            governance_repository=governance_repository,
        )
        reports[f"integration_evidence_dependencies:{index}"] = dependency_resolution
        blockers.extend(
            _prefixed_blockers(
                f"integration_evidence_dependencies:{index}",
                dependency_resolution,
            )
        )
        authoritative_identity = _first_text(
            _mapping(dependency_resolution), "authoritative_data_identity"
        )
        promotion_data_identities.append(
            authoritative_identity
            or json.dumps(
                {
                    "data_usage_receipt_ref": _first_text(
                        evidence, "data_usage_receipt_ref"
                    ),
                    "window_contract_ref": _first_text(evidence, "window_contract_ref"),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    reports["integration_evidence"] = evidence_reports
    if len(set(promotion_data_identities)) != len(promotion_data_identities):
        blockers.append("previously_consumed_rows_used_for_promotion_evidence")
    if not evidence_reports:
        blockers.append("integration_evidence_refs_required")
    required = set(required_stages) | set(_STRICT_INTEGRATION_STAGES)
    if not required.issubset(stages):
        blockers.extend(
            f"required_integration_stage_missing:{stage}"
            for stage in sorted(required - stages)
        )
    completeness = _mapping(claim.get("stage_completeness_report"))
    if set(_strings(completeness.get("required_stages"))) != required:
        blockers.append("claim_stage_completeness_required_stages_mismatch")
    if set(_strings(completeness.get("resolved_stages"))) != stages:
        blockers.append("claim_stage_completeness_resolved_stages_mismatch")
    if completeness.get("complete") != required.issubset(stages):
        blockers.append("claim_stage_completeness_flag_mismatch")

    control_payloads: dict[str, Mapping[str, object]] = {}
    review_event_ref = _first_text(claim, "review_event_ref")
    review_event_report = resolve_governance_artifact(
        review_event_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_integration_review_event",
        expected_digest=_first_text(claim, "review_event_digest"),
    )
    reports["review_event"] = review_event_report
    blockers.extend(_prefixed_blockers("review_event", review_event_report))
    review_event = _mapping(review_event_report.get("payload"))
    control_payloads["review_event"] = review_event
    blockers.extend(
        _prefixed_blockers(
            "review_event_contract",
            validate_strategy_integration_review_event(review_event),
        )
    )

    decision_event_ref = _first_text(claim, "decision_event_ref")
    decision_event_report = resolve_governance_artifact(
        decision_event_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="strategy_integration_decision_event",
        expected_digest=_first_text(claim, "decision_event_digest"),
    )
    reports["decision_event"] = decision_event_report
    blockers.extend(_prefixed_blockers("decision_event", decision_event_report))
    decision_event = _mapping(decision_event_report.get("payload"))
    control_payloads["decision_event"] = decision_event
    blockers.extend(
        _prefixed_blockers(
            "decision_event_contract",
            validate_strategy_integration_decision_event(decision_event),
        )
    )
    for prefix, event in (
        ("review_event", review_event),
        ("decision_event", decision_event),
    ):
        for field, expected in (
            ("strategy_family_id", strategy_family),
            ("strategy_id", strategy_id),
            ("frozen_binding_ref", binding_ref),
            ("binding_digest", binding_digest),
            ("candidate_fingerprint", fingerprint),
            ("review_package_ref", review_ref),
            ("review_package_digest", review_digest),
        ):
            if _first_text(event, field) != expected:
                blockers.append(f"{prefix}_{field}_mismatch")
    if _first_text(decision_event, "review_event_ref") != review_event_ref:
        blockers.append("decision_event_review_event_ref_mismatch")
    if _first_text(decision_event, "review_event_digest") != _first_text(
        review_event, "event_digest"
    ):
        blockers.append("decision_event_review_event_digest_mismatch")
    review_at = _parse_timestamp(_first_text(review_event, "occurred_at"))
    decision_at = _parse_timestamp(_first_text(decision_event, "occurred_at"))
    if review_at is None or decision_at is None or review_at > decision_at:
        blockers.append("integration_review_decision_order_invalid")
    if _first_text(decision_event, "decision") != "approved_for_strategy":
        blockers.append("strategy_integration_decision_not_approved")

    stage_policy_ref = _first_text(claim, "required_stage_policy_ref")
    stage_policy_report = resolve_governance_artifact(
        stage_policy_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="integration_stage_policy",
    )
    reports["stage_policy"] = stage_policy_report
    blockers.extend(_prefixed_blockers("stage_policy", stage_policy_report))
    control_payloads["stage_policy"] = _mapping(stage_policy_report.get("payload"))
    policy_stages = set(
        _strings(control_payloads.get("stage_policy", {}).get("required_stages"))
    )
    if not set(_STRICT_INTEGRATION_STAGES).issubset(policy_stages):
        blockers.append("integration_stage_policy_cannot_weaken_required_stages")
    blockers.extend(
        f"stage_policy_required_integration_stage_missing:{stage}"
        for stage in sorted(policy_stages - stages)
    )

    verdict = _first_text(claim, "claim_verdict")
    if verdict != "validated_for_strategy":
        blockers.append("strategy_integration_claim_not_validated")
    if claim.get("production_authority") is not False:
        blockers.append("strategy_integration_claim_cannot_grant_production_authority")
    receipt: dict[str, object] = {
        "artifact_type": "strategy_integration_resolution_receipt",
        "strategy_family": strategy_family,
        "strategy_id": strategy_id,
        "claim_ref": claim_ref,
        "binding_ref": binding_ref,
        "candidate_fingerprint": fingerprint,
        "admitted_factor_ref": _first_text(binding, "admitted_factor_asset_ref"),
        "baseline_ref": _first_text(binding, "baseline_artifact_ref"),
        "adapter_ref": _first_text(binding, "execution_adapter_ref"),
        "action_id": _first_text(binding, "action_id"),
        "usage_signature_hash": _first_text(binding, "usage_signature_hash"),
        "resolved_stages": sorted(stages),
        "status": "resolved" if not blockers else "blocked",
        "integration_eligible": not blockers,
        "creates_factor_asset": False,
        "production_authority": False,
        "blockers": sorted(set(blockers)),
        "resolution_reports": reports,
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    receipt["checksum"] = receipt["receipt_digest"]
    return receipt


def _resolve_integration_evidence_dependencies(
    evidence: Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None,
    candidate_fingerprint: str,
    strategy_family: str,
    campaign_id: str,
    temporal_policy_ref: str,
    temporal_policy: Mapping[str, object],
    governance_repository: TemporalGovernanceRepository | None,
) -> dict[str, object]:
    """Resolve every evidence-bearing ref inside one frozen-stage record."""

    blockers: list[str] = []
    reports: dict[str, object] = {}
    specs = (
        ("dataset_manifest_ref", {"dataset_manifest"}, ""),
        (
            "window_contract_ref",
            {"strategy_integration_window_contract", "window_contract"},
            "",
        ),
        (
            "fold_contract_ref",
            {"strategy_integration_fold_contract", "fold_contract"},
            "",
        ),
        ("data_usage_receipt_ref", {"data_usage_receipt"}, ""),
        (
            "lockbox_receipt_ref",
            {
                "lockbox_access_receipt",
                "lockbox_open_receipt",
                "lockbox_usage_receipt",
            },
            "",
        ),
        (
            "execution_artifact_ref",
            {
                "strategy_integration_execution_artifact",
                "strategy_execution_evidence",
                "execution_artifact",
            },
            _first_text(evidence, "execution_artifact_digest"),
        ),
        (
            "claim_schema_ref",
            {"strategy_integration_metric_contract"},
            _first_text(evidence, "claim_schema_digest"),
        ),
        (
            "no_harm_schema_ref",
            {"strategy_integration_no_harm_contract"},
            _first_text(evidence, "no_harm_schema_digest"),
        ),
    )
    for field, allowed_types, expected_digest in specs:
        ref = _first_text(evidence, field)
        if (
            field == "lockbox_receipt_ref"
            and _first_text(evidence, "integration_stage") == "lockbox"
            and governance_repository is not None
        ):
            receipt = governance_repository.get_lockbox_access_receipt(ref)
            resolved = receipt is not None
            report = {
                "status": "resolved" if resolved else "blocked",
                "payload": dict(_mapping(receipt)),
                "blockers": []
                if resolved
                else ["authoritative_lockbox_receipt_not_resolved"],
            }
            reports[field] = report
            blockers.extend(_prefixed_blockers(field, report))
            continue
        payload, _, _ = _catalog_payload(ref, evidence_catalog)
        artifact_type = _first_text(_mapping(payload), "artifact_type")
        if artifact_type not in allowed_types:
            blockers.append(f"{field}_artifact_type_invalid")
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type=artifact_type,
            expected_digest=expected_digest or None,
            expected_candidate_fingerprint=(
                candidate_fingerprint if field == "execution_artifact_ref" else None
            ),
        )
        reports[field] = report
        blockers.extend(_prefixed_blockers(field, report))
        if field in {
            "dataset_manifest_ref",
            "window_contract_ref",
            "fold_contract_ref",
        }:
            blockers.extend(
                _integration_dependency_contract_blockers(
                    _mapping(report.get("payload")),
                    artifact_type=artifact_type,
                    evidence=evidence,
                    campaign_id=campaign_id,
                )
            )
    blockers.extend(
        _window_fold_containment_blockers(
            _mapping(_mapping(reports.get("window_contract_ref")).get("payload")),
            _mapping(_mapping(reports.get("fold_contract_ref")).get("payload")),
            prefix="integration_fold_contract",
        )
    )
    for field, value_field, expected_kind in (
        ("claim_schema_ref", "metrics", "metrics"),
        ("no_harm_schema_ref", "no_harm_result", "no_harm"),
    ):
        contract = _mapping(_mapping(reports.get(field)).get("payload"))
        validation = validate_strategy_integration_result_contract(contract)
        blockers.extend(_prefixed_blockers(f"{field}_contract", validation))
        blockers.extend(
            _integration_contract_identity_blockers(
                contract,
                evidence=evidence,
                strategy_family=strategy_family,
                expected_kind=expected_kind,
            )
        )
        blockers.extend(
            _contract_value_blockers(
                contract,
                _mapping(evidence.get(value_field)),
                prefix=value_field,
            )
        )
    generic_reports: list[dict[str, object]] = []
    for index, ref in enumerate(_strings(evidence.get("evidence_refs"))):
        payload, _, _ = _catalog_payload(ref, evidence_catalog)
        artifact_type = _first_text(_mapping(payload), "artifact_type")
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type=artifact_type,
        )
        generic_reports.append(report)
        blockers.extend(_prefixed_blockers(f"evidence_ref:{index}", report))
    reports["evidence_refs"] = generic_reports
    authoritative_data_identity = ""
    if governance_repository is None:
        blockers.append("authoritative_governance_repository_required")
    else:
        authority_blockers, authoritative_data_identity = (
            _authoritative_integration_evidence_blockers(
                evidence,
                candidate_fingerprint=candidate_fingerprint,
                strategy_family=strategy_family,
                campaign_id=campaign_id,
                temporal_policy_ref=temporal_policy_ref,
                temporal_policy=temporal_policy,
                dataset=_mapping(
                    _mapping(reports.get("dataset_manifest_ref")).get("payload")
                ),
                window=_mapping(
                    _mapping(reports.get("window_contract_ref")).get("payload")
                ),
                fold=_mapping(
                    _mapping(reports.get("fold_contract_ref")).get("payload")
                ),
                data_usage_artifact=_mapping(
                    _mapping(reports.get("data_usage_receipt_ref")).get("payload")
                ),
                governance_repository=governance_repository,
            )
        )
        blockers.extend(authority_blockers)
    return {
        "artifact_type": "strategy_integration_evidence_dependency_resolution",
        "status": "resolved" if not blockers else "blocked",
        "reports": reports,
        "authoritative_data_identity": authoritative_data_identity,
        "blockers": sorted(set(blockers)),
    }


def _integration_dependency_contract_blockers(
    payload: Mapping[str, object],
    *,
    artifact_type: str,
    evidence: Mapping[str, object],
    campaign_id: str,
) -> list[str]:
    blockers: list[str] = []
    for field in ("schema_id", "canonicalization_version"):
        if not _first_text(payload, field):
            blockers.append(f"integration_{artifact_type}_{field}_required")
    if _first_text(payload, "canonicalization_version") != CANONICALIZATION_VERSION:
        blockers.append(f"integration_{artifact_type}_canonicalization_invalid")
    if _first_text(payload, "schema_id") not in _NESTED_SCHEMA_IDS.get(
        artifact_type, frozenset()
    ):
        blockers.append(f"integration_{artifact_type}_schema_id_invalid")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append(f"integration_{artifact_type}_field_labels_zh_required")
    if not _is_sha256_digest(payload.get("checksum")):
        blockers.append(f"integration_{artifact_type}_checksum_invalid")
    if artifact_type == "dataset_manifest":
        for field in ("dataset_id", "version", "source_vintage_ref", "available_at"):
            if not _first_text(payload, field):
                blockers.append(f"integration_dataset_manifest_{field}_required")
        if _parse_timestamp(_first_text(payload, "available_at")) is None:
            blockers.append("integration_dataset_manifest_available_at_invalid")
        return blockers
    for field, expected in (
        ("campaign_id", campaign_id),
        ("strategy_id", _first_text(evidence, "strategy_id")),
        ("dataset_manifest_ref", _first_text(evidence, "dataset_manifest_ref")),
        ("frozen_binding_ref", _first_text(evidence, "frozen_binding_ref")),
        ("binding_digest", _first_text(evidence, "binding_digest")),
        ("candidate_fingerprint", _first_text(evidence, "candidate_fingerprint")),
        ("action_id", _first_text(evidence, "action_id")),
    ):
        actual = _first_text(payload, field)
        if not actual:
            blockers.append(f"integration_{artifact_type}_{field}_required")
        elif actual != expected:
            blockers.append(f"integration_{artifact_type}_{field}_mismatch")
    start = _parse_timestamp(_first_text(payload, "start_at"))
    end = _parse_timestamp(_first_text(payload, "end_at"))
    if start is None or end is None:
        blockers.append(f"integration_{artifact_type}_bounds_invalid")
    elif start >= end:
        blockers.append(f"integration_{artifact_type}_bounds_not_ordered")
    if "fold_contract" in artifact_type and _first_text(
        payload, "window_contract_ref"
    ) != _first_text(evidence, "window_contract_ref"):
        blockers.append("integration_fold_contract_window_ref_mismatch")
    return blockers


def _integration_contract_identity_blockers(
    contract: Mapping[str, object],
    *,
    evidence: Mapping[str, object],
    strategy_family: str,
    expected_kind: str,
) -> list[str]:
    blockers: list[str] = []
    for field, expected in (
        ("contract_kind", expected_kind),
        ("strategy_family_id", strategy_family),
        ("strategy_id", _first_text(evidence, "strategy_id")),
        ("frozen_binding_ref", _first_text(evidence, "frozen_binding_ref")),
        ("binding_digest", _first_text(evidence, "binding_digest")),
        ("candidate_fingerprint", _first_text(evidence, "candidate_fingerprint")),
        ("action_id", _first_text(evidence, "action_id")),
    ):
        if _first_text(contract, field) != expected:
            blockers.append(f"integration_result_contract_{field}_mismatch")
    return blockers


def _contract_value_blockers(
    contract: Mapping[str, object],
    value: Mapping[str, object],
    *,
    prefix: str,
) -> list[str]:
    blockers: list[str] = []
    required = _strings(contract.get("required_fields"))
    field_types = _mapping(contract.get("field_types"))
    if set(value) != set(required):
        blockers.append(f"{prefix}_fields_contract_mismatch")
    for field in required:
        if field not in value:
            blockers.append(f"{prefix}_required_field_missing:{field}")
            continue
        if not _value_matches_contract_type(
            value[field], _first_text(field_types, field)
        ):
            blockers.append(f"{prefix}_field_type_mismatch:{field}")
    return blockers


def _value_matches_contract_type(value: object, type_name: str) -> bool:
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "object":
        return isinstance(value, Mapping)
    if type_name == "array":
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    return False


def _authoritative_integration_evidence_blockers(
    evidence: Mapping[str, object],
    *,
    candidate_fingerprint: str,
    strategy_family: str,
    campaign_id: str,
    temporal_policy_ref: str,
    temporal_policy: Mapping[str, object],
    dataset: Mapping[str, object],
    window: Mapping[str, object],
    fold: Mapping[str, object],
    data_usage_artifact: Mapping[str, object],
    governance_repository: TemporalGovernanceRepository,
) -> tuple[list[str], str]:
    """Cross-check integration data claims against append-only repository rows."""

    blockers: list[str] = []
    data_usage_ref = _first_text(evidence, "data_usage_receipt_ref")
    matching_events = [
        event
        for event in governance_repository.get_data_usage_events()
        if data_usage_ref
        in {
            _first_text(event, "access_event_id"),
            _first_text(event, "receipt_id"),
            _first_text(event, "artifact_ref"),
            _first_text(event, "receipt_ref"),
            _first_text(event, "data_usage_receipt_ref"),
        }
    ]
    if len(matching_events) != 1:
        blockers.append("authoritative_data_usage_receipt_not_resolved")
        return blockers, ""
    event = matching_events[0]
    catalog_data_usage = dict(data_usage_artifact)
    _ = catalog_data_usage.pop("checksum", None)
    _ = catalog_data_usage.pop("sha256", None)
    if catalog_data_usage != dict(event):
        blockers.append("authoritative_data_usage_payload_mismatch")
    stage = _first_text(evidence, "integration_stage")
    dataset_identity = _first_text(event, "dataset_manifest_ref", "dataset_ref")
    window_identity = _first_text(event, "window_contract_ref", "window_ref")
    if _first_text(event, "candidate_fingerprint") != candidate_fingerprint:
        blockers.append("authoritative_data_usage_candidate_fingerprint_mismatch")
    if dataset_identity != _first_text(evidence, "dataset_manifest_ref"):
        blockers.append("authoritative_data_usage_dataset_mismatch")
    if window_identity != _first_text(evidence, "window_contract_ref"):
        blockers.append("authoritative_data_usage_window_mismatch")
    if _first_text(event, "usage_stage", "stage") != stage:
        blockers.append("authoritative_data_usage_stage_mismatch")
    if event.get("brokered") is not True:
        blockers.append("authoritative_data_usage_not_brokered")
    blockers.extend(
        _authority_metadata_blockers(
            _mapping(event.get("metadata")),
            strategy_id=_first_text(evidence, "strategy_id"),
            campaign_id=campaign_id,
            dataset=dataset,
            temporal_policy_ref=temporal_policy_ref,
            temporal_policy=temporal_policy,
            window_contract_ref=_first_text(evidence, "window_contract_ref"),
            fold_contract_ref=_first_text(evidence, "fold_contract_ref"),
            window=window,
            fold=fold,
        )
    )

    for label, available_text in (
        (
            "receipt",
            _first_text(
                event, "available_at", "dataset_available_at", "max_available_at"
            ),
        ),
        (
            "dataset",
            _first_text(
                dataset,
                "available_at",
                "dataset_available_at",
                "max_available_at",
            ),
        ),
    ):
        if not available_text:
            continue
        authoritative_at = _parse_timestamp(available_text)
        evidence_at = _parse_timestamp(_first_text(evidence, "available_at"))
        decision_at = _parse_timestamp(_first_text(evidence, "decision_timestamp"))
        if authoritative_at is None:
            blockers.append(f"authoritative_{label}_available_at_invalid")
        elif decision_at is not None and authoritative_at > decision_at:
            blockers.append(f"authoritative_{label}_available_at_after_decision")
        elif evidence_at is not None and authoritative_at != evidence_at:
            blockers.append(f"authoritative_{label}_available_at_mismatch")

    if stage == "lockbox":
        receipt = governance_repository.get_lockbox_access_receipt(
            _first_text(evidence, "lockbox_receipt_ref")
        )
        if receipt is None:
            blockers.append("authoritative_lockbox_receipt_not_resolved")
        else:
            if _first_text(receipt, "candidate_fingerprint") != candidate_fingerprint:
                blockers.append("authoritative_lockbox_candidate_mismatch")
            if _first_text(receipt, "dataset_ref") != dataset_identity:
                blockers.append("authoritative_lockbox_dataset_mismatch")
            if _first_text(receipt, "window_ref") != window_identity:
                blockers.append("authoritative_lockbox_window_mismatch")
            if receipt.get("brokered") is not True:
                blockers.append("authoritative_lockbox_receipt_not_brokered")
            if _first_text(receipt, "data_usage_event_id") != _first_text(
                event, "access_event_id"
            ):
                blockers.append("authoritative_lockbox_data_usage_event_mismatch")
        if (
            governance_repository.get_lockbox_state(
                strategy_family, candidate_fingerprint
            )
            != "LOCKBOX_SEALED_REVIEW_REQUIRED"
        ):
            blockers.append("authoritative_lockbox_not_consumed_once")

    identity = json.dumps(
        {
            "candidate_fingerprint": _first_text(event, "candidate_fingerprint"),
            "dataset": dataset_identity,
            "window": window_identity,
            "row_manifest": _first_text(
                event, "row_manifest_ref", "sample_manifest_ref"
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return blockers, identity


def _prefixed_blockers(prefix: str, report: Mapping[str, object]) -> list[str]:
    return [f"{prefix}:{item}" for item in _strings(report.get("blockers"))]


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(value)


def _non_negative_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _first_text(payload: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        raw_value = payload.get(key)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if value:
            return value
    return ""


def _require_same(
    blockers: list[str],
    field: str,
    expected: str,
    payload: Mapping[str, object],
    prefix: str = "binding",
) -> None:
    actual = _first_text(payload, field)
    if not expected or not actual:
        blockers.append(f"{prefix}_{field}_required")
    elif actual != expected:
        blockers.append(f"{prefix}_{field}_mismatch")


def _require_same_ref(
    blockers: list[str], label: str, expected: str, actual: str
) -> None:
    if not expected or not actual:
        blockers.append(f"{label}_required")
    elif actual != expected:
        blockers.append(f"{label}_mismatch")


def build_frozen_strategy_factor_binding(
    *,
    binding_id: str,
    strategy_id: str,
    factor_ref: str,
    candidate_fingerprint: str,
    action_space_ref: str,
    action_space_version: str,
    action_id: str,
    usage_campaign_receipt_ref: str,
    selection_freeze_manifest_ref: str,
    code_digest: str,
    dataset_refs: Sequence[str],
    strategy_family_id: str,
    factor_asset_ref: str,
    admitted_factor_asset_ref: str,
    admitted_factor_digest: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    usage_hypothesis_ref: str,
    hypothesis_definition_digest: str,
    usage_signature_hash: str,
    selection_event_ref: str,
    execution_adapter_ref: str,
    adapter_digest: str,
    action_space_digest: str,
    usage_campaign_receipt_digest: str,
    selection_freeze_manifest_digest: str,
    immutable_artifact_refs: Sequence[Mapping[str, object]] = (),
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Bind a selected strategy use after discovery, before integration."""

    payload: dict[str, object] = {
        "artifact_type": "frozen_strategy_factor_binding",
        "schema_id": FROZEN_BINDING_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "usage_binding_id": binding_id,
        "binding_id": binding_id,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "factor_asset_ref": factor_asset_ref,
        "factor_ref": factor_ref,
        "admitted_factor_asset_ref": admitted_factor_asset_ref,
        "admitted_factor_digest": admitted_factor_digest,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "usage_hypothesis_ref": usage_hypothesis_ref,
        "hypothesis_definition_digest": hypothesis_definition_digest,
        "usage_signature_hash": usage_signature_hash,
        "candidate_fingerprint": candidate_fingerprint,
        "action_space_ref": action_space_ref,
        "action_space_version": action_space_version,
        "action_space_digest": action_space_digest,
        "action_id": action_id,
        "campaign_receipt_ref": usage_campaign_receipt_ref,
        "usage_campaign_receipt_ref": usage_campaign_receipt_ref,
        "usage_campaign_receipt_digest": usage_campaign_receipt_digest,
        "selection_event_ref": selection_event_ref,
        "selection_freeze_manifest_v2_ref": selection_freeze_manifest_ref,
        "selection_freeze_manifest_ref": selection_freeze_manifest_ref,
        "selection_freeze_manifest_digest": selection_freeze_manifest_digest,
        "execution_adapter_ref": execution_adapter_ref,
        "adapter_digest": adapter_digest,
        "code_digest": code_digest,
        "dataset_refs": list(dataset_refs),
        "immutable_artifact_refs": [dict(item) for item in immutable_artifact_refs]
        or [
            {
                "ref": admitted_factor_asset_ref,
                "digest": admitted_factor_digest,
            },
            {
                "ref": usage_hypothesis_ref,
                "digest": hypothesis_definition_digest,
            },
            {"ref": action_space_ref, "digest": action_space_digest},
            {
                "ref": usage_campaign_receipt_ref,
                "digest": usage_campaign_receipt_digest,
            },
            {
                "ref": selection_freeze_manifest_ref,
                "digest": selection_freeze_manifest_digest,
            },
            {"ref": execution_adapter_ref, "digest": adapter_digest},
            {"ref": baseline_artifact_ref, "digest": baseline_digest},
        ],
        "field_labels_zh": dict(
            field_labels_zh
            or {
                "usage_binding_id": "用途绑定编号",
                "usage_hypothesis_ref": "用途假设引用",
                "action_id": "冻结策略动作",
                "candidate_fingerprint": "候选语义指纹",
                "binding_digest": "绑定摘要",
            }
        ),
    }
    return _seal_artifact(
        payload,
        validate_frozen_strategy_factor_binding,
        digest_field="binding_digest",
    )


def validate_frozen_strategy_factor_binding(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _required_text_blockers(
        payload,
        "binding_id",
        "usage_binding_id",
        "strategy_family_id",
        "strategy_id",
        "factor_asset_ref",
        "factor_ref",
        "admitted_factor_asset_ref",
        "admitted_factor_digest",
        "baseline_artifact_ref",
        "baseline_digest",
        "usage_hypothesis_ref",
        "hypothesis_definition_digest",
        "usage_signature_hash",
        "candidate_fingerprint",
        "action_space_ref",
        "action_space_version",
        "action_space_digest",
        "action_id",
        "campaign_receipt_ref",
        "usage_campaign_receipt_ref",
        "usage_campaign_receipt_digest",
        "selection_event_ref",
        "selection_freeze_manifest_v2_ref",
        "selection_freeze_manifest_ref",
        "selection_freeze_manifest_digest",
        "execution_adapter_ref",
        "adapter_digest",
        "code_digest",
    )
    if not _is_sha256_digest(payload.get("candidate_fingerprint")):
        blockers.append("candidate_fingerprint_digest_required")
    if not _is_sha256_digest(payload.get("code_digest")):
        blockers.append("code_digest_required")
    if ":" not in _first_text(payload, "action_id"):
        blockers.append("strategy_action_id_must_be_namespaced")
    if not _strings(payload.get("dataset_refs")):
        blockers.append("dataset_refs_required")
    if _first_text(payload, "binding_id") != _first_text(payload, "usage_binding_id"):
        blockers.append("usage_binding_id_mismatch")
    if _first_text(payload, "campaign_receipt_ref") != _first_text(
        payload, "usage_campaign_receipt_ref"
    ):
        blockers.append("campaign_receipt_ref_mismatch")
    if _first_text(payload, "selection_freeze_manifest_v2_ref") != _first_text(
        payload, "selection_freeze_manifest_ref"
    ):
        blockers.append("selection_freeze_manifest_v2_ref_mismatch")
    digest_fields = (
        "admitted_factor_digest",
        "baseline_digest",
        "hypothesis_definition_digest",
        "usage_signature_hash",
        "adapter_digest",
        "action_space_digest",
        "usage_campaign_receipt_digest",
        "selection_freeze_manifest_digest",
    )
    for field in digest_fields:
        if not _is_sha256_digest(payload.get(field)):
            blockers.append(f"{field}_invalid")
    if not _sequence(payload.get("immutable_artifact_refs")):
        blockers.append("immutable_artifact_refs_required")
    for item in _sequence(payload.get("immutable_artifact_refs")):
        artifact = _mapping(item)
        if not _first_text(artifact, "ref"):
            blockers.append("immutable_artifact_ref_required")
        if not _is_sha256_digest(artifact.get("digest")):
            blockers.append("immutable_artifact_digest_invalid")
        if _first_text(artifact, "artifact_type") in {
            "strategy_integration_evidence",
            "strategy_integration_review_package",
            "strategy_integration_claim",
            "strategy_integration_decision_event",
            "strategy_usage_execution_receipt",
            "project_production_authorization",
        }:
            blockers.append("integration_artifact_cycle_detected")
    immutable_pairs = {
        (_first_text(_mapping(item), "ref"), _first_text(_mapping(item), "digest"))
        for item in _sequence(payload.get("immutable_artifact_refs"))
    }
    required_pairs = {
        (
            _first_text(payload, "admitted_factor_asset_ref"),
            _first_text(payload, "admitted_factor_digest"),
        ),
        (
            _first_text(payload, "usage_hypothesis_ref"),
            _first_text(payload, "hypothesis_definition_digest"),
        ),
        (
            _first_text(payload, "action_space_ref"),
            _first_text(payload, "action_space_digest"),
        ),
        (
            _first_text(payload, "usage_campaign_receipt_ref"),
            _first_text(payload, "usage_campaign_receipt_digest"),
        ),
        (
            _first_text(payload, "selection_freeze_manifest_ref"),
            _first_text(payload, "selection_freeze_manifest_digest"),
        ),
        (
            _first_text(payload, "execution_adapter_ref"),
            _first_text(payload, "adapter_digest"),
        ),
        (
            _first_text(payload, "baseline_artifact_ref"),
            _first_text(payload, "baseline_digest"),
        ),
    }
    if not required_pairs.issubset(immutable_pairs):
        blockers.append("immutable_artifact_refs_incomplete")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append("field_labels_zh_required")
    return _validation_report(payload, FROZEN_BINDING_SCHEMA_ID, blockers)


def build_legacy_compatible_frozen_strategy_factor_binding(
    *,
    binding_id: str,
    strategy_id: str,
    factor_ref: str,
    candidate_fingerprint: str,
    action_space_ref: str,
    usage_campaign_receipt_ref: str,
    selection_freeze_manifest_ref: str,
    code_digest: str,
    dataset_refs: Sequence[str],
) -> dict[str, object]:
    """Explicitly adapt one historical weak binding into the rich envelope.

    New callers must use :func:`build_frozen_strategy_factor_binding` and
    provide every frozen identity field.  This named compatibility surface is
    intentionally noisy so unresolved historical lineage cannot be mistaken
    for a normal rich write.
    """

    unresolved_ref = "artifact://legacy-unresolved"
    payload = build_frozen_strategy_factor_binding(
        binding_id=binding_id,
        strategy_family_id=f"legacy:{strategy_id}",
        strategy_id=strategy_id,
        factor_asset_ref=f"{unresolved_ref}/factor-asset",
        factor_ref=factor_ref,
        admitted_factor_asset_ref=f"{unresolved_ref}/admitted-factor",
        admitted_factor_digest=_legacy_compatibility_digest("admitted-factor"),
        baseline_artifact_ref=f"{unresolved_ref}/baseline",
        baseline_digest=_legacy_compatibility_digest("baseline"),
        usage_hypothesis_ref=f"{unresolved_ref}/usage-hypothesis",
        hypothesis_definition_digest=_legacy_compatibility_digest("usage-hypothesis"),
        usage_signature_hash=_legacy_compatibility_digest("usage-signature"),
        candidate_fingerprint=candidate_fingerprint,
        action_space_ref=action_space_ref,
        action_space_version="legacy:unresolved",
        action_space_digest=_legacy_compatibility_digest("action-space"),
        action_id="legacy:unresolved",
        usage_campaign_receipt_ref=usage_campaign_receipt_ref,
        usage_campaign_receipt_digest=_legacy_compatibility_digest("campaign"),
        selection_event_ref=f"{unresolved_ref}/selection-event",
        selection_freeze_manifest_ref=selection_freeze_manifest_ref,
        selection_freeze_manifest_digest=_legacy_compatibility_digest("freeze"),
        execution_adapter_ref=f"{unresolved_ref}/execution-adapter",
        adapter_digest=_legacy_compatibility_digest("execution-adapter"),
        code_digest=code_digest,
        dataset_refs=dataset_refs,
    )
    _ = payload.pop("binding_digest", None)
    _ = payload.pop("checksum", None)
    payload["artifact_type"] = "legacy_compatible_frozen_strategy_factor_binding"
    payload["schema_id"] = "legacy_compatible_frozen_strategy_factor_binding@1.0"
    payload["compatibility_mode"] = "legacy_unresolved_import"
    payload["promotion_eligible"] = False
    payload["checksum"] = canonical_digest(payload)
    return payload


def build_strategy_integration_evidence(
    *,
    integration_evidence_id: str,
    binding_ref: str,
    binding_digest: str,
    strategy_id: str,
    candidate_fingerprint: str,
    action_id: str,
    usage_signature_hash: str,
    integration_stage: str,
    outcome: str,
    dataset_manifest_ref: str,
    window_contract_ref: str,
    fold_contract_ref: str,
    data_usage_receipt_ref: str,
    lockbox_receipt_ref: str,
    observation_timestamp: str,
    available_at: str,
    decision_timestamp: str,
    execution_timestamp: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    execution_artifact_ref: str,
    execution_artifact_digest: str,
    metrics: Mapping[str, object],
    claim_schema_ref: str,
    claim_schema_digest: str,
    no_harm_schema_ref: str,
    no_harm_schema_digest: str,
    no_harm_result: Mapping[str, object],
    failure_scope: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Record frozen-stage integration evidence independently of discovery."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_integration_evidence",
        "schema_id": INTEGRATION_EVIDENCE_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "integration_evidence_id": integration_evidence_id,
        "frozen_binding_ref": binding_ref,
        "binding_digest": binding_digest,
        "strategy_id": strategy_id,
        "candidate_fingerprint": candidate_fingerprint,
        "action_id": action_id,
        "usage_signature_hash": usage_signature_hash,
        "integration_stage": integration_stage,
        "dataset_manifest_ref": dataset_manifest_ref,
        "window_contract_ref": window_contract_ref,
        "fold_contract_ref": fold_contract_ref,
        "data_usage_receipt_ref": data_usage_receipt_ref,
        "lockbox_receipt_ref": lockbox_receipt_ref,
        "observation_timestamp": observation_timestamp,
        "available_at": available_at,
        "decision_timestamp": decision_timestamp,
        "execution_timestamp": execution_timestamp,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "execution_artifact_ref": execution_artifact_ref,
        "execution_artifact_digest": execution_artifact_digest,
        "metrics": dict(metrics),
        "claim_schema_ref": claim_schema_ref,
        "claim_schema_digest": claim_schema_digest,
        "no_harm_schema_ref": no_harm_schema_ref,
        "no_harm_schema_digest": no_harm_schema_digest,
        "no_harm_result": dict(no_harm_result),
        "failure_scope": list(failure_scope),
        "evidence_refs": list(evidence_refs),
        "evidence_verdict": outcome,
        "field_labels_zh": dict(
            field_labels_zh
            or {
                "integration_evidence_id": "策略集成证据编号",
                "integration_stage": "冻结后验证阶段",
                "action_id": "冻结策略动作",
                "frozen_binding_ref": "冻结用途绑定引用",
                "evidence_verdict": "证据结论",
                "evidence_digest": "证据摘要",
            }
        ),
    }
    return _seal_artifact(
        payload,
        validate_strategy_integration_evidence,
        digest_field="evidence_digest",
    )


def build_strategy_integration_result_contract(
    *,
    contract_id: str,
    contract_kind: str,
    strategy_family_id: str,
    strategy_id: str,
    binding_ref: str,
    binding_digest: str,
    candidate_fingerprint: str,
    action_id: str,
    required_fields: Sequence[str],
    field_types: Mapping[str, str],
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Build a typed metric/no-harm contract bound to one frozen usage."""

    if contract_kind not in {"metrics", "no_harm"}:
        raise ValueError("contract_kind must be metrics or no_harm")
    artifact_type = (
        "strategy_integration_metric_contract"
        if contract_kind == "metrics"
        else "strategy_integration_no_harm_contract"
    )
    schema_id = (
        INTEGRATION_METRIC_CONTRACT_SCHEMA_ID
        if contract_kind == "metrics"
        else INTEGRATION_NO_HARM_CONTRACT_SCHEMA_ID
    )
    payload: dict[str, object] = {
        "artifact_type": artifact_type,
        "schema_id": schema_id,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "contract_id": contract_id,
        "contract_kind": contract_kind,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "frozen_binding_ref": binding_ref,
        "binding_digest": binding_digest,
        "candidate_fingerprint": candidate_fingerprint,
        "action_id": action_id,
        "required_fields": list(required_fields),
        "field_types": dict(field_types),
        "additional_fields_allowed": False,
        "field_labels_zh": dict(
            field_labels_zh
            or {
                "contract_id": "结果合同编号",
                "required_fields": "必填字段",
                "field_types": "字段类型约束",
            }
        ),
    }
    return _seal_artifact(
        payload,
        validate_strategy_integration_result_contract,
        digest_field="contract_digest",
    )


def validate_strategy_integration_result_contract(
    payload: Mapping[str, object],
) -> dict[str, object]:
    kind = _first_text(payload, "contract_kind")
    schema_id = (
        INTEGRATION_METRIC_CONTRACT_SCHEMA_ID
        if kind == "metrics"
        else INTEGRATION_NO_HARM_CONTRACT_SCHEMA_ID
    )
    blockers = _required_text_blockers(
        payload,
        "contract_id",
        "contract_kind",
        "strategy_family_id",
        "strategy_id",
        "frozen_binding_ref",
        "binding_digest",
        "candidate_fingerprint",
        "action_id",
    )
    expected_type = {
        "metrics": "strategy_integration_metric_contract",
        "no_harm": "strategy_integration_no_harm_contract",
    }.get(kind, "")
    if not expected_type:
        blockers.append("integration_result_contract_kind_invalid")
    if _first_text(payload, "artifact_type") != expected_type:
        blockers.append("integration_result_contract_artifact_type_invalid")
    if _first_text(payload, "schema_id") != schema_id:
        blockers.append("integration_result_contract_schema_id_invalid")
    if _first_text(payload, "canonicalization_version") != CANONICALIZATION_VERSION:
        blockers.append("integration_result_contract_canonicalization_invalid")
    for field in ("binding_digest", "candidate_fingerprint"):
        if not _is_sha256_digest(payload.get(field)):
            blockers.append(f"{field}_invalid")
    required_fields = _strings(payload.get("required_fields"))
    field_types = _mapping(payload.get("field_types"))
    if not required_fields:
        blockers.append("integration_result_contract_required_fields_required")
    allowed_types = {"number", "integer", "string", "boolean", "object", "array"}
    if set(field_types) != set(required_fields):
        blockers.append("integration_result_contract_field_types_mismatch")
    for field, type_name in field_types.items():
        if str(type_name) not in allowed_types:
            blockers.append(f"integration_result_contract_type_invalid:{field}")
    if kind == "no_harm" and not {"passed", "status"}.issubset(required_fields):
        blockers.append("no_harm_contract_passed_status_required")
    if payload.get("additional_fields_allowed") is not False:
        blockers.append("integration_result_contract_additional_fields_forbidden")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append("field_labels_zh_required")
    allowed_fields = {
        "artifact_type",
        "schema_id",
        "canonicalization_version",
        "contract_id",
        "contract_kind",
        "strategy_family_id",
        "strategy_id",
        "frozen_binding_ref",
        "binding_digest",
        "candidate_fingerprint",
        "action_id",
        "required_fields",
        "field_types",
        "additional_fields_allowed",
        "field_labels_zh",
        "contract_digest",
        "checksum",
    }
    if set(payload) - allowed_fields:
        blockers.append("integration_result_contract_additional_fields_forbidden")
    return _validation_report(payload, schema_id, blockers)


def build_strategy_integration_review_event(
    *,
    event_id: str,
    strategy_family_id: str,
    strategy_id: str,
    binding_ref: str,
    binding_digest: str,
    candidate_fingerprint: str,
    review_package_ref: str,
    review_package_digest: str,
    occurred_at: str,
    actor: str,
) -> dict[str, object]:
    """Freeze the human/machine review of one exact review package."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_integration_review_event",
        "schema_id": INTEGRATION_REVIEW_EVENT_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "event_id": event_id,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "frozen_binding_ref": binding_ref,
        "binding_digest": binding_digest,
        "candidate_fingerprint": candidate_fingerprint,
        "review_package_ref": review_package_ref,
        "review_package_digest": review_package_digest,
        "decision": "reviewed",
        "occurred_at": occurred_at,
        "actor": actor,
        "field_labels_zh": {"event_id": "集成审查事件编号", "decision": "审查结论"},
    }
    return _seal_artifact(
        payload,
        validate_strategy_integration_review_event,
        digest_field="event_digest",
    )


def validate_strategy_integration_review_event(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _integration_event_common_blockers(payload)
    if _first_text(payload, "decision") != "reviewed":
        blockers.append("strategy_integration_review_event_not_reviewed")
    if any(key in payload for key in ("claim_ref", "integration_claim_ref")):
        blockers.append("review_event_claim_back_reference_forbidden")
    return _validation_report(payload, INTEGRATION_REVIEW_EVENT_SCHEMA_ID, blockers)


def build_strategy_integration_decision_event(
    *,
    event_id: str,
    strategy_family_id: str,
    strategy_id: str,
    binding_ref: str,
    binding_digest: str,
    candidate_fingerprint: str,
    review_package_ref: str,
    review_package_digest: str,
    review_event_ref: str,
    review_event_digest: str,
    decision: str,
    occurred_at: str,
    actor: str,
) -> dict[str, object]:
    """Freeze a decision after, and only after, one exact review event."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_integration_decision_event",
        "schema_id": INTEGRATION_DECISION_EVENT_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "event_id": event_id,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "frozen_binding_ref": binding_ref,
        "binding_digest": binding_digest,
        "candidate_fingerprint": candidate_fingerprint,
        "review_package_ref": review_package_ref,
        "review_package_digest": review_package_digest,
        "review_event_ref": review_event_ref,
        "review_event_digest": review_event_digest,
        "decision": decision,
        "occurred_at": occurred_at,
        "actor": actor,
        "field_labels_zh": {"event_id": "集成决策事件编号", "decision": "决策结论"},
    }
    return _seal_artifact(
        payload,
        validate_strategy_integration_decision_event,
        digest_field="event_digest",
    )


def validate_strategy_integration_decision_event(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _integration_event_common_blockers(payload)
    blockers.extend(
        _required_text_blockers(payload, "review_event_ref", "review_event_digest")
    )
    if _first_text(payload, "decision") not in {
        "approved_for_strategy",
        "rejected_for_strategy",
        "inconclusive",
    }:
        blockers.append("strategy_integration_decision_invalid")
    if not _is_sha256_digest(payload.get("review_event_digest")):
        blockers.append("review_event_digest_invalid")
    if any(key in payload for key in ("claim_ref", "integration_claim_ref")):
        blockers.append("decision_event_claim_back_reference_forbidden")
    return _validation_report(payload, INTEGRATION_DECISION_EVENT_SCHEMA_ID, blockers)


def _integration_event_common_blockers(payload: Mapping[str, object]) -> list[str]:
    blockers = _required_text_blockers(
        payload,
        "event_id",
        "strategy_family_id",
        "strategy_id",
        "frozen_binding_ref",
        "binding_digest",
        "candidate_fingerprint",
        "review_package_ref",
        "review_package_digest",
        "decision",
        "occurred_at",
        "actor",
    )
    for field in ("binding_digest", "candidate_fingerprint", "review_package_digest"):
        if not _is_sha256_digest(payload.get(field)):
            blockers.append(f"{field}_invalid")
    if _parse_timestamp(_first_text(payload, "occurred_at")) is None:
        blockers.append("integration_event_occurred_at_invalid")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append("field_labels_zh_required")
    allowed_fields = {
        "artifact_type",
        "schema_id",
        "canonicalization_version",
        "event_id",
        "strategy_family_id",
        "strategy_id",
        "frozen_binding_ref",
        "binding_digest",
        "candidate_fingerprint",
        "review_package_ref",
        "review_package_digest",
        "decision",
        "occurred_at",
        "actor",
        "field_labels_zh",
        "event_digest",
        "checksum",
    }
    if _first_text(payload, "artifact_type") == "strategy_integration_decision_event":
        allowed_fields.update({"review_event_ref", "review_event_digest"})
    if set(payload) - allowed_fields:
        blockers.append("integration_event_additional_fields_forbidden")
    return blockers


def validate_strategy_integration_evidence(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _required_text_blockers(
        payload,
        "integration_evidence_id",
        "frozen_binding_ref",
        "binding_digest",
        "strategy_id",
        "candidate_fingerprint",
        "action_id",
        "usage_signature_hash",
        "dataset_manifest_ref",
        "window_contract_ref",
        "fold_contract_ref",
        "data_usage_receipt_ref",
        "lockbox_receipt_ref",
        "observation_timestamp",
        "available_at",
        "decision_timestamp",
        "execution_timestamp",
        "baseline_artifact_ref",
        "baseline_digest",
        "execution_artifact_ref",
        "execution_artifact_digest",
        "claim_schema_ref",
        "claim_schema_digest",
        "no_harm_schema_ref",
        "no_harm_schema_digest",
    )
    stage = _first_text(payload, "integration_stage", "stage")
    if stage not in _INTEGRATION_STAGES:
        blockers.append("integration_stage_invalid")
    if _first_text(payload, "artifact_type") == "factor_usage_trial_evidence" or (
        stage in _STRICT_INTEGRATION_STAGES
        and not _first_text(payload, "frozen_binding_ref")
    ):
        blockers.append("prefreeze_validation_forbidden")
    if str(payload.get("evidence_verdict")) not in _INTEGRATION_OUTCOMES:
        blockers.append("integration_outcome_invalid")
    if ":" not in _first_text(payload, "action_id"):
        blockers.append("strategy_action_id_must_be_namespaced")
    for field in (
        "binding_digest",
        "candidate_fingerprint",
        "usage_signature_hash",
        "baseline_digest",
        "execution_artifact_digest",
        "claim_schema_digest",
        "no_harm_schema_digest",
    ):
        if not _is_sha256_digest(payload.get(field)):
            blockers.append(f"{field}_invalid")
    if not _mapping(payload.get("metrics")):
        blockers.append("metrics_required")
    if not _mapping(payload.get("no_harm_result")):
        blockers.append("no_harm_result_required")
    no_harm = _mapping(payload.get("no_harm_result"))
    if _first_text(payload, "evidence_verdict") == "supported" and (
        no_harm.get("passed") is not True or _first_text(no_harm, "status") != "passed"
    ):
        blockers.append("supported_evidence_requires_explicit_no_harm_pass")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append("field_labels_zh_required")
    available_at = _parse_timestamp(_first_text(payload, "available_at"))
    decision_at = _parse_timestamp(_first_text(payload, "decision_timestamp"))
    execution_at = _parse_timestamp(_first_text(payload, "execution_timestamp"))
    observation_at = _parse_timestamp(_first_text(payload, "observation_timestamp"))
    if None in {available_at, decision_at, execution_at, observation_at}:
        blockers.append("integration_timestamp_invalid")
    else:
        assert available_at is not None
        assert decision_at is not None
        assert execution_at is not None
        assert observation_at is not None
        try:
            if available_at > decision_at:
                blockers.append("future_available_at_after_decision")
            if observation_at > available_at:
                blockers.append("observation_after_available_at")
            if decision_at > execution_at:
                blockers.append("decision_after_execution")
        except TypeError:
            blockers.append("integration_timestamp_timezone_mismatch")
    return _validation_report(payload, INTEGRATION_EVIDENCE_SCHEMA_ID, blockers)


def build_legacy_compatible_strategy_integration_evidence(
    *,
    integration_evidence_id: str,
    binding_ref: str,
    strategy_id: str,
    candidate_fingerprint: str,
    integration_stage: str,
    outcome: str,
) -> dict[str, object]:
    """Explicit historical adapter; never used by the normal rich builder."""

    unresolved_ref = "artifact://legacy-unresolved"
    timestamp = "1970-01-01T00:00:00+00:00"
    payload = build_strategy_integration_evidence(
        integration_evidence_id=integration_evidence_id,
        binding_ref=binding_ref,
        binding_digest=_legacy_compatibility_digest("binding"),
        strategy_id=strategy_id,
        candidate_fingerprint=candidate_fingerprint,
        action_id="legacy:unresolved",
        usage_signature_hash=_legacy_compatibility_digest("usage-signature"),
        integration_stage=integration_stage,
        outcome=outcome,
        dataset_manifest_ref=f"{unresolved_ref}/dataset-manifest",
        window_contract_ref=f"{unresolved_ref}/window",
        fold_contract_ref=f"{unresolved_ref}/fold",
        data_usage_receipt_ref=f"{unresolved_ref}/data-usage",
        lockbox_receipt_ref=f"{unresolved_ref}/lockbox",
        observation_timestamp=timestamp,
        available_at=timestamp,
        decision_timestamp=timestamp,
        execution_timestamp=timestamp,
        baseline_artifact_ref=f"{unresolved_ref}/baseline",
        baseline_digest=_legacy_compatibility_digest("baseline"),
        execution_artifact_ref=f"{unresolved_ref}/execution",
        execution_artifact_digest=_legacy_compatibility_digest("execution"),
        metrics={"legacy_unresolved": True},
        claim_schema_ref=f"{unresolved_ref}/claim-schema",
        claim_schema_digest=_legacy_compatibility_digest("claim-schema"),
        no_harm_schema_ref=f"{unresolved_ref}/no-harm-schema",
        no_harm_schema_digest=_legacy_compatibility_digest("no-harm-schema"),
        no_harm_result={
            "passed": outcome == "supported",
            "status": "passed" if outcome == "supported" else "legacy_unresolved",
        },
        failure_scope=("legacy_compatibility_only",),
    )
    _ = payload.pop("evidence_digest", None)
    _ = payload.pop("checksum", None)
    payload["artifact_type"] = "legacy_compatible_strategy_integration_evidence"
    payload["schema_id"] = "legacy_compatible_strategy_integration_evidence@1.0"
    payload["compatibility_mode"] = "legacy_unresolved_import"
    payload["promotion_eligible"] = False
    payload["checksum"] = canonical_digest(payload)
    return payload


def resolve_usage_integration_evidence(
    *,
    binding: Mapping[str, object] | None,
    integration_evidence: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Resolve an integration decision from frozen, identity-consistent evidence."""

    blockers: list[str] = []
    if binding is None:
        blockers.append("frozen_binding_required")
        binding_report: dict[str, object] = {}
        binding_id = ""
        strategy_id = ""
        fingerprint = ""
    else:
        binding_report = validate_frozen_strategy_factor_binding(binding)
        if binding_report["status"] != "valid":
            blockers.extend(_strings(binding_report["blockers"]))
        binding_id = _first_text(binding, "usage_binding_id", "binding_id")
        strategy_id = str(binding.get("strategy_id", ""))
        fingerprint = str(binding.get("candidate_fingerprint", ""))
    evidence_reports: list[dict[str, object]] = []
    outcomes: list[str] = []
    for item in integration_evidence:
        report = validate_strategy_integration_evidence(item)
        evidence_reports.append(report)
        if report["status"] != "valid":
            blockers.extend(_strings(report["blockers"]))
            continue
        if _first_text(item, "frozen_binding_ref", "binding_ref") != binding_id:
            blockers.append("integration_binding_ref_mismatch")
        if _first_text(item, "binding_digest") != _first_text(
            _mapping(binding), "binding_digest", "checksum"
        ):
            blockers.append("integration_binding_digest_mismatch")
        if str(item.get("strategy_id")) != strategy_id:
            blockers.append("integration_strategy_id_mismatch")
        if str(item.get("candidate_fingerprint")) != fingerprint:
            blockers.append("integration_candidate_fingerprint_mismatch")
        for field in ("action_id", "usage_signature_hash"):
            if _first_text(item, field) != _first_text(_mapping(binding), field):
                blockers.append(f"integration_{field}_mismatch")
        outcomes.append(_first_text(item, "evidence_verdict", "outcome"))
    if not integration_evidence:
        blockers.append("integration_evidence_required")
    if "rejected" in outcomes:
        blockers.append("integration_rejected_evidence_present")
    if "supported" not in outcomes:
        blockers.append("supported_integration_evidence_required")
    eligible = not blockers
    return {
        "artifact_type": "usage_integration_evidence_resolution",
        "status": "eligible" if eligible else "blocked",
        "integration_status": "eligible" if eligible else "blocked",
        "binding_validation": binding_report,
        "integration_evidence": evidence_reports,
        "blockers": sorted(set(blockers)),
    }


def build_strategy_integration_review_package(
    *,
    review_package_id: str,
    binding_ref: str,
    binding_digest: str,
    strategy_id: str,
    candidate_fingerprint: str,
    admitted_factor_asset_ref: str,
    admitted_factor_digest: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    integration_evidence_refs: Sequence[Mapping[str, object]],
    resolver_report_ref: str,
    resolver_report_digest: str,
    readiness: str,
    blockers: Sequence[str] = (),
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Assemble a review package; references remain resolver-gated downstream."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_integration_review_package",
        "schema_id": INTEGRATION_REVIEW_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "integration_review_package_id": review_package_id,
        "admitted_factor_asset_ref": admitted_factor_asset_ref,
        "admitted_factor_digest": admitted_factor_digest,
        "frozen_binding_ref": binding_ref,
        "binding_digest": binding_digest,
        "strategy_id": strategy_id,
        "candidate_fingerprint": candidate_fingerprint,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "integration_evidence_refs": [dict(item) for item in integration_evidence_refs],
        "resolver_report_ref": resolver_report_ref,
        "resolver_report_digest": resolver_report_digest,
        "readiness": readiness,
        "blockers": list(blockers),
        "creates_integration_claim": False,
        "production_authority": False,
        "field_labels_zh": dict(
            field_labels_zh
            or {
                "integration_review_package_id": "策略集成审查包编号",
                "frozen_binding_ref": "冻结用途绑定引用",
                "readiness": "审查就绪状态",
                "package_digest": "审查包摘要",
            }
        ),
    }
    return _seal_artifact(
        payload,
        validate_strategy_integration_review_package,
        digest_field="package_digest",
    )


def validate_strategy_integration_review_package(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _required_text_blockers(
        payload,
        "integration_review_package_id",
        "admitted_factor_asset_ref",
        "admitted_factor_digest",
        "frozen_binding_ref",
        "binding_digest",
        "strategy_id",
        "candidate_fingerprint",
        "baseline_artifact_ref",
        "baseline_digest",
        "resolver_report_ref",
        "resolver_report_digest",
    )
    if not _sequence(payload.get("integration_evidence_refs")):
        blockers.append("integration_evidence_refs_required")
    for item in _sequence(payload.get("integration_evidence_refs")):
        entry = _mapping(item)
        for field in ("ref", "stage", "artifact_type", "schema_id", "evidence_digest"):
            if not _first_text(entry, field):
                blockers.append(f"integration_evidence_entry_{field}_required")
        if _first_text(entry, "stage") not in _INTEGRATION_STAGES:
            blockers.append("integration_evidence_entry_stage_invalid")
        if _first_text(entry, "artifact_type") != "strategy_integration_evidence":
            blockers.append("integration_evidence_entry_artifact_type_invalid")
        if _first_text(entry, "schema_id") != INTEGRATION_EVIDENCE_SCHEMA_ID:
            blockers.append("integration_evidence_entry_schema_id_invalid")
        if not _is_sha256_digest(entry.get("evidence_digest")):
            blockers.append("integration_evidence_entry_digest_invalid")
    readiness = _first_text(payload, "readiness")
    if readiness not in _REVIEW_READINESS:
        blockers.append("review_readiness_invalid")
    if readiness == "ready_for_integration_review" and _strings(
        payload.get("blockers")
    ):
        blockers.append("ready_review_cannot_have_blockers")
    if _first_text(payload, "recommendation") == "not_eligible":
        blockers.append("strategy_integration_review_not_eligible")
    for field in (
        "admitted_factor_digest",
        "binding_digest",
        "baseline_digest",
        "resolver_report_digest",
    ):
        if not _is_sha256_digest(payload.get(field)):
            blockers.append(f"{field}_invalid")
    if payload.get("creates_integration_claim") is not False:
        blockers.append("review_package_cannot_create_claim")
    if payload.get("production_authority") is not False:
        blockers.append("review_package_cannot_grant_production_authority")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append("field_labels_zh_required")
    return _validation_report(payload, INTEGRATION_REVIEW_SCHEMA_ID, blockers)


def build_strategy_integration_claim(
    *,
    claim_id: str,
    review_package_ref: str,
    strategy_id: str,
    candidate_fingerprint: str,
    review_resolution: Mapping[str, object],
    execution_surface_eligible: bool,
) -> dict[str, object]:
    """Build a compatibility envelope that still requires resolver proof.

    The supplied booleans are copied only for diagnostics. The generated
    unresolved refs ensure this helper can never replace the typed claim DAG.
    """

    _ = (review_resolution, execution_surface_eligible)
    payload: dict[str, object] = {
        "artifact_type": "strategy_integration_claim",
        "schema_id": INTEGRATION_CLAIM_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "integration_claim_id": claim_id,
        "claim_id": claim_id,
        "strategy_family_id": f"legacy:{strategy_id}",
        "admitted_factor_asset_ref": "artifact://legacy-unresolved/admitted-factor",
        "admitted_factor_digest": _legacy_compatibility_digest("admitted-factor"),
        "frozen_binding_ref": "artifact://legacy-unresolved/binding",
        "binding_digest": _legacy_compatibility_digest("binding"),
        "review_package_ref": review_package_ref,
        "strategy_integration_review_package_ref": review_package_ref,
        "review_package_digest": _legacy_compatibility_digest("review-package"),
        "strategy_id": strategy_id,
        "candidate_fingerprint": candidate_fingerprint,
        "baseline_artifact_ref": "artifact://legacy-unresolved/baseline",
        "baseline_digest": _legacy_compatibility_digest("baseline"),
        "usage_signature_hash": _legacy_compatibility_digest("usage-signature"),
        "integration_evidence_refs": [
            {
                "ref": "artifact://legacy-unresolved/integration-evidence",
                "stage": "validation",
                "artifact_type": "strategy_integration_evidence",
                "schema_id": INTEGRATION_EVIDENCE_SCHEMA_ID,
                "evidence_digest": _legacy_compatibility_digest("integration-evidence"),
            }
        ],
        "required_stage_policy_ref": "artifact://legacy-unresolved/stage-policy",
        "stage_completeness_report": {
            "required_stages": ["validation"],
            "resolved_stages": ["validation"],
            "complete": True,
        },
        "review_event_ref": "artifact://legacy-unresolved/review-event",
        "review_event_digest": _legacy_compatibility_digest("review-event"),
        "decision_event_ref": "artifact://legacy-unresolved/decision-event",
        "decision_event_digest": _legacy_compatibility_digest("decision-event"),
        "claim_verdict": "blocked",
        "failure_scope": ["legacy_self_reported_compatibility_only"],
        "field_labels_zh": {
            "integration_claim_id": "兼容声明编号",
            "claim_verdict": "自报结论（不可作为权威证据）",
        },
        "creates_effective_factor": False,
        "creates_admitted_factor": False,
        "integration_status": "blocked",
        "execution_eligible": False,
        "production_authority": False,
    }
    return _seal_artifact(
        payload,
        validate_strategy_integration_claim,
        digest_field="claim_digest",
    )


def validate_strategy_integration_claim(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _required_text_blockers(
        payload,
        "integration_claim_id",
        "claim_id",
        "strategy_family_id",
        "admitted_factor_asset_ref",
        "admitted_factor_digest",
        "frozen_binding_ref",
        "binding_digest",
        "baseline_artifact_ref",
        "baseline_digest",
        "usage_signature_hash",
        "required_stage_policy_ref",
        "strategy_integration_review_package_ref",
        "review_package_digest",
        "review_event_ref",
        "review_event_digest",
        "decision_event_ref",
        "decision_event_digest",
        "strategy_id",
        "candidate_fingerprint",
    )
    if _first_text(payload, "integration_claim_id") != _first_text(payload, "claim_id"):
        blockers.append("integration_claim_id_mismatch")
    verdict = _first_text(payload, "claim_verdict")
    if verdict not in {"rejected", "validated_for_strategy", "blocked", "inconclusive"}:
        blockers.append("claim_verdict_invalid")
    evidence_entries = _sequence(payload.get("integration_evidence_refs"))
    if not evidence_entries:
        blockers.append("integration_evidence_refs_required")
    for item in evidence_entries:
        entry = _mapping(item)
        if set(entry) != {
            "ref",
            "stage",
            "artifact_type",
            "schema_id",
            "evidence_digest",
        }:
            blockers.append("integration_evidence_entry_fields_invalid")
        for field in ("ref", "stage", "artifact_type", "schema_id", "evidence_digest"):
            if not _first_text(entry, field):
                blockers.append(f"integration_evidence_entry_{field}_required")
        if _first_text(entry, "stage") not in _INTEGRATION_STAGES:
            blockers.append("integration_evidence_entry_stage_invalid")
        if _first_text(entry, "artifact_type") != "strategy_integration_evidence":
            blockers.append("integration_evidence_entry_artifact_type_invalid")
        if _first_text(entry, "schema_id") != INTEGRATION_EVIDENCE_SCHEMA_ID:
            blockers.append("integration_evidence_entry_schema_id_invalid")
        if not _is_sha256_digest(entry.get("evidence_digest")):
            blockers.append("integration_evidence_entry_digest_invalid")
    completeness = _mapping(payload.get("stage_completeness_report"))
    if not completeness:
        blockers.append("stage_completeness_report_required")
    elif set(completeness) != {"required_stages", "resolved_stages", "complete"}:
        blockers.append("stage_completeness_report_fields_invalid")
    elif (
        verdict == "validated_for_strategy" and completeness.get("complete") is not True
    ):
        blockers.append("validated_claim_requires_complete_stages")
    for field in (
        "admitted_factor_digest",
        "binding_digest",
        "baseline_digest",
        "usage_signature_hash",
        "review_package_digest",
        "review_event_digest",
        "decision_event_digest",
    ):
        if not _is_sha256_digest(payload.get(field)):
            blockers.append(f"{field}_invalid")
    if payload.get("creates_effective_factor") is not False:
        blockers.append("integration_claim_cannot_create_effective_factor")
    if payload.get("creates_admitted_factor") is not False:
        blockers.append("integration_claim_cannot_create_admitted_factor")
    if payload.get("production_authority") is not False:
        blockers.append("integration_claim_cannot_grant_production_authority")
    if payload.get("integration_status") != "blocked":
        blockers.append("integration_claim_cannot_self_report_eligible_status")
    if payload.get("execution_eligible") is not False:
        blockers.append("integration_claim_cannot_self_report_execution_eligibility")
    allowed_fields = {
        "artifact_type",
        "schema_id",
        "canonicalization_version",
        "integration_claim_id",
        "claim_id",
        "strategy_family_id",
        "strategy_id",
        "admitted_factor_asset_ref",
        "admitted_factor_digest",
        "frozen_binding_ref",
        "binding_digest",
        "candidate_fingerprint",
        "baseline_artifact_ref",
        "baseline_digest",
        "usage_signature_hash",
        "integration_evidence_refs",
        "required_stage_policy_ref",
        "stage_completeness_report",
        "strategy_integration_review_package_ref",
        "review_package_ref",
        "review_package_digest",
        "review_event_ref",
        "review_event_digest",
        "decision_event_ref",
        "decision_event_digest",
        "claim_verdict",
        "failure_scope",
        "field_labels_zh",
        "creates_effective_factor",
        "creates_admitted_factor",
        "integration_status",
        "execution_eligible",
        "production_authority",
        "claim_digest",
        "checksum",
    }
    if set(payload) - allowed_fields:
        blockers.append("integration_claim_additional_fields_forbidden")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append("field_labels_zh_required")
    return _validation_report(payload, INTEGRATION_CLAIM_SCHEMA_ID, blockers)


def build_legacy_usage_discovery_cutover_compatibility(
    *,
    change_id: str,
    strategy_id: str,
    mode: str,
    reason: str,
    authorized_claim_ids: Sequence[str] = (),
    prior_cutover: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the legacy cutover envelope for historical-read compatibility."""

    payload: dict[str, object] = {
        "artifact_type": "usage_discovery_cutover",
        "schema_id": USAGE_DISCOVERY_CUTOVER_SCHEMA_ID,
        "change_id": change_id,
        "strategy_id": strategy_id,
        "mode": mode,
        "reason": reason,
        "authorized_claim_ids": list(authorized_claim_ids),
        "required_history": bool(
            prior_cutover
            and (
                str(prior_cutover.get("mode")) == "required"
                or prior_cutover.get("required_history") is True
            )
        )
        or mode == "required",
        "version": int(str(prior_cutover.get("version", 0))) + 1
        if prior_cutover
        else 1,
    }
    report = validate_usage_discovery_cutover(payload, prior_cutover=prior_cutover)
    if report["status"] != "valid":
        raise ValueError("; ".join(_strings(report["blockers"])))
    payload["checksum"] = canonical_digest(payload)
    return payload


def build_usage_discovery_cutover(
    *,
    change_id: str,
    strategy_id: str,
    mode: str,
    reason: str,
    authorized_claim_ids: Sequence[str] = (),
    prior_cutover: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Deprecated alias for the explicit historical-read compatibility builder."""

    return build_legacy_usage_discovery_cutover_compatibility(
        change_id=change_id,
        strategy_id=strategy_id,
        mode=mode,
        reason=reason,
        authorized_claim_ids=authorized_claim_ids,
        prior_cutover=prior_cutover,
    )


def build_strategy_usage_cutover(
    *,
    change_id: str,
    strategy_family_id: str,
    strategy_id: str,
    owner: str,
    mode: str,
    action_space_ref: str,
    action_space_digest: str,
    action_space_version: str,
    adapter_ref: str,
    adapter_digest: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    effective_at: str,
    reason: str,
    evidence_refs: Sequence[str],
    test_refs: Sequence[str],
    rollback_target: str = "shadow_audit",
    authorized_claim_ids: Sequence[str] = (),
    prior_cutover: Mapping[str, object] | None = None,
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Build one immutable rich per-strategy cutover matrix row."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_usage_cutover",
        "schema_id": STRATEGY_USAGE_CUTOVER_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "change_id": change_id,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "owner": owner,
        "mode": mode,
        "action_space_ref": action_space_ref,
        "action_space_digest": action_space_digest,
        "action_space_version": action_space_version,
        "adapter_ref": adapter_ref,
        "adapter_digest": adapter_digest,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "effective_at": effective_at,
        "rollback_target": rollback_target,
        "evidence_refs": list(evidence_refs),
        "test_refs": list(test_refs),
        "reason": reason,
        "authorized_claim_ids": list(authorized_claim_ids),
        "required_history": bool(
            prior_cutover
            and (
                _first_text(prior_cutover, "mode") == "required"
                or prior_cutover.get("required_history") is True
            )
        )
        or mode == "required",
        "legacy_new_promotion_allowed": False,
        "production_authority": False,
        "version": int(str(prior_cutover.get("version", 0))) + 1
        if prior_cutover
        else 1,
        "field_labels_zh": dict(
            field_labels_zh
            or {
                "strategy_id": "策略编号",
                "owner": "迁移负责人",
                "mode": "逐策略切换状态",
                "effective_at": "生效时间",
                "rollback_target": "回滚目标",
                "cutover_digest": "切换记录摘要",
            }
        ),
    }
    return _seal_artifact(
        payload,
        lambda item: validate_strategy_usage_cutover(item, prior_cutover=prior_cutover),
        digest_field="cutover_digest",
    )


def build_strategy_usage_cutover_transition_receipt(
    *,
    transition_id: str,
    strategy_id: str,
    expected_prior_state: str,
    expected_prior_version: int,
    next_state: str,
    reason: str,
    authorization_ref: str,
    authorization_digest: str = "",
    rich_cutover_digest: str = "",
    assurance_records: Sequence[Mapping[str, object]] = (),
    occurred_at: str,
    rollback_snapshot_ref: str = "",
    authorized_claim_ids: Sequence[str] = (),
    prior_required_history: bool = False,
) -> dict[str, object]:
    """Build an append-only receipt for one legal cutover CAS transition."""

    blockers: list[str] = []
    allowed = {
        ("legacy_read", "shadow_audit"),
        ("shadow_audit", "required"),
        ("required", "shadow_audit"),
    }
    if (expected_prior_state, next_state) not in allowed:
        blockers.append("invalid_usage_discovery_cutover_transition")
    if expected_prior_version < 0:
        blockers.append("expected_prior_version_invalid")
    for field, value in (
        ("transition_id", transition_id),
        ("strategy_id", strategy_id),
        ("reason", reason),
        ("authorization_ref", authorization_ref),
        ("occurred_at", occurred_at),
    ):
        if not str(value).strip():
            blockers.append(f"{field}_required")
    occurred = _parse_timestamp(occurred_at)
    if occurred is None or occurred.tzinfo is None:
        blockers.append("occurred_at_invalid")
    if expected_prior_state == "required" and next_state == "shadow_audit":
        if not rollback_snapshot_ref:
            blockers.append("rollback_snapshot_ref_required")
    for field, digest in (
        ("authorization_digest", authorization_digest),
        ("rich_cutover_digest", rich_cutover_digest),
    ):
        if digest and not _is_sha256_digest(digest):
            blockers.append(f"{field}_invalid")
    normalized_assurance_records: list[dict[str, str]] = []
    for index, record in enumerate(assurance_records):
        normalized = {
            "ref": _first_text(record, "ref"),
            "digest": _first_text(record, "digest"),
            "kind": _first_text(record, "kind"),
        }
        if not normalized["ref"]:
            blockers.append(f"assurance_record_ref_required:{index}")
        if not _is_sha256_digest(normalized["digest"]):
            blockers.append(f"assurance_record_digest_invalid:{index}")
        if normalized["kind"] not in {"evidence", "test"}:
            blockers.append(f"assurance_record_kind_invalid:{index}")
        normalized_assurance_records.append(normalized)
    if next_state == "required":
        if not authorization_digest:
            blockers.append("authorization_digest_required")
        if not rich_cutover_digest:
            blockers.append("rich_cutover_digest_required")
        if not normalized_assurance_records:
            blockers.append("assurance_records_required")
    if blockers:
        raise ValueError("; ".join(sorted(set(blockers))))
    payload: dict[str, object] = {
        "artifact_type": "strategy_usage_cutover_transition_receipt",
        "schema_id": CUTOVER_TRANSITION_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "transition_id": transition_id,
        "strategy_id": strategy_id,
        "expected_prior_state": expected_prior_state,
        "expected_prior_version": expected_prior_version,
        "next_state": next_state,
        "reason": reason,
        "authorization_ref": authorization_ref,
        "authorization_digest": authorization_digest,
        "rich_cutover_digest": rich_cutover_digest,
        "assurance_records": normalized_assurance_records,
        "rollback_snapshot_ref": rollback_snapshot_ref,
        "occurred_at": occurred_at,
        "authorized_claim_ids": list(authorized_claim_ids),
        "required_history": (
            prior_required_history
            or expected_prior_state == "required"
            or next_state == "required"
        ),
        "legacy_new_promotion_allowed": False,
        "production_authority": False,
        "field_labels_zh": {
            "transition_id": "切换转换编号",
            "expected_prior_state": "预期前态",
            "next_state": "目标状态",
            "rollback_snapshot_ref": "回滚快照引用",
            "receipt_digest": "转换回执摘要",
        },
    }
    payload["receipt_digest"] = canonical_digest(payload)
    return payload


def validate_usage_discovery_cutover(
    payload: Mapping[str, object],
    *,
    prior_cutover: Mapping[str, object] | None = None,
) -> dict[str, object]:
    blockers = _required_text_blockers(payload, "change_id", "strategy_id", "reason")
    mode = str(payload.get("mode"))
    if mode not in _CUTOVER_MODES:
        blockers.append("cutover_mode_invalid")
    authorized_ids = _strings(payload.get("authorized_claim_ids"))
    if len(authorized_ids) != len(set(authorized_ids)):
        blockers.append("authorized_claim_ids_duplicate")
    if prior_cutover is not None:
        if str(prior_cutover.get("strategy_id")) != str(payload.get("strategy_id")):
            blockers.append("cutover_strategy_id_mismatch")
        else:
            blockers.extend(_cutover_transition_blockers(prior_cutover, mode))
            prior_ids = set(_strings(prior_cutover.get("authorized_claim_ids")))
            if not prior_ids.issubset(set(authorized_ids)):
                blockers.append("authorized_claim_ids_cannot_be_removed")
    return _validation_report(payload, USAGE_DISCOVERY_CUTOVER_SCHEMA_ID, blockers)


def validate_strategy_usage_cutover(
    payload: Mapping[str, object],
    *,
    prior_cutover: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate the rich cutover row used by all new migration writes."""

    blockers = _required_text_blockers(
        payload,
        "change_id",
        "strategy_family_id",
        "strategy_id",
        "owner",
        "action_space_ref",
        "action_space_digest",
        "action_space_version",
        "adapter_ref",
        "adapter_digest",
        "baseline_artifact_ref",
        "baseline_digest",
        "effective_at",
        "rollback_target",
        "reason",
    )
    mode = _first_text(payload, "mode")
    if mode not in _CUTOVER_MODES:
        blockers.append("cutover_mode_invalid")
    if _first_text(payload, "rollback_target") != "shadow_audit":
        blockers.append("cutover_rollback_target_invalid")
    for field in (
        "action_space_digest",
        "adapter_digest",
        "baseline_digest",
        "cutover_digest",
    ):
        if str(payload.get(field, "")).strip() and not _is_sha256_digest(
            payload.get(field)
        ):
            blockers.append(f"{field}_invalid")
    effective_at = _parse_timestamp(_first_text(payload, "effective_at"))
    if effective_at is None or effective_at.tzinfo is None:
        blockers.append("cutover_effective_at_invalid")
    if mode in {"shadow_audit", "required"} and not _strings(
        payload.get("evidence_refs")
    ):
        blockers.append("cutover_evidence_refs_required")
    if mode == "required" and not _strings(payload.get("test_refs")):
        blockers.append("cutover_test_refs_required")
    if payload.get("legacy_new_promotion_allowed") is not False:
        blockers.append("legacy_new_promotion_must_remain_closed")
    if payload.get("production_authority") is not False:
        blockers.append("cutover_cannot_grant_production_authority")
    if not _mapping(payload.get("field_labels_zh")):
        blockers.append("field_labels_zh_required")
    authorized_ids = _strings(payload.get("authorized_claim_ids"))
    if len(authorized_ids) != len(set(authorized_ids)):
        blockers.append("authorized_claim_ids_duplicate")
    if prior_cutover is not None:
        if _first_text(prior_cutover, "strategy_id") != _first_text(
            payload, "strategy_id"
        ):
            blockers.append("cutover_strategy_id_mismatch")
        else:
            blockers.extend(_cutover_transition_blockers(prior_cutover, mode))
        if (
            int(str(payload.get("version", 0)))
            != int(str(prior_cutover.get("version", 0))) + 1
        ):
            blockers.append("cutover_version_not_sequential")
    return _validation_report(payload, STRATEGY_USAGE_CUTOVER_SCHEMA_ID, blockers)


def validate_strategy_usage_cutover_assurance(
    payload: Mapping[str, object],
    *,
    cutover: Mapping[str, object],
    expected_kind: str,
    evidence_catalog: EvidenceCatalog | None,
) -> list[str]:
    """Validate one cutover assurance and re-resolve its bound results.

    A positive top-level status is only a summary.  Eligibility is grounded in
    immutable result references whose recorded digests are recomputed here.
    """

    blockers: list[str] = []
    expected_type = (
        "strategy_usage_cutover_evidence"
        if expected_kind == "evidence"
        else "strategy_usage_cutover_test"
    )
    expected_result_type = (
        "strategy_usage_shadow_result"
        if expected_kind == "evidence"
        else "strategy_usage_conformance_result"
    )
    expected_result_schema_id = f"{expected_result_type}@1.0"
    if _first_text(payload, "artifact_type") != expected_type:
        blockers.append("artifact_type_mismatch")
    if _first_text(payload, "schema_id") != "strategy_usage_cutover_assurance@1.0":
        blockers.append("schema_id_mismatch")
    if _first_text(payload, "canonicalization_version") != CANONICALIZATION_VERSION:
        blockers.append("canonicalization_version_mismatch")
    if _first_text(payload, "assurance_kind") != expected_kind:
        blockers.append("assurance_kind_mismatch")
    for field in (
        "strategy_family_id",
        "strategy_id",
        "change_id",
        "mode",
        "version",
        "cutover_digest",
        "action_space_ref",
        "action_space_digest",
        "action_space_version",
        "adapter_ref",
        "adapter_digest",
        "baseline_artifact_ref",
        "baseline_digest",
    ):
        if str(payload.get(field, "")) != str(cutover.get(field, "")):
            blockers.append(f"{field}_mismatch")
    if _first_text(payload, "status") != "passed":
        blockers.append("assurance_status_not_passed")
    result_refs = _strings(payload.get("result_refs"))
    result_digests = _strings(payload.get("result_digests"))
    if not result_refs or len(result_refs) != len(result_digests):
        blockers.append("assurance_result_ledger_invalid")
        return blockers
    if len(result_refs) != len(set(result_refs)):
        blockers.append("assurance_result_refs_duplicate")
    pairs = zip(result_refs, result_digests, strict=True)
    for index, (ref, digest) in enumerate(pairs):
        if not _is_sha256_digest(digest):
            blockers.append(f"assurance_result_digest_invalid:{index}")
            continue
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type=expected_result_type,
            expected_digest=digest,
        )
        blockers.extend(
            f"assurance_result:{index}:{item}"
            for item in _strings(report.get("blockers"))
        )
        result = _mapping(report.get("payload"))
        if _first_text(result, "schema_id") != expected_result_schema_id:
            blockers.append(f"assurance_result_schema_id_mismatch:{index}")
        if _first_text(result, "canonicalization_version") != (
            CANONICALIZATION_VERSION
        ):
            blockers.append(
                f"assurance_result_canonicalization_version_mismatch:{index}"
            )
        if not _mapping(result.get("field_labels_zh")):
            blockers.append(f"assurance_result_field_labels_zh_required:{index}")
        for field in (
            "strategy_family_id",
            "strategy_id",
            "change_id",
            "mode",
            "version",
            "cutover_digest",
        ):
            if str(result.get(field, "")) != str(cutover.get(field, "")):
                blockers.append(f"assurance_result_{field}_mismatch:{index}")
        if _first_text(result, "status") != "passed":
            blockers.append(f"assurance_result_status_not_passed:{index}")
        if result.get("passed") is not True:
            blockers.append(f"assurance_result_passed_not_true:{index}")
    return blockers


def validate_authoritative_rich_cutover_execution_context(
    snapshot: Mapping[str, object],
    *,
    integration_resolution: Mapping[str, object],
    evidence_catalog: EvidenceCatalog | None,
) -> list[str]:
    """Re-resolve the exact required cutover matrix at every execution gate.

    The execution-eligibility gate and outer execution surface share this
    helper so neither can drift to a weaker cutover identity contract.
    """

    blockers: list[str] = []
    cutover = _mapping(snapshot.get("rich_cutover"))
    if not cutover:
        return ["authoritative_rich_cutover_required"]
    validation = validate_strategy_usage_cutover(cutover)
    blockers.extend(_prefixed_blockers("authoritative_rich_cutover", validation))
    supplied_digest = _first_text(cutover, "cutover_digest")
    digest_payload = dict(cutover)
    _ = digest_payload.pop("cutover_digest", None)
    _ = digest_payload.pop("checksum", None)
    if not _is_sha256_digest(supplied_digest) or supplied_digest != canonical_digest(
        digest_payload
    ):
        blockers.append("authoritative_rich_cutover_digest_mismatch")
    if supplied_digest != _first_text(snapshot, "rich_cutover_digest"):
        blockers.append("authoritative_snapshot_rich_cutover_digest_mismatch")

    effective_at = _parse_timestamp(_first_text(cutover, "effective_at"))
    if effective_at is None or effective_at.tzinfo is None:
        blockers.append("authoritative_rich_cutover_effective_at_invalid")
    elif effective_at > datetime.now(UTC):
        blockers.append("authoritative_rich_cutover_not_yet_effective")

    reports = _mapping(integration_resolution.get("resolution_reports"))
    binding = _mapping(_mapping(reports.get("binding")).get("payload"))
    for cutover_field, binding_field in (
        ("strategy_family_id", "strategy_family_id"),
        ("strategy_id", "strategy_id"),
        ("action_space_ref", "action_space_ref"),
        ("action_space_digest", "action_space_digest"),
        ("action_space_version", "action_space_version"),
        ("adapter_ref", "execution_adapter_ref"),
        ("adapter_digest", "adapter_digest"),
        ("baseline_artifact_ref", "baseline_artifact_ref"),
        ("baseline_digest", "baseline_digest"),
    ):
        if _first_text(cutover, cutover_field) != _first_text(binding, binding_field):
            blockers.append(f"rich_cutover_binding_{cutover_field}_mismatch")

    resolved: dict[str, Mapping[str, object]] = {}
    for label, ref_field, digest_field, artifact_type in (
        (
            "action_space",
            "action_space_ref",
            "action_space_digest",
            "strategy_factor_action_space",
        ),
        (
            "adapter",
            "adapter_ref",
            "adapter_digest",
            "strategy_factor_execution_adapter",
        ),
        (
            "baseline",
            "baseline_artifact_ref",
            "baseline_digest",
            "strategy_baseline",
        ),
    ):
        report = resolve_governance_artifact(
            cutover.get(ref_field),
            evidence_catalog=evidence_catalog,
            expected_artifact_type=artifact_type,
            expected_digest=_first_text(cutover, digest_field) or None,
        )
        blockers.extend(_prefixed_blockers(f"rich_cutover_{label}", report))
        resolved[label] = _mapping(report.get("payload"))
    action_space = resolved.get("action_space", {})
    if _first_text(binding, "action_id") not in set(
        _strings(action_space.get("action_ids"))
    ):
        blockers.append("rich_cutover_binding_action_not_in_action_space")
    adapter = resolved.get("adapter", {})
    if _first_text(binding, "action_id") not in set(
        _strings(adapter.get("supported_action_ids"))
    ):
        blockers.append("rich_cutover_binding_action_not_supported_by_adapter")
    for label in ("adapter", "baseline"):
        payload = resolved.get(label, {})
        expected_schema_id = (
            "strategy_factor_execution_adapter@1.0"
            if label == "adapter"
            else "strategy_baseline@1.0"
        )
        if _first_text(payload, "schema_id") != expected_schema_id:
            blockers.append(f"rich_cutover_{label}_schema_id_mismatch")
        if _first_text(payload, "canonicalization_version") != (
            CANONICALIZATION_VERSION
        ):
            blockers.append(f"rich_cutover_{label}_canonicalization_version_mismatch")
        identity_fields = [
            "strategy_family_id",
            "strategy_id",
            "action_space_ref",
            "action_space_version",
        ]
        if label == "adapter":
            identity_fields.append("action_space_digest")
        for field in identity_fields:
            if _first_text(payload, field) != _first_text(cutover, field):
                blockers.append(f"rich_cutover_{label}_{field}_mismatch")
    for field in ("baseline_artifact_ref", "baseline_digest"):
        if _first_text(adapter, field) != _first_text(cutover, field):
            blockers.append(f"rich_cutover_adapter_{field}_mismatch")

    authorization_ref = _first_text(snapshot, "required_authorization_ref")
    authorization_digest = _first_text(snapshot, "required_authorization_digest")
    if not _is_sha256_digest(authorization_digest):
        blockers.append("rich_cutover_authorization_digest_required")
    authorization_report = resolve_governance_artifact(
        authorization_ref,
        evidence_catalog=evidence_catalog,
        expected_artifact_type="manual_authorization_decision",
        expected_digest=authorization_digest or None,
    )
    blockers.extend(
        _prefixed_blockers("rich_cutover_authorization", authorization_report)
    )
    authorization = _mapping(authorization_report.get("payload"))
    # This structural call is intentionally shared with every other manual
    # authorization consumer; owner/cutover identity remains context-specific.
    blockers.extend(
        f"rich_cutover_authorization:{item}"
        for item in validate_manual_authorization_decision(authorization)
    )
    for field, expected in (
        ("strategy_id", _first_text(cutover, "strategy_id")),
        ("owner", _first_text(cutover, "owner")),
        ("cutover_digest", supplied_digest),
        ("change_id", _first_text(cutover, "change_id")),
        ("mode", "required"),
        ("version", cutover.get("version", "")),
    ):
        if str(authorization.get(field, "")) != str(expected):
            blockers.append(f"rich_cutover_authorization_{field}_mismatch")

    ledger_records = _sequence(snapshot.get("required_assurance_records"))
    expected_records = {
        ref: kind
        for kind, field in (("evidence", "evidence_refs"), ("test", "test_refs"))
        for ref in _strings(cutover.get(field))
    }
    actual_records: dict[str, tuple[str, str]] = {}
    for index, item in enumerate(ledger_records):
        record = _mapping(item)
        ref = _first_text(record, "ref")
        digest = _first_text(record, "digest")
        kind = _first_text(record, "kind")
        if not ref or ref in actual_records:
            blockers.append(f"rich_cutover_assurance_ledger_ref_invalid:{index}")
            continue
        actual_records[ref] = (digest, kind)
    if set(actual_records) != set(expected_records):
        blockers.append("rich_cutover_assurance_ledger_refs_mismatch")
    for index, (ref, expected_kind) in enumerate(expected_records.items()):
        digest, kind = actual_records.get(ref, ("", ""))
        if not _is_sha256_digest(digest):
            blockers.append(f"rich_cutover_assurance_ledger_digest_invalid:{index}")
        if kind != expected_kind:
            blockers.append(f"rich_cutover_assurance_ledger_kind_mismatch:{index}")
        report = resolve_governance_artifact(
            ref,
            evidence_catalog=evidence_catalog,
            expected_artifact_type=(
                "strategy_usage_cutover_evidence"
                if expected_kind == "evidence"
                else "strategy_usage_cutover_test"
            ),
            expected_digest=digest or None,
        )
        blockers.extend(_prefixed_blockers(f"rich_cutover_assurance:{index}", report))
        blockers.extend(
            f"rich_cutover_assurance:{index}:{item}"
            for item in validate_strategy_usage_cutover_assurance(
                _mapping(report.get("payload")),
                cutover=cutover,
                expected_kind=expected_kind,
                evidence_catalog=evidence_catalog,
            )
        )
    return blockers


def evaluate_strategy_usage_execution_eligibility(
    *,
    cutover: Mapping[str, object] | None,
    integration_claim: Mapping[str, object] | None,
    integration_claim_ref: str | None = None,
    governance_repository: TemporalGovernanceRepository | None = None,
    admitted_factor_loader: Callable[[str], Mapping[str, object]] | None = None,
    production_authorization_loader: (
        Callable[[str], Mapping[str, object]] | None
    ) = None,
    execution_evidence_refs: Sequence[str] = (),
    evidence_catalog: EvidenceCatalog | None = None,
    production_authorization_ref: str | None = None,
    revocation_ref: str | None = None,
) -> dict[str, object]:
    """Gate strategy-use execution with resolver-backed evidence in v2 modes."""

    blockers: list[str] = []
    if cutover is None:
        return _execution_blocked("usage_discovery_cutover_required")
    mode = str(cutover.get("mode"))
    cutover_has_required_history = cutover.get("required_history") is True
    if mode == "required" or cutover_has_required_history:
        if governance_repository is None:
            blockers.append("authoritative_cutover_repository_required")
            transition: Mapping[str, object] = {}
        else:
            strategy_id = _first_text(cutover, "strategy_id")
            live_cutover = governance_repository.get_strategy_usage_cutover_snapshot(
                strategy_id
            )
            transitions = governance_repository.get_strategy_usage_cutover_transitions(
                strategy_id
            )
            transition = transitions[-1] if transitions else {}
            if dict(cutover) != dict(live_cutover):
                blockers.append("caller_cutover_not_authoritative_repository_snapshot")
            cutover = live_cutover
        transition_digest_payload = dict(transition)
        supplied_transition_digest = str(
            transition_digest_payload.pop("receipt_digest", "")
        )
        if supplied_transition_digest != canonical_digest(transition_digest_payload):
            blockers.append("authoritative_cutover_transition_digest_mismatch")
        version = int(str(cutover.get("version", 0)))
        if (
            version < (2 if mode == "required" else 3)
            or cutover.get("required_history") is not True
            or _first_text(cutover, "latest_transition_id")
            != _first_text(transition, "transition_id")
            or _first_text(transition, "next_state") != mode
            or int(str(transition.get("expected_prior_version", -1))) + 1 != version
        ):
            blockers.append("authoritative_required_cutover_snapshot_mismatch")
        if mode == "shadow_audit" and (
            _first_text(transition, "expected_prior_state") != "required"
            or not _first_text(transition, "rollback_snapshot_ref")
        ):
            blockers.append("authoritative_rollback_transition_required")
    else:
        cutover_report = validate_usage_discovery_cutover(cutover)
        if cutover_report["status"] != "valid":
            return _execution_blocked(*_strings(cutover_report["blockers"]))
    if integration_claim is None:
        return _execution_blocked("strategy_integration_claim_required")
    claim_report = validate_strategy_integration_claim(integration_claim)
    if claim_report["status"] != "valid":
        return _execution_blocked(*_strings(claim_report["blockers"]))
    if str(cutover.get("strategy_id")) != str(integration_claim.get("strategy_id")):
        blockers.append("execution_claim_strategy_id_mismatch")
    claim_id = str(integration_claim.get("claim_id"))
    # Authorized IDs are the rollback preservation allowlist.  While the live
    # mode is still ``required`` the same claim is a newly eligible strict-path
    # claim, not a legacy/preserved execution.
    preserved = mode != "required" and claim_id in set(
        _strings(cutover.get("authorized_claim_ids"))
    )
    required_history = bool(cutover.get("required_history")) or mode == "required"
    strict_path = required_history or bool(integration_claim_ref)
    integration_resolution: dict[str, object] = {}
    execution_reports: list[dict[str, object]] = []
    if strict_path:
        if not integration_claim_ref:
            blockers.append("resolver_backed_integration_claim_ref_required")
        else:
            integration_resolution = resolve_strategy_integration_claim(
                claim_ref=integration_claim_ref,
                evidence_catalog=evidence_catalog,
                admitted_factor_loader=admitted_factor_loader,
                governance_repository=governance_repository,
                require_authoritative_claim=True,
            )
            blockers.extend(_prefixed_blockers("integration", integration_resolution))
            if integration_resolution.get("status") != "resolved":
                blockers.append("resolver_backed_integration_receipt_required")
            resolution_reports = _mapping(
                integration_resolution.get("resolution_reports")
            )
            resolved_claim_report = _mapping(resolution_reports.get("claim"))
            resolved_claim = _mapping(resolved_claim_report.get("payload"))
            for field in (
                "claim_id",
                "claim_digest",
                "strategy_id",
                "candidate_fingerprint",
            ):
                if str(resolved_claim.get(field, "")) != str(
                    integration_claim.get(field, "")
                ):
                    blockers.append(f"integration_claim_body_ref_{field}_mismatch")
            blockers.extend(
                validate_authoritative_rich_cutover_execution_context(
                    cutover,
                    integration_resolution=integration_resolution,
                    evidence_catalog=evidence_catalog,
                )
            )
        if not execution_evidence_refs:
            blockers.append("resolver_backed_execution_evidence_required")
        for index, ref in enumerate(execution_evidence_refs):
            report = resolve_governance_artifact(
                ref,
                evidence_catalog=evidence_catalog,
                expected_artifact_type="strategy_execution_evidence",
                expected_candidate_fingerprint=str(
                    integration_resolution.get("candidate_fingerprint", "")
                ),
            )
            execution_reports.append(report)
            blockers.extend(_prefixed_blockers(f"execution:{index}", report))
            payload = _mapping(report.get("payload"))
            if payload.get("execution_eligible") is not True:
                blockers.append(f"execution_evidence_not_eligible:{index}")
            if (
                integration_claim_ref
                and _first_text(payload, "integration_claim_ref")
                != integration_claim_ref
            ):
                blockers.append(f"execution_claim_ref_mismatch:{index}")
            binding_ref = _first_text(integration_resolution, "binding_ref")
            if binding_ref and _first_text(payload, "binding_ref") != binding_ref:
                blockers.append(f"execution_binding_ref_mismatch:{index}")
            for field in ("action_id", "usage_signature_hash"):
                expected = _first_text(integration_resolution, field)
                if expected and _first_text(payload, field) != expected:
                    blockers.append(f"execution_{field}_mismatch:{index}")

    new_eligible = mode == "required" and strict_path and not blockers
    prior_execution_receipt_ref = ""
    prior_execution_receipt_digest = ""
    preserved_authorization_ref = ""
    preserved_authorization_digest = ""
    prior_required_cutover_version: object = ""
    prior_rich_cutover_digest = ""
    prior_required_transition_digest = ""
    if preserved and mode != "required":
        if not bool(cutover.get("required_history")):
            blockers.append("preserved_v2_claim_without_required_history")
        snapshot_report = resolve_governance_artifact(
            cutover.get("rollback_snapshot_ref"),
            evidence_catalog=evidence_catalog,
            expected_artifact_type="strategy_usage_required_snapshot",
            expected_digest=_first_text(cutover, "rollback_snapshot_digest") or None,
            expected_candidate_fingerprint=str(
                integration_resolution.get("candidate_fingerprint", "")
            )
            or None,
        )
        blockers.extend(_prefixed_blockers("rollback_snapshot", snapshot_report))
        snapshot = _mapping(snapshot_report.get("payload"))
        snapshot_entries = [
            _mapping(item)
            for item in _sequence(snapshot.get("authorized_claims"))
            if _first_text(_mapping(item), "claim_id") == claim_id
        ]
        if len(snapshot_entries) != 1:
            blockers.append("preserved_claim_snapshot_entry_required")
        else:
            snapshot_entry = snapshot_entries[0]
            prior_execution_receipt_ref = _first_text(
                snapshot_entry, "prior_execution_receipt_ref"
            )
            prior_execution_receipt_digest = _first_text(
                snapshot_entry, "prior_execution_receipt_digest"
            )
            preserved_authorization_ref = _first_text(
                snapshot_entry, "production_authorization_ref"
            )
            preserved_authorization_digest = _first_text(
                snapshot_entry, "production_authorization_digest"
            )
            prior_required_cutover_version = snapshot_entry.get(
                "prior_required_cutover_version", ""
            )
            prior_rich_cutover_digest = _first_text(
                snapshot_entry, "prior_rich_cutover_digest"
            )
            prior_required_transition_digest = _first_text(
                snapshot_entry, "prior_required_transition_digest"
            )
            prior_execution_report = resolve_governance_artifact(
                prior_execution_receipt_ref,
                evidence_catalog=evidence_catalog,
                expected_artifact_type="strategy_usage_execution_receipt",
                expected_digest=prior_execution_receipt_digest or None,
                expected_candidate_fingerprint=str(
                    integration_resolution.get("candidate_fingerprint", "")
                )
                or None,
            )
            blockers.extend(
                _prefixed_blockers("prior_execution_receipt", prior_execution_report)
            )
            prior_execution = _mapping(prior_execution_report.get("payload"))
            if (
                prior_execution.get("status") != "eligible"
                or prior_execution.get("execution_eligible") is not True
            ):
                blockers.append("prior_execution_receipt_not_eligible")
            if prior_execution.get("mode") != "required":
                blockers.append("prior_execution_receipt_not_required_mode")
            for field, expected in (
                ("strategy_id", integration_resolution.get("strategy_id")),
                ("integration_claim_ref", integration_claim_ref),
                ("binding_ref", integration_resolution.get("binding_ref")),
                (
                    "candidate_fingerprint",
                    integration_resolution.get("candidate_fingerprint"),
                ),
                ("cutover_version", prior_required_cutover_version),
                ("cutover_digest", prior_rich_cutover_digest),
                (
                    "cutover_transition_digest",
                    prior_required_transition_digest,
                ),
            ):
                if str(prior_execution.get(field, "")) != str(expected or ""):
                    blockers.append(f"prior_execution_receipt_{field}_mismatch")
        if production_authorization_ref != preserved_authorization_ref:
            blockers.append("preserved_authorization_ref_snapshot_mismatch")
        if production_authorization_loader is None or not production_authorization_ref:
            blockers.append("authoritative_production_authorization_loader_required")
            authoritative_authorization: Mapping[str, object] = {}
        else:
            try:
                authoritative_authorization = production_authorization_loader(
                    production_authorization_ref
                )
            except Exception as exc:
                blockers.append(
                    "authoritative_production_authorization_not_resolved:"
                    + type(exc).__name__
                )
                authoritative_authorization = {}
        authorization_report = resolve_governance_artifact(
            production_authorization_ref,
            evidence_catalog=(
                {str(production_authorization_ref): authoritative_authorization}
                if authoritative_authorization
                else None
            ),
            expected_artifact_type="project_production_authorization",
            expected_digest=preserved_authorization_digest or None,
            expected_candidate_fingerprint=str(
                integration_resolution.get("candidate_fingerprint", "")
            ),
        )
        blockers.extend(_prefixed_blockers("authorization", authorization_report))
        authorization = _mapping(authorization_report.get("payload"))
        if authorization.get("production_authority") is not True:
            blockers.append("preserved_claim_real_authorization_required")
        if authorization.get("revoked") is not False:
            blockers.append("preserved_claim_unrevoked_authorization_required")
        for field, expected in (
            ("strategy_id", integration_resolution.get("strategy_id")),
            ("claim_ref", integration_claim_ref),
            ("binding_ref", integration_resolution.get("binding_ref")),
            ("cutover_version", prior_required_cutover_version),
            ("cutover_digest", prior_rich_cutover_digest),
            (
                "cutover_transition_digest",
                prior_required_transition_digest,
            ),
        ):
            if str(authorization.get(field, "")) != str(expected or ""):
                blockers.append(f"preserved_authorization_{field}_mismatch")
        if revocation_ref:
            blockers.append("caller_supplied_revocation_ref_not_authoritative")
    if not preserved and not new_eligible:
        blockers.append("usage_discovery_cutover_does_not_allow_new_execution")
    eligible = not blockers
    receipt: dict[str, object] = {
        "artifact_type": "strategy_usage_execution_receipt",
        "strategy_family": _first_text(
            _mapping(integration_resolution), "strategy_family"
        ),
        "strategy_id": str(integration_claim.get("strategy_id", "")),
        "candidate_fingerprint": str(
            integration_claim.get("candidate_fingerprint", "")
        ),
        "admitted_factor_ref": _first_text(
            _mapping(integration_resolution), "admitted_factor_ref"
        ),
        "integration_claim_ref": integration_claim_ref or "",
        "binding_ref": _first_text(_mapping(integration_resolution), "binding_ref"),
        "action_id": _first_text(_mapping(integration_resolution), "action_id"),
        "usage_signature_hash": _first_text(
            _mapping(integration_resolution), "usage_signature_hash"
        ),
        "status": "eligible" if eligible else "blocked",
        "execution_eligible": eligible,
        "production_authority": False,
        "mode": mode,
        "preserved_authorized_claim": preserved,
        "cutover_version": cutover.get("version", 0),
        "cutover_digest": _first_text(cutover, "rich_cutover_digest", "cutover_digest"),
        "cutover_transition_digest": _first_text(cutover, "latest_transition_digest"),
        "prior_execution_receipt_ref": prior_execution_receipt_ref,
        "prior_execution_receipt_digest": prior_execution_receipt_digest,
        "preserved_production_authorization_ref": preserved_authorization_ref,
        "preserved_production_authorization_digest": preserved_authorization_digest,
        "integration_resolution": integration_resolution,
        "execution_evidence": execution_reports,
        "blockers": sorted(set(blockers)),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    receipt["checksum"] = receipt["receipt_digest"]
    return receipt


def _execution_blocked(*blockers: str) -> dict[str, object]:
    return {
        "artifact_type": "strategy_usage_execution_eligibility",
        "status": "blocked",
        "execution_eligible": False,
        "production_authority": False,
        "mode": "missing",
        "preserved_authorized_claim": False,
        "blockers": list(blockers),
    }


def _cutover_transition_blockers(
    prior_cutover: Mapping[str, object], new_mode: str
) -> list[str]:
    prior_mode = str(prior_cutover.get("mode"))
    allowed = {
        "legacy_read": {"legacy_read", "shadow_audit"},
        "shadow_audit": {"shadow_audit", "required"},
        "required": {"required", "shadow_audit"},
    }
    if new_mode not in allowed.get(prior_mode, set()):
        return ["invalid_usage_discovery_cutover_transition"]
    return []


def _seal_artifact(
    payload: dict[str, object],
    validator: Callable[[Mapping[str, object]], dict[str, object]],
    *,
    digest_field: str,
) -> dict[str, object]:
    """Seal one immutable rich artifact with one canonical semantic digest."""

    digest = canonical_digest(payload)
    payload[digest_field] = digest
    # ``checksum`` remains an exact alias for generic resolver compatibility;
    # it never changes the semantic digest payload.
    payload["checksum"] = digest
    final_report = validator(payload)
    if final_report["status"] != "valid":
        raise ValueError("; ".join(_strings(final_report["blockers"])))
    return payload


def _validation_report(
    payload: Mapping[str, object], schema_id: str, blockers: list[str]
) -> dict[str, object]:
    expected_artifact_type = {
        FROZEN_BINDING_SCHEMA_ID: "frozen_strategy_factor_binding",
        INTEGRATION_EVIDENCE_SCHEMA_ID: "strategy_integration_evidence",
        INTEGRATION_REVIEW_SCHEMA_ID: "strategy_integration_review_package",
        INTEGRATION_CLAIM_SCHEMA_ID: "strategy_integration_claim",
        INTEGRATION_REVIEW_EVENT_SCHEMA_ID: "strategy_integration_review_event",
        INTEGRATION_DECISION_EVENT_SCHEMA_ID: "strategy_integration_decision_event",
        INTEGRATION_METRIC_CONTRACT_SCHEMA_ID: ("strategy_integration_metric_contract"),
        INTEGRATION_NO_HARM_CONTRACT_SCHEMA_ID: (
            "strategy_integration_no_harm_contract"
        ),
        USAGE_DISCOVERY_CUTOVER_SCHEMA_ID: "usage_discovery_cutover",
        STRATEGY_USAGE_CUTOVER_SCHEMA_ID: "strategy_usage_cutover",
    }.get(schema_id, "")
    if str(payload.get("artifact_type")) != expected_artifact_type:
        blockers.append("artifact_type_invalid")
    if str(payload.get("schema_id")) != schema_id:
        blockers.append("schema_id_invalid")
    if (
        schema_id
        in {
            FROZEN_BINDING_SCHEMA_ID,
            INTEGRATION_EVIDENCE_SCHEMA_ID,
            INTEGRATION_REVIEW_SCHEMA_ID,
            INTEGRATION_CLAIM_SCHEMA_ID,
            INTEGRATION_REVIEW_EVENT_SCHEMA_ID,
            INTEGRATION_DECISION_EVENT_SCHEMA_ID,
            INTEGRATION_METRIC_CONTRACT_SCHEMA_ID,
            INTEGRATION_NO_HARM_CONTRACT_SCHEMA_ID,
            STRATEGY_USAGE_CUTOVER_SCHEMA_ID,
        }
        and _first_text(payload, "canonicalization_version") != CANONICALIZATION_VERSION
    ):
        blockers.append("canonicalization_version_invalid")
    digest_field = {
        FROZEN_BINDING_SCHEMA_ID: "binding_digest",
        INTEGRATION_EVIDENCE_SCHEMA_ID: "evidence_digest",
        INTEGRATION_REVIEW_SCHEMA_ID: "package_digest",
        INTEGRATION_CLAIM_SCHEMA_ID: "claim_digest",
        INTEGRATION_REVIEW_EVENT_SCHEMA_ID: "event_digest",
        INTEGRATION_DECISION_EVENT_SCHEMA_ID: "event_digest",
        INTEGRATION_METRIC_CONTRACT_SCHEMA_ID: "contract_digest",
        INTEGRATION_NO_HARM_CONTRACT_SCHEMA_ID: "contract_digest",
        STRATEGY_USAGE_CUTOVER_SCHEMA_ID: "cutover_digest",
    }.get(schema_id, "")
    recorded_digest = _first_text(payload, digest_field) if digest_field else ""
    if digest_field and not _is_sha256_digest(recorded_digest):
        blockers.append(f"{digest_field}_required")
    if recorded_digest:
        digest_payload = dict(payload)
        _ = digest_payload.pop(digest_field, None)
        _ = digest_payload.pop("checksum", None)
        if recorded_digest != canonical_digest(digest_payload):
            blockers.append(f"{digest_field}_mismatch")
    checksum = str(payload.get("checksum", ""))
    if digest_field and not _is_sha256_digest(checksum):
        blockers.append("checksum_required")
    if digest_field and checksum and checksum != recorded_digest:
        blockers.append("checksum_digest_alias_mismatch")
    if checksum:
        checksum_payload = dict(payload)
        _ = checksum_payload.pop("checksum", None)
        if digest_field:
            _ = checksum_payload.pop(digest_field, None)
        if checksum != canonical_digest(checksum_payload):
            blockers.append("checksum_mismatch")
    return {
        "artifact_type": "factor_usage_integration_validation",
        "schema_id": schema_id,
        "status": "blocked" if blockers else "valid",
        "blockers": blockers,
    }


def _required_text_blockers(payload: Mapping[str, object], *keys: str) -> list[str]:
    return [f"{key}_required" for key in keys if not str(payload.get(key, "")).strip()]


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


__all__ = [
    "FROZEN_BINDING_SCHEMA_ID",
    "INTEGRATION_CLAIM_SCHEMA_ID",
    "INTEGRATION_DECISION_EVENT_SCHEMA_ID",
    "INTEGRATION_EVIDENCE_SCHEMA_ID",
    "INTEGRATION_METRIC_CONTRACT_SCHEMA_ID",
    "INTEGRATION_NO_HARM_CONTRACT_SCHEMA_ID",
    "INTEGRATION_REVIEW_SCHEMA_ID",
    "INTEGRATION_REVIEW_EVENT_SCHEMA_ID",
    "STRATEGY_USAGE_CUTOVER_SCHEMA_ID",
    "USAGE_DISCOVERY_CUTOVER_SCHEMA_ID",
    "build_frozen_strategy_factor_binding",
    "build_legacy_usage_discovery_cutover_compatibility",
    "build_strategy_integration_claim",
    "build_strategy_integration_decision_event",
    "build_strategy_integration_evidence",
    "build_strategy_integration_result_contract",
    "build_strategy_integration_review_event",
    "build_strategy_integration_review_package",
    "build_strategy_usage_cutover",
    "build_strategy_usage_cutover_transition_receipt",
    "build_usage_discovery_cutover",
    "evaluate_strategy_usage_execution_eligibility",
    "resolve_factor_usage_campaign_dependencies",
    "resolve_governance_artifact",
    "resolve_strategy_integration_claim",
    "resolve_usage_integration_evidence",
    "validate_frozen_strategy_factor_binding",
    "validate_strategy_integration_claim",
    "validate_strategy_integration_decision_event",
    "validate_strategy_integration_evidence",
    "validate_strategy_integration_result_contract",
    "validate_strategy_integration_review_event",
    "validate_strategy_integration_review_package",
    "validate_strategy_usage_cutover",
    "validate_strategy_usage_cutover_assurance",
    "validate_authoritative_rich_cutover_execution_context",
    "validate_usage_discovery_cutover",
]
