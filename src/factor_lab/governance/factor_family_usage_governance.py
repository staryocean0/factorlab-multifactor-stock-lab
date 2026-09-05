"""Sealed usage-discovery bridge for the real Feature Library family record."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID = "factor_family_usage_governance@1.0"
CANONICALIZATION_VERSION = "factorlab_canonical_json@1"


def build_factor_family_usage_governance(
    source_record: Mapping[str, object],
    *,
    parent_multiplicity_family_id: str,
    factor_identity_dimension_ids: Sequence[str],
) -> dict[str, object]:
    """Bind a persisted FactorFamilyGovernanceRecord to usage accounting."""

    payload: dict[str, object] = {
        "artifact_type": "factor_family_governance",
        "schema_id": SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "source_governance_id": str(source_record.get("governance_id", "")),
        "source_governance_record": dict(source_record),
        "source_record_digest": canonical_digest(source_record),
        "strategy_id": str(source_record.get("strategy_id", "")),
        "factor_ref": str(source_record.get("factor_ref", "")),
        "family_id": str(source_record.get("family_id", "")),
        "parent_multiplicity_family_id": parent_multiplicity_family_id,
        "owner_layer": "factor_identity",
        "factor_identity_dimension_ids": list(factor_identity_dimension_ids),
        "field_labels_zh": {
            "source_governance_id": "因子家族治理编号",
            "parent_multiplicity_family_id": "父多重检验家族编号",
            "factor_identity_dimension_ids": "因子身份维度编号",
        },
    }
    payload["checksum"] = canonical_digest(payload)
    report = validate_factor_family_usage_governance(payload)
    if report["status"] != "valid":
        raise ValueError("; ".join(cast(list[str], report["blockers"])))
    return payload


def validate_factor_family_usage_governance(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers: list[str] = []
    expected_fields = {
        "artifact_type",
        "schema_id",
        "canonicalization_version",
        "source_governance_id",
        "source_governance_record",
        "source_record_digest",
        "strategy_id",
        "factor_ref",
        "family_id",
        "parent_multiplicity_family_id",
        "owner_layer",
        "factor_identity_dimension_ids",
        "field_labels_zh",
        "checksum",
    }
    if set(payload) != expected_fields:
        blockers.append("factor_family_usage_governance_fields_invalid")
    for field, expected in (
        ("artifact_type", "factor_family_governance"),
        ("schema_id", SCHEMA_ID),
        ("canonicalization_version", CANONICALIZATION_VERSION),
        ("owner_layer", "factor_identity"),
    ):
        if payload.get(field) != expected:
            blockers.append(f"{field}_invalid")
    for field in (
        "source_governance_id",
        "strategy_id",
        "factor_ref",
        "family_id",
        "parent_multiplicity_family_id",
    ):
        if not str(payload.get(field, "")).strip():
            blockers.append(f"{field}_required")
    source = payload.get("source_governance_record")
    if not isinstance(source, Mapping):
        blockers.append("source_governance_record_required")
        source_record: Mapping[str, object] = {}
    else:
        source_record = cast(Mapping[str, object], source)
    for bridge_field, source_field in (
        ("source_governance_id", "governance_id"),
        ("strategy_id", "strategy_id"),
        ("factor_ref", "factor_ref"),
        ("family_id", "family_id"),
    ):
        if str(payload.get(bridge_field, "")) != str(
            source_record.get(source_field, "")
        ):
            blockers.append(f"source_{source_field}_mismatch")
    source_digest = str(payload.get("source_record_digest", ""))
    if source_digest != canonical_digest(source_record):
        blockers.append("source_record_digest_mismatch")
    dimensions = payload.get("factor_identity_dimension_ids")
    if not isinstance(dimensions, Sequence) or isinstance(dimensions, (str, bytes)):
        dimension_ids: list[str] = []
    else:
        dimension_ids = [str(item) for item in dimensions]
    if not dimension_ids:
        blockers.append("factor_identity_dimension_ids_required")
    if len(dimension_ids) != len(set(dimension_ids)):
        blockers.append("factor_identity_dimension_ids_duplicate")
    if any(not item.startswith("factor_identity:") for item in dimension_ids):
        blockers.append("factor_identity_dimension_namespace_invalid")
    labels = payload.get("field_labels_zh")
    if not isinstance(labels, Mapping) or not labels:
        blockers.append("field_labels_zh_required")
    checksum = str(payload.get("checksum", ""))
    semantic = dict(payload)
    _ = semantic.pop("checksum", None)
    if checksum != canonical_digest(semantic):
        blockers.append("checksum_mismatch")
    return {
        "schema_id": SCHEMA_ID,
        "status": "valid" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "production_authority": False,
    }


__all__ = [
    "SCHEMA_ID",
    "build_factor_family_usage_governance",
    "validate_factor_family_usage_governance",
]
