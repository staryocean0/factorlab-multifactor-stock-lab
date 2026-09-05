# pyright: reportAny=false, reportArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportMissingTypeStubs=false, reportOperatorIssue=false
# pyright: reportReturnType=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownParameterType=false
# pyright: reportUnknownVariableType=false, reportUnnecessaryIsInstance=false

"""Fail-closed DataHub adapter for the schedule-bound Alpha158 price parent.

The upstream product is deliberately narrower than a generic adjusted-bars
authority.  It is granted only for the pinned 2013--2020 Alpha158 research
surface, only when ``vwap_valid`` is true, and only under the strict
``available_at < decision_at`` predicate.  This adapter preserves those
limits and returns at most sixty prior observations per symbol as formula
context; it does not copy the lake into FactorLab or broaden the grant.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

from factor_lab.factor_rotation.reaka_alpha158 import ALPHA158_MAX_LOOKBACK_BARS
from factor_lab.governance.canonicalization import canonical_digest

ALPHA158_PRICE_PARENT_SCHEMA_ID: Final[str] = "reaka_alpha158_schedule_bound_price_parent@1.0"
REQUIRED_DATASET_KIND: Final[str] = "alpha158_adjusted_daily_bars_schedule_bound"
REQUIRED_CONTRACT_ID: Final[str] = "factorlab_alpha158_cn_a_adjusted_vwap_2013_2020_schedule_bound.v1"
REQUIRED_CAPABILITY_SCOPE: Final[str] = "schedule_bound_alpha158_adjusted_price_and_vwap_rows_where_vwap_valid_true"
REQUIRED_PRICE_SPACE: Final[str] = "causal_relative_adjusted_anchor_first_observation"
REQUIRED_PIT_MODE: Final[str] = "PIT_SAFE_SCHEDULE_BOUND_HISTORY"
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "symbol",
    "trading_day",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "vwap_valid",
    "available_at",
    "pit_availability_mode",
    "price_space",
    "dataset_version",
)
OUTPUT_COLUMNS: Final[tuple[str, ...]] = (
    "symbol",
    "trading_day",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
)


@dataclass(frozen=True, slots=True)
class GrantedAlpha158PriceWindow:
    """One visible output window plus bounded raw left context."""

    current_rows: pd.DataFrame
    history_rows: pd.DataFrame
    receipt: dict[str, object]


def load_granted_alpha158_price_window(
    *,
    artifact_dir: Path,
    consumer_contract_path: Path,
    output_start: str | pd.Timestamp,
    output_end: str | pd.Timestamp,
    decision_at: str | pd.Timestamp,
    symbols: tuple[str, ...] | list[str] | None = None,
    left_context_rows: int = ALPHA158_MAX_LOOKBACK_BARS,
) -> GrantedAlpha158PriceWindow:
    """Validate the immutable grant and predicate-read one Alpha158 window."""

    if not isinstance(left_context_rows, int) or isinstance(left_context_rows, bool):
        raise ValueError("reaka_alpha158_price_parent_left_context_invalid")
    if left_context_rows < 0 or left_context_rows > ALPHA158_MAX_LOOKBACK_BARS:
        raise ValueError("reaka_alpha158_price_parent_left_context_invalid")

    artifact_dir = artifact_dir.expanduser().resolve()
    manifest = _read_json(artifact_dir / "manifest.json")
    certification = _read_json(artifact_dir / "certification_report.json")
    contract = _read_json(consumer_contract_path.expanduser().resolve())
    dataset_version = _validate_authority(
        manifest=manifest,
        certification=certification,
        contract=contract,
    )
    observations_meta = _mapping(manifest, "observations")
    observations_path = artifact_dir / _text(observations_meta, "path")
    observations_sha256 = _sha256_file(observations_path)
    if observations_sha256 != _text(observations_meta, "sha256"):
        raise ValueError("reaka_alpha158_price_parent_observations_hash_mismatch")
    _validate_report_hashes(artifact_dir=artifact_dir, manifest=manifest)

    start = _normal_day(output_start)
    end = _normal_day(output_end)
    cutoff = _decision_instant(decision_at)
    if start > end:
        raise ValueError("reaka_alpha158_price_parent_window_invalid")
    scope = _mapping(contract, "scope")
    scope_start = _normal_day(_text(scope, "coverage_start"))
    scope_end = _normal_day(_text(scope, "coverage_end"))
    if start < scope_start or end > scope_end:
        raise ValueError("reaka_alpha158_price_parent_window_outside_contract")
    if cutoff <= _decision_instant(end):
        raise ValueError("reaka_alpha158_price_parent_decision_not_after_output")

    requested_symbols = _normalize_symbols(symbols)
    dataset = ds.dataset(str(observations_path), format="parquet")
    missing = set(REQUIRED_COLUMNS).difference(dataset.schema.names)
    if missing:
        raise ValueError("reaka_alpha158_price_parent_columns_missing:" + ",".join(sorted(missing)))
    trading_end = _arrow_filter_value(dataset.schema.field("trading_day").type, end)
    available_cutoff = _arrow_filter_value(
        dataset.schema.field("available_at").type,
        cutoff,
    )
    predicate = (
        (ds.field("trading_day") <= trading_end) & (ds.field("available_at") < available_cutoff) & (ds.field("vwap_valid") == True)  # noqa: E712 - Arrow expression API
    )
    if requested_symbols:
        predicate &= ds.field("symbol").isin(requested_symbols)
    table = dataset.to_table(columns=list(REQUIRED_COLUMNS), filter=predicate)
    visible = _normalize_rows(table.to_pandas(), expected_dataset_version=dataset_version)
    if requested_symbols and not set(visible["symbol"]).issubset(requested_symbols):
        raise ValueError("reaka_alpha158_price_parent_symbol_predicate_failed")

    current = visible.loc[visible["trading_day"].between(start, end, inclusive="both")].copy()
    if current.empty:
        raise ValueError("reaka_alpha158_price_parent_current_rows_empty")
    current_symbols = set(current["symbol"])
    history = visible.loc[visible["symbol"].isin(current_symbols) & visible["trading_day"].lt(start)].copy()
    if left_context_rows == 0:
        history = history.iloc[0:0].copy()
    else:
        history = history.groupby("symbol", sort=False, group_keys=False).tail(left_context_rows).copy()
    current = current.loc[:, OUTPUT_COLUMNS].reset_index(drop=True)
    history = history.loc[:, OUTPUT_COLUMNS].reset_index(drop=True)
    if len(history) > len(current_symbols) * left_context_rows:
        raise AssertionError("reaka_alpha158_price_parent_context_bound_failed")

    receipt: dict[str, object] = {
        "schema_id": ALPHA158_PRICE_PARENT_SCHEMA_ID,
        "dataset_kind": REQUIRED_DATASET_KIND,
        "dataset_version": dataset_version,
        "consumer_contract_id": REQUIRED_CONTRACT_ID,
        "observations_sha256": observations_sha256,
        "output_start": str(start.date()),
        "output_end": str(end.date()),
        "decision_at": cutoff.isoformat(),
        "predicate": "trading_day<=output_end AND available_at<decision_at AND vwap_valid=true",
        "requested_symbol_count": len(requested_symbols) if requested_symbols else None,
        "current_symbol_count": int(current["symbol"].nunique()),
        "current_row_count": len(current),
        "history_row_count": len(history),
        "left_context_rows_per_symbol_max": left_context_rows,
        "maximum_loaded_trading_day": str(current["trading_day"].max().date()),
        "rows_where_vwap_valid_false_used": 0,
        "post_2020_rows_used": 0,
        "datahub_certification_is_authoritative": True,
        "factorlab_source_document_reverification_performed": False,
        "factorlab_consumer_validation_scope": ("product_identity_contract_binding_hash_integrity_and_row_compatibility"),
        "latest_alias_used": False,
        "copied_or_migrated_lake_data": False,
        "price_parent_only": True,
        "receipt_exact_pit_claimed": False,
        "total_return_authority": False,
        "production_authority": False,
        "current_coordinate_digest": canonical_digest(current.loc[:, ["symbol", "trading_day"]].astype(str).to_dict("records")),
        "history_coordinate_digest": canonical_digest(history.loc[:, ["symbol", "trading_day"]].astype(str).to_dict("records")),
    }
    receipt["canonical_digest"] = canonical_digest(receipt)
    return GrantedAlpha158PriceWindow(
        current_rows=current,
        history_rows=history,
        receipt=receipt,
    )


def _validate_authority(
    *,
    manifest: dict[str, object],
    certification: dict[str, object],
    contract: dict[str, object],
) -> str:
    if manifest.get("dataset_kind") != REQUIRED_DATASET_KIND:
        raise ValueError("reaka_alpha158_price_parent_dataset_kind_mismatch")
    dataset_version = _text(manifest, "dataset_version")
    if manifest.get("immutable") is not True or manifest.get("latest_alias_allowed") is not False:
        raise ValueError("reaka_alpha158_price_parent_immutability_missing")
    if manifest.get("price_space") != REQUIRED_PRICE_SPACE:
        raise ValueError("reaka_alpha158_price_parent_price_space_mismatch")
    if manifest.get("consumer_contract_id") != REQUIRED_CONTRACT_ID:
        raise ValueError("reaka_alpha158_price_parent_manifest_contract_mismatch")
    if contract.get("consumer_contract_id") != REQUIRED_CONTRACT_ID:
        raise ValueError("reaka_alpha158_price_parent_contract_identity_mismatch")
    binding = _mapping(contract, "dataset_binding")
    if binding.get("dataset_kind") != REQUIRED_DATASET_KIND:
        raise ValueError("reaka_alpha158_price_parent_contract_kind_mismatch")
    if binding.get("dataset_version") != dataset_version:
        raise ValueError("reaka_alpha158_price_parent_contract_version_mismatch")
    if binding.get("latest_alias_allowed") is not False:
        raise ValueError("reaka_alpha158_price_parent_contract_latest_forbidden")
    availability = _mapping(contract, "availability")
    if availability.get("predicate") != "available_at < strategy_date":
        raise ValueError("reaka_alpha158_price_parent_contract_predicate_mismatch")
    if availability.get("mode") != REQUIRED_PIT_MODE:
        raise ValueError("reaka_alpha158_price_parent_contract_pit_mode_mismatch")
    scope = _mapping(contract, "scope")
    if scope.get("price_space") != REQUIRED_PRICE_SPACE:
        raise ValueError("reaka_alpha158_price_parent_contract_price_space_mismatch")
    if scope.get("post_2020_rows_granted") is not False:
        raise ValueError("reaka_alpha158_price_parent_contract_scope_too_broad")
    if certification.get("capability_decision") != "granted":
        raise ValueError("reaka_alpha158_price_parent_capability_not_granted")
    if certification.get("capability_scope") != REQUIRED_CAPABILITY_SCOPE:
        raise ValueError("reaka_alpha158_price_parent_capability_scope_mismatch")
    if certification.get("consumer_contract_id") != REQUIRED_CONTRACT_ID:
        raise ValueError("reaka_alpha158_price_parent_certification_contract_mismatch")
    if certification.get("dataset_version") != dataset_version:
        raise ValueError("reaka_alpha158_price_parent_certification_version_mismatch")
    required_filter = certification.get("required_consumer_filter")
    if required_filter != "vwap_valid = true AND available_at < strategy_date":
        raise ValueError("reaka_alpha158_price_parent_certification_filter_mismatch")
    return dataset_version


def _validate_report_hashes(*, artifact_dir: Path, manifest: dict[str, object]) -> None:
    reports = _mapping(manifest, "reports")
    required = {
        "certification_report",
        "coverage_report",
        "gap_ledger",
        "prefix_invariance_report",
        "quality_report",
        "replay_validation_report",
    }
    if not required.issubset(reports):
        raise ValueError("reaka_alpha158_price_parent_reports_missing")
    for report_name in sorted(required):
        report = _mapping(reports, report_name)
        path = artifact_dir / _text(report, "path")
        if _sha256_file(path) != _text(report, "sha256"):
            raise ValueError(f"reaka_alpha158_price_parent_report_hash_mismatch:{report_name}")


def _normalize_rows(frame: pd.DataFrame, *, expected_dataset_version: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    output["symbol"] = output["symbol"].astype(str).str.strip()
    if output["symbol"].eq("").any():
        raise ValueError("reaka_alpha158_price_parent_symbol_empty")
    output["trading_day"] = pd.to_datetime(output["trading_day"], errors="raise").dt.normalize()
    output["available_at"] = pd.to_datetime(output["available_at"], errors="raise", utc=True)
    if not output["vwap_valid"].eq(True).all():  # noqa: E712
        raise ValueError("reaka_alpha158_price_parent_invalid_vwap_row_loaded")
    if not output["pit_availability_mode"].eq(REQUIRED_PIT_MODE).all():
        raise ValueError("reaka_alpha158_price_parent_row_pit_mode_mismatch")
    if not output["price_space"].eq(REQUIRED_PRICE_SPACE).all():
        raise ValueError("reaka_alpha158_price_parent_row_price_space_mismatch")
    if not output["dataset_version"].eq(expected_dataset_version).all():
        raise ValueError("reaka_alpha158_price_parent_row_dataset_version_mismatch")
    trading_at = output["trading_day"].dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")
    if not output["available_at"].gt(trading_at).all():
        raise ValueError("reaka_alpha158_price_parent_same_day_availability")
    for column in ("open", "high", "low", "close", "volume", "vwap"):
        output[column] = pd.to_numeric(output[column], errors="raise")
    numeric = output.loc[:, ["open", "high", "low", "close", "volume", "vwap"]]
    if not np.isfinite(numeric.to_numpy(dtype=np.float64)).all():
        raise ValueError("reaka_alpha158_price_parent_nonfinite_granted_row")
    if output.duplicated(["symbol", "trading_day"]).any():
        raise ValueError("reaka_alpha158_price_parent_duplicate_coordinate")
    return output.sort_values(["symbol", "trading_day"], kind="mergesort").reset_index(drop=True)


def _normalize_symbols(symbols: tuple[str, ...] | list[str] | None) -> set[str]:
    if symbols is None:
        return set()
    if isinstance(symbols, (str, bytes)):
        raise ValueError("reaka_alpha158_price_parent_symbols_invalid")
    normalized = {str(symbol).strip() for symbol in symbols}
    if not normalized or "" in normalized or len(normalized) != len(symbols):
        raise ValueError("reaka_alpha158_price_parent_symbols_invalid")
    return normalized


def _normal_day(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("Asia/Shanghai").tz_localize(None)
    return timestamp.normalize()


def _decision_instant(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("Asia/Shanghai")
    return timestamp.tz_convert("Asia/Shanghai")


def _arrow_filter_value(data_type: pa.DataType, value: pd.Timestamp) -> object:
    if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return value.isoformat() if value.tzinfo is not None else value.strftime("%Y-%m-%d")
    if pa.types.is_date(data_type):
        return value.date()
    if pa.types.is_timestamp(data_type):
        timestamp = value
        if data_type.tz is None and timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        elif data_type.tz is not None and timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(data_type.tz)
        elif data_type.tz is not None:
            timestamp = timestamp.tz_convert(data_type.tz)
        return timestamp.to_pydatetime()
    raise ValueError(f"reaka_alpha158_price_parent_time_type_unsupported:{data_type}")


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"reaka_alpha158_price_parent_evidence_unreadable:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"reaka_alpha158_price_parent_evidence_not_object:{path}")
    return payload


def _mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"reaka_alpha158_price_parent_mapping_missing:{key}")
    return value


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"reaka_alpha158_price_parent_text_missing:{key}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValueError(f"reaka_alpha158_price_parent_artifact_unreadable:{path}") from exc
    return digest.hexdigest()


__all__ = [
    "ALPHA158_PRICE_PARENT_SCHEMA_ID",
    "GrantedAlpha158PriceWindow",
    "load_granted_alpha158_price_window",
]
