# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnusedCallResult=false
"""Latent factor Phase 1 domain and artifact contracts.

This module deliberately stops before numeric cluster discovery.  It owns the
repo-native records, frame schema checks, leakage gates, source-family boundary,
and artifact-backed matrix/exposure manifests required before later clustering,
interpretation, and CandidateFactor handoff work can safely build on them.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time
from typing import Final, Literal, cast

from factor_lab.core.errors import ValidationError
from factor_lab.core.hashing import sha256_hash
from factor_lab.core.runtime_records import (
    artifact_payload,
    get_record,
    materialize_artifact,
    upsert_record,
    utcnow,
)
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.core.source_universe import (
    PRICE_VOLUME_SOURCE_FAMILY,
    validate_source_family,
)
from factor_lab.factor_engine.models.factor_spec import FactorSpec
from factor_lab.governance.services.event_store import event_store

LatentMembershipRole = Literal["core", "edge", "inverse", "none", "noise"]
LatentFactorType = Literal[
    "theme",
    "regime",
    "inverse_theme",
    "event_window",
    "basket_timing",
]
SimilarityMode = Literal["dense", "sparse_top_k"]

LATENT_ARTIFACT_SCHEMA_VERSION: Final[str] = "latent_factor_phase1@1.0"
MATERIALIZED_FACTOR_TYPE: Final[str] = "materialized_frame"
LATENT_CONSTRUCTION_METHOD: Final[str] = "latent_cluster"
DEFAULT_DENSE_UNIVERSE_CAP: Final[int] = 100

_ALLOWED_MEMBERSHIP_ROLES: Final[frozenset[str]] = frozenset(
    {"core", "edge", "inverse", "none", "noise"}
)
_ALLOWED_LATENT_FACTOR_TYPES: Final[frozenset[str]] = frozenset(
    {"theme", "regime", "inverse_theme", "event_window", "basket_timing"}
)
_ALLOWED_HORIZONS: Final[frozenset[str]] = frozenset(
    {"intraday", "short", "medium", "long"}
)
_REQUIRED_EXPOSURE_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "date",
        "timestamp",
        "asset_id",
        "symbol",
        "factor_spec_version",
        "latent_factor_id",
        "latent_factor_version",
        "factor_value",
        "exposure",
        "confidence",
        "membership_role",
        "as_of_date",
        "available_at",
        "frequency",
        "view",
        "source_family",
        "source_refs",
    }
)


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} is required")
    return text


def _string_list(value: object, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"{field_name} must be a list")
    return [str(item) for item in cast(list[object], value)]


def _object_dict(value: object | None) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    typed = cast(Mapping[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _float_value(value: object, *, field_name: str) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be numeric") from exc


def _parse_instant(value: object, *, field_name: str) -> datetime:
    text = _required_text(value, field_name=field_name).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text)
        except ValueError as exc:
            raise ValidationError(f"{field_name} must be ISO date/datetime") from exc
        parsed = datetime.combine(parsed_date, time.min)
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _validate_source_family_is_latent_mvp(value: object, *, context: str) -> str:
    source_family = validate_source_family(value, context=context)
    if source_family != PRICE_VOLUME_SOURCE_FAMILY:
        raise ValidationError(
            "MVP latent factors must keep source_family=price_volume",
            details={
                "reason_code": "E_LATENT_MVP_SOURCE_FAMILY_REQUIRED",
                "source_family": source_family,
                "required_source_family": PRICE_VOLUME_SOURCE_FAMILY,
            },
        )
    return source_family


@dataclass(slots=True)
class LatentDiscoveryRunRecord:
    run_id: str
    universe_ref: str
    start_date: str
    end_date: str
    feature_set_version: str
    similarity_method: str
    cluster_method: str
    neutralization_policy: str
    dataset_versions: list[str]
    seed: int
    search_budget: int
    source_family: str
    source_refs: list[str]
    status: str
    created_at: str
    created_by: str
    failure_reasons: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LatentFeatureSetRecord:
    feature_set_version: str
    name: str
    feature_families: list[str]
    parameters: dict[str, object]
    created_at: str
    created_by: str
    description: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LatentClusterCandidateRecord:
    cluster_id: str
    run_id: str
    cluster_rank: int
    member_count: int
    core_assets: list[str]
    inverse_assets: list[str]
    cohesion_score: float
    separation_score: float
    stability_score: float
    explicit_overlap: dict[str, object]
    representative_series_ref: str
    metric_mode: str
    status: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LatentFactorDefinitionRecord:
    latent_factor_id: str
    name: str
    description: str
    thesis: str
    horizon: str
    latent_factor_type: str
    source_cluster_ids: list[str]
    created_by: str
    created_at: str
    naming_time: str
    status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LatentFactorVersionRecord:
    latent_factor_version: str
    latent_factor_id: str
    prototype_method: str
    exposure_method: str
    training_window: int
    rolling_window: int
    neutralization_policy: str
    feature_set_version: str
    valid_from: str
    valid_to: str
    status: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class LatentFactorContractService:
    """Phase 1 contract service for latent factor records and artifacts."""

    def create_feature_set(
        self,
        *,
        name: str,
        feature_families: Sequence[str],
        created_by: str,
        feature_set_version: str | None = None,
        parameters: Mapping[str, object] | None = None,
        description: str = "",
    ) -> dict[str, object]:
        cleaned_name = _required_text(name, field_name="name")
        families = [
            _required_text(item, field_name="feature_family")
            for item in feature_families
        ]
        if not families:
            raise ValidationError("feature_families must not be empty")
        feature_digest = sha256_hash({"name": cleaned_name, "families": families})[:16]
        version = feature_set_version or f"lfs_{feature_digest}@1.0"
        record = LatentFeatureSetRecord(
            feature_set_version=version,
            name=cleaned_name,
            feature_families=families,
            parameters=_object_dict(parameters),
            description=description,
            created_at=utcnow(),
            created_by=_required_text(created_by, field_name="created_by"),
        ).to_dict()
        upsert_record("latent_feature_sets", version, record)
        _ = event_store.append(
            event_type="latent_feature_set.upserted",
            payload={"feature_set_version": version, "feature_families": families},
        )
        return record

    def create_discovery_run(
        self,
        *,
        universe_ref: str,
        start_date: str,
        end_date: str,
        feature_set_version: str,
        similarity_method: str,
        cluster_method: str,
        neutralization_policy: str,
        dataset_versions: Sequence[str],
        seed: int,
        search_budget: int,
        source_refs: Sequence[str],
        created_by: str,
        source_family: str = PRICE_VOLUME_SOURCE_FAMILY,
        status: str = "planned",
    ) -> dict[str, object]:
        _ = _parse_instant(start_date, field_name="start_date")
        if _parse_instant(end_date, field_name="end_date") < _parse_instant(
            start_date, field_name="start_date"
        ):
            raise ValidationError("end_date must be on or after start_date")
        if search_budget < 1:
            raise ValidationError("search_budget must be positive")
        family = _validate_source_family_is_latent_mvp(
            source_family, context="latent_discovery_run.source_family"
        )
        record = LatentDiscoveryRunRecord(
            run_id=_uuid("ldr"),
            universe_ref=_required_text(universe_ref, field_name="universe_ref"),
            start_date=_required_text(start_date, field_name="start_date"),
            end_date=_required_text(end_date, field_name="end_date"),
            feature_set_version=_required_text(
                feature_set_version, field_name="feature_set_version"
            ),
            similarity_method=_required_text(
                similarity_method, field_name="similarity_method"
            ),
            cluster_method=_required_text(cluster_method, field_name="cluster_method"),
            neutralization_policy=_required_text(
                neutralization_policy, field_name="neutralization_policy"
            ),
            dataset_versions=[str(item) for item in dataset_versions],
            seed=int(seed),
            search_budget=int(search_budget),
            source_family=family,
            source_refs=[str(item) for item in source_refs],
            status=status,
            created_at=utcnow(),
            created_by=_required_text(created_by, field_name="created_by"),
        ).to_dict()
        if not record["dataset_versions"]:
            raise ValidationError("dataset_versions must not be empty")
        upsert_record("latent_discovery_runs", str(record["run_id"]), record)
        _ = event_store.append(
            event_type="latent_discovery_run.created",
            payload={"run_id": str(record["run_id"]), "status": status},
            run_id=str(record["run_id"]),
        )
        return record

    def create_cluster_candidate(
        self,
        *,
        run_id: str,
        cluster_rank: int,
        core_assets: Sequence[str],
        inverse_assets: Sequence[str] = (),
        cohesion_score: float = 0.0,
        separation_score: float = 0.0,
        stability_score: float = 0.0,
        explicit_overlap: Mapping[str, object] | None = None,
        representative_series_ref: str = "",
        metric_mode: str = "dense",
        status: str = "raw",
    ) -> dict[str, object]:
        if get_record("latent_discovery_runs", run_id) is None:
            raise ValidationError(f"latent discovery run not found: {run_id}")
        core = [_required_text(item, field_name="core_asset") for item in core_assets]
        if not core:
            raise ValidationError("core_assets must not be empty")
        inverse = [str(item) for item in inverse_assets]
        cluster_digest = sha256_hash(
            {"run_id": run_id, "rank": cluster_rank, "core": core}
        )[:20]
        cluster_id = f"lcc_{cluster_digest}"
        record = LatentClusterCandidateRecord(
            cluster_id=cluster_id,
            run_id=run_id,
            cluster_rank=int(cluster_rank),
            member_count=len(set([*core, *inverse])),
            core_assets=core,
            inverse_assets=inverse,
            cohesion_score=float(cohesion_score),
            separation_score=float(separation_score),
            stability_score=float(stability_score),
            explicit_overlap=_object_dict(explicit_overlap),
            representative_series_ref=representative_series_ref,
            metric_mode=_required_text(metric_mode, field_name="metric_mode"),
            status=status,
            created_at=utcnow(),
        ).to_dict()
        upsert_record("latent_cluster_candidates", cluster_id, record)
        _ = event_store.append(
            event_type="latent_cluster_candidate.created",
            payload={"cluster_id": cluster_id, "run_id": run_id},
            run_id=run_id,
        )
        return record

    def materialize_membership_frame(
        self,
        *,
        run_id: str,
        cluster_id: str,
        rows: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        if get_record("latent_cluster_candidates", cluster_id) is None:
            raise ValidationError(f"latent cluster candidate not found: {cluster_id}")
        normalized_rows: list[dict[str, object]] = []
        for index, row in enumerate(rows):
            role = _required_text(row.get("role"), field_name=f"rows[{index}].role")
            if role not in _ALLOWED_MEMBERSHIP_ROLES:
                raise ValidationError(f"Unsupported membership role: {role}")
            normalized_rows.append(
                {
                    "run_id": run_id,
                    "cluster_id": cluster_id,
                    "asset_id": _required_text(
                        row.get("asset_id"), field_name=f"rows[{index}].asset_id"
                    ),
                    "membership_score": _float_value(
                        row.get("membership_score"),
                        field_name=f"rows[{index}].membership_score",
                    ),
                    "role": role,
                    "rank_in_cluster": int(str(row.get("rank_in_cluster", index + 1))),
                }
            )
        if not normalized_rows:
            raise ValidationError("membership frame rows must not be empty")
        artifact = materialize_artifact(
            run_id,
            "latent_cluster_membership_frame",
            {
                "schema_version": LATENT_ARTIFACT_SCHEMA_VERSION,
                "run_id": run_id,
                "cluster_id": cluster_id,
                "rows": normalized_rows,
            },
        )
        frame_id = f"lcmf_{artifact.artifact_id}"
        record: dict[str, object] = {
            "membership_frame_id": frame_id,
            "run_id": run_id,
            "cluster_id": cluster_id,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
            "row_count": len(normalized_rows),
            "created_at": utcnow(),
        }
        upsert_record("latent_cluster_membership_frames", frame_id, record)
        return record

    def materialize_similarity_matrix(
        self,
        *,
        run_id: str,
        universe_size: int,
        similarities: Sequence[Mapping[str, object]],
        dense_universe_cap: int = DEFAULT_DENSE_UNIVERSE_CAP,
        sparse_top_k: int | None = None,
        capacity_diagnostics: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        if universe_size < 1:
            raise ValidationError("universe_size must be positive")
        if dense_universe_cap < 1:
            raise ValidationError("dense_universe_cap must be positive")
        normalized_edges = [
            self._normalize_similarity_edge(item) for item in similarities
        ]
        if universe_size > dense_universe_cap:
            if sparse_top_k is None or sparse_top_k < 1:
                raise ValidationError(
                    (
                        "Latent similarity matrix exceeds dense cap; "
                        "configure sparse_top_k"
                    ),
                    details={
                        "reason_code": "E_LATENT_MATRIX_DENSE_CAP_EXCEEDED",
                        "universe_size": universe_size,
                        "dense_universe_cap": dense_universe_cap,
                    },
                )
            mode: SimilarityMode = "sparse_top_k"
            artifact_edges = self._sparse_top_k_edges(
                normalized_edges, top_k=sparse_top_k
            )
        else:
            mode = "dense"
            artifact_edges = normalized_edges
        diagnostics = {
            **_object_dict(capacity_diagnostics),
            "universe_size": universe_size,
            "dense_universe_cap": dense_universe_cap,
            "sparse_top_k": sparse_top_k,
            "actual_edge_count": len(artifact_edges),
            "degraded_to_sparse": mode == "sparse_top_k",
            "failure_reason_code": "",
        }

        artifact = materialize_artifact(
            run_id,
            "latent_similarity_matrix",
            {
                "schema_version": LATENT_ARTIFACT_SCHEMA_VERSION,
                "run_id": run_id,
                "mode": mode,
                "universe_size": universe_size,
                "dense_universe_cap": dense_universe_cap,
                "sparse_top_k": sparse_top_k,
                "edge_count": len(artifact_edges),
                "capacity_diagnostics": diagnostics,
                "edges": artifact_edges,
            },
        )
        matrix_id = f"lsm_{artifact.artifact_id}"
        record: dict[str, object] = {
            "matrix_id": matrix_id,
            "run_id": run_id,
            "mode": mode,
            "universe_size": universe_size,
            "dense_universe_cap": dense_universe_cap,
            "sparse_top_k": sparse_top_k,
            "edge_count": len(artifact_edges),
            "capacity_diagnostics": diagnostics,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
            "created_at": utcnow(),
        }
        upsert_record("latent_similarity_matrices", matrix_id, record)
        return record

    def _normalize_similarity_edge(
        self, edge: Mapping[str, object]
    ) -> dict[str, object]:
        return {
            "asset_i": _required_text(edge.get("asset_i"), field_name="asset_i"),
            "asset_j": _required_text(edge.get("asset_j"), field_name="asset_j"),
            "similarity": _float_value(edge.get("similarity"), field_name="similarity"),
            "component": str(
                edge.get("component", edge.get("similarity_component", "total"))
                or "total"
            ),
        }

    def _sparse_top_k_edges(
        self,
        edges: Sequence[Mapping[str, object]],
        *,
        top_k: int,
    ) -> list[dict[str, object]]:
        by_asset: dict[str, list[dict[str, object]]] = defaultdict(list)
        for edge in edges:
            edge_dict = dict(edge)
            by_asset[str(edge_dict["asset_i"])].append(edge_dict)
            by_asset[str(edge_dict["asset_j"])].append(edge_dict)
        selected: dict[str, dict[str, object]] = {}
        for asset_edges in by_asset.values():
            ranked = sorted(
                asset_edges,
                key=lambda item: abs(float(str(item["similarity"]))),
                reverse=True,
            )[:top_k]
            for item in ranked:
                left = str(item["asset_i"])
                right = str(item["asset_j"])
                key = "|".join(sorted((left, right))) + f"|{item['component']}"
                selected[key] = dict(item)
        return sorted(
            selected.values(),
            key=lambda item: (
                str(item["asset_i"]),
                str(item["asset_j"]),
                str(item["component"]),
            ),
        )

    def create_factor_definition(
        self,
        *,
        source_cluster_ids: Sequence[str],
        name: str,
        thesis: str,
        horizon: str,
        latent_factor_type: str,
        created_by: str,
        naming_time: str,
        description: str = "",
        status: str = "research",
    ) -> dict[str, object]:
        clusters = [
            _required_text(item, field_name="source_cluster_id")
            for item in source_cluster_ids
        ]
        if not clusters:
            raise ValidationError("source_cluster_ids must not be empty")
        for cluster_id in clusters:
            cluster = get_record("latent_cluster_candidates", cluster_id)
            if cluster is None:
                raise ValidationError(
                    f"latent cluster candidate not found: {cluster_id}"
                )
            run = get_record("latent_discovery_runs", str(cluster.get("run_id", "")))
            if run is not None:
                _ = self.validate_leakage_windows(
                    discovery_end=str(run.get("end_date", "")),
                    naming_time=naming_time,
                    validation_start=None,
                )
        if horizon not in _ALLOWED_HORIZONS:
            raise ValidationError(f"Unsupported latent factor horizon: {horizon}")
        if latent_factor_type not in _ALLOWED_LATENT_FACTOR_TYPES:
            raise ValidationError(
                f"Unsupported latent_factor_type: {latent_factor_type}"
            )
        latent_factor_id = (
            f"lf_{sha256_hash({'name': name, 'clusters': clusters})[:20]}"
        )
        record = LatentFactorDefinitionRecord(
            latent_factor_id=latent_factor_id,
            name=_required_text(name, field_name="name"),
            description=description,
            thesis=_required_text(thesis, field_name="thesis"),
            horizon=horizon,
            latent_factor_type=latent_factor_type,
            source_cluster_ids=clusters,
            created_by=_required_text(created_by, field_name="created_by"),
            created_at=utcnow(),
            naming_time=_required_text(naming_time, field_name="naming_time"),
            status=status,
        ).to_dict()
        upsert_record("latent_factor_definitions", latent_factor_id, record)
        _ = event_store.append(
            event_type="latent_factor_definition.created",
            payload={
                "latent_factor_id": latent_factor_id,
                "source_cluster_ids": clusters,
            },
        )
        return record

    def create_factor_version(
        self,
        *,
        latent_factor_id: str,
        prototype_method: str,
        exposure_method: str,
        training_window: int,
        rolling_window: int,
        neutralization_policy: str,
        feature_set_version: str,
        valid_from: str,
        valid_to: str = "",
        status: str = "research",
    ) -> dict[str, object]:
        definition = get_record("latent_factor_definitions", latent_factor_id)
        if definition is None:
            raise ValidationError(
                f"latent factor definition not found: {latent_factor_id}"
            )
        if training_window < 1 or rolling_window < 1:
            raise ValidationError("training_window and rolling_window must be positive")
        version_digest = sha256_hash(
            {
                "prototype": prototype_method,
                "exposure": exposure_method,
                "training_window": training_window,
                "window": rolling_window,
                "neutralization_policy": neutralization_policy,
                "feature_set_version": feature_set_version,
            }
        )[:8]
        version_id = f"{latent_factor_id}@{version_digest}"
        record = LatentFactorVersionRecord(
            latent_factor_version=version_id,
            latent_factor_id=latent_factor_id,
            prototype_method=_required_text(
                prototype_method, field_name="prototype_method"
            ),
            exposure_method=_required_text(
                exposure_method, field_name="exposure_method"
            ),
            training_window=int(training_window),
            rolling_window=int(rolling_window),
            neutralization_policy=_required_text(
                neutralization_policy, field_name="neutralization_policy"
            ),
            feature_set_version=_required_text(
                feature_set_version, field_name="feature_set_version"
            ),
            valid_from=_required_text(valid_from, field_name="valid_from"),
            valid_to=valid_to,
            status=status,
            created_at=utcnow(),
        ).to_dict()
        upsert_record("latent_factor_versions", version_id, record)
        return record

    def materialize_exposure_frame(
        self,
        *,
        run_id: str,
        latent_factor_version: str,
        factor_spec_version: str,
        rows: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        if get_record("latent_factor_versions", latent_factor_version) is None:
            raise ValidationError(
                f"latent factor version not found: {latent_factor_version}"
            )
        normalized_rows = [
            self.validate_exposure_row_contract(row, row_index=index)
            for index, row in enumerate(rows)
        ]
        if not normalized_rows:
            raise ValidationError("exposure frame rows must not be empty")
        artifact = materialize_artifact(
            run_id,
            "latent_factor_exposure_frame",
            {
                "schema_version": LATENT_ARTIFACT_SCHEMA_VERSION,
                "run_id": run_id,
                "latent_factor_version": latent_factor_version,
                "factor_spec_version": factor_spec_version,
                "required_columns": sorted(_REQUIRED_EXPOSURE_COLUMNS),
                "rows": normalized_rows,
            },
        )
        exposure_frame_id = f"lfef_{artifact.artifact_id}"
        record: dict[str, object] = {
            "exposure_frame_id": exposure_frame_id,
            "run_id": run_id,
            "latent_factor_version": latent_factor_version,
            "factor_spec_version": factor_spec_version,
            "row_count": len(normalized_rows),
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
            "created_at": utcnow(),
        }
        upsert_record("latent_factor_exposure_frames", exposure_frame_id, record)
        return record

    def validate_exposure_row_contract(
        self,
        row: Mapping[str, object],
        *,
        row_index: int = 0,
    ) -> dict[str, object]:
        missing = sorted(key for key in _REQUIRED_EXPOSURE_COLUMNS if key not in row)
        if missing:
            raise ValidationError(
                "latent exposure row is missing FactorFrame-compatible fields",
                details={
                    "reason_code": "E_LATENT_EXPOSURE_ROW_SCHEMA",
                    "row_index": row_index,
                    "missing_fields": missing,
                },
            )
        role = _required_text(row.get("membership_role"), field_name="membership_role")
        if role not in _ALLOWED_MEMBERSHIP_ROLES:
            raise ValidationError(f"Unsupported membership_role: {role}")
        source_family = _validate_source_family_is_latent_mvp(
            row.get("source_family"),
            context="latent_factor_exposure_frame.source_family",
        )
        factor_value = _float_value(row.get("factor_value"), field_name="factor_value")
        exposure = _float_value(row.get("exposure"), field_name="exposure")
        if abs(factor_value - exposure) > 1e-12:
            raise ValidationError(
                "factor_value must equal exposure for latent exposure exports",
                details={"reason_code": "E_LATENT_FACTOR_VALUE_MISMATCH"},
            )
        confidence = _float_value(row.get("confidence"), field_name="confidence")
        if confidence < 0.0 or confidence > 1.0:
            raise ValidationError("confidence must be in [0, 1]")
        timestamp = _parse_instant(row.get("timestamp"), field_name="timestamp")
        available_at = _parse_instant(
            row.get("available_at"), field_name="available_at"
        )
        if available_at > timestamp:
            raise ValidationError(
                "latent exposure row available_at must be <= timestamp",
                details={
                    "reason_code": "E_LATENT_EXPOSURE_NOT_AVAILABLE",
                    "row_index": row_index,
                    "timestamp": str(row.get("timestamp")),
                    "available_at": str(row.get("available_at")),
                },
            )
        source_refs = _string_list(row.get("source_refs"), field_name="source_refs")
        return {
            "date": _required_text(row.get("date"), field_name="date"),
            "timestamp": _required_text(row.get("timestamp"), field_name="timestamp"),
            "asset_id": _required_text(row.get("asset_id"), field_name="asset_id"),
            "symbol": _required_text(row.get("symbol"), field_name="symbol"),
            "factor_spec_version": _required_text(
                row.get("factor_spec_version"), field_name="factor_spec_version"
            ),
            "latent_factor_id": _required_text(
                row.get("latent_factor_id"), field_name="latent_factor_id"
            ),
            "latent_factor_version": _required_text(
                row.get("latent_factor_version"), field_name="latent_factor_version"
            ),
            "factor_value": factor_value,
            "exposure": exposure,
            "confidence": confidence,
            "membership_role": role,
            "as_of_date": _required_text(
                row.get("as_of_date"), field_name="as_of_date"
            ),
            "available_at": _required_text(
                row.get("available_at"), field_name="available_at"
            ),
            "frequency": _required_text(row.get("frequency"), field_name="frequency"),
            "view": _required_text(row.get("view"), field_name="view"),
            "source_family": source_family,
            "source_refs": source_refs,
        }

    def validate_leakage_windows(
        self,
        *,
        discovery_end: str,
        naming_time: str,
        validation_start: str | None,
    ) -> dict[str, object]:
        discovery_end_at = _parse_instant(discovery_end, field_name="discovery_end")
        naming_at = _parse_instant(naming_time, field_name="naming_time")
        if discovery_end_at > naming_at:
            raise ValidationError(
                "discovery_window.end must be <= naming_time",
                details={"reason_code": "E_LATENT_DISCOVERY_AFTER_NAMING"},
            )
        if validation_start:
            validation_at = _parse_instant(
                validation_start, field_name="validation_start"
            )
            if validation_at <= naming_at:
                raise ValidationError(
                    "validation_window.start must be > naming_time",
                    details={"reason_code": "E_LATENT_VALIDATION_BEFORE_NAMING"},
                )
        return {
            "discovery_end": discovery_end,
            "naming_time": naming_time,
            "validation_start": validation_start or "",
            "gate_status": "passed",
        }

    def build_materialized_factor_spec(
        self,
        *,
        exposure_frame_id: str,
        latent_factor_version: str,
        name: str,
        description: str = "",
    ) -> FactorSpec:
        frame_record = get_record("latent_factor_exposure_frames", exposure_frame_id)
        if frame_record is None:
            raise ValidationError(
                f"latent exposure frame not found: {exposure_frame_id}"
            )
        version_record = get_record("latent_factor_versions", latent_factor_version)
        if version_record is None:
            raise ValidationError(
                f"latent factor version not found: {latent_factor_version}"
            )
        definition = (
            get_record(
                "latent_factor_definitions",
                str(version_record.get("latent_factor_id", "")),
            )
            or {}
        )
        spec_version = str(
            frame_record.get("factor_spec_version") or f"fac_{exposure_frame_id}@1.0"
        )
        return FactorSpec(
            spec_id=spec_version,
            spec_version=spec_version,
            name=_required_text(name, field_name="name"),
            description=description,
            factor_type=MATERIALIZED_FACTOR_TYPE,
            materialized_frame_ref=f"latent_factor_exposure_frame:{exposure_frame_id}",
            value_column="factor_value",
            input_schema={
                "frame_type": "latent_factor_exposure_frame",
                "required_columns": sorted(_REQUIRED_EXPOSURE_COLUMNS),
            },
            output_schema={"value_column": "factor_value"},
            source_family=PRICE_VOLUME_SOURCE_FAMILY,
            source_refs=[f"latent_factor_exposure_frame:{exposure_frame_id}"],
            input_field_lineage={
                "factor_value": f"latent_factor_version:{latent_factor_version}",
                "exposure": f"latent_factor_version:{latent_factor_version}",
            },
            tags={
                "construction_method": LATENT_CONSTRUCTION_METHOD,
                "latent_factor_type": str(
                    definition.get("latent_factor_type", "theme")
                ),
                "source_family": PRICE_VOLUME_SOURCE_FAMILY,
            },
        )

    def build_factor_card(
        self,
        *,
        latent_factor_id: str,
        generated_by: str,
    ) -> dict[str, object]:
        definition = get_record("latent_factor_definitions", latent_factor_id)
        if definition is None:
            raise ValidationError(
                f"latent factor definition not found: {latent_factor_id}"
            )
        versions = [
            dict(record)
            for record in runtime_state_store.load()["latent_factor_versions"].values()
            if str(record.get("latent_factor_id")) == latent_factor_id
        ]
        source_clusters = _string_list(
            definition.get("source_cluster_ids"), field_name="source_cluster_ids"
        )
        card_id = f"lfc_{latent_factor_id}"
        record: dict[str, object] = {
            "latent_factor_card_id": card_id,
            "latent_factor_id": latent_factor_id,
            "name": str(definition.get("name", "")),
            "thesis": str(definition.get("thesis", "")),
            "horizon": str(definition.get("horizon", "")),
            "latent_factor_type": str(definition.get("latent_factor_type", "")),
            "source_cluster_ids": source_clusters,
            "latest_versions": versions,
            "governance_status": str(definition.get("status", "research")),
            "evidence_refs": [
                f"latent_cluster_candidate:{item}" for item in source_clusters
            ],
            "generated_at": utcnow(),
            "generated_by": _required_text(generated_by, field_name="generated_by"),
        }
        upsert_record("latent_factor_cards", card_id, record)
        return record

    def artifact_payload_for_record(
        self, record: Mapping[str, object]
    ) -> dict[str, object]:
        artifact_id = str(record.get("artifact_id", ""))
        if not artifact_id:
            return {}
        artifact = get_record("artifacts", artifact_id)
        if artifact is None:
            return {}
        return artifact_payload(artifact)


latent_factor_contract_service = LatentFactorContractService()
