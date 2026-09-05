"""Analyzer for out-of-sample (OOS) statistics."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factor_lab.evaluation.engine import EvaluationEngine, EvaluationObservation


@dataclass(slots=True)
class OOSFoldResult:
    """Result of a single OOS fold/period."""

    fold_id: int
    start_date: str
    end_date: str
    ic_mean: float
    rank_ic_mean: float
    coverage_ratio: float
    turnover_mean: float
    sample_count: int
    period_count: int
    valid_ic_period_count: int


@dataclass(slots=True)
class OOSSummary:
    """Summary of OOS stability statistics."""

    fold_count: int
    folds: list[OOSFoldResult]
    positive_ic_fold_ratio: float
    positive_rank_ic_fold_ratio: float
    positive_ic_period_ratio: float
    positive_rank_ic_period_ratio: float
    mean_oos_ic: float
    mean_oos_rank_ic: float
    worst_fold_ic: float
    worst_fold_rank_ic: float
    ic_dispersion: float
    rank_ic_dispersion: float
    insufficient_sample: bool
    min_fold_sample_count: int
    enhancement_type: str = "post_req001_oos_statistics_v1"

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for artifact storage."""
        payload = asdict(self)
        payload["folds"] = [asdict(fold) for fold in self.folds]
        return payload


def _valid_ic_period_count(observations: list[EvaluationObservation]) -> int:
    """Count periods with enough cross-section rows for IC/RankIC."""
    by_timestamp: dict[str, int] = {}
    for observation in observations:
        if isfinite(observation.factor_value) and isfinite(observation.forward_return):
            by_timestamp[observation.timestamp] = (
                by_timestamp.get(observation.timestamp, 0) + 1
            )
    return sum(1 for count in by_timestamp.values() if count >= 2)


def _empty_summary() -> OOSSummary:
    return OOSSummary(
        fold_count=0,
        folds=[],
        positive_ic_fold_ratio=0.0,
        positive_rank_ic_fold_ratio=0.0,
        positive_ic_period_ratio=0.0,
        positive_rank_ic_period_ratio=0.0,
        mean_oos_ic=0.0,
        mean_oos_rank_ic=0.0,
        worst_fold_ic=0.0,
        worst_fold_rank_ic=0.0,
        ic_dispersion=0.0,
        rank_ic_dispersion=0.0,
        insufficient_sample=True,
        min_fold_sample_count=0,
    )


def analyze_oos(
    observations: list[EvaluationObservation],
    fold_count: int = 3,
    min_periods_per_fold: int = 2,
    engine: EvaluationEngine | None = None,
) -> OOSSummary:
    """
    Perform time-split OOS analysis by dividing observations into folds.

    Args:
        observations: List of evaluation observations.
        fold_count: Number of time-based folds to split into.
        min_periods_per_fold: Minimum periods required per fold to avoid
            insufficient flag.
        engine: Evaluation engine to reuse for fold calculations.

    Returns:
        OOSSummary containing fold results and stability metrics.
    """
    if not observations:
        return _empty_summary()

    # Late import to avoid circular dependency.
    from factor_lab.evaluation.engine import EvaluationEngine

    if engine is None:
        engine = EvaluationEngine({})

    # Group by timestamp to ensure time-based splitting.
    timestamps = sorted({obs.timestamp for obs in observations})
    total_periods = len(timestamps)

    if total_periods == 0:
        return _empty_summary()

    actual_fold_count = min(fold_count, total_periods)
    if actual_fold_count <= 0:
        actual_fold_count = 1

    periods_per_fold = total_periods // actual_fold_count
    remainder = total_periods % actual_fold_count

    folds: list[OOSFoldResult] = []
    current_idx = 0
    insufficient = False
    min_samples = float("inf")

    for i in range(actual_fold_count):
        fold_size = periods_per_fold + (1 if i < remainder else 0)
        fold_timestamps = set(timestamps[current_idx : current_idx + fold_size])
        current_idx += fold_size

        if not fold_timestamps:
            continue

        fold_obs = [obs for obs in observations if obs.timestamp in fold_timestamps]
        fold_periods = len(fold_timestamps)
        valid_ic_periods = _valid_ic_period_count(fold_obs)

        if (
            fold_periods < min_periods_per_fold
            or valid_ic_periods < min_periods_per_fold
        ):
            insufficient = True

        # Use the fold's own row count for a local coverage measure.
        fold_res = engine.evaluate_observations(
            fold_obs, total_factor_rows=len(fold_obs)
        )
        min_samples = min(min_samples, fold_res.observation_count)

        folds.append(
            OOSFoldResult(
                fold_id=i + 1,
                start_date=min(fold_timestamps),
                end_date=max(fold_timestamps),
                ic_mean=fold_res.ic_mean,
                rank_ic_mean=fold_res.rank_ic_mean,
                coverage_ratio=fold_res.coverage_ratio,
                turnover_mean=fold_res.turnover_mean,
                sample_count=fold_res.observation_count,
                period_count=fold_res.period_count,
                valid_ic_period_count=valid_ic_periods,
            )
        )

    if not folds:
        return _empty_summary()

    ic_values = [f.ic_mean for f in folds]
    rank_ic_values = [f.rank_ic_mean for f in folds]

    def pos_ratio(values: list[float]) -> float:
        if not values:
            return 0.0
        return len([v for v in values if v > 0]) / len(values)

    positive_ic_fold_ratio = pos_ratio(ic_values)
    positive_rank_ic_fold_ratio = pos_ratio(rank_ic_values)

    return OOSSummary(
        fold_count=len(folds),
        folds=folds,
        positive_ic_fold_ratio=positive_ic_fold_ratio,
        positive_rank_ic_fold_ratio=positive_rank_ic_fold_ratio,
        # Backward-compatible aliases retained for existing artifact consumers.
        positive_ic_period_ratio=positive_ic_fold_ratio,
        positive_rank_ic_period_ratio=positive_rank_ic_fold_ratio,
        mean_oos_ic=statistics.mean(ic_values) if ic_values else 0.0,
        mean_oos_rank_ic=statistics.mean(rank_ic_values) if rank_ic_values else 0.0,
        worst_fold_ic=min(ic_values) if ic_values else 0.0,
        worst_fold_rank_ic=min(rank_ic_values) if rank_ic_values else 0.0,
        ic_dispersion=statistics.pstdev(ic_values) if len(ic_values) >= 2 else 0.0,
        rank_ic_dispersion=(
            statistics.pstdev(rank_ic_values) if len(rank_ic_values) >= 2 else 0.0
        ),
        insufficient_sample=insufficient,
        min_fold_sample_count=int(min_samples) if min_samples != float("inf") else 0,
    )
