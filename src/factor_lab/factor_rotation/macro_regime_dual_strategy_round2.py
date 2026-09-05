# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportArgumentType=false, reportReturnType=false
# pyright: reportGeneralTypeIssues=false, reportCallIssue=false, reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false, reportUnannotatedClassAttribute=false
# pyright: reportImplicitOverride=false, reportUnusedCallResult=false
"""Broad-factor incumbent/REAKA battle on consumed A-share history.

Round 2 deliberately separates the 310-name recovered registry from the
smaller set of candidates that have auditable, stock-level values.  The model
code only accepts the latter.  Registry-only names remain visible in the
coverage ledger and can never be converted into zero-filled pseudo factors.

The module is research-only.  It creates scores and paired diagnostics, never
holdings, orders, factor admission, a production winner, or production
authority.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import numpy as np
import pandas as pd
import torch
from numpy.typing import NDArray
from scipy import stats
from torch import Tensor, nn
from torch.nn import functional as F

from factor_lab.governance.canonicalization import canonical_digest

ROUND2_SCHEMA_ID: Final = "macro_regime_dual_strategy_round2_broad_factor_proxy@1.0"
ROUND2_TRIAL_ID: Final = "macro_regime_v1_vs_reaka_v1_round2_310_registry_202_stock_proxy_2018_2020"
ROUND2_ITERATION_ID: Final = "macro-regime-v1-vs-reaka-v1-round2-310-registry-202-stock-proxy"
INCUMBENT_STRATEGY_ID: Final = "macro_regime_conditioned_multifactor_v1"
CHALLENGER_STRATEGY_ID: Final = "reaka_adaptive_koopman_v1"
INCUMBENT_ARM_ID: Final = "legacy_202_factor_adaptive_allocator_proxy"
CHALLENGER_ARM_ID: Final = "reaka_202_factor_adaptive_koopman_diffusion"

_FALSE_AUTHORITY: Final[dict[str, bool]] = {
    "factor_admission_allowed": False,
    "asset_selection_allowed": False,
    "individual_stock_scoring_allowed": False,
    "portfolio_construction_allowed": False,
    "portfolio_execution": False,
    "holdings_created": False,
    "orders_created": False,
    "production_authority": False,
}


@dataclass(frozen=True, slots=True)
class Round2Config:
    """Frozen model, sample, cost, and allocator choices."""

    lookback_months: int = 6
    minimum_feature_coverage: float = 0.50
    duplicate_resolution_policy: str = "keep_first_matching_historical_consumer"
    latent_dim: int = 16
    encoder_hidden_dim: int = 32
    operator_count: int = 4
    base_epochs: int = 10
    residual_epochs: int = 10
    diffusion_steps: int = 6
    batch_size: int = 1024
    learning_rate: float = 1e-3
    ridge_penalty: float = 1e-2
    validation_years: tuple[int, ...] = (2019, 2020)
    seeds: tuple[int, ...] = (11, 29, 47)
    top_bottom_fraction: float = 0.20
    long_only_count: int = 50
    one_way_cost_bps: float = 15.0
    allocator_lookback_days: int = 60
    allocator_fast_days: int = 20
    allocator_min_periods: int = 20
    allocator_min_hit_rate: float = 0.48
    allocator_max_active_factors: int = 80
    allocator_min_active_factors: int = 25
    allocator_factor_cap: float = 0.06
    allocator_family_cap: float = 0.30
    allocator_corr_threshold: float = 0.85
    bootstrap_replicates: int = 5000
    bootstrap_block_months: int = 3

    def as_dict(self) -> dict[str, object]:
        return {
            "lookback_months": self.lookback_months,
            "minimum_feature_coverage": self.minimum_feature_coverage,
            "duplicate_resolution_policy": self.duplicate_resolution_policy,
            "latent_dim": self.latent_dim,
            "encoder_hidden_dim": self.encoder_hidden_dim,
            "operator_count": self.operator_count,
            "base_epochs": self.base_epochs,
            "residual_epochs": self.residual_epochs,
            "diffusion_steps": self.diffusion_steps,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "ridge_penalty": self.ridge_penalty,
            "validation_years": list(self.validation_years),
            "seeds": list(self.seeds),
            "top_bottom_fraction": self.top_bottom_fraction,
            "long_only_count": self.long_only_count,
            "one_way_cost_bps": self.one_way_cost_bps,
            "allocator_lookback_days": self.allocator_lookback_days,
            "allocator_fast_days": self.allocator_fast_days,
            "allocator_min_periods": self.allocator_min_periods,
            "allocator_min_hit_rate": self.allocator_min_hit_rate,
            "allocator_max_active_factors": self.allocator_max_active_factors,
            "allocator_min_active_factors": self.allocator_min_active_factors,
            "allocator_factor_cap": self.allocator_factor_cap,
            "allocator_family_cap": self.allocator_family_cap,
            "allocator_corr_threshold": self.allocator_corr_threshold,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_block_months": self.bootstrap_block_months,
        }


@dataclass(frozen=True, slots=True)
class Round2Panel:
    """Compact monthly factor cube plus sample coordinates.

    Sequences are gathered lazily from ``features``.  This avoids duplicating a
    roughly 100 MB factor cube into current/previous sequence tensors.
    """

    month_dates: NDArray[np.datetime64]
    symbols: NDArray[np.str_]
    factor_ids: tuple[str, ...]
    features: NDArray[np.float32]
    observed: NDArray[np.bool_]
    feature_coverage: NDArray[np.float32]
    targets: NDArray[np.float64]
    target_available_at: NDArray[np.datetime64]
    tradeable: NDArray[np.bool_]
    sample_month_indices: NDArray[np.int64]
    sample_symbol_indices: NDArray[np.int64]

    def __len__(self) -> int:
        return int(self.sample_month_indices.size)


@dataclass(frozen=True, slots=True)
class ReakaFitResult:
    """One seed/fold challenger result."""

    scores: NDArray[np.float64]
    operator_ids: NDArray[np.int64]
    operator_matrices: NDArray[np.float64]
    score_components: dict[str, NDArray[np.float64]]
    diagnostics: dict[str, object]


def build_factor_coverage(
    registry: Mapping[str, object],
    *,
    stock_exposure_factor_ids: set[str],
    materialized_context_by_source: Mapping[str, set[str]],
) -> pd.DataFrame:
    """Classify all recovered candidates without manufacturing missing values."""

    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("round2_registry_candidates_required")
    source_refs: dict[str, str] = {}
    for raw in cast(list[object], registry.get("source_artifacts", [])):
        if isinstance(raw, Mapping):
            source_refs[str(raw.get("source_id", ""))] = str(raw.get("ref", ""))

    rows: list[dict[str, object]] = []
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            raise ValueError("round2_registry_candidate_object_required")
        candidate = cast(Mapping[str, object], raw)
        candidate_id = str(candidate.get("candidate_id", ""))
        source_factor_id = str(candidate.get("source_factor_id", ""))
        source_id = str(candidate.get("source_id", ""))
        lane = str(candidate.get("source_lane", ""))
        scope = str(candidate.get("carrier_scope", ""))
        materialization_status: str
        battle_role: str
        executable = False
        exclusion_reason = ""

        if lane == "stock_factor_history":
            if source_factor_id in stock_exposure_factor_ids:
                materialization_status = "materialized_stock_cross_section"
                battle_role = "cross_sectional_alpha_input"
                executable = True
            else:
                materialization_status = "registered_missing_stock_materialization"
                battle_role = "deferred_cross_sectional_alpha"
                exclusion_reason = "stock_exposure_column_missing"
        elif source_factor_id in materialized_context_by_source.get(source_id, set()):
            materialization_status = "materialized_non_stock_context"
            battle_role = "deferred_context_input"
            if source_id == "entity_catch_up_registry":
                exclusion_reason = "entity_panel_not_mapped_to_stock_symbols"
            elif source_id == "macro_registry":
                exclusion_reason = "macro_consumer_contract_missing_or_context_not_stock_alpha"
            else:
                exclusion_reason = "context_series_has_no_direct_stock_cross_section"
        elif scope == "diagnostic_only":
            materialization_status = "diagnostic_identity_only"
            battle_role = "diagnostic_only"
            exclusion_reason = "diagnostic_must_not_vote_as_alpha"
        elif scope == "fund_adapter_only":
            materialization_status = "adapter_identity_only"
            battle_role = "fund_adapter_only"
            exclusion_reason = "fund_premium_discount_has_no_stock_semantics"
        elif lane.startswith("timing"):
            materialization_status = "registered_formula_without_stock_materializer"
            battle_role = "deferred_timing_cross_section"
            exclusion_reason = "stock_level_formula_and_normalization_not_frozen"
        elif lane == "sector_strategy_composite":
            materialization_status = "strategy_composite_not_atomic_factor"
            battle_role = "deferred_family_context"
            exclusion_reason = "composite_requires_atomic_decomposition"
        elif lane == "fund_strategy_components":
            materialization_status = "registered_formula_without_stock_materializer"
            battle_role = "deferred_carrier_neutral_candidate"
            exclusion_reason = "stock_adapter_formula_and_lineage_not_frozen"
        else:
            materialization_status = "unresolved_registry_identity"
            battle_role = "deferred_unresolved"
            exclusion_reason = "materialization_source_not_resolved"

        rows.append(
            {
                "candidate_id": candidate_id,
                "source_lane": lane,
                "source_id": source_id,
                "source_factor_id": source_factor_id,
                "mechanism_family": str(candidate.get("mechanism_family", "")),
                "carrier_scope": scope,
                "current_research_status": str(candidate.get("current_research_status", "")),
                "data_authority_status": str(candidate.get("data_authority_status", "")),
                "materialization_status": materialization_status,
                "battle_role": battle_role,
                "executable_round2": executable,
                "exclusion_reason": exclusion_reason,
                "source_ref": source_refs.get(source_id, "generated_or_embedded_registry_source"),
                "production_authority": False,
            }
        )

    frame = pd.DataFrame(rows).sort_values("candidate_id", kind="stable").reset_index(drop=True)
    expected_count = int(registry.get("candidate_count", len(frame)))
    if len(frame) != expected_count or frame["candidate_id"].nunique() != expected_count:
        raise ValueError("round2_factor_coverage_registry_identity_mismatch")
    return frame


def summarize_factor_coverage(coverage: pd.DataFrame) -> dict[str, object]:
    """Return deterministic registry/materialization counts."""

    return {
        "registered_candidate_count": int(len(coverage)),
        "executable_stock_factor_count": int(coverage["executable_round2"].sum()),
        "materialized_context_count": int(coverage["materialization_status"].eq("materialized_non_stock_context").sum()),
        "materialization_status_counts": {
            str(key): int(value) for key, value in coverage["materialization_status"].value_counts().sort_index().items()
        },
        "source_lane_counts": {str(key): int(value) for key, value in coverage["source_lane"].value_counts().sort_index().items()},
        "battle_role_counts": {str(key): int(value) for key, value in coverage["battle_role"].value_counts().sort_index().items()},
        "placeholder_factor_count": 0,
    }


def rank_factor_cube(raw_features: NDArray[np.float32]) -> tuple[NDArray[np.float32], NDArray[np.bool_]]:
    """Cross-sectionally rank values and retain an explicit observation mask.

    Missing cells use zero only as a storage sentinel.  Consumers must use the
    returned mask to distinguish that sentinel from a genuinely observed
    cross-sectional median.
    """

    if raw_features.ndim != 3:
        raise ValueError("round2_raw_feature_cube_must_be_three_dimensional")
    observed = np.isfinite(raw_features)
    ranked = np.zeros(raw_features.shape, dtype=np.float32)
    for month_index in range(raw_features.shape[0]):
        frame = pd.DataFrame(raw_features[month_index].astype(np.float64, copy=False))
        month_rank = frame.rank(method="average", pct=True, axis=0).to_numpy(dtype=np.float64)
        ranked[month_index] = np.nan_to_num(month_rank - 0.5, nan=0.0).astype(np.float32)
    return ranked, observed


def build_round2_panel(
    *,
    month_dates: NDArray[np.datetime64],
    symbols: NDArray[np.str_],
    factor_ids: Sequence[str],
    raw_features: NDArray[np.float32],
    targets: NDArray[np.float64],
    target_available_at: NDArray[np.datetime64],
    tradeable: NDArray[np.bool_],
    config: Round2Config,
) -> Round2Panel:
    """Build the audited sample coordinates over a compact monthly cube."""

    if config.lookback_months < 2:
        raise ValueError("round2_lookback_must_be_at_least_two")
    expected_shape = (month_dates.size, symbols.size)
    if raw_features.shape != (*expected_shape, len(factor_ids)):
        raise ValueError("round2_raw_feature_shape_mismatch")
    if targets.shape != expected_shape or target_available_at.shape != expected_shape:
        raise ValueError("round2_target_shape_mismatch")
    if tradeable.shape != expected_shape:
        raise ValueError("round2_tradeability_shape_mismatch")
    if len(set(factor_ids)) != len(factor_ids):
        raise ValueError("round2_factor_ids_must_be_unique")

    ranked, observed = rank_factor_cube(raw_features)
    coverage = observed.mean(axis=2).astype(np.float32)
    sample_months: list[int] = []
    sample_symbols: list[int] = []
    for month_index in range(config.lookback_months, month_dates.size):
        sequence_coverage = coverage[month_index - config.lookback_months : month_index + 1]
        continuous = np.all(sequence_coverage >= config.minimum_feature_coverage, axis=0)
        # Sample membership is fixed entirely from decision-time information.
        # A future return that cannot be formed remains a missing label; it
        # must not remove the stock from the universe that was actually scored.
        valid = continuous & tradeable[month_index]
        symbol_indices = np.flatnonzero(valid)
        sample_months.extend([month_index] * int(symbol_indices.size))
        sample_symbols.extend(symbol_indices.tolist())
    if not sample_months:
        raise ValueError("round2_sample_index_empty")

    panel = Round2Panel(
        month_dates=month_dates.astype("datetime64[ns]"),
        symbols=symbols.astype(np.str_),
        factor_ids=tuple(str(value) for value in factor_ids),
        features=ranked,
        observed=observed,
        feature_coverage=coverage,
        targets=targets,
        target_available_at=target_available_at.astype("datetime64[ns]"),
        tradeable=tradeable,
        sample_month_indices=np.asarray(sample_months, dtype=np.int64),
        sample_symbol_indices=np.asarray(sample_symbols, dtype=np.int64),
    )
    _validate_panel(panel, config=config)
    return panel


def fold_indices(
    panel: Round2Panel,
    *,
    validation_year: int,
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Create an anchored fold without deriving the score universe from labels.

    Training rows require a finite target that was available before the fold
    start.  Test rows are every decision-time-eligible row in the validation
    year; missing future outcomes remain missing labels and are filtered only
    by evaluation, after both arms have scored the identical universe.
    """

    dates = panel.month_dates[panel.sample_month_indices]
    available = panel.target_available_at[panel.sample_month_indices, panel.sample_symbol_indices]
    targets = panel.targets[panel.sample_month_indices, panel.sample_symbol_indices]
    start = np.datetime64(f"{validation_year}-01-01", "ns")
    end = np.datetime64(f"{validation_year + 1}-01-01", "ns")
    labeled = np.isfinite(targets) & ~np.isnat(available)
    train = np.flatnonzero((dates < start) & labeled & (available < start)).astype(np.int64)
    test = np.flatnonzero((dates >= start) & (dates < end)).astype(np.int64)
    if train.size < 1000:
        raise ValueError(f"round2_fold_training_rows_insufficient:{validation_year}")
    if test.size < 1000:
        raise ValueError(f"round2_fold_test_rows_insufficient:{validation_year}")
    return train, test


class AdaptiveKoopmanAutoencoder(nn.Module):
    def __init__(self, *, input_dim: int, config: Round2Config) -> None:
        super().__init__()
        self.alpha_dim = input_dim
        self.mask_control_dim = input_dim
        self.encoder_input_dim = input_dim
        self.latent_dim = config.latent_dim
        self.operator_count = config.operator_count
        self.encoder = nn.LSTM(
            input_size=self.encoder_input_dim,
            hidden_size=config.encoder_hidden_dim,
            batch_first=True,
        )
        self.projection = nn.Linear(config.encoder_hidden_dim, config.latent_dim)
        self.decoder = nn.Sequential(
            nn.Linear(config.latent_dim, config.encoder_hidden_dim),
            nn.SiLU(),
            nn.Linear(config.encoder_hidden_dim, self.alpha_dim),
        )
        identity = torch.eye(config.latent_dim).repeat(config.operator_count, 1, 1)
        self.operators = nn.Parameter(identity + 0.01 * torch.randn_like(identity))
        self.selector = nn.Linear(config.latent_dim, config.operator_count)
        self.target_head = nn.Linear(config.latent_dim, 1)

    def encode(self, sequence: Tensor, observed: Tensor) -> Tensor:
        """Encode gated alpha values; the mask cannot generate signal alone."""

        if sequence.shape != observed.shape or sequence.shape[-1] != self.alpha_dim:
            raise ValueError("reaka_encoder_value_mask_shape_mismatch")
        mask = observed.to(dtype=sequence.dtype)
        observed_count = mask.sum(dim=2, keepdim=True).clamp_min(1.0)
        scale = torch.sqrt(
            torch.as_tensor(
                float(self.alpha_dim),
                dtype=sequence.dtype,
                device=sequence.device,
            )
            / observed_count
        )
        gated = sequence * mask * scale
        hidden = self.encoder(gated)[1][0][-1]
        return torch.tanh(self.projection(hidden))

    def transition(self, latent: Tensor, *, gumbel: bool) -> tuple[Tensor, Tensor]:
        logits = self.selector(latent)
        if gumbel:
            weights = F.gumbel_softmax(logits, tau=0.75, hard=False, dim=1)
        else:
            selected = torch.argmax(logits, dim=1)
            weights = F.one_hot(selected, num_classes=self.operator_count).to(latent.dtype)
        transformed = torch.einsum("kij,bj->bki", self.operators, latent)
        return torch.einsum("bk,bki->bi", weights, transformed), weights

    def objective(
        self,
        previous_sequence: Tensor,
        previous_observed: Tensor,
        current_sequence: Tensor,
        current_observed: Tensor,
        target: Tensor,
    ) -> tuple[Tensor, dict[str, Tensor]]:
        previous_latent = self.encode(previous_sequence, previous_observed)
        current_latent = self.encode(current_sequence, current_observed)
        predicted_current, selector_weights = self.transition(previous_latent, gumbel=True)
        predicted_next, _ = self.transition(current_latent, gumbel=True)
        reconstructed_latest = self.decoder(current_latent)
        latest_values = current_sequence[:, -1, :]
        latest_observed = current_observed[:, -1, :].to(dtype=latest_values.dtype)
        squared_error = torch.square(reconstructed_latest - latest_values)
        reconstruction_loss = torch.sum(squared_error * latest_observed) / torch.clamp_min(
            latest_observed.sum(),
            1.0,
        )
        dynamics_loss = F.mse_loss(predicted_current, current_latent)
        prediction_loss = F.smooth_l1_loss(self.target_head(predicted_next).squeeze(1), target)
        occupancy = selector_weights.mean(dim=0).clamp_min(1e-8)
        balance_penalty = torch.sum(occupancy * torch.log(occupancy * self.operator_count))
        variance_penalty = torch.relu(0.02 - current_latent.var(dim=0, unbiased=False)).mean()
        total = 0.40 * reconstruction_loss + dynamics_loss + 0.60 * prediction_loss + 0.02 * balance_penalty + 0.05 * variance_penalty
        return total, {
            "reconstruction_loss": reconstruction_loss,
            "dynamics_loss": dynamics_loss,
            "prediction_loss": prediction_loss,
            "balance_penalty": balance_penalty,
            "latent_variance_penalty": variance_penalty,
        }


class _ResidualDenoiser(nn.Module):
    def __init__(self, *, latent_dim: int, diffusion_steps: int) -> None:
        super().__init__()
        self.time_embedding = nn.Embedding(diffusion_steps, 8)
        self.network = nn.Sequential(
            nn.Linear(latent_dim * 3 + 8, 64),
            nn.SiLU(),
            nn.Linear(64, 64),
            nn.SiLU(),
            nn.Linear(64, latent_dim),
        )

    def forward(self, noisy: Tensor, condition: Tensor, steps: Tensor) -> Tensor:
        return self.network(torch.cat([noisy, condition, self.time_embedding(steps)], dim=1))


def fit_reaka_challenger(
    *,
    panel: Round2Panel,
    train_indices: NDArray[np.int64],
    test_indices: NDArray[np.int64],
    config: Round2Config,
    seed: int,
) -> ReakaFitResult:
    """Fit the full adaptive-K plus diffusion-residual challenger."""

    _seed_everything(seed)
    torch.set_num_threads(1)
    train_targets_raw = _sample_targets(panel, train_indices)
    lower, upper = np.quantile(train_targets_raw, [0.01, 0.99])
    clipped = np.clip(train_targets_raw, lower, upper)
    target_mean = float(clipped.mean())
    target_scale = float(clipped.std(ddof=0))
    if target_scale < 1e-8:
        target_scale = 1.0
    normalized_targets = ((clipped - target_mean) / target_scale).astype(np.float32)

    model = AdaptiveKoopmanAutoencoder(input_dim=len(panel.factor_ids), config=config)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    rng = np.random.default_rng(seed)
    last_losses: dict[str, float] = {}
    model.train()
    for _ in range(config.base_epochs):
        order = rng.permutation(train_indices.size)
        sums: dict[str, float] = {}
        cells = 0
        for start in range(0, order.size, config.batch_size):
            positions = order[start : start + config.batch_size]
            batch_indices = train_indices[positions]
            previous, previous_observed, current, current_observed = _sequence_pair(
                panel,
                batch_indices,
                config=config,
            )
            target = normalized_targets[positions]
            optimizer.zero_grad(set_to_none=True)
            loss, components = model.objective(
                torch.from_numpy(previous),
                torch.from_numpy(previous_observed),
                torch.from_numpy(current),
                torch.from_numpy(current_observed),
                torch.from_numpy(target),
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            for key, value in components.items():
                sums[key] = sums.get(key, 0.0) + float(value.detach()) * len(positions)
            cells += len(positions)
        last_losses = {key: value / max(cells, 1) for key, value in sums.items()}

    train_latent = _extract_latent_bundle(model, panel, train_indices, config=config)
    test_latent = _extract_latent_bundle(model, panel, test_indices, config=config)
    denoiser, residual_scale, residual_training = _fit_residual_denoiser(
        train_latent=train_latent,
        config=config,
        seed=seed,
    )
    train_correction = _sample_diffusion_residual(
        denoiser,
        latent=train_latent["current"],
        base_next=train_latent["base_next"],
        residual_scale=residual_scale,
        config=config,
    )
    test_correction = _sample_diffusion_residual(
        denoiser,
        latent=test_latent["current"],
        base_next=test_latent["base_next"],
        residual_scale=residual_scale,
        config=config,
    )
    train_forecast = train_latent["base_next"] + train_correction
    test_forecast = test_latent["base_next"] + test_correction
    coefficients = _fit_ridge(train_forecast, normalized_targets.astype(np.float64), config.ridge_penalty)
    scores = _predict_ridge(test_forecast, coefficients)
    factor_scores = _predict_ridge(cast(NDArray[np.float64], test_latent["current"]), coefficients)
    state_path_scores = _predict_ridge(cast(NDArray[np.float64], test_latent["base_next"]), coefficients)
    score_components = {
        "factor_encoding_base": factor_scores,
        "adaptive_state_dynamics_increment": state_path_scores - factor_scores,
        "dynamic_residual_increment": scores - state_path_scores,
    }
    reconciled_scores = sum(score_components.values(), np.zeros_like(scores))
    score_reconciliation_error = float(np.max(np.abs(scores - reconciled_scores)))
    operators = model.operators.detach().cpu().numpy().astype(np.float64)
    operator_ids = cast(NDArray[np.int64], test_latent["operator_ids"])
    diagnostics: dict[str, object] = {
        "fit_kind": "factor_lstm_adaptive_koopman_autoencoder_with_diffusion_residual",
        "input_factor_count": len(panel.factor_ids),
        "alpha_count": len(panel.factor_ids),
        "mask_control_count": len(panel.factor_ids),
        "learned_encoder_alpha_columns": len(panel.factor_ids),
        "encoder_input_count": len(panel.factor_ids),
        "mask_can_generate_signal_alone": False,
        "encoder_observation_normalization": "sqrt_alpha_count_over_observed_count_after_mask_gating",
        "observation_mask_is_alpha_vote": False,
        "reconstruction_loss_observed_cells_only": True,
        "missing_value_storage_sentinel": 0.0,
        "train_row_count": int(train_indices.size),
        "test_row_count": int(test_indices.size),
        "target_train_clip": [float(lower), float(upper)],
        "base_training_last_epoch": last_losses,
        "operator_count": config.operator_count,
        "operator_occupancy": _operator_occupancy(operator_ids, config.operator_count),
        "operator_digest": canonical_digest(operators.round(10).tolist()),
        "latent_train_mean_std": float(np.std(train_latent["current"], axis=0).mean()),
        "latent_test_mean_std": float(np.std(test_latent["current"], axis=0).mean()),
        "residual_training": residual_training,
        "train_residual_correction_energy_ratio": _energy_ratio(train_correction, train_latent["base_next"]),
        "test_residual_correction_energy_ratio": _energy_ratio(test_correction, test_latent["base_next"]),
        "ranking_head": "train_only_ridge_on_corrected_forecast_latent",
        "ranking_head_coefficient_norm": float(np.linalg.norm(coefficients[1:])),
        "score_decomposition": ("shared_final_ridge_head:intercept_plus_wT_Z+wT_KsZ_minus_Z+wT_residual"),
        "score_decomposition_max_abs_error": score_reconciliation_error,
    }
    return ReakaFitResult(
        scores=scores,
        operator_ids=operator_ids,
        operator_matrices=operators,
        score_components=score_components,
        diagnostics=diagnostics,
    )


def build_incumbent_weight_table(
    factor_excess_returns: pd.DataFrame,
    *,
    decision_dates: Sequence[pd.Timestamp],
    factor_ids: Sequence[str],
    mechanism_family_by_factor: Mapping[str, str],
    config: Round2Config,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Reproduce the historical adaptive allocator with strict date lagging."""

    missing = sorted(set(factor_ids) - set(factor_excess_returns.columns))
    if missing:
        raise ValueError("round2_incumbent_factor_return_columns_missing:" + ",".join(missing))
    returns = factor_excess_returns.loc[:, list(factor_ids)].sort_index().astype(float)
    rows: list[pd.Series] = []
    fallback_dates: list[str] = []
    active_counts: list[int] = []
    for raw_date in decision_dates:
        date = pd.Timestamp(raw_date)
        history = returns.loc[returns.index < date].tail(config.allocator_lookback_days)
        valid_count = history.notna().sum()
        mean = history.mean()
        vol = history.std(ddof=1).clip(lower=1e-4)
        sharpe = mean.div(vol).mul(math.sqrt(252.0))
        hit_rate = history.gt(0.0).mean()
        fast_sum = history.tail(config.allocator_fast_days).sum()
        raw_score = sharpe.clip(lower=0.0)
        raw_score = raw_score.where(valid_count >= config.allocator_min_periods, 0.0)
        raw_score = raw_score.where(hit_rate >= config.allocator_min_hit_rate, 0.0)
        raw_score = raw_score.where(fast_sum > 0.0, 0.0)
        weights = _select_low_redundancy(
            raw_score,
            history,
            mechanism_family_by_factor=mechanism_family_by_factor,
            config=config,
        )
        if float(weights.sum()) <= 0.0:
            fallback_dates.append(date.strftime("%Y-%m-%d"))
            prior = mean.where(valid_count >= config.allocator_min_periods).clip(lower=0.0).dropna()
            if prior.empty:
                prior = pd.Series(1.0, index=list(factor_ids), dtype=float)
            weights = _apply_caps(
                prior,
                mechanism_family_by_factor=mechanism_family_by_factor,
                config=config,
            ).reindex(factor_ids, fill_value=0.0)
        weights = weights.reindex(factor_ids, fill_value=0.0).astype(np.float32)
        weights.name = date
        rows.append(weights)
        active_counts.append(int((weights > 0.0).sum()))
    table = pd.DataFrame(rows).sort_index()
    diagnostics = {
        "fit_kind": "legacy_lagged_factor_return_adaptive_allocator",
        "decision_count": len(rows),
        "fallback_decision_dates": fallback_dates,
        "average_active_factor_count": float(np.mean(active_counts)),
        "minimum_active_factor_count": int(min(active_counts)),
        "maximum_active_factor_count": int(max(active_counts)),
        "lookback_days": config.allocator_lookback_days,
        "fast_confirmation_days": config.allocator_fast_days,
        "factor_cap": config.allocator_factor_cap,
        "family_cap": config.allocator_family_cap,
        "future_factor_return_rows_read": False,
    }
    return table, diagnostics


def score_incumbent(
    panel: Round2Panel,
    *,
    sample_indices: NDArray[np.int64],
    weights: pd.DataFrame,
) -> NDArray[np.float64]:
    """Apply previsible weights without shrinking scores for honest gaps.

    Missing values remain neutral, while the weights that are actually
    observed for each stock are renormalized back to the same absolute mass.
    Thus two otherwise identical signals do not receive different score scales
    merely because one stock has fewer observed factor cells.
    """

    result = np.zeros(sample_indices.size, dtype=np.float64)
    months = panel.sample_month_indices[sample_indices]
    symbols = panel.sample_symbol_indices[sample_indices]
    for month_index in np.unique(months):
        positions = np.flatnonzero(months == month_index)
        date = pd.Timestamp(panel.month_dates[month_index])
        if date not in weights.index:
            raise ValueError(f"round2_incumbent_weight_date_missing:{date.date()}")
        matrix = panel.features[month_index, symbols[positions], :].astype(np.float64, copy=False)
        weight = weights.loc[date].to_numpy(dtype=np.float64)
        result[positions] = score_with_observed_weight_mass(
            matrix,
            observed=panel.observed[month_index, symbols[positions], :],
            weights=weight,
        )
    return result


def score_with_observed_weight_mass(
    values: NDArray[np.float64],
    *,
    observed: NDArray[np.bool_],
    weights: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Score rows on a constant absolute-weight scale across honest gaps."""

    if values.ndim != 2 or observed.shape != values.shape:
        raise ValueError("factor_score_value_observation_shape_mismatch")
    if weights.shape != (values.shape[1],):
        raise ValueError("factor_score_weight_shape_mismatch")
    full_mass = float(np.abs(weights).sum())
    observed_mass = observed.astype(np.float64) @ np.abs(weights)
    raw = values @ weights
    return np.divide(
        raw * full_mass,
        observed_mass,
        out=np.zeros_like(raw),
        where=observed_mass > 1e-12,
    )


def prediction_frame(
    panel: Round2Panel,
    *,
    sample_indices: NDArray[np.int64],
    scores: NDArray[np.float64],
    strategy_id: str,
    arm_id: str,
    seed: int | None,
    validation_year: int,
) -> pd.DataFrame:
    """Create a common scoring frame for either strategy."""

    if scores.shape != (sample_indices.size,):
        raise ValueError("round2_prediction_score_shape_mismatch")
    months = panel.sample_month_indices[sample_indices]
    symbols = panel.sample_symbol_indices[sample_indices]
    return pd.DataFrame(
        {
            "strategy_id": strategy_id,
            "arm_id": arm_id,
            "seed": seed,
            "validation_year": validation_year,
            "date": pd.to_datetime(panel.month_dates[months]),
            "symbol": panel.symbols[symbols],
            "score": scores,
            "target_return": panel.targets[months, symbols],
            "target_available_at": pd.to_datetime(panel.target_available_at[months, symbols]),
            "feature_coverage": panel.feature_coverage[months, symbols],
        }
    )


def evaluate_predictions(
    predictions: pd.DataFrame,
    *,
    config: Round2Config,
) -> tuple[dict[str, float | int], pd.DataFrame]:
    """Evaluate factor spread and a secondary Top-50 long-only portfolio."""

    required = {"date", "symbol", "score", "target_return"}
    if not required.issubset(predictions.columns):
        raise ValueError("round2_prediction_columns_missing")
    monthly_rows: list[dict[str, object]] = []
    previous_top: set[str] = set()
    previous_bottom: set[str] = set()
    previous_long: set[str] = set()
    for date, raw_group in predictions.groupby("date", sort=True, observed=True):
        eligible = raw_group.dropna(subset=["score", "target_return"]).sort_values("symbol", ascending=True, kind="stable")
        universe_return = float(eligible["target_return"].mean())
        group = eligible.sort_values(["score", "symbol"], ascending=[False, True], kind="stable")
        if len(group) < 20:
            continue
        leg_count = max(2, int(math.floor(len(group) * config.top_bottom_fraction)))
        top = group.head(leg_count)
        bottom = group.tail(leg_count)
        long_only = group.head(min(config.long_only_count, len(group)))
        top_members = set(top["symbol"].astype(str))
        bottom_members = set(bottom["symbol"].astype(str))
        long_members = set(long_only["symbol"].astype(str))
        top_turnover = _equal_weight_turnover(previous_top, top_members)
        bottom_turnover = _equal_weight_turnover(previous_bottom, bottom_members)
        long_turnover = _equal_weight_turnover(previous_long, long_members)
        gross_spread = float(top["target_return"].mean() - bottom["target_return"].mean())
        spread_cost = (top_turnover + bottom_turnover) * config.one_way_cost_bps / 10_000.0
        long_gross = float(long_only["target_return"].mean())
        long_cost = long_turnover * config.one_way_cost_bps / 10_000.0
        target_rank = group["target_return"].rank(method="average", pct=True)
        score_rank = group["score"].rank(method="average", pct=True)
        rank_ic = float(score_rank.corr(target_rank))
        monthly_rows.append(
            {
                "date": pd.Timestamp(date),
                "eligible_count": int(len(group)),
                "rank_ic": rank_ic,
                "top_count": int(len(top)),
                "bottom_count": int(len(bottom)),
                "gross_spread_return": gross_spread,
                "spread_turnover": top_turnover + bottom_turnover,
                "spread_cost": spread_cost,
                "net_spread_return": gross_spread - spread_cost,
                "long_only_count": int(len(long_only)),
                "long_only_gross_return": long_gross,
                "long_only_turnover": long_turnover,
                "long_only_cost": long_cost,
                "long_only_net_return": long_gross - long_cost,
                "equal_weight_universe_return": universe_return,
            }
        )
        previous_top = top_members
        previous_bottom = bottom_members
        previous_long = long_members
    monthly = pd.DataFrame(monthly_rows).sort_values("date", kind="stable").reset_index(drop=True)
    if monthly.empty:
        raise ValueError("round2_monthly_evaluation_empty")
    spread = monthly["net_spread_return"].to_numpy(dtype=np.float64)
    long_return = monthly["long_only_net_return"].to_numpy(dtype=np.float64)
    benchmark = monthly["equal_weight_universe_return"].to_numpy(dtype=np.float64)
    metrics: dict[str, float | int] = {
        "month_count": int(len(monthly)),
        "mean_rank_ic": float(monthly["rank_ic"].mean()),
        "rank_ic_positive_month_rate": float(monthly["rank_ic"].gt(0.0).mean()),
        "cost_adjusted_annualized_spread_return": _annualized_return(spread),
        "spread_sharpe": _annualized_sharpe(spread),
        "spread_max_drawdown": _maximum_drawdown(spread),
        "average_annualized_spread_turnover": float(monthly["spread_turnover"].mean() * 12.0),
        "long_only_annualized_return": _annualized_return(long_return),
        "long_only_annualized_equal_weight_excess": _annualized_return(long_return) - _annualized_return(benchmark),
        "long_only_sharpe": _annualized_sharpe(long_return),
        "long_only_max_drawdown": _maximum_drawdown(long_return),
        "average_annualized_long_only_turnover": float(monthly["long_only_turnover"].mean() * 12.0),
        "average_eligible_stock_count": float(monthly["eligible_count"].mean()),
    }
    return metrics, monthly


def build_factor_scorecard(
    panel: Round2Panel,
    *,
    validation_years: Sequence[int],
    mechanism_family_by_factor: Mapping[str, str],
) -> pd.DataFrame:
    """Run the one-shot 202-factor table with BH multiplicity control."""

    sample_dates = panel.month_dates[panel.sample_month_indices]
    sample_available = panel.target_available_at[
        panel.sample_month_indices,
        panel.sample_symbol_indices,
    ]
    sample_targets = panel.targets[
        panel.sample_month_indices,
        panel.sample_symbol_indices,
    ]
    eligible_mask = np.zeros(sample_dates.shape, dtype=np.bool_)
    for year in validation_years:
        start = np.datetime64(f"{int(year)}-01-01", "ns")
        end = np.datetime64(f"{int(year) + 1}-01-01", "ns")
        eligible_mask |= (
            (sample_dates >= start)
            & (sample_dates < end)
            & np.isfinite(sample_targets)
            & ~np.isnat(sample_available)
            & (sample_available < end)
        )
    eligible_indices = np.flatnonzero(eligible_mask).astype(np.int64)
    monthly_ic: list[list[float]] = [[] for _ in panel.factor_ids]
    monthly_spread: list[list[float]] = [[] for _ in panel.factor_ids]
    year_ic: dict[int, list[list[float]]] = {int(year): [[] for _ in panel.factor_ids] for year in validation_years}
    coverage_sum = np.zeros(len(panel.factor_ids), dtype=np.float64)
    coverage_cells = np.zeros(len(panel.factor_ids), dtype=np.float64)

    months = panel.sample_month_indices[eligible_indices]
    for month_index in np.unique(months):
        positions = eligible_indices[months == month_index]
        symbol_indices = panel.sample_symbol_indices[positions]
        target = panel.targets[month_index, symbol_indices]
        target_rank = pd.Series(target).rank(method="average", pct=True).to_numpy(dtype=np.float64)
        year = int(pd.Timestamp(panel.month_dates[month_index]).year)
        for factor_index in range(len(panel.factor_ids)):
            observed = panel.observed[month_index, symbol_indices, factor_index]
            coverage_sum[factor_index] += float(observed.sum())
            coverage_cells[factor_index] += float(observed.size)
            if int(observed.sum()) < 20:
                continue
            feature = panel.features[month_index, symbol_indices, factor_index][observed].astype(np.float64)
            local_target_rank = target_rank[observed]
            if float(np.std(feature)) < 1e-12 or float(np.std(local_target_rank)) < 1e-12:
                continue
            ic = float(np.corrcoef(feature, local_target_rank)[0, 1])
            order = np.argsort(feature, kind="stable")
            leg_count = max(2, int(math.floor(order.size * 0.20)))
            raw_target = target[observed]
            spread = float(raw_target[order[-leg_count:]].mean() - raw_target[order[:leg_count]].mean())
            monthly_ic[factor_index].append(ic)
            monthly_spread[factor_index].append(spread)
            if year in year_ic:
                year_ic[year][factor_index].append(ic)

    p_values = np.ones(len(panel.factor_ids), dtype=np.float64)
    rows: list[dict[str, object]] = []
    for factor_index, factor_id in enumerate(panel.factor_ids):
        ic_values = np.asarray(monthly_ic[factor_index], dtype=np.float64)
        spread_values = np.asarray(monthly_spread[factor_index], dtype=np.float64)
        if ic_values.size >= 3 and float(ic_values.std(ddof=1)) > 0.0:
            p_values[factor_index] = float(stats.ttest_1samp(ic_values, 0.0).pvalue)
        row: dict[str, object] = {
            "factor_id": factor_id,
            "mechanism_family": mechanism_family_by_factor.get(factor_id, "unknown"),
            "validation_month_count": int(ic_values.size),
            "mean_rank_ic": float(ic_values.mean()) if ic_values.size else float("nan"),
            "rank_ic_t_stat": (
                float(ic_values.mean() / (ic_values.std(ddof=1) / math.sqrt(ic_values.size)))
                if ic_values.size >= 3 and float(ic_values.std(ddof=1)) > 0.0
                else float("nan")
            ),
            "rank_ic_p_value": p_values[factor_index],
            "positive_ic_month_rate": float((ic_values > 0.0).mean()) if ic_values.size else float("nan"),
            "mean_gross_top_bottom_spread": float(spread_values.mean()) if spread_values.size else float("nan"),
            "annualized_gross_top_bottom_spread": _annualized_return(spread_values) if spread_values.size else float("nan"),
            "observed_cell_rate": (
                float(coverage_sum[factor_index] / coverage_cells[factor_index]) if coverage_cells[factor_index] > 0 else 0.0
            ),
        }
        for year in validation_years:
            values = np.asarray(year_ic[int(year)][factor_index], dtype=np.float64)
            row[f"mean_rank_ic_{year}"] = float(values.mean()) if values.size else float("nan")
        rows.append(row)
    q_values = _benjamini_hochberg(p_values)
    for row, q_value in zip(rows, q_values, strict=True):
        row["rank_ic_bh_q_value"] = float(q_value)
        row["bh_q_le_0_10"] = bool(q_value <= 0.10)
    frame = pd.DataFrame(rows)
    return frame.sort_values(
        ["rank_ic_bh_q_value", "mean_rank_ic", "factor_id"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def compare_paired_monthly(
    incumbent_monthly: pd.DataFrame,
    challenger_monthly: pd.DataFrame,
    *,
    config: Round2Config,
) -> dict[str, object]:
    """Compare both arms month for month with a fixed block bootstrap."""

    columns = ["date", "net_spread_return", "rank_ic", "long_only_net_return"]
    paired = incumbent_monthly[columns].merge(
        challenger_monthly[columns], on="date", suffixes=("_incumbent", "_challenger"), validate="one_to_one"
    )
    if len(paired) != len(incumbent_monthly) or len(paired) != len(challenger_monthly):
        raise ValueError("round2_paired_monthly_exam_mismatch")
    spread_delta = (paired["net_spread_return_challenger"] - paired["net_spread_return_incumbent"]).to_numpy(dtype=np.float64)
    ic_delta = (paired["rank_ic_challenger"] - paired["rank_ic_incumbent"]).to_numpy(dtype=np.float64)
    long_delta = (paired["long_only_net_return_challenger"] - paired["long_only_net_return_incumbent"]).to_numpy(dtype=np.float64)
    spread_ci = _moving_block_bootstrap_mean_ci(
        spread_delta,
        block_size=config.bootstrap_block_months,
        replicates=config.bootstrap_replicates,
        seed=20260810,
    )
    return {
        "paired_month_count": int(len(paired)),
        "challenger_minus_incumbent_mean_monthly_net_spread": float(spread_delta.mean()),
        "challenger_minus_incumbent_annualized_net_spread": _annualized_return(
            paired["net_spread_return_challenger"].to_numpy(dtype=np.float64)
        )
        - _annualized_return(paired["net_spread_return_incumbent"].to_numpy(dtype=np.float64)),
        "challenger_minus_incumbent_mean_rank_ic": float(ic_delta.mean()),
        "challenger_minus_incumbent_mean_monthly_long_only_return": float(long_delta.mean()),
        "challenger_spread_win_month_rate": float((spread_delta > 0.0).mean()),
        "moving_block_bootstrap": {
            "block_months": config.bootstrap_block_months,
            "replicates": config.bootstrap_replicates,
            "mean_monthly_spread_delta_ci_95": spread_ci,
            "ci_excludes_zero": bool(spread_ci[0] > 0.0 or spread_ci[1] < 0.0),
        },
    }


def validate_round2_result(payload: Mapping[str, object]) -> dict[str, object]:
    """Fail closed on registry, exam, digest, or authority drift."""

    blockers: list[str] = []
    if payload.get("schema_id") != ROUND2_SCHEMA_ID:
        blockers.append("schema_id_mismatch")
    coverage = payload.get("factor_coverage_summary")
    if not isinstance(coverage, Mapping):
        blockers.append("factor_coverage_summary_missing")
    else:
        if int(coverage.get("registered_candidate_count", -1)) != 310:
            blockers.append("registered_candidate_count_not_310")
        if int(coverage.get("executable_stock_factor_count", -1)) <= 0:
            blockers.append("no_executable_stock_factors")
        if int(coverage.get("placeholder_factor_count", -1)) != 0:
            blockers.append("placeholder_factors_forbidden")
    strategies = payload.get("strategy_metrics")
    if not isinstance(strategies, list) or len(strategies) != 2:
        blockers.append("paired_strategy_metrics_required")
    if payload.get("winner_strategy_id") is not None:
        blockers.append("consumed_history_proxy_winner_must_be_null")
    authority = payload.get("authority")
    if not isinstance(authority, Mapping) or dict(authority) != _FALSE_AUTHORITY:
        blockers.append("round2_authority_must_remain_false")
    expected_digest = payload.get("canonical_digest")
    body = dict(payload)
    body.pop("canonical_digest", None)
    if expected_digest != canonical_digest(body):
        blockers.append("canonical_digest_mismatch")
    return {"status": "valid" if not blockers else "invalid", "blockers": blockers}


def seal_round2_result(payload: dict[str, object]) -> None:
    """Attach a canonical digest after all fields are final."""

    payload.pop("canonical_digest", None)
    payload["canonical_digest"] = canonical_digest(payload)


def round2_false_authority() -> dict[str, bool]:
    return dict(_FALSE_AUTHORITY)


def _validate_panel(panel: Round2Panel, *, config: Round2Config) -> None:
    if not np.isfinite(panel.features).all():
        raise ValueError("round2_ranked_features_must_be_finite")
    if len(panel.factor_ids) != panel.features.shape[2]:
        raise ValueError("round2_panel_factor_identity_mismatch")
    months = panel.sample_month_indices
    symbols = panel.sample_symbol_indices
    if bool(np.any(months < config.lookback_months)):
        raise ValueError("round2_sample_sequence_underflow")
    decisions = panel.month_dates[months]
    available = panel.target_available_at[months, symbols]
    targets = panel.targets[months, symbols]
    labeled = np.isfinite(targets)
    if bool(np.any(labeled != ~np.isnat(available))):
        raise ValueError("round2_target_and_availability_must_be_jointly_missing")
    if bool(np.any(available[labeled] <= decisions[labeled])):
        raise ValueError("round2_target_not_strictly_after_decision")
    if bool(np.any(~panel.tradeable[months, symbols])):
        raise ValueError("round2_sample_must_be_decision_time_eligible")
    if bool(np.any(panel.feature_coverage[months, symbols] < config.minimum_feature_coverage)):
        raise ValueError("round2_sample_current_coverage_below_floor")


def _sequence_pair(
    panel: Round2Panel,
    sample_indices: NDArray[np.int64],
    *,
    config: Round2Config,
) -> tuple[
    NDArray[np.float32],
    NDArray[np.float32],
    NDArray[np.float32],
    NDArray[np.float32],
]:
    """Return alpha values and masks as four separate tensors."""

    month = panel.sample_month_indices[sample_indices]
    symbol = panel.sample_symbol_indices[sample_indices]
    current_offsets = np.arange(-config.lookback_months + 1, 1, dtype=np.int64)
    previous_offsets = np.arange(-config.lookback_months, 0, dtype=np.int64)
    current_months = month[:, None] + current_offsets[None, :]
    previous_months = month[:, None] + previous_offsets[None, :]
    symbol_grid = np.broadcast_to(symbol[:, None], current_months.shape)
    current_values = panel.features[current_months, symbol_grid, :]
    previous_values = panel.features[previous_months, symbol_grid, :]
    current_observed = panel.observed[current_months, symbol_grid, :]
    previous_observed = panel.observed[previous_months, symbol_grid, :]
    return (
        previous_values.astype(np.float32, copy=False),
        previous_observed.astype(np.float32),
        current_values.astype(np.float32, copy=False),
        current_observed.astype(np.float32),
    )


def _sample_targets(panel: Round2Panel, indices: NDArray[np.int64]) -> NDArray[np.float64]:
    return panel.targets[
        panel.sample_month_indices[indices],
        panel.sample_symbol_indices[indices],
    ].astype(np.float64)


def _extract_latent_bundle(
    model: AdaptiveKoopmanAutoencoder,
    panel: Round2Panel,
    indices: NDArray[np.int64],
    *,
    config: Round2Config,
) -> dict[str, NDArray[np.float64] | NDArray[np.int64]]:
    previous_rows: list[NDArray[np.float64]] = []
    current_rows: list[NDArray[np.float64]] = []
    base_current_rows: list[NDArray[np.float64]] = []
    base_next_rows: list[NDArray[np.float64]] = []
    operator_rows: list[NDArray[np.int64]] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, indices.size, config.batch_size):
            batch = indices[start : start + config.batch_size]
            previous, previous_observed, current, current_observed = _sequence_pair(
                panel,
                batch,
                config=config,
            )
            previous_latent = model.encode(
                torch.from_numpy(previous),
                torch.from_numpy(previous_observed),
            )
            current_latent = model.encode(
                torch.from_numpy(current),
                torch.from_numpy(current_observed),
            )
            base_current, _ = model.transition(previous_latent, gumbel=False)
            base_next, weights = model.transition(current_latent, gumbel=False)
            previous_rows.append(previous_latent.cpu().numpy().astype(np.float64))
            current_rows.append(current_latent.cpu().numpy().astype(np.float64))
            base_current_rows.append(base_current.cpu().numpy().astype(np.float64))
            base_next_rows.append(base_next.cpu().numpy().astype(np.float64))
            operator_rows.append(torch.argmax(weights, dim=1).cpu().numpy().astype(np.int64))
    return {
        "previous": np.concatenate(previous_rows),
        "current": np.concatenate(current_rows),
        "base_current": np.concatenate(base_current_rows),
        "base_next": np.concatenate(base_next_rows),
        "operator_ids": np.concatenate(operator_rows),
    }


def _fit_residual_denoiser(
    *,
    train_latent: Mapping[str, NDArray[np.float64] | NDArray[np.int64]],
    config: Round2Config,
    seed: int,
) -> tuple[_ResidualDenoiser, float, dict[str, float | int]]:
    _seed_everything(seed + 10_000)
    previous = cast(NDArray[np.float64], train_latent["previous"]).astype(np.float32)
    base_current = cast(NDArray[np.float64], train_latent["base_current"]).astype(np.float32)
    current = cast(NDArray[np.float64], train_latent["current"]).astype(np.float32)
    residual = current - base_current
    residual_scale = float(np.std(residual))
    if residual_scale < 1e-6:
        residual_scale = 1.0
    clean = residual / residual_scale
    condition = np.concatenate([previous, base_current], axis=1)
    model = _ResidualDenoiser(latent_dim=config.latent_dim, diffusion_steps=config.diffusion_steps)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    _, alpha_bar = _diffusion_schedule(config.diffusion_steps)
    rng = np.random.default_rng(seed + 10_000)
    last_loss = 0.0
    model.train()
    for _ in range(config.residual_epochs):
        order = rng.permutation(clean.shape[0])
        total = 0.0
        cells = 0
        for start in range(0, order.size, config.batch_size):
            rows = order[start : start + config.batch_size]
            clean_tensor = torch.from_numpy(clean[rows])
            condition_tensor = torch.from_numpy(condition[rows])
            steps = torch.from_numpy(rng.integers(0, config.diffusion_steps, size=rows.size, dtype=np.int64))
            noise = torch.randn_like(clean_tensor)
            selected_alpha = alpha_bar[steps].unsqueeze(1)
            noisy = torch.sqrt(selected_alpha) * clean_tensor + torch.sqrt(1.0 - selected_alpha) * noise
            optimizer.zero_grad(set_to_none=True)
            predicted_noise = model(noisy, condition_tensor, steps)
            loss = F.mse_loss(predicted_noise, noise)
            loss.backward()
            optimizer.step()
            total += float(loss.detach()) * rows.size
            cells += rows.size
        last_loss = total / max(cells, 1)
    return (
        model,
        residual_scale,
        {
            "epochs": config.residual_epochs,
            "last_epoch_noise_loss": last_loss,
            "residual_scale": residual_scale,
            "train_transition_residual_energy": float(np.mean(np.square(residual))),
        },
    )


def _sample_diffusion_residual(
    model: _ResidualDenoiser,
    *,
    latent: NDArray[np.float64] | NDArray[np.int64],
    base_next: NDArray[np.float64] | NDArray[np.int64],
    residual_scale: float,
    config: Round2Config,
) -> NDArray[np.float64]:
    latent_array = cast(NDArray[np.float64], latent).astype(np.float32)
    base_array = cast(NDArray[np.float64], base_next).astype(np.float32)
    outputs: list[NDArray[np.float64]] = []
    _, alpha_bar = _diffusion_schedule(config.diffusion_steps)
    model.eval()
    with torch.no_grad():
        for start in range(0, latent_array.shape[0], config.batch_size):
            stop = min(start + config.batch_size, latent_array.shape[0])
            condition = torch.from_numpy(np.concatenate([latent_array[start:stop], base_array[start:stop]], axis=1))
            noisy = torch.zeros((stop - start, config.latent_dim), dtype=torch.float32)
            for step in range(config.diffusion_steps - 1, -1, -1):
                steps = torch.full((stop - start,), step, dtype=torch.long)
                predicted_noise = model(noisy, condition, steps)
                selected_alpha = alpha_bar[step]
                predicted_clean = (noisy - torch.sqrt(1.0 - selected_alpha) * predicted_noise) / torch.sqrt(selected_alpha)
                if step == 0:
                    noisy = predicted_clean
                else:
                    previous_alpha = alpha_bar[step - 1]
                    noisy = torch.sqrt(previous_alpha) * predicted_clean + torch.sqrt(1.0 - previous_alpha) * predicted_noise
            outputs.append(noisy.cpu().numpy().astype(np.float64) * residual_scale)
    return np.concatenate(outputs)


def _diffusion_schedule(steps: int) -> tuple[Tensor, Tensor]:
    beta = torch.linspace(1e-4, 0.02, steps=steps, dtype=torch.float32)
    alpha = 1.0 - beta
    return beta, torch.cumprod(alpha, dim=0)


def _fit_ridge(design: NDArray[np.float64], target: NDArray[np.float64], penalty: float) -> NDArray[np.float64]:
    augmented = np.column_stack([np.ones(design.shape[0], dtype=np.float64), design])
    regularizer = np.eye(augmented.shape[1], dtype=np.float64) * penalty
    regularizer[0, 0] = 0.0
    return np.linalg.solve(augmented.T @ augmented + regularizer, augmented.T @ target)


def _predict_ridge(design: NDArray[np.float64], coefficients: NDArray[np.float64]) -> NDArray[np.float64]:
    augmented = np.column_stack([np.ones(design.shape[0], dtype=np.float64), design])
    return (augmented @ coefficients).astype(np.float64)


def _select_low_redundancy(
    raw_score: pd.Series,
    history: pd.DataFrame,
    *,
    mechanism_family_by_factor: Mapping[str, str],
    config: Round2Config,
) -> pd.Series:
    score = raw_score.replace([np.inf, -np.inf], np.nan).dropna()
    score = score[score > 0.0].sort_values(ascending=False, kind="stable")
    if score.empty:
        return pd.Series(dtype=float)
    candidate_count = max(config.allocator_max_active_factors * 4, config.allocator_min_active_factors)
    candidates = list(score.index[:candidate_count])
    correlation = history[candidates].corr(min_periods=config.allocator_min_periods)
    selected: list[str] = []
    for factor_id in candidates:
        if len(selected) >= config.allocator_max_active_factors:
            break
        if not selected:
            selected.append(str(factor_id))
            continue
        peer = correlation.loc[factor_id, selected].abs().max()
        if pd.isna(peer) or float(peer) < config.allocator_corr_threshold:
            selected.append(str(factor_id))
    if len(selected) < config.allocator_min_active_factors:
        for factor_id in candidates:
            if str(factor_id) not in selected:
                selected.append(str(factor_id))
            if len(selected) >= config.allocator_min_active_factors:
                break
    return _apply_caps(
        score.loc[selected],
        mechanism_family_by_factor=mechanism_family_by_factor,
        config=config,
    )


def _apply_caps(
    raw: pd.Series,
    *,
    mechanism_family_by_factor: Mapping[str, str],
    config: Round2Config,
) -> pd.Series:
    weights = raw.clip(lower=0.0).astype(float)
    if float(weights.sum()) <= 0.0:
        return weights
    weights /= float(weights.sum())
    for _ in range(12):
        weights = weights.clip(upper=config.allocator_factor_cap)
        families = sorted({mechanism_family_by_factor.get(str(fid), "unknown") for fid in weights.index})
        for family in families:
            members = [fid for fid in weights.index if mechanism_family_by_factor.get(str(fid), "unknown") == family]
            family_total = float(weights.loc[members].sum())
            if family_total > config.allocator_family_cap:
                weights.loc[members] *= config.allocator_family_cap / family_total
        total = float(weights.sum())
        if total <= 0.0:
            break
        weights /= total
    return weights


def _operator_occupancy(operator_ids: NDArray[np.int64], count: int) -> dict[str, float]:
    if operator_ids.size == 0:
        return {str(index): 0.0 for index in range(count)}
    return {str(index): float(np.mean(operator_ids == index)) for index in range(count)}


def _energy_ratio(correction: NDArray[np.float64], base: NDArray[np.float64] | NDArray[np.int64]) -> float:
    denominator = float(np.mean(np.square(cast(NDArray[np.float64], base))))
    return float(np.mean(np.square(correction)) / max(denominator, 1e-12))


def _equal_weight_turnover(previous: set[str], current: set[str]) -> float:
    if not current:
        return 0.0
    if not previous:
        return 1.0
    previous_weight = 1.0 / len(previous)
    current_weight = 1.0 / len(current)
    retained = len(previous & current) * min(previous_weight, current_weight)
    return float(max(0.0, 1.0 - retained))


def _annualized_return(returns: NDArray[np.float64]) -> float:
    if returns.size == 0:
        return 0.0
    gross = float(np.prod(1.0 + np.clip(returns, -0.999999, None)))
    if gross <= 0.0:
        return -1.0
    return gross ** (12.0 / returns.size) - 1.0


def _annualized_sharpe(returns: NDArray[np.float64]) -> float:
    if returns.size < 2:
        return 0.0
    scale = float(np.std(returns, ddof=1))
    return float(np.mean(returns) / scale * math.sqrt(12.0)) if scale > 0.0 else 0.0


def _maximum_drawdown(returns: NDArray[np.float64]) -> float:
    if returns.size == 0:
        return 0.0
    nav = np.cumprod(1.0 + np.clip(returns, -0.999999, None))
    return float(np.min(nav / np.maximum.accumulate(nav) - 1.0))


def _benjamini_hochberg(p_values: NDArray[np.float64]) -> NDArray[np.float64]:
    count = p_values.size
    order = np.argsort(p_values, kind="stable")
    ranked = p_values[order]
    adjusted = ranked * count / np.arange(1, count + 1, dtype=np.float64)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result = np.empty(count, dtype=np.float64)
    result[order] = np.clip(adjusted, 0.0, 1.0)
    return result


def _moving_block_bootstrap_mean_ci(
    values: NDArray[np.float64],
    *,
    block_size: int,
    replicates: int,
    seed: int,
) -> list[float]:
    if values.size == 0:
        return [0.0, 0.0]
    block_size = min(max(1, block_size), values.size)
    starts = np.arange(values.size - block_size + 1)
    blocks_needed = int(math.ceil(values.size / block_size))
    rng = np.random.default_rng(seed)
    means = np.empty(replicates, dtype=np.float64)
    for replicate in range(replicates):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate([values[start : start + block_size] for start in selected])[: values.size]
        means[replicate] = float(sample.mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
