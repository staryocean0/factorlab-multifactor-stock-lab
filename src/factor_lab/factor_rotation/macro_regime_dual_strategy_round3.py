"""Round-3 readiness contracts for the incumbent-versus-REAKA programme.

This module does not run the battle.  It freezes the source-lineage repair,
timing-feature semantics, context-consumer boundary, and the strict-PIT gate
that must all pass before formal Round-3 observations may be read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

import pandas as pd

from factor_lab.governance.canonicalization import canonical_digest

ROUND3_READINESS_SCHEMA_ID: Final = "macro_regime_dual_strategy_round3_readiness@1.0"
ROUND3_READINESS_ARTIFACT_TYPE: Final = "macro_regime_dual_strategy_round3_readiness"
ROUND3_TRIAL_ID: Final = "macro_regime_v1_vs_reaka_v1_round3_strict_pit_prospective"
ROUND3_ITERATION_ID: Final = "macro_regime_dual_strategy_round3"

REGISTERED_CANDIDATE_COUNT: Final = 310
STOCK_FACTOR_COUNT: Final = 205
TIMING_CANDIDATE_COUNT: Final = 20
CONTEXT_CANDIDATE_COUNT: Final = 70

STRICT_FINANCIAL_DATASET_VERSION: Final = "cn_a_financial_pit_first_release_annual_semi_2009_2021.v71.20260731"

INDUSTRY_FACTOR_IDS: Final[tuple[str, ...]] = (
    "industry_idiovol_120d_lag1",
    "industry_idiovol_60d_lag1",
    "industry_index_reversal_10d_lag1",
    "industry_index_volatility_120d_lag1",
    "industry_low_beta_60d_lag1",
    "industry_relative_reversal_120d_lag1",
    "industry_relative_reversal_20d_lag1",
    "industry_relative_reversal_250d_lag1",
    "industry_relative_reversal_5d_lag1",
    "industry_relative_reversal_60d_lag1",
    "industry_reversal_20d_lag1",
    "industry_reversal_60d_lag1",
    "industry_volatility_60d_lag1",
)

MISSING_STOCK_FACTOR_IDS: Final[tuple[str, ...]] = (
    "cash_flow_quality_lag1",
    "illiquidity_volume_120d_lag1",
    "illiquidity_volume_250d_lag1",
)

_FALSE_AUTHORITY: Final[dict[str, bool]] = {
    "asset_selection_allowed": False,
    "individual_stock_scoring_allowed": False,
    "portfolio_construction_allowed": False,
    "portfolio_execution": False,
    "holdings_created": False,
    "orders_created": False,
    "production_authority": False,
}

_DUPLICATE_LINEAGE_ROWS: Final[tuple[dict[str, object], ...]] = (
    {
        "factor_id": "amihud_illiquidity_60d_lag1",
        "duplicate_family": "p3a_reappended_by_p4d",
        "pre_resolution_duplicate_key_group_count": 115_809,
        "pre_resolution_conflicting_value_group_count": 0,
        "selected_source_ref": "output/factor-rotation/new_factors_p3a_20260702/p3a_factor_exposure.parquet",
        "excluded_source_ref": "output/factor-rotation/new_factors_p4d_20260702/p4d_factor_exposure.parquet",
        "resolution_rule": "select_original_p3a_source_and_exclude_reappended_p4d_rows",
    },
    {
        "factor_id": "amihud_illiquidity_120d_lag1",
        "duplicate_family": "p3a_reappended_by_p4d",
        "pre_resolution_duplicate_key_group_count": 108_682,
        "pre_resolution_conflicting_value_group_count": 0,
        "selected_source_ref": "output/factor-rotation/new_factors_p3a_20260702/p3a_factor_exposure.parquet",
        "excluded_source_ref": "output/factor-rotation/new_factors_p4d_20260702/p4d_factor_exposure.parquet",
        "resolution_rule": "select_original_p3a_source_and_exclude_reappended_p4d_rows",
    },
    {
        "factor_id": "amount_price_corr_120d_lag1",
        "duplicate_family": "p3a_reappended_by_p4d",
        "pre_resolution_duplicate_key_group_count": 108_682,
        "pre_resolution_conflicting_value_group_count": 0,
        "selected_source_ref": "output/factor-rotation/new_factors_p3a_20260702/p3a_factor_exposure.parquet",
        "excluded_source_ref": "output/factor-rotation/new_factors_p4d_20260702/p4d_factor_exposure.parquet",
        "resolution_rule": "select_original_p3a_source_and_exclude_reappended_p4d_rows",
    },
    {
        "factor_id": "volume_price_corr_120d_lag1",
        "duplicate_family": "p3a_reappended_by_p4d",
        "pre_resolution_duplicate_key_group_count": 108_682,
        "pre_resolution_conflicting_value_group_count": 0,
        "selected_source_ref": "output/factor-rotation/new_factors_p3a_20260702/p3a_factor_exposure.parquet",
        "excluded_source_ref": "output/factor-rotation/new_factors_p4d_20260702/p4d_factor_exposure.parquet",
        "resolution_rule": "select_original_p3a_source_and_exclude_reappended_p4d_rows",
    },
    {
        "factor_id": "reversal_120d_lag1",
        "duplicate_family": "price_style_identity_collision",
        "pre_resolution_duplicate_key_group_count": 90_561,
        "pre_resolution_conflicting_value_group_count": 90_561,
        "selected_source_ref": "output/factor-rotation/style_matrix_20260701/batch_6/style_batch_exposure.parquet",
        "excluded_source_ref": "legacy_price_volume_reversal_120d_source",
        "resolution_rule": "select_style_batch6_final_replacement_and_exclude_price_volume_identity",
    },
    {
        "factor_id": "earnings_quality_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 765,
        "pre_resolution_conflicting_value_group_count": 763,
        "selected_source_ref": "legacy_statement_recompute_with_report_period",
    },
    {
        "factor_id": "operating_margin_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 764,
        "pre_resolution_conflicting_value_group_count": 760,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_5/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "profit_margin_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 764,
        "pre_resolution_conflicting_value_group_count": 757,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_1/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "margin_acceleration_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 730,
        "pre_resolution_conflicting_value_group_count": 729,
        "selected_source_ref": "output/factor-rotation/new_factors_p1_20260702/p1_factor_exposure.parquet",
    },
    {
        "factor_id": "accruals_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 718,
        "pre_resolution_conflicting_value_group_count": 718,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_5/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "cash_flow_to_assets_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 718,
        "pre_resolution_conflicting_value_group_count": 718,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_4/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "roa_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 718,
        "pre_resolution_conflicting_value_group_count": 717,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_1/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "cash_flow_roe_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 717,
        "pre_resolution_conflicting_value_group_count": 716,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_5/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "cashflow_to_debt_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 717,
        "pre_resolution_conflicting_value_group_count": 715,
        "selected_source_ref": "legacy_statement_recompute_with_report_period",
    },
    {
        "factor_id": "net_profit_to_debt_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 717,
        "pre_resolution_conflicting_value_group_count": 715,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_7/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "fundamental_quality_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 717,
        "pre_resolution_conflicting_value_group_count": 714,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_8/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "roic_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 717,
        "pre_resolution_conflicting_value_group_count": 714,
        "selected_source_ref": "legacy_statement_recompute_with_report_period",
    },
    {
        "factor_id": "asset_turnover_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 717,
        "pre_resolution_conflicting_value_group_count": 713,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_2/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "net_profit_growth_yoy",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 713,
        "pre_resolution_conflicting_value_group_count": 712,
        "selected_source_ref": "output/factor-rotation/new_factors_p0_20260702/p0_factor_exposure.parquet",
    },
    {
        "factor_id": "equity_turnover_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 716,
        "pre_resolution_conflicting_value_group_count": 710,
        "selected_source_ref": "output/factor-rotation/fundamental_matrix_20260701/batch_6/fundamental_batch_exposure.parquet",
    },
    {
        "factor_id": "asset_turnover_stability_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 698,
        "pre_resolution_conflicting_value_group_count": 682,
        "selected_source_ref": "legacy_statement_recompute_with_report_period",
    },
    {
        "factor_id": "revenue_trend_3q_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 715,
        "pre_resolution_conflicting_value_group_count": 660,
        "selected_source_ref": "output/factor-rotation/new_factors_p1_20260702/p1_factor_exposure.parquet",
    },
    {
        "factor_id": "equity_growth_yoy",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 623,
        "pre_resolution_conflicting_value_group_count": 614,
        "selected_source_ref": "output/factor-rotation/new_factors_p0_20260702/p0_factor_exposure.parquet",
    },
    {
        "factor_id": "assets_growth_yoy",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 623,
        "pre_resolution_conflicting_value_group_count": 613,
        "selected_source_ref": "output/factor-rotation/new_factors_p0_20260702/p0_factor_exposure.parquet",
    },
    {
        "factor_id": "roe_improvement_count_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 719,
        "pre_resolution_conflicting_value_group_count": 218,
        "selected_source_ref": "output/factor-rotation/new_factors_p1_20260702/p1_factor_exposure.parquet",
    },
    {
        "factor_id": "earnings_consistency_lag1",
        "duplicate_family": "same_announcement_multiple_report_periods",
        "pre_resolution_duplicate_key_group_count": 719,
        "pre_resolution_conflicting_value_group_count": 104,
        "selected_source_ref": "output/factor-rotation/new_factors_p1_20260702/p1_factor_exposure.parquet",
    },
)

_TIMING_PARAMETER_SPECS: Final[dict[str, dict[str, object]]] = {
    "bollinger_volatility_channel": {
        "frequency": "1d",
        "parameters": {"window_bars": 20, "width_sigma": 2.0},
        "parameter_status": "certified_fixed_daily",
        "disposition": "formula_ready_daily",
    },
    "butterworth_clean_bandpass": {
        "frequency": "1d",
        "parameters": {"short_period_bars": 28, "long_period_bars": 57, "order": 4},
        "parameter_status": "certified_fixed_daily",
        "disposition": "formula_ready_daily",
    },
    "butterworth_lowpass_residual_envelope": {
        "frequency": "15m",
        "parameters": {
            "cutoff_period_bars": 96,
            "lowpass_order": 4,
            "thickness_lower_quantile": 0.1,
            "thickness_upper_quantile": 0.9,
            "thickness_smoothing_half_life_bars": 6.0,
            "thickness_window_bars": 64,
            "warmup_bars": 512,
        },
        "parameter_status": "certified_fixed_intraday_only",
        "disposition": "deferred_intraday_only",
    },
    "causal_haar_wavelet_bandpass": {
        "frequency": "1d",
        "parameters": {"level": 2, "slow_level": 5, "window_bars": 128},
        "parameter_status": "certified_fixed_daily",
        "disposition": "formula_ready_daily",
    },
    "donchian_price_channel": {
        "frequency": "1d",
        "parameters": {"entry_window_bars": 20, "exit_window_bars": 10},
        "parameter_status": "certified_fixed_daily",
        "disposition": "formula_ready_daily",
    },
    "frequency_selective_bollinger_channel": {
        "frequency": "15m",
        "parameters": {
            "action": "trend_breakout",
            "filter_order": 2,
            "period_bars": 48,
            "thickness_source": "bandpass",
            "width_multiplier": 1.0,
            "window_multiplier": 2.0,
        },
        "parameter_status": "certified_fixed_intraday_only",
        "disposition": "deferred_intraday_only",
    },
    "laplace_iir_mixed_bandpass": {
        "frequency": "1d",
        "parameters": {"period_bars": 40, "q": 1.0},
        "parameter_status": "certified_fixed_daily",
        "disposition": "formula_ready_daily",
    },
    "r3_nested_moving_average_component": {
        "frequency": "1d",
        "parameters": {"fast_window_bars": 2, "slow_window_bars": 16},
        "parameter_status": "certified_fixed_daily",
        "disposition": "formula_ready_daily",
    },
    "simple_moving_average_trend": {
        "frequency": "1d",
        "parameters": {"fast_window_bars": 10, "slow_window_bars": 30},
        "parameter_status": "certified_fixed_daily",
        "disposition": "formula_ready_daily",
    },
    "fda_explosive_lifecycle_continuous_primitives": {
        "frequency": "1d",
        "parameters": {"features": ["lagged_speed", "lagged_acceleration", "completed_down_leg_age"]},
        "parameter_status": "historical_composite_spec",
        "disposition": "deferred_composite_materializer",
    },
    "p48_p96_channel_continuous_primitives": {
        "frequency": "1d",
        "parameters": {"period_bars": [48, 96], "rails": "prior_outer_rails_only"},
        "parameter_status": "historical_composite_spec",
        "disposition": "deferred_composite_materializer",
    },
    "causal_asymmetric_arc_state_space_envelope": {
        "frequency": "15m",
        "parameters": {"candidate_period_bars": [64, 128, 256, 512]},
        "parameter_status": "rejected_descriptive_baseline",
        "disposition": "deferred_unvalidated_or_rejected",
    },
    "causal_trendline_channel": {
        "frequency": "1d",
        "parameters": {"window_bars": 40, "rail_sigma": 1.5},
        "parameter_status": "rejected_descriptive_baseline",
        "disposition": "deferred_unvalidated_or_rejected",
    },
    "laplace_iir_lowpass": {
        "frequency": "1d",
        "parameters": {"period_bars": 75, "q": 1.0},
        "parameter_status": "rejected_descriptive_baseline",
        "disposition": "deferred_unvalidated_or_rejected",
    },
    "rolling_fourier_bandpass": {
        "frequency": "1d",
        "parameters": {"window_bars": 256, "low_period_bars": 20, "high_period_bars": 80},
        "parameter_status": "rejected_descriptive_baseline",
        "disposition": "deferred_unvalidated_or_rejected",
    },
    "donchian_breakout_margin": {
        "frequency": "1d",
        "parameters": {"inherits": "donchian_price_channel"},
        "parameter_status": "registered_derived_from_certified_daily",
        "disposition": "formula_ready_daily",
    },
    "frequency_channel_position": {
        "frequency": "15m",
        "parameters": {"inherits": "frequency_selective_bollinger_channel"},
        "parameter_status": "registered_derived_from_certified_intraday_only",
        "disposition": "deferred_intraday_only",
    },
    "haar_component_delta": {
        "frequency": "1d",
        "parameters": {"inherits": "causal_haar_wavelet_bandpass"},
        "parameter_status": "registered_derived_from_certified_daily",
        "disposition": "formula_ready_daily",
    },
    "r3_component_delta": {
        "frequency": "1d",
        "parameters": {"inherits": "r3_nested_moving_average_component"},
        "parameter_status": "registered_derived_from_certified_daily",
        "disposition": "formula_ready_daily",
    },
    "tool14_multiscale_persistence": {
        "frequency": "1d",
        "parameters": {"feature_set": ["lagged_scale_agreement", "lagged_scale_disagreement", "train_only_realisation_discount"]},
        "parameter_status": "registered_hypothesis_without_fixed_parameter",
        "disposition": "deferred_unfrozen_parameters",
    },
}


def round3_false_authority() -> dict[str, bool]:
    """Return a fresh all-false authority object."""

    return dict(_FALSE_AUTHORITY)


def build_duplicate_lineage_contract() -> list[dict[str, object]]:
    """Freeze the one-source-per-factor repair for all 26 ambiguous identities."""

    rows: list[dict[str, object]] = []
    for source in _DUPLICATE_LINEAGE_ROWS:
        row = dict(source)
        if row["duplicate_family"] == "same_announcement_multiple_report_periods":
            row.setdefault("excluded_source_ref", "legacy_combined_exposure_without_report_period")
            row.setdefault(
                "resolution_rule",
                "carry_report_period_then_select_latest_report_period_per_date_symbol_factor",
            )
        row["post_resolution_duplicate_key_group_count"] = 0
        row["post_resolution_conflicting_value_group_count"] = 0
        row["production_authority"] = False
        rows.append(row)
    validate_duplicate_lineage_contract(rows)
    return rows


def validate_duplicate_lineage_contract(rows: Sequence[Mapping[str, object]]) -> None:
    """Fail closed if the frozen duplicate forensics or repair rules drift."""

    if len(rows) != 26:
        raise ValueError("round3_duplicate_lineage_expected_26_factor_identities")
    factor_ids = [str(row.get("factor_id", "")) for row in rows]
    if "" in factor_ids or len(factor_ids) != len(set(factor_ids)):
        raise ValueError("round3_duplicate_lineage_factor_ids_must_be_unique_nonempty")
    duplicate_values = [row.get("pre_resolution_duplicate_key_group_count") for row in rows]
    conflict_values = [row.get("pre_resolution_conflicting_value_group_count") for row in rows]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in [*duplicate_values, *conflict_values]):
        raise ValueError("round3_duplicate_lineage_counts_must_be_integers")
    duplicate_groups = sum(cast(int, value) for value in duplicate_values)
    conflict_groups = sum(cast(int, value) for value in conflict_values)
    if duplicate_groups != 547_421:
        raise ValueError(f"round3_duplicate_group_forensics_drift:{duplicate_groups}")
    if conflict_groups != 104_323:
        raise ValueError(f"round3_conflict_group_forensics_drift:{conflict_groups}")
    for row in rows:
        if not str(row.get("selected_source_ref", "")).strip() or not str(row.get("resolution_rule", "")).strip():
            raise ValueError(f"round3_duplicate_source_rule_missing:{row.get('factor_id', '')}")
        if row.get("post_resolution_duplicate_key_group_count") != 0:
            raise ValueError(f"round3_duplicate_not_resolved:{row.get('factor_id', '')}")
        if row.get("post_resolution_conflicting_value_group_count") != 0:
            raise ValueError(f"round3_conflict_not_resolved:{row.get('factor_id', '')}")
        if row.get("production_authority") is not False:
            raise ValueError(f"round3_duplicate_lineage_false_authority_required:{row.get('factor_id', '')}")


def resolve_latest_report_period(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """Resolve same-day financial releases by the latest fiscal report period.

    Exact repeats at the winning report period are collapsed.  Conflicting rows
    at that same winning period are rejected because report-period ordering no
    longer provides an economic rule for choosing between them.
    """

    required = {"date", "symbol", "factor_id", "factor_value", "available_at", "report_period"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"round3_report_period_columns_missing:{','.join(missing)}")
    work = frame.loc[:, sorted(required)].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["available_at"] = pd.to_datetime(work["available_at"], errors="coerce")
    work["report_period"] = pd.to_datetime(work["report_period"], errors="coerce")
    work["symbol"] = work["symbol"].astype(str).str.zfill(6)
    work["factor_id"] = work["factor_id"].astype(str)
    work["factor_value"] = pd.to_numeric(work["factor_value"], errors="coerce")
    if work[list(required)].isna().any().any():
        raise ValueError("round3_report_period_rows_must_be_complete")
    if (work["available_at"] > work["date"]).any():
        raise ValueError("round3_financial_value_available_after_decision")

    keys = ["date", "symbol", "factor_id"]
    duplicate_group_count = int((work.groupby(keys, sort=False).size() > 1).sum())
    selected_period = work.groupby(keys, sort=False)["report_period"].transform("max")
    latest = work.loc[work["report_period"].eq(selected_period)].copy()
    winning_keys = [*keys, "report_period"]
    conflict = latest.groupby(winning_keys, sort=False).agg(
        value_count=("factor_value", "nunique"),
        availability_count=("available_at", "nunique"),
    )
    bad = conflict.loc[(conflict["value_count"] > 1) | (conflict["availability_count"] > 1)]
    if not bad.empty:
        raise ValueError(f"round3_latest_report_period_still_conflicting:{len(bad)}")
    resolved = latest.drop_duplicates(winning_keys, keep="last").drop(columns=["report_period"])
    resolved = resolved.sort_values(keys, kind="stable").reset_index(drop=True)
    if resolved.duplicated(keys).any():
        raise ValueError("round3_report_period_resolution_left_duplicate_keys")
    audit: dict[str, object] = {
        "input_row_count": int(len(work)),
        "pre_resolution_duplicate_key_group_count": duplicate_group_count,
        "output_row_count": int(len(resolved)),
        "dropped_row_count": int(len(work) - len(resolved)),
        "post_resolution_duplicate_key_group_count": 0,
        "post_resolution_conflicting_value_group_count": 0,
        "resolution_rule": "latest_report_period_per_date_symbol_factor_then_collapse_exact_repeats",
        "production_authority": False,
    }
    return resolved, audit


def build_timing_candidate_contract(registry: Mapping[str, object]) -> dict[str, object]:
    """Freeze stock-level semantics and dispositions for all 20 timing identities."""

    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("round3_recovered_registry_candidates_required")
    timing_rows = [
        cast(Mapping[str, object], row)
        for row in raw_candidates
        if isinstance(row, Mapping) and str(row.get("source_lane", "")).startswith("timing")
    ]
    rows: list[dict[str, object]] = []
    for source in sorted(timing_rows, key=lambda item: str(item.get("candidate_id", ""))):
        factor_id = str(source.get("source_factor_id", ""))
        parameter_spec = _TIMING_PARAMETER_SPECS.get(factor_id)
        if parameter_spec is None:
            raise ValueError(f"round3_timing_parameter_spec_missing:{factor_id}")
        disposition = str(parameter_spec["disposition"])
        defer_reason = ""
        if disposition == "deferred_intraday_only":
            defer_reason = "no_certified_daily_parameter_for_daily_stock_cross_section"
        elif disposition == "deferred_composite_materializer":
            defer_reason = "atomic_daily_stock_formula_not_yet_materialized"
        elif disposition == "deferred_unvalidated_or_rejected":
            defer_reason = "historical_parameter_was_rejected_or_lacks_capability_certificate"
        elif disposition == "deferred_unfrozen_parameters":
            defer_reason = "fixed_multiscale_parameter_contract_missing"
        row: dict[str, object] = {
            "candidate_id": str(source.get("candidate_id", "")),
            "source_factor_id": factor_id,
            "source_lane": str(source.get("source_lane", "")),
            "tool_or_parent_id": str(source.get("legacy_membership", "")),
            "mechanism_family": str(source.get("mechanism_family", "")),
            "formula_summary": str(source.get("formula_summary", "")),
            "input_contract": "per_stock_adjusted_ohlcv_closed_bar_t_only",
            "decision_clock": "official_session_close_t",
            "earliest_action": "next_executable_open_t_plus_one",
            "frequency": parameter_spec["frequency"],
            "parameters": dict(cast(Mapping[str, object], parameter_spec["parameters"])),
            "parameter_status": str(parameter_spec["parameter_status"]),
            "round3_disposition": disposition,
            "defer_reason": defer_reason,
            "mechanism_vote_key": str(source.get("mechanism_family", "")),
            "direct_vote_count": 1 if disposition == "formula_ready_daily" else 0,
            "prohibited_inputs": [
                "current_or_future_tool_profit",
                "historical_cagr_as_predictor",
                "winner_label",
                "future_rail_or_component",
                "component_sign_without_delta",
                "zero_crossing",
                "phase_peak",
            ],
            "production_authority": False,
        }
        rows.append(row)
    payload: dict[str, object] = {
        "artifact_type": "macro_regime_dual_strategy_round3_timing_candidate_contract",
        "contract_version": "round3_timing_stock_transform@1.0",
        "candidate_count": len(rows),
        "candidates": rows,
        "normalization_contract": {
            "raw_stage": "causal_continuous_transform_per_stock_without_future_suffix",
            "cross_section_stage": "within_date_median_mad_clip_plus_or_minus_5_then_percentile_rank_to_minus1_plus1",
            "missing_policy": "explicit_observation_mask_never_zero_fill",
            "minimum_cross_section_observations": 50,
            "fit_policy": "no_full_sample_fit;any_learned_discount_uses_expanding_train_prefix_only",
        },
        "multiplicity_contract": {
            "vote_unit": "mechanism_family",
            "max_votes_per_mechanism_family": 1,
            "aliases_and_overlapping_tools_do_not_multiply_votes": True,
        },
        "authority": round3_false_authority(),
    }
    payload["canonical_digest"] = canonical_digest(payload)
    validate_timing_candidate_contract(payload)
    return payload


def validate_timing_candidate_contract(payload: Mapping[str, object]) -> None:
    """Validate timing identity, causality, normalization, and disposition coverage."""

    rows = payload.get("candidates")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("round3_timing_candidates_array_required")
    candidate_rows = cast(list[Mapping[str, object]], rows)
    if payload.get("candidate_count") != TIMING_CANDIDATE_COUNT or len(candidate_rows) != TIMING_CANDIDATE_COUNT:
        raise ValueError("round3_timing_candidate_count_must_equal_20")
    factor_ids = [str(row.get("source_factor_id", "")) for row in candidate_rows]
    if set(factor_ids) != set(_TIMING_PARAMETER_SPECS) or len(factor_ids) != len(set(factor_ids)):
        raise ValueError("round3_timing_factor_identity_drift")
    allowed = {
        "formula_ready_daily",
        "deferred_intraday_only",
        "deferred_composite_materializer",
        "deferred_unvalidated_or_rejected",
        "deferred_unfrozen_parameters",
    }
    for row in candidate_rows:
        disposition = str(row.get("round3_disposition", ""))
        if disposition not in allowed:
            raise ValueError(f"round3_timing_disposition_invalid:{row.get('source_factor_id', '')}")
        if disposition != "formula_ready_daily" and not str(row.get("defer_reason", "")).strip():
            raise ValueError(f"round3_timing_defer_reason_required:{row.get('source_factor_id', '')}")
        prohibited = row.get("prohibited_inputs")
        if not isinstance(prohibited, list) or "current_or_future_tool_profit" not in prohibited:
            raise ValueError(f"round3_timing_profit_prohibition_required:{row.get('source_factor_id', '')}")
        if row.get("production_authority") is not False:
            raise ValueError(f"round3_timing_false_authority_required:{row.get('source_factor_id', '')}")
    normalization = payload.get("normalization_contract")
    if not isinstance(normalization, Mapping) or normalization.get("missing_policy") != "explicit_observation_mask_never_zero_fill":
        raise ValueError("round3_timing_missing_mask_contract_required")
    multiplicity = payload.get("multiplicity_contract")
    if not isinstance(multiplicity, Mapping) or multiplicity.get("max_votes_per_mechanism_family") != 1:
        raise ValueError("round3_timing_one_mechanism_one_vote_required")
    _validate_all_false_authority(payload.get("authority"), "round3_timing")
    _validate_digest(payload)


def build_context_consumer_contract(
    registry: Mapping[str, object],
    *,
    source_by_factor: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Connect all 70 context identities without broadcasting them as stock alpha."""

    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("round3_recovered_registry_candidates_required")
    context_rows = [
        cast(Mapping[str, object], row)
        for row in raw_candidates
        if isinstance(row, Mapping) and row.get("source_lane") == "project_registered_candidates"
    ]
    rows: list[dict[str, object]] = []
    for source in sorted(context_rows, key=lambda item: str(item.get("candidate_id", ""))):
        factor_id = str(source.get("source_factor_id", ""))
        receipt = source_by_factor.get(factor_id)
        if receipt is None:
            raise ValueError(f"round3_context_source_not_materialized:{factor_id}")
        has_available_at = receipt.get("available_at_column_present") is True
        blockers = ["strategy_scoped_datahub_consumer_contract_fl_z1hie_not_granted"]
        if not has_available_at:
            blockers.insert(0, "available_at_column_missing_requires_upstream_rematerialization")
        if source.get("source_id") == "entity_catch_up_registry":
            blockers.append("entity_panel_has_no_governed_stock_symbol_mapping")
        rows.append(
            {
                "candidate_id": str(source.get("candidate_id", "")),
                "source_id": str(source.get("source_id", "")),
                "source_factor_id": factor_id,
                "mechanism_family": str(source.get("mechanism_family", "")),
                "source_artifact_ref": str(receipt.get("source_artifact_ref", "")),
                "source_artifact_digest": str(receipt.get("source_artifact_digest", "")),
                "available_at_column_present": has_available_at,
                "asof_policy": "latest_available_at_strictly_before_decision_time",
                "normalization_policy": "expanding_train_prefix_median_iqr_with_explicit_missing_mask",
                "incumbent_consumer_role": "family_weight_or_gate_context_only",
                "challenger_consumer_role": "operator_transition_or_context_encoder_only",
                "direct_stock_alpha_vote_allowed": False,
                "same_snapshot_required_for_both_strategies": True,
                "consumption_ready": False,
                "blockers": blockers,
                "production_authority": False,
            }
        )
    payload: dict[str, object] = {
        "artifact_type": "macro_regime_dual_strategy_round3_context_consumer_contract",
        "contract_version": "round3_context_consumer@1.0",
        "candidate_count": len(rows),
        "candidates": rows,
        "global_rules": {
            "broadcast_context_as_stock_alpha": False,
            "same_context_snapshot_for_both_strategies": True,
            "asof_join": "available_at_strictly_before_decision_time",
            "normalization": "expanding_train_prefix_only_median_iqr",
            "missingness": "explicit_mask_no_zero_fill",
            "borrow_other_strategy_consumer_grant": False,
        },
        "authority": round3_false_authority(),
    }
    payload["canonical_digest"] = canonical_digest(payload)
    validate_context_consumer_contract(payload)
    return payload


def validate_context_consumer_contract(payload: Mapping[str, object]) -> None:
    """Fail closed on missing identities, direct stock votes, or consumer readiness drift."""

    rows = payload.get("candidates")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("round3_context_candidates_array_required")
    candidate_rows = cast(list[Mapping[str, object]], rows)
    if payload.get("candidate_count") != CONTEXT_CANDIDATE_COUNT or len(candidate_rows) != CONTEXT_CANDIDATE_COUNT:
        raise ValueError("round3_context_candidate_count_must_equal_70")
    ids = [str(row.get("candidate_id", "")) for row in candidate_rows]
    if "" in ids or len(ids) != len(set(ids)):
        raise ValueError("round3_context_candidate_ids_must_be_unique_nonempty")
    for row in candidate_rows:
        if row.get("direct_stock_alpha_vote_allowed") is not False:
            raise ValueError(f"round3_context_stock_vote_forbidden:{row.get('candidate_id', '')}")
        if row.get("consumption_ready") is not False or not row.get("blockers"):
            raise ValueError(f"round3_context_must_remain_deferred_until_grant:{row.get('candidate_id', '')}")
        if row.get("same_snapshot_required_for_both_strategies") is not True:
            raise ValueError(f"round3_context_shared_snapshot_required:{row.get('candidate_id', '')}")
        if row.get("production_authority") is not False:
            raise ValueError(f"round3_context_false_authority_required:{row.get('candidate_id', '')}")
    rules = payload.get("global_rules")
    if not isinstance(rules, Mapping) or rules.get("broadcast_context_as_stock_alpha") is not False:
        raise ValueError("round3_context_broadcast_must_be_false")
    if rules.get("borrow_other_strategy_consumer_grant") is not False:
        raise ValueError("round3_context_grant_borrowing_must_be_false")
    _validate_all_false_authority(payload.get("authority"), "round3_context")
    _validate_digest(payload)


def evaluate_strict_pit_gate(
    *,
    manifest: Mapping[str, object],
    certification: Mapping[str, object],
    context_contract: Mapping[str, object],
    prospective_observation_count: int,
    rematerialized_industry_factor_ids: Sequence[str],
) -> dict[str, object]:
    """Return the mechanical Round-3 start verdict without reading model inputs."""

    blockers: list[str] = []
    if manifest.get("dataset_version") != STRICT_FINANCIAL_DATASET_VERSION:
        blockers.append("strict_financial_dataset_version_mismatch")
    if manifest.get("first_release_semantics") is not True:
        blockers.append("strict_financial_first_release_semantics_not_proven")
    if certification.get("dataset_version") != STRICT_FINANCIAL_DATASET_VERSION:
        blockers.append("strict_financial_certification_version_mismatch")
    if certification.get("capability_decision") != "granted":
        blockers.append("strict_financial_capability_not_granted")
    if certification.get("state") not in {"certified", "active", "granted"}:
        blockers.append("strict_financial_dataset_not_in_certified_state")
    grants = certification.get("grants")
    grant_values = set(cast(list[str], grants)) if isinstance(grants, list) and all(isinstance(item, str) for item in grants) else set()
    if "single_asset_scoring" not in grant_values:
        blockers.append("single_asset_scoring_grant_missing")
    context_rows = context_contract.get("candidates")
    ready_context_count = 0
    if isinstance(context_rows, list):
        ready_context_count = sum(isinstance(row, Mapping) and row.get("consumption_ready") is True for row in context_rows)
    if ready_context_count != CONTEXT_CANDIDATE_COUNT:
        blockers.append(f"context_consumer_contract_not_ready:{ready_context_count}/{CONTEXT_CANDIDATE_COUNT}")
    rematerialized: set[str] = set(rematerialized_industry_factor_ids)
    required_industry: set[str] = set(INDUSTRY_FACTOR_IDS)
    missing_industry = sorted(required_industry - rematerialized)
    if missing_industry:
        blockers.append(f"authorized_csrc_industry_rematerialization_incomplete:{len(missing_industry)}")
    if prospective_observation_count <= 0:
        blockers.append("fresh_prospective_forward_observations_unavailable")
    return {
        "artifact_type": "macro_regime_dual_strategy_round3_strict_pit_gate",
        "status": "ready" if not blockers else "blocked",
        "dataset_version": str(manifest.get("dataset_version", "")),
        "dataset_hash": str(manifest.get("dataset_hash", "")),
        "manifest_first_release_semantics": manifest.get("first_release_semantics") is True,
        "capability_decision": str(certification.get("capability_decision", "")),
        "dataset_state": str(certification.get("state", "")),
        "grants": sorted(grant_values),
        "context_consumption_ready_count": ready_context_count,
        "industry_factor_required_count": len(INDUSTRY_FACTOR_IDS),
        "industry_factor_rematerialized_count": len(rematerialized & required_industry),
        "prospective_observation_count": int(prospective_observation_count),
        "blockers": blockers,
        "formal_metric_pipeline_observations_read": False,
        "battle_started": False,
        "winner_strategy_id": None,
        "authority": round3_false_authority(),
    }


def build_round3_factor_coverage(
    round2_coverage: pd.DataFrame,
    *,
    stock_factor_ids: Sequence[str],
    strict_financial_factor_ids: Sequence[str],
    timing_contract: Mapping[str, object],
) -> pd.DataFrame:
    """Promote the 310-name inventory into explicit prepared/deferred dispositions."""

    if len(round2_coverage) != REGISTERED_CANDIDATE_COUNT:
        raise ValueError("round3_coverage_requires_310_round2_registry_rows")
    stock_ids = set(stock_factor_ids)
    if len(stock_ids) != STOCK_FACTOR_COUNT:
        raise ValueError("round3_coverage_requires_205_unique_stock_factor_ids")
    financial_ids = set(strict_financial_factor_ids)
    timing_rows = timing_contract.get("candidates")
    if not isinstance(timing_rows, list):
        raise ValueError("round3_timing_contract_candidates_required")
    timing_by_id = {
        str(cast(Mapping[str, object], row).get("candidate_id", "")): cast(Mapping[str, object], row)
        for row in timing_rows
        if isinstance(row, Mapping)
    }
    rows: list[dict[str, object]] = []
    for source in round2_coverage.to_dict(orient="records"):
        row = dict(source)
        lane = str(row.get("source_lane", ""))
        candidate_id = str(row.get("candidate_id", ""))
        factor_id = str(row.get("source_factor_id", ""))
        local_ready = False
        if lane == "stock_factor_history":
            if factor_id not in stock_ids:
                raise ValueError(f"round3_stock_factor_not_materialized:{factor_id}")
            row["materialization_status"] = "materialized_legacy_lineage_repaired_stock_cross_section"
            row["battle_role"] = "shared_cross_sectional_alpha_input_after_strict_rematerialization"
            row["legacy_value_materialized"] = True
            if factor_id in set(INDUSTRY_FACTOR_IDS):
                disposition = "deferred_authorized_csrc_industry_rematerialization"
                reason = "legacy_sw2021_membership_forbidden_for_strict_round3"
            elif factor_id in financial_ids:
                disposition = "deferred_strict_first_release_financial_authority"
                reason = "fl_tzkr_single_asset_scoring_grant_missing"
            else:
                disposition = "prepared_causal_market_materializer_requires_global_gate"
                reason = "global_strict_pit_context_and_prospective_gate_blocked"
                local_ready = True
        elif lane.startswith("timing"):
            contract_row = timing_by_id.get(candidate_id)
            if contract_row is None:
                raise ValueError(f"round3_timing_coverage_contract_missing:{candidate_id}")
            disposition = str(contract_row.get("round3_disposition", ""))
            reason = str(contract_row.get("defer_reason", "")) or "daily_formula_frozen_but_stock_values_not_materialized"
            row["materialization_status"] = "stock_formula_and_normalization_frozen"
            row["battle_role"] = "deferred_timing_cross_section_until_materialized"
            row["legacy_value_materialized"] = False
            local_ready = disposition == "formula_ready_daily"
        elif lane == "project_registered_candidates":
            disposition = "deferred_context_consumer_contract"
            reason = "context_must_not_broadcast_as_stock_alpha_and_strategy_contract_is_ungranted"
            row["battle_role"] = "shared_strategy_context_only"
            row["legacy_value_materialized"] = True
        else:
            disposition = "deferred_non_stock_or_non_atomic_identity"
            reason = str(row.get("exclusion_reason", "")) or "no_legal_stock_cross_section_semantics"
            row["legacy_value_materialized"] = False
        row["round3_input_disposition"] = disposition
        row["round3_defer_reason"] = reason
        row["local_preparation_ready"] = local_ready
        row["executable_round3"] = False
        row["placeholder_factor"] = False
        row["production_authority"] = False
        rows.append(row)
    coverage = pd.DataFrame(rows).sort_values("candidate_id", kind="stable").reset_index(drop=True)
    if len(coverage) != REGISTERED_CANDIDATE_COUNT or coverage["candidate_id"].nunique() != REGISTERED_CANDIDATE_COUNT:
        raise ValueError("round3_coverage_registry_identity_mismatch")
    if int(coverage["placeholder_factor"].sum()) != 0:
        raise ValueError("round3_coverage_placeholder_forbidden")
    if coverage["round3_input_disposition"].astype(str).str.len().eq(0).any():
        raise ValueError("round3_coverage_disposition_required")
    if coverage["round3_defer_reason"].astype(str).str.len().eq(0).any():
        raise ValueError("round3_coverage_defer_reason_required")
    return coverage


def summarize_round3_factor_coverage(coverage: pd.DataFrame) -> dict[str, object]:
    """Return the deterministic 310-name readiness census."""

    return {
        "registered_candidate_count": int(len(coverage)),
        "legacy_lineage_repaired_stock_factor_count": int(
            coverage["materialization_status"].eq("materialized_legacy_lineage_repaired_stock_cross_section").sum()
        ),
        "newly_materialized_missing_stock_factor_count": len(MISSING_STOCK_FACTOR_IDS),
        "timing_candidate_contract_count": int(coverage["source_lane"].astype(str).str.startswith("timing").sum()),
        "context_candidate_contract_count": int(coverage["source_lane"].eq("project_registered_candidates").sum()),
        "round3_executable_before_global_gate_count": int(coverage["executable_round3"].sum()),
        "local_preparation_ready_count": int(coverage["local_preparation_ready"].sum()),
        "placeholder_factor_count": int(coverage["placeholder_factor"].sum()),
        "disposition_counts": {
            str(key): int(value) for key, value in coverage["round3_input_disposition"].value_counts().sort_index().items()
        },
    }


def seal_round3_readiness(payload: dict[str, object]) -> None:
    """Attach the readiness digest after validating non-digest fields."""

    payload.pop("canonical_digest", None)
    payload["canonical_digest"] = canonical_digest(payload)
    report = validate_round3_readiness(payload)
    if report["status"] != "valid":
        raise ValueError(";".join(cast(list[str], report["blockers"])))


def validate_round3_readiness(payload: Mapping[str, object]) -> dict[str, object]:
    """Validate that a blocked readiness package cannot masquerade as Round 3."""

    blockers: list[str] = []
    if payload.get("artifact_type") != ROUND3_READINESS_ARTIFACT_TYPE:
        blockers.append("artifact_type_mismatch")
    if payload.get("schema_id") != ROUND3_READINESS_SCHEMA_ID:
        blockers.append("schema_id_mismatch")
    if payload.get("trial_id") != ROUND3_TRIAL_ID:
        blockers.append("trial_id_mismatch")
    if payload.get("iteration_id") != ROUND3_ITERATION_ID:
        blockers.append("iteration_id_mismatch")
    if payload.get("status") != "blocked":
        blockers.append("readiness_status_must_remain_blocked_until_gate_passes")
    coverage = payload.get("factor_coverage_summary")
    if not isinstance(coverage, Mapping):
        blockers.append("factor_coverage_summary_required")
    else:
        expected = {
            "registered_candidate_count": REGISTERED_CANDIDATE_COUNT,
            "legacy_lineage_repaired_stock_factor_count": STOCK_FACTOR_COUNT,
            "newly_materialized_missing_stock_factor_count": len(MISSING_STOCK_FACTOR_IDS),
            "timing_candidate_contract_count": TIMING_CANDIDATE_COUNT,
            "context_candidate_contract_count": CONTEXT_CANDIDATE_COUNT,
            "round3_executable_before_global_gate_count": 0,
            "placeholder_factor_count": 0,
        }
        for key, value in expected.items():
            if coverage.get(key) != value:
                blockers.append(f"factor_coverage_{key}_mismatch")
    duplicate = payload.get("duplicate_lineage_summary")
    if not isinstance(duplicate, Mapping):
        blockers.append("duplicate_lineage_summary_required")
    else:
        for key, value in {
            "ambiguous_factor_count": 26,
            "pre_resolution_duplicate_key_group_count": 547_421,
            "pre_resolution_conflicting_value_group_count": 104_323,
            "post_resolution_duplicate_key_group_count": 0,
            "post_resolution_conflicting_value_group_count": 0,
        }.items():
            if duplicate.get(key) != value:
                blockers.append(f"duplicate_lineage_{key}_mismatch")
    gate = payload.get("strict_pit_gate")
    if not isinstance(gate, Mapping) or gate.get("status") != "blocked" or not gate.get("blockers"):
        blockers.append("strict_pit_blocked_gate_required")
    if payload.get("formal_metric_pipeline_observations_read") is not False:
        blockers.append("formal_metric_pipeline_observations_must_not_be_read")
    if payload.get("battle_started") is not False:
        blockers.append("round3_battle_must_not_be_marked_started")
    if payload.get("winner_strategy_id") is not None:
        blockers.append("round3_winner_must_be_null")
    try:
        _validate_all_false_authority(payload.get("authority"), "round3_readiness")
    except ValueError as exc:
        blockers.append(str(exc))
    digest = payload.get("canonical_digest")
    expected_digest = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    if digest != expected_digest:
        blockers.append("canonical_digest_mismatch")
    return {
        "schema_id": ROUND3_READINESS_SCHEMA_ID,
        "status": "valid" if not blockers else "invalid",
        "blockers": blockers,
    }


def _validate_all_false_authority(value: object, prefix: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(_FALSE_AUTHORITY):
        raise ValueError(f"{prefix}_authority_shape_invalid")
    if any(item is not False for item in value.values()):
        raise ValueError(f"{prefix}_authority_must_be_all_false")


def _validate_digest(payload: Mapping[str, object]) -> None:
    digest = payload.get("canonical_digest")
    expected = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    if digest != expected:
        raise ValueError("canonical_digest_mismatch")
