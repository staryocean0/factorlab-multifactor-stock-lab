"""Evidence reference resolution for promotion-capable governance gates."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast
from urllib.parse import ParseResult, urlparse

ACCEPTED_EVIDENCE_REF_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "artifact",
        "runtime",
        "dataset",
        "candidate_asset",
        "ledger",
        "approval",
    }
)

EvidenceCatalog = Mapping[str, Mapping[str, object]]
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")


def resolve_evidence_ref(
    evidence_ref: object,
    *,
    catalog: EvidenceCatalog | None = None,
    expected_artifact_type: str | None = None,
    expected_schema_id: str | None = None,
    expected_candidate_fingerprint: str | None = None,
    expected_dataset_ref: str | None = None,
    expected_source_vintage_ref: str | None = None,
) -> dict[str, object]:
    """Resolve and validate an evidence ref.

    The resolver deliberately treats a bare string as insufficient. Promotion
    paths must provide cataloged or file-backed artifact metadata so schema,
    checksum, fingerprint, and lineage can be checked deterministically.
    """

    ref = str(evidence_ref or "").strip()
    blockers: list[str] = []
    warnings: list[str] = []
    if not ref:
        blockers.append("evidence_ref_missing")
        return _blocked_result(ref, blockers, warnings)

    parsed = urlparse(ref)
    if not parsed.scheme:
        blockers.append("evidence_ref_scheme_missing")
        return _blocked_result(ref, blockers, warnings)
    if parsed.scheme not in ACCEPTED_EVIDENCE_REF_SCHEMES:
        blockers.append("unknown_evidence_ref_scheme")
        return _blocked_result(ref, blockers, warnings)
    if "://" not in ref:
        blockers.append("legacy_evidence_ref_shorthand_not_allowed_for_at5")
        return _blocked_result(ref, blockers, warnings)

    catalog_entry = _catalog_entry(ref, parsed, catalog)
    file_payload = _file_payload(parsed)
    if catalog_entry is None and file_payload is None:
        blockers.append("evidence_artifact_not_resolved")
        return _blocked_result(ref, blockers, warnings)

    payload: dict[str, object] = {}
    if file_payload is not None:
        payload.update(file_payload)
    if catalog_entry is not None:
        if file_payload is None:
            payload.update(dict(catalog_entry))
        else:
            for field, value in catalog_entry.items():
                if field in {"checksum", "sha256", "path", "resolved_path_or_uri"}:
                    payload[field] = value
                elif field not in file_payload or file_payload.get(field) != value:
                    blockers.append("file_catalog_semantic_payload_mismatch")

    artifact_type = _string(payload.get("artifact_type"))
    schema_id = _string(payload.get("schema_id"))
    schema_version = _string(payload.get("schema_version"))
    resolved_path_or_uri = _string(
        payload.get("resolved_path_or_uri") or payload.get("path") or ref
    )

    checksum_status = _checksum_status(
        payload,
        parsed,
        file_backed=file_payload is not None,
    )
    fingerprint_status = _fingerprint_status(payload, expected_candidate_fingerprint)
    lineage_status = _lineage_status(
        payload,
        expected_dataset_ref=expected_dataset_ref,
        expected_source_vintage_ref=expected_source_vintage_ref,
    )

    if expected_artifact_type and artifact_type != expected_artifact_type:
        blockers.append("artifact_type_mismatch")
    if expected_schema_id and schema_id != expected_schema_id:
        blockers.append("schema_id_mismatch")
    if checksum_status != "passed":
        blockers.append(f"checksum_{checksum_status}")
    if fingerprint_status != "passed":
        blockers.append(f"fingerprint_{fingerprint_status}")
    if lineage_status != "passed":
        blockers.append(f"lineage_{lineage_status}")
    if artifact_type == "manual_authorization_decision":
        blockers.extend(validate_manual_authorization_decision(payload))

    canonical_digest = _canonical_digest(payload)
    return {
        "status": "blocked" if blockers else "resolved",
        "evidence_ref": ref,
        "artifact_type": artifact_type,
        "schema_id": schema_id,
        "schema_version": schema_version,
        "checksum_status": checksum_status,
        "fingerprint_status": fingerprint_status,
        "lineage_status": lineage_status,
        "resolved_path_or_uri": resolved_path_or_uri,
        "blockers": blockers,
        "warnings": warnings,
        "canonical_digest": canonical_digest,
        "payload": payload,
    }


def resolve_evidence_refs(
    evidence_refs: Mapping[str, object],
    *,
    catalog: EvidenceCatalog | None = None,
    expected_artifact_types: Mapping[str, str] | None = None,
    expected_candidate_fingerprint: str | None = None,
    expected_dataset_ref: str | None = None,
    expected_source_vintage_ref: str | None = None,
) -> dict[str, dict[str, object]]:
    """Resolve a mapping of named evidence refs."""

    artifact_types = expected_artifact_types or {}
    return {
        field_name: resolve_evidence_ref(
            evidence_ref,
            catalog=catalog,
            expected_artifact_type=artifact_types.get(field_name),
            expected_candidate_fingerprint=expected_candidate_fingerprint,
            expected_dataset_ref=expected_dataset_ref,
            expected_source_vintage_ref=expected_source_vintage_ref,
        )
        for field_name, evidence_ref in evidence_refs.items()
    }


def _blocked_result(
    evidence_ref: str, blockers: list[str], warnings: list[str]
) -> dict[str, object]:
    return {
        "status": "blocked",
        "evidence_ref": evidence_ref,
        "artifact_type": "",
        "schema_id": "",
        "schema_version": "",
        "checksum_status": "not_checked",
        "fingerprint_status": "not_checked",
        "lineage_status": "not_checked",
        "resolved_path_or_uri": "",
        "blockers": blockers,
        "warnings": warnings,
        "canonical_digest": "",
        "payload": {},
    }


def _catalog_entry(
    ref: str,
    parsed_ref: ParseResult,
    catalog: EvidenceCatalog | None,
) -> Mapping[str, object] | None:
    if catalog is None:
        return None
    ref_key = _ref_key(parsed_ref)
    return catalog.get(ref) or catalog.get(ref_key)


def _ref_key(parsed_ref: ParseResult) -> str:
    if parsed_ref.netloc and parsed_ref.path:
        return f"{parsed_ref.netloc}{parsed_ref.path}"
    if parsed_ref.netloc:
        return parsed_ref.netloc
    return parsed_ref.path.lstrip("/")


def _file_payload(parsed_ref: ParseResult) -> dict[str, object] | None:
    if parsed_ref.scheme != "artifact":
        return None
    path = Path(parsed_ref.path)
    if not path.is_file():
        return None
    payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        return None
    raw_payload = cast(Mapping[object, object], payload)
    return {str(key): value for key, value in raw_payload.items()}


def _checksum_status(
    payload: Mapping[str, object],
    parsed_ref: ParseResult,
    *,
    file_backed: bool,
) -> str:
    expected = _string(payload.get("checksum") or payload.get("sha256"))
    if not expected:
        return "missing"
    if _SHA256_RE.fullmatch(expected) is None:
        return "malformed"
    # File-byte integrity is available only when this exact artifact ref was
    # resolved from disk.  A catalog entry cannot redirect verification to an
    # unrelated existing file by self-declaring ``path``.
    path_text = parsed_ref.path if file_backed else ""
    path = Path(path_text)
    if file_backed and path_text and path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return "passed" if digest == expected.removeprefix("sha256:") else "mismatch"
    canonical = _canonical_payload_digest(payload)
    if expected == canonical:
        return "passed"
    # Rich governance artifacts expose their semantic digest twice: under a
    # typed field (for example ``binding_digest``) and ``checksum`` (generic
    # resolver compatibility). Recompute with that typed digest field removed
    # rather than trusting either self-declared value.
    for field, value in payload.items():
        if (
            field not in {"checksum", "sha256", "computed_checksum"}
            and (field.endswith("_digest") or field.endswith("_checksum"))
            and _string(value) == expected
        ):
            semantic_payload = dict(payload)
            _ = semantic_payload.pop(field, None)
            if expected == _canonical_payload_digest(semantic_payload):
                return "passed"
    return "unverified"


def _fingerprint_status(
    payload: Mapping[str, object],
    expected_candidate_fingerprint: str | None,
) -> str:
    expected = _string(expected_candidate_fingerprint)
    if not expected:
        return "passed"
    actual = _string(payload.get("candidate_fingerprint"))
    if not actual:
        return "missing"
    return "passed" if actual == expected else "mismatch"


def _lineage_status(
    payload: Mapping[str, object],
    *,
    expected_dataset_ref: str | None,
    expected_source_vintage_ref: str | None,
) -> str:
    expected_dataset = _string(expected_dataset_ref)
    expected_vintage = _string(expected_source_vintage_ref)
    if expected_dataset:
        actual_dataset = _string(payload.get("dataset_ref"))
        if not actual_dataset:
            return "missing"
        if actual_dataset != expected_dataset:
            return "mismatch"
    if expected_vintage:
        actual_vintage = _string(payload.get("source_vintage_ref"))
        if not actual_vintage:
            return "missing"
        if actual_vintage != expected_vintage:
            return "mismatch"
    return "passed"


def validate_manual_authorization_decision(
    payload: Mapping[str, object],
) -> list[str]:
    """Validate an immutable manual decision independently of ref scheme.

    A decision is an identity-bearing authorization contract.  Its checksum
    must therefore be a full canonical SHA-256 digest of the semantic payload;
    a caller-supplied ``computed_checksum`` is deliberately ignored.  This
    validator is public so required-cutover, rollback, and final-production
    gates share one contract instead of depending on an ``approval://`` URI.
    """

    blockers: list[str] = []
    if _string(payload.get("artifact_type")) != "manual_authorization_decision":
        blockers.append("approval_artifact_type_must_be_manual_decision")
    if _string(payload.get("decision")) != "approved":
        blockers.append("approval_decision_not_approved")
    if _string(payload.get("status")) != "approved":
        blockers.append("approval_status_not_approved")
    signature_ref = _string(payload.get("signature_ref"))
    if not signature_ref:
        blockers.append("approval_decision_not_signed")
    else:
        parsed_signature = urlparse(signature_ref)
        if (
            parsed_signature.scheme != "signature"
            or "://" not in signature_ref
            or not (parsed_signature.netloc or parsed_signature.path.strip("/"))
        ):
            blockers.append("approval_signature_ref_invalid")
    immutable = (
        payload.get("immutable") is True
        or payload.get("decision_artifact_immutable") is True
    )
    if not immutable:
        blockers.append("approval_decision_not_immutable")
    expected_digest = _string(payload.get("checksum") or payload.get("sha256"))
    if (
        _SHA256_RE.fullmatch(expected_digest) is None
        or expected_digest != _canonical_payload_digest(payload)
    ):
        blockers.append("approval_decision_integrity_contract_invalid")
    return blockers


def _canonical_digest(payload: Mapping[str, object]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _canonical_payload_digest(payload: Mapping[str, object]) -> str:
    semantic_payload = dict(payload)
    for field in ("checksum", "sha256", "computed_checksum", "resolved_path_or_uri"):
        _ = semantic_payload.pop(field, None)
    return _canonical_digest(semantic_payload)


def _string(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


__all__ = [
    "ACCEPTED_EVIDENCE_REF_SCHEMES",
    "EvidenceCatalog",
    "resolve_evidence_ref",
    "resolve_evidence_refs",
    "validate_manual_authorization_decision",
]
