"""Persistent candidate factor asset service.

This module separates high-volume discovery assets from legacy governance
candidates.  DataHub remains the authority for source datasets; Factor Lab owns
candidate-factor metadata, dataset-scoped validation claims, and effective-factor
lifecycle records.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Final, cast

from factor_lab.candidate_assets.services.factor_asset_service import (
    factor_asset_service,
)
from factor_lab.core.errors import ConflictError, NotFoundError, ValidationError
from factor_lab.core.hashing import sha256_hash
from factor_lab.core.runtime_records import (
    artifact_payload,
    find_first_artifact_id,
    get_record,
    upsert_record,
    utcnow,
)
from factor_lab.core.runtime_state import Record, runtime_state_store
from factor_lab.core.source_universe import (
    source_family_for_dataset_version,
    source_refs_for_dataset_version,
)
from factor_lab.evaluation.services.factor_evaluation_service import (
    factor_evaluation_service,
)
from factor_lab.factor_engine.dsl import factor_spec_from_dsl
from factor_lab.factor_engine.repositories.spec_registry import spec_registry
from factor_lab.governance.services.event_store import event_store
from factor_lab.governance.temporal_integrity import (
    validate_temporal_evaluation_contract,
)

_POOL_STATUS_ORDER: Final[dict[str, int]] = {
    "discovered": 1,
    "screened": 2,
    "proposed": 3,
    "watchlist": 4,
    "archived": 5,
    "deprecated": 6,
}
_VALID_CLAIM_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending_review", "approved", "rejected", "superseded", "expired"}
)
_ACTIVE_EFFECTIVE_STATUSES: Final[frozenset[str]] = frozenset(
    {"active", "suspended", "retired", "superseded", "revoked"}
)
_ADMITTED_FACTOR_STATUSES: Final[frozenset[str]] = frozenset(
    {"admitted", "published", "suspended", "retired", "superseded", "revoked"}
)
_COMPLETE_FACTOR_SPEC_KEYS: Final[frozenset[str]] = frozenset(
    {
        "spec_id",
        "spec_version",
        "factor_spec_version",
        "name",
        "description",
        "factor_type",
        "callable_ref",
        "dsl_expression",
        "materialized_frame_ref",
        "value_column",
        "preprocess_spec_version",
        "input_schema",
        "output_schema",
        "parameters",
        "source_family",
        "source_refs",
        "input_field_lineage",
        "dsl_ast_version",
        "operator_set_version",
        "expression_hash",
        "complexity_score",
        "field_refs",
        "window_refs",
        "nan_policy",
        "normalized_ast",
        "operator_list",
        "tags",
        "feature_refs",
    }
)
_FACTOR_TYPES: Final[frozenset[str]] = frozenset(
    {"python_callable", "template", "formulaic_dsl", "materialized_frame"}
)
_FULL_FACTOR_SPEC_SENTINEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "spec_id",
        "spec_version",
        "name",
        "description",
        "factor_type",
        "callable_ref",
        "materialized_frame_ref",
        "value_column",
        "preprocess_spec_version",
        "input_schema",
        "output_schema",
        "parameters",
        "source_family",
        "source_refs",
        "input_field_lineage",
        "dsl_ast_version",
        "operator_set_version",
        "tags",
        "feature_refs",
    }
)


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    typed_value = cast(Mapping[object, object], value)
    return {str(key): item for key, item in typed_value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def _int_list(value: object) -> list[int]:
    return [int(str(item)) for item in _string_list(value)]


def _float_from_object(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _dedupe_string_refs(values: Sequence[object]) -> list[str]:
    refs: list[str] = []
    for value in values:
        ref = str(value).strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


@dataclass(slots=True)
class CandidatePoolFactorRecord:
    candidate_factor_id: str
    factor_spec_version: str
    source_family: str
    pool_status: str
    candidate_name: str
    canonical_hash: str
    expression_hash: str
    dsl_expression_snapshot: str
    normalized_ast: dict[str, object]
    operator_list: list[str]
    field_lineage: dict[str, object]
    field_refs: list[str]
    window_refs: list[int]
    complexity_score: float
    nan_policy: str
    source_refs: list[str]
    discovery_source_refs: list[str]
    first_seen_run_id: str
    first_seen_batch_id: str
    latest_seen_run_id: str
    latest_seen_batch_id: str
    created_at: str
    latest_seen_at: str
    created_by: str
    discovery_count: int = 1
    latest_screening_evaluation_run_id: str = ""
    latest_discovery_score: float = 0.0
    latest_rank_ic_mean: float = 0.0
    latest_ic_mean: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class CandidateBatchRecord:
    candidate_batch_id: str
    source_run_id: str
    search_kind: str
    template_id: str
    dataset_version_used_for_discovery: str
    label_spec_version: str
    protocol_version: str
    source_family: str
    source_refs: list[str]
    search_budget: int
    top_k: int
    seed: int
    created_at: str
    created_by: str
    status: str = "open"
    candidate_count: int = 0
    pool_candidate_count: int = 0
    deduped_count: int = 0
    failed_count: int = 0
    top_candidate_factor_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class CandidateBatchMemberRecord:
    candidate_batch_member_id: str
    candidate_batch_id: str
    candidate_factor_id: str
    factor_spec_version: str
    rank_order: int
    duplicate_status: str
    source_family: str
    evaluation_run_id: str = ""
    discovery_score: float = 0.0
    rank_ic_mean: float = 0.0
    ic_mean: float = 0.0
    failed_reason: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ValidationClaimRecord:
    validation_claim_id: str
    candidate_factor_id: str
    factor_spec_version: str
    dataset_version: str
    dataset_fingerprint: str
    label_spec_version: str
    protocol_version: str
    source_family: str
    source_refs: list[str]
    evaluation_run_id: str
    verdict: str
    claim_status: str
    score_summary: dict[str, object]
    oos_summary: dict[str, object]
    risk_exposure_summary: dict[str, object]
    temporal_integrity_summary: dict[str, object]
    evidence_artifact_ids: list[str]
    preprocessing_config: dict[str, object]
    neutralization_config: dict[str, object]
    created_at: str
    created_by: str
    updated_at: str
    review_reason: str = ""
    approved_by: str = ""
    approved_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class EffectiveFactorRecord:
    effective_factor_id: str
    candidate_factor_id: str
    validation_claim_id: str
    evaluation_run_id: str
    dataset_version: str
    dataset_fingerprint: str
    label_spec_version: str
    protocol_version: str
    source_family: str
    effective_name: str
    activation_status: str
    approval_request_id: str
    activated_at: str
    activated_by: str
    materialization_policy: dict[str, object]
    score_summary: dict[str, object]
    evidence_artifact_ids: list[str]
    factor_spec_version: str = ""
    source_refs: list[str] = field(default_factory=list)
    factor_type: str = ""
    materialized_frame_ref: str = ""
    retired_at: str = ""
    replacement_effective_factor_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class AdmittedFactorRecord:
    admitted_factor_id: str
    effective_factor_id: str
    candidate_factor_id: str
    validation_claim_id: str
    evaluation_run_id: str
    dataset_version: str
    dataset_fingerprint: str
    label_spec_version: str
    protocol_version: str
    source_family: str
    admitted_name: str
    admission_status: str
    approval_request_id: str
    admitted_at: str
    admitted_by: str
    score_summary: dict[str, object]
    evidence_artifact_ids: list[str]
    release_policy: dict[str, object]
    factor_spec_version: str = ""
    source_refs: list[str] = field(default_factory=list)
    factor_type: str = ""
    materialized_frame_ref: str = ""
    retired_at: str = ""
    replacement_admitted_factor_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CandidateAssetService:
    """Durable pool, validation-claim, and effective-factor registry."""

    def candidate_identity_from_spec(
        self,
        *,
        spec: Mapping[str, object],
        source_family: str,
    ) -> dict[str, str]:
        """Derive the stable candidate identity without reading or mutating state."""

        self._validate_complete_identity_spec(spec, source_family=source_family)
        metadata = self._candidate_identity_metadata(spec)
        canonical_hash = self._canonical_hash(
            source_family=source_family,
            metadata=metadata,
        )
        return {
            "candidate_factor_id": f"cpf_{canonical_hash[:16]}",
            "canonical_hash": canonical_hash,
            "factor_spec_version": str(metadata["factor_spec_version"]),
        }

    @staticmethod
    def _validate_complete_identity_spec(
        spec: Mapping[str, object],
        *,
        source_family: str,
        require_executable_semantics: bool = True,
    ) -> None:
        """Reject partial or conflicting self-attested FactorSpec identities."""

        if set(spec) != set(_COMPLETE_FACTOR_SPEC_KEYS):
            raise ValidationError("candidate identity requires the complete FactorSpec field set")
        if any(
            not isinstance(spec.get(field), str)
            for field in ("spec_id", "spec_version", "factor_spec_version", "name")
        ):
            raise ValidationError("candidate identity FactorSpec identity fields must be strings")
        spec_id = cast(str, spec["spec_id"]).strip()
        spec_version = cast(str, spec["spec_version"]).strip()
        factor_spec_version = cast(str, spec["factor_spec_version"]).strip()
        if not spec_id or spec_id != spec_version or spec_version != factor_spec_version:
            raise ValidationError(
                "candidate identity requires one non-empty consistent FactorSpec version"
            )
        if (
            not source_family.strip()
            or not isinstance(spec.get("source_family"), str)
            or spec.get("source_family") != source_family
        ):
            raise ValidationError("candidate identity source_family conflicts with FactorSpec")
        if not str(spec.get("name", "")).strip():
            raise ValidationError("candidate identity requires a FactorSpec name")
        if not isinstance(spec.get("factor_type"), str):
            raise ValidationError("candidate identity factor_type must be a string")
        factor_type = cast(str, spec["factor_type"]).strip()
        if not factor_type:
            raise ValidationError("candidate identity requires a non-empty factor_type")
        if require_executable_semantics and factor_type not in _FACTOR_TYPES:
            raise ValidationError("candidate identity requires a supported factor_type")
        if factor_type == "python_callable" and not str(spec.get("callable_ref", "")).strip():
            raise ValidationError("python_callable candidate identity requires callable_ref")
        if factor_type == "formulaic_dsl" and not str(spec.get("dsl_expression", "")).strip():
            raise ValidationError("formulaic_dsl candidate identity requires dsl_expression")
        if factor_type == "materialized_frame" and not str(spec.get("materialized_frame_ref", "")).strip():
            raise ValidationError(
                "materialized_frame candidate identity requires materialized_frame_ref"
            )
        for text_field in (
            "description",
            "callable_ref",
            "materialized_frame_ref",
            "value_column",
            "preprocess_spec_version",
            "dsl_ast_version",
            "operator_set_version",
            "nan_policy",
        ):
            if not isinstance(spec.get(text_field), str):
                raise ValidationError(
                    f"candidate identity requires string FactorSpec field {text_field}"
                )
        if not cast(str, spec["value_column"]).strip():
            raise ValidationError("candidate identity requires a non-empty value_column")
        dsl_expression = spec.get("dsl_expression")
        if dsl_expression is not None and not isinstance(dsl_expression, str):
            raise ValidationError("candidate identity dsl_expression must be string or null")
        for mapping_field in (
            "input_schema",
            "output_schema",
            "parameters",
            "normalized_ast",
            "tags",
        ):
            if not isinstance(spec.get(mapping_field), Mapping):
                raise ValidationError(
                    f"candidate identity requires mapping FactorSpec field {mapping_field}"
                )
        for identity_field in ("operator_list", "field_refs", "source_refs"):
            value = spec.get(identity_field)
            if (
                not isinstance(value, list)
                or any(
                    not isinstance(item, str)
                    for item in cast(list[object], value)
                )
            ):
                raise ValidationError(
                    f"candidate identity requires string-list {identity_field}"
                )
        for list_field in ("window_refs", "feature_refs"):
            value = spec.get(list_field)
            if not isinstance(value, list):
                raise ValidationError(
                    f"candidate identity requires list FactorSpec field {list_field}"
                )
        window_refs = cast(list[object], spec["window_refs"])
        if any(isinstance(value, bool) or not isinstance(value, int) for value in window_refs):
            raise ValidationError("candidate identity window_refs must contain integers")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in cast(list[object], spec["feature_refs"])
        ):
            raise ValidationError("candidate identity feature_refs must contain strings")
        tags = cast(Mapping[object, object], spec["tags"])
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in tags.items()):
            raise ValidationError("candidate identity tags must be string-to-string")
        field_lineage = spec.get("input_field_lineage")
        if (
            not isinstance(field_lineage, Mapping)
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                for key, value in cast(Mapping[object, object], field_lineage).items()
            )
        ):
            raise ValidationError("candidate identity requires string input_field_lineage")
        if not isinstance(spec.get("expression_hash"), str):
            raise ValidationError("candidate identity expression_hash must be a string")
        if require_executable_semantics:
            normalized_ast = cast(Mapping[object, object], spec["normalized_ast"])
            operator_list = cast(list[object], spec["operator_list"])
            field_refs = cast(list[object], spec["field_refs"])
            source_refs = cast(list[object], spec["source_refs"])
            if not normalized_ast:
                raise ValidationError("candidate identity requires a non-empty normalized_ast")
            if not operator_list or not field_refs or not source_refs:
                raise ValidationError(
                    "candidate identity requires operators, fields, and source refs"
                )
            if not cast(Mapping[object, object], field_lineage):
                raise ValidationError(
                    "candidate identity requires complete input_field_lineage"
                )
            if not cast(str, spec["nan_policy"]).strip():
                raise ValidationError("candidate identity requires a nan_policy")
            expression_hash = cast(str, spec["expression_hash"]).strip()
            if expression_hash.startswith("sha256:"):
                expression_hash = expression_hash.removeprefix("sha256:")
            if len(expression_hash) != 64 or any(
                character not in "0123456789abcdef" for character in expression_hash
            ):
                raise ValidationError("candidate identity expression_hash is invalid")
        complexity = spec.get("complexity_score")
        if (
            isinstance(complexity, bool)
            or not isinstance(complexity, (int, float))
            or not isfinite(float(complexity))
            or float(complexity) < 0.0
        ):
            raise ValidationError("candidate identity complexity_score is invalid")

    @staticmethod
    def _candidate_identity_metadata(spec: Mapping[str, object]) -> dict[str, object]:
        """Normalize a complete supplied spec without consulting mutable registries."""

        factor_spec_version = str(spec.get("factor_spec_version", ""))
        return {
            "factor_spec_version": factor_spec_version,
            "candidate_name": str(spec.get("name", factor_spec_version)),
            "dsl_expression_snapshot": str(
                spec.get("dsl_expression_snapshot", spec.get("dsl_expression", ""))
                or ""
            ),
            "normalized_ast": _object_dict(spec.get("normalized_ast", {})),
            "operator_list": _string_list(spec.get("operator_list", [])),
            "field_lineage": _object_dict(
                spec.get("field_lineage", spec.get("input_field_lineage", {}))
            ),
            "field_refs": _string_list(spec.get("field_refs", [])),
            "window_refs": _int_list(spec.get("window_refs", [])),
            "complexity_score": _float_from_object(spec.get("complexity_score", 0.0)),
            "nan_policy": str(spec.get("nan_policy", "")),
            "expression_hash": str(spec.get("expression_hash", "")),
            "complete_factor_spec_identity": {
                key: spec[key] for key in sorted(_COMPLETE_FACTOR_SPEC_KEYS)
            },
        }

    def _candidate_spec_metadata(
        self,
        spec: Mapping[str, object],
        *,
        source_family: str,
    ) -> dict[str, object]:
        """Resolve legacy discovery envelopes through the registered FactorSpec.

        Legacy mining payloads may carry search metadata, but they never define
        candidate identity.  The registered complete FactorSpec is the sole
        identity source, which prevents a partial envelope from retaining the
        historical reduced-hash path.
        """

        factor_spec_version = str(spec.get("factor_spec_version", ""))
        factor_spec = spec_registry.get_factor_spec_sync(factor_spec_version)
        if factor_spec is None:
            raise ValidationError(
                "candidate upsert requires a complete or registered FactorSpec"
            )
        complete_spec = factor_spec.to_dict()
        self._validate_complete_identity_spec(
            complete_spec,
            source_family=source_family,
            require_executable_semantics=False,
        )
        return self._candidate_identity_metadata(complete_spec)

    @staticmethod
    def _canonical_hash(
        *,
        source_family: str,
        metadata: Mapping[str, object],
    ) -> str:
        complete_identity = metadata.get("complete_factor_spec_identity")
        if not isinstance(complete_identity, Mapping) or set(
            cast(Mapping[str, object], complete_identity)
        ) != set(_COMPLETE_FACTOR_SPEC_KEYS):
            raise ValidationError("candidate canonical hash lacks a complete FactorSpec")
        return sha256_hash(
            {
                "identity_schema": "complete_factor_spec_identity@1.0",
                "source_family": source_family,
                "factor_spec": dict(cast(Mapping[str, object], complete_identity)),
            }
        )

    def _existing_by_hash(
        self,
        *,
        source_family: str,
        canonical_hash: str,
    ) -> Record | None:
        for record in runtime_state_store.load()["candidate_pool_factors"].values():
            if (
                str(record.get("source_family")) == source_family
                and str(record.get("canonical_hash")) == canonical_hash
            ):
                return record
        return None

    @staticmethod
    def _merged_pool_status(current: str, incoming: str) -> str:
        if current in {"archived", "deprecated"}:
            return current
        current_rank = _POOL_STATUS_ORDER.get(current, 0)
        incoming_rank = _POOL_STATUS_ORDER.get(incoming, 0)
        return incoming if incoming_rank > current_rank else current

    def create_candidate_batch(
        self,
        *,
        source_run_id: str,
        search_kind: str,
        template_id: str,
        dataset_version_used_for_discovery: str,
        label_spec_version: str,
        protocol_version: str,
        source_family: str,
        source_refs: list[str],
        search_budget: int,
        top_k: int,
        seed: int,
        created_by: str,
    ) -> dict[str, object]:
        batch = CandidateBatchRecord(
            candidate_batch_id=str(uuid.uuid4()),
            source_run_id=source_run_id,
            search_kind=search_kind,
            template_id=template_id,
            dataset_version_used_for_discovery=dataset_version_used_for_discovery,
            label_spec_version=label_spec_version,
            protocol_version=protocol_version,
            source_family=source_family,
            source_refs=list(dict.fromkeys(source_refs)),
            search_budget=search_budget,
            top_k=top_k,
            seed=seed,
            created_at=utcnow(),
            created_by=created_by,
        )
        upsert_record(
            "candidate_batches",
            batch.candidate_batch_id,
            batch.to_dict(),
        )
        _ = event_store.append(
            event_type="candidate_pool.batch_created",
            payload=batch.to_dict(),
            run_id=source_run_id,
        )
        return batch.to_dict()

    def upsert_candidate_from_spec(
        self,
        *,
        spec: Mapping[str, object],
        source_family: str,
        source_refs: list[str],
        source_run_id: str,
        candidate_batch_id: str,
        created_by: str,
        pool_status: str = "discovered",
        screening: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        if pool_status not in _POOL_STATUS_ORDER:
            raise ValidationError(f"Unsupported pool_status: {pool_status}")
        supplied_keys = set(spec)
        if supplied_keys == set(_COMPLETE_FACTOR_SPEC_KEYS):
            self._validate_complete_identity_spec(
                spec,
                source_family=source_family,
            )
            metadata = self._candidate_identity_metadata(spec)
        elif supplied_keys & _FULL_FACTOR_SPEC_SENTINEL_KEYS:
            raise ValidationError(
                "candidate upsert rejects a partial or extended complete FactorSpec"
            )
        else:
            metadata = self._candidate_spec_metadata(
                spec,
                source_family=source_family,
            )
        canonical_hash = self._canonical_hash(
            source_family=source_family,
            metadata=metadata,
        )
        complete_identity = cast(
            Mapping[str, object],
            metadata["complete_factor_spec_identity"],
        )
        canonical_source_refs = _string_list(complete_identity["source_refs"])
        existing = self._existing_by_hash(
            source_family=source_family,
            canonical_hash=canonical_hash,
        )
        now = utcnow()
        screening_payload = dict(screening or {})
        if existing is not None:
            updated = dict(existing)
            updated["pool_status"] = self._merged_pool_status(
                str(updated.get("pool_status", "discovered")),
                pool_status,
            )
            updated["latest_seen_run_id"] = source_run_id
            updated["latest_seen_batch_id"] = candidate_batch_id
            updated["latest_seen_at"] = now
            updated["source_refs"] = canonical_source_refs
            updated["discovery_source_refs"] = list(
                dict.fromkeys(
                    [
                        *_string_list(updated.get("discovery_source_refs", [])),
                        *source_refs,
                    ]
                )
            )
            updated["discovery_count"] = int(str(updated.get("discovery_count", 0))) + 1
            for key in (
                "latest_screening_evaluation_run_id",
                "latest_discovery_score",
                "latest_rank_ic_mean",
                "latest_ic_mean",
            ):
                if key in screening_payload:
                    updated[key] = screening_payload[key]
            upsert_record(
                "candidate_pool_factors",
                str(updated["candidate_factor_id"]),
                updated,
            )
            return factor_asset_service.synchronize_candidate(
                candidate=updated,
                assigned_by=created_by,
            )

        record = CandidatePoolFactorRecord(
            candidate_factor_id=f"cpf_{canonical_hash[:16]}",
            factor_spec_version=str(metadata["factor_spec_version"]),
            source_family=source_family,
            pool_status=pool_status,
            candidate_name=str(metadata.get("candidate_name", "")),
            canonical_hash=canonical_hash,
            expression_hash=str(metadata.get("expression_hash", "")),
            dsl_expression_snapshot=str(metadata.get("dsl_expression_snapshot", "")),
            normalized_ast=_object_dict(metadata.get("normalized_ast", {})),
            operator_list=_string_list(metadata.get("operator_list", [])),
            field_lineage=_object_dict(metadata.get("field_lineage", {})),
            field_refs=_string_list(metadata.get("field_refs", [])),
            window_refs=_int_list(metadata.get("window_refs", [])),
            complexity_score=_float_from_object(metadata.get("complexity_score", 0.0)),
            nan_policy=str(metadata.get("nan_policy", "")),
            source_refs=canonical_source_refs,
            discovery_source_refs=list(dict.fromkeys(source_refs)),
            first_seen_run_id=source_run_id,
            first_seen_batch_id=candidate_batch_id,
            latest_seen_run_id=source_run_id,
            latest_seen_batch_id=candidate_batch_id,
            created_at=now,
            latest_seen_at=now,
            created_by=created_by,
            latest_screening_evaluation_run_id=str(
                screening_payload.get("latest_screening_evaluation_run_id", "")
            ),
            latest_discovery_score=_float_from_object(
                screening_payload.get("latest_discovery_score", 0.0)
            ),
            latest_rank_ic_mean=_float_from_object(
                screening_payload.get("latest_rank_ic_mean", 0.0)
            ),
            latest_ic_mean=_float_from_object(
                screening_payload.get("latest_ic_mean", 0.0)
            ),
        )
        upsert_record(
            "candidate_pool_factors",
            record.candidate_factor_id,
            record.to_dict(),
        )
        _ = event_store.append(
            event_type="candidate_pool.factor_upserted",
            payload={
                "candidate_factor_id": record.candidate_factor_id,
                "factor_spec_version": record.factor_spec_version,
                "canonical_hash": record.canonical_hash,
                "pool_status": record.pool_status,
                "candidate_batch_id": candidate_batch_id,
            },
            run_id=source_run_id,
        )
        return factor_asset_service.synchronize_candidate(
            candidate=record.to_dict(),
            assigned_by=created_by,
        )

    def record_batch_member(
        self,
        *,
        candidate_batch_id: str,
        candidate_factor_id: str,
        factor_spec_version: str,
        rank_order: int,
        duplicate_status: str,
        source_family: str,
        evaluation_run_id: str = "",
        discovery_score: float = 0.0,
        rank_ic_mean: float = 0.0,
        ic_mean: float = 0.0,
        failed_reason: str = "",
    ) -> dict[str, object]:
        member_id = f"{candidate_batch_id}:{candidate_factor_id}:{rank_order}"
        record = CandidateBatchMemberRecord(
            candidate_batch_member_id=member_id,
            candidate_batch_id=candidate_batch_id,
            candidate_factor_id=candidate_factor_id,
            factor_spec_version=factor_spec_version,
            rank_order=rank_order,
            duplicate_status=duplicate_status,
            source_family=source_family,
            evaluation_run_id=evaluation_run_id,
            discovery_score=discovery_score,
            rank_ic_mean=rank_ic_mean,
            ic_mean=ic_mean,
            failed_reason=failed_reason,
            created_at=utcnow(),
        )
        upsert_record("candidate_batch_members", member_id, record.to_dict())
        return record.to_dict()

    def finalize_candidate_batch(
        self,
        *,
        candidate_batch_id: str,
        candidate_count: int,
        pool_candidate_count: int,
        failed_count: int,
        top_candidate_factor_ids: list[str],
    ) -> dict[str, object]:
        batch = get_record("candidate_batches", candidate_batch_id)
        if batch is None:
            raise NotFoundError(f"Candidate batch not found: {candidate_batch_id}")
        updated = dict(batch)
        updated.update(
            {
                "status": "completed",
                "candidate_count": candidate_count,
                "pool_candidate_count": pool_candidate_count,
                "deduped_count": max(candidate_count - pool_candidate_count, 0),
                "failed_count": failed_count,
                "top_candidate_factor_ids": top_candidate_factor_ids,
            }
        )
        upsert_record("candidate_batches", candidate_batch_id, updated)
        _ = event_store.append(
            event_type="candidate_pool.batch_completed",
            payload={
                "candidate_batch_id": candidate_batch_id,
                "candidate_count": candidate_count,
                "pool_candidate_count": pool_candidate_count,
                "failed_count": failed_count,
            },
            run_id=str(updated.get("source_run_id", "")),
        )
        return updated

    async def add_manual_candidate(
        self,
        *,
        factor_spec_version: str | None,
        dsl_expression: str | None,
        candidate_name: str | None,
        source_family: str,
        source_refs: list[str],
        dataset_version_used_for_discovery: str,
        label_spec_version: str,
        protocol_version: str,
        created_by: str,
        spec_version: str | None = None,
        pool_status: str = "proposed",
        tags: Mapping[str, str] | None = None,
        parent_factor_refs: list[str] | None = None,
    ) -> dict[str, object]:
        """Add a manually submitted factor to the candidate pool via a manual batch."""

        existing_spec = (factor_spec_version or "").strip()
        expression = (dsl_expression or "").strip()
        if bool(existing_spec) == bool(expression):
            raise ValidationError(
                "Provide exactly one of factor_spec_version or dsl_expression"
            )
        if pool_status not in _POOL_STATUS_ORDER:
            raise ValidationError(f"Unsupported pool_status: {pool_status}")

        if expression:
            spec = factor_spec_from_dsl(
                expression=expression,
                name=(candidate_name or "manual_dsl_candidate").strip()
                or "manual_dsl_candidate",
                spec_version=spec_version,
                source_family=source_family,
            )
            registered = spec_registry.get_factor_spec_sync(spec.spec_version)
            if registered is None:
                registered = await spec_registry.register_factor_spec(spec)
            spec_payload = {"factor_spec_version": registered.spec_version}
        else:
            registered = spec_registry.get_factor_spec_sync(existing_spec)
            if registered is None:
                raise NotFoundError(f"Factor spec not found: {existing_spec}")
            spec_payload = {"factor_spec_version": registered.spec_version}

        resolved_source_refs = list(dict.fromkeys(source_refs))
        if not resolved_source_refs and dataset_version_used_for_discovery:
            resolved_source_refs = [f"dataset:{dataset_version_used_for_discovery}"]
        batch = self.create_candidate_batch(
            source_run_id=f"manual:{uuid.uuid4()}",
            search_kind="manual",
            template_id="manual_candidate",
            dataset_version_used_for_discovery=dataset_version_used_for_discovery,
            label_spec_version=label_spec_version,
            protocol_version=protocol_version,
            source_family=source_family,
            source_refs=resolved_source_refs,
            search_budget=1,
            top_k=1,
            seed=0,
            created_by=created_by,
        )
        candidate = self.upsert_candidate_from_spec(
            spec=spec_payload,
            source_family=source_family,
            source_refs=resolved_source_refs,
            source_run_id=str(batch["source_run_id"]),
            candidate_batch_id=str(batch["candidate_batch_id"]),
            created_by=created_by,
            pool_status=pool_status,
        )
        candidate = factor_asset_service.synchronize_candidate(
            candidate=candidate,
            manual_tags=tags,
            parent_factor_refs=parent_factor_refs or [],
            assigned_by=created_by,
        )
        duplicate_status = (
            "unique"
            if str(candidate.get("first_seen_batch_id"))
            == str(batch["candidate_batch_id"])
            else "duplicate"
        )
        member = self.record_batch_member(
            candidate_batch_id=str(batch["candidate_batch_id"]),
            candidate_factor_id=str(candidate["candidate_factor_id"]),
            factor_spec_version=str(candidate["factor_spec_version"]),
            rank_order=1,
            duplicate_status=duplicate_status,
            source_family=source_family,
        )
        completed_batch = self.finalize_candidate_batch(
            candidate_batch_id=str(batch["candidate_batch_id"]),
            candidate_count=1,
            pool_candidate_count=1,
            failed_count=0,
            top_candidate_factor_ids=[str(candidate["candidate_factor_id"])],
        )
        _ = event_store.append(
            event_type="candidate_pool.manual_added",
            payload={
                "candidate_factor_id": str(candidate["candidate_factor_id"]),
                "candidate_batch_id": str(batch["candidate_batch_id"]),
                "factor_spec_version": str(candidate["factor_spec_version"]),
                "duplicate_status": duplicate_status,
            },
            run_id=str(batch["source_run_id"]),
        )
        return {
            "candidate": candidate,
            "candidate_batch": completed_batch,
            "member": member,
        }

    def get_candidate(self, candidate_factor_id: str) -> dict[str, object]:
        candidate = get_record("candidate_pool_factors", candidate_factor_id)
        if candidate is None:
            raise NotFoundError(
                f"Candidate pool factor not found: {candidate_factor_id}"
            )
        return dict(candidate)

    def list_candidates(
        self,
        *,
        pool_status: str | None = None,
        source_family: str | None = None,
        factor_spec_version: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        records: list[dict[str, object]] = []
        for record in runtime_state_store.load()["candidate_pool_factors"].values():
            if (
                pool_status is not None
                and str(record.get("pool_status")) != pool_status
            ):
                continue
            if (
                source_family is not None
                and str(record.get("source_family")) != source_family
            ):
                continue
            if (
                factor_spec_version is not None
                and str(record.get("factor_spec_version")) != factor_spec_version
            ):
                continue
            records.append(dict(record))
        ordered = sorted(
            records, key=lambda item: str(item.get("latest_seen_at", "")), reverse=True
        )
        return {
            "candidates": ordered[offset : offset + limit],
            "total": len(ordered),
            "filters": {
                "pool_status": pool_status,
                "source_family": source_family,
                "factor_spec_version": factor_spec_version,
                "limit": str(limit),
                "offset": str(offset),
            },
        }

    def list_batches(
        self,
        *,
        source_run_id: str | None = None,
        dataset_version: str | None = None,
    ) -> dict[str, object]:
        batches: list[dict[str, object]] = []
        for record in runtime_state_store.load()["candidate_batches"].values():
            if (
                source_run_id is not None
                and str(record.get("source_run_id")) != source_run_id
            ):
                continue
            if (
                dataset_version is not None
                and str(record.get("dataset_version_used_for_discovery"))
                != dataset_version
            ):
                continue
            batches.append(dict(record))
        ordered = sorted(
            batches, key=lambda item: str(item.get("created_at", "")), reverse=True
        )
        return {
            "candidate_batches": ordered,
            "total": len(ordered),
            "filters": {
                "source_run_id": source_run_id,
                "dataset_version": dataset_version,
            },
        }

    def get_batch_detail(self, candidate_batch_id: str) -> dict[str, object]:
        batch = get_record("candidate_batches", candidate_batch_id)
        if batch is None:
            raise NotFoundError(f"Candidate batch not found: {candidate_batch_id}")
        members = [
            dict(record)
            for record in runtime_state_store.load()["candidate_batch_members"].values()
            if str(record.get("candidate_batch_id")) == candidate_batch_id
        ]
        return {
            "candidate_batch": dict(batch),
            "members": sorted(
                members, key=lambda item: int(str(item.get("rank_order", 0)))
            ),
        }

    def _score_summary_from_evaluation_run(
        self, evaluation_run_id: str
    ) -> dict[str, object]:
        snapshot: dict[str, object] = {}
        for artifact in runtime_state_store.list_artifacts_for_run(evaluation_run_id):
            if str(artifact.get("artifact_type")) == "run_record_snapshot":
                snapshot = artifact_payload(artifact)
                break
        result_summary = _object_dict(snapshot.get("result_summary", {}))
        raw_summary = _object_dict(snapshot.get("raw_result_summary", {}))
        return {
            "score": _float_from_object(result_summary.get("score", 0.0)),
            "coverage_ratio": _float_from_object(
                result_summary.get("coverage_ratio", 0.0)
            ),
            "observation_count": int(
                _float_from_object(result_summary.get("observation_count", 0))
            ),
            "period_count": int(
                _float_from_object(result_summary.get("period_count", 0))
            ),
            "rank_ic_mean": _float_from_object(raw_summary.get("rank_ic_mean", 0.0)),
            "ic_mean": _float_from_object(raw_summary.get("ic_mean", 0.0)),
        }

    @staticmethod
    def _verdict_for_score(score_summary: Mapping[str, object]) -> str:
        observation_count = int(
            _float_from_object(score_summary.get("observation_count", 0))
        )
        coverage_ratio = _float_from_object(score_summary.get("coverage_ratio", 0.0))
        score = _float_from_object(score_summary.get("score", 0.0))
        rank_ic_mean = _float_from_object(score_summary.get("rank_ic_mean", 0.0))
        if observation_count <= 0 or coverage_ratio <= 0:
            return "insufficient"
        if score > 0 and rank_ic_mean >= 0:
            return "positive"
        if score < 0 and rank_ic_mean < 0:
            return "negative"
        return "mixed"

    def record_validation_claim_from_run(
        self,
        *,
        candidate_factor_id: str,
        evaluation_run_id: str,
        created_by: str,
    ) -> dict[str, object]:
        candidate = self.get_candidate(candidate_factor_id)
        run = get_record("runs", evaluation_run_id)
        if run is None:
            raise NotFoundError(f"Evaluation run not found: {evaluation_run_id}")
        if str(run.get("run_type")) != "factor_evaluation":
            raise ValidationError("Validation claims require factor_evaluation runs")
        factor_spec_version = str(run.get("factor_spec_version", ""))
        if factor_spec_version != str(candidate.get("factor_spec_version", "")):
            raise ValidationError(
                "Evaluation run factor_spec_version does not match candidate"
            )
        factor_spec = spec_registry.get_factor_spec_sync(factor_spec_version)
        dataset_version = str(run.get("dataset_version", ""))
        source_family = str(
            run.get("source_family")
            or source_family_for_dataset_version(dataset_version)
        )
        score_summary = self._score_summary_from_evaluation_run(evaluation_run_id)
        validation_kernel_report: dict[str, object] = {}
        factor_frame_source_refs: list[str] = []
        for artifact in runtime_state_store.list_artifacts_for_run(evaluation_run_id):
            if str(artifact.get("artifact_type")) == "validation_kernel_report":
                validation_kernel_report = artifact_payload(artifact)
            if str(artifact.get("artifact_type")) == "factor_frame":
                factor_frame = artifact_payload(artifact)
                factor_frame_source_refs = _string_list(
                    factor_frame.get("source_refs", [])
                )
        source_refs = _dedupe_string_refs(
            [
                *source_refs_for_dataset_version(dataset_version),
                *_string_list(candidate.get("source_refs", [])),
                *_string_list(candidate.get("discovery_source_refs", [])),
                *(factor_spec.source_refs if factor_spec is not None else []),
                *factor_frame_source_refs,
            ]
        )
        validation_kernel_blocked = bool(
            validation_kernel_report.get("validation_blocked", False)
        )
        declared_temporal_integrity_summary = _object_dict(
            validation_kernel_report.get("temporal_integrity_report", {})
        )
        temporal_evaluation_contract = _object_dict(
            validation_kernel_report.get("temporal_evaluation_contract", {})
        )
        temporal_integrity_summary = validate_temporal_evaluation_contract(
            temporal_evaluation_contract
        )
        temporal_report_mismatch = (
            declared_temporal_integrity_summary != temporal_integrity_summary
        )
        temporal_promotion_eligible = bool(
            not temporal_report_mismatch
            and temporal_integrity_summary.get("status") == "eligible"
            and temporal_integrity_summary.get("stage") in {"validation", "lockbox"}
        )
        verdict = (
            "blocked"
            if validation_kernel_blocked or not temporal_promotion_eligible
            else self._verdict_for_score(score_summary)
        )
        evidence_artifact_ids = [
            artifact_id
            for artifact_type in (
                "eval_report",
                "eval_metrics_table",
                "validation_kernel_report",
                "oos_statistics_report",
                "risk_exposure_report",
                "run_record_snapshot",
            )
            if (artifact_id := find_first_artifact_id(evaluation_run_id, artifact_type))
        ]
        claim = ValidationClaimRecord(
            validation_claim_id=str(uuid.uuid4()),
            candidate_factor_id=candidate_factor_id,
            factor_spec_version=factor_spec_version,
            dataset_version=dataset_version,
            dataset_fingerprint=sha256_hash({"dataset_version": dataset_version})[:16],
            label_spec_version=str(run.get("label_spec_version", "")),
            protocol_version=str(run.get("protocol_version", "")),
            source_family=source_family,
            source_refs=source_refs,
            evaluation_run_id=evaluation_run_id,
            verdict=verdict,
            claim_status="pending_review",
            score_summary=score_summary,
            oos_summary=_object_dict(validation_kernel_report.get("oos_summary", {})),
            risk_exposure_summary=_object_dict(
                validation_kernel_report.get("risk_exposure_summary", {})
            ),
            temporal_integrity_summary=temporal_integrity_summary,
            evidence_artifact_ids=evidence_artifact_ids,
            preprocessing_config=_object_dict(run.get("preprocessing_config", {})),
            neutralization_config=_object_dict(run.get("neutralization_config", {})),
            created_at=utcnow(),
            created_by=created_by,
            updated_at=utcnow(),
        )
        upsert_record("validation_claims", claim.validation_claim_id, claim.to_dict())
        _ = event_store.append(
            event_type="validation_claim.created",
            payload={
                "validation_claim_id": claim.validation_claim_id,
                "candidate_factor_id": candidate_factor_id,
                "dataset_version": dataset_version,
                "verdict": claim.verdict,
                "claim_status": claim.claim_status,
                "temporal_integrity_status": temporal_integrity_summary.get(
                    "status", "missing"
                ),
                "temporal_integrity_stage": temporal_integrity_summary.get(
                    "stage", "missing"
                ),
            },
            run_id=evaluation_run_id,
        )
        return claim.to_dict()

    async def submit_candidate_validation(
        self,
        *,
        candidate_factor_id: str,
        dataset_version: str,
        label_spec_version: str,
        protocol_version: str,
        policy_pack: str,
        code_version: str,
        seed: int,
        principal_id: str,
        source_family: str | None = None,
        preprocessing_config: Mapping[str, object] | None = None,
        neutralization_config: Mapping[str, object] | None = None,
        selection_context: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        candidate = self.get_candidate(candidate_factor_id)
        evaluation = await factor_evaluation_service.submit_evaluation(
            dataset_version=dataset_version,
            factor_spec_version=str(candidate["factor_spec_version"]),
            preprocess_spec_version="",
            label_spec_version=label_spec_version,
            protocol_version=protocol_version,
            policy_pack=policy_pack,
            code_version=code_version,
            seed=seed,
            principal_id=principal_id,
            source_family=source_family or str(candidate.get("source_family", "")),
            preprocessing_config=preprocessing_config,
            neutralization_config=neutralization_config,
            selection_context=selection_context,
        )
        claim = self.record_validation_claim_from_run(
            candidate_factor_id=candidate_factor_id,
            evaluation_run_id=str(evaluation["run_id"]),
            created_by=principal_id,
        )
        return {
            **evaluation,
            "validation_claim_id": str(claim["validation_claim_id"]),
            "candidate_factor_id": candidate_factor_id,
            "verdict": str(claim["verdict"]),
            "claim_status": str(claim["claim_status"]),
        }

    def get_validation_claim(self, validation_claim_id: str) -> dict[str, object]:
        claim = get_record("validation_claims", validation_claim_id)
        if claim is None:
            raise NotFoundError(f"Validation claim not found: {validation_claim_id}")
        return dict(claim)

    def list_validation_claims(
        self,
        *,
        candidate_factor_id: str | None = None,
        dataset_version: str | None = None,
        claim_status: str | None = None,
    ) -> dict[str, object]:
        claims: list[dict[str, object]] = []
        for record in runtime_state_store.load()["validation_claims"].values():
            if (
                candidate_factor_id is not None
                and str(record.get("candidate_factor_id")) != candidate_factor_id
            ):
                continue
            if (
                dataset_version is not None
                and str(record.get("dataset_version")) != dataset_version
            ):
                continue
            if (
                claim_status is not None
                and str(record.get("claim_status")) != claim_status
            ):
                continue
            claims.append(dict(record))
        ordered = sorted(
            claims, key=lambda item: str(item.get("created_at", "")), reverse=True
        )
        return {
            "validation_claims": ordered,
            "total": len(ordered),
            "filters": {
                "candidate_factor_id": candidate_factor_id,
                "dataset_version": dataset_version,
                "claim_status": claim_status,
            },
        }

    def validation_matrix(
        self,
        *,
        candidate_factor_id: str | None = None,
        dataset_version: str | None = None,
    ) -> dict[str, object]:
        claims = cast(
            list[dict[str, object]],
            self.list_validation_claims(
                candidate_factor_id=candidate_factor_id,
                dataset_version=dataset_version,
            )["validation_claims"],
        )
        cells = [
            {
                "candidate_factor_id": claim["candidate_factor_id"],
                "dataset_version": claim["dataset_version"],
                "label_spec_version": claim["label_spec_version"],
                "protocol_version": claim["protocol_version"],
                "verdict": claim["verdict"],
                "claim_status": claim["claim_status"],
                "validation_claim_id": claim["validation_claim_id"],
            }
            for claim in claims
        ]
        return {"cells": cells, "total": len(cells)}

    def transition_validation_claim(
        self,
        *,
        validation_claim_id: str,
        new_status: str,
        operator_id: str,
        reason: str,
    ) -> dict[str, object]:
        if new_status not in _VALID_CLAIM_STATUSES:
            raise ValidationError(f"Unsupported validation claim status: {new_status}")
        if not reason.strip():
            raise ValidationError("reason is required")
        claim = self.get_validation_claim(validation_claim_id)
        previous_status = str(claim.get("claim_status", ""))
        if previous_status in {"rejected", "superseded", "expired"}:
            raise ConflictError(f"Validation claim is terminal: {previous_status}")
        if new_status == "approved" and str(claim.get("verdict")) in {
            "insufficient",
            "blocked",
        }:
            raise ValidationError("insufficient or blocked claims cannot be approved")
        updated = dict(claim)
        updated["claim_status"] = new_status
        updated["updated_at"] = utcnow()
        updated["review_reason"] = reason
        if new_status == "approved":
            updated["approved_by"] = operator_id
            updated["approved_at"] = updated["updated_at"]
        upsert_record("validation_claims", validation_claim_id, updated)
        _ = event_store.append(
            event_type="validation_claim.status_changed",
            payload={
                "validation_claim_id": validation_claim_id,
                "previous_status": previous_status,
                "new_status": new_status,
                "reason": reason,
            },
            run_id=str(updated.get("evaluation_run_id", "")),
        )
        return {
            "validation_claim_id": validation_claim_id,
            "previous_status": previous_status,
            "new_status": new_status,
            "updated_at": str(updated["updated_at"]),
        }

    def activate_effective_factor(
        self,
        *,
        validation_claim_id: str,
        effective_name: str | None,
        activated_by: str,
        approval_request_id: str | None = None,
        materialization_policy: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        claim = self.get_validation_claim(validation_claim_id)
        if str(claim.get("claim_status")) != "approved":
            raise ValidationError(
                "Effective factors require an approved validation claim"
            )
        if str(claim.get("verdict")) not in {"positive", "mixed"}:
            raise ValidationError(
                "Effective factors require positive or mixed validation evidence"
            )
        candidate = self.get_candidate(str(claim["candidate_factor_id"]))
        factor_spec_version = str(claim.get("factor_spec_version", ""))
        factor_spec = spec_registry.get_factor_spec_sync(factor_spec_version)
        source_refs = _dedupe_string_refs(
            [
                *_string_list(claim.get("source_refs", [])),
                *_string_list(candidate.get("source_refs", [])),
                *_string_list(candidate.get("discovery_source_refs", [])),
                *(factor_spec.source_refs if factor_spec is not None else []),
            ]
        )
        effective = EffectiveFactorRecord(
            effective_factor_id=str(uuid.uuid4()),
            candidate_factor_id=str(claim["candidate_factor_id"]),
            validation_claim_id=validation_claim_id,
            evaluation_run_id=str(claim["evaluation_run_id"]),
            dataset_version=str(claim["dataset_version"]),
            dataset_fingerprint=str(claim["dataset_fingerprint"]),
            label_spec_version=str(claim["label_spec_version"]),
            protocol_version=str(claim["protocol_version"]),
            source_family=str(claim["source_family"]),
            effective_name=effective_name
            or (
                f"{candidate.get('candidate_name', claim['factor_spec_version'])}:"
                f"{claim['dataset_version']}"
            ),
            activation_status="active",
            approval_request_id=approval_request_id or "",
            activated_at=utcnow(),
            activated_by=activated_by,
            materialization_policy=dict(materialization_policy or {}),
            score_summary=_object_dict(claim.get("score_summary", {})),
            evidence_artifact_ids=_string_list(claim.get("evidence_artifact_ids", [])),
            factor_spec_version=factor_spec_version,
            source_refs=source_refs,
            factor_type=factor_spec.factor_type if factor_spec is not None else "",
            materialized_frame_ref=(
                factor_spec.materialized_frame_ref if factor_spec is not None else ""
            ),
        )
        upsert_record(
            "effective_factors", effective.effective_factor_id, effective.to_dict()
        )
        _ = event_store.append(
            event_type="effective_factor.activated",
            payload={
                "effective_factor_id": effective.effective_factor_id,
                "candidate_factor_id": effective.candidate_factor_id,
                "validation_claim_id": validation_claim_id,
                "dataset_version": effective.dataset_version,
            },
            run_id=str(claim.get("evaluation_run_id", "")),
        )
        return factor_asset_service.synchronize_effective(
            effective=effective.to_dict(),
            assigned_by=activated_by,
        )

    def list_effective_factors(
        self,
        *,
        dataset_version: str | None = None,
        activation_status: str | None = None,
    ) -> dict[str, object]:
        records: list[dict[str, object]] = []
        for record in runtime_state_store.load()["effective_factors"].values():
            if (
                dataset_version is not None
                and str(record.get("dataset_version")) != dataset_version
            ):
                continue
            if (
                activation_status is not None
                and str(record.get("activation_status")) != activation_status
            ):
                continue
            records.append(dict(record))
        ordered = sorted(
            records, key=lambda item: str(item.get("activated_at", "")), reverse=True
        )
        return {
            "effective_factors": ordered,
            "total": len(ordered),
            "filters": {
                "dataset_version": dataset_version,
                "activation_status": activation_status,
            },
        }

    def get_effective_factor(self, effective_factor_id: str) -> dict[str, object]:
        record = get_record("effective_factors", effective_factor_id)
        if record is None:
            raise NotFoundError(f"Effective factor not found: {effective_factor_id}")
        return dict(record)

    def transition_effective_factor(
        self,
        *,
        effective_factor_id: str,
        new_status: str,
        operator_id: str,
        reason: str,
        replacement_effective_factor_id: str | None = None,
    ) -> dict[str, object]:
        if new_status not in _ACTIVE_EFFECTIVE_STATUSES:
            raise ValidationError(f"Unsupported effective factor status: {new_status}")
        if not reason.strip():
            raise ValidationError("reason is required")
        record = self.get_effective_factor(effective_factor_id)
        previous_status = str(record.get("activation_status", ""))
        updated = dict(record)
        updated["activation_status"] = new_status
        if new_status in {"retired", "revoked", "superseded"}:
            updated["retired_at"] = utcnow()
        if replacement_effective_factor_id:
            updated["replacement_effective_factor_id"] = replacement_effective_factor_id
        upsert_record("effective_factors", effective_factor_id, updated)
        lifecycle_id = str(uuid.uuid4())
        lifecycle_event: dict[str, object] = {
            "factor_lifecycle_event_id": lifecycle_id,
            "effective_factor_id": effective_factor_id,
            "previous_status": previous_status,
            "new_status": new_status,
            "operator_id": operator_id,
            "reason": reason,
            "created_at": utcnow(),
        }
        upsert_record("factor_lifecycle_events", lifecycle_id, lifecycle_event)
        _ = event_store.append(
            event_type="effective_factor.status_changed",
            payload=lifecycle_event,
            run_id=str(record.get("evaluation_run_id", "")),
        )
        return lifecycle_event

    def _approved_factor_admission_request(
        self,
        *,
        approval_request_id: str,
        effective_factor_id: str,
    ) -> dict[str, object]:
        request = get_record("approval_requests", approval_request_id)
        if request is None:
            raise NotFoundError(f"Approval request not found: {approval_request_id}")
        if str(request.get("request_type")) != "factor_admission":
            raise ValidationError(
                "approval_request_id must refer to a factor_admission request"
            )
        if str(request.get("status")) != "approved":
            raise ValidationError(
                "Admitted factors require an approved factor_admission request"
            )
        expected_target_ref = f"effective_factor:{effective_factor_id}"
        if str(request.get("target_ref")) != expected_target_ref:
            raise ValidationError(
                "factor_admission target_ref must match " + expected_target_ref
            )
        requester_id = str(request.get("requester_id", ""))
        for decision in runtime_state_store.load()["approval_decisions"].values():
            if str(decision.get("approval_request_id")) != approval_request_id:
                continue
            if str(decision.get("decision")) != "approved":
                continue
            if requester_id and str(decision.get("reviewer_id")) == requester_id:
                raise ConflictError(
                    "Requester cannot approve their own factor_admission request"
                )
        return dict(request)

    def admit_factor(
        self,
        *,
        effective_factor_id: str,
        approval_request_id: str,
        admitted_by: str,
        admitted_name: str | None = None,
        release_policy: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        effective = self.get_effective_factor(effective_factor_id)
        if str(effective.get("activation_status")) != "active":
            raise ValidationError("Only active effective factors can be admitted")
        for record in runtime_state_store.load()["admitted_factors"].values():
            if str(record.get("effective_factor_id")) == effective_factor_id and str(
                record.get("admission_status")
            ) not in {"retired", "revoked"}:
                raise ConflictError(
                    "Effective factor is already admitted: "
                    + str(record.get("admitted_factor_id"))
                )

        _ = self._approved_factor_admission_request(
            approval_request_id=approval_request_id,
            effective_factor_id=effective_factor_id,
        )
        admitted = AdmittedFactorRecord(
            admitted_factor_id=str(uuid.uuid4()),
            effective_factor_id=effective_factor_id,
            candidate_factor_id=str(effective["candidate_factor_id"]),
            validation_claim_id=str(effective["validation_claim_id"]),
            evaluation_run_id=str(effective["evaluation_run_id"]),
            dataset_version=str(effective["dataset_version"]),
            dataset_fingerprint=str(effective["dataset_fingerprint"]),
            label_spec_version=str(effective["label_spec_version"]),
            protocol_version=str(effective["protocol_version"]),
            source_family=str(effective["source_family"]),
            admitted_name=admitted_name
            or str(effective.get("effective_name") or effective_factor_id),
            admission_status="admitted",
            approval_request_id=approval_request_id,
            admitted_at=utcnow(),
            admitted_by=admitted_by,
            score_summary=_object_dict(effective.get("score_summary", {})),
            evidence_artifact_ids=_string_list(
                effective.get("evidence_artifact_ids", [])
            ),
            release_policy=dict(release_policy or {}),
            factor_spec_version=str(effective.get("factor_spec_version", "")),
            source_refs=_string_list(effective.get("source_refs", [])),
            factor_type=str(effective.get("factor_type", "")),
            materialized_frame_ref=str(effective.get("materialized_frame_ref", "")),
        )
        upsert_record(
            "admitted_factors",
            admitted.admitted_factor_id,
            admitted.to_dict(),
        )
        lifecycle_id = str(uuid.uuid4())
        lifecycle_event: dict[str, object] = {
            "admitted_factor_lifecycle_event_id": lifecycle_id,
            "admitted_factor_id": admitted.admitted_factor_id,
            "effective_factor_id": effective_factor_id,
            "previous_status": "",
            "new_status": admitted.admission_status,
            "operator_id": admitted_by,
            "reason": "factor admitted through approved factor_admission request",
            "approval_request_id": approval_request_id,
            "created_at": admitted.admitted_at,
        }
        upsert_record(
            "admitted_factor_lifecycle_events",
            lifecycle_id,
            lifecycle_event,
        )
        _ = event_store.append(
            event_type="admitted_factor.admitted",
            payload={
                "admitted_factor_id": admitted.admitted_factor_id,
                "effective_factor_id": effective_factor_id,
                "approval_request_id": approval_request_id,
            },
            run_id=str(effective.get("evaluation_run_id", "")),
        )
        return factor_asset_service.synchronize_admitted(
            admitted=admitted.to_dict(),
            assigned_by=admitted_by,
        )

    def list_admitted_factors(
        self,
        *,
        dataset_version: str | None = None,
        admission_status: str | None = None,
    ) -> dict[str, object]:
        records: list[dict[str, object]] = []
        for record in runtime_state_store.load()["admitted_factors"].values():
            if (
                dataset_version is not None
                and str(record.get("dataset_version")) != dataset_version
            ):
                continue
            if (
                admission_status is not None
                and str(record.get("admission_status")) != admission_status
            ):
                continue
            records.append(dict(record))
        ordered = sorted(
            records, key=lambda item: str(item.get("admitted_at", "")), reverse=True
        )
        return {
            "admitted_factors": ordered,
            "total": len(ordered),
            "filters": {
                "dataset_version": dataset_version,
                "admission_status": admission_status,
            },
        }

    def get_admitted_factor(self, admitted_factor_id: str) -> dict[str, object]:
        record = get_record("admitted_factors", admitted_factor_id)
        if record is None:
            raise NotFoundError(f"Admitted factor not found: {admitted_factor_id}")
        return dict(record)

    def transition_admitted_factor(
        self,
        *,
        admitted_factor_id: str,
        new_status: str,
        operator_id: str,
        reason: str,
        replacement_admitted_factor_id: str | None = None,
    ) -> dict[str, object]:
        if new_status not in _ADMITTED_FACTOR_STATUSES:
            raise ValidationError(f"Unsupported admitted factor status: {new_status}")
        if not reason.strip():
            raise ValidationError("reason is required")
        record = self.get_admitted_factor(admitted_factor_id)
        previous_status = str(record.get("admission_status", ""))
        updated = dict(record)
        updated["admission_status"] = new_status
        if new_status in {"retired", "revoked", "superseded"}:
            updated["retired_at"] = utcnow()
        if replacement_admitted_factor_id:
            updated["replacement_admitted_factor_id"] = replacement_admitted_factor_id
        upsert_record("admitted_factors", admitted_factor_id, updated)
        lifecycle_id = str(uuid.uuid4())
        lifecycle_event: dict[str, object] = {
            "admitted_factor_lifecycle_event_id": lifecycle_id,
            "admitted_factor_id": admitted_factor_id,
            "effective_factor_id": str(record.get("effective_factor_id", "")),
            "previous_status": previous_status,
            "new_status": new_status,
            "operator_id": operator_id,
            "reason": reason,
            "created_at": utcnow(),
        }
        upsert_record(
            "admitted_factor_lifecycle_events",
            lifecycle_id,
            lifecycle_event,
        )
        _ = event_store.append(
            event_type="admitted_factor.status_changed",
            payload=lifecycle_event,
            run_id=str(record.get("evaluation_run_id", "")),
        )
        return lifecycle_event

    def reset(self) -> None:
        return None


candidate_asset_service = CandidateAssetService()
