"""Machine contract for append-only strategy-usage cutover receipts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from factor_lab.governance.canonicalization import canonical_digest

CUTOVER_TRANSITION_SCHEMA_ID = "strategy_usage_cutover_transition_receipt@1.0"
CANONICALIZATION_VERSION = "factorlab_canonical_json@1"

_FIELDS = frozenset(
    {
        "artifact_type",
        "schema_id",
        "canonicalization_version",
        "transition_id",
        "strategy_id",
        "expected_prior_state",
        "expected_prior_version",
        "next_state",
        "reason",
        "authorization_ref",
        "authorization_digest",
        "rich_cutover_digest",
        "assurance_records",
        "rollback_snapshot_ref",
        "occurred_at",
        "authorized_claim_ids",
        "required_history",
        "legacy_new_promotion_allowed",
        "production_authority",
        "field_labels_zh",
        "receipt_digest",
    }
)
_TRANSITIONS = frozenset(
    {
        ("legacy_read", "shadow_audit"),
        ("shadow_audit", "required"),
        ("required", "shadow_audit"),
    }
)


def validate_strategy_usage_cutover_transition_receipt(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate the complete receipt shape and recompute its typed digest."""

    blockers: list[str] = []
    if frozenset(payload) != _FIELDS:
        blockers.append("cutover_transition_receipt_fields_mismatch")
    for field, expected in (
        ("artifact_type", "strategy_usage_cutover_transition_receipt"),
        ("schema_id", CUTOVER_TRANSITION_SCHEMA_ID),
        ("canonicalization_version", CANONICALIZATION_VERSION),
    ):
        if str(payload.get(field, "")) != expected:
            blockers.append(f"cutover_transition_receipt_{field}_mismatch")
    for field in (
        "transition_id",
        "strategy_id",
        "reason",
        "authorization_ref",
        "occurred_at",
    ):
        if not str(payload.get(field, "")).strip():
            blockers.append(f"cutover_transition_receipt_{field}_required")

    prior_state = str(payload.get("expected_prior_state", ""))
    next_state = str(payload.get("next_state", ""))
    if (prior_state, next_state) not in _TRANSITIONS:
        blockers.append("invalid_usage_discovery_cutover_transition")
    prior_version = payload.get("expected_prior_version")
    if (
        not isinstance(prior_version, int)
        or isinstance(prior_version, bool)
        or prior_version < 0
    ):
        blockers.append("cutover_transition_receipt_expected_prior_version_invalid")

    occurred_at = str(payload.get("occurred_at", ""))
    try:
        parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        blockers.append("cutover_transition_receipt_occurred_at_invalid")

    for field in ("authorization_digest", "rich_cutover_digest"):
        value = str(payload.get(field, ""))
        if value and not _is_sha256(value):
            blockers.append(f"cutover_transition_receipt_{field}_invalid")
    if next_state == "required":
        for field in ("authorization_digest", "rich_cutover_digest"):
            if not str(payload.get(field, "")):
                blockers.append(f"cutover_transition_receipt_{field}_required")

    rollback_ref = str(payload.get("rollback_snapshot_ref", ""))
    if prior_state == "required" and next_state == "shadow_audit":
        if not rollback_ref:
            blockers.append("rollback_snapshot_ref_required")

    blockers.extend(_assurance_blockers(payload.get("assurance_records"), next_state))
    blockers.extend(
        _string_list_blockers(
            payload.get("authorized_claim_ids"),
            field="authorized_claim_ids",
        )
    )
    required_history = payload.get("required_history")
    if not isinstance(required_history, bool):
        blockers.append("cutover_transition_receipt_required_history_boolean_required")
    elif (
        prior_state == "required" or next_state == "required"
    ) and not required_history:
        blockers.append("cutover_transition_receipt_required_history_must_be_true")
    if payload.get("legacy_new_promotion_allowed") is not False:
        blockers.append("cutover_transition_receipt_legacy_promotion_must_be_false")
    if payload.get("production_authority") is not False:
        blockers.append("cutover_transition_receipt_production_authority_must_be_false")
    labels_value = payload.get("field_labels_zh")
    labels: Mapping[object, object] = (
        cast(Mapping[object, object], labels_value)
        if isinstance(labels_value, Mapping)
        else cast(Mapping[object, object], {})
    )
    if not labels or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or not value.strip()
        for key, value in labels.items()
    ):
        blockers.append("cutover_transition_receipt_field_labels_zh_invalid")

    receipt_digest = str(payload.get("receipt_digest", ""))
    semantic = dict(payload)
    _ = semantic.pop("receipt_digest", None)
    if not _is_sha256(receipt_digest):
        blockers.append("cutover_transition_receipt_digest_invalid")
    else:
        try:
            expected_digest = canonical_digest(semantic)
        except (TypeError, ValueError):
            blockers.append("cutover_transition_receipt_canonical_payload_invalid")
        else:
            if receipt_digest != expected_digest:
                blockers.append("cutover_transition_receipt_digest_mismatch")
    return {
        "artifact_type": "strategy_usage_cutover_transition_receipt_validation",
        "schema_id": CUTOVER_TRANSITION_SCHEMA_ID,
        "status": "valid" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
    }


def _assurance_blockers(value: object, next_state: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ["cutover_transition_receipt_assurance_records_array_required"]
    blockers: list[str] = []
    identities: list[tuple[str, str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            blockers.append(
                f"cutover_transition_receipt_assurance_record_invalid:{index}"
            )
            continue
        record = cast(Mapping[object, object], item)
        if set(record) != {"ref", "digest", "kind"}:
            blockers.append(
                f"cutover_transition_receipt_assurance_record_invalid:{index}"
            )
            continue
        ref = str(record.get("ref", "")).strip()
        digest = str(record.get("digest", ""))
        kind = str(record.get("kind", ""))
        if not ref:
            blockers.append(
                f"cutover_transition_receipt_assurance_ref_required:{index}"
            )
        if not _is_sha256(digest):
            blockers.append(
                f"cutover_transition_receipt_assurance_digest_invalid:{index}"
            )
        if kind not in {"evidence", "test"}:
            blockers.append(
                f"cutover_transition_receipt_assurance_kind_invalid:{index}"
            )
        identities.append((ref, digest, kind))
    if len(identities) != len(set(identities)):
        blockers.append("cutover_transition_receipt_assurance_records_duplicate")
    if next_state == "required" and not identities:
        blockers.append("cutover_transition_receipt_assurance_records_required")
    return blockers


def _string_list_blockers(value: object, *, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return [f"cutover_transition_receipt_{field}_array_required"]
    normalized = tuple(str(item).strip() for item in value)
    blockers: list[str] = []
    if any(not isinstance(item, str) or not item.strip() for item in value):
        blockers.append(f"cutover_transition_receipt_{field}_items_invalid")
    if len(normalized) != len(set(normalized)):
        blockers.append(f"cutover_transition_receipt_{field}_duplicate")
    return blockers


def _is_sha256(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


__all__ = [
    "CANONICALIZATION_VERSION",
    "CUTOVER_TRANSITION_SCHEMA_ID",
    "validate_strategy_usage_cutover_transition_receipt",
]
