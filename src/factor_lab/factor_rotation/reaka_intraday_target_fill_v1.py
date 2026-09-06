# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false, reportArgumentType=false
# pyright: reportReturnType=false, reportOperatorIssue=false
# pyright: reportCallIssue=false, reportConstantRedefinition=false
# pyright: reportGeneralTypeIssues=false, reportUnusedCallResult=false

"""P6.1 intraday target/fill materialization for REAKA.

The product keeps information available at the 14:30/14:45 decision separate
from the first tradable raw fill after that clock.  It materializes no score,
model, holding, account, or scientific result.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
from numpy.typing import NDArray

from factor_lab.governance.canonicalization import canonical_digest

INTRADAY_TARGET_FILL_SCHEMA_ID: Final = "factorlab.reaka_intraday_target_fill_contract@1.0"
INTRADAY_TARGET_FILL_STORE_SCHEMA_ID: Final = "factorlab.reaka_intraday_target_fill_store@1.0"
INTRADAY_TARGET_FILL_VALIDATION_SCHEMA_ID: Final = "factorlab.reaka_intraday_target_fill_validation@1.0"
CLOCKS: Final[tuple[str, ...]] = ("14:30", "14:45")
CLOCK_SUFFIX: Final = {"14:30": "1430", "14:45": "1445"}
HORIZON_DAYS: Final = 20
SEQUENCE_POINTS: Final = 10
DECISION_INTERVAL_DAYS: Final = 5
HISTORY_FOOTPRINT_DAYS: Final = HORIZON_DAYS * SEQUENCE_POINTS
ANCHOR_DAY: Final = np.datetime64("2008-12-01")
START_MONTH: Final = "2007-01"
END_MONTH: Final = "2020-12"
DEFAULT_DATASET_VERSION: Final = "bars_cn_a_1m_raw_canonical_4ceca170a851"
DEFAULT_DATASET_ROOT: Final = Path(
    f"/home/starryocean/桌面/量化/unified_datahub/.runtime/live/lake/bars/dataset_version={DEFAULT_DATASET_VERSION}"
)
ARTIFACT_NAMES: Final = (
    "calendar.npy",
    "symbols.npy",
    "decision_positions.npy",
    "decision_close_1430.npy",
    "decision_minute_1430.npy",
    "entry_open_1430.npy",
    "entry_minute_1430.npy",
    "history_h20_raw_1430.npy",
    "future_h20_raw_1430.npy",
    "inference_rows_1430.npy",
    "evaluation_row_indices_1430.npy",
    "decision_close_1445.npy",
    "decision_minute_1445.npy",
    "entry_open_1445.npy",
    "entry_minute_1445.npy",
    "history_h20_raw_1445.npy",
    "future_h20_raw_1445.npy",
    "inference_rows_1445.npy",
    "evaluation_row_indices_1445.npy",
    "lineage.json",
)

_WORKER_SYMBOLS: frozenset[str] = frozenset()
_WORKER_CALENDAR_DAYS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class MonthExtraction:
    month: str
    input_rows: int
    rows: pd.DataFrame


def _with_digest(payload: Mapping[str, object]) -> dict[str, object]:
    output = dict(payload)
    _ = output.pop("canonical_digest", None)
    output["canonical_digest"] = canonical_digest(output)
    return output


def read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def write_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    output = _with_digest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_valid(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def month_range(start: str = START_MONTH, end: str = END_MONTH) -> tuple[str, ...]:
    values = pd.period_range(start, end, freq="M")
    return tuple(str(value) for value in values)


def _minute_of_day(values: pd.Series) -> NDArray[np.int16]:
    hour = pd.to_numeric(values.str.slice(0, 2), errors="raise").to_numpy(np.int16)
    minute = pd.to_numeric(values.str.slice(3, 5), errors="raise").to_numpy(np.int16)
    return (hour * 60 + minute).astype(np.int16)


def select_clock_coordinates(frame: pd.DataFrame) -> pd.DataFrame:
    """Select the causal decision mark and first post-decision fill per clock."""

    required = {"symbol", "trading_day", "timestamp", "open", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("reaka_intraday_source_columns_missing:" + ",".join(sorted(missing)))
    local = frame.loc[:, sorted(required)].copy()
    local["symbol"] = local["symbol"].astype(str)
    local["trading_day"] = local["trading_day"].astype(str)
    local["timestamp"] = local["timestamp"].astype(str)
    local["time"] = local["timestamp"].str.slice(11, 16)
    local = local.loc[local["time"].between("13:00", "15:00", inclusive="both")].copy()
    keys = ["trading_day", "symbol"]
    outputs: list[pd.DataFrame] = []
    for clock in CLOCKS:
        before = local.loc[
            local["time"].le(clock)
            & np.isfinite(pd.to_numeric(local["close"], errors="coerce"))
            & pd.to_numeric(local["close"], errors="coerce").gt(0.0)
        ]
        after = local.loc[
            local["time"].gt(clock)
            & local["time"].le("15:00")
            & np.isfinite(pd.to_numeric(local["open"], errors="coerce"))
            & pd.to_numeric(local["open"], errors="coerce").gt(0.0)
        ]
        if before.empty:
            decision = pd.DataFrame(columns=[*keys, "decision_timestamp", "decision_close"])
        else:
            before_index = before.groupby(keys, sort=False)["timestamp"].idxmax()
            decision = before.loc[before_index, [*keys, "timestamp", "close"]].rename(
                columns={
                    "timestamp": "decision_timestamp",
                    "close": "decision_close",
                }
            )
        if after.empty:
            entry = pd.DataFrame(columns=[*keys, "entry_timestamp", "entry_open"])
        else:
            after_index = after.groupby(keys, sort=False)["timestamp"].idxmin()
            entry = after.loc[after_index, [*keys, "timestamp", "open"]].rename(
                columns={"timestamp": "entry_timestamp", "open": "entry_open"}
            )
        merged = decision.merge(entry, on=keys, how="outer", validate="one_to_one")
        merged["decision_clock"] = clock
        outputs.append(merged)
    result = pd.concat(outputs, ignore_index=True)
    return result.sort_values(
        ["decision_clock", "trading_day", "symbol"],
        kind="mergesort",
    ).reset_index(drop=True)


def _init_worker_axis(symbols: tuple[str, ...], calendar_days: tuple[str, ...]) -> None:
    global _WORKER_SYMBOLS, _WORKER_CALENDAR_DAYS  # noqa: PLW0603
    _WORKER_SYMBOLS = frozenset(symbols)
    _WORKER_CALENDAR_DAYS = frozenset(calendar_days)


def _extract_month(args: tuple[str, str]) -> MonthExtraction:
    path_text, month = args
    path = Path(path_text)
    table = pq.ParquetFile(path).read(columns=["symbol", "trading_day", "timestamp", "open", "close"])
    input_rows = table.num_rows
    time_values = pc.utf8_slice_codeunits(table["timestamp"], 11, 16)
    afternoon = pc.and_(
        pc.greater_equal(time_values, "13:00"),
        pc.less_equal(time_values, "15:00"),
    )
    table = table.filter(afternoon)
    frame = table.to_pandas(split_blocks=True, self_destruct=True)
    frame = frame.loc[frame["symbol"].astype(str).isin(_WORKER_SYMBOLS) & frame["trading_day"].astype(str).isin(_WORKER_CALENDAR_DAYS)]
    return MonthExtraction(
        month=month,
        input_rows=input_rows,
        rows=select_clock_coordinates(frame),
    )


def partition_files(
    dataset_root: Path,
    *,
    months: Sequence[str],
) -> tuple[tuple[str, Path], ...]:
    output: list[tuple[str, Path]] = []
    for month in months:
        path = dataset_root / "instrument_type=stock" / f"trading_month={month}" / "data_0.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"reaka_intraday_partition_missing:{month}:{path}")
        output.append((month, path))
    return tuple(output)


def _load_reference_axis(
    reference_path: Path,
) -> tuple[NDArray[np.datetime64], NDArray[np.str_]]:
    with np.load(reference_path, allow_pickle=False) as payload:
        calendar = np.asarray(payload["calendar"], dtype="datetime64[ns]")
        symbols = np.asarray(payload["symbols"], dtype=str)
    if len(np.unique(calendar)) != len(calendar) or len(np.unique(symbols)) != len(symbols):
        raise ValueError("reaka_intraday_reference_axis_not_unique")
    if calendar[0] != np.datetime64("2007-01-04") or calendar[-1] != np.datetime64("2020-12-31"):
        raise ValueError("reaka_intraday_reference_calendar_identity_drift")
    return calendar, symbols


def _build_feature_support(
    *,
    calendar: NDArray[np.datetime64],
    symbol_count: int,
    ot3_path: Path,
) -> NDArray[np.bool_]:
    transport = pd.read_parquet(
        ot3_path,
        columns=["asof_date", "symbol_position", "available", "uses_future"],
    )
    if transport["uses_future"].any() or not transport["available"].all():
        raise ValueError("reaka_intraday_OT3_causality_invalid")
    transport["asof_date"] = pd.to_datetime(transport["asof_date"], errors="raise")
    dates = pd.DatetimeIndex(sorted(transport["asof_date"].unique()))
    day_map = {pd.Timestamp(value): index for index, value in enumerate(calendar)}
    asof_positions = np.asarray([day_map[pd.Timestamp(value)] for value in dates], dtype=np.int64)
    weekly = np.zeros((len(dates), symbol_count), dtype=bool)
    date_index = {pd.Timestamp(value): index for index, value in enumerate(dates)}
    row = transport["asof_date"].map(date_index).to_numpy(np.int64)
    symbol = transport["symbol_position"].to_numpy(np.int64)
    if (symbol < 0).any() or (symbol >= symbol_count).any():
        raise ValueError("reaka_intraday_OT3_symbol_position_invalid")
    weekly[row, symbol] = True
    latest = np.searchsorted(asof_positions, np.arange(len(calendar)), side="left") - 1
    support = np.zeros((len(calendar), symbol_count), dtype=bool)
    valid = latest >= 0
    support[valid] = weekly[latest[valid]]
    return support


def _h20_surfaces(
    decision_close: NDArray[np.float32],
    entry_open: NDArray[np.float32],
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    if decision_close.shape != entry_open.shape:
        raise ValueError("reaka_intraday_price_surface_shape_mismatch")
    history = np.full(decision_close.shape, np.nan, dtype=np.float32)
    future = np.full(entry_open.shape, np.nan, dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        history[HORIZON_DAYS:] = decision_close[HORIZON_DAYS:] / decision_close[:-HORIZON_DAYS] - 1.0
        future[:-HORIZON_DAYS] = entry_open[HORIZON_DAYS:] / entry_open[:-HORIZON_DAYS] - 1.0
    history[~np.isfinite(history)] = np.nan
    future[~np.isfinite(future)] = np.nan
    return history, future


def _decision_positions(calendar: NDArray[np.datetime64]) -> NDArray[np.int64]:
    anchor = np.flatnonzero(calendar.astype("datetime64[D]") == ANCHOR_DAY)
    if len(anchor) != 1:
        raise ValueError("reaka_intraday_D5_anchor_missing")
    positions = np.arange(int(anchor[0]), len(calendar), DECISION_INTERVAL_DAYS, dtype=np.int64)
    return positions[calendar[positions].astype("datetime64[Y]").astype(int) + 1970 >= 2009]


def _inference_rows(
    *,
    calendar: NDArray[np.datetime64],
    history: NDArray[np.float32],
    feature_support: NDArray[np.bool_],
    future: NDArray[np.float32],
    decision_positions: NDArray[np.int64],
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    parts: list[NDArray[np.int64]] = []
    anchor = int(np.flatnonzero(calendar.astype("datetime64[D]") == ANCHOR_DAY)[0])
    offsets = np.arange(
        -(SEQUENCE_POINTS - 1) * HORIZON_DAYS,
        1,
        HORIZON_DAYS,
        dtype=np.int64,
    )
    for day in decision_positions:
        endpoints = day + offsets
        if (endpoints < 0).any():
            continue
        history_ok = np.isfinite(history[endpoints]).all(axis=0)
        usable = history_ok & feature_support[day]
        symbols = np.flatnonzero(usable).astype(np.int64)
        if not len(symbols):
            continue
        year = int(calendar[day].astype("datetime64[Y]").astype(int) + 1970)
        phase = int(((day - anchor) // DECISION_INTERVAL_DAYS) % 4)
        parts.append(
            np.column_stack(
                (
                    np.full(len(symbols), day, dtype=np.int64),
                    symbols,
                    np.full(len(symbols), year, dtype=np.int64),
                    np.full(len(symbols), phase, dtype=np.int64),
                )
            )
        )
    rows = np.vstack(parts) if parts else np.empty((0, 4), dtype=np.int64)
    label_ok = np.isfinite(future[rows[:, 0], rows[:, 1]]) if len(rows) else np.zeros(0, dtype=bool)
    evaluation = np.flatnonzero(label_ok).astype(np.int64)
    return rows, evaluation


def _assign_month(
    *,
    extraction: MonthExtraction,
    day_index: Mapping[str, int],
    symbol_index: Mapping[str, int],
    decision_close: Mapping[str, NDArray[np.float32]],
    decision_minute: Mapping[str, NDArray[np.int16]],
    entry_open: Mapping[str, NDArray[np.float32]],
    entry_minute: Mapping[str, NDArray[np.int16]],
) -> None:
    frame = extraction.rows
    if frame.empty:
        return
    days = frame["trading_day"].map(day_index)
    symbols = frame["symbol"].map(symbol_index)
    if days.isna().any() or symbols.isna().any():
        raise ValueError(f"reaka_intraday_axis_join_failed:{extraction.month}")
    di = days.to_numpy(np.int64)
    si = symbols.to_numpy(np.int64)
    for clock in CLOCKS:
        local = frame["decision_clock"].eq(clock).to_numpy()
        suffix = CLOCK_SUFFIX[clock]
        local_days = di[local]
        local_symbols = si[local]
        closes = pd.to_numeric(frame.loc[local, "decision_close"], errors="coerce").to_numpy(np.float32)
        opens = pd.to_numeric(frame.loc[local, "entry_open"], errors="coerce").to_numpy(np.float32)
        decision_timestamps = frame.loc[local, "decision_timestamp"].astype("string")
        entry_timestamps = frame.loc[local, "entry_timestamp"].astype("string")
        decision_times = decision_timestamps.str.slice(11, 16)
        entry_times = entry_timestamps.str.slice(11, 16)
        valid_close = np.isfinite(closes)
        valid_open = np.isfinite(opens)
        decision_close[suffix][local_days[valid_close], local_symbols[valid_close]] = closes[valid_close]
        entry_open[suffix][local_days[valid_open], local_symbols[valid_open]] = opens[valid_open]
        valid_decision_time = decision_times.notna().to_numpy()
        valid_entry_time = entry_times.notna().to_numpy()
        if valid_decision_time.any():
            decision_minute[suffix][local_days[valid_decision_time], local_symbols[valid_decision_time]] = _minute_of_day(
                decision_times.loc[valid_decision_time]
            )
        if valid_entry_time.any():
            entry_minute[suffix][local_days[valid_entry_time], local_symbols[valid_entry_time]] = _minute_of_day(
                entry_times.loc[valid_entry_time]
            )


def materialize_intraday_target_fill(
    *,
    output_root: Path,
    dataset_root: Path,
    reference_path: Path,
    ot3_path: Path,
    contract_digest: str,
    workers: int = 4,
) -> dict[str, object]:
    if output_root.exists():
        raise FileExistsError(f"reaka_intraday_output_exists:{output_root}")
    calendar, symbols = _load_reference_axis(reference_path)
    partitions = partition_files(dataset_root, months=month_range())
    shape = (len(calendar), len(symbols))
    decision_close = {suffix: np.full(shape, np.nan, dtype=np.float32) for suffix in CLOCK_SUFFIX.values()}
    entry_open = {suffix: np.full(shape, np.nan, dtype=np.float32) for suffix in CLOCK_SUFFIX.values()}
    decision_minute = {suffix: np.full(shape, -1, dtype=np.int16) for suffix in CLOCK_SUFFIX.values()}
    entry_minute = {suffix: np.full(shape, -1, dtype=np.int16) for suffix in CLOCK_SUFFIX.values()}
    day_strings = tuple(str(value.astype("datetime64[D]")) for value in calendar)
    symbol_strings = tuple(str(value) for value in symbols)
    args = tuple((str(path), month) for month, path in partitions)
    day_index = {value: index for index, value in enumerate(day_strings)}
    symbol_index = {value: index for index, value in enumerate(symbol_strings)}
    input_rows = 0
    extracted_rows = 0
    with ProcessPoolExecutor(
        max_workers=max(1, workers),
        initializer=_init_worker_axis,
        initargs=(symbol_strings, day_strings),
    ) as executor:
        for extraction in executor.map(_extract_month, args, chunksize=1):
            input_rows += extraction.input_rows
            extracted_rows += len(extraction.rows)
            _assign_month(
                extraction=extraction,
                day_index=day_index,
                symbol_index=symbol_index,
                decision_close=decision_close,
                decision_minute=decision_minute,
                entry_open=entry_open,
                entry_minute=entry_minute,
            )
    feature_support = _build_feature_support(
        calendar=calendar,
        symbol_count=len(symbols),
        ot3_path=ot3_path,
    )
    decisions = _decision_positions(calendar)
    history: dict[str, NDArray[np.float32]] = {}
    future: dict[str, NDArray[np.float32]] = {}
    rows: dict[str, NDArray[np.int64]] = {}
    evaluations: dict[str, NDArray[np.int64]] = {}
    for suffix in CLOCK_SUFFIX.values():
        history[suffix], future[suffix] = _h20_surfaces(decision_close[suffix], entry_open[suffix])
        rows[suffix], evaluations[suffix] = _inference_rows(
            calendar=calendar,
            history=history[suffix],
            feature_support=feature_support,
            future=future[suffix],
            decision_positions=decisions,
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    try:
        np.save(temporary / "calendar.npy", calendar, allow_pickle=False)
        np.save(temporary / "symbols.npy", symbols, allow_pickle=False)
        np.save(temporary / "decision_positions.npy", decisions, allow_pickle=False)
        for suffix in CLOCK_SUFFIX.values():
            np.save(
                temporary / f"decision_close_{suffix}.npy",
                decision_close[suffix],
                allow_pickle=False,
            )
            np.save(
                temporary / f"decision_minute_{suffix}.npy",
                decision_minute[suffix],
                allow_pickle=False,
            )
            np.save(
                temporary / f"entry_open_{suffix}.npy",
                entry_open[suffix],
                allow_pickle=False,
            )
            np.save(
                temporary / f"entry_minute_{suffix}.npy",
                entry_minute[suffix],
                allow_pickle=False,
            )
            np.save(
                temporary / f"history_h20_raw_{suffix}.npy",
                history[suffix],
                allow_pickle=False,
            )
            np.save(
                temporary / f"future_h20_raw_{suffix}.npy",
                future[suffix],
                allow_pickle=False,
            )
            np.save(
                temporary / f"inference_rows_{suffix}.npy",
                rows[suffix],
                allow_pickle=False,
            )
            np.save(
                temporary / f"evaluation_row_indices_{suffix}.npy",
                evaluations[suffix],
                allow_pickle=False,
            )
        lineage = write_json(
            temporary / "lineage.json",
            {
                "schema_id": "factorlab.reaka_intraday_target_fill_lineage@1.0",
                "dataset_version": DEFAULT_DATASET_VERSION,
                "decision_price": ("last_raw_trade_close_between_1300_and_decision_clock_same_day"),
                "entry_fill": "first_raw_1m_bar_open_after_decision_clock_same_day",
                "exit_fill": "same_clock_first_raw_1m_bar_open_after_clock_on_t_plus_20",
                "history_return": "decision_close_t_div_decision_close_t_minus_20_minus_1",
                "future_target": "entry_open_t_plus_20_div_entry_open_t_minus_1",
                "inference_filters": [
                    "historical_window_complete_at_decision",
                    "strictly_prior_OT3_feature_support",
                ],
                "forbidden_inference_filters": ["future_target", "entry_fill"],
                "labels_joined_after_scoring": True,
                "execution_eligibility_applied_after_scoring": True,
                "next_open_used": False,
            },
        )
        artifact_digests = {name: file_digest(temporary / name) for name in ARTIFACT_NAMES}
        per_clock: dict[str, object] = {}
        for clock, suffix in CLOCK_SUFFIX.items():
            evaluation_count = len(evaluations[suffix])
            inference_count = len(rows[suffix])
            per_clock[clock] = {
                "decision_price_count": int(np.isfinite(decision_close[suffix]).sum()),
                "entry_fill_count": int(np.isfinite(entry_open[suffix]).sum()),
                "history_h20_count": int(np.isfinite(history[suffix]).sum()),
                "future_h20_count": int(np.isfinite(future[suffix]).sum()),
                "inference_row_count": inference_count,
                "evaluation_label_row_count": evaluation_count,
                "inference_without_future_label_count": inference_count - evaluation_count,
                "decision_minute_max": int(decision_minute[suffix].max()),
                "entry_minute_min": int(entry_minute[suffix][entry_minute[suffix] >= 0].min()),
            }
        manifest = write_json(
            temporary / "manifest.json",
            {
                "schema_id": INTRADAY_TARGET_FILL_STORE_SCHEMA_ID,
                "status": "materialized_result_free_intraday_target_fill",
                "contract_digest": contract_digest,
                "dataset_version": DEFAULT_DATASET_VERSION,
                "calendar_start": str(calendar[0].astype("datetime64[D]")),
                "calendar_end": str(calendar[-1].astype("datetime64[D]")),
                "calendar_days": len(calendar),
                "symbol_count": len(symbols),
                "source_partition_count": len(partitions),
                "source_row_count": input_rows,
                "extracted_coordinate_row_count": extracted_rows,
                "decision_position_count": len(decisions),
                "decision_clocks": list(CLOCKS),
                "execution_window": "next_tradable_after_bar_close",
                "fill_view": "raw_1m",
                "H_days": HORIZON_DAYS,
                "L_points": SEQUENCE_POINTS,
                "W_days": HISTORY_FOOTPRINT_DAYS,
                "decision_interval_days": DECISION_INTERVAL_DAYS,
                "phase_count": 4,
                "per_clock": per_clock,
                "lineage_digest": lineage["canonical_digest"],
                "artifact_digests": artifact_digests,
                "post_2020_rows_read": 0,
                "training_run": False,
                "score_run": False,
                "account_run": False,
                "production_authority": False,
            },
        )
        temporary.rename(output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def validate_contract(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_id") != INTRADAY_TARGET_FILL_SCHEMA_ID:
        blockers.append("intraday_contract_schema_invalid")
    if not canonical_valid(payload):
        blockers.append("intraday_contract_digest_invalid")
    if payload.get("decision_clocks") != list(CLOCKS):
        blockers.append("intraday_contract_clocks_invalid")
    if payload.get("execution_window") != "next_tradable_after_bar_close":
        blockers.append("intraday_contract_execution_invalid")
    if payload.get("next_open_allowed") is not False:
        blockers.append("intraday_contract_next_open_not_forbidden")
    if payload.get("model_training_allowed") is not False:
        blockers.append("intraday_contract_training_must_be_closed")
    if payload.get("score_materialization_allowed") is not False:
        blockers.append("intraday_contract_scoring_must_be_closed")
    if payload.get("account_execution_allowed") is not False:
        blockers.append("intraday_contract_account_must_be_closed")
    return blockers


__all__ = [
    "ANCHOR_DAY",
    "ARTIFACT_NAMES",
    "CLOCKS",
    "CLOCK_SUFFIX",
    "DECISION_INTERVAL_DAYS",
    "DEFAULT_DATASET_ROOT",
    "DEFAULT_DATASET_VERSION",
    "END_MONTH",
    "HISTORY_FOOTPRINT_DAYS",
    "HORIZON_DAYS",
    "INTRADAY_TARGET_FILL_SCHEMA_ID",
    "INTRADAY_TARGET_FILL_STORE_SCHEMA_ID",
    "INTRADAY_TARGET_FILL_VALIDATION_SCHEMA_ID",
    "MonthExtraction",
    "SEQUENCE_POINTS",
    "START_MONTH",
    "canonical_valid",
    "file_digest",
    "materialize_intraday_target_fill",
    "month_range",
    "partition_files",
    "read_json",
    "select_clock_coordinates",
    "validate_contract",
    "write_json",
]
