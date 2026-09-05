"""Factor evaluation service."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from factor_lab.core.errors import (
    GateBlockedError,
    JsonValue,
    NotFoundError,
    ValidationError,
)
from factor_lab.core.runtime_records import artifact_payload, get_record
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.core.settings import get_artifacts_dir
from factor_lab.core.source_universe import (
    SourceUniverseGateStatus,
    assert_consistent_source_family,
    optional_source_family,
    source_family_for_dataset_version,
    source_refs_for_dataset_version,
)
from factor_lab.core.storage import read_json_storage_uri, to_portable_storage_uri
from factor_lab.core.versions import validate_policy_pack
from factor_lab.evaluation.engine import EvaluationEngine, EvaluationObservation
from factor_lab.evaluation.label_builder import LabelBuilder
from factor_lab.evaluation.oos_analyzer import analyze_oos
from factor_lab.evaluation.preprocessing import (
    apply_preprocess_config,
    apply_preprocess_spec,
)
from factor_lab.evaluation.report_generator import ReportGenerator
from factor_lab.evaluation.risk_exposure_analyzer import analyze_risk_exposure
from factor_lab.factor_engine.advanced_factors import (
    build_advanced_factor_frame,
    get_advanced_factor_spec,
)
from factor_lab.factor_engine.dsl import build_dsl_factor_frame
from factor_lab.factor_engine.models.factor_spec import FactorSpec
from factor_lab.factor_engine.repositories.spec_registry import spec_registry
from factor_lab.factor_engine.standard_factors import (
    build_standard_factor_frame,
    get_standard_factor_spec,
)
from factor_lab.governance.multiple_testing import build_multiple_testing_report
from factor_lab.governance.run_snapshot import RunSnapshot
from factor_lab.governance.services.event_store import event_store
from factor_lab.governance.services.state_machine import JobStatus, RunStatus
from factor_lab.governance.temporal_integrity import (
    CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY,
    validate_temporal_evaluation_contract,
)

TEMPORAL_ROUTING_GATE_NAME = "factor_temporal_routing"
TEMPORAL_ROUTING_POLICY = "static_slow_direct_regression_hard_block@1.0"


@dataclass(slots=True)
class EvaluationRunRecord:
    run_id: str
    run_type: str
    status: str
    dataset_version: str
    factor_spec_version: str
    preprocess_spec_version: str
    label_spec_version: str
    protocol_version: str
    policy_pack: str
    code_version: str
    seed: int
    principal_id: str
    created_at: str
    source_family: str = ""
    factor_temporal_profile_id: str = ""
    factor_temporal_class: str = ""
    temporal_routing_decision: dict[str, object] | None = None
    temporal_routing_policy: str = ""
    preprocessing_config: dict[str, object] | None = None
    neutralization_config: dict[str, object] | None = None
    selection_context: dict[str, object] | None = None
    code_dirty: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class EvaluationJobRecord:
    job_id: str
    run_id: str
    status: str
    status_uri: str
    job_type: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class EvaluationArtifactRecord:
    artifact_id: str
    run_id: str
    artifact_type: str
    artifact_name: str
    publish_state: str
    storage_uri: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _int_from_object(value: object) -> int:
    return int(str(value))


def _positive_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _float_from_object(value: object) -> float:
    return float(str(value))


def _parse_instant_for_leakage(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _row_violates_availability(row: Mapping[str, object]) -> bool:
    available_at = _parse_instant_for_leakage(row.get("available_at"))
    decision_time = _parse_instant_for_leakage(row.get("decision_time"))
    if available_at is None or decision_time is None:
        return True
    return available_at > decision_time


def _profile_timestamp(row: Mapping[str, object]) -> str:
    """Use end-of-day timestamps for daily temporal diagnostics.

    Existing price-volume factor rows use the bar timestamp (for example 09:30)
    and same-day post-close availability (for example 15:00).  The temporal
    classifier needs daily ordering, not intraday execution timing, so diagnostic
    copies are normalized to the row's as-of day end while preserving real rows
    for evaluation/leakage artifacts.
    """

    asof_date = str(row.get("asof_date") or "").strip()
    if asof_date:
        return f"{asof_date.split('T', maxsplit=1)[0]}T23:59:59Z"
    timestamp = str(row.get("timestamp") or row.get("date") or "").strip()
    if "T" in timestamp:
        return f"{timestamp.split('T', maxsplit=1)[0]}T23:59:59Z"
    return timestamp


class FactorEvaluationService:
    """Service for factor evaluation."""

    def __init__(self):
        self._runs: dict[str, EvaluationRunRecord] = {}
        self._jobs: dict[str, EvaluationJobRecord] = {}
        self._artifacts: dict[str, EvaluationArtifactRecord] = {}
        self._report_generator: ReportGenerator = ReportGenerator()

    def _artifacts_dir(self) -> Path:
        return get_artifacts_dir()

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[4]

    @classmethod
    def _fixture_root(cls) -> Path:
        return cls._project_root() / "tests" / "fixtures"

    def _materialize_artifact(
        self,
        run_id: str,
        artifact_type: str,
        payload: dict[str, object],
    ) -> EvaluationArtifactRecord:
        artifact_id = str(uuid.uuid4())
        artifact_dir = self._artifacts_dir() / run_id / artifact_type / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        content_path = artifact_dir / "content.json"
        _ = content_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        artifact = EvaluationArtifactRecord(
            artifact_id=artifact_id,
            run_id=run_id,
            artifact_type=artifact_type,
            artifact_name=f"{artifact_type}.json",
            publish_state="published",
            storage_uri=to_portable_storage_uri(content_path),
        )
        self._artifacts[artifact_id] = artifact
        runtime_state_store.upsert("artifacts", artifact_id, artifact.to_dict())
        _ = event_store.append(
            event_type="artifact.published",
            payload={
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "storage_uri": artifact.storage_uri,
            },
            run_id=run_id,
        )
        return artifact

    @classmethod
    def _load_json_fixture(cls, path: Path) -> dict[str, object]:
        payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
        return cast(dict[str, object], payload) if isinstance(payload, dict) else {}

    @classmethod
    def _load_protocol_config(cls, protocol_version: str) -> dict[str, object]:
        protocol_file = (
            cls._project_root()
            / "docs"
            / "schemas"
            / "json"
            / f"{protocol_version}.json"
        )
        if protocol_file.exists():
            payload = cls._load_json_fixture(protocol_file)
            return {
                "horizon": payload.get("horizon", "1d"),
                "groups": payload.get("groups", ["quantile_5"]),
                "metrics": payload.get("metrics", ["ic", "rank_ic", "turnover"]),
            }
        return {
            "horizon": "1d",
            "groups": ["quantile_5"],
            "metrics": ["ic", "rank_ic", "turnover"],
        }

    @classmethod
    def _load_label_builder(cls, label_spec_version: str) -> tuple[LabelBuilder, str]:
        label_file = cls._fixture_root() / "label_specs" / f"{label_spec_version}.json"
        if label_file.exists():
            payload = cls._load_json_fixture(label_file)
            horizon = str(payload.get("horizon", "5d"))
            exclude_current_bar = bool(payload.get("exclude_current_bar", True))
            label_name = str(payload.get("name", label_spec_version))
            return LabelBuilder(
                horizon=horizon, exclude_current_bar=exclude_current_bar
            ), label_name
        return LabelBuilder(horizon="5d", exclude_current_bar=True), label_spec_version

    @classmethod
    def _resolve_factor_name(cls, factor_spec_version: str) -> str:
        factor_file = (
            cls._fixture_root() / "factor_specs" / f"{factor_spec_version}.json"
        )
        if factor_file.exists():
            payload = cls._load_json_fixture(factor_file)
            output_schema = payload.get("output_schema", {})
            if isinstance(output_schema, dict):
                output_schema_dict = cast(dict[str, object], output_schema)
                factor_name = output_schema_dict.get("factor_name", "")
                if isinstance(factor_name, str) and factor_name:
                    return factor_name
        standard_spec = get_standard_factor_spec(factor_spec_version)
        if standard_spec is not None:
            factor_name = standard_spec.output_schema.get("factor_name")
            if isinstance(factor_name, str) and factor_name:
                return factor_name
        advanced_spec = get_advanced_factor_spec(factor_spec_version)
        if advanced_spec is not None:
            factor_name = advanced_spec.output_schema.get("factor_name")
            if isinstance(factor_name, str) and factor_name:
                return factor_name
        registered_spec = spec_registry.get_factor_spec_sync(factor_spec_version)
        if registered_spec is not None:
            factor_name = registered_spec.output_schema.get("factor_name")
            if isinstance(factor_name, str) and factor_name:
                return factor_name
            if registered_spec.name:
                return registered_spec.name
        if "mom" in factor_spec_version:
            return "momentum_20d"
        if "vol" in factor_spec_version:
            return "volatility_20d"
        return factor_spec_version.split("@", maxsplit=1)[0]

    @staticmethod
    def _runtime_dataset_rows(dataset_version: str) -> list[dict[str, object]]:
        state = runtime_state_store.load()
        for artifact in state["artifacts"].values():
            artifact_type = str(artifact.get("artifact_type", ""))
            if artifact_type not in {"pit_dataset_snapshot", "clean_dataset_snapshot"}:
                continue
            run_id = str(artifact.get("run_id", ""))
            source_run = state["runs"].get(run_id)
            if source_run is None:
                continue
            if str(source_run.get("run_type", "")) != "dataset_publish":
                continue
            if str(source_run.get("status", "")) != RunStatus.COMPLETED:
                continue
            storage_uri = artifact.get("storage_uri")
            if not isinstance(storage_uri, str):
                continue
            payload = read_json_storage_uri(storage_uri, allow_http=False)
            if not isinstance(payload, dict):
                continue
            payload_dict = cast(dict[str, object], payload)
            if str(payload_dict.get("dataset_version", "")) != dataset_version:
                continue
            rows = payload_dict.get("rows", [])
            if isinstance(rows, list):
                return cast(list[dict[str, object]], rows)
        return []

    @classmethod
    def _load_base_rows(cls, dataset_version: str) -> list[dict[str, object]]:
        runtime_rows = cls._runtime_dataset_rows(dataset_version)
        if runtime_rows:
            return runtime_rows
        raise NotFoundError(f"Published dataset artifact not found: {dataset_version}")

    @staticmethod
    def _expand_price_panel(
        base_rows: list[dict[str, object]], days: int = 8
    ) -> list[dict[str, object]]:
        if not base_rows:
            base_rows = [
                {
                    "symbol": "000001.SZ",
                    "timestamp": "2024-01-01T09:30:00Z",
                    "asof_date": "2024-01-01",
                    "available_at": "2024-01-01T15:00:00Z",
                    "open": 10.0,
                    "high": 10.4,
                    "low": 9.8,
                    "close": 10.2,
                    "volume": 1000000,
                },
                {
                    "symbol": "000002.SZ",
                    "timestamp": "2024-01-01T09:30:00Z",
                    "asof_date": "2024-01-01",
                    "available_at": "2024-01-01T15:00:00Z",
                    "open": 20.0,
                    "high": 20.6,
                    "low": 19.8,
                    "close": 20.3,
                    "volume": 1500000,
                },
                {
                    "symbol": "000003.SZ",
                    "timestamp": "2024-01-01T09:30:00Z",
                    "asof_date": "2024-01-01",
                    "available_at": "2024-01-01T15:00:00Z",
                    "open": 30.0,
                    "high": 30.8,
                    "low": 29.7,
                    "close": 30.5,
                    "volume": 1800000,
                },
            ]

        expanded: list[dict[str, object]] = []
        for day_index in range(days):
            date = f"2024-01-{day_index + 1:02d}"
            timestamp = f"{date}T09:30:00Z"
            available_at = f"{date}T15:00:00Z"
            for symbol_index, base_row in enumerate(base_rows):
                symbol = str(
                    base_row.get("symbol")
                    or base_row.get("asset_id")
                    or f"SYM{symbol_index}"
                )
                base_close = _float_from_object(
                    base_row.get("close", 10.0 + symbol_index)
                )
                drift = 1.0 + (day_index * 0.01) + (symbol_index * 0.005)
                close = round(base_close * drift, 6)
                open_price = round(close * (0.985 + symbol_index * 0.002), 6)
                high = round(close * 1.015, 6)
                low = round(close * 0.985, 6)
                volume = int(1000000 + (day_index * 25000) + (symbol_index * 75000))
                expanded_row: dict[str, object] = {
                    key: (
                        round(float(value) * drift, 6)
                        if isinstance(value, int | float)
                        and not isinstance(value, bool)
                        else value
                    )
                    for key, value in base_row.items()
                    if key
                    not in {
                        "symbol",
                        "asset_id",
                        "timestamp",
                        "asof_date",
                        "available_at",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                    }
                }
                expanded_row.update(
                    {
                        "symbol": symbol,
                        "asset_id": symbol,
                        "timestamp": timestamp,
                        "asof_date": date,
                        "available_at": available_at,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                    }
                )
                expanded.append(expanded_row)
        return expanded

    @classmethod
    def _load_price_rows(cls, dataset_version: str) -> list[dict[str, object]]:
        return cls._price_rows_from_base_rows(cls._load_base_rows(dataset_version))

    @staticmethod
    def _has_historical_panel_rows(base_rows: list[dict[str, object]]) -> bool:
        timestamps_by_symbol: dict[str, set[str]] = defaultdict(set)
        for row in base_rows:
            symbol = str(row.get("symbol") or row.get("asset_id") or "")
            timestamp = str(row.get("timestamp") or row.get("asof_date") or "")
            if symbol and timestamp:
                timestamps_by_symbol[symbol].add(timestamp)
        return any(len(timestamps) > 1 for timestamps in timestamps_by_symbol.values())

    @classmethod
    def _price_rows_from_base_rows(
        cls,
        base_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if cls._has_historical_panel_rows(base_rows):
            return sorted(
                [dict(row) for row in base_rows],
                key=lambda row: (
                    str(row.get("symbol") or row.get("asset_id") or ""),
                    str(row.get("timestamp") or row.get("asof_date") or ""),
                ),
            )
        return cls._expand_price_panel(base_rows)

    @staticmethod
    def _build_factor_rows(
        price_rows: list[dict[str, object]],
        factor_spec_version: str,
        factor_name: str,
        source_refs: list[str],
        factor_spec: FactorSpec | None = None,
    ) -> list[dict[str, object]]:
        if factor_spec is not None and factor_spec.factor_type == "materialized_frame":
            return FactorEvaluationService._build_materialized_factor_rows(
                factor_spec=factor_spec,
                factor_spec_version=factor_spec_version,
                factor_name=factor_name,
                source_refs=source_refs,
            )
        if get_standard_factor_spec(factor_spec_version) is not None:
            return build_standard_factor_frame(
                price_rows,
                factor_spec_version=factor_spec_version,
                source_refs=source_refs,
            )
        if get_advanced_factor_spec(factor_spec_version) is not None:
            return build_advanced_factor_frame(
                price_rows,
                factor_spec_version=factor_spec_version,
                source_refs=source_refs,
            )
        if factor_spec is not None and factor_spec.factor_type == "formulaic_dsl":
            return build_dsl_factor_frame(
                price_rows,
                factor_spec=factor_spec,
                source_refs=source_refs,
            )

        by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in price_rows:
            by_symbol[str(row["symbol"])].append(row)

        factor_rows: list[dict[str, object]] = []
        source_ref_list = list(dict.fromkeys(source_refs))
        for symbol_rows in by_symbol.values():
            ordered_rows = sorted(symbol_rows, key=lambda row: str(row["timestamp"]))
            previous_close: float | None = None
            for row in ordered_rows:
                open_price = _float_from_object(row["open"])
                close_price = _float_from_object(row["close"])
                high_price = _float_from_object(row["high"])
                low_price = _float_from_object(row["low"])
                if "mom" in factor_spec_version:
                    factor_value = (
                        (close_price / previous_close) - 1.0
                        if previous_close and previous_close != 0
                        else (close_price / open_price) - 1.0
                    )
                elif "vol" in factor_spec_version:
                    factor_value = (high_price - low_price) / close_price
                else:
                    factor_value = (
                        (close_price / previous_close) - 1.0
                        if previous_close and previous_close != 0
                        else (close_price - open_price) / open_price
                    )
                factor_rows.append(
                    {
                        "symbol": str(row["symbol"]),
                        "timestamp": str(row["timestamp"]),
                        "asof_date": str(row["asof_date"]),
                        "available_at": str(row["available_at"]),
                        "factor_value": round(factor_value, 6),
                        "factor_name": factor_name,
                        "factor_spec_version": factor_spec_version,
                        "source_refs": source_ref_list,
                        "input_field_lineage": {
                            field: f"dataset.rows[].{field}"
                            for field in ("open", "high", "low", "close", "volume")
                        },
                    }
                )
                previous_close = close_price
        return factor_rows

    @staticmethod
    def _build_materialized_factor_rows(
        *,
        factor_spec: FactorSpec,
        factor_spec_version: str,
        factor_name: str,
        source_refs: list[str],
    ) -> list[dict[str, object]]:
        materialized_ref = factor_spec.materialized_frame_ref.strip()
        prefix = "latent_factor_exposure_frame:"
        if not materialized_ref.startswith(prefix):
            raise ValidationError(
                "Unsupported materialized_frame_ref",
                details={"materialized_frame_ref": materialized_ref},
            )
        exposure_frame_id = materialized_ref.removeprefix(prefix)
        frame_record = get_record("latent_factor_exposure_frames", exposure_frame_id)
        if frame_record is None:
            raise NotFoundError(
                f"latent exposure frame not found: {exposure_frame_id}"
            )
        payload = artifact_payload(frame_record)
        raw_rows = payload.get("rows", [])
        if not isinstance(raw_rows, list):
            raise ValidationError("latent exposure frame artifact rows must be a list")
        materialized_rows = cast(list[object], raw_rows)
        value_column = factor_spec.value_column or "factor_value"
        factor_rows: list[dict[str, object]] = []
        spec_source_refs = list(
            dict.fromkeys([*source_refs, *factor_spec.source_refs])
        )
        for index, raw_row in enumerate(materialized_rows):
            if not isinstance(raw_row, Mapping):
                continue
            row = cast(Mapping[str, object], raw_row)
            if value_column not in row:
                raise ValidationError(
                    "materialized factor row is missing value_column",
                    details={"row_index": index, "value_column": value_column},
                )
            row_source_refs = [
                str(item)
                for item in cast(list[object], row.get("source_refs", []))
                if str(item)
            ] if isinstance(row.get("source_refs"), list) else []
            lineage = {
                "factor_value": (
                    f"latent_factor_exposure_frame:{exposure_frame_id}."
                    f"rows[{index}].{value_column}"
                )
            }
            lineage.update(factor_spec.input_field_lineage)
            factor_rows.append(
                {
                    "symbol": str(row.get("symbol") or row.get("asset_id") or ""),
                    "timestamp": str(row["timestamp"]),
                    "asof_date": str(row.get("asof_date") or row.get("as_of_date")),
                    "available_at": str(row["available_at"]),
                    "factor_value": _float_from_object(row[value_column]),
                    "factor_name": factor_name,
                    "factor_spec_version": factor_spec_version,
                    "source_refs": list(
                        dict.fromkeys([*spec_source_refs, *row_source_refs])
                    ),
                    "input_field_lineage": lineage,
                    "materialized_frame_ref": materialized_ref,
                    "latent_factor_id": str(row.get("latent_factor_id", "")),
                    "latent_factor_version": str(
                        row.get("latent_factor_version", "")
                    ),
                    "exposure_frame_id": exposure_frame_id,
                    "confidence": row.get("confidence", 0.0),
                    "membership_role": str(row.get("membership_role", "")),
                }
            )
        if not factor_rows:
            raise ValidationError("latent exposure frame contains no factor rows")
        return factor_rows

    @staticmethod
    def _quantile_labels(values: list[float], bucket_count: int) -> list[int]:
        if not values:
            return []
        if len(values) == 1:
            return [1]
        ordered = sorted(range(len(values)), key=lambda index: values[index])
        labels = [1] * len(values)
        max_bucket = max(bucket_count, 1)
        for rank, index in enumerate(ordered):
            labels[index] = 1 + ((rank * (max_bucket - 1)) // (len(values) - 1))
        return labels

    @classmethod
    def _build_observations(
        cls,
        factor_rows: Sequence[Mapping[str, object]],
        label_rows: Sequence[Mapping[str, object]],
        bucket_count: int,
    ) -> list[EvaluationObservation]:
        label_map = {
            (str(row["symbol"]), str(row["timestamp"])): _float_from_object(
                row["label_value"]
            )
            for row in label_rows
        }
        by_timestamp: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in factor_rows:
            key = (str(row["symbol"]), str(row["timestamp"]))
            if key in label_map:
                by_timestamp[str(row["timestamp"])].append(dict(row))

        observations: list[EvaluationObservation] = []
        for timestamp, timestamp_rows in sorted(by_timestamp.items()):
            labels = [
                label_map[(str(row["symbol"]), timestamp)] for row in timestamp_rows
            ]
            factor_values = [
                _float_from_object(row["factor_value"]) for row in timestamp_rows
            ]
            quantile_labels = cls._quantile_labels(factor_values, bucket_count)
            for row, label_value, quantile in zip(
                timestamp_rows, labels, quantile_labels, strict=False
            ):
                observations.append(
                    EvaluationObservation(
                        symbol=str(row["symbol"]),
                        timestamp=timestamp,
                        factor_value=_float_from_object(row["factor_value"]),
                        forward_return=label_value,
                        quantile=quantile,
                    )
                )
        return observations

    @staticmethod
    def _bucket_count(protocol_groups: list[str]) -> int:
        for group in protocol_groups:
            if group.startswith("quantile_"):
                return int(group.split("_", maxsplit=1)[1])
        return 5

    @staticmethod
    def _leakage_report(
        run_id: str, factor_rows: list[dict[str, object]]
    ) -> dict[str, object]:
        violations = [
            {
                "symbol": row["symbol"],
                "timestamp": row["timestamp"],
                "available_at": row.get("available_at", ""),
                "decision_time": row.get("decision_time", ""),
            }
            for row in factor_rows
            if _row_violates_availability(row)
        ]
        return {
            "run_id": run_id,
            "checked_rules": [
                "available_at_required",
                "decision_time_required",
                "available_at_not_after_decision_time",
            ],
            "violations": violations,
            "blocked": bool(violations),
            "override_required": bool(violations),
        }

    @staticmethod
    def _temporal_profile_rows(
        factor_rows: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        profile_rows: list[dict[str, object]] = []
        for row in factor_rows:
            profile_row = dict(row)
            if not profile_row.get("asset_id") and profile_row.get("symbol"):
                profile_row["asset_id"] = str(profile_row["symbol"])
            timestamp = _profile_timestamp(profile_row)
            if timestamp:
                profile_row["timestamp"] = timestamp
            profile_rows.append(profile_row)
        return profile_rows

    @staticmethod
    def _temporal_routing_metadata(
        profile: Mapping[str, object],
    ) -> dict[str, object]:
        raw_decision = profile.get("routing_decision", {})
        routing_decision = (
            dict(cast(Mapping[str, object], raw_decision))
            if isinstance(raw_decision, Mapping)
            else {}
        )
        return {
            "factor_temporal_profile_id": str(profile.get("profile_id", "")),
            "factor_temporal_class": str(profile.get("temporal_class", "")),
            "temporal_routing_decision": routing_decision,
            "temporal_routing_policy": str(
                routing_decision.get("policy") or TEMPORAL_ROUTING_POLICY
            ),
        }

    @staticmethod
    def _recommended_temporal_research_surfaces(
        *,
        dataset_version: str,
        factor_spec_version: str,
    ) -> dict[str, JsonValue]:
        return {
            "profile": {
                "cli": (
                    "factor-lab factor-dynamics profile "
                    f"--dataset-version {dataset_version} "
                    f"--factor-ref {factor_spec_version} "
                    "--value-column factor_value --json"
                ),
                "api": "POST /api/v1/factor_temporal_profiles:evaluate",
            },
            "cohort_index": {
                "cli": (
                    "factor-lab factor-dynamics indexes create "
                    "--name <descriptor_cohort_name> "
                    f"--descriptor-ref {factor_spec_version} "
                    f"--membership-dataset-version {dataset_version} "
                    "--membership-value-column factor_value "
                    "--cohort-value <bucket_or_descriptor_value> --json"
                ),
                "api": "POST /api/v1/cohort_indexes",
            },
            "rotation": {
                "cli": (
                    "factor-lab factor-dynamics rotation analyze "
                    "--source-return-frame-id <source_frame> "
                    "--target-return-frame-id <target_frame> --json"
                ),
                "api": "POST /api/v1/factor_rotation:analyze",
            },
            "conditional_evaluation": {
                "cli": (
                    "factor-lab factor-dynamics conditional evaluate "
                    f"{factor_spec_version} "
                    "--signal-dataset-version <dynamic_signal_rows> "
                    f"--descriptor-dataset-version {dataset_version} "
                    "--label-dataset-version <forward_label_rows> "
                    "--descriptor-value-column factor_value --json"
                ),
                "api": "POST /api/v1/factors/{factor_id}:conditional_evaluate",
            },
        }

    @classmethod
    def _temporal_gate_details(
        cls,
        *,
        dataset_version: str,
        factor_spec_version: str,
        profile: Mapping[str, object],
    ) -> dict[str, JsonValue]:
        raw_decision = profile.get("routing_decision", {})
        routing_decision = (
            dict(cast(Mapping[str, object], raw_decision))
            if isinstance(raw_decision, Mapping)
            else {}
        )
        raw_recommended = routing_decision.get("recommended_uses", [])
        recommended_uses: list[JsonValue] = (
            [str(item) for item in raw_recommended]
            if isinstance(raw_recommended, Sequence)
            and not isinstance(raw_recommended, str | bytes)
            else []
        )
        blocked_reason = str(
            routing_decision.get("blocked_reason")
            or "E_STATIC_OR_SLOW_FACTOR_DIRECT_REGRESSION_BLOCKED"
        )
        return {
            "factor_spec_version": factor_spec_version,
            "dataset_version": dataset_version,
            "profile_id": str(profile.get("profile_id", "")),
            "temporal_class": str(profile.get("temporal_class", "")),
            "blocked_reason": blocked_reason,
            "recommended_uses": recommended_uses,
            "temporal_routing_policy": str(
                routing_decision.get("policy") or TEMPORAL_ROUTING_POLICY
            ),
            "deterministic_research_surfaces": (
                cls._recommended_temporal_research_surfaces(
                    dataset_version=dataset_version,
                    factor_spec_version=factor_spec_version,
                )
            ),
        }

    @classmethod
    def _raise_if_temporal_direct_regression_blocked(
        cls,
        *,
        dataset_version: str,
        factor_spec_version: str,
        profile: Mapping[str, object],
    ) -> None:
        raw_decision = profile.get("routing_decision", {})
        routing_decision = (
            dict(cast(Mapping[str, object], raw_decision))
            if isinstance(raw_decision, Mapping)
            else {}
        )
        if bool(routing_decision.get("direct_regression_allowed")):
            return
        temporal_class = str(profile.get("temporal_class", ""))
        raise GateBlockedError(
            (
                "Static or slow-moving descriptor factors are blocked from direct "
                "factor-return regression; use factor-dynamics profile, cohort "
                "index, rotation, or conditional evaluation workflows instead."
            ),
            gate_name=TEMPORAL_ROUTING_GATE_NAME,
            details=cls._temporal_gate_details(
                dataset_version=dataset_version,
                factor_spec_version=factor_spec_version,
                profile=profile,
            )
            | {"temporal_class": temporal_class},
        )

    def preflight_temporal_direct_regression(
        self,
        *,
        dataset_version: str,
        factor_spec_version: str,
        principal_id: str,
        source_family: str | None = None,
    ) -> dict[str, object]:
        """Return temporal routing metadata before creating validation state."""

        request_source_family = optional_source_family(
            source_family, context="factor_evaluation.request"
        )
        price_rows = self._load_price_rows(dataset_version)
        dataset_source_family = source_family_for_dataset_version(dataset_version)
        factor_spec = spec_registry.get_factor_spec_sync(factor_spec_version)
        factor_spec_source_family = (
            factor_spec.source_family if factor_spec is not None else None
        )
        _ = assert_consistent_source_family(
            ("request.source_family", request_source_family),
            ("dataset_manifest.source_family", dataset_source_family),
            ("factor_spec.source_family", factor_spec_source_family),
            context="factor_evaluation.temporal_preflight",
        )
        raw_factor_rows = self._build_factor_rows(
            price_rows,
            factor_spec_version,
            self._resolve_factor_name(factor_spec_version),
            source_refs_for_dataset_version(dataset_version),
            factor_spec,
        )
        temporal_profile = self._evaluate_temporal_routing_profile(
            raw_factor_rows=raw_factor_rows,
            dataset_version=dataset_version,
            factor_spec_version=factor_spec_version,
            factor_spec=factor_spec,
            principal_id=principal_id,
        )
        self._raise_if_temporal_direct_regression_blocked(
            dataset_version=dataset_version,
            factor_spec_version=factor_spec_version,
            profile=temporal_profile,
        )
        return temporal_profile

    @classmethod
    def _evaluate_temporal_routing_profile(
        cls,
        *,
        raw_factor_rows: Sequence[Mapping[str, object]],
        dataset_version: str,
        factor_spec_version: str,
        factor_spec: FactorSpec | None,
        principal_id: str,
    ) -> dict[str, object]:
        from factor_lab.factor_dynamics.services import factor_temporal_dynamics_service

        is_materialized_frame = (
            factor_spec is not None
            and factor_spec.factor_type == "materialized_frame"
        )
        slow_change_threshold = (
            0.25 if is_materialized_frame else 0.05
        )
        return factor_temporal_dynamics_service.evaluate_profile(
            rows=cls._temporal_profile_rows(raw_factor_rows),
            dataset_version=dataset_version,
            factor_ref=factor_spec_version,
            value_column="factor_value",
            slow_change_threshold=slow_change_threshold,
            generated_by=f"factor_evaluation:{principal_id}",
        )

    async def submit_evaluation(
        self,
        dataset_version: str,
        factor_spec_version: str,
        preprocess_spec_version: str,
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
    ) -> dict[str, str]:
        """Submit a factor evaluation request."""
        policy_pack = validate_policy_pack(policy_pack)
        request_source_family = optional_source_family(
            source_family, context="factor_evaluation.request"
        )
        protocol_config = self._load_protocol_config(protocol_version)
        engine = EvaluationEngine(protocol_config)
        label_builder, label_name = self._load_label_builder(label_spec_version)
        factor_name = self._resolve_factor_name(factor_spec_version)
        price_rows = self._load_price_rows(dataset_version)
        dataset_source_family = source_family_for_dataset_version(dataset_version)
        factor_spec = await spec_registry.get_factor_spec(factor_spec_version)
        factor_spec_source_family = (
            factor_spec.source_family if factor_spec is not None else None
        )
        resolved_source_family = assert_consistent_source_family(
            ("request.source_family", request_source_family),
            ("dataset_manifest.source_family", dataset_source_family),
            ("factor_spec.source_family", factor_spec_source_family),
            context="factor_evaluation",
        )
        source_refs = source_refs_for_dataset_version(dataset_version)
        raw_factor_rows = self._build_factor_rows(
            price_rows,
            factor_spec_version,
            factor_name,
            source_refs,
            factor_spec,
        )
        temporal_profile = self._evaluate_temporal_routing_profile(
            raw_factor_rows=raw_factor_rows,
            dataset_version=dataset_version,
            factor_spec_version=factor_spec_version,
            factor_spec=factor_spec,
            principal_id=principal_id,
        )
        self._raise_if_temporal_direct_regression_blocked(
            dataset_version=dataset_version,
            factor_spec_version=factor_spec_version,
            profile=temporal_profile,
        )
        temporal_routing_metadata = self._temporal_routing_metadata(temporal_profile)
        run_id = str(uuid.uuid4())
        run = EvaluationRunRecord(
            run_id=run_id,
            run_type="factor_evaluation",
            status=RunStatus.PENDING,
            dataset_version=dataset_version,
            factor_spec_version=factor_spec_version,
            preprocess_spec_version=preprocess_spec_version,
            label_spec_version=label_spec_version,
            protocol_version=protocol_version,
            policy_pack=policy_pack,
            code_version=code_version,
            seed=seed,
            principal_id=principal_id,
            created_at=datetime.now(UTC).isoformat(),
            source_family=resolved_source_family,
            factor_temporal_profile_id=str(
                temporal_routing_metadata["factor_temporal_profile_id"]
            ),
            factor_temporal_class=str(
                temporal_routing_metadata["factor_temporal_class"]
            ),
            temporal_routing_decision=cast(
                dict[str, object],
                temporal_routing_metadata["temporal_routing_decision"],
            ),
            temporal_routing_policy=str(
                temporal_routing_metadata["temporal_routing_policy"]
            ),
            preprocessing_config=(
                dict(preprocessing_config) if preprocessing_config is not None else None
            ),
            neutralization_config=(
                dict(neutralization_config)
                if neutralization_config is not None
                else None
            ),
            selection_context=(
                dict(selection_context) if selection_context is not None else None
            ),
        )
        self._runs[run_id] = run
        runtime_state_store.upsert("runs", run_id, run.to_dict())

        job_id = str(uuid.uuid4())
        job = EvaluationJobRecord(
            job_id=job_id,
            run_id=run_id,
            status=JobStatus.QUEUED,
            status_uri=f"/api/v1/jobs/{job_id}",
            job_type="factor_evaluation",
            created_at=datetime.now(UTC).isoformat(),
        )
        self._jobs[job_id] = job
        runtime_state_store.upsert("jobs", job_id, job.to_dict())

        _ = event_store.append(
            event_type="run.created",
            payload={"run_id": run_id, "run_type": "factor_evaluation"},
            run_id=run_id,
            job_id=job_id,
        )
        _ = event_store.append(
            event_type="job.queued",
            payload={"job_id": job_id, "run_id": run_id, "status_uri": job.status_uri},
            run_id=run_id,
            job_id=job_id,
        )

        run.status = RunStatus.RUNNING
        job.status = JobStatus.RUNNING
        runtime_state_store.upsert("runs", run_id, run.to_dict())
        runtime_state_store.upsert("jobs", job_id, job.to_dict())
        _ = event_store.append(
            event_type="job.running",
            payload={"job_id": job_id, "run_id": run_id},
            run_id=run_id,
            job_id=job_id,
        )
        _ = event_store.append(
            event_type="factor.temporal_routing_allowed",
            payload={
                "run_id": run_id,
                "profile_id": temporal_routing_metadata[
                    "factor_temporal_profile_id"
                ],
                "temporal_class": temporal_routing_metadata[
                    "factor_temporal_class"
                ],
                "policy": temporal_routing_metadata["temporal_routing_policy"],
            },
            run_id=run_id,
            job_id=job_id,
        )
        factor_rows, preprocess_summary = apply_preprocess_spec(
            raw_factor_rows,
            preprocess_spec_version=preprocess_spec_version,
            fixture_root=self._fixture_root() / "preprocess_specs",
        )
        factor_rows, validation_kernel_summary = apply_preprocess_config(
            factor_rows,
            preprocessing_config=dict(preprocessing_config or {}),
            neutralization_config=dict(neutralization_config or {}),
        )
        preprocess_summary = {
            **preprocess_summary,
            "validation_kernel": validation_kernel_summary,
        }
        label_records = label_builder.build_labels(price_rows, label_name=label_name)
        label_rows = [
            {
                "symbol": record.symbol,
                "timestamp": record.timestamp,
                "label_value": record.label_value,
                "label_name": record.label_name,
            }
            for record in label_records
        ]
        bucket_count = self._bucket_count(engine.groups)
        raw_observations = self._build_observations(
            raw_factor_rows, label_rows, bucket_count
        )
        raw_result = engine.evaluate_observations(
            raw_observations,
            total_factor_rows=len(raw_factor_rows),
        )
        observations = self._build_observations(factor_rows, label_rows, bucket_count)
        result = engine.evaluate_observations(
            observations,
            total_factor_rows=len(factor_rows),
        )
        raw_selection_context = dict(selection_context or {})
        candidate_count = _positive_int_or_none(
            raw_selection_context.get("candidate_count")
        )
        param_search_count = _positive_int_or_none(
            raw_selection_context.get("param_search_count")
        )
        protocol_variant_count = _positive_int_or_none(
            raw_selection_context.get("protocol_variant_count")
        )
        selection_top_k = _positive_int_or_none(raw_selection_context.get("top_k"))
        candidate_count_context = {
            "candidate_count": candidate_count,
            "param_search_count": param_search_count,
            "protocol_variant_count": protocol_variant_count,
            "top_k": selection_top_k,
            "source_ref": str(raw_selection_context.get("source_ref", "")),
        }
        multiple_testing_report = build_multiple_testing_report(
            candidate_count=candidate_count,
            param_search_count=param_search_count,
            protocol_variant_count=protocol_variant_count,
            top_k=selection_top_k or 1,
            best_score=result.score,
        )
        leakage_report = self._leakage_report(run_id, factor_rows)

        # These folds measure time-partition stability; they do not freeze or train
        # a candidate and therefore are not promotion-grade OOS evidence.
        oos_summary_obj = analyze_oos(observations, fold_count=3, engine=engine)
        oos_summary = {
            **oos_summary_obj.to_dict(),
            "evidence_role": "diagnostic_time_partition_stability_not_promotion_oos",
        }
        evaluation_years = sorted(
            {
                int(str(row.get("timestamp", ""))[:4])
                for row in factor_rows
                if str(row.get("timestamp", ""))[:4].isdigit()
            }
        )
        temporal_evaluation_contract: dict[str, object] = {
            "policy_id": CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY.policy_id,
            "stage": "diagnostic",
            "evaluation_mode": "time_partition_stability",
            "train_years": [],
            "test_years": evaluation_years,
            "lockbox_years": [],
            "lockbox_status": "untouched",
            "candidate_frozen": False,
            "formula_or_parameter_selected_on_test_rows": False,
            "test_rows_previously_consumed_by_search": False,
            "evaluation_reuse_count": 1,
            "selection_freeze_date": "",
            "test_start_date": "",
            "preprocessing_fit_scope": "full_sample_diagnostic",
            "feature_availability_status": (
                "passed" if not leakage_report["blocked"] else "blocked"
            ),
            "label_separation_status": "passed",
            "universe_pit_status": "unknown_diagnostic",
            "multiple_testing_status": "diagnostic_only",
            "production_claim": "forbidden",
        }
        temporal_integrity_report = validate_temporal_evaluation_contract(
            temporal_evaluation_contract
        )

        # Enhancement: Risk Exposure Analysis
        risk_exposure_obj = analyze_risk_exposure(factor_rows)
        risk_exposure_summary = risk_exposure_obj.to_dict()

        governance_notes = [
            "multiple_testing_hint=true",
            f"governance_verdict={multiple_testing_report['governance_verdict']}",
            f"risk_exposure_verdict={risk_exposure_obj.governance_verdict}",
            (
                "factor_temporal_profile_id="
                f"{temporal_routing_metadata['factor_temporal_profile_id']}"
            ),
            (
                "factor_temporal_class="
                f"{temporal_routing_metadata['factor_temporal_class']}"
            ),
            (
                "temporal_routing_policy="
                f"{temporal_routing_metadata['temporal_routing_policy']}"
            ),
            "temporal_direct_regression_allowed=true",
        ]

        artifact_generated_at = datetime.now(UTC).isoformat()
        run_snapshot = RunSnapshot(
            run_id=run_id,
            dataset_version=dataset_version,
            factor_spec_version=factor_spec_version,
            preprocess_spec_version=preprocess_spec_version,
            label_spec_version=label_spec_version,
            protocol_version=protocol_version,
            code_version=code_version,
            env_fingerprint="local-test-env",
            seed=seed,
            source_family=resolved_source_family,
        )

        preprocess_artifact = self._materialize_artifact(
            run_id,
            "preprocess_report",
            {
                "run_id": run_id,
                "factor_spec_version": factor_spec_version,
                "source_family": resolved_source_family,
                "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
                **preprocess_summary,
            },
        )
        _ = event_store.append(
            event_type="evaluation.preprocess_completed",
            payload={"artifact_id": preprocess_artifact.artifact_id},
            run_id=run_id,
            job_id=job_id,
        )
        factor_frame_artifact = self._materialize_artifact(
            run_id,
            "factor_frame",
            {
                "run_id": run_id,
                "factor_spec_version": factor_spec_version,
                "preprocess_spec_version": preprocess_spec_version,
                "source_family": resolved_source_family,
                "source_refs": source_refs,
                "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
                **temporal_routing_metadata,
                "schema_version": "1.0",
                "generated_at": artifact_generated_at,
                "preprocess_summary": preprocess_summary,
                "data": factor_rows,
                "row_count": len(factor_rows),
            },
        )
        _ = event_store.append(
            event_type="factor.factor_frame_published",
            payload={"artifact_id": factor_frame_artifact.artifact_id},
            run_id=run_id,
            job_id=job_id,
        )
        label_frame_artifact = self._materialize_artifact(
            run_id,
            "label_frame",
            {
                "run_id": run_id,
                "label_spec_version": label_spec_version,
                "source_family": resolved_source_family,
                "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
                "schema_version": "1.0",
                "generated_at": artifact_generated_at,
                "data": label_rows,
                "row_count": len(label_rows),
            },
        )
        _ = event_store.append(
            event_type="evaluation.label_frame_published",
            payload={"artifact_id": label_frame_artifact.artifact_id},
            run_id=run_id,
            job_id=job_id,
        )
        raw_metrics_table = self._report_generator.generate_metrics_table(raw_result)
        neutralized_metrics_table = self._report_generator.generate_metrics_table(
            result
        )
        metrics_payload = neutralized_metrics_table | {
            "source_family": resolved_source_family,
            "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
            **temporal_routing_metadata,
            "raw_metrics": raw_result.to_dict(),
            "neutralized_metrics": result.to_dict(),
            "preprocessing_config": dict(preprocessing_config or {}),
            "neutralization_config": dict(neutralization_config or {}),
            "multiple_testing_governance": multiple_testing_report,
            "risk_exposure_governance": {
                "governance_verdict": risk_exposure_obj.governance_verdict,
                "warning_flags": risk_exposure_obj.warning_flags,
                "enhancement_type": risk_exposure_obj.enhancement_type,
            },
        }
        metrics_artifact = self._materialize_artifact(
            run_id,
            "eval_metrics_table",
            metrics_payload,
        )
        _ = event_store.append(
            event_type="evaluation.metrics_computed",
            payload={"artifact_id": metrics_artifact.artifact_id},
            run_id=run_id,
            job_id=job_id,
        )
        _ = self._materialize_artifact(
            run_id,
            "validation_kernel_report",
            {
                "run_id": run_id,
                "factor_spec_version": factor_spec_version,
                "source_family": resolved_source_family,
                "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
                **temporal_routing_metadata,
                "raw_metrics_table": raw_metrics_table,
                "neutralized_metrics_table": neutralized_metrics_table,
                "raw_metrics": raw_result.to_dict(),
                "neutralized_metrics": result.to_dict(),
                "preprocessing_config": dict(preprocessing_config or {}),
                "neutralization_config": dict(neutralization_config or {}),
                "validation_blocked": bool(leakage_report["blocked"]),
                "leakage_check": leakage_report,
                "multiple_testing_governance": multiple_testing_report,
                "temporal_evaluation_contract": temporal_evaluation_contract,
                "temporal_integrity_report": temporal_integrity_report,
                "oos_summary": oos_summary,
                "risk_exposure_summary": risk_exposure_summary,
            },
        )
        _ = self._materialize_artifact(
            run_id,
            "oos_statistics_report",
            oos_summary,
        )
        _ = self._materialize_artifact(
            run_id,
            "risk_exposure_report",
            {
                "run_id": run_id,
                "factor_spec_version": factor_spec_version,
                "source_family": resolved_source_family,
                "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
                **risk_exposure_summary,
            },
        )
        report_artifact = self._materialize_artifact(
            run_id,
            "eval_report",
            self._report_generator.generate_report_payload(
                result=result,
                run_id=run_id,
                factor_name=factor_name,
                protocol_version=protocol_version,
                dataset_version=dataset_version,
                label_spec_version=label_spec_version,
                preprocess_spec_version=preprocess_spec_version,
                candidate_count_context=candidate_count_context,
                governance_notes=governance_notes,
                oos_summary=oos_summary,
            ) | {
                "source_family": resolved_source_family,
                "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
                **temporal_routing_metadata,
                "raw_metric_summary": raw_result.to_dict(),
                "neutralized_metric_summary": result.to_dict(),
                "preprocessing_config": dict(preprocessing_config or {}),
                "neutralization_config": dict(neutralization_config or {}),
                "risk_exposure_summary": risk_exposure_summary,
                "temporal_integrity_report": temporal_integrity_report,
            },
        )
        _ = event_store.append(
            event_type="evaluation.report_published",
            payload={"artifact_id": report_artifact.artifact_id},
            run_id=run_id,
            job_id=job_id,
        )
        _ = event_store.append(
            event_type="governance.multiple_testing_hint_emitted",
            payload={
                "run_id": run_id,
                "candidate_count_context": candidate_count_context,
            },
            run_id=run_id,
            job_id=job_id,
        )
        _ = event_store.append(
            event_type="governance.risk_exposure_hint_emitted",
            payload={
                "run_id": run_id,
                "governance_verdict": risk_exposure_obj.governance_verdict,
                "warning_flags": risk_exposure_obj.warning_flags,
            },
            run_id=run_id,
            job_id=job_id,
        )
        _ = self._materialize_artifact(
            run_id,
            "leakage_check_report",
            {
                **leakage_report,
                "source_family": resolved_source_family,
                "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
            },
        )

        snapshot_payload: dict[str, object] = {
            **run_snapshot.to_dict(),
            "generated_at": artifact_generated_at,
            "protocol_groups": engine.groups,
            "protocol_metrics": engine.metrics,
            "result_summary": {
                "score": result.score,
                "coverage_ratio": result.coverage_ratio,
                "observation_count": result.observation_count,
                "period_count": result.period_count,
            },
            "preprocess_summary": preprocess_summary,
            "preprocessing_config": dict(preprocessing_config or {}),
            "neutralization_config": dict(neutralization_config or {}),
            "oos_summary": {
                "fold_count": oos_summary_obj.fold_count,
                "positive_ic_ratio": oos_summary_obj.positive_ic_period_ratio,
                "mean_oos_ic": oos_summary_obj.mean_oos_ic,
                "insufficient_sample": oos_summary_obj.insufficient_sample,
            },
            "risk_exposure_summary": {
                "governance_verdict": risk_exposure_obj.governance_verdict,
                "warning_flags": risk_exposure_obj.warning_flags,
                "industry_concentration_hhi": (
                    risk_exposure_obj.industry_concentration_hhi
                ),
                "size_exposure_status": risk_exposure_obj.size_exposure_status,
                "residualization_status": (
                    risk_exposure_obj.residualization_status
                ),
            },
            "raw_result_summary": {
                "score": raw_result.score,
                "rank_ic_mean": raw_result.rank_ic_mean,
                "ic_mean": raw_result.ic_mean,
            },
            "source_family": resolved_source_family,
            "source_universe_gate_status": SourceUniverseGateStatus.PASSED.value,
            **temporal_routing_metadata,
            "snapshot_version": "1.0",
        }
        _ = self._materialize_artifact(
            run_id,
            "run_record_snapshot",
            snapshot_payload,
        )

        run.status = RunStatus.COMPLETED
        job.status = JobStatus.SUCCEEDED
        runtime_state_store.upsert("runs", run_id, run.to_dict())
        runtime_state_store.upsert("jobs", job_id, job.to_dict())
        _ = event_store.append(
            event_type="job.succeeded",
            payload={"job_id": job_id, "run_id": run_id},
            run_id=run_id,
            job_id=job_id,
        )
        _ = event_store.append(
            event_type="run.completed",
            payload={"run_id": run_id, "run_type": "factor_evaluation"},
            run_id=run_id,
            job_id=job_id,
        )

        return {
            "run_id": run_id,
            "job_id": job_id,
            "status_uri": job.status_uri,
            "source_family": resolved_source_family,
        }

    async def compare_runs(
        self, run_id_a: str, run_id_b: str, principal_id: str
    ) -> dict[str, object]:
        """Compare two runs."""
        _ = principal_id
        run_a = self._runs.get(run_id_a)
        run_b = self._runs.get(run_id_b)

        if run_a is None:
            state_run_a = runtime_state_store.load()["runs"].get(run_id_a)
            if state_run_a is not None:
                run_a = EvaluationRunRecord(
                    run_id=str(state_run_a["run_id"]),
                    run_type=str(state_run_a["run_type"]),
                    status=str(state_run_a["status"]),
                    dataset_version=str(state_run_a["dataset_version"]),
                    factor_spec_version=str(state_run_a["factor_spec_version"]),
                    preprocess_spec_version=str(
                        state_run_a.get("preprocess_spec_version", "")
                    ),
                    label_spec_version=str(state_run_a["label_spec_version"]),
                    protocol_version=str(state_run_a["protocol_version"]),
                    policy_pack=str(state_run_a["policy_pack"]),
                    code_version=str(state_run_a["code_version"]),
                    seed=_int_from_object(state_run_a["seed"]),
                    principal_id=str(state_run_a["principal_id"]),
                    created_at=str(state_run_a["created_at"]),
                    source_family=str(state_run_a.get("source_family", "")),
                    selection_context=(
                        dict(cast(Mapping[str, object], raw_selection))
                        if isinstance(
                            (raw_selection := state_run_a.get("selection_context")),
                            Mapping,
                        )
                        else None
                    ),
                    code_dirty=bool(state_run_a.get("code_dirty", False)),
                )

        if run_b is None:
            state_run_b = runtime_state_store.load()["runs"].get(run_id_b)
            if state_run_b is not None:
                run_b = EvaluationRunRecord(
                    run_id=str(state_run_b["run_id"]),
                    run_type=str(state_run_b["run_type"]),
                    status=str(state_run_b["status"]),
                    dataset_version=str(state_run_b["dataset_version"]),
                    factor_spec_version=str(state_run_b["factor_spec_version"]),
                    preprocess_spec_version=str(
                        state_run_b.get("preprocess_spec_version", "")
                    ),
                    label_spec_version=str(state_run_b["label_spec_version"]),
                    protocol_version=str(state_run_b["protocol_version"]),
                    policy_pack=str(state_run_b["policy_pack"]),
                    code_version=str(state_run_b["code_version"]),
                    seed=_int_from_object(state_run_b["seed"]),
                    principal_id=str(state_run_b["principal_id"]),
                    created_at=str(state_run_b["created_at"]),
                    source_family=str(state_run_b.get("source_family", "")),
                    selection_context=(
                        dict(cast(Mapping[str, object], raw_selection))
                        if isinstance(
                            (raw_selection := state_run_b.get("selection_context")),
                            Mapping,
                        )
                        else None
                    ),
                    code_dirty=bool(state_run_b.get("code_dirty", False)),
                )

        if not run_a or not run_b:
            return {"comparable": False, "reason": "One or both runs not found"}

        if run_a.protocol_version != run_b.protocol_version:
            return {
                "comparable": False,
                "reason": "Different protocol versions",
                "run_a_protocol": run_a.protocol_version,
                "run_b_protocol": run_b.protocol_version,
            }

        if run_a.code_dirty or run_b.code_dirty:
            return {"comparable": False, "reason": "One or both runs have dirty code"}

        return {
            "comparable": True,
            "run_a": {"run_id": run_id_a, "factor_spec": run_a.factor_spec_version},
            "run_b": {"run_id": run_id_b, "factor_spec": run_b.factor_spec_version},
        }

    def reset(self) -> None:
        self._runs.clear()
        self._jobs.clear()
        self._artifacts.clear()

    async def get_job(self, job_id: str) -> dict[str, str] | None:
        job = self._jobs.get(job_id)
        if job is not None:
            return job.to_dict()
        state_job = runtime_state_store.load()["jobs"].get(job_id)
        if state_job is None:
            return None
        return {key: str(value) for key, value in state_job.items()}

    async def get_run(self, run_id: str) -> dict[str, object] | None:
        run = self._runs.get(run_id)
        if run is not None:
            return run.to_dict()
        return runtime_state_store.load()["runs"].get(run_id)

    async def list_artifacts(self, run_id: str) -> list[dict[str, str]]:
        artifacts = [
            artifact.to_dict()
            for artifact in self._artifacts.values()
            if artifact.run_id == run_id
        ]
        if artifacts:
            return artifacts
        return [
            {key: str(value) for key, value in artifact.items()}
            for artifact in runtime_state_store.list_artifacts_for_run(run_id)
        ]


factor_evaluation_service = FactorEvaluationService()
