"""Evaluation engine for factor analysis."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field


def _string_list(value: object, default: list[str]) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return default


@dataclass
class EvaluationResult:
    """Result of factor evaluation."""

    ic_mean: float = 0.0
    ic_std: float = 0.0
    ic_ir: float = 0.0
    rank_ic_mean: float = 0.0
    rank_ic_std: float = 0.0
    rank_ic_ir: float = 0.0
    turnover_mean: float = 0.0
    quantile_returns: dict[int, float] = field(default_factory=dict)
    coverage_ratio: float = 0.0
    observation_count: int = 0
    period_count: int = 0
    decay_curve: dict[str, float] = field(default_factory=dict)
    segment_stability: dict[str, float] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "ic": {
                "mean": self.ic_mean,
                "std": self.ic_std,
                "ir": self.ic_ir,
            },
            "rank_ic": {
                "mean": self.rank_ic_mean,
                "std": self.rank_ic_std,
                "ir": self.rank_ic_ir,
            },
            "turnover": {"mean": self.turnover_mean},
            "quantile_returns": self.quantile_returns,
            "coverage": {
                "ratio": self.coverage_ratio,
                "observation_count": self.observation_count,
                "period_count": self.period_count,
            },
            "decay_curve": self.decay_curve,
            "segment_stability": self.segment_stability,
            "score": self.score,
        }


@dataclass
class EvaluationObservation:
    """Aligned factor/label observation."""

    symbol: str
    timestamp: str
    factor_value: float
    forward_return: float
    quantile: int


class EvaluationEngine:
    """Engine for evaluating factor performance."""

    config: dict[str, object]
    horizon: str
    groups: list[str]
    metrics: list[str]

    def __init__(self, protocol_config: dict[str, object]):
        self.config = protocol_config
        horizon = protocol_config.get("horizon", "1d")
        self.horizon = horizon if isinstance(horizon, str) else "1d"
        self.groups = _string_list(protocol_config.get("groups"), ["quantile_5"])
        self.metrics = _string_list(
            protocol_config.get("metrics"), ["ic", "rank_ic", "turnover"]
        )

    def evaluate(
        self,
        factor_values: list[float],
        forward_returns: list[float],
        group_labels: list[int] | None = None,
    ) -> EvaluationResult:
        """Evaluate flat factor/return vectors."""
        result = EvaluationResult()
        raw_observations = len(factor_values)

        if len(factor_values) != len(forward_returns):
            raise ValueError("Factor values and returns must have same length")

        cleaned = self._filter_finite_pairs(factor_values, forward_returns)
        if not cleaned:
            return result

        filtered_factor_values = [item[0] for item in cleaned]
        filtered_forward_returns = [item[1] for item in cleaned]

        if "ic" in self.metrics:
            result.ic_mean = self._calculate_ic(
                filtered_factor_values, filtered_forward_returns
            )

        if "rank_ic" in self.metrics:
            result.rank_ic_mean = self._calculate_rank_ic(
                filtered_factor_values, filtered_forward_returns
            )

        if "turnover" in self.metrics:
            result.turnover_mean = self._calculate_turnover(group_labels or [])

        if group_labels:
            filtered_group_labels = [
                group_label
                for _, _, group_label in self._filter_finite_triplets(
                    factor_values, forward_returns, group_labels
                )
            ]
            result.quantile_returns = self._calculate_quantile_returns(
                filtered_forward_returns,
                filtered_group_labels,
            )

        result.ic_std, result.ic_ir = self._calc_std_and_ir(
            result.ic_mean, filtered_factor_values
        )
        result.rank_ic_std, result.rank_ic_ir = self._calc_std_and_ir(
            result.rank_ic_mean, filtered_factor_values
        )

        result.observation_count = len(filtered_factor_values)
        result.coverage_ratio = len(filtered_factor_values) / max(raw_observations, 1)
        result.period_count = 1
        result.decay_curve = {
            self.horizon: result.rank_ic_mean,
            "1d": result.ic_mean,
        }
        result.segment_stability = {
            "top_quantile_mean": result.quantile_returns.get(
                max(result.quantile_returns, default=1), 0.0
            ),
            "bottom_quantile_mean": result.quantile_returns.get(
                min(result.quantile_returns, default=1), 0.0
            ),
        }
        result.score = self._calculate_score(result)
        return result

    def evaluate_observations(
        self,
        observations: list[EvaluationObservation],
        *,
        total_factor_rows: int,
    ) -> EvaluationResult:
        """Evaluate observations grouped by timestamp."""
        result = EvaluationResult()
        if not observations or total_factor_rows <= 0:
            return result

        by_timestamp: dict[str, list[EvaluationObservation]] = defaultdict(list)
        for observation in observations:
            by_timestamp[observation.timestamp].append(observation)

        ordered_timestamps = sorted(by_timestamp)
        ic_series: list[float] = []
        rank_ic_series: list[float] = []
        turnover_series: list[float] = []
        quantile_buckets: dict[int, list[float]] = defaultdict(list)
        previous_top_symbols: set[str] | None = None
        valid_observation_count = 0
        valid_period_count = 0

        for timestamp in ordered_timestamps:
            period_rows = [
                row
                for row in by_timestamp[timestamp]
                if math.isfinite(row.factor_value) and math.isfinite(row.forward_return)
            ]

            if not period_rows:
                continue

            valid_period_count += 1
            factor_values = [row.factor_value for row in period_rows]
            forward_returns = [row.forward_return for row in period_rows]
            valid_observation_count += len(period_rows)

            if len(period_rows) >= 2:
                ic_series.append(self._calculate_ic(factor_values, forward_returns))
                rank_ic_series.append(
                    self._calculate_rank_ic(factor_values, forward_returns)
                )

            for row in period_rows:
                quantile_buckets[row.quantile].append(row.forward_return)

            top_quantile = max(row.quantile for row in period_rows)
            current_top_symbols = {
                row.symbol for row in period_rows if row.quantile == top_quantile
            }
            if previous_top_symbols is not None:
                union = previous_top_symbols | current_top_symbols
                turnover_series.append(
                    0.0
                    if not union
                    else 1.0
                    - (len(previous_top_symbols & current_top_symbols) / len(union))
                )
            previous_top_symbols = current_top_symbols

        result.ic_mean, result.ic_std, result.ic_ir = self._summarize_series(ic_series)
        (
            result.rank_ic_mean,
            result.rank_ic_std,
            result.rank_ic_ir,
        ) = self._summarize_series(rank_ic_series)
        result.turnover_mean = (
            statistics.mean(turnover_series) if turnover_series else 0.0
        )
        result.quantile_returns = {
            quantile: statistics.mean(returns)
            for quantile, returns in quantile_buckets.items()
            if returns
        }
        result.coverage_ratio = valid_observation_count / max(total_factor_rows, 1)
        result.observation_count = valid_observation_count
        result.period_count = valid_period_count
        result.decay_curve = {
            self.horizon: result.rank_ic_mean,
            "1d": result.ic_mean,
        }
        result.segment_stability = {
            "top_quantile_mean": result.quantile_returns.get(
                max(result.quantile_returns, default=1), 0.0
            ),
            "bottom_quantile_mean": result.quantile_returns.get(
                min(result.quantile_returns, default=1), 0.0
            ),
        }
        result.score = self._calculate_score(result)
        return result

    @staticmethod
    def _filter_finite_pairs(
        factor_values: list[float], forward_returns: list[float]
    ) -> list[tuple[float, float]]:
        return [
            (float(factor_value), float(forward_return))
            for factor_value, forward_return in zip(
                factor_values, forward_returns, strict=False
            )
            if math.isfinite(factor_value)
            and math.isfinite(forward_return)
        ]

    @staticmethod
    def _filter_finite_triplets(
        factor_values: list[float],
        forward_returns: list[float],
        group_labels: list[int],
    ) -> list[tuple[float, float, int]]:
        return [
            (float(factor_value), float(forward_return), int(group_label))
            for factor_value, forward_return, group_label in zip(
                factor_values, forward_returns, group_labels, strict=False
            )
            if math.isfinite(factor_value)
            and math.isfinite(forward_return)
            and isinstance(group_label, int)
        ]

    @staticmethod
    def _rank_values(values: list[float]) -> list[float]:
        if not values:
            return []

        sorted_pairs = sorted(enumerate(values), key=lambda item: item[1])
        ranks = [0.0] * len(values)
        index = 0

        while index < len(values):
            end = index
            current_value = sorted_pairs[index][1]
            while end + 1 < len(values) and sorted_pairs[end + 1][1] == current_value:
                end += 1

            average_rank = ((index + 1) + (end + 1)) / 2
            for i in range(index, end + 1):
                original_index = sorted_pairs[i][0]
                ranks[original_index] = average_rank
            index = end + 1

        return ranks

    @staticmethod
    def _calculate_rank_ic(
        factor_values: list[float],
        forward_returns: list[float],
    ) -> float:
        if len(factor_values) < 2:
            return 0.0

        ranked_factor = EvaluationEngine._rank_values(factor_values)
        ranked_returns = EvaluationEngine._rank_values(forward_returns)
        return EvaluationEngine._calculate_correlation(ranked_factor, ranked_returns)

    @staticmethod
    def _calculate_ic(
        factor_values: list[float],
        forward_returns: list[float],
    ) -> float:
        if len(factor_values) < 2:
            return 0.0
        return EvaluationEngine._calculate_correlation(factor_values, forward_returns)

    @staticmethod
    def _calculate_correlation(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0

        n = len(left)
        if n < 2:
            return 0.0

        mean_left = statistics.mean(left)
        mean_right = statistics.mean(right)

        numerator = sum(
            (left_value - mean_left) * (right_value - mean_right)
            for left_value, right_value in zip(left, right, strict=False)
        )
        denominator_left = sum((left_value - mean_left) ** 2 for left_value in left)
        denominator_right = sum(
            (right_value - mean_right) ** 2 for right_value in right
        )

        denominator = denominator_left * denominator_right
        if denominator <= 0:
            return 0.0

        return numerator / math.sqrt(denominator)

    @staticmethod
    def _calculate_quantile_returns(
        forward_returns: list[float],
        group_labels: list[int],
    ) -> dict[int, float]:
        buckets: dict[int, list[float]] = defaultdict(list)
        for group_label, return_value in zip(
            group_labels, forward_returns, strict=False
        ):
            buckets[int(group_label)].append(float(return_value))

        return {
            int(group_label): statistics.mean(values)
            for group_label, values in buckets.items()
            if values
        }

    @staticmethod
    def _calc_std_and_ir(
        mean_value: float, values: list[float]
    ) -> tuple[float, float]:
        if len(values) < 2:
            return 0.0, 0.0
        std = statistics.pstdev(values)
        ir = mean_value / std if std > 0 else 0.0
        return std, ir

    @staticmethod
    def _summarize_series(values: list[float]) -> tuple[float, float, float]:
        if not values:
            return 0.0, 0.0, 0.0

        mean = statistics.mean(values)
        std = statistics.pstdev(values) if len(values) >= 2 else 0.0
        ir = mean / std if std > 0 else 0.0
        return mean, std, ir

    @staticmethod
    def _calculate_turnover(group_labels: list[int]) -> float:
        if len(group_labels) < 2:
            return 0.0
        return 0.0 if len(set(group_labels)) > 1 else 1.0

    def _calculate_score(self, result: EvaluationResult) -> float:
        """Return bounded score in [0.0, 1.0]."""
        coverage = max(0.0, min(1.0, result.coverage_ratio))
        ic_strength = max(
            0.0,
            min(1.0, (abs(result.ic_mean) + abs(result.rank_ic_mean)) / 2.0),
        )
        turnover_factor = max(0.0, min(1.0, 1.0 - result.turnover_mean))
        return round(
            min(
                1.0,
                max(
                    0.0,
                    0.35 * coverage + 0.35 * ic_strength + 0.30 * turnover_factor,
                ),
            ),
            6,
        )
