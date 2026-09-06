# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportOperatorIssue=false
"""Signal-only timing states for orthogonal factor pseudo-indexes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from factor_lab.filtering.cloudridge_3_0_hybrid_filter_bank import butterworth_bandpass_component
from factor_lab.filtering.timing_validation import FilterSpec, apply_filter_spec, signal_from_filtered
from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID = "factorlab.orthogonal_factor_timing_state@1.1"
NAKED_BASELINE_ID = "naked_residual_level_follow_control_v1"
COST_BPS = 7.0


@dataclass(frozen=True, slots=True)
class ToolCapability:
    tool_id: str
    method_family_id: str
    warmup_bars: int
    status: str
    reason: str


CAPABILITIES = (
    ToolCapability("laplace_iir_mixed_bandpass", "causal_bandpass_mixed", 120, "eligible_representative", "daily_close_like"),
    ToolCapability("laplace_iir_lowpass", "causal_lowpass_state", 225, "eligible_representative", "daily_close_like"),
    ToolCapability("butterworth_clean_bandpass", "causal_bandpass_clean", 171, "eligible_representative", "daily_close_like"),
    ToolCapability(
        "causal_haar_wavelet_bandpass",
        "multiscale_basis",
        128,
        "eligible_representative",
        "daily_close_like_lower_complexity_representative",
    ),
    ToolCapability("bollinger_volatility_channel", "volatility_channel", 20, "eligible_representative", "daily_close_like"),
    ToolCapability("causal_trendline_channel", "graph_structure", 40, "eligible_representative", "daily_close_like"),
    ToolCapability("simple_moving_average_trend", "moving_average_trend", 60, "eligible_representative", "daily_close_like"),
    ToolCapability(
        "r3_nested_moving_average_component",
        "causal_bandpass_mixed",
        16,
        "deduplicated",
        "same_family_as_laplace_iir_mixed_bandpass",
    ),
    ToolCapability("rolling_fourier_bandpass", "multiscale_basis", 256, "deduplicated", "same_family_as_causal_haar_wavelet_bandpass"),
    ToolCapability("donchian_price_channel", "price_channel", 20, "incompatible", "requires_real_OHLC_not_factor_pseudo_close"),
    ToolCapability(
        "frequency_selective_bollinger_channel",
        "volatility_channel",
        512,
        "incompatible",
        "native_15m_without_daily_transport_receipt",
    ),
    ToolCapability(
        "butterworth_lowpass_residual_envelope",
        "volatility_channel",
        512,
        "incompatible",
        "native_15m_without_daily_transport_receipt",
    ),
    ToolCapability(
        "causal_asymmetric_arc_state_space_envelope",
        "state_space_filter",
        512,
        "incompatible",
        "native_15m_without_daily_transport_receipt",
    ),
    ToolCapability(
        "paper_kernel_multiscale_trend_router",
        "hybrid_router",
        512,
        "incompatible",
        "native_15m_without_daily_transport_receipt",
    ),
    ToolCapability("lowpass_bandpass_lat_channel", "volatility_channel", 512, "incompatible", "native_15m_without_daily_transport_receipt"),
)

ELIGIBLE_TOOL_IDS = tuple(item.tool_id for item in CAPABILITIES if item.status == "eligible_representative")


def capability_rows() -> list[dict[str, object]]:
    return [
        {
            "tool_id": item.tool_id,
            "method_family_id": item.method_family_id,
            "warmup_bars": item.warmup_bars,
            "status": item.status,
            "reason": item.reason,
            "signal_only": item.status == "eligible_representative",
            "reads_forward_outcome": False,
        }
        for item in CAPABILITIES
    ]


def pseudo_log_level(returns: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(returns, errors="coerce").astype(float)
    result = pd.Series(np.nan, index=numeric.index, dtype=float)
    group = numeric.notna().ne(numeric.notna().shift(fill_value=False)).cumsum()
    for _, local in numeric.groupby(group, sort=False):
        if local.notna().all():
            result.loc[local.index] = local.cumsum().to_numpy(dtype=float)
    return result


def naked_residual_state(returns: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(returns, errors="coerce").astype(float)
    level = 0.6 * numeric.rolling(5, min_periods=5).mean() + 0.4 * numeric.rolling(20, min_periods=20).mean()
    state = np.sign(level).astype(float)
    state[level.isna()] = np.nan
    return pd.Series(state, index=returns.index, name=NAKED_BASELINE_ID)


def signed_tool_state(log_level: pd.Series, tool_id: str) -> pd.Series:
    capability = next((item for item in CAPABILITIES if item.tool_id == tool_id), None)
    if capability is None or capability.status != "eligible_representative":
        raise ValueError(f"OT2_tool_not_eligible:{tool_id}")
    positive = _long_cash_state(log_level, tool_id)
    negative = _long_cash_state(-log_level, tool_id)
    state = positive - negative
    state.iloc[: capability.warmup_bars] = np.nan
    state[log_level.isna()] = np.nan
    return state.clip(-1.0, 1.0).rename(tool_id)


def family_tool_state(log_level: pd.Series, returns: pd.Series, tool_id: str, economic_family_id: str) -> pd.Series:
    if economic_family_id == "size":
        return signed_tool_state(log_level, tool_id)
    if economic_family_id not in {"market", "industry"}:
        raise ValueError(f"OT2_unknown_economic_family:{economic_family_id}")
    capability = next((item for item in CAPABILITIES if item.tool_id == tool_id), None)
    if capability is None or capability.status != "eligible_representative":
        raise ValueError(f"OT2_tool_not_eligible:{tool_id}")
    state = _long_cash_state(log_level, tool_id).astype(float)
    state.iloc[: capability.warmup_bars] = np.nan
    state[log_level.isna() | returns.isna()] = np.nan
    return state.clip(0.0, 1.0).rename(tool_id)


def family_naked_state(returns: pd.Series, economic_family_id: str) -> pd.Series:
    state = naked_residual_state(returns)
    if economic_family_id == "size":
        return state
    if economic_family_id in {"market", "industry"}:
        return state.clip(lower=0.0)
    raise ValueError(f"OT2_unknown_economic_family:{economic_family_id}")


def _long_cash_state(log_level: pd.Series, tool_id: str) -> pd.Series:
    if tool_id == "laplace_iir_mixed_bandpass":
        component = apply_filter_spec(
            log_level,
            FilterSpec(
                name="OT2_iir_bandpass",
                family="laplace_iir",
                mode="bandpass",
                params={"period": 40.0, "q": 1.0},
                output_kind="component",
            ),
        )
        return pd.Series(signal_from_filtered(component, output_kind="component"), index=log_level.index, dtype=float)
    if tool_id == "laplace_iir_lowpass":
        level = apply_filter_spec(
            log_level,
            FilterSpec(
                name="OT2_iir_lowpass",
                family="laplace_iir",
                mode="lowpass",
                params={"period": 75.0, "q": 1.0},
                output_kind="level",
            ),
        )
        return pd.Series(signal_from_filtered(level, output_kind="level"), index=log_level.index, dtype=float)
    if tool_id == "butterworth_clean_bandpass":
        component = butterworth_bandpass_component(log_level, short_period_bars=28, long_period_bars=57, order=4)
        return pd.Series(signal_from_filtered(component, output_kind="component"), index=log_level.index, dtype=float)
    if tool_id == "causal_haar_wavelet_bandpass":
        component = apply_filter_spec(
            log_level,
            FilterSpec(
                name="OT2_haar",
                family="wavelet_haar",
                mode="bandpass",
                params={"window": 128, "level": 2, "slow_level": 5},
                output_kind="component",
            ),
        )
        return pd.Series(signal_from_filtered(component, output_kind="component"), index=log_level.index, dtype=float)
    if tool_id == "bollinger_volatility_channel":
        pseudo_close = np.exp(log_level - float(log_level.dropna().iloc[0]))
        center = pseudo_close.rolling(20, min_periods=20).mean().shift(1)
        sigma = pseudo_close.rolling(20, min_periods=20).std(ddof=0).shift(1)
        return _stateful_long_cash(pseudo_close > center + 2.0 * sigma, pseudo_close < center)
    if tool_id == "causal_trendline_channel":
        return _trendline_state(log_level, window=40, rail_sigma=1.5)
    if tool_id == "simple_moving_average_trend":
        pseudo_close = np.exp(log_level - float(log_level.dropna().iloc[0]))
        fast = pseudo_close.rolling(20, min_periods=20).mean()
        slow = pseudo_close.rolling(60, min_periods=60).mean()
        result = (fast > slow).astype(float)
        result[slow.isna()] = np.nan
        return result
    raise ValueError(f"OT2_tool_builder_missing:{tool_id}")


def _trendline_state(log_level: pd.Series, *, window: int, rail_sigma: float) -> pd.Series:
    values = log_level.to_numpy(dtype=float)
    slope = np.full(len(values), np.nan, dtype=float)
    lower_rail = np.full(len(values), np.nan, dtype=float)
    x = np.arange(window, dtype=float)
    centered_x = x - x.mean()
    denominator = float(centered_x @ centered_x)
    for position in range(window, len(values)):
        history = values[position - window : position]
        if not np.isfinite(history).all():
            continue
        mean = float(history.mean())
        beta = float(centered_x @ (history - mean) / denominator)
        intercept = mean - beta * float(x.mean())
        fitted = intercept + beta * x
        sigma = float(np.std(history - fitted, ddof=0))
        slope[position] = beta
        lower_rail[position] = intercept + beta * float(window) - rail_sigma * sigma
    current = pd.Series(values, index=log_level.index)
    slope_series = pd.Series(slope, index=log_level.index)
    lower = pd.Series(lower_rail, index=log_level.index)
    return _stateful_long_cash(slope_series.gt(0.0) & current.ge(lower), slope_series.le(0.0) | current.lt(lower))


def _stateful_long_cash(enter: pd.Series, exit_: pd.Series) -> pd.Series:
    current = 0.0
    output = np.full(len(enter), np.nan, dtype=float)
    available = enter.notna() & exit_.notna()
    for position, (can_use, should_enter, should_exit) in enumerate(
        zip(available.to_numpy(dtype=bool), enter.fillna(False), exit_.fillna(False), strict=True)
    ):
        if not can_use:
            continue
        if bool(should_exit):
            current = 0.0
        elif bool(should_enter):
            current = 1.0
        output[position] = current
    return pd.Series(output, index=enter.index, dtype=float)


def evaluate_timing_state(state: pd.Series, returns: pd.Series, *, cost_bps: float = COST_BPS) -> pd.DataFrame:
    aligned = pd.concat([state.rename("decision_state"), returns.rename("factor_return")], axis=1)
    aligned["held_state"] = aligned["decision_state"].shift(1)
    aligned["turnover"] = aligned["held_state"].diff().abs()
    aligned["gross"] = aligned["held_state"] * aligned["factor_return"]
    aligned["cost"] = aligned["turnover"] * cost_bps / 10_000.0
    aligned["net"] = aligned["gross"] - aligned["cost"]
    return aligned.dropna(subset=["held_state", "factor_return", "turnover", "net"])


def select_one_tool_per_family(annual_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for family_id, local in annual_metrics.groupby("economic_family_id", sort=True):
        candidates: list[dict[str, object]] = []
        for tool_id, tool in local.groupby("tool_id", sort=True):
            if tool_id == NAKED_BASELINE_ID:
                continue
            supported = tool.loc[tool["supported"]].copy()
            increments = supported["incremental_net_vs_naked"].to_numpy(dtype=float)
            positive = increments[increments > 0.0]
            concentration = float(positive.max() / positive.sum()) if len(positive) and positive.sum() > 0.0 else 1.0
            candidate = {
                "economic_family_id": family_id,
                "tool_id": tool_id,
                "supported_years": len(supported),
                "positive_increment_years": int((increments > 0.0).sum()),
                "positive_increment_share": float((increments > 0.0).mean()) if len(increments) else 0.0,
                "median_incremental_net": float(np.median(increments)) if len(increments) else np.nan,
                "total_incremental_net": float(increments.sum()),
                "total_candidate_net": float(supported["candidate_net"].sum()),
                "positive_increment_concentration": concentration,
            }
            candidate["eligible"] = bool(
                candidate["supported_years"] >= 6
                and candidate["positive_increment_share"] >= 0.60
                and candidate["median_incremental_net"] >= 0.0
                and candidate["total_incremental_net"] > 0.0
                and candidate["total_candidate_net"] > 0.0
                and candidate["positive_increment_concentration"] <= 0.60
            )
            candidates.append(candidate)
        eligible = [candidate for candidate in candidates if candidate["eligible"]]
        if eligible:
            selected = sorted(
                eligible,
                key=lambda item: (
                    -float(item["median_incremental_net"]),
                    -float(item["total_incremental_net"]),
                    str(item["tool_id"]),
                ),
            )[0]
            selected["selection_status"] = "retrospective_tool_selected"
        else:
            selected = {
                "economic_family_id": family_id,
                "tool_id": NAKED_BASELINE_ID,
                "selection_status": "no_tool_increment_keep_transparent_control",
                "eligible": False,
            }
        rows.append(selected)
    return pd.DataFrame(rows).sort_values("economic_family_id", kind="stable", ignore_index=True)


def build_contract(*, bindings: Mapping[str, str]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": SCHEMA_ID,
        "status": "exclusive_family_role_aware_state_frozen",
        "issue_ref": "bd://fl-jug4j",
        "predecessor_incident": "factorlab.orthogonal_timing_directionality_incident@1.0",
        "OT1_reuse": "authorized_no_rerun_factor_basis_and_beta_are_state_agnostic",
        "economic_families": ["market", "size", "industry"],
        "idiosyncratic_family": "deferred_not_in_OT2_or_OT3_v1",
        "pseudo_coordinate": "exp(cumulative_orthogonal_return)_for_tool_geometry_only",
        "naked_follow_role": "transparent_control_and_fail_closed_fallback_not_automatic_winner",
        "eligible_tool_ids": list(ELIGIBLE_TOOL_IDS),
        "capability_rows": capability_rows(),
        "tool_state": {
            "market": "native_positive_path_participate_or_neutral_in_0_1",
            "industry": "native_positive_path_bonus_or_neutral_in_0_1_shared_tool",
            "size": "positive_small_minus_negative_large_path_in_minus1_0_plus1",
            "unavailable": "NaN_never_zero",
            "one_selected_state_per_economic_family": True,
            "multiple_tool_votes_or_weighting_allowed": False,
        },
        "selection": {
            "candidate_count": len(ELIGIBLE_TOOL_IDS),
            "same_tool_shared_by_all_12_industries": True,
            "years": list(range(2009, 2021)),
            "annual_sessions_are_sequential_and_digest_chained": True,
            "minimum_supported_years": 6,
            "minimum_positive_increment_share": 0.60,
            "nonnegative_median_increment": True,
            "positive_total_increment_and_candidate_net": True,
            "maximum_positive_increment_concentration": 0.60,
            "all_attempts_enter_multiplicity": True,
            "fresh_oos": False,
        },
        "OT3": {
            "market_score": "beta_market_times_selected_market_state_times_reliability",
            "size_score": "beta_size_times_selected_size_state_times_reliability",
            "industry_score": "sum_normalized_multiindustry_beta_times_selected_industry_state_times_reliability",
            "three_columns_remain_separate": True,
            "pre_sum_allowed": False,
            "tool_level_votes_in_stock_output_allowed": False,
        },
        "bindings": dict(sorted(bindings.items())),
        "authority": {
            "OT2_execution_allowed": True,
            "OT3_execution_allowed_after_OT2_pass": True,
            "downstream_pretraining_account_simulation_allowed": False,
            "factor_admission_allowed": False,
            "strategy_mutation_allowed": False,
            "model_training_allowed": False,
            "production_authority": False,
        },
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def validate_contract(payload: Mapping[str, object]) -> list[str]:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    blockers: list[str] = []
    if stored != canonical_digest(body):
        blockers.append("OT2_contract_digest_mismatch")
    if payload.get("schema_id") != SCHEMA_ID:
        blockers.append("OT2_contract_schema_mismatch")
    if len(payload.get("eligible_tool_ids", [])) != 7:
        blockers.append("OT2_exact_seven_representatives_required")
    return blockers


__all__ = [
    "CAPABILITIES",
    "COST_BPS",
    "ELIGIBLE_TOOL_IDS",
    "NAKED_BASELINE_ID",
    "SCHEMA_ID",
    "build_contract",
    "capability_rows",
    "evaluate_timing_state",
    "family_naked_state",
    "family_tool_state",
    "naked_residual_state",
    "pseudo_log_level",
    "select_one_tool_per_family",
    "signed_tool_state",
    "validate_contract",
]
