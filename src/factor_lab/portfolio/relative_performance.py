"""Period-relative performance metrics for account backtests.

The module deliberately separates two quantities that are often both called
"excess Sharpe":

* ``excess_sharpe_information_ratio`` is the annualized mean/std ratio of the
  daily active return ``strategy_return - benchmark_return``;
* ``sharpe_difference`` is the strategy Sharpe minus the benchmark Sharpe.

Returns passed to this module are simple returns, not log returns.  Calendar
alignment is exact and fail-closed: benchmark dates may extend beyond the
account, but every benchmark date inside the account's first/last date span
must have one matching account observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR: Final = 252.0
CLOUDRIDGE_INDEX_ID: Final = "CN_A_CLOUDRIDGE_BETA_EQW"
CLOUDRIDGE_RETURN_POLICY: Final = "equal_weight_return_only_price_neutral@1.0"


@dataclass(frozen=True, slots=True)
class RelativePerformanceResult:
    """Aligned daily ledger plus annual, quarterly and monthly summaries."""

    daily: pd.DataFrame
    annual: pd.DataFrame
    quarterly: pd.DataFrame
    monthly: pd.DataFrame
    metadata: dict[str, object]


def _daily_series(values: pd.Series, *, label: str) -> pd.Series:
    if not isinstance(values, pd.Series):
        raise TypeError(f"{label}_must_be_series")
    index = pd.DatetimeIndex(pd.to_datetime(values.index, errors="raise"))
    if index.tz is not None:
        index = index.tz_localize(None)
    index = index.normalize()
    numeric = pd.to_numeric(values, errors="raise").to_numpy(dtype=np.float64)
    if not np.isfinite(numeric).all():
        raise ValueError(f"{label}_contains_nonfinite_return")
    if (numeric <= -1.0).any():
        raise ValueError(f"{label}_contains_return_at_or_below_minus_one")
    output = pd.Series(numeric, index=index, name=label)
    if output.index.has_duplicates:
        raise ValueError(f"{label}_contains_duplicate_date")
    if not output.index.is_monotonic_increasing:
        raise ValueError(f"{label}_dates_not_sorted")
    if output.empty:
        raise ValueError(f"{label}_is_empty")
    return output


def _annualized_ratio(values: np.ndarray, annualization: float) -> float:
    if values.size < 2:
        return float("nan")
    volatility = float(values.std(ddof=1))
    if not np.isfinite(volatility) or volatility <= 0.0:
        return float("nan")
    return float(values.mean() / volatility * np.sqrt(annualization))


def _maximum_drawdown(simple_returns: np.ndarray) -> float:
    wealth = np.cumprod(1.0 + simple_returns)
    running_max = np.maximum.accumulate(np.concatenate(([1.0], wealth)))[1:]
    return float(np.min(wealth / running_max - 1.0))


def _period_labels(index: pd.DatetimeIndex, period_type: str) -> np.ndarray:
    if period_type == "annual":
        return index.strftime("%Y").to_numpy()
    if period_type == "quarterly":
        return np.asarray([f"{value.year}Q{value.quarter}" for value in index], dtype=object)
    if period_type == "monthly":
        return index.strftime("%Y-%m").to_numpy()
    raise ValueError(f"relative_performance_period_type_invalid:{period_type}")


def _period_summary(
    aligned: pd.DataFrame,
    *,
    period_type: str,
    annualization: float,
) -> pd.DataFrame:
    labels = _period_labels(pd.DatetimeIndex(aligned.index), period_type)
    first_label = str(labels[0])
    last_label = str(labels[-1])
    rows: list[dict[str, object]] = []
    for label in dict.fromkeys(labels.tolist()):
        local = aligned.loc[labels == label]
        strategy = local["strategy_return"].to_numpy(dtype=np.float64)
        benchmark = local["benchmark_return"].to_numpy(dtype=np.float64)
        active = strategy - benchmark
        relative = (1.0 + strategy) / (1.0 + benchmark) - 1.0
        strategy_total = float(np.prod(1.0 + strategy) - 1.0)
        benchmark_total = float(np.prod(1.0 + benchmark) - 1.0)
        relative_total = float(np.prod(1.0 + relative) - 1.0)
        strategy_sharpe = _annualized_ratio(strategy, annualization)
        benchmark_sharpe = _annualized_ratio(benchmark, annualization)
        tracking_error = (
            float(active.std(ddof=1) * np.sqrt(annualization))
            if active.size > 1
            else float("nan")
        )
        rows.append(
            {
                "period_type": period_type,
                "period": str(label),
                "start_date": pd.Timestamp(local.index[0]).strftime("%Y-%m-%d"),
                "end_date": pd.Timestamp(local.index[-1]).strftime("%Y-%m-%d"),
                "observation_count": int(len(local)),
                "is_input_boundary_period": str(label) in {first_label, last_label},
                "strategy_total_return": strategy_total,
                "benchmark_total_return": benchmark_total,
                "excess_total_return": strategy_total - benchmark_total,
                "excess_total_return_pp": (strategy_total - benchmark_total) * 100.0,
                "relative_excess_return": relative_total,
                "strategy_sharpe": strategy_sharpe,
                "benchmark_sharpe": benchmark_sharpe,
                "excess_sharpe_information_ratio": _annualized_ratio(active, annualization),
                "sharpe_difference": strategy_sharpe - benchmark_sharpe,
                "tracking_error_annualized": tracking_error,
                "relative_excess_max_drawdown": _maximum_drawdown(relative),
            }
        )
    return pd.DataFrame(rows)


def compute_relative_performance(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    strategy_id: str,
    benchmark_id: str = CLOUDRIDGE_INDEX_ID,
    annualization: float = TRADING_DAYS_PER_YEAR,
) -> RelativePerformanceResult:
    """Compute exact daily and calendar-period relative performance.

    ``benchmark_returns`` may cover a wider range than ``strategy_returns``.
    Missing account or benchmark dates inside the account span are rejected;
    no zero fill, forward fill or nearest-date alignment is allowed.
    """

    if not strategy_id.strip() or not benchmark_id.strip():
        raise ValueError("relative_performance_identity_missing")
    if not np.isfinite(annualization) or annualization <= 0.0:
        raise ValueError("relative_performance_annualization_invalid")
    strategy = _daily_series(strategy_returns, label="strategy_return")
    benchmark = _daily_series(benchmark_returns, label="benchmark_return")
    benchmark_span = benchmark.loc[strategy.index[0] : strategy.index[-1]]
    missing_strategy = benchmark_span.index.difference(strategy.index)
    missing_benchmark = strategy.index.difference(benchmark.index)
    if len(missing_strategy) or len(missing_benchmark):
        raise ValueError(
            "relative_performance_calendar_mismatch:"
            f"strategy_missing={len(missing_strategy)}:benchmark_missing={len(missing_benchmark)}"
        )
    aligned = pd.concat(
        [strategy, benchmark.reindex(strategy.index)],
        axis=1,
        verify_integrity=True,
    )
    if aligned.isna().any().any():
        raise ValueError("relative_performance_alignment_produced_missing_value")
    aligned["active_return"] = aligned["strategy_return"] - aligned["benchmark_return"]
    aligned["relative_return"] = (
        (1.0 + aligned["strategy_return"]) / (1.0 + aligned["benchmark_return"]) - 1.0
    )
    aligned["strategy_nav"] = (1.0 + aligned["strategy_return"]).cumprod()
    aligned["benchmark_nav"] = (1.0 + aligned["benchmark_return"]).cumprod()
    aligned["relative_nav"] = aligned["strategy_nav"] / aligned["benchmark_nav"]
    aligned.index.name = "date"
    return RelativePerformanceResult(
        daily=aligned,
        annual=_period_summary(aligned, period_type="annual", annualization=annualization),
        quarterly=_period_summary(aligned, period_type="quarterly", annualization=annualization),
        monthly=_period_summary(aligned, period_type="monthly", annualization=annualization),
        metadata={
            "strategy_id": strategy_id,
            "benchmark_id": benchmark_id,
            "return_kind": "simple_daily_return",
            "calendar_alignment": "exact_account_span_no_fill",
            "period_return_excess": "strategy_period_total_return_minus_benchmark_period_total_return",
            "relative_excess_return": "product_1_plus_strategy_div_product_1_plus_benchmark_minus_1",
            "excess_sharpe_information_ratio": (
                "mean_daily_strategy_minus_benchmark_div_sample_std_times_sqrt_annualization"
            ),
            "sharpe_difference": "strategy_sharpe_minus_benchmark_sharpe",
            "risk_free_rate": 0.0,
            "annualization": float(annualization),
            "start_date": strategy.index[0].strftime("%Y-%m-%d"),
            "end_date": strategy.index[-1].strftime("%Y-%m-%d"),
            "observation_count": int(len(strategy)),
        },
    )


def load_cloudridge_daily_returns(path: Path) -> pd.Series:
    """Load and verify an authoritative CloudRidge weekly-membership level file."""

    frame = pd.read_csv(path)
    required = {
        "index_id",
        "date",
        "daily_return",
        "index_level",
        "previous_level",
        "index_return_policy",
        "absolute_price_neutral",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("cloudridge_level_columns_missing:" + ",".join(sorted(missing)))
    if frame["index_id"].nunique(dropna=False) != 1:
        raise ValueError("cloudridge_index_id_not_unique")
    if set(frame["index_return_policy"].astype(str)) != {CLOUDRIDGE_RETURN_POLICY}:
        raise ValueError("cloudridge_return_policy_invalid")
    if not frame["absolute_price_neutral"].astype(bool).all():
        raise ValueError("cloudridge_absolute_price_neutral_failed")
    daily_return = pd.to_numeric(frame["daily_return"], errors="raise").to_numpy(np.float64)
    level = pd.to_numeric(frame["index_level"], errors="raise").to_numpy(np.float64)
    previous = pd.to_numeric(frame["previous_level"], errors="raise").to_numpy(np.float64)
    reconstructed = level / previous - 1.0
    if not np.allclose(daily_return, reconstructed, rtol=0.0, atol=5.1e-11):
        raise ValueError("cloudridge_daily_return_level_identity_failed")
    return _daily_series(
        pd.Series(daily_return, index=pd.to_datetime(frame["date"], errors="raise")),
        label="benchmark_return",
    )


__all__ = [
    "CLOUDRIDGE_INDEX_ID",
    "CLOUDRIDGE_RETURN_POLICY",
    "RelativePerformanceResult",
    "compute_relative_performance",
    "load_cloudridge_daily_returns",
]
