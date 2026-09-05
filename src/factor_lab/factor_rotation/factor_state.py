"""State labels for time-varying factor effectiveness."""

from __future__ import annotations

import math
from typing import Final

import pandas as pd

FACTOR_STATE_SCHEMA_VERSION: Final[str] = "factor_rotation_factor_state.v1"

CORE_STABLE: Final[str] = "core_stable"
CYCLICAL_POSITIVE: Final[str] = "cyclical_positive"
RECOVERING: Final[str] = "recovering"
DECAYING: Final[str] = "decaying"
INACTIVE: Final[str] = "inactive"
HAZARD: Final[str] = "hazard"
NOISY: Final[str] = "noisy"
INSUFFICIENT_HISTORY: Final[str] = "insufficient_history"

ACTIVE_STATES: Final[set[str]] = {CORE_STABLE, CYCLICAL_POSITIVE, RECOVERING}
SUPPRESSED_STATES: Final[set[str]] = {
    DECAYING,
    INACTIVE,
    HAZARD,
    NOISY,
    INSUFFICIENT_HISTORY,
}


def classify_factor_state(
    *,
    observation_count: int,
    top_bucket_excess_mean: float | None,
    top_bucket_excess_sharpe: float | None,
    hit_rate: float | None,
    trend_slope: float | None,
    max_rolling_drawdown: float | None,
    min_observations: int,
) -> str:
    """Classify a factor-date into an allocator-consumable state.

    The thresholds are intentionally simple.  They are not a production alpha
    model; they are a stable contract that separates usable, weakening, harmful,
    and noisy factor states without using future observations.
    """

    if observation_count < min_observations:
        return INSUFFICIENT_HISTORY

    mean = _finite_or_none(top_bucket_excess_mean)
    sharpe = _finite_or_none(top_bucket_excess_sharpe)
    hit = _finite_or_none(hit_rate)
    slope = _finite_or_none(trend_slope)
    drawdown = _finite_or_none(max_rolling_drawdown)

    if mean is None or sharpe is None:
        return INACTIVE

    if mean < 0.0 and sharpe < -0.25:
        return HAZARD
    if drawdown is not None and drawdown <= -0.20 and sharpe < 0.25:
        return HAZARD
    if mean <= 0.0 and sharpe <= 0.0:
        return INACTIVE

    hit_ok = hit is None or hit >= 0.50
    slope_nonnegative = slope is None or slope >= 0.0
    slope_negative = slope is not None and slope < 0.0

    if sharpe >= 1.0 and mean > 0.0 and hit_ok and slope_nonnegative:
        return CORE_STABLE
    if sharpe >= 0.5 and mean > 0.0 and hit_ok and slope_nonnegative:
        return CYCLICAL_POSITIVE
    if mean > 0.0 and slope is not None and slope > 0.0:
        return RECOVERING
    if mean > 0.0 and slope_negative:
        return DECAYING
    return NOISY


def classify_factor_profile_frame(
    profile: pd.DataFrame,
    *,
    min_observations_column: str = "min_periods",
) -> pd.DataFrame:
    """Add ``state_label`` to a profile frame."""

    output = profile.copy()
    labels: list[str] = []
    for _, row in output.iterrows():
        labels.append(
            classify_factor_state(
                observation_count=int(row.get("observation_count", 0) or 0),
                top_bucket_excess_mean=_to_float(row.get("top_bucket_excess_mean")),
                top_bucket_excess_sharpe=_to_float(row.get("top_bucket_excess_sharpe")),
                hit_rate=_to_float(row.get("hit_rate")),
                trend_slope=_to_float(row.get("trend_slope")),
                max_rolling_drawdown=_to_float(row.get("max_rolling_drawdown")),
                min_observations=int(row.get(min_observations_column, 1) or 1),
            )
        )
    output["state_label"] = labels
    output["state_schema_version"] = FACTOR_STATE_SCHEMA_VERSION
    return output


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
