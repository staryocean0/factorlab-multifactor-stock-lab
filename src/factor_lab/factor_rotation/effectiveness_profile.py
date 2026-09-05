"""Train-only rolling factor effectiveness profiles."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.dates import normalize_date_series
from factor_lab.factor_rotation.factor_state import classify_factor_profile_frame

FACTOR_EFFECTIVENESS_PROFILE_SCHEMA_VERSION: Final[str] = "factor_rotation_effectiveness_profile.v1"
PROFILE_PIT_POLICY: Final[str] = "train_only_lagged_factor_effectiveness_profile"
DEFAULT_LOOKBACK_WINDOWS: Final[tuple[int, ...]] = (30, 60, 126, 252, 504, 756)


def build_factor_effectiveness_profile(
    factor_portfolio_panel: pd.DataFrame,
    *,
    exposure_panel: pd.DataFrame | None = None,
    returns_frame: pd.DataFrame | None = None,
    bucket: str = "top",
    lookback_windows: Sequence[int] = DEFAULT_LOOKBACK_WINDOWS,
    min_period_fraction: float = 0.5,
    trend_window_fraction: float = 0.5,
) -> pd.DataFrame:
    """Build a train-only factor-date effectiveness profile.

    ``factor_portfolio_panel`` contains realized factor paper returns for the
    exposure date.  Every rolling statistic in the returned profile shifts that
    realized series by one row before rolling, so the profile row for date ``t``
    only uses dates strictly before ``t``.
    """

    portfolio = _prepare_portfolio_panel(factor_portfolio_panel, bucket=bucket)
    daily_rank_ic = (
        _build_daily_rank_ic(exposure_panel, returns_frame)
        if exposure_panel is not None and returns_frame is not None
        else pd.DataFrame(columns=["date", "factor_id", "rank_ic"])
    )
    rows: list[pd.DataFrame] = []
    for factor_id, group in portfolio.groupby("factor_id", sort=True):
        group = group.sort_values("date").reset_index(drop=True)
        ic_group = daily_rank_ic[daily_rank_ic["factor_id"] == factor_id]
        ic_by_date = ic_group.set_index("date")["rank_ic"] if not ic_group.empty else None
        for lookback in lookback_windows:
            min_periods = max(1, int(round(float(lookback) * min_period_fraction)))
            trend_window = max(2, int(round(float(lookback) * trend_window_fraction)))
            rows.append(
                _profile_one_factor_window(
                    group,
                    factor_id=str(factor_id),
                    lookback=int(lookback),
                    min_periods=min_periods,
                    trend_window=trend_window,
                    rank_ic_by_date=ic_by_date,
                )
            )
    if not rows:
        return empty_factor_effectiveness_profile()
    profile = pd.concat(rows, ignore_index=True)
    profile = _add_cross_sectional_scores(profile)
    profile = classify_factor_profile_frame(profile)
    return profile.sort_values(["date", "lookback_days", "factor_id"]).reset_index(drop=True)


def empty_factor_effectiveness_profile() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "date",
            "factor_id",
            "lookback_days",
            "min_periods",
            "observation_count",
            "rank_ic_mean",
            "rank_ic_std",
            "rank_ic_ir",
            "top_bucket_excess_mean",
            "top_bucket_excess_std",
            "top_bucket_excess_sharpe",
            "hit_rate",
            "max_rolling_drawdown",
            "effectiveness_zscore",
            "effectiveness_percentile",
            "trend_slope",
            "trend_tstat",
            "state_label",
            "available_at",
            "schema_version",
            "pit_policy",
        ]
    )


def build_factor_profile_cards(
    profile: pd.DataFrame,
    *,
    factor_metadata: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Summarize profile history into per-factor cards."""

    frame = profile.copy()
    if frame.empty:
        return {
            "report_type": "factor_rotation_effectiveness_profile_cards_v1",
            "card_count": 0,
            "cards": [],
        }
    metadata = {}
    if factor_metadata is not None and not factor_metadata.empty:
        metadata = {str(row["factor_id"]): dict(row) for _, row in factor_metadata.iterrows() if "factor_id" in row}
    cards: list[dict[str, object]] = []
    latest_date = frame["date"].max()
    for factor_id, group in frame.groupby("factor_id", sort=True):
        latest = group[group["date"] == latest_date].sort_values("lookback_days")
        state_counts = group["state_label"].value_counts(dropna=False).to_dict()
        positive = group[group["top_bucket_excess_mean"] > 0.0]
        negative = group[group["top_bucket_excess_mean"] < 0.0]
        cards.append(
            {
                "factor_id": str(factor_id),
                "metadata": metadata.get(str(factor_id), {}),
                "latest_date": str(latest_date),
                "latest_states": latest[["lookback_days", "state_label", "top_bucket_excess_sharpe"]].to_dict(
                    "records"
                ),
                "state_transition_summary": {str(key): int(value) for key, value in state_counts.items()},
                "positive_profile_share": float(len(positive) / len(group)) if len(group) else 0.0,
                "negative_profile_share": float(len(negative) / len(group)) if len(group) else 0.0,
                "recommended_usage": _recommended_usage(group),
                "profile_schema_version": FACTOR_EFFECTIVENESS_PROFILE_SCHEMA_VERSION,
            }
        )
    return {
        "report_type": "factor_rotation_effectiveness_profile_cards_v1",
        "card_count": len(cards),
        "cards": cards,
    }


def _prepare_portfolio_panel(frame: pd.DataFrame, *, bucket: str) -> pd.DataFrame:
    required = {"date", "factor_id", "bucket", "excess_return"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"factor portfolio panel missing columns: {sorted(missing)}")
    output = frame.copy()
    output["date"] = normalize_date_series(output["date"])
    output["factor_id"] = output["factor_id"].astype(str)
    output["excess_return"] = pd.to_numeric(output["excess_return"], errors="coerce")
    output = output[output["bucket"].astype(str) == bucket]
    return output.dropna(subset=["excess_return"]).sort_values(["factor_id", "date"])


def _profile_one_factor_window(
    group: pd.DataFrame,
    *,
    factor_id: str,
    lookback: int,
    min_periods: int,
    trend_window: int,
    rank_ic_by_date: pd.Series | None,
) -> pd.DataFrame:
    dates = group["date"].reset_index(drop=True)
    lagged_excess = group["excess_return"].shift(1).astype(float)
    rolling = lagged_excess.rolling(lookback, min_periods=min_periods)
    mean = rolling.mean()
    std = rolling.std()
    sharpe = (mean / std.replace(0.0, np.nan)) * np.sqrt(252.0)
    hit_rate = (lagged_excess > 0.0).rolling(lookback, min_periods=min_periods).mean()
    obs = rolling.count().fillna(0).astype("int64")
    nav = (1.0 + lagged_excess.fillna(0.0)).cumprod()
    rolling_peak = nav.rolling(lookback, min_periods=min_periods).max()
    max_drawdown = nav / rolling_peak.replace(0.0, np.nan) - 1.0
    slope_min_periods = min(trend_window, max(2, trend_window // 2))
    trend_mean = lagged_excess.rolling(
        trend_window,
        min_periods=slope_min_periods,
    ).mean()
    trend_slope = (trend_mean - trend_mean.shift(trend_window)) / float(trend_window)
    trend_tstat = pd.Series(np.nan, index=group.index)
    if rank_ic_by_date is not None:
        rank_ic = dates.map(rank_ic_by_date).astype(float)
        lagged_ic = pd.Series(rank_ic).shift(1)
        ic_roll = lagged_ic.rolling(lookback, min_periods=min_periods)
        ic_mean = ic_roll.mean()
        ic_std = ic_roll.std()
        ic_ir = (ic_mean / ic_std.replace(0.0, np.nan)) * np.sqrt(252.0)
    else:
        ic_mean = pd.Series(np.nan, index=group.index)
        ic_std = pd.Series(np.nan, index=group.index)
        ic_ir = pd.Series(np.nan, index=group.index)
    return pd.DataFrame(
        {
            "date": dates,
            "factor_id": factor_id,
            "lookback_days": lookback,
            "min_periods": min_periods,
            "observation_count": obs.to_numpy(),
            "rank_ic_mean": ic_mean.to_numpy(),
            "rank_ic_std": ic_std.to_numpy(),
            "rank_ic_ir": ic_ir.to_numpy(),
            "top_bucket_excess_mean": mean.to_numpy(),
            "top_bucket_excess_std": std.to_numpy(),
            "top_bucket_excess_sharpe": sharpe.to_numpy(),
            "hit_rate": hit_rate.to_numpy(),
            "max_rolling_drawdown": max_drawdown.to_numpy(),
            "trend_slope": trend_slope.to_numpy(),
            "trend_tstat": trend_tstat.to_numpy(),
            "available_at": dates,
            "schema_version": FACTOR_EFFECTIVENESS_PROFILE_SCHEMA_VERSION,
            "pit_policy": PROFILE_PIT_POLICY,
        }
    )


def _build_daily_rank_ic(exposure_panel: pd.DataFrame, returns_frame: pd.DataFrame) -> pd.DataFrame:
    exposure = exposure_panel.copy()
    returns = returns_frame.copy()
    required_exposure = {"date", "symbol", "factor_id", "factor_value"}
    missing_exposure = required_exposure - set(exposure.columns)
    if missing_exposure:
        raise ValueError(f"exposure panel missing columns: {sorted(missing_exposure)}")
    required_returns = {"date", "symbol", "return"}
    missing_returns = required_returns - set(returns.columns)
    if missing_returns:
        raise ValueError(f"returns frame missing columns: {sorted(missing_returns)}")
    exposure["date"] = normalize_date_series(exposure["date"])
    exposure["symbol"] = exposure["symbol"].astype(str)
    exposure["factor_id"] = exposure["factor_id"].astype(str)
    exposure["factor_value"] = pd.to_numeric(exposure["factor_value"], errors="coerce")
    returns["date"] = normalize_date_series(returns["date"])
    returns["symbol"] = returns["symbol"].astype(str)
    returns["return"] = pd.to_numeric(returns["return"], errors="coerce")
    returns = returns.sort_values(["symbol", "date"])
    returns["next_return"] = returns.groupby("symbol")["return"].shift(-1)
    joined = exposure.merge(returns[["date", "symbol", "next_return"]], on=["date", "symbol"])
    joined = joined.dropna(subset=["factor_value", "next_return"])
    rows: list[dict[str, object]] = []
    for (date, factor_id), group in joined.groupby(["date", "factor_id"], sort=True):
        if len(group) < 3:
            rank_ic = np.nan
        else:
            rank_ic = group["factor_value"].corr(group["next_return"], method="spearman")
        rows.append({"date": date, "factor_id": factor_id, "rank_ic": rank_ic})
    return pd.DataFrame(rows)


def _add_cross_sectional_scores(profile: pd.DataFrame) -> pd.DataFrame:
    output = profile.copy()
    output["effectiveness_zscore"] = np.nan
    output["effectiveness_percentile"] = np.nan
    for (_, _lookback), index in output.groupby(["date", "lookback_days"]).groups.items():
        values = output.loc[index, "top_bucket_excess_sharpe"].astype(float)
        mean = values.mean(skipna=True)
        std = values.std(skipna=True)
        if pd.notna(std) and std > 0.0:
            output.loc[index, "effectiveness_zscore"] = (values - mean) / std
        output.loc[index, "effectiveness_percentile"] = values.rank(pct=True)
    return output


def _max_drawdown_from_returns(returns: pd.Series) -> float:
    clean = returns.dropna()
    if clean.empty:
        return np.nan
    nav = (1.0 + clean).cumprod()
    drawdown = nav / nav.cummax() - 1.0
    return float(drawdown.min())


def _linear_slope(values: pd.Series) -> float:
    clean = values.dropna()
    if len(clean) < 2:
        return np.nan
    x = np.arange(len(clean), dtype=float)
    return float(np.polyfit(x, clean.to_numpy(dtype=float), 1)[0])


def _linear_slope_tstat(values: pd.Series) -> float:
    clean = values.dropna()
    if len(clean) < 3:
        return np.nan
    y = clean.to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (slope * x + intercept)
    denom = np.sqrt(((x - x.mean()) ** 2).sum())
    if denom <= 0.0:
        return np.nan
    sigma = np.sqrt((residual**2).sum() / max(len(y) - 2, 1))
    if sigma <= 0.0:
        return np.nan
    return float(slope / (sigma / denom))


def _recommended_usage(group: pd.DataFrame) -> str:
    state_counts = group["state_label"].value_counts(normalize=True)
    core_share = float(state_counts.get("core_stable", 0.0))
    active_share = core_share + float(state_counts.get("cyclical_positive", 0.0))
    hazard_share = float(state_counts.get("hazard", 0.0))
    noisy_share = float(state_counts.get("noisy", 0.0))
    if hazard_share > 0.25:
        return "disabled"
    if core_share > 0.50:
        return "static_core"
    if active_share > 0.50:
        return "dynamic_core"
    if noisy_share > 0.40:
        return "satellite_only"
    return "regime_conditional"
