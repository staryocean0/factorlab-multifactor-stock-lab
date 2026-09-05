"""Selection freeze manifest creation and validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final, cast

from factor_lab.governance.evidence_resolver import (
    EvidenceCatalog,
    resolve_evidence_ref,
)
from factor_lab.governance.temporal_governance_repository import canonical_digest

CANONICALIZATION_VERSION: Final = "factorlab_canonical_json@1"
CANDIDATE_FINGERPRINT_SCHEMA_ID: Final = "strategy_usage_candidate_fingerprint@1.0"
SELECTION_FREEZE_MANIFEST_V2_SCHEMA_ID: Final = "selection_freeze_manifest@2.0"
CODE_DEFINITION_ARTIFACT_TYPE: Final = "strategy_code_definition"
CODE_DEFINITION_SCHEMA_ID: Final = "strategy_code_definition@1.0"
DATA_DEFINITION_ARTIFACT_TYPE: Final = "strategy_data_definition"
DATA_DEFINITION_SCHEMA_ID: Final = "strategy_data_definition@1.0"


def build_selection_freeze_manifest(
    *,
    strategy_family: str,
    formula: str,
    parameters: Mapping[str, object],
    gates: Mapping[str, object],
    adapter_contract_ref: str,
    code_digest: str,
    dataset_refs: Sequence[str],
    freeze_date: str,
    worktree_status: str = "clean",
    diagnostic_only: bool = False,
    refreeze_reason: str | None = None,
) -> dict[str, object]:
    """Build a freeze manifest with a stable candidate fingerprint."""

    fingerprint_payload = {
        "strategy_family": strategy_family,
        "formula": formula,
        "parameters": dict(parameters),
        "gates": dict(gates),
        "adapter_contract_ref": adapter_contract_ref,
        "code_digest": code_digest,
        "dataset_refs": list(dataset_refs),
    }
    candidate_fingerprint = canonical_digest(fingerprint_payload)
    manifest: dict[str, object] = {
        "artifact_type": "selection_freeze_manifest",
        "schema_id": "selection_freeze_manifest@1.0",
        "strategy_family": strategy_family,
        "candidate_fingerprint": candidate_fingerprint,
        "formula": formula,
        "parameters": dict(parameters),
        "gates": dict(gates),
        "adapter_contract_ref": adapter_contract_ref,
        "code_digest": code_digest,
        "dataset_refs": list(dataset_refs),
        "freeze_date": freeze_date,
        "worktree_status": worktree_status,
        "diagnostic_only": diagnostic_only,
        "refreeze_reason": refreeze_reason,
    }
    manifest["manifest_checksum"] = canonical_digest(manifest)
    return manifest


def validate_selection_freeze_manifest(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Validate checksum, fingerprint, and strict dirty-worktree semantics."""

    blockers: list[str] = []
    for key in (
        "strategy_family",
        "candidate_fingerprint",
        "formula",
        "adapter_contract_ref",
        "code_digest",
        "freeze_date",
        "manifest_checksum",
    ):
        if not str(manifest.get(key, "")).strip():
            blockers.append(f"{key}_required")
    expected_fingerprint = canonical_digest(
        {
            "strategy_family": manifest.get("strategy_family"),
            "formula": manifest.get("formula"),
            "parameters": manifest.get("parameters") or {},
            "gates": manifest.get("gates") or {},
            "adapter_contract_ref": manifest.get("adapter_contract_ref"),
            "code_digest": manifest.get("code_digest"),
            "dataset_refs": manifest.get("dataset_refs") or [],
        }
    )
    if manifest.get("candidate_fingerprint") != expected_fingerprint:
        blockers.append("candidate_fingerprint_mismatch")
    checksum_payload = dict(manifest)
    supplied_checksum = str(checksum_payload.pop("manifest_checksum", ""))
    expected_checksum = canonical_digest(checksum_payload)
    if supplied_checksum != expected_checksum:
        blockers.append("manifest_checksum_mismatch")
    if (
        str(manifest.get("worktree_status", "clean")) != "clean"
        and manifest.get("diagnostic_only") is not True
    ):
        blockers.append("strict_freeze_dirty_worktree")
    return {
        "artifact_type": "selection_freeze_manifest_validation",
        "status": "blocked" if blockers else "valid",
        "blockers": blockers,
        "candidate_fingerprint": manifest.get("candidate_fingerprint", ""),
        "expected_candidate_fingerprint": expected_fingerprint,
        "expected_manifest_checksum": expected_checksum,
    }


def build_selection_freeze_manifest_v2(
    *,
    strategy_id: str,
    candidate_definition_ref: str,
    candidate_definition_digest: str,
    usage_signature_hash: str,
    candidate_fingerprint_ref: str,
    candidate_fingerprint: str,
    action_space_ref: str,
    action_space_digest: str,
    code_digest: str,
    dataset_refs: Sequence[str],
    freeze_date: str,
    worktree_status: str = "clean",
    diagnostic_only: bool = False,
    refreeze_reason: str | None = None,
) -> dict[str, object]:
    """Freeze any strategy-owned candidate representation, not only formulas."""

    manifest: dict[str, object] = {
        "artifact_type": "selection_freeze_manifest",
        "schema_id": SELECTION_FREEZE_MANIFEST_V2_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "strategy_id": strategy_id,
        "candidate_definition_ref": candidate_definition_ref,
        "candidate_definition_digest": candidate_definition_digest,
        "usage_signature_hash": usage_signature_hash,
        "candidate_fingerprint_ref": candidate_fingerprint_ref,
        "candidate_fingerprint": candidate_fingerprint,
        "action_space_ref": action_space_ref,
        "action_space_digest": action_space_digest,
        "code_digest": code_digest,
        "dataset_refs": list(dataset_refs),
        "freeze_date": freeze_date,
        "worktree_status": worktree_status,
        "diagnostic_only": diagnostic_only,
        "refreeze_reason": refreeze_reason,
        "field_labels_zh": {
            "candidate_definition_ref": "候选定义引用",
            "usage_signature_hash": "用途语义签名",
            "candidate_fingerprint": "策略用途候选指纹",
            "freeze_date": "冻结日期",
        },
    }
    manifest["manifest_checksum"] = canonical_digest(manifest)
    return manifest


def validate_selection_freeze_manifest_v2(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Validate a non-formula selection freeze manifest fail-closed."""

    blockers: list[str] = []
    if str(manifest.get("artifact_type")) != "selection_freeze_manifest":
        blockers.append("artifact_type_invalid")
    for key in (
        "strategy_id",
        "candidate_fingerprint",
        "action_space_ref",
        "code_digest",
        "freeze_date",
        "manifest_checksum",
    ):
        if not str(manifest.get(key, "")).strip():
            blockers.append(f"{key}_required")
    for key in (
        "candidate_definition_ref",
        "candidate_definition_digest",
        "usage_signature_hash",
        "candidate_fingerprint_ref",
        "action_space_digest",
    ):
        if not str(manifest.get(key, "")).strip():
            blockers.append(f"{key}_required")
    dataset_refs = manifest.get("dataset_refs")
    if not isinstance(dataset_refs, Sequence) or isinstance(dataset_refs, (str, bytes)):
        blockers.append("dataset_refs_required")
    elif not tuple(str(item).strip() for item in dataset_refs if str(item).strip()):
        blockers.append("dataset_refs_required")
    if str(manifest.get("schema_id")) != SELECTION_FREEZE_MANIFEST_V2_SCHEMA_ID:
        blockers.append("schema_id_invalid")
    if str(manifest.get("canonicalization_version")) != CANONICALIZATION_VERSION:
        blockers.append("canonicalization_version_invalid")
    labels = manifest.get("field_labels_zh")
    if not isinstance(labels, Mapping) or not labels:
        blockers.append("field_labels_zh_required")
    expected_fingerprint = str(manifest.get("candidate_fingerprint", ""))
    for digest_key in (
        "candidate_definition_digest",
        "usage_signature_hash",
        "candidate_fingerprint",
        "action_space_digest",
        "code_digest",
        "manifest_checksum",
    ):
        if not _is_sha256(manifest.get(digest_key)):
            blockers.append(f"{digest_key}_invalid")
    checksum_payload = dict(manifest)
    supplied_checksum = str(checksum_payload.pop("manifest_checksum", ""))
    expected_checksum = canonical_digest(checksum_payload)
    if supplied_checksum != expected_checksum:
        blockers.append("manifest_checksum_mismatch")
    if (
        str(manifest.get("worktree_status", "clean")) != "clean"
        and manifest.get("diagnostic_only") is not True
    ):
        blockers.append("strict_freeze_dirty_worktree")
    return {
        "artifact_type": "selection_freeze_manifest_validation",
        "schema_id": SELECTION_FREEZE_MANIFEST_V2_SCHEMA_ID,
        "status": "blocked" if blockers else "valid",
        "blockers": blockers,
        "candidate_fingerprint": manifest.get("candidate_fingerprint", ""),
        "expected_candidate_fingerprint": expected_fingerprint,
        "expected_manifest_checksum": expected_checksum,
    }


def build_strategy_usage_candidate_fingerprint(
    *,
    fingerprint_id: str,
    strategy_family_id: str,
    strategy_id: str,
    factor_asset_ref: str,
    factor_asset_digest: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    usage_signature_hash: str,
    execution_adapter_ref: str,
    adapter_digest: str,
    code_definition_digests: Sequence[Mapping[str, str]],
    data_definition_digests: Sequence[Mapping[str, str]],
    evidence_catalog: EvidenceCatalog | None = None,
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Build the semantic, order-independent fingerprint for a usage candidate."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_usage_candidate_fingerprint",
        "schema_id": CANDIDATE_FINGERPRINT_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "fingerprint_id": fingerprint_id,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "factor_asset_ref": factor_asset_ref,
        "factor_asset_digest": factor_asset_digest,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "usage_signature_hash": usage_signature_hash,
        "execution_adapter_ref": execution_adapter_ref,
        "adapter_digest": adapter_digest,
        "code_definition_digests": _sorted_digest_records(
            code_definition_digests,
            definition_role="code",
            artifact_type=CODE_DEFINITION_ARTIFACT_TYPE,
            schema_id=CODE_DEFINITION_SCHEMA_ID,
        ),
        "data_definition_digests": _sorted_digest_records(
            data_definition_digests,
            definition_role="data",
            artifact_type=DATA_DEFINITION_ARTIFACT_TYPE,
            schema_id=DATA_DEFINITION_SCHEMA_ID,
        ),
        "field_labels_zh": dict(
            field_labels_zh
            or {
                "fingerprint_id": "候选指纹编号",
                "factor_asset_ref": "因子资产引用",
                "usage_signature_hash": "用途语义签名",
                "candidate_fingerprint": "候选指纹摘要",
            }
        ),
    }
    payload["candidate_fingerprint"] = canonical_digest(
        _candidate_fingerprint_payload(payload)
    )
    payload["artifact_digest"] = canonical_digest(payload)
    report = validate_strategy_usage_candidate_fingerprint(
        payload,
        evidence_catalog=evidence_catalog,
    )
    if report["status"] != "valid":
        blockers = report.get("blockers")
        blocker_text = (
            "; ".join(str(item) for item in blockers)
            if isinstance(blockers, Sequence) and not isinstance(blockers, (str, bytes))
            else "candidate_fingerprint_invalid"
        )
        raise ValueError(blocker_text)
    return payload


def validate_strategy_usage_candidate_fingerprint(
    payload: Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None = None,
) -> dict[str, object]:
    """Recompute and resolver-check every candidate definition dependency."""

    blockers: list[str] = []
    if str(payload.get("artifact_type")) != "strategy_usage_candidate_fingerprint":
        blockers.append("artifact_type_invalid")
    if str(payload.get("schema_id")) != CANDIDATE_FINGERPRINT_SCHEMA_ID:
        blockers.append("schema_id_invalid")
    if str(payload.get("canonicalization_version")) != CANONICALIZATION_VERSION:
        blockers.append("canonicalization_version_invalid")
    for key in (
        "fingerprint_id",
        "strategy_family_id",
        "strategy_id",
        "factor_asset_ref",
        "baseline_artifact_ref",
        "execution_adapter_ref",
    ):
        if not str(payload.get(key, "")).strip():
            blockers.append(f"{key}_required")
    for key in (
        "factor_asset_digest",
        "baseline_digest",
        "usage_signature_hash",
        "adapter_digest",
        "candidate_fingerprint",
        "artifact_digest",
    ):
        if not _is_sha256(payload.get(key)):
            blockers.append(f"{key}_invalid")
    definition_contracts = {
        "code_definition_digests": (
            "code",
            CODE_DEFINITION_ARTIFACT_TYPE,
            CODE_DEFINITION_SCHEMA_ID,
        ),
        "data_definition_digests": (
            "data",
            DATA_DEFINITION_ARTIFACT_TYPE,
            DATA_DEFINITION_SCHEMA_ID,
        ),
    }
    for key, (
        definition_role,
        artifact_type,
        schema_id,
    ) in definition_contracts.items():
        records = _digest_records(payload.get(key))
        if not records:
            blockers.append(f"{key}_required")
        elif records != sorted(records, key=lambda item: str(item["ref"])):
            blockers.append(f"{key}_must_be_sorted")
        for index, item in enumerate(records):
            if (
                not str(item.get("ref", "")).strip()
                or not _is_sha256(item.get("digest"))
                or str(item.get("digest_algorithm", "")) != "sha256"
                or str(item.get("definition_role", "")) != definition_role
                or str(item.get("artifact_type", "")) != artifact_type
                or str(item.get("schema_id", "")) != schema_id
            ):
                blockers.append(f"{key}_record_invalid:{index}")
                continue
            ref = str(item["ref"])
            resolution = resolve_evidence_ref(
                ref,
                catalog=evidence_catalog,
                expected_artifact_type=artifact_type,
                expected_schema_id=schema_id,
            )
            if resolution.get("status") != "resolved":
                blockers.extend(
                    f"{key}_unresolved:{index}:{blocker}"
                    for blocker in _object_strings(resolution.get("blockers"))
                )
                continue
            resolved_payload = _catalog_payload(ref, evidence_catalog)
            if str(resolved_payload.get("definition_role", "")) != definition_role:
                blockers.append(f"{key}_resolved_definition_role_mismatch:{index}")
            if (
                str(resolved_payload.get("canonicalization_version", ""))
                != CANONICALIZATION_VERSION
            ):
                blockers.append(f"{key}_resolved_canonicalization_invalid:{index}")
            if not str(resolved_payload.get("version", "")).strip():
                blockers.append(f"{key}_resolved_version_missing:{index}")
            definition_labels = resolved_payload.get("field_labels_zh")
            if not isinstance(definition_labels, Mapping) or not definition_labels:
                blockers.append(f"{key}_resolved_field_labels_missing:{index}")
            if (
                str(resolved_payload.get("strategy_family_id", ""))
                != str(payload.get("strategy_family_id", ""))
            ):
                blockers.append(f"{key}_resolved_strategy_family_mismatch:{index}")
            if str(resolved_payload.get("strategy_id", "")) != str(
                payload.get("strategy_id", "")
            ):
                blockers.append(f"{key}_resolved_strategy_id_mismatch:{index}")
            resolved_digest = _definition_artifact_digest(resolved_payload)
            if not resolved_digest:
                blockers.append(f"{key}_resolved_digest_missing:{index}")
            elif str(item["digest"]) != resolved_digest:
                blockers.append(f"{key}_resolved_digest_mismatch:{index}")
    labels = payload.get("field_labels_zh")
    if not isinstance(labels, Mapping) or not labels:
        blockers.append("field_labels_zh_required")
    expected = canonical_digest(_candidate_fingerprint_payload(payload))
    if payload.get("candidate_fingerprint") != expected:
        blockers.append("candidate_fingerprint_mismatch")
    artifact_payload = dict(payload)
    supplied_artifact_digest = str(artifact_payload.pop("artifact_digest", ""))
    if supplied_artifact_digest != canonical_digest(artifact_payload):
        blockers.append("artifact_digest_mismatch")
    return {
        "artifact_type": "strategy_usage_candidate_fingerprint_validation",
        "schema_id": CANDIDATE_FINGERPRINT_SCHEMA_ID,
        "status": "blocked" if blockers else "valid",
        "blockers": blockers,
        "expected_candidate_fingerprint": expected,
    }


def _candidate_fingerprint_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        key: payload.get(key)
        for key in (
            "strategy_family_id",
            "strategy_id",
            "factor_asset_ref",
            "factor_asset_digest",
            "baseline_artifact_ref",
            "baseline_digest",
            "usage_signature_hash",
            "execution_adapter_ref",
            "adapter_digest",
            "code_definition_digests",
            "data_definition_digests",
        )
    }


def _sorted_digest_records(
    records: Sequence[Mapping[str, str]],
    *,
    definition_role: str,
    artifact_type: str,
    schema_id: str,
) -> list[dict[str, str]]:
    normalized = [
        {
            "ref": str(item.get("ref", "")),
            "digest": str(item.get("digest", "")),
            "digest_algorithm": str(item.get("digest_algorithm", "")),
            "definition_role": definition_role,
            "artifact_type": artifact_type,
            "schema_id": schema_id,
        }
        for item in records
    ]
    return sorted(normalized, key=lambda item: item["ref"])


def _digest_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [
        dict(cast(Mapping[str, object], item))
        for item in value
        if isinstance(item, Mapping)
    ]


def _is_sha256(value: object) -> bool:
    return re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)) is not None


def _catalog_payload(
    ref: str,
    catalog: EvidenceCatalog | None,
) -> Mapping[str, object]:
    if catalog is None:
        return {}
    return catalog.get(ref, {})


def _definition_artifact_digest(payload: Mapping[str, object]) -> str:
    """Return a definition checksum only when it exactly covers its semantics."""

    supplied = str(payload.get("checksum", ""))
    if not _is_sha256(supplied):
        return ""
    semantic_payload = dict(payload)
    for key in ("checksum", "computed_checksum", "resolved_path_or_uri"):
        _ = semantic_payload.pop(key, None)
    expected = canonical_digest(semantic_payload)
    return supplied if supplied == expected else ""


def _object_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


__all__ = [
    "CANDIDATE_FINGERPRINT_SCHEMA_ID",
    "CANONICALIZATION_VERSION",
    "CODE_DEFINITION_ARTIFACT_TYPE",
    "CODE_DEFINITION_SCHEMA_ID",
    "DATA_DEFINITION_ARTIFACT_TYPE",
    "DATA_DEFINITION_SCHEMA_ID",
    "SELECTION_FREEZE_MANIFEST_V2_SCHEMA_ID",
    "build_selection_freeze_manifest",
    "build_selection_freeze_manifest_v2",
    "build_strategy_usage_candidate_fingerprint",
    "validate_selection_freeze_manifest",
    "validate_selection_freeze_manifest_v2",
    "validate_strategy_usage_candidate_fingerprint",
]
