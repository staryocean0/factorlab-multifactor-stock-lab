# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false, reportReturnType=false
# pyright: reportAny=false, reportImplicitStringConcatenation=false
# pyright: reportMissingTypeStubs=false, reportUnusedCallResult=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Frozen Round-3 incumbent-versus-REAKA battle mechanics.

This module owns the hard preflight gate and model logic.  It deliberately
does not know any default filesystem path, so the runner must validate the
preflight before it can call a feature or outcome loader.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, TypeVar, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from factor_lab.factor_rotation.macro_regime_dual_strategy_round2 import (
    CHALLENGER_STRATEGY_ID,
    INCUMBENT_STRATEGY_ID,
    Round2Config,
    Round2Panel,
    score_with_observed_weight_mass,
)
from factor_lab.factor_rotation.macro_regime_dual_strategy_round3_execution import (
    COMPLETE_VALIDATION_YEARS,
    ROUND3_EXECUTION_RESULT_SCHEMA_ID,
    ROUND3_EXECUTION_TRIAL_ID,
    scale_macro_context_from_training_prefix,
    validate_round3_execution_preflight,
)
from factor_lab.governance.canonicalization import canonical_digest

INCUMBENT_ARM_ID: Final = "macro_persistent_state_shrunken_factor_premium_v1"
CHALLENGER_ARM_ID: Final = "reaka_adaptive_koopman_diffusion_v1"
_RESULT_FALSE_AUTHORITY: Final[dict[str, bool]] = {
    "asset_selection_allowed": False,
    "individual_stock_scoring_allowed": False,
    "portfolio_construction_allowed": False,
    "portfolio_execution": False,
    "holdings_created": False,
    "orders_created": False,
    "production_authority": False,
}
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class Round3BattleConfig:
    """Frozen model and evaluation choices for the five annual folds."""

    lookback_months: int = 6
    minimum_feature_coverage: float = 0.50
    latent_dim: int = 16
    encoder_hidden_dim: int = 32
    operator_count: int = 4
    base_epochs: int = 10
    residual_epochs: int = 10
    diffusion_steps: int = 6
    batch_size: int = 1024
    learning_rate: float = 1e-3
    ridge_penalty: float = 1e-2
    seeds: tuple[int, ...] = (11, 29, 47)
    top_bottom_fraction: float = 0.20
    long_only_count: int = 50
    one_way_cost_bps: float = 15.0
    bootstrap_replicates: int = 5000
    bootstrap_block_months: int = 3
    incumbent_regime_count: int = 4
    incumbent_regime_iterations: int = 20
    incumbent_transition_prior: float = 1.0
    incumbent_emission_variance_floor: float = 0.25
    incumbent_state_deviation_shrinkage: float = 0.50

    def round2_config(self) -> Round2Config:
        return Round2Config(
            lookback_months=self.lookback_months,
            minimum_feature_coverage=self.minimum_feature_coverage,
            duplicate_resolution_policy="unique_lineage_or_global_symbol_quarantine",
            latent_dim=self.latent_dim,
            encoder_hidden_dim=self.encoder_hidden_dim,
            operator_count=self.operator_count,
            base_epochs=self.base_epochs,
            residual_epochs=self.residual_epochs,
            diffusion_steps=self.diffusion_steps,
            batch_size=self.batch_size,
            learning_rate=self.learning_rate,
            ridge_penalty=self.ridge_penalty,
            validation_years=COMPLETE_VALIDATION_YEARS,
            seeds=self.seeds,
            top_bottom_fraction=self.top_bottom_fraction,
            long_only_count=self.long_only_count,
            one_way_cost_bps=self.one_way_cost_bps,
            bootstrap_replicates=self.bootstrap_replicates,
            bootstrap_block_months=self.bootstrap_block_months,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "round2_model_config": self.round2_config().as_dict(),
            "incumbent_regime_count": self.incumbent_regime_count,
            "incumbent_regime_iterations": self.incumbent_regime_iterations,
            "incumbent_transition_prior": self.incumbent_transition_prior,
            "incumbent_emission_variance_floor": self.incumbent_emission_variance_floor,
            "incumbent_state_deviation_shrinkage": self.incumbent_state_deviation_shrinkage,
        }


class Round3PreflightBlocked(RuntimeError):
    """Raised before any formal outcome loader is allowed to run."""


def require_round3_ready_preflight(preflight: Mapping[str, object]) -> None:
    validate_round3_execution_preflight(preflight)
    if preflight.get("status") != "ready":
        blockers = preflight.get("blockers")
        detail = ",".join(map(str, blockers)) if isinstance(blockers, list) else ""
        raise Round3PreflightBlocked(f"round3_preflight_blocked:{detail}")


def execute_after_round3_preflight(preflight: Mapping[str, object], execution: Callable[[], _T]) -> _T:
    """Call ``execution`` only after the outcome-sealed gate is ready."""

    require_round3_ready_preflight(preflight)
    return execution()


def attach_fold_macro_context(
    panel: Round2Panel,
    *,
    macro_values: pd.DataFrame,
    macro_masks: pd.DataFrame,
    train_month_rows: Sequence[bool],
) -> tuple[Round2Panel, NDArray[np.float32], dict[str, object]]:
    """Fit context scaling on the fold prefix and append six shared channels."""

    scaled, observed_month, receipt = scale_macro_context_from_training_prefix(
        macro_values,
        macro_masks,
        train_rows=train_month_rows,
    )
    if scaled.shape[0] != panel.month_dates.size or scaled.shape[1] != 6:
        raise ValueError("round3_fold_macro_context_shape_mismatch")
    context = np.broadcast_to(
        scaled[:, None, :],
        (panel.month_dates.size, panel.symbols.size, scaled.shape[1]),
    )
    context_observed = np.broadcast_to(observed_month[:, None, :], context.shape)
    features = np.concatenate([panel.features, context], axis=2).astype(np.float32, copy=False)
    observed = np.concatenate([panel.observed, context_observed], axis=2)
    context_ids = tuple(f"context:{column}" for column in macro_values.columns[1:])
    result = replace(
        panel,
        factor_ids=(*panel.factor_ids, *context_ids),
        features=features,
        observed=observed,
        feature_coverage=observed.mean(axis=2).astype(np.float32),
    )
    return result, scaled, receipt


def _initial_centroids(values: NDArray[np.float64], regime_count: int) -> NDArray[np.float64]:
    centered = values - values.mean(axis=0, keepdims=True)
    _, _, right = np.linalg.svd(centered, full_matrices=False)
    axis = centered @ right[0]
    order = np.argsort(axis, kind="stable")
    positions = np.linspace(0, len(order) - 1, regime_count).round().astype(int)
    return values[order[positions]].copy()


def _fit_persistent_gaussian_regimes(
    context: NDArray[np.float64],
    *,
    config: Round3BattleConfig,
) -> dict[str, NDArray[np.float64] | NDArray[np.int64]]:
    regime_count = config.incumbent_regime_count
    if context.ndim != 2 or len(context) < regime_count * 2:
        raise ValueError("round3_incumbent_regime_training_months_insufficient")
    centroids = _initial_centroids(context, regime_count)
    labels = np.zeros(len(context), dtype=np.int64)
    for _ in range(config.incumbent_regime_iterations):
        distance = ((context[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        updated = np.argmin(distance, axis=1).astype(np.int64)
        if np.array_equal(updated, labels):
            labels = updated
            break
        labels = updated
        for regime in range(regime_count):
            members = context[labels == regime]
            if len(members):
                centroids[regime] = members.mean(axis=0)
    variances = np.full_like(centroids, config.incumbent_emission_variance_floor)
    for regime in range(regime_count):
        members = context[labels == regime]
        if len(members) >= 2:
            variances[regime] = np.maximum(
                members.var(axis=0, ddof=0),
                config.incumbent_emission_variance_floor,
            )
    prior = config.incumbent_transition_prior
    transition = np.full((regime_count, regime_count), prior, dtype=np.float64)
    for left, right_label in zip(labels[:-1], labels[1:], strict=True):
        transition[left, right_label] += 1.0
    transition /= transition.sum(axis=1, keepdims=True)
    initial = np.bincount(labels, minlength=regime_count).astype(np.float64) + prior
    initial /= initial.sum()
    return {
        "centroids": centroids,
        "variances": variances,
        "transition": transition,
        "initial": initial,
        "labels": labels,
    }


def _filter_regime_probabilities(
    context: NDArray[np.float64],
    model: Mapping[str, NDArray[np.float64] | NDArray[np.int64]],
) -> NDArray[np.float64]:
    centroids = cast(NDArray[np.float64], model["centroids"])
    variances = cast(NDArray[np.float64], model["variances"])
    transition = cast(NDArray[np.float64], model["transition"])
    previous = cast(NDArray[np.float64], model["initial"]).copy()
    rows: list[NDArray[np.float64]] = []
    for value in context:
        log_emission = -0.5 * (np.log(2.0 * np.pi * variances) + ((value[None, :] - centroids) ** 2) / variances).sum(axis=1)
        emission = np.exp(log_emission - log_emission.max())
        predicted = previous @ transition
        posterior = predicted * emission
        total = float(posterior.sum())
        if not np.isfinite(total) or total <= 0.0:
            posterior = predicted
            total = float(posterior.sum())
        previous = posterior / total
        rows.append(previous.copy())
    return np.vstack(rows)


def _monthly_factor_premia(
    panel: Round2Panel,
    train_indices: NDArray[np.int64],
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    sample_months = panel.sample_month_indices[train_indices]
    unique_months = np.unique(sample_months)
    premia = np.full((len(unique_months), len(panel.factor_ids)), np.nan)
    for row, month_index in enumerate(unique_months):
        local = train_indices[sample_months == month_index]
        symbols = panel.sample_symbol_indices[local]
        features = panel.features[month_index, symbols, :].astype(np.float64)
        observed = panel.observed[month_index, symbols, :]
        targets = panel.targets[month_index, symbols].astype(np.float64)
        valid = observed & np.isfinite(targets)[:, None]
        counts = valid.sum(axis=0)
        numerator = np.where(valid, features * targets[:, None], 0.0).sum(axis=0)
        denominator = np.where(valid, features * features, 0.0).sum(axis=0)
        usable = (counts >= 20) & (denominator > 1e-12)
        premia[row, usable] = numerator[usable] / denominator[usable]
    return unique_months.astype(np.int64), premia


def fit_macro_regime_incumbent(
    *,
    panel: Round2Panel,
    train_indices: NDArray[np.int64],
    test_indices: NDArray[np.int64],
    scaled_macro_context: NDArray[np.float32],
    config: Round3BattleConfig,
) -> tuple[NDArray[np.float64], dict[str, object]]:
    """Fit shared premia plus shrunken persistent-state deviations."""

    if scaled_macro_context.shape != (panel.month_dates.size, 6):
        raise ValueError("round3_incumbent_macro_context_shape_mismatch")
    train_months, premia = _monthly_factor_premia(panel, train_indices)
    context = scaled_macro_context.astype(np.float64)
    regime_model = _fit_persistent_gaussian_regimes(context[train_months], config=config)
    filtered = _filter_regime_probabilities(context, regime_model)
    train_probabilities = filtered[train_months]
    finite = np.isfinite(premia)
    baseline_numerator = np.where(finite, premia, 0.0).sum(axis=0)
    baseline_denominator = finite.sum(axis=0)
    baseline = np.divide(
        baseline_numerator,
        baseline_denominator,
        out=np.zeros_like(baseline_numerator),
        where=baseline_denominator > 0,
    )
    state_premia = np.tile(baseline, (config.incumbent_regime_count, 1))
    for regime in range(config.incumbent_regime_count):
        weights = train_probabilities[:, regime, None] * finite
        denominator = weights.sum(axis=0)
        numerator = (weights * np.where(finite, premia, 0.0)).sum(axis=0)
        usable = denominator > 1e-8
        state_premia[regime, usable] = numerator[usable] / denominator[usable]
    test_months = panel.sample_month_indices[test_indices]
    test_symbols = panel.sample_symbol_indices[test_indices]
    scores = np.zeros(len(test_indices), dtype=np.float64)
    shrinkage = config.incumbent_state_deviation_shrinkage
    active_counts: list[int] = []
    for month_index in np.unique(test_months):
        local = np.flatnonzero(test_months == month_index)
        conditional = filtered[month_index] @ state_premia
        weights = baseline + shrinkage * (conditional - baseline)
        norm = float(np.abs(weights).sum())
        if norm <= 1e-12:
            weights = np.full(len(weights), 1.0 / len(weights))
        else:
            weights = weights / norm
        scores[local] = score_with_observed_weight_mass(
            panel.features[month_index, test_symbols[local], :].astype(np.float64),
            observed=panel.observed[month_index, test_symbols[local], :],
            weights=weights,
        )
        active_counts.append(int((np.abs(weights) > 1e-8).sum()))
    diagnostics: dict[str, object] = {
        "fit_kind": "train_only_persistent_gaussian_macro_state_shared_plus_shrunken_factor_premia",
        "train_row_count": int(len(train_indices)),
        "test_row_count": int(len(test_indices)),
        "train_month_count": int(len(train_months)),
        "factor_count": len(panel.factor_ids),
        "regime_count": config.incumbent_regime_count,
        "state_deviation_shrinkage": shrinkage,
        "transition_matrix": cast(NDArray[np.float64], regime_model["transition"]).tolist(),
        "train_regime_occupancy": train_probabilities.mean(axis=0).tolist(),
        "average_active_factor_count": float(np.mean(active_counts)),
        "missing_score_scale_policy": "per_stock_observed_absolute_weight_mass",
        "test_outcomes_used_during_fit": False,
        "full_sample_state_smoothing_used": False,
    }
    return scores, diagnostics


def round3_result_false_authority() -> dict[str, bool]:
    return dict(_RESULT_FALSE_AUTHORITY)


def seal_round3_result(payload: dict[str, object]) -> None:
    payload.pop("canonical_digest", None)
    payload["canonical_digest"] = canonical_digest(payload)


def _forbidden_result_paths(
    value: object,
    *,
    forbidden: set[str],
    path: str = "$",
) -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in forbidden:
                paths.append(child_path)
            paths.extend(_forbidden_result_paths(child, forbidden=forbidden, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(
                _forbidden_result_paths(
                    child,
                    forbidden=forbidden,
                    path=f"{path}[{index}]",
                )
            )
    return paths


def validate_round3_result(payload: Mapping[str, object]) -> None:
    if payload.get("schema_id") != ROUND3_EXECUTION_RESULT_SCHEMA_ID:
        raise ValueError("round3_result_schema_mismatch")
    if payload.get("trial_id") != ROUND3_EXECUTION_TRIAL_ID:
        raise ValueError("round3_result_trial_mismatch")
    if payload.get("status") != "completed":
        raise ValueError("round3_result_not_completed")
    if payload.get("complete_validation_years") != list(COMPLETE_VALIDATION_YEARS):
        raise ValueError("round3_result_validation_years_changed")
    folds = payload.get("fold_results")
    if not isinstance(folds, list) or len(folds) != 5:
        raise ValueError("round3_result_five_fold_results_required")
    for raw, year in zip(folds, COMPLETE_VALIDATION_YEARS, strict=True):
        if not isinstance(raw, Mapping) or raw.get("validation_year") != year:
            raise ValueError("round3_result_fold_year_order_changed")
        if raw.get("train_end") != f"{year - 1}-12-31":
            raise ValueError(f"round3_result_train_prefix_mismatch:{year}")
        if raw.get("test_start") != f"{year}-01-01" or raw.get("test_end") != f"{year}-12-31":
            raise ValueError(f"round3_result_test_window_mismatch:{year}")
    strategies = payload.get("strategy_metrics")
    if not isinstance(strategies, list) or {raw.get("strategy_id") for raw in strategies if isinstance(raw, Mapping)} != {
        INCUMBENT_STRATEGY_ID,
        CHALLENGER_STRATEGY_ID,
    }:
        raise ValueError("round3_result_paired_strategy_metrics_required")
    if payload.get("incomplete_preview_year") != 2026 or payload.get("incomplete_preview_scored") is not False:
        raise ValueError("round3_result_2026_preview_must_remain_unscored")
    black_box = payload.get("market_black_box_policy")
    if not isinstance(black_box, Mapping) or (
        black_box.get("test_year_outcomes_hidden_during_fit") is not True
        or black_box.get("test_year_drilldown_persisted") is not False
        or black_box.get("only_annual_and_paired_aggregate_metrics_persisted") is not True
    ):
        raise ValueError("round3_result_black_box_policy_invalid")
    forbidden = {
        "monthly_metrics",
        "predictions",
        "stock_scores",
        "holdings",
        "orders",
        "test_year_drilldown",
    }
    forbidden_paths = _forbidden_result_paths(payload, forbidden=forbidden)
    if forbidden_paths:
        raise ValueError("round3_result_forbidden_detail_persisted:" + ",".join(forbidden_paths))
    if payload.get("authority") != _RESULT_FALSE_AUTHORITY:
        raise ValueError("round3_result_authority_must_remain_false")
    winner = payload.get("winner_strategy_id")
    if winner not in {None, INCUMBENT_STRATEGY_ID, CHALLENGER_STRATEGY_ID}:
        raise ValueError("round3_result_winner_invalid")
    expected = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    if payload.get("canonical_digest") != expected:
        raise ValueError("round3_result_digest_mismatch")


__all__ = [
    "CHALLENGER_ARM_ID",
    "INCUMBENT_ARM_ID",
    "Round3BattleConfig",
    "Round3PreflightBlocked",
    "attach_fold_macro_context",
    "execute_after_round3_preflight",
    "fit_macro_regime_incumbent",
    "require_round3_ready_preflight",
    "round3_result_false_authority",
    "seal_round3_result",
    "validate_round3_result",
]
