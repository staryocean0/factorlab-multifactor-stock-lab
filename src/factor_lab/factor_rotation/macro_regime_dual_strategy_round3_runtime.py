# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false, reportReturnType=false
# pyright: reportAny=false, reportImplicitStringConcatenation=false
# pyright: reportMissingTypeStubs=false, reportUnusedCallResult=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Outcome-sealed runtime for the Round-3 annual rolling battle.

The runtime deliberately separates three stages:

1. load the already audited FactorLab feature surfaces;
2. load market outcomes only after the external preflight is ``ready``;
3. retain stock-level predictions only in memory and persist annual summaries.

The source feature month is mapped to the following exam month.  Therefore the
December 2020 decision is part of the 2021 exam, while December 2025 is an
unscored 2026 preview.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from numpy.typing import NDArray

from factor_lab.factor_rotation.macro_regime_dual_strategy_round2 import (
    CHALLENGER_STRATEGY_ID,
    INCUMBENT_STRATEGY_ID,
    build_round2_panel,
    compare_paired_monthly,
    evaluate_predictions,
    fit_reaka_challenger,
    fold_indices,
    prediction_frame,
)
from factor_lab.factor_rotation.macro_regime_dual_strategy_round3_battle import (
    CHALLENGER_ARM_ID,
    INCUMBENT_ARM_ID,
    Round3BattleConfig,
    attach_fold_macro_context,
    fit_macro_regime_incumbent,
    round3_result_false_authority,
    seal_round3_result,
    validate_round3_result,
)
from factor_lab.factor_rotation.macro_regime_dual_strategy_round3_execution import (
    COMPLETE_VALIDATION_YEARS,
    ROUND3_EXECUTION_RESULT_SCHEMA_ID,
    ROUND3_EXECUTION_TRIAL_ID,
)
from factor_lab.factor_rotation.macro_regime_dual_strategy_round3_shadow import (
    SHADOW_RESULT_SCHEMA_ID,
    SHADOW_TRIAL_ID,
    build_round3_nonfinancial_shadow_assessment,
    shadow_declared_omission,
    shadow_input_counts,
    validate_round3_nonfinancial_shadow_contract,
    validate_round3_nonfinancial_shadow_preflight,
    validate_round3_nonfinancial_shadow_result,
)
from factor_lab.governance.canonicalization import canonical_digest

_COORDINATE_COLUMNS = (
    "row_id",
    "month_start",
    "decision_date",
    "feature_date",
    "decision_as_of",
    "symbol",
)


@dataclass(frozen=True, slots=True)
class Round3FeatureBundle:
    """Aligned governed stock-input cube and six decision-time contexts."""

    coordinates: pd.DataFrame
    month_dates: NDArray[np.datetime64]
    symbols: NDArray[np.str_]
    factor_ids: tuple[str, ...]
    raw_features: NDArray[np.float32]
    macro_values: pd.DataFrame
    macro_masks: pd.DataFrame
    receipt: dict[str, object]


@dataclass(frozen=True, slots=True)
class Round3TargetBundle:
    """Next-session-open to twentieth-session-close black-box outcomes."""

    targets: NDArray[np.float64]
    target_available_at: NDArray[np.datetime64]
    tradeable: NDArray[np.bool_]
    receipt: dict[str, object]


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return cast(dict[str, object], value)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _string_list(value: object, *, field: str, count: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(f"round3_runtime_{field}_count_mismatch")
    result = tuple(str(item) for item in value)
    if len(set(result)) != count or any(not item for item in result):
        raise ValueError(f"round3_runtime_{field}_identity_invalid")
    return result


def _load_aligned_factor_frame(
    path: Path,
    *,
    expected_row_ids: NDArray[np.int64],
    factor_ids: Sequence[str],
) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=["row_id", *factor_ids])
    row_ids = frame["row_id"].to_numpy(dtype=np.int64)
    if not np.array_equal(row_ids, expected_row_ids):
        raise ValueError(f"round3_runtime_row_id_alignment_mismatch:{path.name}")
    return frame


def _load_round3_feature_bundle(
    input_root: Path | str,
    *,
    include_strict_annual_financial: bool,
) -> Round3FeatureBundle:
    """Load one explicitly declared stock-input variant without outcomes."""

    root = Path(input_root).expanduser().resolve()
    stock_dir = root / "stock_nonfinancial"
    timing_dir = root / "timing_formula"
    finance_dir = root / "strict_annual_financial"
    macro_dir = root / "macro_context"
    required_dirs = (
        (stock_dir, timing_dir, finance_dir, macro_dir) if include_strict_annual_financial else (stock_dir, timing_dir, macro_dir)
    )
    if any(not directory.is_dir() for directory in required_dirs):
        missing = [str(directory) for directory in required_dirs if not directory.is_dir()]
        raise FileNotFoundError("round3_runtime_surface_missing:" + ",".join(missing))

    stock_manifest = _read_json(stock_dir / "manifest.json")
    stock_coverage = _read_json(stock_dir / "coverage_report.json")
    timing_manifest = _read_json(timing_dir / "manifest.json")
    finance_manifest = _read_json(finance_dir / "manifest.json") if include_strict_annual_financial else None
    macro_manifest = _read_json(macro_dir / "manifest.json")
    for name, manifest in (
        ("stock", stock_manifest),
        ("timing", timing_manifest),
        ("macro", macro_manifest),
    ):
        if manifest.get("state") != "READY" or manifest.get("production_authority") is not False:
            raise ValueError(f"round3_runtime_surface_not_research_ready:{name}")
    if include_strict_annual_financial:
        if not isinstance(finance_manifest, Mapping) or (
            finance_manifest.get("state") != "READY" or finance_manifest.get("production_authority") is not False
        ):
            raise ValueError("round3_runtime_surface_not_research_ready:finance")

    stock_ids = _string_list(stock_coverage.get("factor_ids"), field="stock_factor_ids", count=165)
    timing_ids = _string_list(timing_manifest.get("tool_ids"), field="timing_tool_ids", count=7)
    finance_ids = (
        _string_list(
            finance_manifest.get("factor_ids"),
            field="finance_factor_ids",
            count=21,
        )
        if isinstance(finance_manifest, Mapping)
        else ()
    )
    factor_ids = (*stock_ids, *timing_ids, *finance_ids)
    expected_factor_count = 193 if include_strict_annual_financial else 172
    if len(factor_ids) != expected_factor_count or len(set(factor_ids)) != expected_factor_count:
        raise ValueError(f"round3_runtime_exact_{expected_factor_count}_unique_stock_inputs_required")

    coordinates = pd.read_parquet(stock_dir / "coordinates.parquet", columns=list(_COORDINATE_COLUMNS)).sort_values("row_id", kind="stable")
    coordinates = coordinates.reset_index(drop=True)
    row_ids = coordinates["row_id"].to_numpy(dtype=np.int64)
    if not np.array_equal(row_ids, np.arange(len(coordinates), dtype=np.int64)):
        raise ValueError("round3_runtime_coordinate_row_ids_not_dense")
    coordinates["month_start"] = pd.to_datetime(coordinates["month_start"], errors="coerce")
    coordinates["decision_date"] = pd.to_datetime(coordinates["decision_date"], errors="coerce")
    coordinates["symbol"] = coordinates["symbol"].astype(str).str.zfill(6)
    if coordinates[list(_COORDINATE_COLUMNS)].isna().any().any():
        raise ValueError("round3_runtime_coordinate_nulls_forbidden")
    if coordinates.duplicated(["month_start", "symbol"]).any():
        raise ValueError("round3_runtime_duplicate_month_symbol_coordinate")

    stock = _load_aligned_factor_frame(
        stock_dir / "stock_nonfinancial_surface.parquet",
        expected_row_ids=row_ids,
        factor_ids=stock_ids,
    )
    timing = _load_aligned_factor_frame(
        timing_dir / "timing_formula_surface.parquet",
        expected_row_ids=row_ids,
        factor_ids=timing_ids,
    )
    finance = (
        _load_aligned_factor_frame(
            finance_dir / "strict_annual_financial_surface.parquet",
            expected_row_ids=row_ids,
            factor_ids=finance_ids,
        )
        if include_strict_annual_financial
        else None
    )

    source_months = pd.DatetimeIndex(coordinates["month_start"].unique()).sort_values()
    if len(source_months) != 96:
        raise ValueError("round3_runtime_exact_96_source_months_required")
    exam_months = source_months + pd.offsets.MonthBegin(1)
    symbols = np.asarray(sorted(coordinates["symbol"].unique()), dtype=np.str_)
    month_codes = pd.Categorical(coordinates["month_start"], categories=source_months, ordered=True).codes
    symbol_codes = pd.Categorical(coordinates["symbol"], categories=symbols, ordered=True).codes
    if bool(np.any(month_codes < 0) or np.any(symbol_codes < 0)):
        raise ValueError("round3_runtime_coordinate_code_failure")
    raw_features = np.full(
        (len(source_months), len(symbols), len(factor_ids)),
        np.nan,
        dtype=np.float32,
    )
    offset = 0
    factor_frames: list[tuple[pd.DataFrame, tuple[str, ...]]] = [
        (stock, stock_ids),
        (timing, timing_ids),
    ]
    if finance is not None:
        factor_frames.append((finance, finance_ids))
    for frame, ids in factor_frames:
        stop = offset + len(ids)
        raw_features[month_codes, symbol_codes, offset:stop] = frame.loc[:, list(ids)].to_numpy(dtype=np.float32)
        offset = stop

    macro_values = pd.read_parquet(macro_dir / "macro_context_values.parquet")
    macro_masks = pd.read_parquet(macro_dir / "macro_context_masks.parquet")
    macro_source_dates = pd.DatetimeIndex(pd.to_datetime(macro_values["date"], errors="coerce"))
    if not macro_source_dates.equals(source_months):
        raise ValueError("round3_runtime_macro_source_month_alignment_mismatch")
    if not pd.DatetimeIndex(pd.to_datetime(macro_masks["date"])).equals(source_months):
        raise ValueError("round3_runtime_macro_mask_month_alignment_mismatch")
    macro_values = macro_values.copy()
    macro_masks = macro_masks.copy()
    macro_values["date"] = exam_months
    macro_masks["date"] = exam_months

    receipt: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_feature_runtime_receipt.v1",
        "input_root": str(root),
        "coordinate_count": int(len(coordinates)),
        "source_month_count": len(source_months),
        "symbol_count": len(symbols),
        "stock_nonfinancial_factor_count": len(stock_ids),
        "timing_formula_count": len(timing_ids),
        "strict_annual_financial_factor_count": len(finance_ids),
        "stock_level_input_count": len(factor_ids),
        "macro_context_count": int(len(macro_values.columns) - 1),
        "input_variant": (
            "formal_with_strict_annual_financial" if include_strict_annual_financial else "nonfinancial_shadow_declared_ablation"
        ),
        "strict_annual_financial_intentionally_omitted": (not include_strict_annual_financial),
        "feature_to_exam_mapping": "source_decision_month_t_to_exam_month_t_plus_1",
        "first_exam_month": str(exam_months.min())[:10],
        "last_exam_month": str(exam_months.max())[:10],
        "artifact_sha256": {
            "stock_surface": _sha256_file(stock_dir / "stock_nonfinancial_surface.parquet"),
            "timing_surface": _sha256_file(timing_dir / "timing_formula_surface.parquet"),
            "macro_values": _sha256_file(macro_dir / "macro_context_values.parquet"),
            "macro_masks": _sha256_file(macro_dir / "macro_context_masks.parquet"),
        },
        "market_outcome_rows_read": 0,
        "production_authority": False,
    }
    if include_strict_annual_financial:
        cast(dict[str, str], receipt["artifact_sha256"])["financial_surface"] = _sha256_file(
            finance_dir / "strict_annual_financial_surface.parquet"
        )
    receipt["canonical_digest"] = canonical_digest(receipt)
    return Round3FeatureBundle(
        coordinates=coordinates,
        month_dates=exam_months.to_numpy(dtype="datetime64[ns]"),
        symbols=symbols,
        factor_ids=factor_ids,
        raw_features=raw_features,
        macro_values=macro_values,
        macro_masks=macro_masks,
        receipt=receipt,
    )


def load_round3_feature_bundle(input_root: Path | str) -> Round3FeatureBundle:
    """Load the formal exact 165 + 7 + 21 stock-level factor bundle."""

    return _load_round3_feature_bundle(
        input_root,
        include_strict_annual_financial=True,
    )


def load_round3_nonfinancial_shadow_feature_bundle(
    input_root: Path | str,
) -> Round3FeatureBundle:
    """Load the declared 165 + 7 shadow ablation without financial fallback."""

    return _load_round3_feature_bundle(
        input_root,
        include_strict_annual_financial=False,
    )


def build_round3_target_bundle(
    *,
    coordinates: pd.DataFrame,
    month_dates: NDArray[np.datetime64],
    symbols: NDArray[np.str_],
    bars: pd.DataFrame,
    horizon_sessions: int = 20,
) -> Round3TargetBundle:
    """Create a common outcome cube from an already loaded bar frame.

    The entry is the market calendar's first session strictly after the
    decision date.  The exit is that session plus 19 market sessions, making
    it the twentieth future session.  Every coordinate already admitted by
    the decision-time feature surface remains score eligible.  Missing future
    entry/exit bars create a missing label only; they never rewrite that
    historical score universe.
    """

    if horizon_sessions != 20:
        raise ValueError("round3_runtime_horizon_must_remain_20_sessions")
    required_coordinates = {"month_start", "decision_date", "symbol"}
    required_bars = {"symbol", "trading_day", "open", "close"}
    if not required_coordinates.issubset(coordinates.columns):
        raise ValueError("round3_runtime_target_coordinate_columns_missing")
    if not required_bars.issubset(bars.columns):
        raise ValueError("round3_runtime_target_bar_columns_missing")

    coordinate_frame = coordinates.loc[:, ["month_start", "decision_date", "symbol"]].copy()
    coordinate_frame["month_start"] = pd.to_datetime(coordinate_frame["month_start"], errors="coerce")
    coordinate_frame["decision_date"] = pd.to_datetime(coordinate_frame["decision_date"], errors="coerce").dt.normalize()
    coordinate_frame["symbol"] = coordinate_frame["symbol"].astype(str).str.zfill(6)
    source_months = pd.DatetimeIndex(coordinate_frame["month_start"].unique()).sort_values()
    expected_exam_months = (source_months + pd.offsets.MonthBegin(1)).to_numpy(dtype="datetime64[ns]")
    if not np.array_equal(expected_exam_months, month_dates):
        raise ValueError("round3_runtime_target_exam_month_alignment_mismatch")

    decision_counts = coordinate_frame.groupby("month_start", observed=True)["decision_date"].nunique()
    if not decision_counts.eq(1).all():
        raise ValueError("round3_runtime_multiple_decision_dates_per_month")
    decisions = (
        coordinate_frame.loc[:, ["month_start", "decision_date"]]
        .drop_duplicates()
        .sort_values("month_start", kind="stable")
        .reset_index(drop=True)
    )

    bar_frame = bars.loc[:, ["symbol", "trading_day", "open", "close"]].copy()
    bar_frame["symbol"] = bar_frame["symbol"].astype(str).str.zfill(6)
    bar_frame["trading_day"] = pd.to_datetime(bar_frame["trading_day"], errors="coerce").dt.normalize()
    bar_frame["open"] = pd.to_numeric(bar_frame["open"], errors="coerce")
    bar_frame["close"] = pd.to_numeric(bar_frame["close"], errors="coerce")
    bar_frame = bar_frame.dropna(subset=["symbol", "trading_day"])
    if bar_frame.duplicated(["symbol", "trading_day"]).any():
        raise ValueError("round3_runtime_duplicate_symbol_trading_day")
    calendar = pd.DatetimeIndex(bar_frame["trading_day"].unique()).sort_values()
    if calendar.empty:
        raise ValueError("round3_runtime_market_calendar_empty")

    entry_days: list[pd.Timestamp] = []
    exit_days: list[pd.Timestamp] = []
    for decision in decisions["decision_date"]:
        entry_index = int(calendar.searchsorted(pd.Timestamp(decision), side="right"))
        exit_index = entry_index + horizon_sessions - 1
        if entry_index >= len(calendar) or exit_index >= len(calendar):
            raise ValueError(f"round3_runtime_future_sessions_missing:{decision}")
        entry_days.append(pd.Timestamp(calendar[entry_index]))
        exit_days.append(pd.Timestamp(calendar[exit_index]))
    decisions["entry_day"] = entry_days
    decisions["exit_day"] = exit_days
    scheduled = coordinate_frame.merge(
        decisions,
        on=["month_start", "decision_date"],
        how="left",
        validate="many_to_one",
    )

    indexed = bar_frame.set_index(["trading_day", "symbol"], verify_integrity=True)
    entry_key = pd.MultiIndex.from_arrays(
        [scheduled["entry_day"], scheduled["symbol"]],
        names=["trading_day", "symbol"],
    )
    exit_key = pd.MultiIndex.from_arrays(
        [scheduled["exit_day"], scheduled["symbol"]],
        names=["trading_day", "symbol"],
    )
    entry_open = indexed["open"].reindex(entry_key).to_numpy(dtype=np.float64)
    exit_close = indexed["close"].reindex(exit_key).to_numpy(dtype=np.float64)
    valid = np.isfinite(entry_open) & np.isfinite(exit_close) & (entry_open > 0.0) & (exit_close > 0.0)
    returns = np.full(len(scheduled), np.nan, dtype=np.float64)
    returns[valid] = exit_close[valid] / entry_open[valid] - 1.0

    targets = np.full((len(month_dates), len(symbols)), np.nan, dtype=np.float64)
    available = np.full((len(month_dates), len(symbols)), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    # ``tradeable`` is the legacy Round2 field name.  In Round3 it means
    # decision-time score eligibility, which is sealed by ``coordinates`` and
    # therefore cannot depend on future entry/exit outcomes.
    tradeable = np.zeros((len(month_dates), len(symbols)), dtype=np.bool_)
    month_codes = pd.Categorical(scheduled["month_start"], categories=source_months, ordered=True).codes
    symbol_codes = pd.Categorical(scheduled["symbol"], categories=symbols, ordered=True).codes
    if bool(np.any(month_codes < 0) or np.any(symbol_codes < 0)):
        raise ValueError("round3_runtime_target_coordinate_code_failure")
    targets[month_codes, symbol_codes] = returns
    exit_available = (pd.DatetimeIndex(scheduled["exit_day"]) + pd.Timedelta(hours=15)).to_numpy(dtype="datetime64[ns]")
    available[month_codes[valid], symbol_codes[valid]] = exit_available[valid]
    tradeable[month_codes, symbol_codes] = True

    receipt: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_market_outcome_receipt.v1",
        "definition": "first_market_session_after_decision_open_to_20th_market_session_close",
        "horizon_sessions": horizon_sessions,
        "suspension_policy": ("missing_common_calendar_entry_or_exit_bar_yields_missing_label;no_delayed_entry;score_universe_unchanged"),
        "score_universe_policy": "decision_time_coordinates_only;future_outcomes_never_filter_scores",
        "score_universe_depends_on_future_outcome": False,
        "source_bar_row_count": int(len(bar_frame)),
        "coordinate_count": int(len(scheduled)),
        "decision_time_score_eligible_count": int(len(scheduled)),
        "observed_target_count": int(valid.sum()),
        "missing_target_count": int((~valid).sum()),
        "evaluation_missing_label_policy": ("score_ex_ante_then_exclude_missing_label_from_return_diagnostics_only"),
        "evaluation_missing_label_count": int((~valid).sum()),
        "tradeable_target_count": int(len(scheduled)),
        "untradeable_target_count": 0,
        "first_entry_day": str(decisions["entry_day"].min())[:10],
        "last_exit_day": str(decisions["exit_day"].max())[:10],
        "test_year_outcomes_hidden_during_fit": True,
        "stock_level_outcomes_persisted": False,
        "production_authority": False,
    }
    receipt["canonical_digest"] = canonical_digest(receipt)
    return Round3TargetBundle(
        targets=targets,
        target_available_at=available,
        tradeable=tradeable,
        receipt=receipt,
    )


def _bar_paths(bars_root: Path, *, minimum_month: str, maximum_month: str) -> list[Path]:
    paths: list[Path] = []
    for directory in sorted(bars_root.glob("trading_month=????-??")):
        month = directory.name.removeprefix("trading_month=")
        if minimum_month <= month <= maximum_month:
            paths.extend(sorted(directory.glob("part-*.parquet")))
    if not paths:
        raise FileNotFoundError("round3_runtime_stock_bar_partitions_missing")
    return paths


def load_round3_target_bundle(
    *,
    coordinates: pd.DataFrame,
    month_dates: NDArray[np.datetime64],
    symbols: NDArray[np.str_],
    bars_root: Path | str,
) -> Round3TargetBundle:
    """Read only the bar partitions needed by the fixed exam."""

    root = Path(bars_root).expanduser().resolve()
    decisions = pd.to_datetime(coordinates["decision_date"], errors="coerce")
    minimum_day = pd.Timestamp(decisions.min()).normalize() + pd.Timedelta(days=1)
    maximum_day = pd.Timestamp(decisions.max()).normalize() + pd.Timedelta(days=62)
    paths = _bar_paths(
        root,
        minimum_month=minimum_day.strftime("%Y-%m"),
        maximum_month=maximum_day.strftime("%Y-%m"),
    )
    dataset = ds.dataset([str(path) for path in paths], format="parquet")
    predicate = (
        ds.field("symbol").isin(symbols.tolist())
        & (ds.field("trading_day") >= minimum_day.strftime("%Y-%m-%d"))
        & (ds.field("trading_day") <= maximum_day.strftime("%Y-%m-%d"))
    )
    bars = dataset.to_table(columns=["symbol", "trading_day", "open", "close"], filter=predicate).to_pandas()
    bundle = build_round3_target_bundle(
        coordinates=coordinates,
        month_dates=month_dates,
        symbols=symbols,
        bars=bars,
    )
    receipt = dict(bundle.receipt)
    receipt["bars_root"] = str(root)
    receipt["partition_file_count"] = len(paths)
    receipt["partition_file_sha256_digest"] = canonical_digest({str(path): _sha256_file(path) for path in paths})
    receipt.pop("canonical_digest", None)
    receipt["canonical_digest"] = canonical_digest(receipt)
    return Round3TargetBundle(
        targets=bundle.targets,
        target_available_at=bundle.target_available_at,
        tradeable=bundle.tradeable,
        receipt=receipt,
    )


def _fit_receipt(diagnostics: Mapping[str, object], *, seed: int | None) -> dict[str, object]:
    allowed = (
        "fit_kind",
        "input_factor_count",
        "alpha_count",
        "mask_control_count",
        "learned_encoder_alpha_columns",
        "encoder_input_count",
        "mask_can_generate_signal_alone",
        "encoder_observation_normalization",
        "observation_mask_is_alpha_vote",
        "reconstruction_loss_observed_cells_only",
        "missing_value_storage_sentinel",
        "factor_count",
        "train_row_count",
        "test_row_count",
        "train_month_count",
        "regime_count",
        "state_deviation_shrinkage",
        "operator_count",
        "operator_digest",
        "test_outcomes_used_during_fit",
        "full_sample_state_smoothing_used",
        "missing_score_scale_policy",
    )
    receipt = {key: diagnostics[key] for key in allowed if key in diagnostics}
    receipt["seed"] = seed
    receipt["canonical_digest"] = canonical_digest(receipt)
    return receipt


def _winner_from_paired_comparison(comparison: Mapping[str, object]) -> str | None:
    bootstrap = comparison.get("moving_block_bootstrap")
    if not isinstance(bootstrap, Mapping) or bootstrap.get("ci_excludes_zero") is not True:
        return None
    spread_delta = float(cast(float, comparison["challenger_minus_incumbent_mean_monthly_net_spread"]))
    rank_ic_delta = float(cast(float, comparison["challenger_minus_incumbent_mean_rank_ic"]))
    if spread_delta > 0.0 and rank_ic_delta > 0.0:
        return CHALLENGER_STRATEGY_ID
    if spread_delta < 0.0 and rank_ic_delta < 0.0:
        return INCUMBENT_STRATEGY_ID
    return None


def _run_round3_battle_variant(
    *,
    features: Round3FeatureBundle,
    targets: Round3TargetBundle,
    preflight: Mapping[str, object],
    result_contract: Mapping[str, object],
    result_schema_id: str,
    trial_id: str,
    contract_digest_field: str,
    result_finalizer: Callable[[dict[str, object]], None] | None,
    prediction_observer: Callable[[pd.DataFrame, pd.DataFrame], None] | None,
    result_validator: Callable[[Mapping[str, object]], None],
    config: Round3BattleConfig | None = None,
) -> dict[str, object]:
    """Execute one frozen five-fold variant and retain aggregates only."""

    battle_config = config or Round3BattleConfig()
    round2_config = battle_config.round2_config()
    panel = build_round2_panel(
        month_dates=features.month_dates,
        symbols=features.symbols,
        factor_ids=features.factor_ids,
        raw_features=features.raw_features,
        targets=targets.targets,
        target_available_at=targets.target_available_at,
        tradeable=targets.tradeable,
        config=round2_config,
    )
    incumbent_prediction_parts: list[pd.DataFrame] = []
    challenger_prediction_parts: list[pd.DataFrame] = []
    fold_results: list[dict[str, object]] = []
    for year in COMPLETE_VALIDATION_YEARS:
        train_indices, test_indices = fold_indices(panel, validation_year=year)
        train_month_rows = np.zeros(panel.month_dates.size, dtype=np.bool_)
        train_month_rows[np.unique(panel.sample_month_indices[train_indices])] = True
        challenger_panel, scaled_context, scaler_receipt = attach_fold_macro_context(
            panel,
            macro_values=features.macro_values,
            macro_masks=features.macro_masks,
            train_month_rows=train_month_rows,
        )
        incumbent_scores, incumbent_diagnostics = fit_macro_regime_incumbent(
            panel=panel,
            train_indices=train_indices,
            test_indices=test_indices,
            scaled_macro_context=scaled_context,
            config=battle_config,
        )
        seed_results = [
            fit_reaka_challenger(
                panel=challenger_panel,
                train_indices=train_indices,
                test_indices=test_indices,
                config=round2_config,
                seed=seed,
            )
            for seed in battle_config.seeds
        ]
        challenger_scores = np.mean(np.vstack([result.scores for result in seed_results]), axis=0)
        incumbent_predictions = prediction_frame(
            panel,
            sample_indices=test_indices,
            scores=incumbent_scores,
            strategy_id=INCUMBENT_STRATEGY_ID,
            arm_id=INCUMBENT_ARM_ID,
            seed=None,
            validation_year=year,
        )
        challenger_predictions = prediction_frame(
            panel,
            sample_indices=test_indices,
            scores=challenger_scores,
            strategy_id=CHALLENGER_STRATEGY_ID,
            arm_id=CHALLENGER_ARM_ID,
            seed=None,
            validation_year=year,
        )
        incumbent_metrics, _ = evaluate_predictions(incumbent_predictions, config=round2_config)
        challenger_metrics, _ = evaluate_predictions(challenger_predictions, config=round2_config)
        incumbent_prediction_parts.append(incumbent_predictions)
        challenger_prediction_parts.append(challenger_predictions)
        fold_results.append(
            {
                "validation_year": year,
                "train_end": f"{year - 1}-12-31",
                "test_start": f"{year}-01-01",
                "test_end": f"{year}-12-31",
                "train_sample_count": int(len(train_indices)),
                "test_sample_count": int(len(test_indices)),
                "incumbent_annual_metrics": incumbent_metrics,
                "challenger_annual_metrics": challenger_metrics,
                "context_scaler_digest": scaler_receipt["canonical_digest"],
                "incumbent_fit_receipt": _fit_receipt(incumbent_diagnostics, seed=None),
                "challenger_seed_fit_receipts": [
                    _fit_receipt(result.diagnostics, seed=seed) for seed, result in zip(battle_config.seeds, seed_results, strict=True)
                ],
                "test_outcomes_used_during_fit": False,
            }
        )

    incumbent_predictions = pd.concat(incumbent_prediction_parts, ignore_index=True)
    challenger_predictions = pd.concat(challenger_prediction_parts, ignore_index=True)
    incumbent_metrics, incumbent_monthly = evaluate_predictions(incumbent_predictions, config=round2_config)
    challenger_metrics, challenger_monthly = evaluate_predictions(challenger_predictions, config=round2_config)
    if prediction_observer is not None:
        prediction_observer(incumbent_predictions, challenger_predictions)
    paired_comparison = compare_paired_monthly(
        incumbent_monthly,
        challenger_monthly,
        config=round2_config,
    )
    result: dict[str, object] = {
        "schema_id": result_schema_id,
        "trial_id": trial_id,
        "status": "completed",
        "preflight_digest": str(preflight.get("canonical_digest", "")),
        contract_digest_field: str(result_contract.get("canonical_digest", "")),
        "complete_validation_years": list(COMPLETE_VALIDATION_YEARS),
        "fold_results": fold_results,
        "strategy_metrics": [
            {"strategy_id": INCUMBENT_STRATEGY_ID, **incumbent_metrics},
            {"strategy_id": CHALLENGER_STRATEGY_ID, **challenger_metrics},
        ],
        "paired_comparison": paired_comparison,
        "winner_strategy_id": _winner_from_paired_comparison(paired_comparison),
        "winner_rule": ("paired_spread_block_bootstrap_ci_excludes_zero_and_rank_ic_delta_has_same_direction;otherwise_no_winner"),
        "incomplete_preview_year": 2026,
        "incomplete_preview_scored": False,
        "battle_config": battle_config.as_dict(),
        "feature_receipt": features.receipt,
        "market_outcome_receipt": targets.receipt,
        "market_black_box_policy": {
            "test_year_outcomes_hidden_during_fit": True,
            "test_year_drilldown_persisted": False,
            "only_annual_and_paired_aggregate_metrics_persisted": True,
        },
        "missing_data_contract": {
            "missing_value_storage_sentinel": 0.0,
            "observation_mask_control_count_equals_reaka_alpha_count": True,
            "observation_mask_is_alpha_vote": False,
            "observation_mask_can_generate_signal_alone": False,
            "reaka_encoder_observation_normalization": ("sqrt_alpha_count_over_observed_count_after_mask_gating"),
            "reaka_reconstruction_loss_observed_cells_only": True,
            "incumbent_score_scale": "per_stock_observed_absolute_weight_mass",
            "future_outcome_filters_scoring_universe": False,
        },
        "authority": round3_result_false_authority(),
    }
    if result_finalizer is not None:
        result_finalizer(result)
    seal_round3_result(result)
    result_validator(result)
    return result


def run_round3_battle(
    *,
    features: Round3FeatureBundle,
    targets: Round3TargetBundle,
    preflight: Mapping[str, object],
    annual_contract: Mapping[str, object],
    config: Round3BattleConfig | None = None,
) -> dict[str, object]:
    """Execute the formal five-fold battle with all 193 stock inputs."""

    return _run_round3_battle_variant(
        features=features,
        targets=targets,
        preflight=preflight,
        result_contract=annual_contract,
        result_schema_id=ROUND3_EXECUTION_RESULT_SCHEMA_ID,
        trial_id=ROUND3_EXECUTION_TRIAL_ID,
        contract_digest_field="annual_contract_digest",
        result_finalizer=None,
        prediction_observer=None,
        result_validator=validate_round3_result,
        config=config,
    )


def run_round3_nonfinancial_shadow_battle(
    *,
    features: Round3FeatureBundle,
    targets: Round3TargetBundle,
    preflight: Mapping[str, object],
    shadow_contract: Mapping[str, object],
    prediction_observer: Callable[[pd.DataFrame, pd.DataFrame], None] | None = None,
    config: Round3BattleConfig | None = None,
) -> dict[str, object]:
    """Run the declared finance-absent shadow without formal replacement power."""

    validate_round3_nonfinancial_shadow_preflight(preflight)
    validate_round3_nonfinancial_shadow_contract(shadow_contract)
    if features.receipt.get("input_variant") != ("nonfinancial_shadow_declared_ablation"):
        raise ValueError("round3_shadow_requires_nonfinancial_feature_bundle")

    def finalize(result: dict[str, object]) -> None:
        result["parent_formal_trial_id"] = ROUND3_EXECUTION_TRIAL_ID
        result["input_counts"] = shadow_input_counts()
        result["declared_input_omission"] = shadow_declared_omission()
        result["replacement_assessment"] = build_round3_nonfinancial_shadow_assessment(result)

    return _run_round3_battle_variant(
        features=features,
        targets=targets,
        preflight=preflight,
        result_contract=shadow_contract,
        result_schema_id=SHADOW_RESULT_SCHEMA_ID,
        trial_id=SHADOW_TRIAL_ID,
        contract_digest_field="shadow_contract_digest",
        result_finalizer=finalize,
        prediction_observer=prediction_observer,
        result_validator=validate_round3_nonfinancial_shadow_result,
        config=config,
    )


__all__ = [
    "Round3FeatureBundle",
    "Round3TargetBundle",
    "build_round3_target_bundle",
    "load_round3_feature_bundle",
    "load_round3_nonfinancial_shadow_feature_bundle",
    "load_round3_target_bundle",
    "run_round3_battle",
    "run_round3_nonfinancial_shadow_battle",
]
