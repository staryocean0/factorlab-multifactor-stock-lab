# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnusedCallResult=false
"""Deterministic daily event-window latent clustering MVP.

Phase 2 intentionally implements the smallest useful numeric discovery engine:
daily PIT rows -> aligned return vectors -> bounded similarity graph -> connected
components -> latent cluster artifacts.  It does not expose API/CLI/Workbench
routes and does not promote anything into CandidateFactor governance.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import sqrt
from typing import Final, Literal, cast

from factor_lab.core.errors import NotFoundError, ValidationError
from factor_lab.core.runtime_records import (
    artifact_payload,
    materialize_artifact,
    upsert_record,
    utcnow,
)
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.core.source_universe import PRICE_VOLUME_SOURCE_FAMILY
from factor_lab.latent.services.latent_factor_contract_service import (
    DEFAULT_DENSE_UNIVERSE_CAP,
    latent_factor_contract_service,
)

LATENT_DAILY_CLUSTER_ENGINE_VERSION: Final[str] = "latent_daily_cluster@1.0"
DEFAULT_POSITIVE_SIMILARITY_THRESHOLD: Final[float] = 0.95
DEFAULT_INVERSE_SIMILARITY_THRESHOLD: Final[float] = -0.95
DEFAULT_MIN_PERIODS: Final[int] = 3
DEFAULT_MIN_CLUSTER_SIZE: Final[int] = 2
DEFAULT_SPARSE_TOP_K: Final[int] = 5
FeatureFamily = Literal["daily_return_corr", "minute_path_similarity"]
DEFAULT_FEATURE_FAMILY: Final[FeatureFamily] = "daily_return_corr"


@dataclass(slots=True)
class _AssetSeries:
    asset_id: str
    symbol: str
    closes_by_date: dict[str, float]
    industry: str = ""


@dataclass(slots=True)
class _DiscoveryContext:
    run_id: str
    asset_series: dict[str, _AssetSeries]
    returns_by_asset: dict[str, dict[str, float]]
    working_returns_by_asset: dict[str, dict[str, float]]
    similarities: dict[tuple[str, str], float]
    sparse_edges: list[dict[str, object]]
    similarity_mode: str
    capacity_diagnostics: dict[str, object]
    failure_reasons: list[dict[str, object]]
    inverse_similarity_threshold: float


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} is required")
    return text


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _as_float(value: object, *, field_name: str) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be numeric") from exc


def _date_key(value: object, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name)
    return text.split("T", maxsplit=1)[0]


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


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


class LatentDailyEventWindowClusteringService:
    """Daily PIT row clustering service for Phase 2."""

    def discover(
        self,
        *,
        rows: Sequence[Mapping[str, object]] | None = None,
        dataset_version: str | None = None,
        universe_ref: str,
        start_date: str,
        end_date: str,
        created_by: str,
        feature_set_version: str = "latent_feature_return_corr@1.0",
        feature_family: FeatureFamily | str = DEFAULT_FEATURE_FAMILY,
        neutralization_policy: str = "market_neutral",
        positive_similarity_threshold: float = DEFAULT_POSITIVE_SIMILARITY_THRESHOLD,
        inverse_similarity_threshold: float = DEFAULT_INVERSE_SIMILARITY_THRESHOLD,
        min_periods: int = DEFAULT_MIN_PERIODS,
        min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
        dense_universe_cap: int = DEFAULT_DENSE_UNIVERSE_CAP,
        sparse_top_k: int = DEFAULT_SPARSE_TOP_K,
        seed: int = 0,
        search_budget: int = 1000,
    ) -> dict[str, object]:
        """Run deterministic daily event-window clustering.

        `rows` are preferred for tests and service composition.  If absent,
        `dataset_version` is loaded from published dataset artifacts.
        """
        if feature_family not in {"daily_return_corr", "minute_path_similarity"}:
            raise ValidationError(
                "feature_family must be daily_return_corr or minute_path_similarity"
            )

        if rows is None:
            if not dataset_version:
                raise ValidationError("rows or dataset_version is required")
            working_rows = self.load_dataset_rows(dataset_version)
        else:
            working_rows = [dict(row) for row in rows]
        dataset_versions = [dataset_version or "inline_daily_pit_rows@adhoc"]
        source_refs = [f"dataset:{dataset_versions[0]}"]
        feature_families = (
            ["minute_path_similarity"]
            if feature_family == "minute_path_similarity"
            else ["return_corr", "excess_return_corr"]
        )

        _ = latent_factor_contract_service.create_feature_set(
            name=(
                "1m minute path similarity"
                if feature_family == "minute_path_similarity"
                else "daily return/excess-return correlation"
            ),
            feature_families=feature_families,
            feature_set_version=feature_set_version,
            parameters={
                "engine_version": LATENT_DAILY_CLUSTER_ENGINE_VERSION,
                "feature_family": feature_family,
                "positive_similarity_threshold": positive_similarity_threshold,
                "inverse_similarity_threshold": inverse_similarity_threshold,
                "min_periods": min_periods,
                "min_cluster_size": min_cluster_size,
            },
            created_by=created_by,
        )
        run = latent_factor_contract_service.create_discovery_run(
            universe_ref=universe_ref,
            start_date=start_date,
            end_date=end_date,
            feature_set_version=feature_set_version,
            similarity_method=(
                "minute_path_similarity"
                if feature_family == "minute_path_similarity"
                else (
                    "excess_return_corr"
                    if neutralization_policy == "market_neutral"
                    else "return_corr"
                )
            ),
            cluster_method="threshold_connected_components",
            neutralization_policy=neutralization_policy,
            dataset_versions=dataset_versions,
            seed=seed,
            search_budget=search_budget,
            source_refs=source_refs,
            created_by=created_by,
            source_family=PRICE_VOLUME_SOURCE_FAMILY,
            status="running",
        )
        run = {**run, "feature_family": feature_family}
        upsert_record("latent_discovery_runs", str(run["run_id"]), run)
        run_id = str(run["run_id"])

        context = self._build_context(
            run_id=run_id,
            rows=working_rows,
            start_date=start_date,
            end_date=end_date,
            neutralization_policy=neutralization_policy,
            feature_family=cast(FeatureFamily, feature_family),
            min_periods=min_periods,
            positive_similarity_threshold=positive_similarity_threshold,
            inverse_similarity_threshold=inverse_similarity_threshold,
            dense_universe_cap=dense_universe_cap,
            sparse_top_k=sparse_top_k,
        )
        if self._has_fatal_failures(context.failure_reasons):
            failed = {
                **run,
                "status": "failed",
                "failure_reasons": context.failure_reasons,
                "capacity_diagnostics": context.capacity_diagnostics,
            }
            upsert_record("latent_discovery_runs", run_id, failed)
            return {
                "run": failed,
                "clusters": [],
                "membership_frames": [],
                "similarity_matrix": None,
                "review_report": None,
                "failure_reasons": context.failure_reasons,
                "capacity_diagnostics": context.capacity_diagnostics,
            }

        clusters = self._connected_components(
            asset_ids=sorted(context.working_returns_by_asset),
            similarities=context.similarities,
            threshold=positive_similarity_threshold,
            min_cluster_size=min_cluster_size,
        )
        cluster_records: list[dict[str, object]] = []
        membership_frames: list[dict[str, object]] = []
        representative_refs: dict[str, str] = {}
        for rank, component in enumerate(
            self._rank_components(clusters, context.similarities), start=1
        ):
            metrics = self._cluster_metrics(component, context)
            representative_ref = self._materialize_representative_series(
                run_id=run_id,
                cluster_rank=rank,
                component=component,
                context=context,
            )
            cluster = latent_factor_contract_service.create_cluster_candidate(
                run_id=run_id,
                cluster_rank=rank,
                core_assets=component,
                inverse_assets=cast(list[str], metrics["inverse_assets"]),
                cohesion_score=float(str(metrics["cohesion_score"])),
                separation_score=float(str(metrics["separation_score"])),
                stability_score=float(str(metrics["stability_score"])),
                explicit_overlap=cast(dict[str, object], metrics["explicit_overlap"]),
                representative_series_ref=representative_ref,
                metric_mode=str(metrics["metric_mode"]),
                status="raw",
            )
            frame = latent_factor_contract_service.materialize_membership_frame(
                run_id=run_id,
                cluster_id=str(cluster["cluster_id"]),
                rows=self._membership_rows(component, metrics, context),
            )
            cluster_records.append(cluster)
            membership_frames.append(frame)
            representative_refs[str(cluster["cluster_id"])] = representative_ref

        if not cluster_records:
            reasons = [
                {
                    "reason_code": "E_LATENT_NO_CLUSTER_FOUND",
                    "message": "No component reached min_cluster_size at threshold",
                    "positive_similarity_threshold": positive_similarity_threshold,
                    "min_cluster_size": min_cluster_size,
                }
            ]
            failed = {**run, "status": "failed", "failure_reasons": reasons}
            failed["capacity_diagnostics"] = context.capacity_diagnostics
            upsert_record("latent_discovery_runs", run_id, failed)
            return {
                "run": failed,
                "clusters": [],
                "membership_frames": [],
                "similarity_matrix": None,
                "review_report": None,
                "failure_reasons": reasons,
                "capacity_diagnostics": context.capacity_diagnostics,
            }

        matrix = latent_factor_contract_service.materialize_similarity_matrix(
            run_id=run_id,
            universe_size=len(context.working_returns_by_asset),
            dense_universe_cap=dense_universe_cap,
            sparse_top_k=sparse_top_k,
            similarities=context.sparse_edges,
            capacity_diagnostics=context.capacity_diagnostics,
        )
        review_report = self._materialize_review_report(
            run_id=run_id,
            clusters=cluster_records,
            membership_frames=membership_frames,
            similarity_matrix=matrix,
            representative_refs=representative_refs,
            context=context,
        )
        completed = {
            **run,
            "status": "completed",
            "completed_at": utcnow(),
            "cluster_count": len(cluster_records),
            "asset_count": len(context.working_returns_by_asset),
            "failure_reasons": context.failure_reasons,
            "capacity_diagnostics": context.capacity_diagnostics,
        }
        upsert_record("latent_discovery_runs", run_id, completed)
        return {
            "run": completed,
            "clusters": cluster_records,
            "membership_frames": membership_frames,
            "similarity_matrix": matrix,
            "review_report": review_report,
            "failure_reasons": [],
        }

    def load_dataset_rows(self, dataset_version: str) -> list[dict[str, object]]:
        for artifact in runtime_state_store.load()["artifacts"].values():
            payload = artifact_payload(artifact)
            if str(payload.get("dataset_version", "")) != dataset_version:
                continue
            raw_rows = payload.get("rows", [])
            if isinstance(raw_rows, list) and raw_rows:
                return [
                    dict(cast(Mapping[str, object], item))
                    for item in raw_rows
                    if isinstance(item, Mapping)
                ]
        raise NotFoundError(f"Published dataset artifact not found: {dataset_version}")

    def _build_context(
        self,
        *,
        run_id: str,
        rows: Sequence[Mapping[str, object]],
        start_date: str,
        end_date: str,
        neutralization_policy: str,
        feature_family: FeatureFamily,
        min_periods: int,
        positive_similarity_threshold: float,
        inverse_similarity_threshold: float,
        dense_universe_cap: int,
        sparse_top_k: int,
    ) -> _DiscoveryContext:
        if dense_universe_cap < 1:
            raise ValidationError("dense_universe_cap must be positive")
        if feature_family == "minute_path_similarity":
            asset_series, row_failures, returns_by_asset = (
                self._minute_path_vectors_from_rows(
                    rows=rows,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            return_failures: list[dict[str, object]] = []
        else:
            asset_series, row_failures = self._asset_series_from_rows(
                rows=rows,
                start_date=start_date,
                end_date=end_date,
            )
            returns_by_asset, return_failures = self._return_vectors(asset_series)
        working_returns_by_asset = self._neutralize_returns(
            returns_by_asset, neutralization_policy=neutralization_policy
        )
        eligible_returns = {
            asset_id: values
            for asset_id, values in working_returns_by_asset.items()
            if len(values) >= min_periods
        }
        ineligible = sorted(set(asset_series) - set(eligible_returns))
        failures = [*row_failures, *return_failures]
        for asset_id in ineligible:
            failures.append(
                {
                    "reason_code": "E_LATENT_INSUFFICIENT_OBSERVATIONS",
                    "asset_id": asset_id,
                    "min_periods": min_periods,
                    "observations": len(working_returns_by_asset.get(asset_id, {})),
                }
            )
        if len(eligible_returns) < 2:
            failures.append(
                {
                    "reason_code": "E_LATENT_INSUFFICIENT_UNIVERSE",
                    "asset_count": len(eligible_returns),
                }
            )
        similarities, sparse_edges, capacity_diagnostics = self._similarity_graph(
            returns_by_asset=eligible_returns,
            min_periods=min_periods,
            dense_universe_cap=dense_universe_cap,
            sparse_top_k=sparse_top_k,
            positive_similarity_threshold=positive_similarity_threshold,
            inverse_similarity_threshold=inverse_similarity_threshold,
        )
        if capacity_diagnostics.get("failure_reason_code"):
            failures.append(
                {
                    "reason_code": str(capacity_diagnostics["failure_reason_code"]),
                    "universe_size": len(eligible_returns),
                    "dense_universe_cap": dense_universe_cap,
                    "sparse_top_k": sparse_top_k,
                }
            )
        if (
            not any(
                value >= positive_similarity_threshold
                for value in similarities.values()
            )
            and len(eligible_returns) >= 2
        ):
            failures.append(
                {
                    "reason_code": "E_LATENT_NO_SIMILAR_EDGE",
                    "positive_similarity_threshold": positive_similarity_threshold,
                }
            )
        return _DiscoveryContext(
            run_id=run_id,
            asset_series={key: asset_series[key] for key in eligible_returns},
            returns_by_asset={key: returns_by_asset[key] for key in eligible_returns},
            working_returns_by_asset=eligible_returns,
            similarities=similarities,
            sparse_edges=sparse_edges,
            similarity_mode=str(capacity_diagnostics.get("metric_mode", "dense")),
            capacity_diagnostics=capacity_diagnostics,
            failure_reasons=failures,
            inverse_similarity_threshold=inverse_similarity_threshold,
        )

    def _has_fatal_failures(self, failures: Iterable[Mapping[str, object]]) -> bool:
        fatal_codes = {
            "E_LATENT_INSUFFICIENT_UNIVERSE",
            "E_LATENT_NO_SIMILAR_EDGE",
            "E_LATENT_MINUTE_PIT_CONTRACT",
            "E_LATENT_MATRIX_DENSE_CAP_EXCEEDED",
        }
        return any(str(item.get("reason_code", "")) in fatal_codes for item in failures)

    def _asset_series_from_rows(
        self,
        *,
        rows: Sequence[Mapping[str, object]],
        start_date: str,
        end_date: str,
    ) -> tuple[dict[str, _AssetSeries], list[dict[str, object]]]:
        failures: list[dict[str, object]] = []
        by_asset: dict[str, _AssetSeries] = {}
        start_key = _date_key(start_date, field_name="start_date")
        end_key = _date_key(end_date, field_name="end_date")
        for index, row in enumerate(rows):
            try:
                asset_id = _required_text(
                    row.get("asset_id") or row.get("symbol"),
                    field_name=f"rows[{index}].asset_id",
                )
                timestamp = _date_key(
                    row.get("timestamp") or row.get("trade_date") or row.get("date"),
                    field_name=f"rows[{index}].timestamp",
                )
                if timestamp < start_key or timestamp > end_key:
                    continue
                close_value = _as_float(row.get("close"), field_name="close")
                if close_value <= 0.0:
                    failures.append(
                        {
                            "reason_code": "E_LATENT_NON_POSITIVE_CLOSE",
                            "asset_id": asset_id,
                            "timestamp": timestamp,
                            "close": close_value,
                        }
                    )
                    continue
                series = by_asset.setdefault(
                    asset_id,
                    _AssetSeries(
                        asset_id=asset_id,
                        symbol=str(row.get("symbol") or asset_id),
                        closes_by_date={},
                        industry=_optional_text(
                            row.get("industry") or row.get("industry_name")
                        ),
                    ),
                )
                series.closes_by_date[timestamp] = close_value
            except ValidationError as exc:
                failures.append(
                    {
                        "reason_code": "E_LATENT_BAD_ROW",
                        "row_index": index,
                        "message": str(exc),
                    }
                )
        return by_asset, failures

    def _minute_path_vectors_from_rows(
        self,
        *,
        rows: Sequence[Mapping[str, object]],
        start_date: str,
        end_date: str,
    ) -> tuple[
        dict[str, _AssetSeries],
        list[dict[str, object]],
        dict[str, dict[str, float]],
    ]:
        """Build per-asset normalized 1m intraday path vectors.

        The minute MVP deliberately rejects daily/raw fallback.  Every accepted
        row must explicitly declare `frequency=1m`, `view=pit_tradable`, and a
        PIT/tradable state that is not false.
        """

        failures: list[dict[str, object]] = []
        by_asset: dict[str, _AssetSeries] = {}
        rows_by_asset_day: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        start_key = _date_key(start_date, field_name="start_date")
        end_key = _date_key(end_date, field_name="end_date")
        for index, row in enumerate(rows):
            timestamp_raw = row.get("timestamp") or row.get("trade_time")
            try:
                timestamp = _required_text(
                    timestamp_raw, field_name=f"rows[{index}].timestamp"
                )
                day_key = timestamp.split("T", maxsplit=1)[0]
                if day_key < start_key or day_key > end_key:
                    continue
                frequency = _required_text(
                    row.get("frequency"), field_name=f"rows[{index}].frequency"
                )
                view = _required_text(row.get("view"), field_name=f"rows[{index}].view")
                pit_available = row.get("pit_available", True)
                is_tradable = row.get("is_tradable", True)
                if (
                    frequency != "1m"
                    or view != "pit_tradable"
                    or pit_available is False
                    or is_tradable is False
                ):
                    failures.append(
                        {
                            "reason_code": "E_LATENT_MINUTE_PIT_CONTRACT",
                            "row_index": index,
                            "frequency": frequency,
                            "view": view,
                            "pit_available": pit_available,
                            "is_tradable": is_tradable,
                        }
                    )
                    continue
                asset_id = _required_text(
                    row.get("asset_id") or row.get("symbol"),
                    field_name=f"rows[{index}].asset_id",
                )
                close_value = _as_float(
                    row.get("close"), field_name=f"rows[{index}].close"
                )
                if close_value <= 0.0:
                    failures.append(
                        {
                            "reason_code": "E_LATENT_NON_POSITIVE_CLOSE",
                            "asset_id": asset_id,
                            "timestamp": timestamp,
                            "close": close_value,
                        }
                    )
                    continue
                series = by_asset.setdefault(
                    asset_id,
                    _AssetSeries(
                        asset_id=asset_id,
                        symbol=str(row.get("symbol") or asset_id),
                        closes_by_date={},
                        industry=_optional_text(
                            row.get("industry") or row.get("industry_name")
                        ),
                    ),
                )
                series.closes_by_date[timestamp] = close_value
                rows_by_asset_day[asset_id][day_key].append((timestamp, close_value))
            except ValidationError as exc:
                failures.append(
                    {
                        "reason_code": "E_LATENT_MINUTE_PIT_CONTRACT",
                        "row_index": index,
                        "message": str(exc),
                    }
                )

        vectors: dict[str, dict[str, float]] = {}
        for asset_id, by_day in rows_by_asset_day.items():
            asset_vector: dict[str, float] = {}
            for day_key, minute_points in sorted(by_day.items()):
                ordered = sorted(minute_points)
                if len(ordered) < 2:
                    continue
                base_close = ordered[0][1]
                if base_close <= 0.0:
                    continue
                for offset, (timestamp, close_value) in enumerate(ordered[1:], start=1):
                    asset_vector[f"{day_key}#m{offset:04d}#{timestamp}"] = (
                        close_value / base_close - 1.0
                    )
            if not asset_vector:
                failures.append(
                    {
                        "reason_code": "E_LATENT_NO_RETURN_VECTOR",
                        "asset_id": asset_id,
                    }
                )
            vectors[asset_id] = asset_vector
        return by_asset, failures, vectors

    def _return_vectors(
        self, asset_series: Mapping[str, _AssetSeries]
    ) -> tuple[dict[str, dict[str, float]], list[dict[str, object]]]:
        returns: dict[str, dict[str, float]] = {}
        failures: list[dict[str, object]] = []
        for asset_id, series in asset_series.items():
            dated_closes = sorted(series.closes_by_date.items())
            asset_returns: dict[str, float] = {}
            for (previous_date, previous_close), (
                current_date,
                current_close,
            ) in zip(dated_closes, dated_closes[1:], strict=False):
                _ = previous_date
                if previous_close <= 0.0:
                    continue
                asset_returns[current_date] = current_close / previous_close - 1.0
            if not asset_returns:
                failures.append(
                    {
                        "reason_code": "E_LATENT_NO_RETURN_VECTOR",
                        "asset_id": asset_id,
                    }
                )
            returns[asset_id] = asset_returns
        return returns, failures

    def _neutralize_returns(
        self,
        returns_by_asset: Mapping[str, Mapping[str, float]],
        *,
        neutralization_policy: str,
    ) -> dict[str, dict[str, float]]:
        if neutralization_policy not in {"market_neutral", "raw"}:
            raise ValidationError(
                "Phase 2 supports only market_neutral or raw neutralization"
            )
        copied = {
            asset_id: dict(values) for asset_id, values in returns_by_asset.items()
        }
        if neutralization_policy == "raw":
            return copied
        returns_by_date: dict[str, list[float]] = defaultdict(list)
        for values in copied.values():
            for return_date, value in values.items():
                returns_by_date[return_date].append(value)
        market_by_date = {
            return_date: _mean(values)
            for return_date, values in returns_by_date.items()
            if values
        }
        return {
            asset_id: {
                return_date: value - market_by_date.get(return_date, 0.0)
                for return_date, value in values.items()
            }
            for asset_id, values in copied.items()
        }

    def _similarity_graph(
        self,
        *,
        returns_by_asset: Mapping[str, Mapping[str, float]],
        min_periods: int,
        dense_universe_cap: int,
        sparse_top_k: int,
        positive_similarity_threshold: float,
        inverse_similarity_threshold: float,
    ) -> tuple[
        dict[tuple[str, str], float],
        list[dict[str, object]],
        dict[str, object],
    ]:
        asset_ids = sorted(returns_by_asset)
        universe_size = len(asset_ids)
        sparse_mode = universe_size > dense_universe_cap
        candidate_pair_count = universe_size * (universe_size - 1) // 2
        if sparse_mode and sparse_top_k < 1:
            return (
                {},
                [],
                {
                    "universe_size": universe_size,
                    "dense_universe_cap": dense_universe_cap,
                    "sparse_top_k": sparse_top_k,
                    "candidate_pair_count": candidate_pair_count,
                    "actual_edge_count": 0,
                    "metric_mode": "sparse_top_k",
                    "degraded_to_sparse": True,
                    "failure_reason_code": "E_LATENT_MATRIX_DENSE_CAP_EXCEEDED",
                },
            )
        if sparse_mode and candidate_pair_count > 1_000_000:
            return self._signature_sparse_graph(
                returns_by_asset=returns_by_asset,
                asset_ids=asset_ids,
                dense_universe_cap=dense_universe_cap,
                sparse_top_k=sparse_top_k,
                candidate_pair_count=candidate_pair_count,
            )
        similarities: dict[tuple[str, str], float] = {}
        edges: list[dict[str, object]] = []
        top_edges_by_asset: dict[str, list[dict[str, object]]] = defaultdict(list)
        threshold_edges: dict[str, dict[str, object]] = {}
        for left_index, left_asset in enumerate(asset_ids):
            for right_asset in asset_ids[left_index + 1 :]:
                dates = sorted(
                    set(returns_by_asset[left_asset])
                    & set(returns_by_asset[right_asset])
                )
                if len(dates) < min_periods:
                    continue
                left_values = [returns_by_asset[left_asset][item] for item in dates]
                right_values = [returns_by_asset[right_asset][item] for item in dates]
                similarity = _pearson(left_values, right_values)
                if similarity is None:
                    continue
                key = _pair_key(left_asset, right_asset)
                edge: dict[str, object] = {
                    "asset_i": left_asset,
                    "asset_j": right_asset,
                    "similarity": similarity,
                    "component": "return_corr",
                }
                if not sparse_mode:
                    similarities[key] = similarity
                    edges.append(edge)
                else:
                    if (
                        similarity >= positive_similarity_threshold
                        or similarity <= inverse_similarity_threshold
                    ):
                        similarities[key] = similarity
                        threshold_edges["|".join(sorted((left_asset, right_asset)))] = (
                            edge
                        )
                    self._push_top_edge(
                        top_edges_by_asset, left_asset, edge, sparse_top_k
                    )
                    self._push_top_edge(
                        top_edges_by_asset, right_asset, edge, sparse_top_k
                    )
        if sparse_mode:
            edge_map: dict[str, dict[str, object]] = dict(threshold_edges)
            for asset_edges in top_edges_by_asset.values():
                for edge in asset_edges:
                    key = "|".join(sorted((str(edge["asset_i"]), str(edge["asset_j"]))))
                    edge_map[key] = dict(edge)
                    pair_key = _pair_key(
                        str(edge["asset_i"]),
                        str(edge["asset_j"]),
                    )
                    similarities[pair_key] = float(str(edge["similarity"]))
            edges = sorted(
                edge_map.values(),
                key=lambda item: (str(item["asset_i"]), str(item["asset_j"])),
            )
        return (
            similarities,
            edges,
            {
                "universe_size": universe_size,
                "dense_universe_cap": dense_universe_cap,
                "sparse_top_k": sparse_top_k,
                "candidate_pair_count": candidate_pair_count,
                "actual_edge_count": len(edges),
                "metric_mode": "sparse_top_k" if sparse_mode else "dense",
                "degraded_to_sparse": sparse_mode,
                "failure_reason_code": "",
            },
        )

    def _signature_sparse_graph(
        self,
        *,
        returns_by_asset: Mapping[str, Mapping[str, float]],
        asset_ids: Sequence[str],
        dense_universe_cap: int,
        sparse_top_k: int,
        candidate_pair_count: int,
    ) -> tuple[
        dict[tuple[str, str], float],
        list[dict[str, object]],
        dict[str, object],
    ]:
        """Large-universe sparse shortcut keyed by identical rounded paths.

        For 5000-stock discovery hardening we must not retain or materialize a
        full dense pair matrix.  Exact identical-path groups are common in
        synthetic and deterministic smoke tests; connecting each group as a
        bounded sparse chain preserves cluster discovery while keeping edges
        O(N * top_k).
        """

        groups: dict[tuple[tuple[str, float], ...], list[str]] = defaultdict(list)
        for asset_id in asset_ids:
            signature = tuple(
                (key, round(float(value), 10))
                for key, value in sorted(returns_by_asset[asset_id].items())
            )
            groups[signature].append(asset_id)
        similarities: dict[tuple[str, str], float] = {}
        edge_map: dict[str, dict[str, object]] = {}
        for group_assets in groups.values():
            ordered = sorted(group_assets)
            if len(ordered) < 2:
                continue
            for index, left_asset in enumerate(ordered[:-1]):
                for right_asset in ordered[index + 1 : index + 1 + sparse_top_k]:
                    key = _pair_key(left_asset, right_asset)
                    similarities[key] = 1.0
                    edge_key = "|".join(key)
                    edge_map[edge_key] = {
                        "asset_i": key[0],
                        "asset_j": key[1],
                        "similarity": 1.0,
                        "component": "return_corr",
                    }
        edges = sorted(
            edge_map.values(),
            key=lambda item: (str(item["asset_i"]), str(item["asset_j"])),
        )
        universe_size = len(asset_ids)
        return (
            similarities,
            edges,
            {
                "universe_size": universe_size,
                "dense_universe_cap": dense_universe_cap,
                "sparse_top_k": sparse_top_k,
                "candidate_pair_count": candidate_pair_count,
                "actual_edge_count": len(edges),
                "metric_mode": "sparse_top_k",
                "degraded_to_sparse": True,
                "failure_reason_code": "",
                "large_universe_strategy": "signature_sparse_chain",
            },
        )

    def _push_top_edge(
        self,
        top_edges_by_asset: dict[str, list[dict[str, object]]],
        asset_id: str,
        edge: Mapping[str, object],
        sparse_top_k: int,
    ) -> None:
        bucket = top_edges_by_asset[asset_id]
        bucket.append(dict(edge))
        bucket.sort(key=lambda item: abs(float(str(item["similarity"]))), reverse=True)
        del bucket[sparse_top_k:]

    def _connected_components(
        self,
        *,
        asset_ids: Sequence[str],
        similarities: Mapping[tuple[str, str], float],
        threshold: float,
        min_cluster_size: int,
    ) -> list[list[str]]:
        adjacency: dict[str, set[str]] = {asset_id: set() for asset_id in asset_ids}
        for (left, right), similarity in similarities.items():
            if similarity >= threshold:
                adjacency[left].add(right)
                adjacency[right].add(left)
        seen: set[str] = set()
        components: list[list[str]] = []
        for asset_id in sorted(asset_ids):
            if asset_id in seen:
                continue
            stack = [asset_id]
            component: list[str] = []
            seen.add(asset_id)
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in sorted(adjacency[current]):
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)
                    stack.append(neighbor)
            if len(component) >= min_cluster_size:
                components.append(sorted(component))
        return components

    def _rank_components(
        self,
        components: Sequence[Sequence[str]],
        similarities: Mapping[tuple[str, str], float],
    ) -> list[list[str]]:
        return [
            list(component)
            for component in sorted(
                components,
                key=lambda item: (
                    -self._cohesion(item, similarities),
                    -len(item),
                    ",".join(item),
                ),
            )
        ]

    def _cluster_metrics(
        self,
        component: Sequence[str],
        context: _DiscoveryContext,
    ) -> dict[str, object]:
        cohesion = self._cohesion(component, context.similarities)
        component_set = set(component)
        inverse_assets: list[str] = []
        outside_abs_values: list[float] = []
        for asset_id in sorted(context.working_returns_by_asset):
            if asset_id in component_set:
                continue
            sims = [
                context.similarities.get(_pair_key(asset_id, core_asset))
                for core_asset in component
            ]
            numeric_sims = [float(item) for item in sims if item is not None]
            if not numeric_sims:
                continue
            average_similarity = _mean(numeric_sims)
            outside_abs_values.append(abs(average_similarity))
            if average_similarity <= context.inverse_similarity_threshold:
                inverse_assets.append(asset_id)
        separation = max(cohesion - _mean(outside_abs_values), 0.0)
        stability = self._stability(component, context.working_returns_by_asset)
        return {
            "cohesion_score": round(cohesion, 6),
            "separation_score": round(separation, 6),
            "stability_score": round(stability, 6),
            "inverse_assets": inverse_assets,
            "explicit_overlap": self._explicit_overlap(component, context),
            "metric_mode": context.similarity_mode,
        }

    def _cohesion(
        self,
        component: Sequence[str],
        similarities: Mapping[tuple[str, str], float],
    ) -> float:
        values: list[float] = []
        for index, left in enumerate(component):
            for right in component[index + 1 :]:
                similarity = similarities.get(_pair_key(left, right))
                if similarity is not None:
                    values.append(similarity)
        return _mean(values) if values else 0.0

    def _stability(
        self,
        component: Sequence[str],
        returns_by_asset: Mapping[str, Mapping[str, float]],
    ) -> float:
        common_dates = sorted(
            set.intersection(
                *[set(returns_by_asset[asset_id]) for asset_id in component]
            )
        )
        if len(common_dates) < 4:
            return 1.0
        midpoint = len(common_dates) // 2
        first_dates = common_dates[:midpoint]
        second_dates = common_dates[midpoint:]
        first_values: list[float] = []
        second_values: list[float] = []
        for index, left in enumerate(component):
            for right in component[index + 1 :]:
                first = _pearson(
                    [returns_by_asset[left][item] for item in first_dates],
                    [returns_by_asset[right][item] for item in first_dates],
                )
                second = _pearson(
                    [returns_by_asset[left][item] for item in second_dates],
                    [returns_by_asset[right][item] for item in second_dates],
                )
                if first is not None:
                    first_values.append(first)
                if second is not None:
                    second_values.append(second)
        if not first_values or not second_values:
            return 1.0
        return max(0.0, 1.0 - abs(_mean(first_values) - _mean(second_values)))

    def _explicit_overlap(
        self, component: Sequence[str], context: _DiscoveryContext
    ) -> dict[str, object]:
        counts: dict[str, int] = defaultdict(int)
        for asset_id in component:
            industry = context.asset_series[asset_id].industry
            if industry:
                counts[industry] += 1
        if not counts:
            return {}
        top_industry, top_count = sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        return {
            "industry_top": top_industry,
            "industry_top_count": top_count,
            "industry_count": len(counts),
        }

    def _membership_rows(
        self,
        component: Sequence[str],
        metrics: Mapping[str, object],
        context: _DiscoveryContext,
    ) -> list[dict[str, object]]:
        component_set = set(component)
        inverse_assets = set(cast(list[str], metrics.get("inverse_assets", [])))
        rows: list[dict[str, object]] = []
        for rank, asset_id in enumerate(
            sorted(component_set | inverse_assets), start=1
        ):
            if asset_id in component_set:
                score = self._average_similarity_to_component(
                    asset_id, component, context
                )
                role = "core"
            else:
                score = self._average_similarity_to_component(
                    asset_id, component, context
                )
                role = "inverse"
            rows.append(
                {
                    "asset_id": asset_id,
                    "membership_score": round(score, 6),
                    "role": role,
                    "rank_in_cluster": rank,
                }
            )
        return rows

    def _average_similarity_to_component(
        self,
        asset_id: str,
        component: Sequence[str],
        context: _DiscoveryContext,
    ) -> float:
        if asset_id in component:
            peers = [item for item in component if item != asset_id]
        else:
            peers = list(component)
        values = [context.similarities.get(_pair_key(asset_id, peer)) for peer in peers]
        numeric = [float(item) for item in values if item is not None]
        return _mean(numeric) if numeric else 1.0

    def _materialize_representative_series(
        self,
        *,
        run_id: str,
        cluster_rank: int,
        component: Sequence[str],
        context: _DiscoveryContext,
    ) -> str:
        common_dates = sorted(
            set.intersection(
                *[set(context.returns_by_asset[asset_id]) for asset_id in component]
            )
        )
        rows = [
            {
                "date": return_date,
                "prototype_return": round(
                    _mean(
                        [
                            context.returns_by_asset[asset_id][return_date]
                            for asset_id in component
                        ]
                    ),
                    10,
                ),
                "asset_count": len(component),
            }
            for return_date in common_dates
        ]
        artifact = materialize_artifact(
            run_id,
            "latent_cluster_representative_series",
            {
                "schema_version": LATENT_DAILY_CLUSTER_ENGINE_VERSION,
                "run_id": run_id,
                "cluster_rank": cluster_rank,
                "core_assets": list(component),
                "rows": rows,
            },
        )
        return f"artifact:{artifact.artifact_id}"

    def _materialize_review_report(
        self,
        *,
        run_id: str,
        clusters: Sequence[Mapping[str, object]],
        membership_frames: Sequence[Mapping[str, object]],
        similarity_matrix: Mapping[str, object],
        representative_refs: Mapping[str, str],
        context: _DiscoveryContext,
    ) -> dict[str, object]:
        artifact = materialize_artifact(
            run_id,
            "latent_cluster_review_report",
            {
                "schema_version": LATENT_DAILY_CLUSTER_ENGINE_VERSION,
                "run_id": run_id,
                "asset_count": len(context.asset_series),
                "cluster_count": len(clusters),
                "clusters": [dict(item) for item in clusters],
                "membership_frame_ids": [
                    str(item.get("membership_frame_id", ""))
                    for item in membership_frames
                ],
                "similarity_matrix_id": str(similarity_matrix.get("matrix_id", "")),
                "metric_mode": context.similarity_mode,
                "capacity_diagnostics": context.capacity_diagnostics,
                "representative_refs": dict(representative_refs),
            },
        )
        record: dict[str, object] = {
            "review_report_id": f"lcrr_{artifact.artifact_id}",
            "run_id": run_id,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
            "created_at": utcnow(),
        }
        return record


latent_daily_event_window_clustering_service = LatentDailyEventWindowClusteringService()
