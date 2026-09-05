# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportIndexIssue=false
"""OT1 causal carrier-basis and stock-exposure materialization primitives."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID = "factorlab.orthogonal_index_timing_transport_OT1@1.1"
LOOKBACK = 120
MIN_OBSERVATIONS = 96
HALF_MIN_OBSERVATIONS = 40
CROSS_FIT_FOLDS = 5
MAX_CONDITION_NUMBER = 1.0e8
FULL_VARIANT_ID = "full_reference"
MARKET_FACTOR_ID = "orthogonal_market_cloudridge_v1"
SIZE_FACTOR_ID = "orthogonal_size_small_minus_large_v1"
SMALL_TARGET_ID = "SIZE_FACTOR_CORE:SMALL"
LARGE_TARGET_ID = "SIZE_FACTOR_CORE:LARGE"


@dataclass(frozen=True, slots=True)
class Projection:
    intercept: float
    coefficients: np.ndarray
    residual_current: float
    observation_count: int
    design_rank: int
    condition_number: float
    orthogonality_max_abs: float
    reconstruction_max_abs_error: float


def variant_ids() -> tuple[str, ...]:
    return (FULL_VARIANT_ID, *(f"crossfit_fold_{fold}" for fold in range(CROSS_FIT_FOLDS)))


def stock_fold(symbol_positions: np.ndarray) -> np.ndarray:
    return np.asarray(symbol_positions, dtype=np.int64) % CROSS_FIT_FOLDS


def _fit_projection(
    dependent_history: np.ndarray,
    regressor_history: np.ndarray,
    dependent_current: float,
    regressor_current: np.ndarray,
    *,
    minimum_observations: int = MIN_OBSERVATIONS,
) -> Projection | None:
    y = np.asarray(dependent_history, dtype=np.float64)
    x = np.asarray(regressor_history, dtype=np.float64)
    current_x = np.asarray(regressor_current, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if current_x.ndim != 1 or current_x.shape[0] != x.shape[1]:
        raise ValueError("OT1_projection_current_regressor_shape_mismatch")
    valid = np.isfinite(y) & np.isfinite(x).all(axis=1)
    if int(valid.sum()) < minimum_observations or not np.isfinite(dependent_current) or not np.isfinite(current_x).all():
        return None
    design = np.column_stack([np.ones(int(valid.sum()), dtype=np.float64), x[valid]])
    rank = int(np.linalg.matrix_rank(design))
    condition = float(np.linalg.cond(design))
    if rank != design.shape[1] or not np.isfinite(condition) or condition > MAX_CONDITION_NUMBER:
        return None
    coefficients, *_ = np.linalg.lstsq(design, y[valid], rcond=None)
    residual_history = y[valid] - design @ coefficients
    scale = max(float(np.linalg.norm(residual_history)), 1.0e-12)
    orthogonality = float(np.max(np.abs(design.T @ residual_history)) / scale)
    reconstructed = design @ coefficients + residual_history
    return Projection(
        intercept=float(coefficients[0]),
        coefficients=np.asarray(coefficients[1:], dtype=np.float64),
        residual_current=float(dependent_current - coefficients[0] - current_x @ coefficients[1:]),
        observation_count=int(valid.sum()),
        design_rank=rank,
        condition_number=condition,
        orthogonality_max_abs=orthogonality,
        reconstruction_max_abs_error=float(np.max(np.abs(reconstructed - y[valid]))),
    )


def materialize_equal_weight_carriers(
    daily_returns: np.ndarray,
    calendar: np.ndarray,
    membership: pd.DataFrame,
    target_ids: Sequence[str],
    *,
    minimum_members: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Expand effective-dated membership into full and five cross-fit returns."""

    if daily_returns.ndim != 2 or len(calendar) != daily_returns.shape[0]:
        raise ValueError("OT1_carrier_daily_return_shape_mismatch")
    required = {"effective_date", "target_id", "symbol_position"}
    if not required.issubset(membership.columns):
        raise ValueError("OT1_carrier_membership_schema_mismatch")
    variants = variant_ids()
    output = np.full((len(variants), len(calendar), len(target_ids)), np.nan, dtype=np.float64)
    counts = np.zeros((len(variants), len(calendar), len(target_ids)), dtype=np.int16)
    calendar_index = {pd.Timestamp(day): index for index, day in enumerate(calendar)}
    for target_index, target_id in enumerate(target_ids):
        local = membership.loc[membership["target_id"].eq(target_id)].copy()
        local["effective_date"] = pd.to_datetime(local["effective_date"])
        groups = [(pd.Timestamp(date), group) for date, group in local.groupby("effective_date", sort=True)]
        for group_index, (effective_date, group) in enumerate(groups):
            start = calendar_index.get(effective_date)
            if start is None:
                continue
            if group_index + 1 < len(groups):
                next_start = calendar_index.get(groups[group_index + 1][0], len(calendar))
                end = int(next_start) - 1
            else:
                end = len(calendar) - 1
            if end < start:
                continue
            positions = np.unique(group["symbol_position"].to_numpy(dtype=np.int64))
            for variant_index, variant_id in enumerate(variants):
                selected = positions
                if variant_id != FULL_VARIANT_ID:
                    fold = int(variant_id.rsplit("_", 1)[1])
                    selected = positions[stock_fold(positions) != fold]
                if len(selected) < minimum_members:
                    continue
                values = daily_returns[start : end + 1, selected]
                finite_count = np.isfinite(values).sum(axis=1)
                carrier = np.divide(
                    np.nansum(values, axis=1),
                    finite_count,
                    out=np.full(end - start + 1, np.nan, dtype=np.float64),
                    where=finite_count >= minimum_members,
                )
                output[variant_index, start : end + 1, target_index] = carrier
                counts[variant_index, start : end + 1, target_index] = finite_count.astype(np.int16)
    return output, counts


def build_causal_basis(
    raw_carriers: np.ndarray,
    calendar: np.ndarray,
    industry_target_ids: Sequence[str],
) -> tuple[np.ndarray, pd.DataFrame, pd.DataFrame]:
    """Create M, one S, and industry residual returns with t-1 fits."""

    expected_targets = 3 + len(industry_target_ids)
    if raw_carriers.ndim != 3 or raw_carriers.shape[2] != expected_targets:
        raise ValueError("OT1_raw_carrier_target_shape_mismatch")
    variants = variant_ids()
    factor_ids = (MARKET_FACTOR_ID, SIZE_FACTOR_ID, *industry_target_ids)
    basis = np.full((len(variants), len(calendar), len(factor_ids)), np.nan, dtype=np.float64)
    basis_rows: list[dict[str, object]] = []
    receipt_rows: list[dict[str, object]] = []
    for variant_index, variant_id in enumerate(variants):
        market = raw_carriers[variant_index, :, 0]
        small = raw_carriers[variant_index, :, 1]
        large = raw_carriers[variant_index, :, 2]
        basis[variant_index, :, 0] = market
        for day in range(LOOKBACK, len(calendar)):
            history = slice(day - LOOKBACK, day)
            small_projection = _fit_projection(
                small[history], market[history], small[day], np.asarray([market[day]]),
            )
            large_projection = _fit_projection(
                large[history], market[history], large[day], np.asarray([market[day]]),
            )
            if small_projection is not None and large_projection is not None:
                basis[variant_index, day, 1] = small_projection.residual_current - large_projection.residual_current
                for leg, projection in (("small_on_market", small_projection), ("large_on_market", large_projection)):
                    receipt_rows.append(
                        _projection_row(variant_id, calendar, day, leg, projection, [MARKET_FACTOR_ID])
                    )
        size = basis[variant_index, :, 1]
        for industry_offset, target_id in enumerate(industry_target_ids):
            raw_index = 3 + industry_offset
            basis_index = 2 + industry_offset
            industry = raw_carriers[variant_index, :, raw_index]
            for day in range(LOOKBACK, len(calendar)):
                history = slice(day - LOOKBACK, day)
                projection = _fit_projection(
                    industry[history],
                    np.column_stack([market[history], size[history]]),
                    industry[day],
                    np.asarray([market[day], size[day]]),
                )
                if projection is None:
                    continue
                basis[variant_index, day, basis_index] = projection.residual_current
                receipt_rows.append(
                    _projection_row(
                        variant_id,
                        calendar,
                        day,
                        f"{target_id}_on_market_size",
                        projection,
                        [MARKET_FACTOR_ID, SIZE_FACTOR_ID],
                    )
                )
        for factor_index, factor_id in enumerate(factor_ids):
            values = basis[variant_index, :, factor_index]
            if factor_index == 0:
                raw_values = market
            elif factor_index == 1:
                raw_values = small - large
            else:
                raw_values = raw_carriers[variant_index, :, factor_index + 1]
            for day in np.flatnonzero(np.isfinite(values)):
                basis_rows.append(
                    {
                        "variant_id": variant_id,
                        "trading_day": pd.Timestamp(calendar[day]),
                        "day_position": int(day),
                        "factor_id": factor_id,
                        "raw_return": float(raw_values[day]),
                        "orthogonal_return": float(values[day]),
                        "available": True,
                        "uses_future": False,
                    }
                )
    return basis, pd.DataFrame(basis_rows), pd.DataFrame(receipt_rows)


def _projection_row(
    variant_id: str,
    calendar: np.ndarray,
    day: int,
    projection_id: str,
    projection: Projection,
    regressor_ids: Sequence[str],
) -> dict[str, object]:
    row: dict[str, object] = {
        "variant_id": variant_id,
        "trading_day": pd.Timestamp(calendar[day]),
        "fit_end_date": pd.Timestamp(calendar[day - 1]),
        "projection_id": projection_id,
        "regressor_ids": "|".join(regressor_ids),
        "intercept": projection.intercept,
        "observation_count": projection.observation_count,
        "design_rank": projection.design_rank,
        "condition_number": projection.condition_number,
        "orthogonality_max_abs": projection.orthogonality_max_abs,
        "reconstruction_max_abs_error": projection.reconstruction_max_abs_error,
        "uses_future": False,
    }
    for index, coefficient in enumerate(projection.coefficients):
        row[f"coefficient_{index}"] = float(coefficient)
    return row


def membership_tuples(
    membership: pd.DataFrame,
    accepted_industry_ids: Sequence[str],
) -> dict[pd.Timestamp, dict[int, tuple[str, ...]]]:
    local = membership.loc[membership["target_id"].isin(accepted_industry_ids)].copy()
    local["asof_date"] = pd.to_datetime(local["asof_date"])
    output: dict[pd.Timestamp, dict[int, tuple[str, ...]]] = {}
    for date, group in local.groupby("asof_date", sort=True):
        mapping: defaultdict[int, list[str]] = defaultdict(list)
        for row in group[["symbol_position", "target_id"]].itertuples(index=False):
            mapping[int(row.symbol_position)].append(str(row.target_id))
        output[pd.Timestamp(date)] = {position: tuple(sorted(set(values))) for position, values in mapping.items()}
    return output


def fit_stock_exposures(
    daily_returns: np.ndarray,
    listed_mask: np.ndarray,
    basis: np.ndarray,
    calendar: np.ndarray,
    symbols: np.ndarray,
    decision_frame: pd.DataFrame,
    industry_target_ids: Sequence[str],
    industry_membership: Mapping[pd.Timestamp, Mapping[int, tuple[str, ...]]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Fit weekly cross-fit stock exposures and causal next-interval epsilon."""

    factor_index = {factor_id: index for index, factor_id in enumerate((MARKET_FACTOR_ID, SIZE_FACTOR_ID, *industry_target_ids))}
    calendar_index = {pd.Timestamp(day): index for index, day in enumerate(calendar)}
    decisions = decision_frame.sort_values(["asof_date", "effective_date"], kind="stable").drop_duplicates("asof_date")
    exposure_rows: list[dict[str, object]] = []
    industry_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    epsilon = np.full_like(daily_returns, np.nan, dtype=np.float32)
    folds = stock_fold(np.arange(len(symbols), dtype=np.int64))
    for decision_number, decision in enumerate(decisions.itertuples(index=False)):
        asof_date = pd.Timestamp(decision.asof_date)
        effective_date = pd.Timestamp(decision.effective_date)
        day = calendar_index.get(asof_date)
        effective_day = calendar_index.get(effective_date)
        if day is None or effective_day is None:
            continue
        next_effective = len(calendar)
        if decision_number + 1 < len(decisions):
            next_effective = calendar_index.get(pd.Timestamp(decisions.iloc[decision_number + 1]["effective_date"]), len(calendar))
        if day < LOOKBACK - 1:
            continue
        window = np.arange(day - LOOKBACK + 1, day + 1, dtype=np.int64)
        current_membership = industry_membership.get(asof_date, {})
        eligible = np.flatnonzero(listed_mask[day])
        groups: defaultdict[tuple[int, tuple[str, ...]], list[int]] = defaultdict(list)
        for position in eligible:
            groups[(int(folds[position]), tuple(current_membership.get(int(position), ())))].append(int(position))
        available_count = 0
        unavailable_count = 0
        reliability_values: list[float] = []
        for (fold, industry_ids), positions_list in sorted(groups.items()):
            positions = np.asarray(positions_list, dtype=np.int64)
            columns = [factor_index[MARKET_FACTOR_ID], factor_index[SIZE_FACTOR_ID]]
            columns.extend(factor_index[target_id] for target_id in industry_ids)
            x = basis[fold + 1, window][:, columns]
            common_factor = np.isfinite(x).all(axis=1)
            design = np.column_stack([np.ones(len(window), dtype=np.float64), x])
            design_valid = design[common_factor]
            rank = int(np.linalg.matrix_rank(design_valid)) if len(design_valid) else 0
            condition = float(np.linalg.cond(design_valid)) if rank == design.shape[1] else np.inf
            group_coefficients: dict[int, tuple[np.ndarray, int, float, float, float, float]] = {}
            if rank == design.shape[1] and np.isfinite(condition) and condition <= MAX_CONDITION_NUMBER:
                stock_valid = listed_mask[window][:, positions] & np.isfinite(daily_returns[window][:, positions])
                valid_count = (stock_valid & common_factor[:, None]).sum(axis=0)
                complete = valid_count == int(common_factor.sum())
                if complete.any() and int(common_factor.sum()) >= MIN_OBSERVATIONS:
                    complete_positions = positions[complete]
                    batch = _fit_stock_batch(
                        design[common_factor],
                        daily_returns[window][:, complete_positions][common_factor],
                        condition,
                    )
                    if batch is not None:
                        coefficients, r_squared, stability, reliability, residual_scale = batch
                        for column, position in enumerate(complete_positions):
                            group_coefficients[int(position)] = (
                                coefficients[:, column],
                                int(common_factor.sum()),
                                float(r_squared[column]),
                                float(stability[column]),
                                float(reliability[column]),
                                float(residual_scale[column]),
                            )
                for position in positions[~complete]:
                    valid = common_factor & listed_mask[window, position] & np.isfinite(daily_returns[window, position])
                    fitted = _fit_stock_single(design, daily_returns[window, position], valid)
                    if fitted is not None:
                        group_coefficients[int(position)] = fitted
            apply_days = np.arange(effective_day, min(int(next_effective), len(calendar)), dtype=np.int64)
            for position in positions:
                fitted = group_coefficients.get(int(position))
                if fitted is None:
                    unavailable_count += 1
                    continue
                coefficients, observations, r_squared, stability, reliability, residual_scale = fitted
                available_count += 1
                reliability_values.append(reliability)
                exposure_rows.append(
                    {
                        "asof_date": asof_date,
                        "effective_date": effective_date,
                        "symbol": str(symbols[position]),
                        "symbol_position": int(position),
                        "crossfit_fold": fold,
                        "intercept": float(coefficients[0]),
                        "beta_market": float(coefficients[1]),
                        "beta_size": float(coefficients[2]),
                        "industry_exposure_count": len(industry_ids),
                        "observation_count": observations,
                        "design_rank": rank,
                        "condition_number": condition,
                        "r_squared": r_squared,
                        "beta_half_stability": stability,
                        "residual_scale": residual_scale,
                        "reliability": reliability,
                        "available": True,
                        "uses_future": False,
                    }
                )
                for industry_offset, target_id in enumerate(industry_ids):
                    industry_rows.append(
                        {
                            "asof_date": asof_date,
                            "effective_date": effective_date,
                            "symbol": str(symbols[position]),
                            "symbol_position": int(position),
                            "crossfit_fold": fold,
                            "industry_factor_id": target_id,
                            "beta_industry": float(coefficients[3 + industry_offset]),
                            "family_vote_weight": 1.0 / len(industry_ids),
                            "reliability": reliability,
                            "available": True,
                            "uses_future": False,
                        }
                    )
                if len(apply_days):
                    apply_x = basis[fold + 1, apply_days][:, columns]
                    apply_design = np.column_stack([np.ones(len(apply_days), dtype=np.float64), apply_x])
                    observed = daily_returns[apply_days, position]
                    valid_apply = (
                        np.isfinite(apply_design).all(axis=1)
                        & np.isfinite(observed)
                        & listed_mask[apply_days, position]
                    )
                    residual = np.full(len(apply_days), np.nan, dtype=np.float64)
                    residual[valid_apply] = observed[valid_apply] - apply_design[valid_apply] @ coefficients
                    epsilon[apply_days, position] = residual.astype(np.float32)
        summary_rows.append(
            {
                "asof_date": asof_date,
                "effective_date": effective_date,
                "eligible_stock_count": len(eligible),
                "available_exposure_count": available_count,
                "unavailable_exposure_count": unavailable_count,
                "coverage": available_count / len(eligible) if len(eligible) else 0.0,
                "mean_reliability": float(np.mean(reliability_values)) if reliability_values else np.nan,
                "uses_future": False,
            }
        )
    return pd.DataFrame(exposure_rows), pd.DataFrame(industry_rows), pd.DataFrame(summary_rows), epsilon


def _fit_stock_single(
    design: np.ndarray,
    dependent: np.ndarray,
    valid: np.ndarray,
) -> tuple[np.ndarray, int, float, float, float, float] | None:
    observations = int(valid.sum())
    if observations < MIN_OBSERVATIONS:
        return None
    local_x = design[valid]
    local_y = dependent[valid].astype(np.float64)
    rank = int(np.linalg.matrix_rank(local_x))
    condition = float(np.linalg.cond(local_x))
    if rank != local_x.shape[1] or not np.isfinite(condition) or condition > MAX_CONDITION_NUMBER:
        return None
    coefficients, *_ = np.linalg.lstsq(local_x, local_y, rcond=None)
    residual = local_y - local_x @ coefficients
    total = local_y - float(np.mean(local_y))
    total_ss = float(total @ total)
    residual_ss = float(residual @ residual)
    r_squared = 1.0 - residual_ss / total_ss if total_ss > 0.0 else 0.0
    split = len(local_y) // 2
    if split < HALF_MIN_OBSERVATIONS or len(local_y) - split < HALF_MIN_OBSERVATIONS:
        return None
    first, *_ = np.linalg.lstsq(local_x[:split], local_y[:split], rcond=None)
    second, *_ = np.linalg.lstsq(local_x[split:], local_y[split:], rcond=None)
    denominator = max(float(np.linalg.norm(coefficients[1:])), 1.0e-6)
    drift = float(np.linalg.norm(first[1:] - second[1:]) / denominator)
    stability = 1.0 / (1.0 + drift)
    coverage = min(observations / LOOKBACK, 1.0)
    condition_reliability = 1.0 / (1.0 + max(np.log10(max(condition, 1.0)), 0.0))
    reliability = min(coverage, stability, condition_reliability)
    residual_scale = float(np.std(residual, ddof=0))
    return coefficients, observations, r_squared, stability, reliability, residual_scale


def _fit_stock_batch(
    design: np.ndarray,
    dependent: np.ndarray,
    condition_number: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    if len(design) < MIN_OBSERVATIONS or dependent.ndim != 2 or dependent.shape[0] != len(design):
        return None
    split = len(design) // 2
    if split < HALF_MIN_OBSERVATIONS or len(design) - split < HALF_MIN_OBSERVATIONS:
        return None
    coefficients, *_ = np.linalg.lstsq(design, dependent, rcond=None)
    residual = dependent - design @ coefficients
    centered = dependent - np.mean(dependent, axis=0, keepdims=True)
    total_ss = np.sum(centered * centered, axis=0)
    residual_ss = np.sum(residual * residual, axis=0)
    r_squared = np.divide(
        total_ss - residual_ss,
        total_ss,
        out=np.zeros_like(total_ss, dtype=np.float64),
        where=total_ss > 0.0,
    )
    first, *_ = np.linalg.lstsq(design[:split], dependent[:split], rcond=None)
    second, *_ = np.linalg.lstsq(design[split:], dependent[split:], rcond=None)
    denominator = np.maximum(np.linalg.norm(coefficients[1:], axis=0), 1.0e-6)
    drift = np.linalg.norm(first[1:] - second[1:], axis=0) / denominator
    stability = 1.0 / (1.0 + drift)
    coverage = min(len(design) / LOOKBACK, 1.0)
    condition_reliability = 1.0 / (1.0 + max(np.log10(max(condition_number, 1.0)), 0.0))
    reliability = np.minimum(np.minimum(coverage, stability), condition_reliability)
    residual_scale = np.std(residual, axis=0, ddof=0)
    return coefficients, r_squared, stability, reliability, residual_scale


def build_contract(*, bindings: Mapping[str, str]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": SCHEMA_ID,
        "status": "result_free_OT1_v1_1_frozen_controller_execution_authorized",
        "issue_ref": "bd://fl-od40m",
        "pre_result_incident": {
            "rejected_contract": "factorlab.orthogonal_index_timing_transport_OT1@1.0",
            "reason": "REAKA_qfq_stock_return_tensor_did_not_reconstruct_authoritative_raw_CloudRidge_return",
            "observed_market_correlation": 0.9168711631805089,
            "scientific_or_economic_authority": False,
        },
        "data_usage": {
            "2007_2008_prefix": "warmup_only",
            "2009_2020": "consumed_development_material_result_free_reconstruction",
            "post_2020_rows_allowed": 0,
            "fresh_oos": False,
            "oracle_or_forward_outcome_read_allowed": False,
        },
        "input_allowlist": [
            "shared_calendar_and_symbol_identity",
            "DataHub_authoritative_raw_daily_stock_bars_2007_2020",
            "PIT_total_market_cap_listing_mask",
            "V9_CloudRidge_effective_membership_and_daily_return",
            "B7_extended_weekly_membership_only",
            "accepted_condensation_registry",
        ],
        "denylist": [
            "FINAL_V2_oracle_and_gap_ledgers",
            "B7_labels_candidate_materials_metrics_weights_and_scorecards",
            "all_forward_returns_and_H1_H5_H20_H60_labels",
            "all_timing_tool_outputs",
            "all_strategy_and_model_outputs",
        ],
        "basis": {
            "lookback_sessions": LOOKBACK,
            "minimum_observations": MIN_OBSERVATIONS,
            "order": ["market", "single_small_minus_large_size", "accepted_dynamic_industries", "stock_idiosyncratic"],
            "market": "authoritative_V9_CloudRidge_equal_weight_return",
            "size": "small_and_large_each_projected_on_market_then_small_residual_minus_large_residual",
            "industry": "each_accepted_core_projected_on_market_and_size",
            "fit_window": "strictly_through_t_minus_1_for_factor_return_at_t",
            "return_carrier_rescaling": "forbidden",
        },
        "stock_exposure": {
            "cadence": "authoritative_weekly_condensation_asof",
            "fit_window": "120_sessions_through_asof_t_close",
            "effective": "next_trading_session",
            "cross_fit_folds": CROSS_FIT_FOLDS,
            "fold_rule": "symbol_position_mod_5",
            "carrier_excludes_entire_stock_fold": True,
            "industry_exposures": "all_current_accepted_dynamic_memberships_preserved_as_vector",
            "reliability": "minimum_of_coverage_half_beta_stability_and_condition_reliability",
            "epsilon": "next_interval_out_of_fit_residual_using_prior_weekly_coefficients",
        },
        "numerical_gate": {
            "solver": "complete_case_OLS_lstsq_with_intercept",
            "maximum_condition_number": MAX_CONDITION_NUMBER,
            "rank_deficiency": "fail_closed",
            "formal_and_isolated_byte_replay_required": True,
            "CPU_ROCm_benchmark_required": True,
        },
        "outputs": [
            "daily_factor_basis.parquet",
            "basis_projection_receipts.parquet",
            "weekly_stock_exposures.parquet",
            "weekly_stock_industry_exposures.parquet",
            "exposure_decision_summary.parquet",
            "daily_stock_idiosyncratic_returns.npz",
            "output_manifest.json",
        ],
        "next_checkpoint": "user_review_before_OT1_closeout_or_OT2_freeze",
        "bindings": dict(sorted(bindings.items())),
        "authority": {
            "OT1_execution_allowed": True,
            "OT2_execution_allowed": False,
            "factor_admission_allowed": False,
            "strategy_mutation_allowed": False,
            "model_training_allowed": False,
            "production_authority": False,
        },
        "fresh_oos": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def validate_contract(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body):
        blockers.append("OT1_contract_digest_mismatch")
    if payload.get("schema_id") != SCHEMA_ID:
        blockers.append("OT1_contract_schema_mismatch")
    authority = payload.get("authority")
    if not isinstance(authority, Mapping) or authority.get("OT1_execution_allowed") is not True:
        blockers.append("OT1_execution_not_authorized")
    elif any(
        authority.get(field) is not False
        for field in (
            "OT2_execution_allowed",
            "factor_admission_allowed",
            "strategy_mutation_allowed",
            "model_training_allowed",
            "production_authority",
        )
    ):
        blockers.append("OT1_downstream_authority_fail_open")
    return blockers


__all__ = [
    "CROSS_FIT_FOLDS",
    "FULL_VARIANT_ID",
    "HALF_MIN_OBSERVATIONS",
    "LARGE_TARGET_ID",
    "LOOKBACK",
    "MARKET_FACTOR_ID",
    "MAX_CONDITION_NUMBER",
    "MIN_OBSERVATIONS",
    "SCHEMA_ID",
    "SIZE_FACTOR_ID",
    "SMALL_TARGET_ID",
    "build_causal_basis",
    "build_contract",
    "fit_stock_exposures",
    "materialize_equal_weight_carriers",
    "membership_tuples",
    "stock_fold",
    "validate_contract",
    "variant_ids",
]
