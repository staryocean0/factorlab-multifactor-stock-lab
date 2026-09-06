# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
# pyright: reportOperatorIssue=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedCallResult=false
"""Aggregate-only 2021--2026 replay for the frozen current REAKA generation."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
from numpy.typing import NDArray

from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
from factor_lab.factor_rotation import reaka_intraday_target_fill_v1 as target_fill_module
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    IntradayK1InputStore,
    build_exposure_store,
    build_inference_rows,
    build_state_store,
    factor_order,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    LARGE_TARGET_ID,
    MARKET_FACTOR_ID,
    SMALL_TARGET_ID,
    build_causal_basis_pair,
    build_selected_states,
    fit_intraday_stock_exposures,
    load_memberships,
    membership_for_decisions,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    CLOCK_SUFFIX,
    CLOCKS,
    COMMON_ROOT_POLICY_ID,
    INITIAL_NAV,
    SLIPPAGE_MULTIPLIERS,
    TradabilityRow,
    account_metrics,
    apply_non_rebalance_day,
    apply_rebalance_day,
    build_execution_target,
    current_weights_from_book,
    policy_by_id,
    rank_portfolio_table,
)
from factor_lab.factor_rotation.reaka_intraday_target_fill_v1 import (
    _assign_month,
    _decision_positions,
    _h20_surfaces,
    _init_worker_axis,
    month_range,
    partition_files,
    select_clock_coordinates,
)
from factor_lab.factor_rotation.reaka_stage6_portfolio_execution import (
    eligibility_from_row,
    map_risk_warning_for_rules,
)
from factor_lab.governance.aggregate_blackbox_evaluation import (
    AggregateBlackboxPlan,
    validate_aggregate_result,
)
from factor_lab.governance.canonicalization import canonical_digest

ROOT: Final = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATAHUB: Final = Path("/home/starryocean/桌面/量化/unified_datahub")
QUERY_ID: Final = "REAKA_CURRENT_GENERATION_V1_2021_2026_AGGREGATE_BLACKBOX_Q1"
CANDIDATE_FINGERPRINT: Final = (
    "sha256:a181d22711254a4e01206a1b3006cbb736082e38054682a78e5d89d2bb6181fa"
)
CONTRACT_RELATIVE: Final = Path(
    "docs/ops/reaka_current_generation_aggregate_blackbox@1.5.json"
)
OLD_TARGET_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"
OLD_OT_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
OLD_STORE_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
CHECKPOINT_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017"
NORMALIZER_ROOT: Final = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight"
EXTENSION_ROOT: Final = ROOT / "output/factor-rotation/reaka_residual_only_post2020_extension_v1_2009_2026"
FACTOR_REGISTRY: Final = ROOT / "docs/ops/factor_condensation_index_registry@1.0.json"
OLD_CLOUDRIDGE: Final = (
    ROOT
    / "output/factor-rotation/reaka_opportunity_ledger_v9_inputs_2008_2020"
    / "cloudridge_beta_weekly_2008_2020.constituents.csv"
)
INTRADAY_DATASET_ROOT: Final = (
    DATAHUB
    / ".runtime/live/lake/bars"
    / "dataset_version=bars_cn_a_1m_raw_canonical_4ceca170a851"
)
ADJUSTMENT_FACTORS: Final = (
    DATAHUB
    / ".runtime/live/lake/adjustment_factors"
    / "dataset_version=adjust_factors_cn_a_xdxr_v9_20260814"
    / "factors.parquet"
)
METADATA_VERSIONS: Final = (
    "security_day_metadata_cn_a_stock_2021_pool_assembled_v2_20260821",
    "security_day_metadata_cn_a_stock_2022_pool_assembled_v2_20260821",
    "security_day_metadata_cn_a_stock_2023_pool_assembled_v2_20260821",
    "security_day_metadata_cn_a_stock_2024_pool_assembled_v2_20260821",
    "security_day_metadata_cn_a_stock_2025_pool_assembled_v2_20260821",
    "security_day_metadata_cn_a_stock_2026_pool_assembled_v1_20260825",
)
SOURCE_FILES: Final[tuple[str, ...]] = (
    "docs/ops/aggregate_blackbox_evaluation@1.0.json",
    "docs/ops/aggregate_blackbox_evaluation_whitepaper.md",
    "docs/user/aggregate_blackbox_evaluation_workflow.md",
    "docs/ops/reaka_current_generation_aggregate_blackbox_whitepaper.md",
    "docs/user/reaka_current_generation_aggregate_blackbox_workflow.md",
    "src/factor_lab/governance/aggregate_blackbox_evaluation.py",
    "src/factor_lab/factor_rotation/reaka_current_generation_aggregate_blackbox_v1.py",
    "scripts/factor_rotation/run_reaka_current_generation_aggregate_blackbox_v1.py",
    "scripts/factor_rotation/validate_reaka_current_generation_aggregate_blackbox_v1.py",
    "tests/unit/test_aggregate_blackbox_evaluation.py",
    "tests/unit/test_reaka_current_generation_aggregate_blackbox_v1.py",
    "src/factor_lab/factor_rotation/reaka_intraday_target_fill_v1.py",
    "src/factor_lab/factor_rotation/reaka_intraday_orthogonal_ot_v1.py",
    "src/factor_lab/factor_rotation/reaka_intraday_k1_preflight_v1.py",
    "src/factor_lab/factor_rotation/reaka_intraday_k1_training_v1.py",
    "src/factor_lab/factor_rotation/reaka_intraday_portfolio_mapping_v1.py",
    "scripts/factor_rotation/build_reaka_intraday_portfolio_mapping_inputs_v1.py",
)


@dataclass(slots=True)
class ExtendedTargetSurfaces:
    tree: str
    root: Path
    calendar: NDArray[np.datetime64]
    symbols: NDArray[np.str_]
    decision_positions: NDArray[np.int64]
    prefix_checks: dict[str, bool]


@dataclass(frozen=True, slots=True)
class BlackboxMonthExtraction:
    month: str
    coordinates: pd.DataFrame
    final_closes: pd.DataFrame


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_valid(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def write_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result.pop("canonical_digest", None)
    result["canonical_digest"] = canonical_digest(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def source_closure() -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"reaka_blackbox_source_missing:{relative}")
        result[relative] = file_digest(path)
    return result


def input_binding_map() -> dict[str, str]:
    bindings: dict[str, str] = {}

    def bind(key: str, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"reaka_blackbox_input_missing:{key}:{path}")
        bindings[key] = file_digest(path)

    bind("raw_1m_manifest", INTRADAY_DATASET_ROOT / "manifest.json")
    bind("adjustment_factors_v9", ADJUSTMENT_FACTORS)
    for version in METADATA_VERSIONS:
        root = (
            DATAHUB
            / ".runtime/live/lake/security_day_metadata"
            / f"dataset_version={version}"
        )
        bind(f"metadata_manifest:{version}", root / "manifest.json")
        bind(f"metadata_data:{version}", root / "security_day_metadata.parquet")
    for tree in ("formal", "isolated"):
        bind(
            f"extension_store_manifest:{tree}",
            EXTENSION_ROOT / tree / "store/manifest.json",
        )
        bind(
            f"extension_array_manifest:{tree}",
            EXTENSION_ROOT / tree / "arrays/array_manifest.json",
        )
        bind(f"old_target_manifest:{tree}", OLD_TARGET_ROOT / tree / "manifest.json")
        for suffix in CLOCK_SUFFIX.values():
            for stage in ("ot1", "ot2", "ot3"):
                bind(
                    f"old_intraday_{stage}:{tree}:{suffix}",
                    OLD_OT_ROOT / tree / suffix / stage / "manifest.json",
                )
            for seed in (11, 29, 47):
                bind(
                    f"checkpoint:{tree}:{suffix}:{seed}",
                    CHECKPOINT_ROOT
                    / tree
                    / suffix
                    / f"checkpoints/seed_{seed}/manifest.json",
                )
    for suffix in CLOCK_SUFFIX.values():
        bind(f"normalizer:{suffix}", NORMALIZER_ROOT / suffix / "normalizer.json")
    return dict(sorted(bindings.items()))


def load_contract() -> dict[str, object]:
    payload = read_json(ROOT / CONTRACT_RELATIVE)
    if not canonical_valid(payload):
        raise ValueError("reaka_blackbox_contract_digest_invalid")
    if "base_contract" in payload:
        binding = cast(Mapping[str, object], payload["base_contract"])
        base_path = ROOT / str(binding["path"])
        if file_digest(base_path) != binding.get("sha256"):
            raise ValueError("reaka_blackbox_base_contract_file_drift")
        base = read_json(base_path)
        if not canonical_valid(base) or base.get("canonical_digest") != binding.get("canonical_digest"):
            raise ValueError("reaka_blackbox_base_contract_canonical_drift")
        wrapper = payload
        payload = {**base, **cast(Mapping[str, object], wrapper["overrides"])}
        payload.update(
            {
                "schema_id": wrapper["schema_id"],
                "status": wrapper["status"],
                "base_contract": binding,
                "pre_result_incident_digest": wrapper["pre_result_incident_digest"],
                "canonical_digest": wrapper["canonical_digest"],
            }
        )
    if payload.get("status") != "frozen_candidate_specific_aggregate_repeat_audit_open":
        raise ValueError("reaka_blackbox_contract_not_open")
    if payload.get("candidate_fingerprint") != CANDIDATE_FINGERPRINT:
        raise ValueError("reaka_blackbox_candidate_fingerprint_drift")
    if payload.get("source_closure") != source_closure():
        raise ValueError("reaka_blackbox_source_closure_drift")
    bindings = input_binding_map()
    if payload.get("input_binding_count") != len(bindings):
        raise ValueError("reaka_blackbox_input_binding_count_drift")
    if payload.get("input_binding_digest") != canonical_digest(bindings):
        raise ValueError("reaka_blackbox_input_binding_digest_drift")
    if payload.get("fresh_oos") is not False or payload.get("result_backflow_allowed") is not False:
        raise ValueError("reaka_blackbox_authority_failed_open")
    return payload


def blackbox_plan() -> AggregateBlackboxPlan:
    return AggregateBlackboxPlan(
        query_id=QUERY_ID,
        candidate_fingerprint=CANDIDATE_FINGERPRINT,
        detail_state_before="detail_previously_consumed",
        aggregate_answer_state_before="aggregate_unopened",
        evidence_role="candidate_specific_first_aggregate_blackbox_on_globally_consumed_interval",
        account_identities=CLOCKS,
        cost_identities=tuple(f"slippage_{value:.1f}x" for value in SLIPPAGE_MULTIPLIERS),
        attempt_count=len(CLOCKS) * len(SLIPPAGE_MULTIPLIERS),
        fresh_oos=False,
    )


def _arrays_equal(left: NDArray[np.generic], right: NDArray[np.generic]) -> bool:
    left_array = np.asarray(left)
    right_array = np.asarray(right)
    if np.issubdtype(left_array.dtype, np.floating):
        return bool(np.array_equal(left_array, right_array, equal_nan=True))
    return bool(np.array_equal(left_array, right_array))


def _extract_month_with_final_close(args: tuple[str, str]) -> BlackboxMonthExtraction:
    path_text, month = args
    table = pq.ParquetFile(Path(path_text)).read(
        columns=["symbol", "trading_day", "timestamp", "open", "close"]
    )
    time_values = pc.utf8_slice_codeunits(table["timestamp"], 11, 16)
    afternoon = pc.and_(
        pc.greater_equal(time_values, "13:00"),
        pc.less_equal(time_values, "15:00"),
    )
    frame = table.filter(afternoon).to_pandas(split_blocks=True, self_destruct=True)
    frame = frame.loc[
        frame["symbol"].astype(str).isin(target_fill_module._WORKER_SYMBOLS)
        & frame["trading_day"].astype(str).isin(target_fill_module._WORKER_CALENDAR_DAYS)
    ].copy()
    coordinates = select_clock_coordinates(frame)
    close = pd.to_numeric(frame["close"], errors="coerce")
    valid = frame.loc[np.isfinite(close) & close.gt(0.0)].copy()
    if valid.empty:
        final_closes = pd.DataFrame(columns=["trading_day", "symbol", "raw_close"])
    else:
        final_index = valid.groupby(["trading_day", "symbol"], sort=False)[
            "timestamp"
        ].idxmax()
        final_closes = valid.loc[
            final_index, ["trading_day", "symbol", "close"]
        ].rename(columns={"close": "raw_close"})
    return BlackboxMonthExtraction(
        month=month,
        coordinates=coordinates,
        final_closes=final_closes,
    )


def build_extended_target_surfaces(
    *,
    tree: str,
    output_root: Path,
    workers: int = 4,
) -> ExtendedTargetSurfaces:
    extension_arrays = EXTENSION_ROOT / tree / "arrays"
    calendar = np.load(extension_arrays / "calendar.npy", mmap_mode="r")
    symbols = np.load(extension_arrays / "symbols.npy", mmap_mode="r").astype(str)
    old = OLD_TARGET_ROOT / tree
    old_calendar = np.load(old / "calendar.npy", mmap_mode="r")
    old_symbols = np.load(old / "symbols.npy", mmap_mode="r").astype(str)
    if not _arrays_equal(calendar[: len(old_calendar)], old_calendar):
        raise ValueError("reaka_blackbox_calendar_prefix_drift")
    if not _arrays_equal(symbols[: len(old_symbols)], old_symbols):
        raise ValueError("reaka_blackbox_symbol_prefix_drift")
    output_root.mkdir(parents=True, exist_ok=False)
    np.save(output_root / "calendar.npy", np.asarray(calendar), allow_pickle=False)
    np.save(output_root / "symbols.npy", np.asarray(symbols), allow_pickle=False)
    shape = (len(calendar), len(symbols))
    decision_close: dict[str, NDArray[np.float32]] = {}
    entry_open: dict[str, NDArray[np.float32]] = {}
    decision_minute: dict[str, NDArray[np.int16]] = {}
    entry_minute: dict[str, NDArray[np.int16]] = {}
    raw_close = np.lib.format.open_memmap(
        output_root / "raw_close.npy", mode="w+", dtype=np.float32, shape=shape
    )
    raw_close[:] = np.nan
    extension_close = np.load(EXTENSION_ROOT / tree / "arrays/raw_close.npy", mmap_mode="r")
    raw_close[: len(old_calendar), : len(old_symbols)] = extension_close[
        : len(old_calendar), : len(old_symbols)
    ]
    for suffix in CLOCK_SUFFIX.values():
        decision_close[suffix] = np.lib.format.open_memmap(
            output_root / f"decision_close_{suffix}.npy", mode="w+", dtype=np.float32, shape=shape
        )
        entry_open[suffix] = np.lib.format.open_memmap(
            output_root / f"entry_open_{suffix}.npy", mode="w+", dtype=np.float32, shape=shape
        )
        decision_minute[suffix] = np.lib.format.open_memmap(
            output_root / f"decision_minute_{suffix}.npy", mode="w+", dtype=np.int16, shape=shape
        )
        entry_minute[suffix] = np.lib.format.open_memmap(
            output_root / f"entry_minute_{suffix}.npy", mode="w+", dtype=np.int16, shape=shape
        )
        decision_close[suffix][:] = np.nan
        entry_open[suffix][:] = np.nan
        decision_minute[suffix][:] = -1
        entry_minute[suffix][:] = -1
        old_rows = len(old_calendar)
        old_columns = len(old_symbols)
        decision_close[suffix][:old_rows, :old_columns] = np.load(
            old / f"decision_close_{suffix}.npy", mmap_mode="r"
        )
        entry_open[suffix][:old_rows, :old_columns] = np.load(
            old / f"entry_open_{suffix}.npy", mmap_mode="r"
        )
        decision_minute[suffix][:old_rows, :old_columns] = np.load(
            old / f"decision_minute_{suffix}.npy", mmap_mode="r"
        )
        entry_minute[suffix][:old_rows, :old_columns] = np.load(
            old / f"entry_minute_{suffix}.npy", mmap_mode="r"
        )
    months = month_range("2021-01", "2026-08")
    partitions = partition_files(INTRADAY_DATASET_ROOT, months=months)
    day_strings = tuple(str(value.astype("datetime64[D]")) for value in calendar)
    symbol_strings = tuple(str(value) for value in symbols)
    day_index = {value: index for index, value in enumerate(day_strings)}
    symbol_index = {value: index for index, value in enumerate(symbol_strings)}
    with ProcessPoolExecutor(
        max_workers=max(1, workers),
        initializer=_init_worker_axis,
        initargs=(symbol_strings, day_strings),
    ) as executor:
        args = tuple((str(path), month) for month, path in partitions)
        for extraction in executor.map(_extract_month_with_final_close, args, chunksize=1):
            _assign_month(
                extraction=target_fill_module.MonthExtraction(
                    month=extraction.month,
                    input_rows=0,
                    rows=extraction.coordinates,
                ),
                day_index=day_index,
                symbol_index=symbol_index,
                decision_close=decision_close,
                decision_minute=decision_minute,
                entry_open=entry_open,
                entry_minute=entry_minute,
            )
            closes = extraction.final_closes
            if not closes.empty:
                day_rows = closes["trading_day"].astype(str).map(day_index)
                symbol_rows = closes["symbol"].astype(str).map(symbol_index)
                if day_rows.isna().any() or symbol_rows.isna().any():
                    raise ValueError(f"reaka_blackbox_final_close_axis_join_failed:{extraction.month}")
                raw_close[
                    day_rows.to_numpy(np.int64),
                    symbol_rows.to_numpy(np.int64),
                ] = pd.to_numeric(closes["raw_close"], errors="raise").to_numpy(np.float32)
    for values in (
        *decision_close.values(),
        *entry_open.values(),
        *decision_minute.values(),
        *entry_minute.values(),
        raw_close,
    ):
        values.flush()  # type: ignore[attr-defined]
    decisions = _decision_positions(np.asarray(calendar))
    np.save(output_root / "decision_positions.npy", decisions, allow_pickle=False)
    prefix_checks: dict[str, bool] = {
        "calendar": True,
        "symbols": True,
    }
    for suffix in CLOCK_SUFFIX.values():
        for prefix in ("decision_close", "entry_open", "decision_minute", "entry_minute"):
            current = np.load(output_root / f"{prefix}_{suffix}.npy", mmap_mode="r")
            historical = np.load(old / f"{prefix}_{suffix}.npy", mmap_mode="r")
            prefix_checks[f"{prefix}_{suffix}"] = _arrays_equal(
                current[: len(old_calendar), : len(old_symbols)], historical
            )
        clock_minute = 14 * 60 + (30 if suffix == "1430" else 45)
        minute_values = np.load(output_root / f"entry_minute_{suffix}.npy", mmap_mode="r")
        observed = minute_values[minute_values >= 0]
        prefix_checks[f"entry_strictly_after_{suffix}"] = bool(len(observed) and int(observed.min()) > clock_minute)
    if not all(prefix_checks.values()):
        failed = [key for key, value in prefix_checks.items() if not value]
        raise ValueError("reaka_blackbox_target_prefix_or_clock_failed:" + ",".join(failed))
    return ExtendedTargetSurfaces(
        tree=tree,
        root=output_root,
        calendar=np.asarray(calendar),
        symbols=np.asarray(symbols),
        decision_positions=np.asarray(decisions),
        prefix_checks=prefix_checks,
    )


def _frozen_selections(tree: str, suffix: str) -> pd.DataFrame:
    payload = read_json(OLD_OT_ROOT / tree / suffix / "ot2/selected_family_tools.json")
    rows = cast(list[dict[str, object]], payload["selections"])
    selected = pd.DataFrame(rows)
    if set(selected["economic_family_id"].astype(str)) != {"market", "size", "industry"}:
        raise ValueError("reaka_blackbox_frozen_OT2_selection_invalid")
    return selected


def _append_only_cloudridge_path(*, tree: str, target_root: Path) -> Path:
    extension_path = (
        EXTENSION_ROOT
        / tree
        / "cloudridge/cloudridge_beta_weekly_2008_2026.constituents.csv"
    )
    old = pd.read_csv(OLD_CLOUDRIDGE, dtype={"symbol": str})
    extension = pd.read_csv(extension_path, dtype={"symbol": str})
    extension["effective_date"] = pd.to_datetime(
        extension["effective_date"], errors="raise"
    )
    appended = extension.loc[
        extension["effective_date"].gt(pd.Timestamp("2020-12-31"))
    ].copy()
    for frame in (old, appended):
        for column in ("as_of_date", "effective_date"):
            frame[column] = pd.to_datetime(frame[column], errors="raise").dt.strftime(
                "%Y-%m-%d"
            )
        frame["symbol"] = frame["symbol"].astype(str).str.zfill(6)
    combined = pd.concat([old, appended], ignore_index=True)
    key = ["as_of_date", "effective_date", "symbol"]
    if combined.duplicated(key).any():
        raise ValueError("reaka_blackbox_append_only_cloudridge_duplicate")
    output = target_root / "append_only_cloudridge_2008_2026.csv"
    combined.to_csv(output, index=False, lineterminator="\n")
    return output


def _prefix_store_checks(
    *,
    tree: str,
    suffix: str,
    store: IntradayK1InputStore,
) -> dict[str, bool]:
    old = IntradayK1InputStore.load(OLD_STORE_ROOT / tree / suffix)
    old_days = len(old.calendar)
    old_symbols = len(old.symbols)
    old_decisions = len(old.exposure_decision_positions)
    checks = {
        "calendar": _arrays_equal(store.calendar[:old_days], old.calendar),
        "symbols": _arrays_equal(store.symbols[:old_symbols], old.symbols),
        "epsilon_history": _arrays_equal(
            store.epsilon_history[:old_days, :old_symbols], old.epsilon_history
        ),
        "epsilon_future": _arrays_equal(
            store.epsilon_future[:old_days, :old_symbols], old.epsilon_future
        ),
        "state_values": _arrays_equal(store.state_values[:, :old_days], old.state_values),
        "state_available": _arrays_equal(store.state_available[:, :old_days], old.state_available),
        "exposure_positions": _arrays_equal(
            store.exposure_decision_positions[:old_decisions], old.exposure_decision_positions
        ),
        "exposures": _arrays_equal(
            store.stock_factor_exposures[:old_decisions, :old_symbols], old.stock_factor_exposures
        ),
        "reliability": _arrays_equal(
            store.exposure_reliability[:old_decisions, :old_symbols], old.exposure_reliability
        ),
        "exposure_available": _arrays_equal(
            store.exposure_available[:old_decisions, :old_symbols], old.exposure_available
        ),
    }
    current_rows = np.asarray(store.inference_rows)
    checks["inference_rows"] = _arrays_equal(
        current_rows[current_rows[:, 2] <= 2020], np.asarray(old.inference_rows)
    )
    return checks


def build_current_scores(
    *,
    tree: str,
    clock: str,
    target: ExtendedTargetSurfaces,
) -> tuple[pd.DataFrame, dict[str, bool]]:
    from scripts.factor_rotation.build_reaka_intraday_portfolio_mapping_inputs_v1 import (
        _ensemble_seed_scores,
    )

    suffix = CLOCK_SUFFIX[clock]
    history_raw, future_raw = _h20_surfaces(
        np.load(target.root / f"decision_close_{suffix}.npy", mmap_mode="r"),
        np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r"),
    )
    extension = EXTENSION_ROOT / tree
    cloudridge = _append_only_cloudridge_path(tree=tree, target_root=target.root)
    core = extension / "condensation/extended_weekly_membership.parquet"
    cloudridge_frame, core_frame, industry_ids = load_memberships(
        cloudridge_path=cloudridge,
        core_path=core,
        registry_path=FACTOR_REGISTRY,
        symbols=target.symbols,
    )
    market_h, _ = old_ot1.materialize_equal_weight_carriers(
        history_raw, target.calendar, cloudridge_frame, [MARKET_FACTOR_ID], minimum_members=12
    )
    market_f, _ = old_ot1.materialize_equal_weight_carriers(
        future_raw, target.calendar, cloudridge_frame, [MARKET_FACTOR_ID], minimum_members=12
    )
    target_order = [SMALL_TARGET_ID, LARGE_TARGET_ID, *industry_ids]
    core_h, _ = old_ot1.materialize_equal_weight_carriers(
        history_raw, target.calendar, core_frame, target_order, minimum_members=5
    )
    core_f, _ = old_ot1.materialize_equal_weight_carriers(
        future_raw, target.calendar, core_frame, target_order, minimum_members=5
    )
    raw_h = np.concatenate([market_h, core_h], axis=2)
    raw_f = np.concatenate([market_f, core_f], axis=2)
    basis_h, basis_f, basis_history, _, _ = build_causal_basis_pair(
        raw_h, raw_f, target.calendar, industry_ids, decision_clock=clock
    )
    memberships = membership_for_decisions(
        core_frame, industry_ids, target.calendar, target.decision_positions
    )
    exposures, industry_exposures, _, epsilon_h, epsilon_f = fit_intraday_stock_exposures(
        history_returns=history_raw,
        future_returns=future_raw,
        decision_marks=np.load(target.root / f"decision_close_{suffix}.npy", mmap_mode="r"),
        history_basis=basis_h,
        future_basis=basis_f,
        calendar=target.calendar,
        symbols=target.symbols,
        decision_positions=target.decision_positions,
        industry_ids=industry_ids,
        industry_membership=memberships,
        decision_clock=clock,
    )
    states = build_selected_states(
        history_basis=basis_history,
        selections=_frozen_selections(tree, suffix),
        decision_clock=clock,
    )
    factor_ids = factor_order(states)
    state_values, state_available = build_state_store(states, target.calendar, factor_ids)
    beta, reliability, exposure_available = build_exposure_store(
        exposures=exposures,
        industry_exposures=industry_exposures,
        calendar=target.calendar,
        symbol_count=len(target.symbols),
        factor_ids=factor_ids,
        decision_positions=target.decision_positions,
    )
    old_store = IntradayK1InputStore.load(OLD_STORE_ROOT / tree / suffix)
    old_days = len(old_store.calendar)
    old_symbols = len(old_store.symbols)
    old_decisions = len(old_store.exposure_decision_positions)
    epsilon_h[:old_days, :old_symbols] = old_store.epsilon_history
    epsilon_f[:old_days, :old_symbols] = old_store.epsilon_future
    state_values[:, :old_days] = old_store.state_values
    state_available[:, :old_days] = old_store.state_available
    beta[:old_decisions, :old_symbols] = old_store.stock_factor_exposures
    reliability[:old_decisions, :old_symbols] = old_store.exposure_reliability
    exposure_available[:old_decisions, :old_symbols] = old_store.exposure_available
    rows, labelled = build_inference_rows(
        calendar=target.calendar,
        epsilon_history=epsilon_h,
        epsilon_future=epsilon_f,
        decision_positions=target.decision_positions,
        exposure_available=exposure_available,
    )
    store = IntradayK1InputStore(
        root=target.root,
        calendar=target.calendar,
        symbols=target.symbols,
        factor_ids=tuple(factor_ids),
        epsilon_history=epsilon_h,
        epsilon_future=epsilon_f,
        state_values=state_values,
        state_available=state_available,
        exposure_decision_positions=target.decision_positions,
        stock_factor_exposures=beta,
        exposure_reliability=reliability,
        exposure_available=exposure_available,
        inference_rows=rows,
        labelled_row_indices=labelled,
    )
    prefix_checks = _prefix_store_checks(tree=tree, suffix=suffix, store=store)
    if not all(prefix_checks.values()):
        failed = [key for key, value in prefix_checks.items() if not value]
        raise ValueError(f"reaka_blackbox_store_prefix_failed:{clock}:" + ",".join(failed))
    years = np.asarray(store.inference_rows[:, 2], dtype=np.int64)
    indices = np.flatnonzero(years >= 2021).astype(np.int64)
    _, frame = _ensemble_seed_scores(
        store=store,
        normalizer=read_json(NORMALIZER_ROOT / suffix / "normalizer.json"),
        checkpoint_root=CHECKPOINT_ROOT / tree / suffix,
        indices=indices,
    )
    frame["decision_clock"] = clock
    frame = frame.loc[
        pd.to_datetime(frame["decision_date"]).between("2021-01-01", "2026-08-25")
    ].sort_values(["decision_date", "symbol"], kind="mergesort", ignore_index=True)
    if frame.empty or frame.duplicated(["decision_date", "decision_clock", "symbol"]).any():
        raise ValueError("reaka_blackbox_score_panel_invalid")
    return frame, prefix_checks


def _load_rules() -> tuple[object, object, object, Path]:
    if str(DATAHUB / "src") not in sys.path:
        sys.path.insert(0, str(DATAHUB / "src"))
    from datahub.core.services.market_standards.cn_a_stock_rules import (  # type: ignore[import-not-found]
        RuleQuery,
        default_cn_a_stock_rule_profile_path,
        load_cn_a_stock_rule_profile,
        resolve_rule,
    )

    path = default_cn_a_stock_rule_profile_path(DATAHUB)
    return load_cn_a_stock_rule_profile(path), RuleQuery, resolve_rule, path


def build_adjustment_factor_matrix(
    *,
    calendar: NDArray[np.datetime64],
    symbols: NDArray[np.str_],
    minimum_day: str = "2020-01-01",
) -> NDArray[np.float64]:
    start = int(np.searchsorted(calendar, np.datetime64(minimum_day, "ns"), side="left"))
    dates = pd.DatetimeIndex(calendar[start:])
    factors = pd.read_parquet(
        ADJUSTMENT_FACTORS,
        columns=["symbol", "trading_day", "price_multiplier"],
        filters=[
            ("instrument_type", "=", "stock"),
            ("factor_type", "=", "hfq"),
            ("trading_day", ">=", minimum_day),
        ],
    )
    factors["symbol"] = factors["symbol"].astype(str).str.zfill(6)
    factors["trading_day"] = pd.to_datetime(factors["trading_day"], errors="raise")
    symbol_map = pd.Series(np.arange(len(symbols), dtype=np.int64), index=symbols)
    date_map = pd.Series(np.arange(len(dates), dtype=np.int64), index=dates)
    factors["symbol_position"] = factors["symbol"].map(symbol_map)
    factors["day_position"] = factors["trading_day"].map(date_map)
    factors = factors.dropna(subset=["symbol_position", "day_position"])
    matrix = np.full((len(dates), len(symbols)), np.nan, dtype=np.float64)
    matrix[
        factors["day_position"].to_numpy(np.int64),
        factors["symbol_position"].to_numpy(np.int64),
    ] = pd.to_numeric(factors["price_multiplier"], errors="raise").to_numpy(np.float64)
    last = np.full(len(symbols), np.nan, dtype=np.float64)
    for position in range(len(matrix)):
        local = matrix[position]
        valid = np.isfinite(local) & (local > 0.0)
        last[valid] = local[valid]
        local[~valid] = last[~valid]
    return matrix


def build_tradability_maps(
    *,
    decision_dates: Sequence[pd.Timestamp],
    calendar: NDArray[np.datetime64],
    symbols: NDArray[np.str_],
    raw_close: NDArray[np.float32],
    raw_execution: NDArray[np.float32],
    factor_matrix: NDArray[np.float64],
    factor_start: int,
) -> dict[pd.Timestamp, dict[str, TradabilityRow]]:
    decisions = {pd.Timestamp(value).normalize() for value in decision_dates}
    metadata_columns = [
        "trading_day",
        "symbol",
        "exchange",
        "board",
        "listing_phase",
        "risk_warning_state",
        "suspension_status",
    ]
    parts: list[pd.DataFrame] = []
    for version in METADATA_VERSIONS:
        path = (
            DATAHUB
            / ".runtime/live/lake/security_day_metadata"
            / f"dataset_version={version}"
            / "security_day_metadata.parquet"
        )
        frame = pd.read_parquet(path, columns=metadata_columns)
        frame["trading_day"] = pd.to_datetime(frame["trading_day"], errors="raise").dt.normalize()
        frame = frame.loc[frame["trading_day"].isin(decisions)]
        frame["symbol"] = frame["symbol"].astype(str).str.zfill(6)
        parts.append(frame)
    metadata = pd.concat(parts, ignore_index=True)
    if metadata.duplicated(["trading_day", "symbol"]).any():
        raise ValueError("reaka_blackbox_metadata_duplicate")
    calendar_index = {pd.Timestamp(value): index for index, value in enumerate(calendar)}
    symbol_index = {str(value): index for index, value in enumerate(symbols)}
    decision_positions = {calendar_index[value] for value in decisions}
    previous: dict[int, NDArray[np.float32]] = {}
    last = np.full(len(symbols), np.nan, dtype=np.float32)
    for day in range(max(decision_positions) + 1):
        if day in decision_positions:
            previous[day] = last.copy()
        close = np.asarray(raw_close[day], dtype=np.float32)
        finite = np.isfinite(close) & (close > 0.0)
        last[finite] = close[finite]
    metadata["day_position"] = metadata["trading_day"].map(calendar_index)
    metadata["symbol_position"] = metadata["symbol"].map(symbol_index)
    metadata = metadata.dropna(subset=["day_position", "symbol_position"])
    metadata["day_position"] = metadata["day_position"].astype(np.int64)
    metadata["symbol_position"] = metadata["symbol_position"].astype(np.int64)
    metadata["risk_for_rules"] = metadata["risk_warning_state"].map(map_risk_warning_for_rules)
    profile, rule_query, resolve_rule, _ = _load_rules()
    cache: dict[tuple[object, ...], dict[str, object]] = {}
    result: dict[pd.Timestamp, dict[str, TradabilityRow]] = {value: {} for value in decisions}
    for row in metadata.itertuples(index=False):
        day = pd.Timestamp(row.trading_day)
        di = int(row.day_position)
        si = int(row.symbol_position)
        risk = str(row.risk_for_rules)
        key = (day.date(), str(row.exchange), str(row.board), risk, str(row.listing_phase))
        if key not in cache:
            query = rule_query(
                family="price_limit",
                on_date=date(day.year, day.month, day.day),
                exchange=str(row.exchange),
                instrument_type="stock",
                board=str(row.board),
                risk_warning_state=None if risk == "unknown" else risk,
                listing_phase=str(row.listing_phase),
            )
            resolved = resolve_rule(profile, query)
            cache[key] = {
                "status": resolved.status,
                "rule_id": resolved.rule_id,
                "gap_id": resolved.gap_id,
                "params": dict(resolved.params),
                "detail": resolved.detail,
            }
        execution = float(raw_execution[di, si])
        previous_close = float(previous[di][si])
        local_factor = factor_matrix[di - factor_start, si] if di >= factor_start else np.nan
        accounting_ready = bool(np.isfinite(local_factor) and local_factor > 0.0)
        gate = eligibility_from_row(
            {"suspension_status": row.suspension_status},
            previous_tradable_close=previous_close if np.isfinite(previous_close) else None,
            open_price=execution if np.isfinite(execution) and execution > 0.0 else None,
            resolved=cache[key],
        )
        result[day][str(row.symbol)] = TradabilityRow(
            symbol=str(row.symbol),
            buy_ok=bool(gate.buy_ok and accounting_ready),
            sell_ok=bool(gate.sell_ok and accounting_ready),
        )
    return result


def run_account_aggregate(
    *,
    score_frame: pd.DataFrame,
    target: ExtendedTargetSurfaces,
    clock: str,
    factor_matrix: NDArray[np.float64],
    slippage_multiplier: float,
    tradability_maps: Mapping[pd.Timestamp, Mapping[str, TradabilityRow]] | None = None,
    raw_close_override: NDArray[np.float32] | None = None,
) -> dict[str, object]:
    suffix = CLOCK_SUFFIX[clock]
    raw_execution = np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r")
    raw_close = (
        raw_close_override
        if raw_close_override is not None
        else np.load(target.root / "raw_close.npy", mmap_mode="r")
    )
    factor_start = int(np.searchsorted(target.calendar, np.datetime64("2020-01-01", "ns"), side="left"))
    decisions = {
        pd.Timestamp(day): rank_portfolio_table(group)
        for day, group in score_frame.groupby("decision_date", sort=True)
    }
    gates = (
        {pd.Timestamp(key): dict(value) for key, value in tradability_maps.items()}
        if tradability_maps is not None
        else build_tradability_maps(
            decision_dates=list(decisions),
            calendar=target.calendar,
            symbols=target.symbols,
            raw_close=raw_close,
            raw_execution=raw_execution,
            factor_matrix=factor_matrix,
            factor_start=factor_start,
        )
    )
    symbol_index = {str(value): index for index, value in enumerate(target.symbols)}
    policy = policy_by_id(COMMON_ROOT_POLICY_ID)
    shares: dict[str, float] = {}
    cash = float(INITIAL_NAV)
    nav = float(INITIAL_NAV)
    previous_marks: dict[str, float] = {}
    returns: list[float] = []
    cash_weights: list[float] = []
    holding_counts: list[int] = []
    rebalance_count = 0
    trade_leg_count = 0
    execution_event_count = 0
    start = int(np.searchsorted(target.calendar, np.datetime64("2021-01-01", "ns"), side="left"))
    for di in range(start, len(target.calendar)):
        day = pd.Timestamp(target.calendar[di])
        previous_nav = nav
        factor = factor_matrix[di - factor_start]
        if day in decisions:
            ranked = decisions[day]
            candidate_symbols = set(ranked["symbol"].astype(str)) | set(shares)
            execution_prices = {
                symbol: float(raw_execution[di, symbol_index[symbol]] * factor[symbol_index[symbol]])
                for symbol in candidate_symbols
                if symbol in symbol_index
                and np.isfinite(raw_execution[di, symbol_index[symbol]])
                and raw_execution[di, symbol_index[symbol]] > 0.0
                and np.isfinite(factor[symbol_index[symbol]])
                and factor[symbol_index[symbol]] > 0.0
            }
            close_prices = {
                symbol: float(raw_close[di, symbol_index[symbol]] * factor[symbol_index[symbol]])
                for symbol in candidate_symbols
                if symbol in symbol_index
                and np.isfinite(raw_close[di, symbol_index[symbol]])
                and raw_close[di, symbol_index[symbol]] > 0.0
                and np.isfinite(factor[symbol_index[symbol]])
                and factor[symbol_index[symbol]] > 0.0
            }
            mark_execution = {
                symbol: execution_prices.get(symbol, previous_marks.get(symbol, float("nan")))
                for symbol in shares
            }
            current_weights, _ = current_weights_from_book(
                shares=shares,
                prices=mark_execution,
                cash=cash,
            )
            target_weights, forced, blocked_buy, events = build_execution_target(
                ranked,
                policy=policy,
                previous_shares=shares,
                current_weights=current_weights,
                tradability=gates.get(day, {}),
                size_labels={},
            )
            result = apply_rebalance_day(
                previous_shares=shares,
                previous_cash=cash,
                open_prices=execution_prices,
                close_prices=close_prices,
                target_weights=target_weights,
                forced_symbols=forced,
                blocked_buy_symbols=blocked_buy,
                previous_mark_prices=previous_marks,
                slippage_multiplier=slippage_multiplier,
            )
            shares = cast(dict[str, float], result["shares"])
            cash = float(result["cash"])
            nav = float(result["close_nav"])
            previous_marks.update(
                cast(Mapping[str, float], result["close_mark_prices"])
            )
            rebalance_count += 1
            execution_event_count += len(events)
            trade_leg_count += len(cast(Mapping[str, float], result["buy_legs"]))
            trade_leg_count += len(cast(Mapping[str, float], result["sell_legs"]))
        else:
            close_prices = {
                symbol: float(raw_close[di, symbol_index[symbol]] * factor[symbol_index[symbol]])
                for symbol in shares
                if symbol in symbol_index
                and np.isfinite(raw_close[di, symbol_index[symbol]])
                and raw_close[di, symbol_index[symbol]] > 0.0
                and np.isfinite(factor[symbol_index[symbol]])
                and factor[symbol_index[symbol]] > 0.0
            }
            nav = apply_non_rebalance_day(
                shares=shares,
                cash=cash,
                close_prices=close_prices,
                previous_mark_prices=previous_marks,
            )
        daily_return = nav / previous_nav - 1.0 if previous_nav > 0.0 else 0.0
        returns.append(daily_return)
        cash_weights.append(cash / nav if nav > 0.0 else 0.0)
        holding_counts.append(len(shares))
        for symbol in shares:
            si = symbol_index[symbol]
            if np.isfinite(raw_close[di, si]) and raw_close[di, si] > 0.0 and np.isfinite(factor[si]):
                previous_marks[symbol] = float(raw_close[di, si] * factor[si])
    metrics = account_metrics(returns)
    return {
        "account_identity": clock,
        "cost_identity": f"slippage_{slippage_multiplier:.1f}x",
        **metrics,
        "mean_cash_weight": float(np.mean(cash_weights)),
        "mean_holding_count": float(np.mean(holding_counts)),
        "rebalance_count": rebalance_count,
        "trade_leg_count": trade_leg_count,
        "execution_event_count": execution_event_count,
    }


def execute_tree(
    *,
    tree: str,
    output_root: Path,
    workers: int = 4,
) -> dict[str, object]:
    if tree not in {"formal", "isolated"}:
        raise ValueError("reaka_blackbox_tree_invalid")
    if output_root.exists():
        raise FileExistsError(output_root)
    contract = load_contract()
    plan = blackbox_plan()
    with tempfile.TemporaryDirectory(prefix=f"reaka_blackbox_{tree}_") as temporary:
        target = build_extended_target_surfaces(
            tree=tree,
            output_root=Path(temporary) / "target",
            workers=workers,
        )
        factor_matrix = build_adjustment_factor_matrix(
            calendar=target.calendar,
            symbols=target.symbols,
        )
        accounts: list[dict[str, object]] = []
        prefix_checks: dict[str, object] = {"target": target.prefix_checks}
        decision_counts: list[int] = []
        for clock in CLOCKS:
            scores, checks = build_current_scores(tree=tree, clock=clock, target=target)
            prefix_checks[clock] = checks
            decision_counts.append(int(scores["decision_date"].nunique()))
            suffix = CLOCK_SUFFIX[clock]
            raw_execution = np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r")
            raw_close = np.load(target.root / "raw_close.npy", mmap_mode="r")
            factor_start = int(
                np.searchsorted(target.calendar, np.datetime64("2020-01-01", "ns"), side="left")
            )
            gates = build_tradability_maps(
                decision_dates=[pd.Timestamp(value) for value in scores["decision_date"].unique()],
                calendar=target.calendar,
                symbols=target.symbols,
                raw_close=raw_close,
                raw_execution=raw_execution,
                factor_matrix=factor_matrix,
                factor_start=factor_start,
            )
            for multiplier in SLIPPAGE_MULTIPLIERS:
                accounts.append(
                    run_account_aggregate(
                        score_frame=scores,
                        target=target,
                        clock=clock,
                        factor_matrix=factor_matrix,
                        slippage_multiplier=multiplier,
                        tradability_maps=gates,
                        raw_close_override=raw_close,
                    )
                )
        result = write_json(
            output_root / "aggregate_result.json",
            {
                "schema_id": "factorlab.reaka_current_generation_aggregate_blackbox_result@1.0",
                "query_id": QUERY_ID,
                "candidate_fingerprint": CANDIDATE_FINGERPRINT,
                "evidence_role": "candidate_specific_first_aggregate_blackbox_on_globally_consumed_interval",
                "detail_state_before": "detail_previously_consumed",
                "detail_state_after": "detail_previously_consumed",
                "aggregate_answer_state_before": "aggregate_unopened",
                "aggregate_answer_state_after": "aggregate_opened_once",
                "interval_start": "2021-01-01",
                "interval_end": "2026-08-25",
                "partial_endpoint": True,
                "trading_day_count": int((target.calendar >= np.datetime64("2021-01-01")).sum()),
                "decision_count": min(decision_counts),
                "attempt_count": len(accounts),
                "accounts": sorted(
                    accounts,
                    key=lambda row: (str(row["account_identity"]), str(row["cost_identity"])),
                ),
                "model_or_parameter_update": False,
                "result_backflow_allowed": False,
                "fresh_oos": False,
                "production_authority": False,
            },
        )
        validate_aggregate_result(result, plan=plan)
        receipt = write_json(
            output_root / "execution_receipt.json",
            {
                "schema_id": "factorlab.reaka_current_generation_aggregate_blackbox_execution@1.0",
                "status": "completed_aggregate_only_repeat_audit",
                "query_id": QUERY_ID,
                "candidate_fingerprint": CANDIDATE_FINGERPRINT,
                "contract_digest": contract["canonical_digest"],
                "plan_digest": plan.semantic_digest(),
                "aggregate_result_digest": result["canonical_digest"],
                "prefix_checks": prefix_checks,
                "temporary_detail_directory_deleted_on_exit": True,
                "source_digests": source_closure(),
                "model_or_parameter_update": False,
                "result_backflow_allowed": False,
                "fresh_oos": False,
                "production_authority": False,
            },
        )
    return receipt


__all__ = [
    "CANDIDATE_FINGERPRINT",
    "CLOCKS",
    "QUERY_ID",
    "SOURCE_FILES",
    "blackbox_plan",
    "build_adjustment_factor_matrix",
    "build_extended_target_surfaces",
    "canonical_valid",
    "execute_tree",
    "file_digest",
    "input_binding_map",
    "load_contract",
    "read_json",
    "run_account_aggregate",
    "source_closure",
    "write_json",
]
