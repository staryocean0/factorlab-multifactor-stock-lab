# pyright: reportAny=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportGeneralTypeIssues=false, reportCallIssue=false
# pyright: reportAttributeAccessIssue=false, reportMissingTypeStubs=false
# pyright: reportIndexIssue=false
"""Formula-faithful REAKA architecture and the FactorLab research adapter.

This module deliberately does not mutate the earlier
``reaka_adaptive_koopman_v1`` proxy.  The proxy used a single feature LSTM, a
separately fitted residual model, a zero-start reverse path, and a ridge
ranking head.  Those choices are useful historical evidence but are not the
architecture described by Liao et al. (2026).

The neural dataflow below follows equations (1)--(31): two overlapping return
and feature windows, two LSTMs, a feature-controlled gate, per-time-step
adaptive Koopman selection, a conditional DDPM residual, a return decoder,
and one end-to-end objective ``L_rec + L_koop + L_diff``.  The paper omits
several implementation details.  Every such choice is exposed by
``ReakaPaperConfig`` and labelled ``paper_unspecified_assumption`` in the
replication contract; none is presented as an author-supplied hyperparameter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn
from torch.nn import functional as F

from factor_lab.factor_rotation.macro_regime_dual_strategy_round2 import (
    Round2Panel,
)
from factor_lab.governance.canonicalization import canonical_digest
from factor_lab.governance.reaka_foundation_contract import require_research_action

REAKA_PAPER_STRATEGY_ID: Final = "reaka_paper_formula_faithful_v1"
REAKA_PAPER_CONTRACT_SCHEMA_ID: Final = "reaka_paper_replication_contract@1.0"
REAKA_PAPER_SOURCE_REF: Final = (
    "research_materials/10_regime_dynamics_investment_frameworks/liao_residual_enhanced_adaptive_koopman_stock_prediction_2026.pdf"
)

REAKA_PAPER_FULL_ARM_ID: Final = "reaka"
REAKA_PAPER_WITHOUT_AKS_ARM_ID: Final = "without_aks"
REAKA_PAPER_WITHOUT_DRC_ARM_ID: Final = "without_drc"
REAKA_PAPER_WITHOUT_GATE_ARM_ID: Final = "without_gate"
REAKA_PAPER_VANILLA_AE_ARM_ID: Final = "vanilla_autoencoder"
REAKA_PAPER_RESIDUAL_MLP_ARM_ID: Final = "residual_mlp"
REAKA_PAPER_ARM_IDS: Final[tuple[str, ...]] = (
    REAKA_PAPER_FULL_ARM_ID,
    REAKA_PAPER_WITHOUT_AKS_ARM_ID,
    REAKA_PAPER_WITHOUT_DRC_ARM_ID,
    REAKA_PAPER_WITHOUT_GATE_ARM_ID,
    REAKA_PAPER_VANILLA_AE_ARM_ID,
    REAKA_PAPER_RESIDUAL_MLP_ARM_ID,
)
ReakaPaperResidualMode = Literal["diffusion", "none", "mlp"]


@dataclass(frozen=True, slots=True)
class ReakaPaperAblation:
    """One same-graph arm from the paper's Table 2 comparison."""

    arm_id: str
    feature_gate: bool
    adaptive_koopman_selector: bool
    koopman_transition: bool
    residual_mode: ReakaPaperResidualMode

    def validate(self) -> None:
        if self.arm_id not in REAKA_PAPER_ARM_IDS:
            raise ValueError("reaka_paper_ablation_arm_unknown")
        if self.residual_mode not in {"diffusion", "none", "mlp"}:
            raise ValueError("reaka_paper_ablation_residual_mode_unknown")
        if not self.koopman_transition and self.residual_mode != "none":
            raise ValueError("reaka_paper_autoencoder_cannot_enable_residual")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "arm_id": self.arm_id,
            "feature_gate": self.feature_gate,
            "adaptive_koopman_selector": self.adaptive_koopman_selector,
            "koopman_transition": self.koopman_transition,
            "residual_mode": self.residual_mode,
        }


def reaka_paper_ablation(arm_id: str) -> ReakaPaperAblation:
    """Return a frozen, auditable interpretation of one paper ablation."""

    arms = {
        REAKA_PAPER_FULL_ARM_ID: ReakaPaperAblation(
            arm_id=REAKA_PAPER_FULL_ARM_ID,
            feature_gate=True,
            adaptive_koopman_selector=True,
            koopman_transition=True,
            residual_mode="diffusion",
        ),
        REAKA_PAPER_WITHOUT_AKS_ARM_ID: ReakaPaperAblation(
            arm_id=REAKA_PAPER_WITHOUT_AKS_ARM_ID,
            feature_gate=True,
            adaptive_koopman_selector=False,
            koopman_transition=True,
            residual_mode="diffusion",
        ),
        REAKA_PAPER_WITHOUT_DRC_ARM_ID: ReakaPaperAblation(
            arm_id=REAKA_PAPER_WITHOUT_DRC_ARM_ID,
            feature_gate=True,
            adaptive_koopman_selector=True,
            koopman_transition=True,
            residual_mode="none",
        ),
        REAKA_PAPER_WITHOUT_GATE_ARM_ID: ReakaPaperAblation(
            arm_id=REAKA_PAPER_WITHOUT_GATE_ARM_ID,
            feature_gate=False,
            adaptive_koopman_selector=True,
            koopman_transition=True,
            residual_mode="diffusion",
        ),
        REAKA_PAPER_VANILLA_AE_ARM_ID: ReakaPaperAblation(
            arm_id=REAKA_PAPER_VANILLA_AE_ARM_ID,
            feature_gate=True,
            adaptive_koopman_selector=False,
            koopman_transition=False,
            residual_mode="none",
        ),
        REAKA_PAPER_RESIDUAL_MLP_ARM_ID: ReakaPaperAblation(
            arm_id=REAKA_PAPER_RESIDUAL_MLP_ARM_ID,
            feature_gate=True,
            adaptive_koopman_selector=True,
            koopman_transition=True,
            residual_mode="mlp",
        ),
    }
    try:
        selected = arms[arm_id]
    except KeyError as exc:
        raise ValueError("reaka_paper_ablation_arm_unknown") from exc
    selected.validate()
    return selected


@dataclass(frozen=True, slots=True)
class ReakaPaperConfig:
    """Historical implementation values, never future parameter authority.

    New training must bind the parameter catalog and its scope gate.  These
    constructor values preserve old artifacts and tests; they are not evidence
    that the paper specified the hyperparameters or that a successor may reuse
    them silently.
    """

    window_length: int = 10
    latent_dim: int = 16
    network_hidden_dim: int = 32
    operator_count: int = 4
    training_epochs: int = 3
    diffusion_steps: int = 6
    batch_size: int = 4096
    learning_rate: float = 1e-3
    gumbel_temperature: float = 0.75
    beta_start: float = 1e-4
    beta_end: float = 2e-2
    time_embedding_dim: int = 8
    denoiser_hidden_dim: int = 64
    denoiser_depth: int = 2
    gradient_clip_norm: float = 5.0
    inference_draws: int = 1
    torch_num_threads: int = 16

    def validate(self) -> None:
        if self.window_length < 2:
            raise ValueError("reaka_paper_window_length_must_be_at_least_two")
        integer_fields = {
            "latent_dim": self.latent_dim,
            "network_hidden_dim": self.network_hidden_dim,
            "operator_count": self.operator_count,
            "training_epochs": self.training_epochs,
            "diffusion_steps": self.diffusion_steps,
            "batch_size": self.batch_size,
            "time_embedding_dim": self.time_embedding_dim,
            "denoiser_hidden_dim": self.denoiser_hidden_dim,
            "denoiser_depth": self.denoiser_depth,
            "inference_draws": self.inference_draws,
            "torch_num_threads": self.torch_num_threads,
        }
        for name, value in integer_fields.items():
            if value < 1:
                raise ValueError(f"reaka_paper_{name}_must_be_positive")
        if self.operator_count < 2:
            raise ValueError("reaka_paper_operator_count_must_be_at_least_two")
        if self.learning_rate <= 0.0:
            raise ValueError("reaka_paper_learning_rate_must_be_positive")
        if self.gumbel_temperature <= 0.0:
            raise ValueError("reaka_paper_gumbel_temperature_must_be_positive")
        if not 0.0 < self.beta_start < self.beta_end < 1.0:
            raise ValueError("reaka_paper_beta_schedule_invalid")
        if self.gradient_clip_norm <= 0.0:
            raise ValueError("reaka_paper_gradient_clip_norm_must_be_positive")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "window_length": self.window_length,
            "latent_dim": self.latent_dim,
            "network_hidden_dim": self.network_hidden_dim,
            "operator_count": self.operator_count,
            "training_epochs": self.training_epochs,
            "diffusion_steps": self.diffusion_steps,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "gumbel_temperature": self.gumbel_temperature,
            "beta_start": self.beta_start,
            "beta_end": self.beta_end,
            "time_embedding_dim": self.time_embedding_dim,
            "denoiser_hidden_dim": self.denoiser_hidden_dim,
            "denoiser_depth": self.denoiser_depth,
            "gradient_clip_norm": self.gradient_clip_norm,
            "inference_draws": self.inference_draws,
            "torch_num_threads": self.torch_num_threads,
        }


@dataclass(frozen=True, slots=True)
class FactorLabReakaAdapterConfig:
    """Honest adapter for the existing monthly Round-3A evidence surface.

    The paper consumes daily contemporaneous returns and Alpha158.  Round 3A
    instead stores monthly stock factors and forward 20-session outcomes.  A
    two-period lag is therefore required before those outcomes become usable
    as historical-return inputs.  The adapter rejects incomplete windows and
    never fills a missing return with zero.
    """

    history_lag_periods: int = 2
    minimum_train_windows: int = 512
    minimum_test_windows: int = 128

    def validate(self) -> None:
        if self.history_lag_periods < 1:
            raise ValueError("reaka_adapter_history_lag_must_be_positive")
        if self.minimum_train_windows < 1 or self.minimum_test_windows < 1:
            raise ValueError("reaka_adapter_minimum_window_count_must_be_positive")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "history_lag_periods": self.history_lag_periods,
            "minimum_train_windows": self.minimum_train_windows,
            "minimum_test_windows": self.minimum_test_windows,
        }


@dataclass(frozen=True, slots=True)
class ReakaPaperWindows:
    """One causal collection of full ``1:T`` return/feature windows."""

    sample_indices: NDArray[np.int64]
    month_indices: NDArray[np.int64]
    symbol_indices: NDArray[np.int64]
    returns: NDArray[np.float32]
    features: NDArray[np.float32]

    def __len__(self) -> int:
        return int(self.sample_indices.size)


@dataclass(frozen=True, slots=True)
class ReakaPaperTrainingOutput:
    """Named tensors needed by tests, diagnostics, and joint optimization."""

    total_loss: Tensor
    reconstruction_loss: Tensor
    koopman_loss: Tensor
    diffusion_loss: Tensor
    historical_prediction: Tensor
    shifted_prediction: Tensor
    latent: Tensor
    next_latent: Tensor
    advanced_latent: Tensor
    corrected_latent: Tensor
    true_residual: Tensor
    estimated_residual: Tensor
    selector_weights: Tensor
    gate: Tensor


@dataclass(frozen=True, slots=True)
class ReakaPaperForecast:
    """One inference draw or the mean of explicitly requested draws."""

    scores: Tensor
    predicted_sequence: Tensor
    operator_ids: Tensor
    selector_weights: Tensor
    gate: Tensor
    residual: Tensor
    initial_noise: Tensor


@dataclass(frozen=True, slots=True)
class ReakaPaperFitResult:
    """Fold/seed fit result for the formula-faithful challenger."""

    sample_indices: NDArray[np.int64]
    scores: NDArray[np.float64]
    operator_ids: NDArray[np.int64]
    operator_matrices: NDArray[np.float64]
    diagnostics: dict[str, object]


def build_reaka_paper_replication_contract(
    *,
    config: ReakaPaperConfig | None = None,
    input_profile: str = "paper_benchmark_alpha158_daily",
) -> dict[str, object]:
    """Return the frozen exact/adapted/unspecified conformance contract."""

    frozen = config or ReakaPaperConfig()
    frozen.validate()
    if input_profile not in {
        "paper_benchmark_alpha158_daily",
        "factorlab_round3a_monthly_adapter",
    }:
        raise ValueError("reaka_paper_input_profile_unknown")
    exact_modules = [
        "equations_1_2_overlapping_windows",
        "equations_3_6_independent_return_and_feature_lstms_with_shared_window_weights",
        "equations_7_10_feature_only_sigmoid_gate_and_elementwise_fusion",
        "equations_11_15_selector_on_concatenated_Z_and_Hy_with_train_gumbel_softmax",
        "equations_16_21_conditional_ddpm_residual_given_Z_and_gaussian_reverse_start",
        "equations_22_27_return_sequence_decoder_and_last_element_forecast",
        "equations_28_31_equal_sum_reconstruction_koopman_and_diffusion_loss",
        "inference_argmax_operator_index_then_codebook_lookup",
    ]
    assumptions = {
        "latent_and_network_dimensions": "paper_unspecified_assumption",
        "operator_count": "paper_unspecified_assumption",
        "optimizer_learning_rate_batch_epochs_and_gradient_clip": ("paper_unspecified_assumption"),
        "gumbel_temperature_fixed_without_annealing_or_straight_through": ("paper_unspecified_assumption"),
        "linear_beta_schedule_and_diffusion_step_count": ("paper_unspecified_assumption"),
        "per_time_step_selector": ("paper_text_supported_tensor_shape_assumption"),
        "training_corrected_latent_uses_one_step_x0_estimate": ("paper_unspecified_assumption"),
        "residual_target_remains_attached_for_joint_training": ("paper_unspecified_assumption"),
        "x0_to_residual_is_identity": "paper_unspecified_assumption",
        "reverse_final_step_has_zero_variance": "standard_ddpm_assumption",
        "single_seeded_inference_draw": "paper_unspecified_assumption",
    }
    payload: dict[str, object] = {
        "schema_id": REAKA_PAPER_CONTRACT_SCHEMA_ID,
        "strategy_id": REAKA_PAPER_STRATEGY_ID,
        "source_ref": REAKA_PAPER_SOURCE_REF,
        "source_scope": "full_five_page_icassp_2026_paper",
        "input_profile": input_profile,
        "paper_exact_architecture_modules": exact_modules,
        "paper_unspecified_assumptions": assumptions,
        "config": frozen.as_dict(),
        "input_conformance": {
            "paper_benchmark_alpha158_daily": input_profile == "paper_benchmark_alpha158_daily",
            "alpha158_feature_count": 158 if input_profile == "paper_benchmark_alpha158_daily" else None,
            "ten_trading_day_window": input_profile == "paper_benchmark_alpha158_daily",
            "factorlab_monthly_adapter": input_profile == "factorlab_round3a_monthly_adapter",
        },
        "scientific_boundaries": {
            "bit_exact_author_replication_claimed": False,
            "paper_reported_metric_replication_claimed": False,
            "consumed_2021_2025_can_create_fresh_oos_claim": False,
            "formal_replacement_allowed": False,
            "production_authority": False,
        },
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


class _ConditionalResidualDenoiser(nn.Module):
    def __init__(self, *, config: ReakaPaperConfig) -> None:
        super().__init__()
        self.time_embedding = nn.Embedding(
            config.diffusion_steps,
            config.time_embedding_dim,
        )
        layers: list[nn.Module] = [
            nn.Linear(
                config.latent_dim * 2 + config.time_embedding_dim,
                config.denoiser_hidden_dim,
            ),
            nn.SiLU(),
        ]
        for _ in range(config.denoiser_depth - 1):
            layers.extend(
                (
                    nn.Linear(
                        config.denoiser_hidden_dim,
                        config.denoiser_hidden_dim,
                    ),
                    nn.SiLU(),
                )
            )
        layers.append(nn.Linear(config.denoiser_hidden_dim, config.latent_dim))
        self.network = nn.Sequential(*layers)

    def forward(self, noisy: Tensor, steps: Tensor, condition: Tensor) -> Tensor:
        if noisy.shape != condition.shape or noisy.ndim != 3:
            raise ValueError("reaka_paper_denoiser_tensor_shape_mismatch")
        batch, sequence, _ = noisy.shape
        time = self.time_embedding(steps).unsqueeze(1).expand(-1, sequence, -1)
        joined = torch.cat((noisy, condition, time), dim=-1)
        return self.network(joined.reshape(batch * sequence, -1)).reshape_as(noisy)


class ReakaPaperModel(nn.Module):
    """Equations (1)--(31) with no proxy ranking head or post-fit residual."""

    def __init__(
        self,
        *,
        feature_dim: int,
        config: ReakaPaperConfig,
        ablation: ReakaPaperAblation | None = None,
    ) -> None:
        super().__init__()
        config.validate()
        if feature_dim < 1:
            raise ValueError("reaka_paper_feature_dim_must_be_positive")
        self.feature_dim = feature_dim
        self.config = config
        self.ablation = ablation or reaka_paper_ablation(REAKA_PAPER_FULL_ARM_ID)
        self.ablation.validate()
        self.return_encoder = nn.LSTM(
            input_size=1,
            hidden_size=config.latent_dim,
            batch_first=True,
        )
        self.feature_encoder = nn.LSTM(
            input_size=feature_dim,
            hidden_size=config.latent_dim,
            batch_first=True,
        )
        self.gate_net = nn.Sequential(
            nn.Linear(config.latent_dim, config.network_hidden_dim),
            nn.SiLU(),
            nn.Linear(config.network_hidden_dim, config.latent_dim),
            nn.Sigmoid(),
        )
        self.selector = nn.Linear(config.latent_dim * 2, config.operator_count)
        effective_operator_count = (
            config.operator_count
            if self.ablation.adaptive_koopman_selector
            else 1
        )
        identity = torch.eye(config.latent_dim).repeat(
            effective_operator_count,
            1,
            1,
        )
        self.operators = nn.Parameter(identity + 0.01 * torch.randn_like(identity))
        self.residual_denoiser = _ConditionalResidualDenoiser(config=config)
        self.residual_mlp = (
            nn.Sequential(
                nn.Linear(config.latent_dim, config.denoiser_hidden_dim),
                nn.SiLU(),
                nn.Linear(config.denoiser_hidden_dim, config.latent_dim),
            )
            if self.ablation.residual_mode == "mlp"
            else None
        )
        self.decoder = nn.Sequential(
            nn.Linear(config.latent_dim, config.network_hidden_dim),
            nn.SiLU(),
            nn.Linear(config.network_hidden_dim, 1),
        )
        beta, alpha, alpha_bar = _diffusion_schedule(config)
        self.register_buffer("diffusion_beta", beta)
        self.register_buffer("diffusion_alpha", alpha)
        self.register_buffer("diffusion_alpha_bar", alpha_bar)

    def _encode_and_gate(
        self,
        returns: Tensor,
        features: Tensor,
    ) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        _validate_model_inputs(
            returns,
            features,
            feature_dim=self.feature_dim,
        )
        return_hidden = self.return_encoder(returns.unsqueeze(-1))[0]
        if self.ablation.feature_gate:
            feature_hidden = self.feature_encoder(features)[0]
            gate = self.gate_net(feature_hidden)
            latent = return_hidden * gate + feature_hidden * (1.0 - gate)
        else:
            feature_hidden = torch.zeros_like(return_hidden)
            gate = torch.ones_like(return_hidden)
            latent = return_hidden
        return latent, return_hidden, feature_hidden, gate

    def _transition(
        self,
        latent: Tensor,
        return_hidden: Tensor,
        *,
        training_gumbel: bool,
    ) -> tuple[Tensor, Tensor, Tensor]:
        if not self.ablation.koopman_transition:
            weights = torch.ones(
                (*latent.shape[:-1], 1),
                dtype=latent.dtype,
                device=latent.device,
            )
            return latent, weights, torch.zeros_like(weights[..., 0], dtype=torch.long)
        if self.ablation.adaptive_koopman_selector:
            logits = F.leaky_relu(
                self.selector(torch.cat((latent, return_hidden), dim=-1)),
                negative_slope=0.01,
            )
            if training_gumbel:
                weights = F.gumbel_softmax(
                    logits,
                    tau=self.config.gumbel_temperature,
                    hard=False,
                    dim=-1,
                )
            else:
                operator_ids = torch.argmax(logits, dim=-1)
                weights = F.one_hot(
                    operator_ids,
                    num_classes=self.config.operator_count,
                ).to(latent.dtype)
        else:
            weights = torch.ones(
                (*latent.shape[:-1], 1),
                dtype=latent.dtype,
                device=latent.device,
            )
        transformed = torch.einsum("kij,btj->btki", self.operators, latent)
        advanced = torch.einsum("btk,btki->bti", weights, transformed)
        return advanced, weights, torch.argmax(weights, dim=-1)

    def training_objective(
        self,
        returns: Tensor,
        features: Tensor,
        *,
        diffusion_steps: Tensor | None = None,
        diffusion_noise: Tensor | None = None,
    ) -> ReakaPaperTrainingOutput:
        """Apply both offset windows and the equal-weight joint paper loss."""

        _validate_model_inputs(
            returns,
            features,
            feature_dim=self.feature_dim,
            minimum_sequence=2,
        )
        historical_returns = returns[:, :-1]
        shifted_returns = returns[:, 1:]
        historical_features = features[:, :-1]
        shifted_features = features[:, 1:]
        latent, return_hidden, _, gate = self._encode_and_gate(
            historical_returns,
            historical_features,
        )
        next_latent, _, _, _ = self._encode_and_gate(
            shifted_returns,
            shifted_features,
        )
        advanced, selector_weights, _ = self._transition(
            latent,
            return_hidden,
            training_gumbel=True,
        )
        true_residual = next_latent - advanced
        batch = returns.shape[0]
        if self.ablation.residual_mode == "diffusion":
            if diffusion_steps is None:
                diffusion_steps = torch.randint(
                    0,
                    self.config.diffusion_steps,
                    (batch,),
                    device=returns.device,
                )
            if diffusion_steps.shape != (batch,):
                raise ValueError("reaka_paper_diffusion_step_shape_mismatch")
            if diffusion_noise is None:
                diffusion_noise = torch.randn_like(true_residual)
            if diffusion_noise.shape != true_residual.shape:
                raise ValueError("reaka_paper_diffusion_noise_shape_mismatch")
            selected_bar = self.diffusion_alpha_bar[diffusion_steps].view(
                batch,
                1,
                1,
            )
            noisy_residual = torch.sqrt(selected_bar) * true_residual + torch.sqrt(1.0 - selected_bar) * diffusion_noise
            predicted_noise = self.residual_denoiser(
                noisy_residual,
                diffusion_steps,
                latent,
            )
            estimated_residual = (noisy_residual - torch.sqrt(1.0 - selected_bar) * predicted_noise) / torch.sqrt(selected_bar)
            diffusion_loss = F.mse_loss(predicted_noise, diffusion_noise)
        elif self.ablation.residual_mode == "mlp":
            if self.residual_mlp is None:
                raise AssertionError("reaka_paper_residual_mlp_missing")
            estimated_residual = self.residual_mlp(latent)
            diffusion_loss = F.mse_loss(estimated_residual, true_residual)
        else:
            estimated_residual = torch.zeros_like(true_residual)
            diffusion_loss = torch.zeros((), dtype=returns.dtype, device=returns.device)
        corrected = advanced + estimated_residual
        historical_prediction = self.decoder(latent).squeeze(-1)
        shifted_prediction = self.decoder(
            next_latent if not self.ablation.koopman_transition else corrected
        ).squeeze(-1)
        reconstruction_loss = F.mse_loss(
            historical_prediction,
            historical_returns,
        ) + F.mse_loss(shifted_prediction, shifted_returns)
        koopman_loss = (
            F.mse_loss(advanced, next_latent)
            if self.ablation.koopman_transition
            else torch.zeros((), dtype=returns.dtype, device=returns.device)
        )
        total = reconstruction_loss + koopman_loss + diffusion_loss
        return ReakaPaperTrainingOutput(
            total_loss=total,
            reconstruction_loss=reconstruction_loss,
            koopman_loss=koopman_loss,
            diffusion_loss=diffusion_loss,
            historical_prediction=historical_prediction,
            shifted_prediction=shifted_prediction,
            latent=latent,
            next_latent=next_latent,
            advanced_latent=advanced,
            corrected_latent=corrected,
            true_residual=true_residual,
            estimated_residual=estimated_residual,
            selector_weights=selector_weights,
            gate=gate,
        )

    def forecast(
        self,
        returns: Tensor,
        features: Tensor,
        *,
        generator: torch.Generator | None = None,
        initial_noise: Tensor | None = None,
        reverse_noises: tuple[Tensor, ...] | None = None,
    ) -> ReakaPaperForecast:
        """Execute equations (24)--(27), including Gaussian DDPM sampling."""

        latent, return_hidden, _, gate = self._encode_and_gate(returns, features)
        advanced, weights, operator_ids = self._transition(
            latent,
            return_hidden,
            training_gumbel=False,
        )
        if self.ablation.residual_mode != "diffusion":
            if initial_noise is not None or reverse_noises is not None:
                raise ValueError("reaka_paper_non_diffusion_noise_forbidden")
            initial_noise = torch.zeros_like(advanced)
            if self.ablation.residual_mode == "mlp":
                if self.residual_mlp is None:
                    raise AssertionError("reaka_paper_residual_mlp_missing")
                residual = self.residual_mlp(latent)
            else:
                residual = torch.zeros_like(advanced)
            corrected = advanced + residual
            predicted_sequence = self.decoder(corrected).squeeze(-1)
            return ReakaPaperForecast(
                scores=predicted_sequence[:, -1],
                predicted_sequence=predicted_sequence,
                operator_ids=operator_ids,
                selector_weights=weights,
                gate=gate,
                residual=residual,
                initial_noise=initial_noise,
            )
        if initial_noise is None:
            initial_noise = torch.randn(
                advanced.shape,
                dtype=advanced.dtype,
                device=advanced.device,
                generator=generator,
            )
        if initial_noise.shape != advanced.shape:
            raise ValueError("reaka_paper_initial_noise_shape_mismatch")
        if reverse_noises is not None and len(reverse_noises) != self.config.diffusion_steps:
            raise ValueError("reaka_paper_reverse_noise_count_mismatch")
        residual = initial_noise.clone()
        batch = returns.shape[0]
        for step in range(self.config.diffusion_steps - 1, -1, -1):
            step_tensor = torch.full(
                (batch,),
                step,
                dtype=torch.long,
                device=returns.device,
            )
            predicted_noise = self.residual_denoiser(
                residual,
                step_tensor,
                latent,
            )
            alpha = self.diffusion_alpha[step]
            alpha_bar = self.diffusion_alpha_bar[step]
            mean = (residual - (1.0 - alpha) / torch.sqrt(1.0 - alpha_bar) * predicted_noise) / torch.sqrt(alpha)
            if step == 0:
                residual = mean
                continue
            previous_alpha_bar = self.diffusion_alpha_bar[step - 1]
            variance = (1.0 - previous_alpha_bar) / (1.0 - alpha_bar) * self.diffusion_beta[step]
            if reverse_noises is None:
                innovation = torch.randn(
                    residual.shape,
                    dtype=residual.dtype,
                    device=residual.device,
                    generator=generator,
                )
            else:
                innovation = reverse_noises[step]
                if innovation.shape != residual.shape:
                    raise ValueError("reaka_paper_reverse_noise_shape_mismatch")
            residual = mean + torch.sqrt(variance) * innovation
        corrected = advanced + residual
        predicted_sequence = self.decoder(corrected).squeeze(-1)
        return ReakaPaperForecast(
            scores=predicted_sequence[:, -1],
            predicted_sequence=predicted_sequence,
            operator_ids=operator_ids,
            selector_weights=weights,
            gate=gate,
            residual=residual,
            initial_noise=initial_noise,
        )


def build_factorlab_reaka_windows(
    panel: Round2Panel,
    sample_indices: NDArray[np.int64],
    *,
    model_config: ReakaPaperConfig,
    adapter_config: FactorLabReakaAdapterConfig | None = None,
) -> ReakaPaperWindows:
    """Map current monthly evidence to causal windows without pseudo returns."""

    adapter = adapter_config or FactorLabReakaAdapterConfig()
    adapter.validate()
    model_config.validate()
    sample_indices = np.asarray(sample_indices, dtype=np.int64)
    months = panel.sample_month_indices[sample_indices]
    symbols = panel.sample_symbol_indices[sample_indices]
    first_offset = -(adapter.history_lag_periods + model_config.window_length - 1)
    last_offset = -adapter.history_lag_periods
    offsets = np.arange(first_offset, last_offset + 1, dtype=np.int64)
    if offsets.size != model_config.window_length:
        raise AssertionError("reaka_adapter_internal_window_length_mismatch")
    historical_months = months[:, None] + offsets[None, :]
    in_bounds = historical_months[:, 0] >= 0
    bounded_rows = np.flatnonzero(in_bounds)
    if bounded_rows.size == 0:
        return _empty_windows(panel, model_config=model_config)
    bounded_months = historical_months[bounded_rows]
    bounded_symbols = symbols[bounded_rows]
    symbol_grid = np.broadcast_to(bounded_symbols[:, None], bounded_months.shape)
    historical_returns = panel.targets[bounded_months, symbol_grid]
    historical_tradeable = panel.tradeable[bounded_months, symbol_grid]
    historical_available = panel.target_available_at[bounded_months, symbol_grid]
    decisions = panel.month_dates[months[bounded_rows]][:, None]
    valid = np.isfinite(historical_returns).all(axis=1) & historical_tradeable.all(axis=1) & (historical_available < decisions).all(axis=1)
    kept_local = bounded_rows[valid]
    kept_months = historical_months[kept_local]
    kept_symbols = symbols[kept_local]
    if kept_local.size == 0:
        return _empty_windows(panel, model_config=model_config)
    kept_symbol_grid = np.broadcast_to(
        kept_symbols[:, None],
        kept_months.shape,
    )
    returns = panel.targets[kept_months, kept_symbol_grid].astype(
        np.float32,
        copy=False,
    )
    features = panel.features[kept_months, kept_symbol_grid, :].astype(
        np.float32,
        copy=False,
    )
    if not np.isfinite(features).all():
        raise ValueError("reaka_adapter_feature_window_must_be_finite")
    return ReakaPaperWindows(
        sample_indices=sample_indices[kept_local],
        month_indices=kept_months,
        symbol_indices=kept_symbols,
        returns=returns,
        features=features,
    )


def fit_reaka_paper_challenger(
    *,
    panel: Round2Panel,
    train_indices: NDArray[np.int64],
    test_indices: NDArray[np.int64],
    config: ReakaPaperConfig | None = None,
    adapter_config: FactorLabReakaAdapterConfig | None = None,
    seed: int,
) -> ReakaPaperFitResult:
    """Fit one end-to-end paper architecture on a frozen FactorLab fold."""
    require_research_action(Path(__file__).resolve().parents[3], "train")

    frozen = config or ReakaPaperConfig()
    adapter = adapter_config or FactorLabReakaAdapterConfig()
    frozen.validate()
    adapter.validate()
    _seed_everything(seed)
    torch.set_num_threads(frozen.torch_num_threads)
    train_windows = build_factorlab_reaka_windows(
        panel,
        train_indices,
        model_config=frozen,
        adapter_config=adapter,
    )
    if len(train_windows) < adapter.minimum_train_windows:
        raise ValueError("reaka_paper_train_window_count_insufficient")
    return_mean = float(train_windows.returns.mean(dtype=np.float64))
    return_scale = float(train_windows.returns.std(dtype=np.float64))
    if not np.isfinite(return_scale) or return_scale < 1e-8:
        raise ValueError("reaka_paper_train_return_scale_invalid")
    normalized_train_returns = ((train_windows.returns - return_mean) / return_scale).astype(np.float32)
    model = ReakaPaperModel(
        feature_dim=len(panel.factor_ids),
        config=frozen,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=frozen.learning_rate)
    rng = np.random.default_rng(seed)
    last_losses: dict[str, float] = {}
    model.train()
    for _ in range(frozen.training_epochs):
        order = rng.permutation(len(train_windows))
        totals = {
            "total_loss": 0.0,
            "reconstruction_loss": 0.0,
            "koopman_loss": 0.0,
            "diffusion_loss": 0.0,
        }
        cell_count = 0
        for start in range(0, order.size, frozen.batch_size):
            rows = order[start : start + frozen.batch_size]
            return_tensor = torch.from_numpy(normalized_train_returns[rows])
            feature_tensor = torch.from_numpy(train_windows.features[rows])
            optimizer.zero_grad(set_to_none=True)
            output = model.training_objective(return_tensor, feature_tensor)
            output.total_loss.backward()
            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                max_norm=frozen.gradient_clip_norm,
            )
            optimizer.step()
            cells = int(rows.size)
            totals["total_loss"] += float(output.total_loss.detach()) * cells
            totals["reconstruction_loss"] += float(output.reconstruction_loss.detach()) * cells
            totals["koopman_loss"] += float(output.koopman_loss.detach()) * cells
            totals["diffusion_loss"] += float(output.diffusion_loss.detach()) * cells
            cell_count += cells
        last_losses = {key: value / max(cell_count, 1) for key, value in totals.items()}
    test_windows = build_factorlab_reaka_windows(
        panel,
        test_indices,
        model_config=frozen,
        adapter_config=adapter,
    )
    if len(test_windows) < adapter.minimum_test_windows:
        raise ValueError("reaka_paper_test_window_count_insufficient")
    normalized_test_returns = ((test_windows.returns - return_mean) / return_scale).astype(np.float32)
    score_draws: list[NDArray[np.float64]] = []
    operator_rows: list[NDArray[np.int64]] = []
    gate_means: list[float] = []
    residual_energy: list[float] = []
    initial_noise_energy: list[float] = []
    model.eval()
    with torch.no_grad():
        for draw in range(frozen.inference_draws):
            generator = torch.Generator(device="cpu")
            generator.manual_seed(seed * 1009 + draw)
            draw_scores: list[NDArray[np.float64]] = []
            draw_operators: list[NDArray[np.int64]] = []
            for start in range(0, len(test_windows), frozen.batch_size):
                stop = min(start + frozen.batch_size, len(test_windows))
                forecast = model.forecast(
                    torch.from_numpy(normalized_test_returns[start:stop]),
                    torch.from_numpy(test_windows.features[start:stop]),
                    generator=generator,
                )
                draw_scores.append(forecast.scores.cpu().numpy().astype(np.float64))
                draw_operators.append(forecast.operator_ids[:, -1].cpu().numpy().astype(np.int64))
                gate_means.append(float(forecast.gate.mean()))
                residual_energy.append(float(torch.mean(torch.square(forecast.residual))))
                initial_noise_energy.append(float(torch.mean(torch.square(forecast.initial_noise))))
            score_draws.append(np.concatenate(draw_scores))
            if draw == 0:
                operator_rows = draw_operators
    scores = np.mean(np.vstack(score_draws), axis=0)
    operator_ids = np.concatenate(operator_rows)
    operators = model.operators.detach().cpu().numpy().astype(np.float64)
    diagnostics: dict[str, object] = {
        "fit_kind": "paper_formula_faithful_dual_lstm_gate_aks_conditional_ddpm_joint_loss",
        "strategy_id": REAKA_PAPER_STRATEGY_ID,
        "input_factor_count": len(panel.factor_ids),
        "train_row_count": int(len(train_windows)),
        "test_row_count": int(len(test_windows)),
        "dropped_train_window_count": int(len(train_indices) - len(train_windows)),
        "dropped_test_window_count": int(len(test_indices) - len(test_windows)),
        "return_train_mean": return_mean,
        "return_train_scale": return_scale,
        "last_epoch_joint_losses": last_losses,
        "joint_loss_exact_sum": True,
        "separate_postfit_residual_training": False,
        "ranking_head": "paper_decoder_last_element_direct_return_score",
        "operator_count": frozen.operator_count,
        "operator_occupancy": _operator_occupancy(
            operator_ids,
            frozen.operator_count,
        ),
        "operator_digest": canonical_digest(operators.round(10).tolist()),
        "gate_mean": float(np.mean(gate_means)),
        "sampled_residual_energy": float(np.mean(residual_energy)),
        "initial_gaussian_noise_energy": float(np.mean(initial_noise_energy)),
        "reverse_process_started_from_gaussian_noise": True,
        "test_current_outcomes_used_during_fit": False,
        "historical_return_availability_checked_per_decision": True,
        "input_adapter": adapter.as_dict(),
        "paper_config": frozen.as_dict(),
        "paper_contract_digest": build_reaka_paper_replication_contract(
            config=frozen,
            input_profile="factorlab_round3a_monthly_adapter",
        )["canonical_digest"],
    }
    return ReakaPaperFitResult(
        sample_indices=test_windows.sample_indices,
        scores=scores,
        operator_ids=operator_ids,
        operator_matrices=operators,
        diagnostics=diagnostics,
    )


def _diffusion_schedule(
    config: ReakaPaperConfig,
) -> tuple[Tensor, Tensor, Tensor]:
    beta = torch.linspace(
        config.beta_start,
        config.beta_end,
        steps=config.diffusion_steps,
        dtype=torch.float32,
    )
    alpha = 1.0 - beta
    return beta, alpha, torch.cumprod(alpha, dim=0)


def _validate_model_inputs(
    returns: Tensor,
    features: Tensor,
    *,
    feature_dim: int,
    minimum_sequence: int = 1,
) -> None:
    if returns.ndim != 2 or features.ndim != 3:
        raise ValueError("reaka_paper_input_rank_mismatch")
    if returns.shape[:2] != features.shape[:2]:
        raise ValueError("reaka_paper_return_feature_window_mismatch")
    if features.shape[2] != feature_dim:
        raise ValueError("reaka_paper_feature_identity_mismatch")
    if returns.shape[1] < minimum_sequence:
        raise ValueError("reaka_paper_sequence_too_short")
    if not bool(torch.isfinite(returns).all()) or not bool(torch.isfinite(features).all()):
        raise ValueError("reaka_paper_inputs_must_be_finite")


def _empty_windows(
    panel: Round2Panel,
    *,
    model_config: ReakaPaperConfig,
) -> ReakaPaperWindows:
    return ReakaPaperWindows(
        sample_indices=np.empty(0, dtype=np.int64),
        month_indices=np.empty(
            (0, model_config.window_length),
            dtype=np.int64,
        ),
        symbol_indices=np.empty(0, dtype=np.int64),
        returns=np.empty(
            (0, model_config.window_length),
            dtype=np.float32,
        ),
        features=np.empty(
            (0, model_config.window_length, len(panel.factor_ids)),
            dtype=np.float32,
        ),
    )


def _operator_occupancy(
    operator_ids: NDArray[np.int64],
    count: int,
) -> dict[str, float]:
    if operator_ids.size == 0:
        return {str(index): 0.0 for index in range(count)}
    return {str(index): float(np.mean(operator_ids == index)) for index in range(count)}


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


__all__ = [
    "REAKA_PAPER_ARM_IDS",
    "REAKA_PAPER_FULL_ARM_ID",
    "REAKA_PAPER_RESIDUAL_MLP_ARM_ID",
    "REAKA_PAPER_VANILLA_AE_ARM_ID",
    "REAKA_PAPER_WITHOUT_AKS_ARM_ID",
    "REAKA_PAPER_WITHOUT_DRC_ARM_ID",
    "REAKA_PAPER_WITHOUT_GATE_ARM_ID",
    "FactorLabReakaAdapterConfig",
    "REAKA_PAPER_CONTRACT_SCHEMA_ID",
    "REAKA_PAPER_SOURCE_REF",
    "REAKA_PAPER_STRATEGY_ID",
    "ReakaPaperAblation",
    "ReakaPaperConfig",
    "ReakaPaperFitResult",
    "ReakaPaperForecast",
    "ReakaPaperModel",
    "ReakaPaperTrainingOutput",
    "ReakaPaperWindows",
    "build_factorlab_reaka_windows",
    "build_reaka_paper_replication_contract",
    "fit_reaka_paper_challenger",
    "reaka_paper_ablation",
]
