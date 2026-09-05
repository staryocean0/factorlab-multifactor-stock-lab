# pyright: reportAny=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Deterministic temporal-dynamics services for static/dynamic factor use.

The service adds a second, orthogonal taxonomy next to explicit/latent factor
production: factor values can be static descriptors, slow-moving descriptors, or
dynamic signals. Static/slow descriptors are intentionally routed away from
factor-return direct regression and toward cohort-index or rotation research.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from statistics import mean, median, pstdev
from typing import Final, Literal, cast

from factor_lab.core.errors import NotFoundError, ValidationError
from factor_lab.core.hashing import sha256_hash
from factor_lab.core.runtime_records import (
    artifact_payload,
    get_record,
    materialize_artifact,
    upsert_record,
    utcnow,
)
from factor_lab.governance.services.event_store import event_store
from factor_lab.latent.services.daily_event_window_clustering_service import (
    latent_daily_event_window_clustering_service,
)

TEMPORAL_DYNAMICS_SCHEMA_VERSION: Final[str] = "factor_temporal_dynamics@1.0"
CohortWeightingMethod = Literal[
    "equal_weight",
    "market_cap_weight",
    "float_market_cap_weight",
]
WEIGHT_FIELD_BY_METHOD: Final[dict[str, str]] = {
    "market_cap_weight": "market_cap",
    "float_market_cap_weight": "float_market_cap",
}
WEIGHT_FIELD_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "market_cap": ("market_cap", "total_market_cap"),
    "float_market_cap": ("float_market_cap",),
}
TemporalClass = Literal[
    "static_descriptor",
    "slow_moving_descriptor",
    "dynamic_signal",
    "rotating_cohort",
    "hybrid_conditional",
]


def _string(value: object) -> str:
    return str(value or "").strip()


def _float(value: object, *, field_name: str = "value") -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValidationError(f"{field_name} must be finite")
    return number


def _optional_float(value: object) -> float | None:
    if value is None or _string(value) == "":
        return None
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive_optional_float(value: object) -> float | None:
    number = _optional_float(value)
    if number is None or number <= 0.0:
        return None
    return number


def _positive_optional_field(
    row: Mapping[str, object],
    field_name: str,
) -> float | None:
    for alias in WEIGHT_FIELD_ALIASES.get(field_name, (field_name,)):
        number = _positive_optional_float(row.get(alias))
        if number is not None:
            return number
    return None


def _optional_timestamp(row: Mapping[str, object]) -> str:
    return _string(row.get("timestamp")) or _string(row.get("date"))


def _timestamp(row: Mapping[str, object]) -> str:
    value = _optional_timestamp(row)
    if not value:
        raise ValidationError("row missing timestamp/date")
    return value


def _asset_id(row: Mapping[str, object]) -> str:
    value = _string(row.get("asset_id")) or _string(row.get("symbol"))
    if not value:
        raise ValidationError("row missing asset_id/symbol")
    return value


def _instant_key(value: object) -> str:
    text = _string(value)
    if not text:
        return ""
    if "T" not in text and len(text) == 10:
        text = f"{text}T23:59:59"
    if text.endswith("Z"):
        text = text[:-1]
    if text.endswith("+00:00"):
        text = text[:-6]
    return text


def _time_after(left: object, right: object) -> bool:
    return _instant_key(left) > _instant_key(right)


def _leaks_available_at(row: Mapping[str, object]) -> bool:
    available_at = row.get("available_at")
    if available_at is None or _string(available_at) == "":
        return False
    timestamp = row.get("timestamp") or row.get("date")
    return _time_after(available_at, timestamp)


def _canonical_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    canonical = [dict(row) for row in rows]
    if not canonical:
        raise ValidationError("rows must not be empty")
    return canonical


def _load_rows(
    *, rows: Sequence[Mapping[str, object]] | None, dataset_version: str | None
) -> tuple[list[dict[str, object]], str, str]:
    if rows is not None:
        return (
            _canonical_rows(rows),
            dataset_version or "inline_factor_temporal_rows@adhoc",
            "rows",
        )
    if not dataset_version:
        raise ValidationError("rows or dataset_version is required")
    loaded = latent_daily_event_window_clustering_service.load_dataset_rows(
        dataset_version
    )
    if not loaded:
        raise ValidationError("dataset_version contains no rows")
    return loaded, dataset_version, "dataset_version"


def _mean(values: Sequence[float]) -> float:
    return mean(values) if values else 0.0


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = _mean(left)
    right_mean = _mean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_var = sum((value - left_mean) ** 2 for value in left)
    right_var = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_var * right_var)
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def _compound_return(values: Sequence[float]) -> float:
    nav = 1.0
    for value in values:
        nav *= 1.0 + value
    return nav - 1.0


def _parse_temporal_instant(value: object) -> datetime | None:
    text = _string(value)
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00"
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _round_optional(value: float | None, digits: int = 8) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _median_optional(values: Sequence[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return None
    return median(clean)


def _change_half_life_periods(change_rate: float) -> float | None:
    if change_rate <= 0.0:
        return None
    if change_rate >= 1.0:
        return 1.0
    return math.log(0.5) / math.log(1.0 - change_rate)


class FactorTemporalDynamicsService:
    """Build temporal profiles, cohort indexes, and rotation reports."""

    def evaluate_profile(
        self,
        *,
        rows: Sequence[Mapping[str, object]] | None = None,
        dataset_version: str | None = None,
        factor_ref: str = "",
        value_column: str = "factor_value",
        generated_by: str,
        static_change_threshold: float = 0.05,
        slow_change_threshold: float = 0.25,
    ) -> dict[str, object]:
        working_rows, resolved_dataset_version, source_mode = _load_rows(
            rows=rows,
            dataset_version=dataset_version,
        )
        if not value_column:
            raise ValidationError("value_column is required")
        leaks = [row for row in working_rows if _leaks_available_at(row)]
        if leaks:
            raise ValidationError(
                "factor temporal profile rows violate PIT available_at"
            )

        by_asset: dict[str, list[dict[str, object]]] = defaultdict(list)
        raw_values: list[object] = []
        for row in working_rows:
            if value_column not in row:
                raise ValidationError(f"row missing value_column: {value_column}")
            by_asset[_asset_id(row)].append(row)
            raw_values.append(row[value_column])

        change_rates: list[float] = []
        numeric_values: list[float] = []
        observation_gaps_days: list[float] = []
        change_gaps_days: list[float] = []
        asset_observation_counts: list[int] = []
        parsed_timestamp_count = 0
        assets_with_changes = 0
        first_timestamp: datetime | None = None
        last_timestamp: datetime | None = None
        for asset_rows in by_asset.values():
            ordered = sorted(asset_rows, key=_timestamp)
            asset_values = [row[value_column] for row in ordered]
            asset_observation_counts.append(len(ordered))
            ordered_timestamps = [
                _parse_temporal_instant(_timestamp(row)) for row in ordered
            ]
            for parsed in ordered_timestamps:
                if parsed is None:
                    continue
                parsed_timestamp_count += 1
                if first_timestamp is None or parsed < first_timestamp:
                    first_timestamp = parsed
                if last_timestamp is None or parsed > last_timestamp:
                    last_timestamp = parsed
            for previous_time, current_time in zip(
                ordered_timestamps, ordered_timestamps[1:], strict=False
            ):
                if previous_time is None or current_time is None:
                    continue
                gap_days = (current_time - previous_time).total_seconds() / 86_400
                if gap_days >= 0.0:
                    observation_gaps_days.append(gap_days)
            changes = 0
            for previous, current, previous_time, current_time in zip(
                asset_values,
                asset_values[1:],
                ordered_timestamps,
                ordered_timestamps[1:],
                strict=False,
            ):
                if str(previous) == str(current):
                    continue
                changes += 1
                if previous_time is None or current_time is None:
                    continue
                gap_days = (current_time - previous_time).total_seconds() / 86_400
                if gap_days >= 0.0:
                    change_gaps_days.append(gap_days)
            if changes:
                assets_with_changes += 1
            if len(asset_values) > 1:
                change_rates.append(changes / (len(asset_values) - 1))
            for value in asset_values:
                optional = _optional_float(value)
                if optional is not None:
                    numeric_values.append(optional)

        row_count = len(working_rows)
        asset_count = len(by_asset)
        unique_values = {str(value) for value in raw_values}
        cardinality_ratio = len(unique_values) / max(1, row_count)
        per_asset_change_rate = _mean(change_rates)
        turnover_rate = per_asset_change_rate
        numeric_coverage = len(numeric_values) / max(1, row_count)
        numeric_volatility = pstdev(numeric_values) if len(numeric_values) >= 2 else 0.0
        stability_score = max(0.0, min(1.0, 1.0 - per_asset_change_rate))
        changed_asset_ratio = assets_with_changes / max(1, asset_count)
        static_asset_ratio = 1.0 - changed_asset_ratio
        timestamp_coverage = parsed_timestamp_count / max(1, row_count)
        median_observation_gap_days = _median_optional(observation_gaps_days)
        median_change_gap_days = _median_optional(change_gaps_days)
        estimated_update_cadence_days = median_change_gap_days
        if (
            estimated_update_cadence_days is None
            and median_observation_gap_days is not None
            and per_asset_change_rate > 0.0
        ):
            estimated_update_cadence_days = (
                median_observation_gap_days / per_asset_change_rate
            )
        half_life_periods = _change_half_life_periods(per_asset_change_rate)
        half_life_days = (
            half_life_periods * median_observation_gap_days
            if half_life_periods is not None and median_observation_gap_days is not None
            else None
        )
        observation_span_days = (
            (last_timestamp - first_timestamp).total_seconds() / 86_400
            if first_timestamp is not None and last_timestamp is not None
            else None
        )
        diagnostic_confidence = "high"
        diagnostic_notes: list[str] = []
        if row_count < 6 or asset_count < 2:
            diagnostic_confidence = "medium"
            diagnostic_notes.append(
                "Small sample: treat temporal class as research guidance, "
                + "not final taxonomy."
            )
        if timestamp_coverage < 0.8:
            diagnostic_confidence = "low"
            diagnostic_notes.append(
                "Timestamp coverage below 80%; cadence and half-life "
                + "diagnostics may be unstable."
            )
        if not change_gaps_days:
            diagnostic_notes.append(
                "No observed value-change intervals; update cadence is not "
                + "directly estimable."
            )

        temporal_class: TemporalClass
        if per_asset_change_rate <= static_change_threshold:
            temporal_class = "static_descriptor"
        elif per_asset_change_rate <= slow_change_threshold:
            temporal_class = "slow_moving_descriptor"
        else:
            temporal_class = "dynamic_signal"

        direct_regression_allowed = temporal_class == "dynamic_signal"
        recommended_uses = (
            [
                "cohort_index_construction",
                "cohort_return_index",
                "rotation_research",
                "conditional_factor_evaluation",
                "neutralization_or_risk_context",
            ]
            if not direct_regression_allowed
            else ["factor_return_regression", "standard_factor_evaluation"]
        )
        blocked_reason = (
            "E_STATIC_OR_SLOW_FACTOR_DIRECT_REGRESSION_BLOCKED"
            if not direct_regression_allowed
            else ""
        )
        diagnostics = {
            "row_count": row_count,
            "asset_count": asset_count,
            "unique_value_count": len(unique_values),
            "cross_sectional_cardinality": round(cardinality_ratio, 8),
            "per_asset_change_rate": round(per_asset_change_rate, 8),
            "turnover_rate": round(turnover_rate, 8),
            "numeric_coverage": round(numeric_coverage, 8),
            "numeric_volatility": round(numeric_volatility, 8),
            "changed_asset_count": assets_with_changes,
            "changed_asset_ratio": round(changed_asset_ratio, 8),
            "static_asset_ratio": round(static_asset_ratio, 8),
            "timestamp_coverage": round(timestamp_coverage, 8),
            "observation_span_days": _round_optional(observation_span_days),
            "median_observation_gap_days": _round_optional(median_observation_gap_days),
            "estimated_update_cadence_days": _round_optional(
                estimated_update_cadence_days
            ),
            "change_half_life_periods": _round_optional(half_life_periods),
            "change_half_life_days": _round_optional(half_life_days),
            "asset_observation_min": min(asset_observation_counts, default=0),
            "asset_observation_max": max(asset_observation_counts, default=0),
            "asset_observation_mean": round(_mean(asset_observation_counts), 8),
            "first_timestamp": first_timestamp.isoformat()
            if first_timestamp is not None
            else "",
            "last_timestamp": last_timestamp.isoformat()
            if last_timestamp is not None
            else "",
            "diagnostic_confidence": diagnostic_confidence,
            "diagnostic_notes": diagnostic_notes,
        }
        now = utcnow()
        profile_id = (
            "ftprof_"
            + sha256_hash(
                {
                    "factor_ref": factor_ref,
                    "dataset_version": resolved_dataset_version,
                    "value_column": value_column,
                    "diagnostics": diagnostics,
                }
            )[:20]
        )
        payload = {
            "schema_version": TEMPORAL_DYNAMICS_SCHEMA_VERSION,
            "record_type": "factor_temporal_profile",
            "profile_id": profile_id,
            "factor_ref": factor_ref,
            "dataset_version": resolved_dataset_version,
            "source_mode": source_mode,
            "value_column": value_column,
            "temporal_class": temporal_class,
            "stability_score": round(stability_score, 8),
            "turnover_rate": round(turnover_rate, 8),
            "cross_sectional_cardinality": round(cardinality_ratio, 8),
            "per_asset_change_rate": round(per_asset_change_rate, 8),
            "diagnostics": diagnostics,
            "routing_decision": {
                "direct_regression_allowed": direct_regression_allowed,
                "recommended_uses": recommended_uses,
                "blocked_reason": blocked_reason,
                "policy": "static_slow_direct_regression_hard_block@1.0",
            },
            "generated_by": generated_by,
            "generated_at": now,
        }
        artifact = materialize_artifact(profile_id, "factor_temporal_profile", payload)
        record: dict[str, object] = {
            **payload,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
        }
        upsert_record("factor_temporal_profiles", profile_id, record)
        _ = event_store.append(
            event_type="factor_temporal_profile.created",
            payload={
                "profile_id": profile_id,
                "temporal_class": temporal_class,
                "direct_regression_allowed": direct_regression_allowed,
            },
            run_id=profile_id,
        )
        return record

    def create_cohort_index(
        self,
        *,
        name: str,
        descriptor_ref: str,
        membership_rows: Sequence[Mapping[str, object]] | None = None,
        membership_dataset_version: str | None = None,
        membership_value_column: str = "member",
        cohort_value: str | None = None,
        weighting_method: CohortWeightingMethod = "equal_weight",
        as_of_time: str = "",
        description: str = "",
        created_by: str,
    ) -> dict[str, object]:
        if not name.strip():
            raise ValidationError("name is required")
        rows, dataset_version, source_mode = _load_rows(
            rows=membership_rows,
            dataset_version=membership_dataset_version,
        )
        members: list[dict[str, object]] = []
        seen: set[str] = set()
        cutoff_time = _string(as_of_time)
        timed_member_count = 0
        eligible_rows: list[tuple[str, dict[str, object], str, str]] = []
        for row in rows:
            asset_id = _asset_id(row)
            membership_timestamp = _optional_timestamp(row)
            available_at = _string(row.get("available_at"))
            if cutoff_time and not (membership_timestamp or available_at):
                raise ValidationError(
                    "cohort membership row missing PIT timing for as_of_time"
                )
            if (
                membership_timestamp
                and available_at
                and _time_after(available_at, membership_timestamp)
            ):
                message = (
                    "cohort membership row available_at must be <= "
                    + "membership timestamp"
                )
                raise ValidationError(message)
            if (
                cutoff_time
                and membership_timestamp
                and _time_after(membership_timestamp, cutoff_time)
            ):
                raise ValidationError(
                    "cohort membership timestamp must be <= as_of_time"
                )
            if cutoff_time and available_at and _time_after(available_at, cutoff_time):
                raise ValidationError(
                    "cohort membership available_at must be <= as_of_time"
                )

            eligible_rows.append(
                (asset_id, dict(row), membership_timestamp, available_at)
            )

        for asset_id, row, membership_timestamp, available_at in eligible_rows:
            if asset_id in seen:
                continue
            raw_value = row.get(membership_value_column, True)
            include = bool(raw_value)
            if cohort_value is not None:
                include = str(raw_value) == str(cohort_value)
            if include:
                seen.add(asset_id)
                if membership_timestamp or available_at:
                    timed_member_count += 1
                member = {
                    "asset_id": asset_id,
                    "symbol": _string(row.get("symbol")) or asset_id,
                    "descriptor_value": raw_value,
                    "membership_timestamp": membership_timestamp,
                    "available_at": available_at or membership_timestamp,
                }
                for size_field in ("market_cap", "float_market_cap"):
                    size_value = _positive_optional_field(row, size_field)
                    if size_value is not None:
                        member[size_field] = size_value
                members.append(member)
        if not members:
            raise ValidationError("cohort index requires at least one member")
        now = utcnow()
        cohort_index_id = (
            "cohort_"
            + sha256_hash(
                {
                    "name": name,
                    "descriptor_ref": descriptor_ref,
                    "dataset_version": dataset_version,
                    "members": members,
                    "weighting_method": weighting_method,
                }
            )[:20]
        )
        payload = {
            "schema_version": TEMPORAL_DYNAMICS_SCHEMA_VERSION,
            "record_type": "cohort_index_definition",
            "cohort_index_id": cohort_index_id,
            "name": name,
            "description": description,
            "descriptor_ref": descriptor_ref,
            "membership_dataset_version": dataset_version,
            "membership_source_mode": source_mode,
            "membership_value_column": membership_value_column,
            "cohort_value": cohort_value or "",
            "weighting_method": weighting_method,
            "as_of_time": as_of_time,
            "pit_diagnostics": {
                "cutoff_applied": bool(cutoff_time),
                "timed_member_count": timed_member_count,
                "untimed_member_count": len(members) - timed_member_count,
            },
            "member_count": len(members),
            "members": members,
            "created_by": created_by,
            "created_at": now,
            "asset_kind": "cohort_index",
            "factor_lifecycle_mutation": False,
        }
        artifact = materialize_artifact(
            cohort_index_id,
            "cohort_index_definition",
            payload,
        )
        record: dict[str, object] = {
            **payload,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
        }
        upsert_record("cohort_index_definitions", cohort_index_id, record)
        _ = event_store.append(
            event_type="cohort_index_definition.created",
            payload={"cohort_index_id": cohort_index_id, "member_count": len(members)},
            run_id=cohort_index_id,
        )
        return record

    def get_cohort_index(self, cohort_index_id: str) -> dict[str, object]:
        record = get_record("cohort_index_definitions", cohort_index_id)
        if record is None:
            raise NotFoundError(f"cohort index not found: {cohort_index_id}")
        return dict(record)

    def materialize_cohort_returns(
        self,
        *,
        cohort_index_id: str,
        price_rows: Sequence[Mapping[str, object]] | None = None,
        price_dataset_version: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        price_column: str = "close",
        generated_by: str,
    ) -> dict[str, object]:
        definition = self.get_cohort_index(cohort_index_id)
        member_records = cast(list[Mapping[str, object]], definition.get("members", []))
        members = [str(item.get("asset_id")) for item in member_records]
        member_set = set(members)
        weighting_method = str(definition.get("weighting_method") or "equal_weight")
        if weighting_method not in (
            "equal_weight",
            "market_cap_weight",
            "float_market_cap_weight",
        ):
            raise ValidationError(f"unsupported weighting_method: {weighting_method}")
        weight_field = WEIGHT_FIELD_BY_METHOD.get(weighting_method, "")
        static_weights = {
            str(item.get("asset_id")): _positive_optional_field(item, weight_field)
            for item in member_records
        }
        if weighting_method != "equal_weight" and not any(
            value is not None for value in static_weights.values()
        ):
            # Daily price rows may still provide the weight field, so do not fail yet.
            pass
        rows, dataset_version, source_mode = _load_rows(
            rows=price_rows,
            dataset_version=price_dataset_version,
        )
        prices_by_asset: dict[str, dict[str, float]] = defaultdict(dict)
        caps_by_asset: dict[str, dict[str, float]] = defaultdict(dict)
        for row in rows:
            asset_id = _asset_id(row)
            if asset_id not in member_set:
                continue
            date_key = _timestamp(row)
            if start_time and date_key < start_time:
                continue
            if end_time and date_key > end_time:
                continue
            if price_column not in row:
                raise ValidationError(f"row missing price_column: {price_column}")
            prices_by_asset[asset_id][date_key] = _float(
                row[price_column], field_name=price_column
            )
            if weight_field:
                cap_value = _positive_optional_field(row, weight_field)
                if cap_value is not None:
                    caps_by_asset[asset_id][date_key] = cap_value
        dates = sorted({date for values in prices_by_asset.values() for date in values})
        if len(dates) < 2:
            raise ValidationError("cohort return materialization requires >=2 dates")
        nav = 1.0
        result_rows: list[dict[str, object]] = []
        previous_prices: dict[str, float] = {}
        previous_caps: dict[str, float] = {}
        for date_key in dates:
            returns_by_asset: dict[str, float] = {}
            active_assets: list[str] = []
            for asset_id in members:
                price = prices_by_asset.get(asset_id, {}).get(date_key)
                if price is None:
                    continue
                active_assets.append(asset_id)
                previous = previous_prices.get(asset_id)
                if previous is not None and previous > 0.0:
                    returns_by_asset[asset_id] = price / previous - 1.0
                previous_prices[asset_id] = price

            weights: dict[str, float] = {}
            if returns_by_asset:
                if weighting_method == "equal_weight":
                    weight = 1.0 / len(returns_by_asset)
                    weights = {asset_id: weight for asset_id in returns_by_asset}
                else:
                    raw_weights: dict[str, float] = {}
                    missing_weight_assets: list[str] = []
                    for asset_id in returns_by_asset:
                        cap = previous_caps.get(asset_id) or static_weights.get(
                            asset_id
                        )
                        if cap is None or cap <= 0.0:
                            missing_weight_assets.append(asset_id)
                        else:
                            raw_weights[asset_id] = cap
                    if missing_weight_assets:
                        raise ValidationError(
                            f"{weighting_method} requires positive {weight_field} "
                            + "for all returning assets; missing "
                            + ",".join(sorted(missing_weight_assets))
                        )
                    total_weight = sum(raw_weights.values())
                    if total_weight <= 0.0:
                        raise ValidationError(
                            f"{weighting_method} requires positive total {weight_field}"
                        )
                    weights = {
                        asset_id: raw_weight / total_weight
                        for asset_id, raw_weight in raw_weights.items()
                    }
            daily_return = sum(
                returns_by_asset[asset_id] * weights.get(asset_id, 0.0)
                for asset_id in returns_by_asset
            )
            if returns_by_asset:
                nav *= 1.0 + daily_return
            weight_sum = sum(weights.values())
            max_weight = max(weights.values(), default=0.0)
            result_rows.append(
                {
                    "timestamp": date_key,
                    "daily_return": round(daily_return, 10),
                    "nav": round(nav, 10),
                    "constituent_count": len(active_assets),
                    "return_count": len(returns_by_asset),
                    "weighting_method": weighting_method,
                    "weight_field": weight_field,
                    "weight_sum": round(weight_sum, 10),
                    "max_weight": round(max_weight, 10),
                    "turnover": 0.0,
                }
            )
            if weight_field:
                for asset_id in members:
                    cap = caps_by_asset.get(asset_id, {}).get(date_key)
                    if cap is not None:
                        previous_caps[asset_id] = cap
        frame_id = (
            "cohortret_"
            + sha256_hash(
                {
                    "cohort_index_id": cohort_index_id,
                    "price_dataset_version": dataset_version,
                    "rows": result_rows,
                    "price_column": price_column,
                    "weighting_method": weighting_method,
                    "weight_field": weight_field,
                }
            )[:20]
        )
        payload = {
            "schema_version": TEMPORAL_DYNAMICS_SCHEMA_VERSION,
            "record_type": "cohort_index_return_frame",
            "return_frame_id": frame_id,
            "cohort_index_id": cohort_index_id,
            "price_dataset_version": dataset_version,
            "price_source_mode": source_mode,
            "price_column": price_column,
            "start_time": start_time or "",
            "end_time": end_time or "",
            "row_count": len(result_rows),
            "rows": result_rows,
            "summary": {
                "final_nav": round(nav, 10),
                "total_return": round(nav - 1.0, 10),
                "member_count": len(members),
                "weighting_method": weighting_method,
                "weight_field": weight_field,
                "min_constituent_count": min(
                    int(str(row["constituent_count"])) for row in result_rows
                ),
            },
            "generated_by": generated_by,
            "generated_at": utcnow(),
            "factor_lifecycle_mutation": False,
        }
        artifact = materialize_artifact(frame_id, "cohort_index_return_frame", payload)
        record: dict[str, object] = {
            **payload,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
        }
        upsert_record("cohort_index_return_frames", frame_id, record)
        _ = event_store.append(
            event_type="cohort_index_return_frame.created",
            payload={"return_frame_id": frame_id, "cohort_index_id": cohort_index_id},
            run_id=frame_id,
        )
        return record

    def evaluate_conditional_factor(
        self,
        *,
        factor_id: str,
        signal_rows: Sequence[Mapping[str, object]] | None = None,
        signal_dataset_version: str | None = None,
        descriptor_rows: Sequence[Mapping[str, object]] | None = None,
        descriptor_dataset_version: str | None = None,
        label_rows: Sequence[Mapping[str, object]] | None = None,
        label_dataset_version: str | None = None,
        signal_value_column: str = "factor_value",
        descriptor_value_column: str = "descriptor_value",
        label_value_column: str = "forward_return",
        min_bucket_samples: int = 2,
        generated_by: str,
    ) -> dict[str, object]:
        if not factor_id.strip():
            raise ValidationError("factor_id is required")
        if min_bucket_samples < 2:
            raise ValidationError("min_bucket_samples must be >= 2")
        signals, signal_dataset, signal_source_mode = _load_rows(
            rows=signal_rows,
            dataset_version=signal_dataset_version,
        )
        descriptors, descriptor_dataset, descriptor_source_mode = _load_rows(
            rows=descriptor_rows,
            dataset_version=descriptor_dataset_version,
        )
        labels, label_dataset, label_source_mode = _load_rows(
            rows=label_rows,
            dataset_version=label_dataset_version,
        )

        descriptor_history: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in descriptors:
            if descriptor_value_column not in row:
                raise ValidationError(
                    f"descriptor row missing value_column: {descriptor_value_column}"
                )
            if _leaks_available_at(row):
                raise ValidationError(
                    "conditional descriptor rows violate PIT available_at"
                )
            _ = _timestamp(row)
            descriptor_history[_asset_id(row)].append(row)
        for asset_rows in descriptor_history.values():
            asset_rows.sort(key=_timestamp)

        labels_by_key: dict[tuple[str, str], float] = {}
        for row in labels:
            if label_value_column not in row:
                raise ValidationError(
                    f"label row missing value_column: {label_value_column}"
                )
            labels_by_key[(_asset_id(row), _timestamp(row))] = _float(
                row[label_value_column], field_name=label_value_column
            )

        bucket_points: dict[str, list[dict[str, object]]] = defaultdict(list)
        dropped = {
            "missing_descriptor": 0,
            "missing_label": 0,
            "signal_pit_violation": 0,
        }
        for row in signals:
            if signal_value_column not in row:
                raise ValidationError(
                    f"signal row missing value_column: {signal_value_column}"
                )
            if _leaks_available_at(row):
                dropped["signal_pit_violation"] += 1
                continue
            asset_id = _asset_id(row)
            timestamp = _timestamp(row)
            descriptor = self._latest_descriptor_for_signal(
                descriptor_history.get(asset_id, []),
                signal_timestamp=timestamp,
            )
            if descriptor is None:
                dropped["missing_descriptor"] += 1
                continue
            label = labels_by_key.get((asset_id, timestamp))
            if label is None:
                dropped["missing_label"] += 1
                continue
            bucket = str(descriptor[descriptor_value_column])
            bucket_points[bucket].append(
                {
                    "asset_id": asset_id,
                    "timestamp": timestamp,
                    "bucket": bucket,
                    "signal_value": _float(
                        row[signal_value_column], field_name=signal_value_column
                    ),
                    "label_value": label,
                    "descriptor_timestamp": _timestamp(descriptor),
                    "descriptor_available_at": _string(descriptor.get("available_at")),
                }
            )
        if dropped["signal_pit_violation"]:
            raise ValidationError("conditional signal rows violate PIT available_at")
        if not bucket_points:
            raise ValidationError("conditional evaluation produced no aligned rows")

        bucket_reports: list[dict[str, object]] = []
        for bucket, points in sorted(bucket_points.items()):
            signals_for_bucket = [float(str(point["signal_value"])) for point in points]
            labels_for_bucket = [float(str(point["label_value"])) for point in points]
            sufficient = len(points) >= min_bucket_samples
            ic = _pearson(signals_for_bucket, labels_for_bucket) if sufficient else 0.0
            spread = self._median_signal_spread(points) if sufficient else 0.0
            bucket_reports.append(
                {
                    "bucket": bucket,
                    "sample_count": len(points),
                    "sufficient_samples": sufficient,
                    "information_coefficient": round(ic, 10),
                    "mean_forward_return": round(_mean(labels_for_bucket), 10),
                    "top_minus_bottom_return_spread": round(spread, 10),
                    "diagnostics": {
                        "reason_code": (
                            "" if sufficient else "E_INSUFFICIENT_BUCKET_SAMPLES"
                        ),
                        "min_bucket_samples": min_bucket_samples,
                    },
                }
            )
        sufficient_reports = [
            report for report in bucket_reports if bool(report["sufficient_samples"])
        ]
        aligned_sample_count = sum(
            int(str(report["sample_count"])) for report in bucket_reports
        )
        best_bucket = max(
            sufficient_reports,
            key=lambda report: abs(float(str(report["information_coefficient"]))),
            default={},
        )
        bucket_mean_returns = [
            float(str(report["mean_forward_return"])) for report in sufficient_reports
        ]
        between_bucket_mean_return_spread = (
            max(bucket_mean_returns) - min(bucket_mean_returns)
            if len(bucket_mean_returns) >= 2
            else 0.0
        )
        report_id = (
            "condfeval_"
            + sha256_hash(
                {
                    "factor_id": factor_id,
                    "signal_dataset": signal_dataset,
                    "descriptor_dataset": descriptor_dataset,
                    "label_dataset": label_dataset,
                    "columns": [
                        signal_value_column,
                        descriptor_value_column,
                        label_value_column,
                    ],
                    "buckets": bucket_reports,
                }
            )[:20]
        )
        payload = {
            "schema_version": TEMPORAL_DYNAMICS_SCHEMA_VERSION,
            "record_type": "conditional_factor_evaluation_report",
            "report_id": report_id,
            "factor_id": factor_id,
            "signal_dataset_version": signal_dataset,
            "descriptor_dataset_version": descriptor_dataset,
            "label_dataset_version": label_dataset,
            "source_modes": {
                "signal": signal_source_mode,
                "descriptor": descriptor_source_mode,
                "label": label_source_mode,
            },
            "columns": {
                "signal_value_column": signal_value_column,
                "descriptor_value_column": descriptor_value_column,
                "label_value_column": label_value_column,
            },
            "bucket_reports": bucket_reports,
            "summary": {
                "bucket_count": len(bucket_reports),
                "sufficient_bucket_count": len(sufficient_reports),
                "aligned_sample_count": aligned_sample_count,
                "dropped_rows": dropped,
                "best_bucket_by_abs_ic": best_bucket,
                "between_bucket_mean_return_spread": round(
                    between_bucket_mean_return_spread,
                    10,
                ),
            },
            "diagnostics": {
                "min_bucket_samples": min_bucket_samples,
                "insufficient_bucket_count": (
                    len(bucket_reports) - len(sufficient_reports)
                ),
            },
            "auto_action_taken": False,
            "factor_lifecycle_mutation": False,
            "generated_by": generated_by,
            "generated_at": utcnow(),
        }
        artifact = materialize_artifact(
            report_id,
            "conditional_factor_evaluation_report",
            payload,
        )
        record: dict[str, object] = {
            **payload,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
        }
        upsert_record("conditional_factor_evaluation_reports", report_id, record)
        _ = event_store.append(
            event_type="conditional_factor_evaluation_report.created",
            payload={"report_id": report_id, "auto_action_taken": False},
            run_id=report_id,
        )
        return record

    @staticmethod
    def _latest_descriptor_for_signal(
        descriptor_rows: Sequence[Mapping[str, object]],
        *,
        signal_timestamp: str,
    ) -> Mapping[str, object] | None:
        selected: Mapping[str, object] | None = None
        for descriptor in descriptor_rows:
            if _time_after(_timestamp(descriptor), signal_timestamp):
                break
            selected = descriptor
        return selected

    @staticmethod
    def _median_signal_spread(points: Sequence[Mapping[str, object]]) -> float:
        ordered = sorted(points, key=lambda item: float(str(item["signal_value"])))
        midpoint = len(ordered) // 2
        lower = ordered[:midpoint]
        upper = ordered[midpoint:]
        if not lower or not upper:
            return 0.0
        return _mean([float(str(point["label_value"])) for point in upper]) - _mean(
            [float(str(point["label_value"])) for point in lower]
        )

    def analyze_rotation(
        self,
        *,
        source_return_frame_id: str,
        target_return_frame_id: str,
        lookback_periods: int = 3,
        forward_periods: int = 1,
        generated_by: str,
    ) -> dict[str, object]:
        if lookback_periods < 1 or forward_periods < 1:
            raise ValidationError("lookback_periods and forward_periods must be >= 1")
        source_frame = get_record("cohort_index_return_frames", source_return_frame_id)
        target_frame = get_record("cohort_index_return_frames", target_return_frame_id)
        if source_frame is None:
            raise NotFoundError(
                f"source return frame not found: {source_return_frame_id}"
            )
        if target_frame is None:
            raise NotFoundError(
                f"target return frame not found: {target_return_frame_id}"
            )
        source_payload = artifact_payload(source_frame) or dict(source_frame)
        target_payload = artifact_payload(target_frame) or dict(target_frame)
        source_rows = self._return_rows(source_payload)
        target_rows = self._return_rows(target_payload)
        target_by_date = {str(row["timestamp"]): row for row in target_rows}
        aligned_dates = [
            str(row["timestamp"])
            for row in source_rows
            if str(row["timestamp"]) in target_by_date
        ]
        source_by_date = {str(row["timestamp"]): row for row in source_rows}
        signal_rows: list[dict[str, object]] = []
        source_signals: list[float] = []
        target_forwards: list[float] = []
        for index in range(lookback_periods - 1, len(aligned_dates) - forward_periods):
            lookback_dates = aligned_dates[index - lookback_periods + 1 : index + 1]
            forward_dates = aligned_dates[index + 1 : index + 1 + forward_periods]
            source_signal = _mean(
                [
                    float(str(source_by_date[date]["daily_return"]))
                    for date in lookback_dates
                ]
            )
            target_forward = _compound_return(
                [
                    float(str(target_by_date[date]["daily_return"]))
                    for date in forward_dates
                ]
            )
            source_signals.append(source_signal)
            target_forwards.append(target_forward)
            signal_rows.append(
                {
                    "as_of_timestamp": aligned_dates[index],
                    "source_signal": round(source_signal, 10),
                    "target_forward_return": round(target_forward, 10),
                    "direction_match": (source_signal >= 0.0 and target_forward >= 0.0)
                    or (source_signal < 0.0 and target_forward < 0.0),
                }
            )
        sample_count = len(signal_rows)
        insufficient = sample_count < 2
        hit_rate = (
            sum(1 for row in signal_rows if bool(row["direction_match"])) / sample_count
            if sample_count
            else 0.0
        )
        correlation = _pearson(source_signals, target_forwards)
        report_id = (
            "rotation_"
            + sha256_hash(
                {
                    "source": source_return_frame_id,
                    "target": target_return_frame_id,
                    "lookback_periods": lookback_periods,
                    "forward_periods": forward_periods,
                    "signals": signal_rows,
                }
            )[:20]
        )
        payload = {
            "schema_version": TEMPORAL_DYNAMICS_SCHEMA_VERSION,
            "record_type": "factor_rotation_report",
            "report_id": report_id,
            "source_return_frame_id": source_return_frame_id,
            "target_return_frame_id": target_return_frame_id,
            "lookback_periods": lookback_periods,
            "forward_periods": forward_periods,
            "sample_count": sample_count,
            "lead_lag_correlation": round(correlation, 10),
            "hit_rate": round(hit_rate, 10),
            "signal_rows": signal_rows,
            "diagnostics": {
                "aligned_periods": len(aligned_dates),
                "insufficient_samples": insufficient,
                "reason_code": (
                    "E_INSUFFICIENT_ROTATION_SAMPLES" if insufficient else ""
                ),
            },
            "notify_only": True,
            "auto_action_taken": False,
            "factor_lifecycle_mutation": False,
            "generated_by": generated_by,
            "generated_at": utcnow(),
        }
        artifact = materialize_artifact(report_id, "factor_rotation_report", payload)
        record: dict[str, object] = {
            **payload,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
        }
        upsert_record("factor_rotation_reports", report_id, record)
        _ = event_store.append(
            event_type="factor_rotation_report.created",
            payload={"report_id": report_id, "notify_only": True},
            run_id=report_id,
        )
        return record

    @staticmethod
    def _return_rows(payload: Mapping[str, object]) -> list[dict[str, object]]:
        raw_rows = payload.get("rows", [])
        if not isinstance(raw_rows, list):
            return []
        rows = [
            dict(cast(Mapping[str, object], row))
            for row in raw_rows
            if isinstance(row, Mapping)
        ]
        return sorted(rows, key=lambda row: str(row.get("timestamp", "")))


factor_temporal_dynamics_service = FactorTemporalDynamicsService()
