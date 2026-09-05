# pyright: reportAny=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Phase 4 latent exposure materialization and governance handoff service.

This service keeps the Phase 4 bridge deliberately deterministic:

* no ML/clustering dependency is added;
* numeric exposures are derived only from PIT daily price rows;
* rows-only materializations are allowed for tests/prototypes but are blocked
  from governance handoff;
* the handoff stops at Candidate + ValidationClaim pending review.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from math import sqrt
from typing import Final, cast

from factor_lab.candidate_assets.services.candidate_asset_service import (
    candidate_asset_service,
)
from factor_lab.core.errors import (
    ConflictError,
    GateBlockedError,
    NotFoundError,
    ValidationError,
)
from factor_lab.core.hashing import sha256_hash
from factor_lab.core.runtime_records import (
    get_record,
    materialize_artifact,
    upsert_record,
    utcnow,
)
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.core.source_universe import PRICE_VOLUME_SOURCE_FAMILY
from factor_lab.factor_engine.models.factor_spec import FactorSpec
from factor_lab.factor_engine.repositories.spec_registry import spec_registry
from factor_lab.governance.services.event_store import event_store
from factor_lab.latent.services.daily_event_window_clustering_service import (
    latent_daily_event_window_clustering_service,
)
from factor_lab.latent.services.latent_factor_contract_service import (
    LATENT_CONSTRUCTION_METHOD,
    latent_factor_contract_service,
)

LATENT_EXPOSURE_ENGINE_VERSION: Final[str] = "latent_exposure_materialization@1.0"
DEFAULT_ROLLING_WINDOW: Final[int] = 20
DEFAULT_MIN_PERIODS: Final[int] = 2
DEFAULT_FEATURE_SET_VERSION: Final[str] = "latent_feature_return_corr@1.0"
DEFAULT_POLICY_PACK: Final[str] = "policy_pack_p0_default@1.0"


@dataclass(slots=True)
class _PricePoint:
    asset_id: str
    symbol: str
    date_key: str
    timestamp: str
    available_at: str
    close: float


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} is required")
    return text


def _float_from_object(value: object, *, field_name: str) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be numeric") from exc


def _date_key(value: object, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name)
    return text.split("T", maxsplit=1)[0]


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


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = _mean(left)
    right_mean = _mean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)
    )
    left_var = sum((x - left_mean) ** 2 for x in left)
    right_var = sum((y - right_mean) ** 2 for y in right)
    denominator = sqrt(left_var * right_var)
    if denominator == 0.0:
        return None
    return max(min(numerator / denominator, 1.0), -1.0)


def _clip01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def _spec_content_signature(spec: FactorSpec) -> dict[str, object]:
    """Return the materialized-frame identity fields used for idempotency."""

    return {
        "factor_type": spec.factor_type,
        "materialized_frame_ref": spec.materialized_frame_ref,
        "value_column": spec.value_column,
        "source_family": spec.source_family,
        "source_refs": sorted(spec.source_refs),
        "input_field_lineage": dict(spec.input_field_lineage),
        "tags": dict(spec.tags),
    }


class LatentExposureMaterializationService:
    """Materialize interpreted latent factors into exposure frames."""

    def _definition(self, latent_factor_id: str) -> dict[str, object]:
        definition = get_record("latent_factor_definitions", latent_factor_id)
        if definition is None:
            raise NotFoundError(
                f"latent factor definition not found: {latent_factor_id}"
            )
        if str(definition.get("status", "")) != "research":
            raise ValidationError("latent factor must be in research status")
        return dict(definition)

    def _clusters_for_definition(
        self, definition: Mapping[str, object]
    ) -> list[dict[str, object]]:
        cluster_ids = _string_list(definition.get("source_cluster_ids"))
        clusters: list[dict[str, object]] = []
        for cluster_id in cluster_ids:
            cluster = get_record("latent_cluster_candidates", cluster_id)
            if cluster is None:
                raise NotFoundError(f"latent cluster candidate not found: {cluster_id}")
            clusters.append(dict(cluster))
        if not clusters:
            raise ValidationError("latent factor definition has no source clusters")
        return clusters

    @staticmethod
    def _feature_set_version(clusters: Sequence[Mapping[str, object]]) -> str:
        for cluster in clusters:
            run = get_record("latent_discovery_runs", str(cluster.get("run_id", "")))
            if run is not None and str(run.get("feature_set_version", "")).strip():
                return str(run["feature_set_version"])
        return DEFAULT_FEATURE_SET_VERSION

    @staticmethod
    def _source_run_id(clusters: Sequence[Mapping[str, object]]) -> str:
        for cluster in clusters:
            run_id = str(cluster.get("run_id", "")).strip()
            if run_id:
                return run_id
        return f"latent_materialize:{uuid.uuid4()}"

    @staticmethod
    def _core_and_inverse_assets(
        clusters: Sequence[Mapping[str, object]]
    ) -> tuple[list[str], list[str], dict[str, str]]:
        core_assets: list[str] = []
        inverse_assets: list[str] = []
        role_by_asset: dict[str, str] = {}
        for cluster in clusters:
            for asset_id in _string_list(cluster.get("core_assets")):
                if asset_id not in core_assets:
                    core_assets.append(asset_id)
                role_by_asset[asset_id] = "core"
            for asset_id in _string_list(cluster.get("inverse_assets")):
                if asset_id not in inverse_assets:
                    inverse_assets.append(asset_id)
                _ = role_by_asset.setdefault(asset_id, "inverse")
        if not core_assets:
            raise ValidationError("latent source clusters must include core assets")
        return core_assets, inverse_assets, role_by_asset

    @staticmethod
    def _cluster_stability(clusters: Sequence[Mapping[str, object]]) -> float:
        values = [
            _float_from_object(
                cluster.get("stability_score", 1.0),
                field_name="stability_score",
            )
            for cluster in clusters
        ]
        return _clip01(_mean(values) if values else 1.0)

    def _load_rows(
        self,
        *,
        rows: Sequence[Mapping[str, object]] | None,
        dataset_version: str | None,
    ) -> tuple[list[dict[str, object]], str, str, bool]:
        if rows is not None:
            materialize_rows = [dict(row) for row in rows]
            if not materialize_rows:
                raise ValidationError("rows must not be empty")
            return (
                materialize_rows,
                dataset_version or "inline_daily_pit_rows@adhoc",
                "rows",
                False,
            )
        if not dataset_version:
            raise ValidationError("dataset_version or rows is required")
        load_dataset_rows = (
            latent_daily_event_window_clustering_service.load_dataset_rows
        )
        materialize_rows = load_dataset_rows(dataset_version)
        if not materialize_rows:
            raise ValidationError("dataset_version contains no materialization rows")
        return materialize_rows, dataset_version, "dataset_version", True

    @staticmethod
    def _price_points(
        rows: Sequence[Mapping[str, object]],
        *,
        start_date: str | None,
        end_date: str | None,
    ) -> dict[str, dict[str, _PricePoint]]:
        by_asset_date: dict[str, dict[str, _PricePoint]] = defaultdict(dict)
        start_key = _date_key(start_date, field_name="start_date") if start_date else ""
        end_key = _date_key(end_date, field_name="end_date") if end_date else ""
        for index, row in enumerate(rows):
            try:
                asset_id = _required_text(
                    row.get("asset_id") or row.get("symbol"),
                    field_name=f"rows[{index}].asset_id",
                )
                timestamp_value = (
                    row.get("timestamp")
                    or row.get("trade_date")
                    or row.get("date")
                    or row.get("asof_date")
                )
                point_date = _date_key(
                    timestamp_value,
                    field_name=f"rows[{index}].timestamp",
                )
                if start_key and point_date < start_key:
                    continue
                if end_key and point_date > end_key:
                    continue
                close = _float_from_object(
                    row.get("close"), field_name=f"rows[{index}].close"
                )
                if close <= 0.0:
                    continue
                timestamp = str(timestamp_value)
                available_at = str(row.get("available_at") or timestamp)
                by_asset_date[asset_id][point_date] = _PricePoint(
                    asset_id=asset_id,
                    symbol=str(row.get("symbol") or asset_id),
                    date_key=point_date,
                    timestamp=timestamp,
                    available_at=available_at,
                    close=close,
                )
            except ValidationError:
                raise
        if not by_asset_date:
            raise ValidationError("no eligible daily PIT price rows in window")
        return by_asset_date

    @staticmethod
    def _returns_by_asset(
        points_by_asset: Mapping[str, Mapping[str, _PricePoint]]
    ) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, str]]]:
        returns: dict[str, dict[str, float]] = {}
        availability: dict[str, dict[str, str]] = {}
        for asset_id, points_by_date in points_by_asset.items():
            ordered = sorted(points_by_date.values(), key=lambda point: point.date_key)
            asset_returns: dict[str, float] = {}
            asset_availability: dict[str, str] = {}
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if previous.close <= 0.0:
                    continue
                asset_returns[current.date_key] = current.close / previous.close - 1.0
                asset_availability[current.date_key] = current.available_at
            returns[asset_id] = asset_returns
            availability[asset_id] = asset_availability
        return returns, availability

    @staticmethod
    def _prototype_returns(
        returns_by_asset: Mapping[str, Mapping[str, float]],
        core_assets: Sequence[str],
    ) -> dict[str, float]:
        by_date: dict[str, list[float]] = defaultdict(list)
        for asset_id in core_assets:
            for return_date, value in returns_by_asset.get(asset_id, {}).items():
                by_date[return_date].append(value)
        return {
            return_date: _mean(values)
            for return_date, values in by_date.items()
            if values
        }

    @staticmethod
    def _max_available_at(
        availability_by_asset: Mapping[str, Mapping[str, str]],
        *,
        sample_dates: Sequence[str],
        asset_id: str,
        core_assets: Sequence[str],
    ) -> str:
        instants: list[tuple[datetime, str]] = []
        for return_date in sample_dates:
            for candidate_asset in (asset_id, *core_assets):
                available_at = availability_by_asset.get(candidate_asset, {}).get(
                    return_date
                )
                if not available_at:
                    continue
                instants.append(
                    (
                        _parse_instant(available_at, field_name="available_at"),
                        available_at,
                    )
                )
        if not instants:
            return sample_dates[-1] if sample_dates else ""
        return max(instants, key=lambda item: item[0])[1]

    def _build_exposure_rows(
        self,
        *,
        definition: Mapping[str, object],
        version: Mapping[str, object],
        clusters: Sequence[Mapping[str, object]],
        input_rows: Sequence[Mapping[str, object]],
        dataset_version: str,
        source_mode: str,
        factor_spec_version: str,
        start_date: str | None,
        end_date: str | None,
        rolling_window: int,
        min_periods: int,
    ) -> list[dict[str, object]]:
        if rolling_window < 2:
            raise ValidationError("rolling_window must be >= 2")
        if min_periods < 2:
            raise ValidationError("min_periods must be >= 2")
        if min_periods > rolling_window:
            raise ValidationError("min_periods must be <= rolling_window")

        points_by_asset = self._price_points(
            input_rows,
            start_date=start_date,
            end_date=end_date,
        )
        returns_by_asset, availability_by_asset = self._returns_by_asset(
            points_by_asset
        )
        core_assets, _inverse_assets, role_by_asset = self._core_and_inverse_assets(
            clusters
        )
        missing_core = [
            asset_id for asset_id in core_assets if asset_id not in returns_by_asset
        ]
        if missing_core:
            raise ValidationError(
                "core assets are missing from materialization rows",
                details={"missing_core_assets": missing_core},
            )
        prototype_by_date = self._prototype_returns(returns_by_asset, core_assets)
        if len(prototype_by_date) < min_periods:
            raise ValidationError("prototype has insufficient return observations")

        all_dates = sorted(
            {
                point.date_key
                for values in points_by_asset.values()
                for point in values.values()
            }
        )
        all_return_dates = sorted(prototype_by_date)
        stability = self._cluster_stability(clusters)
        source_refs = list(
            dict.fromkeys(
                [
                    f"dataset:{dataset_version}",
                    *[
                        f"latent_cluster_candidate:{cluster['cluster_id']}"
                        for cluster in clusters
                        if cluster.get("cluster_id")
                    ],
                    f"latent_factor_definition:{definition['latent_factor_id']}",
                    f"latent_factor_version:{version['latent_factor_version']}",
                ]
            )
        )
        if source_mode == "rows":
            source_refs.insert(0, "rows:inline_daily_pit_rows@adhoc")

        rows: list[dict[str, object]] = []
        latent_factor_id = str(definition["latent_factor_id"])
        latent_factor_version = str(version["latent_factor_version"])
        for current_date in all_dates:
            prior_dates = [
                return_date
                for return_date in all_return_dates
                if return_date < current_date
            ]
            if len(prior_dates) < min_periods:
                continue
            for asset_id, points_by_date in sorted(points_by_asset.items()):
                point = points_by_date.get(current_date)
                if point is None:
                    continue
                sample_dates = [
                    return_date
                    for return_date in prior_dates[-rolling_window:]
                    if return_date in returns_by_asset.get(asset_id, {})
                    and return_date in prototype_by_date
                ]
                if len(sample_dates) < min_periods:
                    continue
                asset_values = [
                    returns_by_asset[asset_id][return_date]
                    for return_date in sample_dates
                ]
                prototype_values = [
                    prototype_by_date[return_date] for return_date in sample_dates
                ]
                correlation = _pearson(asset_values, prototype_values)
                exposure = 0.0 if correlation is None else correlation
                coverage = _clip01(len(sample_dates) / float(rolling_window))
                confidence = _clip01(coverage * stability)
                available_at = self._max_available_at(
                    availability_by_asset,
                    sample_dates=sample_dates,
                    asset_id=asset_id,
                    core_assets=core_assets,
                )
                available_time = _parse_instant(
                    available_at,
                    field_name="available_at",
                )
                timestamp_time = _parse_instant(
                    point.timestamp,
                    field_name="timestamp",
                )
                if available_time > timestamp_time:
                    raise ValidationError(
                        "next-bar latent exposure would leak future data",
                        details={
                            "asset_id": asset_id,
                            "timestamp": point.timestamp,
                            "available_at": available_at,
                        },
                    )
                rows.append(
                    {
                        "date": current_date,
                        "timestamp": point.timestamp,
                        "asset_id": point.asset_id,
                        "symbol": point.symbol,
                        "factor_spec_version": factor_spec_version,
                        "latent_factor_id": latent_factor_id,
                        "latent_factor_version": latent_factor_version,
                        "factor_value": round(exposure, 10),
                        "exposure": round(exposure, 10),
                        "confidence": round(confidence, 10),
                        "membership_role": role_by_asset.get(asset_id, "none"),
                        "as_of_date": sample_dates[-1],
                        "available_at": available_at,
                        "frequency": "1d",
                        "view": "pit_tradable",
                        "source_family": PRICE_VOLUME_SOURCE_FAMILY,
                        "source_refs": source_refs,
                    }
                )
        if not rows:
            raise ValidationError("no latent exposure rows could be materialized")
        return rows

    @staticmethod
    def _default_factor_spec_version(
        *, latent_factor_id: str, dataset_version: str, rolling_window: int
    ) -> str:
        digest = sha256_hash(
            {
                "latent_factor_id": latent_factor_id,
                "dataset_version": dataset_version,
                "rolling_window": rolling_window,
            }
        )[:12]
        return f"fac_latent_exposure_{digest}@1.0"

    @staticmethod
    def _materialization_hash(
        *,
        latent_factor_id: str,
        dataset_version: str,
        source_mode: str,
        start_date: str,
        end_date: str,
        rolling_window: int,
        min_periods: int,
        training_window: int,
        factor_spec_version: str,
        rows: Sequence[Mapping[str, object]],
    ) -> str:
        row_fingerprint = sha256_hash(
            [
                {
                    "asset_id": str(row.get("asset_id") or row.get("symbol") or ""),
                    "timestamp": str(row.get("timestamp") or row.get("date") or ""),
                    "close": str(row.get("close", "")),
                }
                for row in rows
            ]
        )
        return sha256_hash(
            {
                "engine_version": LATENT_EXPOSURE_ENGINE_VERSION,
                "latent_factor_id": latent_factor_id,
                "dataset_version": dataset_version,
                "source_mode": source_mode,
                "start_date": start_date,
                "end_date": end_date,
                "rolling_window": rolling_window,
                "min_periods": min_periods,
                "training_window": training_window,
                "factor_spec_version": factor_spec_version,
                "rows": row_fingerprint,
            }
        )

    @staticmethod
    def _existing_exposure_frame(
        materialization_hash: str,
    ) -> dict[str, object] | None:
        state = runtime_state_store.load()
        for record in state["latent_factor_exposure_frames"].values():
            if str(record.get("materialization_hash", "")) == materialization_hash:
                return dict(record)
        return None

    def materialize_exposures(
        self,
        *,
        latent_factor_id: str,
        dataset_version: str | None = None,
        rows: Sequence[Mapping[str, object]] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        rolling_window: int = DEFAULT_ROLLING_WINDOW,
        min_periods: int = DEFAULT_MIN_PERIODS,
        training_window: int | None = None,
        factor_spec_version: str | None = None,
        created_by: str,
    ) -> dict[str, object]:
        definition = self._definition(latent_factor_id)
        clusters = self._clusters_for_definition(definition)
        (
            input_rows,
            resolved_dataset_version,
            source_mode,
            handoff_allowed,
        ) = self._load_rows(rows=rows, dataset_version=dataset_version)
        resolved_start = start_date or min(
            _date_key(
                row.get("timestamp") or row.get("date") or row.get("asof_date"),
                field_name="timestamp",
            )
            for row in input_rows
        )
        resolved_end = end_date or max(
            _date_key(
                row.get("timestamp") or row.get("date") or row.get("asof_date"),
                field_name="timestamp",
            )
            for row in input_rows
        )
        spec_version = (
            factor_spec_version
            or self._default_factor_spec_version(
                latent_factor_id=latent_factor_id,
                dataset_version=resolved_dataset_version,
                rolling_window=rolling_window,
            )
        )
        version = latent_factor_contract_service.create_factor_version(
            latent_factor_id=latent_factor_id,
            prototype_method="equal_weight_core",
            exposure_method="rolling_corr",
            training_window=int(training_window or rolling_window),
            rolling_window=rolling_window,
            neutralization_policy="raw",
            feature_set_version=self._feature_set_version(clusters),
            valid_from=resolved_start,
            valid_to=resolved_end,
            status="research",
        )
        exposure_rows = self._build_exposure_rows(
            definition=definition,
            version=version,
            clusters=clusters,
            input_rows=input_rows,
            dataset_version=resolved_dataset_version,
            source_mode=source_mode,
            factor_spec_version=spec_version,
            start_date=resolved_start,
            end_date=resolved_end,
            rolling_window=rolling_window,
            min_periods=min_periods,
        )
        materialization_hash = self._materialization_hash(
            latent_factor_id=latent_factor_id,
            dataset_version=resolved_dataset_version,
            source_mode=source_mode,
            start_date=resolved_start,
            end_date=resolved_end,
            rolling_window=rolling_window,
            min_periods=min_periods,
            training_window=int(training_window or rolling_window),
            factor_spec_version=spec_version,
            rows=input_rows,
        )
        existing = self._existing_exposure_frame(materialization_hash)
        if existing is None:
            exposure_frame = latent_factor_contract_service.materialize_exposure_frame(
                run_id=self._source_run_id(clusters),
                latent_factor_version=str(version["latent_factor_version"]),
                factor_spec_version=spec_version,
                rows=exposure_rows,
            )
            exposure_frame = {
                **exposure_frame,
                "engine_version": LATENT_EXPOSURE_ENGINE_VERSION,
                "materialization_hash": materialization_hash,
                "latent_factor_id": latent_factor_id,
                "dataset_version": resolved_dataset_version,
                "source_mode": source_mode,
                "handoff_allowed": handoff_allowed,
                "start_date": resolved_start,
                "end_date": resolved_end,
                "rolling_window": rolling_window,
                "min_periods": min_periods,
                "prototype_method": "equal_weight_core",
                "exposure_method": "rolling_corr",
                "construction_method": LATENT_CONSTRUCTION_METHOD,
                "created_by": created_by,
            }
            upsert_record(
                "latent_factor_exposure_frames",
                str(exposure_frame["exposure_frame_id"]),
                exposure_frame,
            )
        else:
            exposure_frame = existing

        card = latent_factor_contract_service.build_factor_card(
            latent_factor_id=latent_factor_id,
            generated_by=created_by,
        )
        _ = event_store.append(
            event_type="latent_factor_exposure_frame.materialized",
            payload={
                "latent_factor_id": latent_factor_id,
                "latent_factor_version": str(version["latent_factor_version"]),
                "exposure_frame_id": str(exposure_frame["exposure_frame_id"]),
                "row_count": int(str(exposure_frame["row_count"])),
                "source_mode": source_mode,
                "handoff_allowed": handoff_allowed,
            },
            run_id=str(exposure_frame.get("run_id", "")),
        )
        return {
            "latent_factor": definition,
            "factor_version": version,
            "exposure_frame": exposure_frame,
            "factor_card": card,
            "row_count": int(str(exposure_frame["row_count"])),
            "sample_rows": exposure_rows[:5],
            "handoff_allowed": handoff_allowed,
            "source_mode": source_mode,
        }

    def list_versions(self, latent_factor_id: str) -> dict[str, object]:
        if get_record("latent_factor_definitions", latent_factor_id) is None:
            raise NotFoundError(
                f"latent factor definition not found: {latent_factor_id}"
            )
        versions = [
            dict(record)
            for record in runtime_state_store.load()["latent_factor_versions"].values()
            if str(record.get("latent_factor_id", "")) == latent_factor_id
        ]
        return {
            "latent_factor_id": latent_factor_id,
            "versions": sorted(
                versions,
                key=lambda item: (
                    str(item.get("valid_from", "")),
                    str(item.get("latent_factor_version", "")),
                ),
            ),
            "total": len(versions),
        }

    def refresh_exposures(
        self,
        *,
        latent_factor_version: str,
        dataset_version: str | None = None,
        rows: Sequence[Mapping[str, object]] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        rolling_window: int | None = None,
        min_periods: int = DEFAULT_MIN_PERIODS,
        training_window: int | None = None,
        factor_spec_version: str | None = None,
        created_by: str,
    ) -> dict[str, object]:
        source_version = get_record("latent_factor_versions", latent_factor_version)
        if source_version is None:
            raise NotFoundError(
                f"latent factor version not found: {latent_factor_version}"
            )
        latent_factor_id = str(source_version.get("latent_factor_id", ""))
        definition = self._definition(latent_factor_id)
        clusters = self._clusters_for_definition(definition)
        (
            input_rows,
            resolved_dataset_version,
            source_mode,
            handoff_allowed,
        ) = self._load_rows(rows=rows, dataset_version=dataset_version)
        resolved_start = start_date or min(
            _date_key(
                row.get("timestamp") or row.get("date") or row.get("asof_date"),
                field_name="timestamp",
            )
            for row in input_rows
        )
        resolved_end = end_date or max(
            _date_key(
                row.get("timestamp") or row.get("date") or row.get("asof_date"),
                field_name="timestamp",
            )
            for row in input_rows
        )
        resolved_rolling_window = int(
            rolling_window or int(str(source_version.get("rolling_window", 0) or 0))
        )
        if resolved_rolling_window < 1:
            resolved_rolling_window = DEFAULT_ROLLING_WINDOW
        resolved_training_window = int(
            training_window
            or int(
                str(
                    source_version.get("training_window", resolved_rolling_window)
                    or resolved_rolling_window
                )
            )
        )
        spec_version = (
            factor_spec_version
            or self._default_factor_spec_version(
                latent_factor_id=latent_factor_id,
                dataset_version=resolved_dataset_version,
                rolling_window=resolved_rolling_window,
            )
        )
        params_changed = (
            resolved_rolling_window
            != int(str(source_version.get("rolling_window", 0) or 0))
            or resolved_training_window
            != int(str(source_version.get("training_window", 0) or 0))
        )
        if params_changed:
            version = latent_factor_contract_service.create_factor_version(
                latent_factor_id=latent_factor_id,
                prototype_method=str(source_version.get("prototype_method", "")),
                exposure_method=str(source_version.get("exposure_method", "")),
                training_window=resolved_training_window,
                rolling_window=resolved_rolling_window,
                neutralization_policy=str(
                    source_version.get("neutralization_policy", "raw")
                ),
                feature_set_version=str(
                    source_version.get(
                        "feature_set_version",
                        self._feature_set_version(clusters),
                    )
                ),
                valid_from=resolved_start,
                valid_to=resolved_end,
                status=str(source_version.get("status", "research")),
            )
            refresh_mode = "new_version"
        else:
            version = dict(source_version)
            refresh_mode = "same_version_new_frame"

        exposure_rows = self._build_exposure_rows(
            definition=definition,
            version=version,
            clusters=clusters,
            input_rows=input_rows,
            dataset_version=resolved_dataset_version,
            source_mode=source_mode,
            factor_spec_version=spec_version,
            start_date=resolved_start,
            end_date=resolved_end,
            rolling_window=resolved_rolling_window,
            min_periods=min_periods,
        )
        materialization_hash = self._materialization_hash(
            latent_factor_id=latent_factor_id,
            dataset_version=resolved_dataset_version,
            source_mode=source_mode,
            start_date=resolved_start,
            end_date=resolved_end,
            rolling_window=resolved_rolling_window,
            min_periods=min_periods,
            training_window=resolved_training_window,
            factor_spec_version=spec_version,
            rows=input_rows,
        )
        existing = self._existing_exposure_frame(materialization_hash)
        idempotent = existing is not None
        if existing is None:
            exposure_frame = latent_factor_contract_service.materialize_exposure_frame(
                run_id=self._source_run_id(clusters),
                latent_factor_version=str(version["latent_factor_version"]),
                factor_spec_version=spec_version,
                rows=exposure_rows,
            )
            exposure_frame = {
                **exposure_frame,
                "engine_version": LATENT_EXPOSURE_ENGINE_VERSION,
                "materialization_hash": materialization_hash,
                "latent_factor_id": latent_factor_id,
                "dataset_version": resolved_dataset_version,
                "source_mode": source_mode,
                "handoff_allowed": handoff_allowed,
                "start_date": resolved_start,
                "end_date": resolved_end,
                "rolling_window": resolved_rolling_window,
                "min_periods": min_periods,
                "prototype_method": str(version.get("prototype_method", "")),
                "exposure_method": str(version.get("exposure_method", "")),
                "construction_method": LATENT_CONSTRUCTION_METHOD,
                "created_by": created_by,
                "refresh_source_version": latent_factor_version,
                "refresh_mode": refresh_mode,
            }
            upsert_record(
                "latent_factor_exposure_frames",
                str(exposure_frame["exposure_frame_id"]),
                exposure_frame,
            )
        else:
            exposure_frame = existing
        _ = event_store.append(
            event_type="latent_factor_exposure_frame.refreshed",
            payload={
                "latent_factor_id": latent_factor_id,
                "source_version": latent_factor_version,
                "latent_factor_version": str(version["latent_factor_version"]),
                "exposure_frame_id": str(exposure_frame["exposure_frame_id"]),
                "refresh_mode": refresh_mode,
                "idempotent": idempotent,
                "notify_only": False,
            },
            run_id=str(exposure_frame.get("run_id", "")),
        )
        card = latent_factor_contract_service.build_factor_card(
            latent_factor_id=latent_factor_id,
            generated_by=created_by,
        )
        return {
            "latent_factor": definition,
            "source_factor_version": dict(source_version),
            "factor_version": version,
            "exposure_frame": exposure_frame,
            "factor_card": card,
            "row_count": int(str(exposure_frame["row_count"])),
            "sample_rows": exposure_rows[:5],
            "refresh_mode": refresh_mode,
            "idempotent": idempotent,
            "handoff_allowed": handoff_allowed,
            "source_mode": source_mode,
        }

    def select_factor_set(
        self,
        *,
        name: str,
        version_ids: Sequence[str],
        selector_reason: str,
        created_by: str,
    ) -> dict[str, object]:
        versions: list[dict[str, object]] = []
        for version_id in version_ids:
            text = str(version_id or "").strip()
            if not text:
                continue
            version = get_record("latent_factor_versions", text)
            if version is None:
                raise NotFoundError(f"latent factor version not found: {text}")
            versions.append(dict(version))
        if not versions:
            raise ValidationError("version_ids must not be empty")
        ordered_ids = sorted(
            str(version["latent_factor_version"]) for version in versions
        )
        set_id = "lfs_" + sha256_hash({"name": name, "version_ids": ordered_ids})[:20]
        payload = {
            "schema_version": "latent_factor_set_selection@1.0",
            "latent_factor_set_id": set_id,
            "name": name,
            "version_ids": ordered_ids,
            "versions": versions,
            "selector_reason": selector_reason,
            "governance_boundary": {
                "does_not_bypass_handoff": True,
                "candidate_effective_admitted_mutation": False,
            },
            "created_by": created_by,
            "created_at": utcnow(),
        }
        artifact = materialize_artifact(
            "latent_factor_set_selection",
            "latent_factor_set_selection",
            payload,
        )
        record = {
            **payload,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
        }
        upsert_record("latent_factor_sets", set_id, record)
        return {"latent_factor_set": record}

    def factor_card(
        self,
        *,
        latent_factor_id: str,
        generated_by: str,
    ) -> dict[str, object]:
        card = latent_factor_contract_service.build_factor_card(
            latent_factor_id=latent_factor_id,
            generated_by=generated_by,
        )
        state = runtime_state_store.load()
        exposure_frames = [
            dict(record)
            for record in state["latent_factor_exposure_frames"].values()
            if str(record.get("latent_factor_id")) == latent_factor_id
            or str(record.get("latent_factor_version", "")).startswith(
                f"{latent_factor_id}@"
            )
        ]
        factor_specs = []
        for frame in exposure_frames:
            spec_version = str(frame.get("factor_spec_version", ""))
            spec = spec_registry.get_factor_spec_sync(spec_version)
            if spec is not None:
                factor_specs.append(spec.to_dict())
        candidates = []
        validation_claims = []
        spec_versions = {
            str(frame.get("factor_spec_version", "")) for frame in exposure_frames
        }
        for candidate in state["candidate_pool_factors"].values():
            if str(candidate.get("factor_spec_version", "")) in spec_versions:
                candidates.append(dict(candidate))
        candidate_ids = {
            str(candidate.get("candidate_factor_id", "")) for candidate in candidates
        }
        for claim in state["validation_claims"].values():
            if str(claim.get("candidate_factor_id", "")) in candidate_ids:
                validation_claims.append(dict(claim))
        return {
            "factor_card": card,
            "exposure_frames": sorted(
                exposure_frames, key=lambda item: str(item.get("created_at", ""))
            ),
            "factor_specs": factor_specs,
            "candidates": candidates,
            "validation_claims": validation_claims,
            "handoffs": [
                dict(record)
                for record in state["latent_governance_handoffs"].values()
                if str(record.get("latent_factor_id", "")) == latent_factor_id
            ],
        }

    async def register_factor_spec(
        self,
        *,
        exposure_frame_id: str,
        name: str | None = None,
        description: str = "",
    ) -> dict[str, object]:
        frame = get_record("latent_factor_exposure_frames", exposure_frame_id)
        if frame is None:
            raise NotFoundError(
                f"latent exposure frame not found: {exposure_frame_id}"
            )
        latent_factor_version = str(frame.get("latent_factor_version", ""))
        version = get_record("latent_factor_versions", latent_factor_version)
        definition = (
            get_record(
                "latent_factor_definitions",
                str(version.get("latent_factor_id", "")),
            )
            if version is not None
            else None
        )
        spec_name = (
            name
            or (str(definition.get("name", "")) if definition is not None else "")
            or f"latent exposure {exposure_frame_id}"
        )
        spec = latent_factor_contract_service.build_materialized_factor_spec(
            exposure_frame_id=exposure_frame_id,
            latent_factor_version=latent_factor_version,
            name=spec_name,
            description=description
            or "Materialized latent exposure frame for candidate validation.",
        )
        existing = spec_registry.get_factor_spec_sync(spec.spec_version)
        if existing is not None:
            if _spec_content_signature(existing) != _spec_content_signature(spec):
                raise ConflictError(f"FactorSpec conflict for {spec.spec_version}")
            return {
                "factor_spec": existing.to_dict(),
                "created": False,
                "idempotent": True,
                "exposure_frame": dict(frame),
            }
        registered = await spec_registry.register_factor_spec(spec)
        _ = event_store.append(
            event_type="latent_factor_exposure_frame.factor_spec_registered",
            payload={
                "exposure_frame_id": exposure_frame_id,
                "factor_spec_version": registered.spec_version,
                "factor_type": registered.factor_type,
            },
            run_id=str(frame.get("run_id", "")),
        )
        return {
            "factor_spec": registered.to_dict(),
            "created": True,
            "idempotent": False,
            "exposure_frame": dict(frame),
        }

    @staticmethod
    def _handoff_record_id(
        *,
        exposure_frame_id: str,
        dataset_version: str,
        label_spec_version: str,
        protocol_version: str,
    ) -> str:
        digest = sha256_hash(
            {
                "exposure_frame_id": exposure_frame_id,
                "dataset_version": dataset_version,
                "label_spec_version": label_spec_version,
                "protocol_version": protocol_version,
            }
        )[:20]
        return f"lfh_{digest}"

    @staticmethod
    def _upsert_handoff(record: Mapping[str, object]) -> dict[str, object]:
        handoff_id = str(record["handoff_id"])
        upsert_record("latent_governance_handoffs", handoff_id, record)
        return dict(record)

    async def handoff_candidate(
        self,
        *,
        exposure_frame_id: str,
        dataset_version: str | None = None,
        label_spec_version: str,
        protocol_version: str = "eval_daily@1.0",
        policy_pack: str = DEFAULT_POLICY_PACK,
        code_version: str,
        seed: int = 42,
        candidate_name: str | None = None,
        principal_id: str,
        register_if_missing: bool = True,
    ) -> dict[str, object]:
        frame = get_record("latent_factor_exposure_frames", exposure_frame_id)
        if frame is None:
            raise NotFoundError(
                f"latent exposure frame not found: {exposure_frame_id}"
            )
        if str(frame.get("source_mode", "")) != "dataset_version":
            raise ValidationError(
                "rows-only latent exposure frames cannot be handed off"
            )
        resolved_dataset_version = dataset_version or str(
            frame.get("dataset_version", "")
        )
        if not resolved_dataset_version:
            raise ValidationError("dataset_version is required for handoff")
        latent_factor_id = str(frame.get("latent_factor_id", ""))
        handoff_id = self._handoff_record_id(
            exposure_frame_id=exposure_frame_id,
            dataset_version=resolved_dataset_version,
            label_spec_version=label_spec_version,
            protocol_version=protocol_version,
        )
        base_record: dict[str, object] = {
            "handoff_id": handoff_id,
            "status": "running",
            "failed_stage": "",
            "retry_refs": {
                "exposure_frame_id": exposure_frame_id,
                "dataset_version": resolved_dataset_version,
                "label_spec_version": label_spec_version,
                "protocol_version": protocol_version,
            },
            "latent_factor_id": latent_factor_id,
            "exposure_frame_id": exposure_frame_id,
            "dataset_version": resolved_dataset_version,
            "label_spec_version": label_spec_version,
            "protocol_version": protocol_version,
            "policy_pack": policy_pack,
            "code_version": code_version,
            "seed": seed,
            "created_by": principal_id,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        record = self._upsert_handoff(base_record)
        completed: dict[str, object] = {}
        try:
            factor_spec_version = str(frame.get("factor_spec_version", ""))
            factor_spec = spec_registry.get_factor_spec_sync(factor_spec_version)
            if factor_spec is None:
                if not register_if_missing:
                    raise NotFoundError(f"FactorSpec not found: {factor_spec_version}")
                registered = await self.register_factor_spec(
                    exposure_frame_id=exposure_frame_id,
                    name=candidate_name,
                )
                registered_factor_spec = cast(
                    Mapping[str, object],
                    registered["factor_spec"],
                )
                registered_spec_version = str(
                    registered_factor_spec.get("spec_version", "")
                )
                factor_spec = spec_registry.get_factor_spec_sync(
                    registered_spec_version
                )
                if factor_spec is None:
                    raise NotFoundError(f"FactorSpec not found: {factor_spec_version}")
            completed["factor_spec_version"] = factor_spec.spec_version
            record = self._upsert_handoff(
                {
                    **record,
                    **completed,
                    "updated_at": utcnow(),
                    "current_stage": "temporal_routing",
                }
            )
            try:
                from factor_lab.evaluation.services.factor_evaluation_service import (
                    factor_evaluation_service,
                )

                temporal_profile = (
                    factor_evaluation_service.preflight_temporal_direct_regression(
                        dataset_version=resolved_dataset_version,
                        factor_spec_version=factor_spec.spec_version,
                        principal_id=principal_id,
                        source_family=PRICE_VOLUME_SOURCE_FAMILY,
                    )
                )
            except GateBlockedError as exc:
                gate_details = dict(getattr(exc, "details", {}) or {})
                blocked = self._upsert_handoff(
                    {
                        **record,
                        **completed,
                        "status": "blocked_temporal_routing",
                        "current_stage": "temporal_routing",
                        "failed_stage": "temporal_routing",
                        "error": str(exc),
                        "gate_code": str(getattr(exc, "code", "E_GATE_BLOCKED")),
                        "gate_details": gate_details,
                        "updated_at": utcnow(),
                    }
                )
                _ = event_store.append(
                    event_type="latent_factor_exposure_frame.handoff_blocked",
                    payload=blocked,
                    run_id=str(frame.get("run_id", "")),
                )
                return {
                    "handoff": blocked,
                    "factor_spec": factor_spec.to_dict(),
                    "temporal_profile": gate_details,
                    "error": str(exc),
                    "failed_stage": "temporal_routing",
                }
            completed.update(
                {
                    "factor_temporal_profile_id": str(
                        temporal_profile.get("profile_id", "")
                    ),
                    "factor_temporal_class": str(
                        temporal_profile.get("temporal_class", "")
                    ),
                }
            )
            record = self._upsert_handoff(
                {
                    **record,
                    **completed,
                    "updated_at": utcnow(),
                    "current_stage": "candidate_pool",
                }
            )

            candidate_result = await candidate_asset_service.add_manual_candidate(
                factor_spec_version=factor_spec.spec_version,
                dsl_expression=None,
                candidate_name=candidate_name or factor_spec.name,
                source_family=PRICE_VOLUME_SOURCE_FAMILY,
                source_refs=list(
                    dict.fromkeys(
                        [
                            f"dataset:{resolved_dataset_version}",
                            f"latent_factor_exposure_frame:{exposure_frame_id}",
                            *factor_spec.source_refs,
                        ]
                    )
                ),
                dataset_version_used_for_discovery=resolved_dataset_version,
                label_spec_version=label_spec_version,
                protocol_version=protocol_version,
                created_by=principal_id,
                pool_status="proposed",
                tags={
                    "construction_method": LATENT_CONSTRUCTION_METHOD,
                    "source_family": PRICE_VOLUME_SOURCE_FAMILY,
                    "latent_factor_id": latent_factor_id,
                },
                parent_factor_refs=[f"factor_spec:{factor_spec.spec_version}"],
            )
            candidate = cast(dict[str, object], candidate_result["candidate"])
            completed.update(
                {
                    "candidate_factor_id": str(candidate["candidate_factor_id"]),
                    "candidate_batch_id": str(
                        cast(dict[str, object], candidate_result["candidate_batch"])[
                            "candidate_batch_id"
                        ]
                    ),
                }
            )
            record = self._upsert_handoff(
                {
                    **record,
                    **completed,
                    "updated_at": utcnow(),
                    "current_stage": "validation_claim",
                }
            )

            validation = await candidate_asset_service.submit_candidate_validation(
                candidate_factor_id=str(candidate["candidate_factor_id"]),
                dataset_version=resolved_dataset_version,
                label_spec_version=label_spec_version,
                protocol_version=protocol_version,
                policy_pack=policy_pack,
                code_version=code_version,
                seed=seed,
                principal_id=principal_id,
                source_family=PRICE_VOLUME_SOURCE_FAMILY,
            )
            completed.update(
                {
                    "evaluation_run_id": str(validation["run_id"]),
                    "evaluation_job_id": str(validation["job_id"]),
                    "validation_claim_id": str(validation["validation_claim_id"]),
                    "claim_status": str(validation["claim_status"]),
                    "verdict": str(validation["verdict"]),
                }
            )
            record = self._upsert_handoff(
                {
                    **record,
                    **completed,
                    "status": "pending_review",
                    "current_stage": "complete",
                    "failed_stage": "",
                    "updated_at": utcnow(),
                }
            )
            _ = event_store.append(
                event_type="latent_factor_exposure_frame.handoff_completed",
                payload=record,
                run_id=str(frame.get("run_id", "")),
            )
            return {
                "handoff": record,
                "factor_spec": factor_spec.to_dict(),
                "candidate": candidate,
                "candidate_batch": candidate_result["candidate_batch"],
                "member": candidate_result["member"],
                "validation": validation,
            }
        except Exception as exc:
            stage = str(record.get("current_stage") or "factor_spec")
            failed = self._upsert_handoff(
                {
                    **record,
                    **completed,
                    "status": "failed",
                    "failed_stage": stage,
                    "error": str(exc),
                    "updated_at": utcnow(),
                }
            )
            _ = event_store.append(
                event_type="latent_factor_exposure_frame.handoff_failed",
                payload=failed,
                run_id=str(frame.get("run_id", "")),
            )
            return {"handoff": failed, "error": str(exc), "failed_stage": stage}


latent_exposure_materialization_service = LatentExposureMaterializationService()
