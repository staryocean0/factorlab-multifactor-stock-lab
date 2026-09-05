# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false, reportReturnType=false
# pyright: reportAny=false, reportImplicitStringConcatenation=false
# pyright: reportMissingTypeStubs=false, reportUnusedCallResult=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Executable Round-3 contracts for opaque annual rolling validation.

This successor leaves the immutable Round-3 readiness evidence untouched.  It
replaces the old all-or-none gates with item-level admission and implements the
user's chronological black-box rule: train through year ``Y-1``, score year
``Y`` without outcome-conditioned inspection, then mechanically append that
completed year to the next fold's training prefix.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final, cast

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.macro_regime_dual_strategy_round3 import (
    CONTEXT_CANDIDATE_COUNT,
    INDUSTRY_FACTOR_IDS,
    REGISTERED_CANDIDATE_COUNT,
    STOCK_FACTOR_COUNT,
    TIMING_CANDIDATE_COUNT,
)
from factor_lab.factor_rotation.strict_annual_financial_factors import (
    ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS,
    ANNUAL_FINANCIAL_ALIAS_TO_CANONICAL,
    ANNUAL_INCOMPATIBLE_FINANCIAL_FACTOR_IDS,
)
from factor_lab.governance.canonicalization import canonical_digest

ROUND3_EXECUTION_PREFLIGHT_SCHEMA_ID: Final = "macro_regime_dual_strategy_round3_execution_preflight@1.0"
ROUND3_EXECUTION_RESULT_SCHEMA_ID: Final = "macro_regime_dual_strategy_round3_opaque_annual_rolling@1.0"
ROUND3_EXECUTION_TRIAL_ID: Final = "macro_regime_v1_vs_reaka_v1_round3_opaque_annual_rolling_2021_2025"
STRICT_ANNUAL_FINANCIAL_CONSUMER_CONTRACT_ID: Final = "cn_a_financial_pit_first_release_annual_largecap.v1"
ROUND3_MACRO_CONSUMER_CONTRACT_ID: Final = "macro_regime_dual_strategy_annual_rolling.v1"
MINIMUM_TOTAL_MARKET_CAP_CNY: Final = 15_000_000_000
COMPLETE_VALIDATION_YEARS: Final[tuple[int, ...]] = (2021, 2022, 2023, 2024, 2025)
INCOMPLETE_PREVIEW_YEAR: Final = 2026
TAIL_FRESHNESS_TOLERANCE_DAYS: Final = 62

ADMITTED_MACRO_SERIES_IDS: Final[tuple[str, ...]] = (
    "industrial_value_added_yoy",
    "m2_yoy",
    "nominal_gdp_yoy",
    "pmi_manufacturing",
    "pmi_new_orders_index",
    "ppi_yoy",
)

ADMITTED_MACRO_CONTEXT_FACTOR_MAP: Final[dict[str, str]] = {f"macro_{series_id}": series_id for series_id in ADMITTED_MACRO_SERIES_IDS}

ROUND3_TIMING_CANONICAL_ATTRIBUTES: Final[dict[str, tuple[str, str]]] = {
    "bollinger_volatility_channel": (
        "volatility_channel",
        "signed_upper_rail_margin",
    ),
    "butterworth_clean_bandpass": (
        "bandpass_component",
        "component_direction_delta",
    ),
    "causal_haar_wavelet_bandpass": (
        "bandpass_component",
        "component_direction_delta",
    ),
    "donchian_price_channel": ("price_channel", "donchian_entry_margin"),
    "laplace_iir_mixed_bandpass": (
        "bandpass_component",
        "component_direction_delta",
    ),
    "r3_nested_moving_average_component": (
        "trend_component",
        "r3_component_delta",
    ),
    "simple_moving_average_trend": (
        "trend_component",
        "exact_sma_kernel_gap",
    ),
}

ROUND3_TIMING_PARAMETERS: Final[dict[str, dict[str, float | int]]] = {
    "bollinger_volatility_channel": {"width_sigma": 2.0, "window_bars": 20},
    "butterworth_clean_bandpass": {
        "long_period_bars": 57,
        "order": 4,
        "short_period_bars": 28,
    },
    "causal_haar_wavelet_bandpass": {
        "level": 2,
        "slow_level": 5,
        "window_bars": 128,
    },
    "donchian_price_channel": {
        "entry_window_bars": 20,
        "exit_window_bars": 10,
    },
    "laplace_iir_mixed_bandpass": {"period_bars": 40, "q": 1.0},
    "r3_nested_moving_average_component": {
        "fast_window_bars": 2,
        "slow_window_bars": 16,
    },
    "simple_moving_average_trend": {
        "fast_window_bars": 10,
        "slow_window_bars": 30,
    },
}

_TIMING_ALIAS_TO_CANONICAL: Final[dict[str, str]] = {
    "donchian_breakout_margin": "donchian_price_channel",
    "haar_component_delta": "causal_haar_wavelet_bandpass",
    "r3_component_delta": "r3_nested_moving_average_component",
}

_FALSE_AUTHORITY: Final[dict[str, bool]] = {
    "asset_selection_allowed": False,
    "individual_stock_scoring_allowed": False,
    "portfolio_construction_allowed": False,
    "portfolio_execution": False,
    "holdings_created": False,
    "orders_created": False,
    "production_authority": False,
}


def round3_execution_false_authority() -> dict[str, bool]:
    return dict(_FALSE_AUTHORITY)


def build_opaque_annual_rolling_contract() -> dict[str, object]:
    """Freeze the five complete annual black-box folds and the 2026 preview."""

    folds = [
        {
            "fold_id": f"annual_{year}",
            "train_start": "2018-01-01",
            "train_end": f"{year - 1}-12-31",
            "test_start": f"{year}-01-01",
            "test_end": f"{year}-12-31",
            "test_outcome_visibility_during_fit": "opaque",
            "next_fold_update": "mechanically_append_completed_year_without_retuning",
        }
        for year in COMPLETE_VALIDATION_YEARS
    ]
    payload: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_opaque_annual_rolling_contract@1.0",
        "trial_id": ROUND3_EXECUTION_TRIAL_ID,
        "folds": folds,
        "complete_validation_years": list(COMPLETE_VALIDATION_YEARS),
        "incomplete_preview_year": INCOMPLETE_PREVIEW_YEAR,
        "incomplete_preview_scored": False,
        "black_box_policy": {
            "market_outcomes_hidden_during_each_fold_fit": True,
            "no_test_year_drilldown_for_model_or_parameter_selection": True,
            "no_post_hoc_regime_story_changes": True,
            "only_annual_and_paired_aggregate_metrics_persisted": True,
            "completed_test_year_may_enter_next_training_prefix": True,
            "model_family_and_hyperparameters_refrozen_before_first_test": True,
        },
        "authority": round3_execution_false_authority(),
    }
    payload["canonical_digest"] = canonical_digest(payload)
    validate_opaque_annual_rolling_contract(payload)
    return payload


def validate_opaque_annual_rolling_contract(payload: Mapping[str, object]) -> None:
    folds = payload.get("folds")
    if not isinstance(folds, list) or len(folds) != len(COMPLETE_VALIDATION_YEARS):
        raise ValueError("round3_opaque_annual_five_complete_folds_required")
    for raw, year in zip(folds, COMPLETE_VALIDATION_YEARS, strict=True):
        if not isinstance(raw, Mapping):
            raise ValueError("round3_opaque_annual_fold_object_required")
        if raw.get("train_end") != f"{year - 1}-12-31":
            raise ValueError(f"round3_opaque_annual_train_prefix_mismatch:{year}")
        if raw.get("test_start") != f"{year}-01-01" or raw.get("test_end") != f"{year}-12-31":
            raise ValueError(f"round3_opaque_annual_test_window_mismatch:{year}")
        if raw.get("test_outcome_visibility_during_fit") != "opaque":
            raise ValueError(f"round3_opaque_annual_outcome_leakage:{year}")
    if payload.get("incomplete_preview_scored") is not False:
        raise ValueError("round3_opaque_annual_incomplete_2026_must_not_be_scored")
    policy = payload.get("black_box_policy")
    if not isinstance(policy, Mapping) or any(
        policy.get(key) is not True
        for key in (
            "market_outcomes_hidden_during_each_fold_fit",
            "no_test_year_drilldown_for_model_or_parameter_selection",
            "no_post_hoc_regime_story_changes",
            "only_annual_and_paired_aggregate_metrics_persisted",
            "completed_test_year_may_enter_next_training_prefix",
            "model_family_and_hyperparameters_refrozen_before_first_test",
        )
    ):
        raise ValueError("round3_opaque_annual_black_box_policy_incomplete")
    _validate_false_authority(payload.get("authority"), "round3_opaque_annual")
    _validate_digest(payload)


def build_round3_candidate_admission_contract(
    registry: Mapping[str, object],
) -> dict[str, object]:
    """Classify all 310 identities without all-or-none pool blockers."""

    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("round3_execution_registry_candidates_required")
    rows: list[dict[str, object]] = []
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            raise ValueError("round3_execution_registry_candidate_object_required")
        candidate_id = str(raw.get("candidate_id", ""))
        factor_id = str(raw.get("source_factor_id", ""))
        lane = str(raw.get("source_lane", ""))
        model_column_id: str | None = None
        role = "catalog_only"
        status = "deferred"
        reason: str
        if lane == "stock_factor_history":
            role = "stock_cross_sectional_alpha"
            if factor_id in INDUSTRY_FACTOR_IDS:
                reason = "historical_pit_industry_membership_not_proven_for_2021_2025"
            elif factor_id in ANNUAL_INCOMPATIBLE_FINANCIAL_FACTOR_IDS:
                reason = "quarterly_formula_cannot_be_redefined_from_annual_only_facts"
            elif factor_id in ANNUAL_FINANCIAL_ALIAS_TO_CANONICAL:
                status = "alias_deduplicated"
                model_column_id = ANNUAL_FINANCIAL_ALIAS_TO_CANONICAL[factor_id]
                reason = "same_economic_formula_one_model_vote"
            elif factor_id in ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS:
                status = "conditional"
                model_column_id = factor_id
                reason = "requires_granted_fixed_strict_annual_financial_binding"
            else:
                status = "admitted"
                model_column_id = factor_id
                reason = "causal_nonfinancial_stock_factor_with_repaired_unique_lineage"
        elif lane.startswith("timing"):
            role = "stock_formula_attribute"
            if factor_id in _TIMING_ALIAS_TO_CANONICAL:
                status = "alias_deduplicated"
                model_column_id = _TIMING_ALIAS_TO_CANONICAL[factor_id]
                reason = "derived_timing_alias_cannot_multiply_a_mechanism_vote"
            elif factor_id in ROUND3_TIMING_CANONICAL_ATTRIBUTES:
                status = "admitted"
                model_column_id = factor_id
                reason = "frozen_daily_causal_formula_attribute"
            else:
                reason = "intraday_rejected_composite_or_unfrozen_timing_identity"
        elif lane == "project_registered_candidates":
            role = "shared_strategy_context_only"
            if factor_id in ADMITTED_MACRO_CONTEXT_FACTOR_MAP:
                status = "conditional"
                model_column_id = f"context:{ADMITTED_MACRO_CONTEXT_FACTOR_MAP[factor_id]}"
                reason = "requires_exact_round3_macro_consumer_grant"
            else:
                reason = "pit_lineage_or_governed_context_encoding_not_proven"
        else:
            reason = str(raw.get("exclusion_reason", "")) or ("no_atomic_single_stock_or_shared_context_semantics")
        rows.append(
            {
                "candidate_id": candidate_id,
                "source_factor_id": factor_id,
                "source_lane": lane,
                "mechanism_family": str(raw.get("mechanism_family", "")),
                "battle_role": role,
                "admission_status": status,
                "model_column_id": model_column_id,
                "reason": reason,
                "same_disposition_for_both_strategies": True,
                "placeholder_factor": False,
                "production_authority": False,
            }
        )
    rows.sort(key=lambda row: str(row["candidate_id"]))
    payload: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_candidate_admission@1.0",
        "registered_candidate_count": len(rows),
        "rows": rows,
        "rules": {
            "pool_all_or_none_gate": False,
            "same_exclusions_for_both_strategies": True,
            "placeholder_or_zero_fill_allowed": False,
            "industry_and_style_can_be_active_alpha_when_admitted": True,
            "context_direct_stock_alpha_vote_allowed": False,
            "one_model_vote_per_economic_or_timing_alias": True,
        },
        "authority": round3_execution_false_authority(),
    }
    payload["summary"] = summarize_round3_candidate_admission(payload)
    payload["canonical_digest"] = canonical_digest(payload)
    validate_round3_candidate_admission_contract(payload)
    return payload


def summarize_round3_candidate_admission(
    payload: Mapping[str, object],
) -> dict[str, object]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("round3_execution_admission_rows_required")
    typed = [cast(Mapping[str, object], row) for row in rows if isinstance(row, Mapping)]
    status_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for row in typed:
        status = str(row.get("admission_status", ""))
        role = str(row.get("battle_role", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
        role_counts[role] = role_counts.get(role, 0) + 1
    unique_columns = {
        str(row.get("model_column_id"))
        for row in typed
        if row.get("admission_status") in {"admitted", "conditional"} and row.get("model_column_id") is not None
    }
    return {
        "status_counts": dict(sorted(status_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "unique_admitted_or_conditional_model_column_count": len(unique_columns),
        "industry_deferred_count": sum(str(row.get("source_factor_id")) in INDUSTRY_FACTOR_IDS for row in typed),
        "macro_context_conditional_count": sum(
            str(row.get("source_factor_id")) in ADMITTED_MACRO_CONTEXT_FACTOR_MAP
            and row.get("battle_role") == "shared_strategy_context_only"
            for row in typed
        ),
    }


def validate_round3_candidate_admission_contract(
    payload: Mapping[str, object],
) -> None:
    rows = payload.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("round3_execution_admission_rows_required")
    typed = cast(list[Mapping[str, object]], rows)
    if len(typed) != REGISTERED_CANDIDATE_COUNT:
        raise ValueError("round3_execution_admission_requires_310_candidates")
    ids = [str(row.get("candidate_id", "")) for row in typed]
    if "" in ids or len(ids) != len(set(ids)):
        raise ValueError("round3_execution_candidate_ids_must_be_unique")
    if sum(row.get("source_lane") == "stock_factor_history" for row in typed) != STOCK_FACTOR_COUNT:
        raise ValueError("round3_execution_requires_205_stock_identities")
    if sum(str(row.get("source_lane", "")).startswith("timing") for row in typed) != TIMING_CANDIDATE_COUNT:
        raise ValueError("round3_execution_requires_20_timing_identities")
    if sum(row.get("source_lane") == "project_registered_candidates" for row in typed) != CONTEXT_CANDIDATE_COUNT:
        raise ValueError("round3_execution_requires_70_context_identities")
    if any(row.get("placeholder_factor") is not False for row in typed):
        raise ValueError("round3_execution_placeholder_factor_forbidden")
    if any(row.get("same_disposition_for_both_strategies") is not True for row in typed):
        raise ValueError("round3_execution_asymmetric_candidate_disposition")
    rules = payload.get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError("round3_execution_admission_rules_required")
    if rules.get("pool_all_or_none_gate") is not False:
        raise ValueError("round3_execution_all_or_none_pool_gate_forbidden")
    if rules.get("placeholder_or_zero_fill_allowed") is not False:
        raise ValueError("round3_execution_zero_fill_forbidden")
    conditional_context = {
        str(row.get("source_factor_id"))
        for row in typed
        if row.get("battle_role") == "shared_strategy_context_only" and row.get("admission_status") == "conditional"
    }
    if conditional_context != set(ADMITTED_MACRO_CONTEXT_FACTOR_MAP):
        raise ValueError("round3_execution_macro_context_set_changed")
    _validate_false_authority(payload.get("authority"), "round3_execution_admission")
    _validate_digest(payload)


def audit_temporal_source_continuity(
    *,
    observed_dates: Sequence[object],
    governed_expected_dates: Sequence[object],
    as_of_date: date,
    tail_tolerance_days: int = TAIL_FRESHNESS_TOLERANCE_DAYS,
) -> dict[str, object]:
    """Separate blocking interior gaps from tolerated tail staleness."""

    observed = pd.DatetimeIndex(pd.to_datetime(list(observed_dates), errors="coerce")).dropna().normalize().unique().sort_values()
    expected = pd.DatetimeIndex(pd.to_datetime(list(governed_expected_dates), errors="coerce")).dropna().normalize().unique().sort_values()
    if observed.empty or expected.empty:
        raise ValueError("round3_continuity_dates_required")
    observed_set = set(observed)
    maximum_observed = pd.Timestamp(observed.max())
    interior_expected = [item for item in expected if item <= maximum_observed]
    missing_interior = [item for item in interior_expected if item not in observed_set]
    tail_lag_days = (pd.Timestamp(as_of_date) - maximum_observed).days
    payload: dict[str, object] = {
        "schema_id": "factorlab.temporal_source_continuity_audit.v1",
        "observed_start": str(pd.Timestamp(observed.min()).date()),
        "observed_end": str(maximum_observed.date()),
        "as_of_date": as_of_date.isoformat(),
        "tail_lag_days": int(tail_lag_days),
        "tail_tolerance_days": int(tail_tolerance_days),
        "tail_within_tolerance": tail_lag_days <= tail_tolerance_days,
        "interior_gap_count": len(missing_interior),
        "interior_gap_sample": [str(item.date()) for item in missing_interior[:20]],
        "blocking": bool(missing_interior),
        "freshness_action": (
            "no_tail_backfill_required" if tail_lag_days <= tail_tolerance_days else "stale_but_backfill_only_if_strategy_required"
        ),
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def materialize_monthly_macro_context(
    *,
    observations: pd.DataFrame,
    decisions: pd.DataFrame,
    series_ids: Sequence[str] = ADMITTED_MACRO_SERIES_IDS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """As-of materialize the six exact-grant macro contexts and masks."""

    observation_required = {"available_at", "series_id", "value"}
    if not observation_required.issubset(observations.columns):
        missing = sorted(observation_required - set(observations.columns))
        raise ValueError("round3_macro_observation_columns_missing:" + ",".join(missing))
    if not {"date", "decision_as_of"}.issubset(decisions.columns):
        raise ValueError("round3_macro_decision_columns_missing")
    wanted = tuple(str(item) for item in series_ids)
    if len(wanted) != len(set(wanted)) or set(wanted) != set(ADMITTED_MACRO_SERIES_IDS):
        raise ValueError("round3_macro_exact_six_series_required")
    source = observations.loc[observations["series_id"].isin(wanted)].copy()
    source["available_at"] = pd.to_datetime(
        source["available_at"], format="mixed", errors="coerce", utc=True
    ).astype("datetime64[ns, UTC]")
    source["value"] = pd.to_numeric(source["value"], errors="coerce")
    source = source.dropna(subset=["available_at", "series_id", "value"])
    if source.duplicated(["series_id", "available_at"]).any():
        if "observation_date" not in source.columns:
            duplicate = source.groupby(["series_id", "available_at"], observed=True)["value"].nunique()
            if duplicate.gt(1).any():
                raise ValueError("round3_macro_conflicting_vintage_at_same_availability")
            source = source.drop_duplicates(["series_id", "available_at"], keep="first")
        else:
            source["_observation_order"] = pd.to_datetime(
                source["observation_date"], format="mixed", errors="coerce"
            )
            if source["_observation_order"].isna().any():
                raise ValueError("round3_macro_duplicate_release_observation_date_required")
            latest_order = source.groupby(
                ["series_id", "available_at"], observed=True
            )["_observation_order"].transform("max")
            latest = source.loc[source["_observation_order"].eq(latest_order)].copy()
            conflicting_latest = latest.groupby(
                ["series_id", "available_at", "_observation_order"], observed=True
            )["value"].nunique()
            if conflicting_latest.gt(1).any():
                raise ValueError("round3_macro_conflicting_vintage_at_same_availability")
            source = latest.drop_duplicates(
                ["series_id", "available_at"], keep="first"
            )
    decision_frame = decisions.loc[:, ["date", "decision_as_of"]].copy()
    decision_frame["date"] = pd.to_datetime(
        decision_frame["date"], format="mixed", errors="coerce"
    )
    decision_frame["decision_as_of"] = pd.to_datetime(
        decision_frame["decision_as_of"], format="mixed", errors="coerce", utc=True
    ).astype("datetime64[ns, UTC]")
    decision_frame = decision_frame.dropna().drop_duplicates("date").sort_values("decision_as_of")
    values = decision_frame.loc[:, ["date"]].copy()
    masks = decision_frame.loc[:, ["date"]].copy()
    visible_counts: dict[str, int] = {}
    for series_id in wanted:
        rows = source.loc[source["series_id"].eq(series_id), ["available_at", "value"]].sort_values("available_at")
        joined = pd.merge_asof(
            decision_frame,
            rows,
            left_on="decision_as_of",
            right_on="available_at",
            direction="backward",
            allow_exact_matches=False,
        )
        values[series_id] = joined["value"].to_numpy()
        masks[f"{series_id}__observed"] = joined["value"].notna().to_numpy(dtype=bool)
        visible_counts[series_id] = int(joined["value"].notna().sum())
    receipt: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_macro_context_materialization.v1",
        "series_ids": list(wanted),
        "decision_count": int(len(decision_frame)),
        "visible_decision_counts": visible_counts,
        "join_predicate": "available_at < decision_as_of",
        "direct_stock_alpha_vote_allowed": False,
        "same_snapshot_for_both_strategies": True,
        "production_authority": False,
    }
    receipt["canonical_digest"] = canonical_digest(receipt)
    return values, masks, receipt


def scale_macro_context_from_training_prefix(
    values: pd.DataFrame,
    masks: pd.DataFrame,
    *,
    train_rows: Sequence[bool],
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    """Median/IQR scale context using only the current fold's train prefix."""

    factor_columns = [column for column in values.columns if column != "date"]
    mask_columns = [f"{column}__observed" for column in factor_columns]
    if list(masks.columns) != ["date", *mask_columns] or not values["date"].equals(masks["date"]):
        raise ValueError("round3_macro_context_value_mask_alignment_invalid")
    selector = np.asarray(list(train_rows), dtype=bool)
    if selector.shape != (len(values),) or not selector.any():
        raise ValueError("round3_macro_context_train_prefix_required")
    raw = values[factor_columns].to_numpy(dtype=float)
    observed = masks[mask_columns].to_numpy(dtype=bool)
    train = np.where(observed[selector], raw[selector], np.nan)
    median = np.nanmedian(train, axis=0)
    q25 = np.nanquantile(train, 0.25, axis=0)
    q75 = np.nanquantile(train, 0.75, axis=0)
    scale = q75 - q25
    invalid = ~np.isfinite(median) | ~np.isfinite(scale) | (np.abs(scale) < 1e-12)
    median[invalid] = 0.0
    scale[invalid] = 1.0
    scaled = (raw - median) / scale
    scaled = np.where(observed, scaled, 0.0)
    receipt: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_train_prefix_context_scaler.v1",
        "factor_columns": factor_columns,
        "train_row_count": int(selector.sum()),
        "median": median.tolist(),
        "iqr": scale.tolist(),
        "missing_policy": "explicit_mask_and_zero_only_after_scaling_for_tensor_transport",
        "fit_scope": "current_fold_training_prefix_only",
        "production_authority": False,
    }
    receipt["canonical_digest"] = canonical_digest(receipt)
    return scaled.astype(np.float32), observed, receipt


def audit_macro_product_coverage(
    *,
    coverage_report: Mapping[str, object],
    gap_ledger: Mapping[str, object],
) -> dict[str, object]:
    """Reduce the DataHub V90 grant to a fail-closed Round-3 receipt."""

    blockers: list[str] = []
    if coverage_report.get("consumer_contract_id") != ROUND3_MACRO_CONSUMER_CONTRACT_ID:
        blockers.append("macro_coverage_consumer_contract_mismatch")
    if coverage_report.get("status") != "passed" or gap_ledger.get("status") != "passed":
        blockers.append("macro_coverage_or_gap_report_not_passed")
    series = coverage_report.get("series_denominators")
    if not isinstance(series, Mapping) or set(series) != set(ADMITTED_MACRO_SERIES_IDS):
        blockers.append("macro_exact_six_series_denominator_mismatch")
    else:
        for series_id, raw in series.items():
            if not isinstance(raw, Mapping) or raw.get("delivered") != raw.get("required"):
                blockers.append(f"macro_series_incomplete:{series_id}")
    folds = coverage_report.get("fold_denominators")
    if not isinstance(folds, list) or len(folds) != len(COMPLETE_VALIDATION_YEARS):
        blockers.append("macro_five_fold_denominator_mismatch")
    else:
        for year, raw in zip(COMPLETE_VALIDATION_YEARS, folds, strict=True):
            if (
                not isinstance(raw, Mapping)
                or raw.get("test_start_period") != f"{year}-01"
                or raw.get("test_end_period") != f"{year}-12"
                or raw.get("delivered") != raw.get("required")
            ):
                blockers.append(f"macro_fold_incomplete:{year}")
    gaps = gap_ledger.get("gap_totals_by_reason")
    if not isinstance(gaps, Mapping) or any(int(cast(int, value)) != 0 for value in gaps.values()):
        blockers.append("macro_nonzero_historical_gap_ledger")
    payload: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_macro_coverage_audit.v1",
        "source_id": "datahub_macro_v90_exact_consumer_grant",
        "consumer_contract_id": ROUND3_MACRO_CONSUMER_CONTRACT_ID,
        "series_ids": list(ADMITTED_MACRO_SERIES_IDS),
        "complete_validation_years": list(COMPLETE_VALIDATION_YEARS),
        "interior_gap_count": len(blockers),
        "blocking": bool(blockers),
        "blockers": sorted(set(blockers)),
        "tail_scope": "fixed_through_2025_12;2026_preview_unscored",
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def build_market_cap_preflight_receipt(
    *,
    manifest: Mapping[str, object],
    coverage_report: Mapping[str, object],
    gap_ledger: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Bind the fixed monthly PIT cap surface and audit its scoped gaps."""

    blockers: list[str] = []
    if manifest.get("dataset_kind") != "stock_market_cap_monthly_pit":
        blockers.append("market_cap_dataset_kind_mismatch")
    if manifest.get("immutable") is not True or manifest.get("latest_alias_allowed") is not False:
        blockers.append("market_cap_fixed_version_policy_mismatch")
    if coverage_report.get("materialized_start_month") != "2018-01":
        blockers.append("market_cap_start_month_mismatch")
    if coverage_report.get("materialized_end_month") != "2025-12":
        blockers.append("market_cap_end_month_mismatch")
    if int(cast(int, coverage_report.get("materialized_month_count", 0))) != 96:
        blockers.append("market_cap_month_count_mismatch")
    if int(cast(int, coverage_report.get("interior_month_gap_count", 0))) != 0:
        blockers.append("market_cap_interior_month_gap")
    if "interior_symbol_month_gap_count" not in coverage_report:
        blockers.append("market_cap_symbol_month_gap_audit_missing")
    elif int(
        cast(int, coverage_report.get("interior_symbol_month_gap_count", 0))
    ) != 0:
        blockers.append("market_cap_interior_symbol_month_gap")
    if int(cast(int, coverage_report.get("tail_unmaterialized_month_count", 0))) != 0:
        blockers.append("market_cap_requested_scope_tail_gap")
    if int(cast(int, gap_ledger.get("blocking_admitted_scope_gap_count", 0))) != 0:
        blockers.append("market_cap_blocking_admitted_scope_gap")
    if coverage_report.get("latest_fallback_allowed") is not False:
        blockers.append("market_cap_latest_fallback_not_forbidden")
    if coverage_report.get("interpolation_allowed") is not False:
        blockers.append("market_cap_interpolation_not_forbidden")
    if coverage_report.get("research_ready_for_admitted_rows") is not True:
        blockers.append("market_cap_admitted_rows_not_ready")

    gap_classification_keys = (
        "never_admitted_symbol_month_gap_count",
        "prefix_symbol_month_gap_count",
        "interior_symbol_month_gap_count",
        "suffix_symbol_month_gap_count",
    )
    if any(key not in coverage_report for key in gap_classification_keys):
        blockers.append("market_cap_honest_gap_classification_missing")
        gap_classification: dict[str, int] = {}
    else:
        gap_classification = {
            key: int(cast(int, coverage_report.get(key, 0)))
            for key in gap_classification_keys
        }
        if sum(gap_classification.values()) != int(
            cast(int, coverage_report.get("honest_gap_row_count", 0))
        ):
            blockers.append("market_cap_honest_gap_classification_mismatch")
    gap_symbol_classification_keys = (
        "never_admitted_symbol_count",
        "prefix_gap_symbol_count",
        "interior_gap_symbol_count",
        "suffix_gap_symbol_count",
    )
    if any(key not in coverage_report for key in gap_symbol_classification_keys):
        blockers.append("market_cap_gap_symbol_classification_missing")
        gap_symbol_classification: dict[str, int] = {}
    else:
        gap_symbol_classification = {
            key: int(cast(int, coverage_report.get(key, 0)))
            for key in gap_symbol_classification_keys
        }

    audit: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_market_cap_coverage_audit.v1",
        "source_id": "datahub_stock_market_cap_monthly_pit_2018_2025",
        "dataset_version": str(manifest.get("dataset_version", "")),
        "interior_gap_count": len(blockers),
        "blocking": bool(blockers),
        "blockers": sorted(set(blockers)),
        "honest_non_admitted_gap_count": int(cast(int, gap_ledger.get("honest_non_admitted_gap_count", 0))),
        "honest_gap_classification": gap_classification,
        "honest_gap_symbol_classification": gap_symbol_classification,
        "freshness_scope": "requested_product_ends_2025_12;wall_clock_tail_is_not_a_round3_gap",
        "production_authority": False,
    }
    audit["canonical_digest"] = canonical_digest(audit)
    receipt: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_market_cap_binding.v1",
        "dataset_version": str(manifest.get("dataset_version", "")),
        "dataset_hash": str(manifest.get("dataset_hash", "")),
        "manifest_digest": str(manifest.get("canonical_digest", "")),
        "research_ready_for_admitted_rows": not blockers,
        "latest_fallback_allowed": False,
        "interpolation_allowed": False,
        "minimum_total_market_cap_cny": MINIMUM_TOTAL_MARKET_CAP_CNY,
        "honest_non_admitted_gap_count": audit["honest_non_admitted_gap_count"],
        "production_authority": False,
    }
    receipt["canonical_digest"] = canonical_digest(receipt)
    return receipt, audit


def audit_round3_materialized_input_bundle(
    *,
    stock_manifest: Mapping[str, object],
    stock_coverage: Mapping[str, object],
    stock_lineage: Mapping[str, object],
    timing_manifest: Mapping[str, object],
    timing_coverage: Mapping[str, object],
    timing_lineage: Mapping[str, object],
    macro_manifest: Mapping[str, object],
    macro_coverage: Mapping[str, object],
    macro_lineage: Mapping[str, object],
) -> dict[str, object]:
    """Bind all non-financial feature surfaces before any outcome is opened."""

    blockers: list[str] = []
    expected = (
        ("stock", stock_manifest, stock_coverage, "factor_count", 165, 85_051),
        ("timing", timing_manifest, timing_coverage, "tool_count", 7, 85_051),
        ("macro_context", macro_manifest, macro_coverage, "series_count", 6, 96),
    )
    for source_id, manifest, coverage, count_field, count, records in expected:
        if manifest.get("state") != "READY" or manifest.get(count_field) != count:
            blockers.append(f"{source_id}_surface_manifest_scope_mismatch")
        if manifest.get("record_count") != records:
            blockers.append(f"{source_id}_surface_record_count_mismatch")
        if (
            coverage.get("status") != "passed"
            or int(cast(int, coverage.get("interior_or_required_tail_gap_count", -1)))
            != 0
        ):
            blockers.append(f"{source_id}_surface_historical_gap")
    if stock_manifest.get("market_outcome_rows_read") != 0:
        blockers.append("stock_surface_outcome_rows_read")
    for source_id, manifest in (
        ("timing", timing_manifest),
        ("macro_context", macro_manifest),
    ):
        if manifest.get("forward_return_or_test_label_rows_read") != 0:
            blockers.append(f"{source_id}_surface_forward_label_rows_read")
    if stock_lineage.get("same_surface_for_both_strategies") is not True:
        blockers.append("stock_surface_not_shared_by_both_strategies")
    if timing_lineage.get("same_surface_for_both_strategies") is not True:
        blockers.append("timing_surface_not_shared_by_both_strategies")
    if macro_lineage.get("same_snapshot_for_both_strategies") is not True:
        blockers.append("macro_snapshot_not_shared_by_both_strategies")
    if macro_lineage.get("direct_stock_alpha_vote_allowed") is not False:
        blockers.append("macro_context_direct_stock_alpha_vote_not_forbidden")
    honest_gap_count = int(
        cast(int, stock_lineage.get("honest_non_admitted_lineage_gap_symbol_count", 0))
    )
    if honest_gap_count > 20:
        blockers.append("stock_honest_lineage_gap_quarantine_exceeds_limit")
    stock_artifacts = stock_manifest.get("artifacts")
    timing_parents = timing_manifest.get("parents")
    macro_parents = macro_manifest.get("parents")
    if (
        not isinstance(stock_artifacts, Mapping)
        or not isinstance(timing_parents, Mapping)
        or not isinstance(macro_parents, Mapping)
    ):
        blockers.append("round3_shared_coordinate_binding_missing")
    else:
        stock_coordinate_hash = str(stock_artifacts.get("coordinates.parquet", ""))
        timing_coordinate = timing_parents.get("coordinates")
        macro_coordinate = macro_parents.get("coordinates")
        timing_hash = (
            str(timing_coordinate.get("sha256", ""))
            if isinstance(timing_coordinate, Mapping)
            else ""
        )
        macro_hash = (
            str(macro_coordinate.get("sha256", ""))
            if isinstance(macro_coordinate, Mapping)
            else ""
        )
        if not stock_coordinate_hash or len(
            {stock_coordinate_hash, timing_hash, macro_hash}
        ) != 1:
            blockers.append("round3_shared_coordinate_hash_mismatch")
    payload: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_materialized_input_bundle_audit.v1",
        "source_id": "factorlab_round3_materialized_input_bundle",
        "stock_factor_count": 165,
        "timing_tool_count": 7,
        "macro_context_count": 6,
        "unique_model_input_count_after_financial_binding": 199,
        "honest_non_admitted_lineage_gap_symbol_count": honest_gap_count,
        "interior_gap_count": len(blockers),
        "blocking": bool(blockers),
        "blockers": sorted(set(blockers)),
        "forward_return_or_test_label_rows_read": 0,
        "same_inputs_for_both_strategies": True,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def audit_round3_strict_financial_surface(
    *,
    manifest: Mapping[str, object],
    coverage: Mapping[str, object],
    lineage: Mapping[str, object],
    expected_coordinate_sha256: str,
) -> dict[str, object]:
    """Reduce the FactorLab annual-financial materialization to one gate."""

    blockers: list[str] = []
    if (
        manifest.get("state") != "READY"
        or manifest.get("factor_count") != 21
        or manifest.get("record_count") != 85_051
    ):
        blockers.append("strict_financial_surface_manifest_scope_mismatch")
    if (
        coverage.get("status") != "passed"
        or coverage.get("factor_count") != 21
        or int(cast(int, coverage.get("interior_or_required_tail_gap_count", -1)))
        != 0
    ):
        blockers.append("strict_financial_surface_historical_gap")
    if lineage.get("same_surface_for_both_strategies") is not True:
        blockers.append("strict_financial_surface_not_shared_by_both_strategies")
    if lineage.get("quarterly_formula_redefinition_allowed") is not False:
        blockers.append("strict_financial_quarterly_formula_redefined")
    if lineage.get("alias_duplicate_model_vote_allowed") is not False:
        blockers.append("strict_financial_alias_duplicate_vote_allowed")
    if manifest.get("forward_return_or_test_label_rows_read") != 0:
        blockers.append("strict_financial_surface_forward_label_rows_read")
    parents = manifest.get("parents")
    coordinate = parents.get("coordinates") if isinstance(parents, Mapping) else None
    coordinate_hash = (
        str(coordinate.get("sha256", ""))
        if isinstance(coordinate, Mapping)
        else ""
    )
    if not expected_coordinate_sha256 or coordinate_hash != expected_coordinate_sha256:
        blockers.append("strict_financial_surface_coordinate_hash_mismatch")
    payload: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_round3_strict_financial_surface_audit.v1",
        "source_id": "factorlab_round3_strict_annual_financial_surface",
        "factor_count": 21,
        "record_count": int(cast(int, manifest.get("record_count", 0))),
        "interior_gap_count": len(blockers),
        "blocking": bool(blockers),
        "blockers": sorted(set(blockers)),
        "forward_return_or_test_label_rows_read": 0,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def evaluate_round3_execution_preflight(
    *,
    financial_manifest: Mapping[str, object] | None,
    financial_certification: Mapping[str, object] | None,
    macro_manifest: Mapping[str, object] | None,
    macro_certification: Mapping[str, object] | None,
    market_cap_receipt: Mapping[str, object],
    continuity_audits: Sequence[Mapping[str, object]],
    candidate_admission: Mapping[str, object],
) -> dict[str, object]:
    """Evaluate start readiness without opening factors, labels, or outcomes."""

    validate_round3_candidate_admission_contract(candidate_admission)
    blockers: list[str] = []
    financial_binding = _validate_data_binding(
        manifest=financial_manifest,
        certification=financial_certification,
        expected_contract=STRICT_ANNUAL_FINANCIAL_CONSUMER_CONTRACT_ID,
        expected_product_kind="issuer_financial_fact",
    )
    if financial_binding["status"] != "ready":
        blockers.extend(cast(list[str], financial_binding["blockers"]))
    macro_binding = _validate_data_binding(
        manifest=macro_manifest,
        certification=macro_certification,
        expected_contract=ROUND3_MACRO_CONSUMER_CONTRACT_ID,
        expected_product_kind="macro_fundamental_timeseries",
    )
    if macro_binding["status"] != "ready":
        blockers.extend(cast(list[str], macro_binding["blockers"]))
    if market_cap_receipt.get("research_ready_for_admitted_rows") is not True:
        blockers.append("monthly_pit_market_cap_admitted_surface_not_ready")
    if market_cap_receipt.get("latest_fallback_allowed") is not False:
        blockers.append("monthly_pit_market_cap_latest_fallback_not_forbidden")
    for audit in continuity_audits:
        if audit.get("blocking") is True or int(cast(int, audit.get("interior_gap_count", 0))) > 0:
            blockers.append("historical_interior_gap:" + str(audit.get("source_id", "unknown")))
    blockers = sorted(set(blockers))
    payload: dict[str, object] = {
        "schema_id": ROUND3_EXECUTION_PREFLIGHT_SCHEMA_ID,
        "trial_id": ROUND3_EXECUTION_TRIAL_ID,
        "status": "ready" if not blockers else "blocked",
        "financial_binding": financial_binding,
        "macro_binding": macro_binding,
        "market_cap_receipt_digest": str(market_cap_receipt.get("canonical_digest", "")),
        "continuity_audit_count": len(continuity_audits),
        "candidate_admission_digest": str(candidate_admission.get("canonical_digest", "")),
        "blockers": blockers,
        "formal_metric_pipeline_observations_read": False,
        "market_outcome_rows_read": 0,
        "battle_started": False,
        "winner_strategy_id": None,
        "authority": round3_execution_false_authority(),
    }
    payload["canonical_digest"] = canonical_digest(payload)
    validate_round3_execution_preflight(payload)
    return payload


def validate_round3_execution_preflight(payload: Mapping[str, object]) -> None:
    """Reject a preflight that claims readiness or outcome use inconsistently."""

    if payload.get("schema_id") != ROUND3_EXECUTION_PREFLIGHT_SCHEMA_ID:
        raise ValueError("round3_execution_preflight_schema_mismatch")
    if payload.get("trial_id") != ROUND3_EXECUTION_TRIAL_ID:
        raise ValueError("round3_execution_preflight_trial_mismatch")
    blockers = payload.get("blockers")
    if not isinstance(blockers, list) or not all(
        isinstance(item, str) and item for item in blockers
    ):
        raise ValueError("round3_execution_preflight_blockers_invalid")
    expected_status = "ready" if not blockers else "blocked"
    if payload.get("status") != expected_status:
        raise ValueError("round3_execution_preflight_status_inconsistent")
    if (
        payload.get("formal_metric_pipeline_observations_read") is not False
        or payload.get("market_outcome_rows_read") != 0
        or payload.get("battle_started") is not False
        or payload.get("winner_strategy_id") is not None
    ):
        raise ValueError("round3_execution_preflight_opened_outcome_or_battle")
    for field in ("financial_binding", "macro_binding"):
        binding = payload.get(field)
        if not isinstance(binding, Mapping) or binding.get("status") not in {
            "ready",
            "blocked",
        }:
            raise ValueError(f"round3_execution_preflight_{field}_invalid")
    _validate_false_authority(payload.get("authority"), "round3_execution_preflight")
    _validate_digest(payload)


def _validate_data_binding(
    *,
    manifest: Mapping[str, object] | None,
    certification: Mapping[str, object] | None,
    expected_contract: str,
    expected_product_kind: str,
) -> dict[str, object]:
    prefix = "strict_financial" if expected_product_kind == "issuer_financial_fact" else "round3_macro"
    blockers: list[str] = []
    if manifest is None or certification is None:
        blockers.append(f"{prefix}_fixed_certified_artifact_missing")
        return {
            "status": "blocked",
            "dataset_version": "",
            "dataset_hash": "",
            "consumer_contract_id": expected_contract,
            "blockers": blockers,
        }
    version = str(manifest.get("dataset_version", ""))
    dataset_hash = str(manifest.get("dataset_hash", ""))
    manifest_kind = str(manifest.get("dataset_kind", manifest.get("product_kind", "")))
    certification_version = str(
        certification.get(
            "dataset_version", certification.get("target_dataset_version", "")
        )
    )
    contract = str(
        certification.get(
            "consumer_contract_id",
            certification.get("consumer_contract", manifest.get("consumer_contract_id", "")),
        )
    )
    if not version or version != certification_version:
        blockers.append(f"{prefix}_manifest_certification_version_mismatch")
    if not dataset_hash:
        blockers.append(f"{prefix}_dataset_hash_missing")
    if manifest_kind != expected_product_kind:
        blockers.append(f"{prefix}_product_kind_mismatch")
    if contract != expected_contract:
        blockers.append(f"{prefix}_consumer_contract_mismatch")
    if certification.get("capability_decision") != "granted":
        blockers.append(f"{prefix}_capability_not_granted")
    if manifest.get("latest_alias_allowed") is True:
        blockers.append(f"{prefix}_latest_alias_forbidden")
    if expected_product_kind == "issuer_financial_fact":
        forms = manifest.get("included_filing_forms")
        if forms is not None and forms != ["annual"]:
            blockers.append("strict_financial_annual_only_scope_mismatch")
        floor = manifest.get("minimum_total_market_cap_cny")
        if floor is not None and floor != MINIMUM_TOTAL_MARKET_CAP_CNY:
            blockers.append("strict_financial_market_cap_floor_mismatch")
        if manifest.get("first_release_semantics") is not True:
            blockers.append("strict_financial_first_release_semantics_not_proven")
    return {
        "status": "ready" if not blockers else "blocked",
        "dataset_version": version,
        "dataset_hash": dataset_hash,
        "consumer_contract_id": contract,
        "blockers": blockers,
    }


def _validate_false_authority(value: object, prefix: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(_FALSE_AUTHORITY):
        raise ValueError(f"{prefix}_authority_shape_invalid")
    if any(item is not False for item in value.values()):
        raise ValueError(f"{prefix}_authority_must_be_false")


def _validate_digest(payload: Mapping[str, object]) -> None:
    expected = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    if payload.get("canonical_digest") != expected:
        raise ValueError("canonical_digest_mismatch")
