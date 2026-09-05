"""Stage 6 r1 paper-faithful daily training engine (whole-policy rebuild).

The v1 engine was rejected fail-closed by the main controller.  This r1
rebuild is a fresh implementation from the frozen root that repairs every
blocking category in
``docs/ops/evidence/reaka_stage6_engineering_controller_acceptance_v1_20260817``:

1.  availability masks now ENTER the model: each task feature axis is
    ``[rank_centered_values; availability_masks]`` so a true neutral zero
    and a zero-filled missing cell are distinguishable;
2.  the task horizon is bound to the model target: the decoder reconstructs
    the task's ``h``-day label sequence (T+1-open entry, h-day close exit)
    instead of a one-step daily return; the last element remains the
    paper's score (equations 22-27);
3.  the fit seed is set BEFORE model construction so the initial weights
    are reproducible;
4.  the 1% perturbation check compares a genuine pre-perturbation baseline
    against the perturbed model and restores the parameters afterwards;
5.  ``n_k_eff`` is the Kish effective-sample size of soft operator
    transitions, ``(sum w)^2 / sum(w^2)`` over all batch x time
    observations (dimension = transitions), and is reported together with
    ``N``, ``K``, ``d`` and ``n_k_eff / d^2``;
6.  auxiliary residual probes are explicitly non-authoritative; formal
    four-residual evidence is built only from independently trained frozen
    without-DRC / residual-MLP / REAKA arms on one bound support set;
7.  the annual receipt chain recomputes every digest from file bytes
    (never trusting a self-reported field), binds the policy digest to the
    freeze manifest and the tensor digest to the tensor manifest, and
    rejects any chain gap;
8.  the immutable tensor manifest binds the sha256 of every shared array,
    task spec and rows file, and every loader verifies those digests
    before use (fail closed);
9.  annual boundary discipline: every row carries its decision year and
    its label exit year; training rows require the exit inside the
    training prefix, validation rows inside the validation year, and
    diagnostic rows report the cross-year label count explicitly;
10. the handoff validator re-computes key artifacts from raw inputs
    instead of trusting self-reported ``passed`` booleans.

This module contains no scientific judgement: it never ranks candidates by
returns, never opens 2021-2026 rows, and never claims scientific or
production authority.  ``production_authority=false`` everywhere.
"""

# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false, reportMissingTypeArgument=false
# pyright: reportReturnType=false, reportIndexIssue=false
# pyright: reportOperatorIssue=false, reportCallIssue=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnusedCallResult=false
# pyright: reportPossiblyUnboundVariable=false, reportUnusedExpression=false
# pyright: reportImplicitRelativeImport=false

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Final, Literal, cast

import numpy as np
import pandas as pd
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

from factor_lab.factor_rotation.reaka_paper_v1 import (
    REAKA_PAPER_ARM_IDS,
    REAKA_PAPER_FULL_ARM_ID,
    ReakaPaperAblation,
    ReakaPaperConfig,
    ReakaPaperModel,
    ReakaPaperTrainingOutput,
    reaka_paper_ablation,
)
from factor_lab.factor_rotation.reaka_stage6_paper_faithful_freeze import (
    LATENT_DIMENSIONS,
    MODEL_ARM_IDS,
    OPERATOR_COUNTS,
    SEEDS,
    STAGE6_STRATEGY_ID,
    Stage6FreezePolicy,
    canonical_digest,
)
from factor_lab.governance.reaka_residual_certificate import (
    FORMAL_CROSS_ARM_IDS,
    STAGE6_FORMAL_CROSS_ARM_SCHEMA_ID,
    Stage6FormalArmResidualEvidence,
    build_formal_cross_arm_residual_certificate,
    formal_cross_arm_residual_certificate_valid,
)

STAGE6_ENGINE_SCHEMA_ID: Final = "factorlab.reaka_stage6_daily_engine@2.0"
STAGE6_TENSOR_SCHEMA_ID: Final = (
    "factorlab.reaka_stage6_daily_tensor_manifest@2.0"
)
STAGE6_HEALTH_SCHEMA_ID: Final = (
    "factorlab.reaka_stage6_training_health_snapshot@2.0"
)
STAGE6_CERTIFICATE_SCHEMA_ID: Final = (
    "factorlab.reaka_stage6_posttraining_certificate@2.0"
)
STAGE6_YEAR_RECEIPT_SCHEMA_ID: Final = (
    "factorlab.reaka_stage6_annual_controller_receipt@1.0"
)
VALID_CADENCES: Final = ("daily", "weekly", "biweekly")
VALID_HORIZONS: Final = (1, 5, 10, 20, 40)
CADENCE_INTERVALS: Final = {"daily": 1, "weekly": 5, "biweekly": 10}
HORIZON_INDEX: Final = {1: 0, 5: 1, 10: 2, 20: 3, 40: 4}
PATHWAY_IDS: Final = (
    "long_term_main_effect",
    "spatial_specialist",
    "self_lagged_effectiveness_following",
)
VALID_LOOKBACKS: Final = (3, 6, 12)
VALID_QUANTILE_BINS: Final = (0, 1, 2, 3, 4)
MISSING_BIN: Final = np.uint8(255)
FINANCIAL_MONTHLY_FACTORS: Final = (
    "accruals_lag1",
    "asset_turnover_lag1",
    "cash_flow_roe_lag1",
    "cash_flow_to_assets_lag1",
    "earnings_quality_lag1",
    "operating_margin_lag1",
    "sales_to_price_lag1",
)
DESCRIPTOR_COLUMNS: Final = (
    "total_market_cap",
    "float_market_cap",
    "amihud_illiquidity_20d_lag1",
    "beta_20d_lag1",
    "low_volume_momentum_20d_lag1",
)
LABEL_COLUMNS: Final = ("ret_1", "ret_5", "ret_10", "ret_20", "ret_40")
TRAINABLE_ARM_IDS: Final = (
    "vanilla_autoencoder",
    "fixed_k_no_residual",
    "without_aks",
    "without_drc",
    "residual_mlp",
    "without_gate",
    "reaka",
)
TRANSPARENT_ARM_ID: Final = "transparent_rank"
YEAR_MIN: Final = 2009
YEAR_MAX: Final = 2020
ROW_COLUMNS: Final = ("day_position", "symbol_position", "exit_year")
ROW_WIDTH: Final = 3
HASH_CHUNK: Final = 1 << 22

ResidualMode = Literal["none", "mlp", "diffusion"]


# ---------------------------------------------------------------------------
# Frozen arm registry (echo of model_arm_registry.csv, single source of truth)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stage6ArmSpec:
    """One frozen model arm from the Stage 6 arm registry."""

    arm_id: str
    layer_order: int
    feature_gate: bool
    adaptive_selector: bool
    koopman_transition: bool
    residual_mode: ResidualMode
    paper_relation: str
    scientific_activation_prerequisite: str

    @property
    def is_transparent(self) -> bool:
        return self.arm_id == TRANSPARENT_ARM_ID

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


_STAGE6_ARM_ROWS: Final = (
    (TRANSPARENT_ARM_ID, 0, False, False, False, "none", "project_common_root", "always"),
    ("vanilla_autoencoder", 1, True, False, False, "none", "paper_table2_autoencoder", "transparent_core_accepted"),
    ("fixed_k_no_residual", 2, True, False, True, "none", "project_identifiability_prerequisite", "neural_carrier_health_passed"),
    ("without_aks", 3, True, False, True, "diffusion", "paper_table2_without_aks", "full_engine_implemented_diagnostic_only"),
    ("without_drc", 4, True, True, True, "none", "paper_table2_without_drc", "fixed_k_and_neural_health_passed"),
    ("residual_mlp", 5, True, True, True, "mlp", "paper_table2_residual_mlp", "adaptive_koopman_health_passed"),
    ("without_gate", 6, False, True, True, "diffusion", "paper_table2_without_gate", "full_engine_implemented_diagnostic_only"),
    ("reaka", 7, True, True, True, "diffusion", "paper_full", "residual_mlp_health_passed"),
)


def stage6_arm_spec(arm_id: str) -> Stage6ArmSpec:
    """Return the frozen arm specification, rejecting unknown arms."""

    for row in _STAGE6_ARM_ROWS:
        if row[0] == arm_id:
            return Stage6ArmSpec(
                arm_id=str(row[0]),
                layer_order=int(row[1]),
                feature_gate=bool(row[2]),
                adaptive_selector=bool(row[3]),
                koopman_transition=bool(row[4]),
                residual_mode=cast(ResidualMode, str(row[5])),
                paper_relation=str(row[6]),
                scientific_activation_prerequisite=str(row[7]),
            )
    raise ValueError(f"stage6_arm_unknown:{arm_id}")


def stage6_arm_specs() -> dict[str, Stage6ArmSpec]:
    return {spec.arm_id: spec for spec in (stage6_arm_spec(a) for a in MODEL_ARM_IDS)}


def stage6_trainable_arm_ids() -> tuple[str, ...]:
    return TRAINABLE_ARM_IDS


# Frozen layer-unlock ladder: each arm's scientific activation prerequisite
# names the arm whose post-training health certificate must already have
# passed (the controller's adjudicated ladder, mechanically enforced by the
# one-year runner).  Diagnostic-only arms gate on the engine being
# implemented, not on another arm's health.
LAYER_UNLOCK_PREREQUISITE_ARM: Final = {
    "vanilla_autoencoder": TRANSPARENT_ARM_ID,
    "fixed_k_no_residual": "vanilla_autoencoder",
    "without_drc": "fixed_k_no_residual",
    "residual_mlp": "without_drc",
    "reaka": "residual_mlp",
}
LAYER_UNLOCK_DIAGNOSTIC_ONLY: Final = frozenset({"without_aks", "without_gate"})


def layer_unlock_prerequisite_satisfied(
    *,
    arm_id: str,
    activated_arm_ids: set[str],
) -> bool:
    """Mechanical layer-unlock gate.

    ``transparent_rank`` is the always-activated common root; the
    diagnostic-only arms (``without_aks`` / ``without_gate``) require only
    that the full engine is implemented; every other arm requires its
    frozen prerequisite arm to be in the controller-provided activated
    set.  The runner refuses any fit whose prerequisite is not satisfied.
    """

    activated = set(activated_arm_ids) | {TRANSPARENT_ARM_ID}
    if arm_id == TRANSPARENT_ARM_ID or arm_id in LAYER_UNLOCK_DIAGNOSTIC_ONLY:
        return True
    prerequisite = LAYER_UNLOCK_PREREQUISITE_ARM.get(arm_id)
    if prerequisite is None:
        raise ValueError(f"stage6_arm_layer_ladder_missing:{arm_id}")
    return prerequisite in activated


def _paper_ablation_for(spec: Stage6ArmSpec) -> ReakaPaperAblation:
    """Map a frozen Stage 6 arm onto the paper ablation space."""

    if spec.arm_id in REAKA_PAPER_ARM_IDS:
        ablation = reaka_paper_ablation(spec.arm_id)
        expected = (
            bool(ablation.feature_gate) == spec.feature_gate
            and bool(ablation.adaptive_koopman_selector) == spec.adaptive_selector
            and bool(ablation.koopman_transition) == spec.koopman_transition
            and ablation.residual_mode == spec.residual_mode
        )
        if not expected:
            raise RuntimeError(f"stage6_arm_paper_mapping_drift:{spec.arm_id}")
        return ablation
    return ReakaPaperAblation(
        arm_id=spec.arm_id,
        feature_gate=spec.feature_gate,
        adaptive_koopman_selector=spec.adaptive_selector,
        koopman_transition=spec.koopman_transition,
        residual_mode=spec.residual_mode,
    )


class Stage6ReakaModel(ReakaPaperModel):
    """``ReakaPaperModel`` bound to a frozen Stage 6 arm id plus two r1
    input-identity repairs:

    - the feature axis carries ``[values; masks]`` so missingness enters
      the model (frozen_input_identity ``append_availability_mask``);
    - ``training_objective`` accepts the task's ``h``-day label sequence
      as the decoder reconstruction target, so each task learns its own
      horizon instead of a shared one-step daily return (equations 22-27
      keep their decoder + last-element structure).

    When ``targets`` is ``None`` the override reproduces the parent
    objective exactly (a unit test proves byte-for-byte loss equality),
    which anchors the paper equations 1-31 fidelity.
    """

    def __init__(
        self,
        *,
        feature_dim: int,
        config: ReakaPaperConfig,
        arm_id: str,
    ) -> None:
        spec = stage6_arm_spec(arm_id)
        if spec.is_transparent:
            raise ValueError("stage6_transparent_arm_has_no_neural_carrier")
        ablation = _paper_ablation_for(spec)
        self._stage6_single_operator_forced = config.operator_count == 1
        if self._stage6_single_operator_forced and ablation.adaptive_koopman_selector:
            ablation = ReakaPaperAblation(
                arm_id=ablation.arm_id,
                feature_gate=ablation.feature_gate,
                adaptive_koopman_selector=False,
                koopman_transition=ablation.koopman_transition,
                residual_mode=ablation.residual_mode,
            )
        parent_config = config
        if self._stage6_single_operator_forced:
            parent_config = replace(config, operator_count=2)
        if spec.arm_id in REAKA_PAPER_ARM_IDS:
            super().__init__(
                feature_dim=feature_dim,
                config=parent_config,
                ablation=ablation,
            )
        else:
            proxy = ReakaPaperAblation(
                arm_id=REAKA_PAPER_FULL_ARM_ID,
                feature_gate=ablation.feature_gate,
                adaptive_koopman_selector=ablation.adaptive_koopman_selector,
                koopman_transition=ablation.koopman_transition,
                residual_mode=ablation.residual_mode,
            )
            super().__init__(
                feature_dim=feature_dim,
                config=parent_config,
                ablation=proxy,
            )
            self.ablation = ablation
        if self._stage6_single_operator_forced:
            object.__setattr__(self, "config", replace(parent_config, operator_count=1))
            identity = torch.eye(config.latent_dim).repeat(1, 1, 1)
            self.operators = nn.Parameter(identity + 0.01 * torch.randn_like(identity))

    def training_objective(
        self,
        returns: Tensor,
        features: Tensor,
        *,
        targets: Tensor | None = None,
        target_mask: Tensor | None = None,
        diffusion_steps: Tensor | None = None,
        diffusion_noise: Tensor | None = None,
    ) -> ReakaPaperTrainingOutput:
        """Paper objective (1)-(31) with the task horizon as decoder target.

        Without ``targets`` this is numerically identical to the parent
        ``training_objective`` (verified by tests).  With ``targets`` the
        reconstruction loss regresses the decoder output against the
        task's ``h``-day label sequence; ``target_mask`` (0/1, same shape)
        excludes missing labels cell-wise, so a missing horizon label is
        never zero-filled into the loss.
        """

        from factor_lab.factor_rotation.reaka_paper_v1 import (  # noqa: E402
            _validate_model_inputs,
        )

        _validate_model_inputs(
            returns,
            features,
            feature_dim=self.feature_dim,
            minimum_sequence=2,
        )
        batch = returns.shape[0]
        if targets is not None:
            if targets.shape != returns.shape:
                raise ValueError("reaka_stage6_target_shape_mismatch")
            if target_mask is None:
                target_mask = torch.isfinite(targets).to(returns.dtype)
            if target_mask.shape != returns.shape:
                raise ValueError("reaka_stage6_target_mask_shape_mismatch")
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
            noisy_residual = (
                torch.sqrt(selected_bar) * true_residual
                + torch.sqrt(1.0 - selected_bar) * diffusion_noise
            )
            predicted_noise = self.residual_denoiser(
                noisy_residual,
                diffusion_steps,
                latent,
            )
            estimated_residual = (
                noisy_residual
                - torch.sqrt(1.0 - selected_bar) * predicted_noise
            ) / torch.sqrt(selected_bar)
            diffusion_loss = torch.nn.functional.mse_loss(
                predicted_noise, diffusion_noise
            )
        elif self.ablation.residual_mode == "mlp":
            if self.residual_mlp is None:
                raise AssertionError("reaka_paper_residual_mlp_missing")
            estimated_residual = self.residual_mlp(latent)
            diffusion_loss = torch.nn.functional.mse_loss(
                estimated_residual, true_residual
            )
        else:
            estimated_residual = torch.zeros_like(true_residual)
            diffusion_loss = torch.zeros(
                (), dtype=returns.dtype, device=returns.device
            )
        corrected = advanced + estimated_residual
        historical_prediction = self.decoder(latent).squeeze(-1)
        shifted_prediction = self.decoder(
            next_latent if not self.ablation.koopman_transition else corrected
        ).squeeze(-1)
        if targets is None:
            reconstruction_loss = torch.nn.functional.mse_loss(
                historical_prediction, historical_returns
            ) + torch.nn.functional.mse_loss(
                shifted_prediction, shifted_returns
            )
        else:
            mask = target_mask
            historical_target = targets[:, :-1]
            shifted_target = targets[:, 1:]
            historical_weight = mask[:, :-1]
            shifted_weight = mask[:, 1:]
            reconstruction_loss = _masked_mse(
                historical_prediction, historical_target, historical_weight
            ) + _masked_mse(
                shifted_prediction, shifted_target, shifted_weight
            )
        koopman_loss = (
            torch.nn.functional.mse_loss(advanced, next_latent)
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


def _masked_mse(prediction: Tensor, target: Tensor, weight: Tensor) -> Tensor:
    """Cell-wise masked MSE; returns zero when no cell is valid."""

    weight = weight.clamp(min=0.0)
    total_weight = weight.sum()
    if float(total_weight) <= 0.0:
        return torch.zeros((), dtype=prediction.dtype, device=prediction.device)
    target = torch.where(weight > 0.0, target, torch.zeros_like(target))
    squared = torch.square(prediction - target) * weight
    return squared.sum() / total_weight


def build_stage6_reaka_model(
    *,
    feature_dim: int,
    arm_id: str,
    policy: Stage6FreezePolicy | None = None,
    sequence_length: int | None = None,
    latent_dim: int | None = None,
    operator_count: int | None = None,
) -> Stage6ReakaModel:
    """Construct one frozen arm with the frozen training policy baked in."""

    frozen = policy or Stage6FreezePolicy()
    frozen.validate()
    spec = stage6_arm_spec(arm_id)
    if spec.is_transparent:
        raise ValueError("stage6_transparent_arm_has_no_neural_carrier")
    if latent_dim is not None and latent_dim not in LATENT_DIMENSIONS:
        raise ValueError(f"stage6_latent_dimension_not_frozen:{latent_dim}")
    if operator_count is not None and operator_count not in OPERATOR_COUNTS:
        raise ValueError(f"stage6_operator_count_not_frozen:{operator_count}")
    config = ReakaPaperConfig(
        window_length=sequence_length or 10,
        latent_dim=latent_dim or 16,
        operator_count=operator_count or 4,
        training_epochs=frozen.maximum_epochs,
        diffusion_steps=frozen.diffusion_steps,
        batch_size=frozen.batch_size,
        learning_rate=frozen.learning_rate,
        gumbel_temperature=frozen.gumbel_temperature,
        beta_start=frozen.diffusion_beta_start,
        beta_end=frozen.diffusion_beta_end,
        gradient_clip_norm=frozen.gradient_clip_norm,
    )
    return Stage6ReakaModel(
        feature_dim=feature_dim,
        config=config,
        arm_id=arm_id,
    )


# ---------------------------------------------------------------------------
# Task channel compilation (the 1,183-ticket formula)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stage6TicketChannel:
    """One compiled usage ticket inside a task feature axis."""

    usage_ticket_id: str
    factor_id: str
    factor_index: int
    pathway_id: str
    descriptor_index: int
    quantile_bins: tuple[int, ...]
    follow_ticket_index: int
    mechanism_vote_weight: float
    scope_or_context_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "usage_ticket_id": self.usage_ticket_id,
            "factor_id": self.factor_id,
            "factor_index": self.factor_index,
            "pathway_id": self.pathway_id,
            "descriptor_index": self.descriptor_index,
            "quantile_bins": list(self.quantile_bins),
            "follow_ticket_index": self.follow_ticket_index,
            "mechanism_vote_weight": self.mechanism_vote_weight,
            "scope_or_context_id": self.scope_or_context_id,
        }


@dataclass(frozen=True, slots=True)
class Stage6TaskSpec:
    """Frozen compile plan for one ``cadence_id x horizon_days`` task."""

    task_id: str
    cadence_id: str
    horizon_days: int
    sequence_length_candidates: tuple[int, ...]
    state_duration_candidate_days: tuple[int, ...]
    channels: tuple[Stage6TicketChannel, ...]
    tensor_digest: str
    tickets_csv_digest: str
    freeze_root_digest: str

    @property
    def channel_count(self) -> int:
        return len(self.channels)

    @property
    def model_feature_dim(self) -> int:
        """Values plus masks: two model features per channel."""

        return 2 * len(self.channels)

    @property
    def horizon_index(self) -> int:
        return HORIZON_INDEX[self.horizon_days]

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "task_id": self.task_id,
            "cadence_id": self.cadence_id,
            "horizon_days": self.horizon_days,
            "sequence_length_candidates": list(self.sequence_length_candidates),
            "state_duration_candidate_days": list(self.state_duration_candidate_days),
            "channels": [channel.as_dict() for channel in self.channels],
            "tensor_digest": self.tensor_digest,
            "tickets_csv_digest": self.tickets_csv_digest,
            "freeze_root_digest": self.freeze_root_digest,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


def compile_task_channels(
    *,
    task_rows: pd.DataFrame,
    tickets: pd.DataFrame,
    factor_ids: tuple[str, ...],
    descriptor_ids: tuple[str, ...],
    follow_ticket_ids: tuple[str, ...],
) -> tuple[Stage6TicketChannel, ...]:
    """Compile one task's tickets into ordered, formula-ready channels."""

    if len(task_rows) != 1:
        raise ValueError("stage6_task_rows_must_select_exactly_one_task")
    task = task_rows.iloc[0]
    task_id = str(task["task_id"])
    required = {
        "usage_ticket_id",
        "factor_id",
        "pathway_id",
        "cadence_id",
        "horizon_days",
        "mechanism_vote_weight",
    }
    if missing := required - set(tickets.columns):
        raise ValueError(f"stage6_ticket_columns_missing:{sorted(missing)}")
    factor_index = {factor_id: index for index, factor_id in enumerate(factor_ids)}
    descriptor_index = {name: index for index, name in enumerate(descriptor_ids)}
    follow_index = {name: index for index, name in enumerate(follow_ticket_ids)}
    channels: list[Stage6TicketChannel] = []
    for row in tickets.sort_values("usage_ticket_id", kind="mergesort").itertuples(index=False):
        pathway = str(row.pathway_id)
        if pathway not in PATHWAY_IDS:
            raise ValueError(f"stage6_ticket_pathway_unknown:{pathway}")
        if str(row.cadence_id) != str(task["cadence_id"]) or int(row.horizon_days) != int(task["horizon_days"]):
            raise ValueError(f"stage6_ticket_task_mismatch:{row.usage_ticket_id}")
        if row.factor_id not in factor_index:
            raise ValueError(f"stage6_ticket_factor_not_in_tensor:{row.factor_id}")
        descriptor = (
            str(row.descriptor_factor_id)
            if pd.notna(getattr(row, "descriptor_factor_id", None))
            else ""
        )
        descriptor_pos = descriptor_index.get(descriptor, -1)
        bins = (0, 1, 2, 3, 4) if pathway == "long_term_main_effect" else ()
        follow_pos = -1
        if pathway == "spatial_specialist":
            raw_bins = str(row.quantile_bins)
            bins = tuple(int(value) for value in raw_bins.split(",") if value)
            if not bins or any(value not in VALID_QUANTILE_BINS for value in bins):
                raise ValueError(f"stage6_spatial_bins_invalid:{row.usage_ticket_id}:{raw_bins}")
            if descriptor_pos < 0:
                raise ValueError(f"stage6_spatial_descriptor_not_in_tensor:{row.usage_ticket_id}")
        elif pathway == "self_lagged_effectiveness_following":
            scope = str(row.scope_or_context_id)
            lookback = int(scope.removeprefix("matured_lookback_"))
            if lookback not in VALID_LOOKBACKS:
                raise ValueError(f"stage6_follow_lookback_invalid:{row.usage_ticket_id}")
            follow_pos = follow_index.get(str(row.usage_ticket_id), -1)
            if follow_pos < 0:
                raise ValueError(f"stage6_follow_series_missing:{row.usage_ticket_id}")
        vote = float(row.mechanism_vote_weight)
        if not np.isfinite(vote) or vote <= 0.0:
            raise ValueError(f"stage6_vote_weight_invalid:{row.usage_ticket_id}")
        channels.append(
            Stage6TicketChannel(
                usage_ticket_id=str(row.usage_ticket_id),
                factor_id=str(row.factor_id),
                factor_index=factor_index[str(row.factor_id)],
                pathway_id=pathway,
                descriptor_index=descriptor_pos,
                quantile_bins=bins,
                follow_ticket_index=follow_pos,
                mechanism_vote_weight=vote,
                scope_or_context_id=str(row.scope_or_context_id),
            )
        )
    if not channels:
        raise ValueError(f"stage6_task_has_no_channels:{task_id}")
    return tuple(channels)


def transparent_rank_scores(
    *,
    values: NDArray[np.floating],
    availability: NDArray[np.uint8],
) -> NDArray[np.float64]:
    """Deterministic common-root score: mean of available channels."""

    values_arr = np.asarray(values)
    mask = np.asarray(availability, dtype=bool)
    usable = values_arr * mask
    counts = mask.sum(axis=-1)
    scores = np.zeros(values_arr.shape[:-1], dtype=np.float64)
    positive = counts > 0
    scores[positive] = usable[positive].sum(axis=-1) / counts[positive]
    return scores


# ---------------------------------------------------------------------------
# Immutable tensor layout and verified loading
# ---------------------------------------------------------------------------

SHARED_ARRAYS: Final = (
    "calendar",
    "symbols",
    "base_rank_centered",
    "base_available",
    "descriptor_bins",
    "labels",
    "daily_returns",
    "entry_ok",
    "follow_weights",
)


@dataclass(frozen=True, slots=True)
class Stage6SharedTensor:
    """Verified, mmap-backed shared tensor root materialized once for all 12 tasks."""

    root: Path
    calendar: NDArray[np.datetime64]
    symbols: NDArray[np.str_]
    base_rank_centered: NDArray[np.float32]
    base_available: NDArray[np.uint8]
    descriptor_bins: NDArray[np.uint8]
    labels: NDArray[np.float64]
    daily_returns: NDArray[np.float32]
    entry_ok: NDArray[np.uint8]
    follow_weights: NDArray[np.float64]
    follow_ticket_ids: tuple[str, ...]
    factor_ids: tuple[str, ...]
    descriptor_ids: tuple[str, ...]
    manifest_digest: str

    @property
    def day_count(self) -> int:
        return int(self.calendar.size)

    @property
    def symbol_count(self) -> int:
        return int(self.symbols.size)

    def year_positions(self, year: int) -> NDArray[np.int64]:
        years = self.calendar.astype("datetime64[Y]").astype(int) + 1970
        return np.flatnonzero(years == year).astype(np.int64)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_bytes(path: Path, expected_digest: str, label: str) -> bytes:
    actual = sha256_file(path)
    if actual != expected_digest:
        raise RuntimeError(
            f"stage6_tensor_immutability_breach:{label}:{actual}!={expected_digest}"
        )
    return path.read_bytes()


def _load_tensor_manifest(root: Path) -> dict[str, object]:
    """Load the tensor manifest and recompute its digest fail-closed."""

    path = root / "manifest.json"
    raw = _verified_text(path, label="manifest")
    payload = json.loads(raw)
    if payload.get("schema_id") != STAGE6_TENSOR_SCHEMA_ID:
        raise ValueError("stage6_tensor_manifest_schema_mismatch")
    declared = str(payload.get("canonical_digest", ""))
    recomputed = canonical_digest(
        {key: value for key, value in payload.items() if key != "canonical_digest"}
    )
    if declared != recomputed:
        raise RuntimeError("stage6_tensor_manifest_digest_tampered")
    return payload


def _verified_text(path: Path, *, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"stage6_tensor_artifact_unreadable:{label}") from exc


def load_shared_tensor(root: Path, *, verify: bool = True) -> Stage6SharedTensor:
    """Load the shared tensor root with mmap and full digest verification."""

    manifest = _load_tensor_manifest(root)
    artifacts = manifest.get("artifacts", {})
    arrays: dict[str, NDArray[Any]] = {}
    for name in SHARED_ARRAYS:
        path = root / "shared" / f"{name}.npz"
        if verify:
            expected = artifacts.get(f"shared/{name}.npz")
            if not expected:
                raise RuntimeError(f"stage6_tensor_artifact_not_bound:shared/{name}.npz")
            _verified_bytes(path, str(expected), label=f"shared/{name}.npz")
        arrays[name] = cast(
            NDArray[Any], np.load(path, mmap_mode="r", allow_pickle=False)["arr"]
        )
    follow_path = root / "shared" / "follow_ticket_ids.json"
    if verify:
        expected = artifacts.get("shared/follow_ticket_ids.json")
        if not expected:
            raise RuntimeError("stage6_tensor_artifact_not_bound:follow_ticket_ids")
        _verified_bytes(follow_path, str(expected), label="follow_ticket_ids.json")
    follow_ticket_ids = tuple(
        str(item)
        for item in json.loads(follow_path.read_text(encoding="utf-8"))
    )
    factor_ids = tuple(str(item) for item in manifest["factor_ids"])
    descriptor_ids = tuple(str(item) for item in manifest["descriptor_ids"])
    return Stage6SharedTensor(
        root=root,
        calendar=cast(NDArray[np.datetime64], arrays["calendar"]),
        symbols=cast(NDArray[np.str_], arrays["symbols"]),
        base_rank_centered=cast(NDArray[np.float32], arrays["base_rank_centered"]),
        base_available=cast(NDArray[np.uint8], arrays["base_available"]),
        descriptor_bins=cast(NDArray[np.uint8], arrays["descriptor_bins"]),
        labels=cast(NDArray[np.float64], arrays["labels"]),
        daily_returns=cast(NDArray[np.float32], arrays["daily_returns"]),
        entry_ok=cast(NDArray[np.uint8], arrays["entry_ok"]),
        follow_weights=cast(NDArray[np.float64], arrays["follow_weights"]),
        follow_ticket_ids=follow_ticket_ids,
        factor_ids=factor_ids,
        descriptor_ids=descriptor_ids,
        manifest_digest=str(manifest.get("canonical_digest", "")),
    )


def load_task_spec(root: Path, task_id: str, *, verify: bool = True) -> Stage6TaskSpec:
    manifest = _load_tensor_manifest(root)
    spec_path = root / "tasks" / task_id / "spec.json"
    if verify:
        expected = manifest.get("artifacts", {}).get(f"tasks/{task_id}/spec.json")
        if not expected:
            raise RuntimeError(f"stage6_tensor_artifact_not_bound:spec:{task_id}")
        _verified_bytes(spec_path, str(expected), label=f"spec:{task_id}")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    recomputed_spec_digest = canonical_digest(
        {key: value for key, value in payload.items() if key != "canonical_digest"}
    )
    if str(payload.get("canonical_digest", "")) != recomputed_spec_digest:
        raise RuntimeError(f"stage6_spec_digest_tampered:{task_id}")
    shared_digest = str(manifest.get("shared_content_digest", ""))
    if verify and shared_digest and str(payload.get("tensor_digest", "")) != shared_digest:
        raise RuntimeError(f"stage6_spec_shared_digest_unbound:{task_id}")
    channels = tuple(
        Stage6TicketChannel(
            usage_ticket_id=str(channel["usage_ticket_id"]),
            factor_id=str(channel["factor_id"]),
            factor_index=int(channel["factor_index"]),
            pathway_id=str(channel["pathway_id"]),
            descriptor_index=int(channel["descriptor_index"]),
            quantile_bins=tuple(int(value) for value in channel["quantile_bins"]),
            follow_ticket_index=int(channel["follow_ticket_index"]),
            mechanism_vote_weight=float(channel["mechanism_vote_weight"]),
            scope_or_context_id=str(channel["scope_or_context_id"]),
        )
        for channel in payload["channels"]
    )
    spec = Stage6TaskSpec(
        task_id=str(payload["task_id"]),
        cadence_id=str(payload["cadence_id"]),
        horizon_days=int(payload["horizon_days"]),
        sequence_length_candidates=tuple(int(v) for v in payload["sequence_length_candidates"]),
        state_duration_candidate_days=tuple(int(v) for v in payload["state_duration_candidate_days"]),
        channels=channels,
        tensor_digest=str(payload["tensor_digest"]),
        tickets_csv_digest=str(payload["tickets_csv_digest"]),
        freeze_root_digest=str(payload["freeze_root_digest"]),
    )
    if spec.task_id != task_id:
        raise RuntimeError("stage6_spec_task_id_mismatch")
    return spec


def load_task_rows(
    root: Path,
    task_id: str,
    sequence_length: int,
    *,
    verify: bool = True,
) -> dict[int, NDArray[np.int64]]:
    """Load per-year row index arrays of shape (n, 3):
    ``[day_position, symbol_position, exit_year]``."""

    manifest = _load_tensor_manifest(root)
    path = root / "tasks" / task_id / f"rows_L{sequence_length}.npz"
    if verify:
        expected = manifest.get("artifacts", {}).get(
            f"tasks/{task_id}/rows_L{sequence_length}.npz"
        )
        if not expected:
            raise RuntimeError(
                f"stage6_tensor_artifact_not_bound:rows:{task_id}:L{sequence_length}"
            )
        _verified_bytes(path, str(expected), label=f"rows:{task_id}:L{sequence_length}")
    data = np.load(path, mmap_mode="r", allow_pickle=False)
    result: dict[int, NDArray[np.int64]] = {}
    for year in range(YEAR_MIN, YEAR_MAX + 1):
        key = f"year_{year}"
        if key in data.files:
            rows = cast(NDArray[np.int64], data[key])
            if rows.size == 0:
                continue
            if rows.ndim != 2 or rows.shape[1] != ROW_WIDTH:
                raise RuntimeError(f"stage6_rows_shape_invalid:{task_id}:{year}")
            result[year] = rows
    if not result:
        raise RuntimeError(f"stage6_rows_empty:{task_id}:L{sequence_length}")
    return result


def decision_day_positions(shared: Stage6SharedTensor, cadence_id: str) -> NDArray[np.int64]:
    """Stage-12 ``decision_grids`` semantics over the shared calendar.

    The grid is anchored at the first market calendar day (2008-12-01, the
    sealed Stage-2 calendar start), sampled every 1/5/10 days, and gated to
    the first monthly PIT surface date (2009-01-23).  With the shared
    calendar identical to the Stage-2 market calendar this reproduces the
    sealed decision-day set exactly (verified for all three cadences).
    """

    if cadence_id not in CADENCE_INTERVALS:
        raise ValueError(f"stage6_cadence_unknown:{cadence_id}")
    anchor = np.datetime64("2008-12-01")
    start = np.datetime64("2009-01-23")
    end = np.datetime64("2020-12-31")
    if anchor not in shared.calendar:
        raise RuntimeError("stage6_calendar_missing_stage2_anchor_day")
    anchor_position = int(np.flatnonzero(shared.calendar == anchor)[0])
    positions = np.flatnonzero((shared.calendar >= start) & (shared.calendar <= end))
    positions = positions[positions >= anchor_position]
    step = CADENCE_INTERVALS[cadence_id]
    relative = positions - anchor_position
    return positions[(relative % step) == 0].astype(np.int64)


# ---------------------------------------------------------------------------
# Window assembly (equations 1-2 overlap windows + masks + horizon targets)
# ---------------------------------------------------------------------------


def _channel_value_matrix(
    shared: Stage6SharedTensor,
    channels: tuple[Stage6TicketChannel, ...],
    day_positions: NDArray[np.int64],
    symbol_positions: NDArray[np.int64],
) -> tuple[NDArray[np.float32], NDArray[np.uint8]]:
    """Compile ``(n, L, F)`` channel values and masks without copying the
    whole tensor."""

    factor_idx = np.asarray([channel.factor_index for channel in channels], dtype=np.int64)
    values = shared.base_rank_centered[
        day_positions[:, :, None], symbol_positions[:, :, None], factor_idx[None, None, :]
    ]
    available = shared.base_available[
        day_positions[:, :, None], symbol_positions[:, :, None], factor_idx[None, None, :]
    ].astype(np.uint8)
    for position, channel in enumerate(channels):
        if channel.pathway_id == "spatial_specialist" and channel.descriptor_index >= 0:
            bins = shared.descriptor_bins[
                day_positions, symbol_positions, channel.descriptor_index
            ]
            in_bins = np.isin(bins, np.asarray(channel.quantile_bins, dtype=np.uint8))
            values[:, :, position] *= in_bins.astype(np.float32)
            available[:, :, position] &= in_bins.astype(np.uint8)
        if channel.pathway_id == "self_lagged_effectiveness_following" and channel.follow_ticket_index >= 0:
            weights = shared.follow_weights[day_positions, channel.follow_ticket_index]
            finite = np.isfinite(weights)
            values[:, :, position] *= np.where(finite, weights, 0.0).astype(np.float32)
            available[:, :, position] &= finite.astype(np.uint8)
        values[:, :, position] *= np.float32(channel.mechanism_vote_weight)
    return values.astype(np.float32, copy=False), available


def assemble_windows(
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    rows: NDArray[np.int64],
    sequence_length: int,
    *,
    return_mean: float,
    return_scale: float,
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor]:
    """Assemble ``(n, L)`` returns, ``(n, L, 2F)`` mask-augmented features,
    ``(n, L, 2F)`` availability, and the task's ``h``-day label sequence
    with its validity mask.

    The feature axis is ``[values; masks]`` (r1 repair: missingness enters
    the model).  Returns are standardized with the training-prefix
    mean/scale; labels keep their raw units.  Label windows may contain
    NaN (suspension, exit beyond the closed calendar); ``target_mask``
    marks those cells so the loss never zero-fills them.
    """

    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0:
        raise ValueError("stage6_window_rows_empty")
    if rows.ndim != 2 or rows.shape[1] != ROW_WIDTH:
        raise ValueError("stage6_window_rows_must_carry_exit_year")
    if sequence_length not in spec.sequence_length_candidates:
        raise ValueError(f"stage6_sequence_length_not_frozen:{sequence_length}")
    offsets = np.arange(-(sequence_length - 1), 1, dtype=np.int64)
    day_positions = rows[:, 0, None] + offsets[None, :]
    if bool((day_positions < 0).any()):
        raise ValueError("stage6_window_reaches_before_calendar")
    symbol_positions = np.broadcast_to(rows[:, 1, None], day_positions.shape)
    returns = shared.daily_returns[day_positions, symbol_positions]
    if not np.isfinite(returns).all():
        raise ValueError("stage6_window_returns_must_be_finite")
    standardized = (
        (returns.astype(np.float64) - return_mean) / return_scale
    ).astype(np.float32)
    values, availability = _channel_value_matrix(
        shared, spec.channels, day_positions, symbol_positions
    )
    features = np.concatenate(
        [values, availability.astype(np.float32)], axis=-1
    )
    targets = shared.labels[day_positions, symbol_positions, spec.horizon_index]
    target_finite = np.isfinite(targets)
    targets = np.where(target_finite, targets, 0.0).astype(np.float32)
    target_mask = target_finite.astype(np.uint8)
    return (
        torch.from_numpy(np.ascontiguousarray(standardized)),
        torch.from_numpy(np.ascontiguousarray(features)),
        torch.from_numpy(np.ascontiguousarray(availability)),
        torch.from_numpy(np.ascontiguousarray(targets)),
        torch.from_numpy(np.ascontiguousarray(target_mask)),
    )


def assemble_latest_step(
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    rows: NDArray[np.int64],
    *,
    return_mean: float,
    return_scale: float,
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor]:
    """Assemble only the decision-time row for transparent/Ridge/MLP gates.

    These comparators never consume the historical sequence.  Loading an
    entire L40 window for their last-step design inflated I/O and memory by
    roughly forty times, so the aligned successor materializes this exact
    projection directly while preserving the same value/mask/label bytes.
    """

    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0 or rows.ndim != 2 or rows.shape[1] != ROW_WIDTH:
        raise ValueError("stage6_latest_step_rows_invalid")
    day_positions = rows[:, 0, None]
    symbol_positions = rows[:, 1, None]
    returns = shared.daily_returns[rows[:, 0], rows[:, 1]]
    if not np.isfinite(returns).all():
        raise ValueError("stage6_latest_step_returns_must_be_finite")
    standardized = (
        (returns.astype(np.float64) - return_mean) / return_scale
    ).astype(np.float32)
    values, availability = _channel_value_matrix(
        shared,
        spec.channels,
        day_positions,
        symbol_positions,
    )
    values = values[:, 0, :]
    availability = availability[:, 0, :]
    features = np.concatenate(
        (values, availability.astype(np.float32)), axis=1
    )
    targets = shared.labels[rows[:, 0], rows[:, 1], spec.horizon_index]
    target_finite = np.isfinite(targets)
    targets = np.where(target_finite, targets, 0.0).astype(np.float32)
    return (
        torch.from_numpy(np.ascontiguousarray(standardized)),
        torch.from_numpy(np.ascontiguousarray(features)),
        torch.from_numpy(np.ascontiguousarray(availability)),
        torch.from_numpy(np.ascontiguousarray(targets)),
        torch.from_numpy(np.ascontiguousarray(target_finite.astype(np.uint8))),
    )


def train_prefix_return_stats(
    shared: Stage6SharedTensor,
    rows: NDArray[np.int64],
) -> tuple[float, float]:
    """Return mean/scale from the last window step of training rows only."""

    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0:
        raise ValueError("stage6_train_rows_empty")
    values = shared.daily_returns[rows[:, 0], rows[:, 1]].astype(np.float64)
    mean = float(values.mean())
    scale = float(values.std())
    if not np.isfinite(mean) or not np.isfinite(scale) or scale < 1e-8:
        raise ValueError("stage6_train_return_stats_invalid")
    return mean, scale


def filter_rows_by_exit_year(
    rows: NDArray[np.int64],
    *,
    allowed_years: tuple[int, ...],
    decision_year: int | None = None,
    calendar: NDArray[np.datetime64] | None = None,
) -> NDArray[np.int64]:
    """Annual boundary discipline.

    - rows whose label exit year is not inside the allowed set are dropped
      (``exit_year == -1`` never passes);
    - when ``decision_year`` is given together with the shared calendar,
      the decision day of every surviving row is verified to actually fall
      in that calendar year, so rows misplaced under the wrong year key
      are rejected fail-closed.
    """

    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0:
        return rows
    if rows.ndim != 2 or rows.shape[1] != ROW_WIDTH:
        raise ValueError("stage6_rows_must_carry_exit_year")
    allowed = np.asarray(sorted(allowed_years), dtype=np.int64)
    keep = np.isin(rows[:, 2], allowed)
    if decision_year is not None:
        keep &= rows[:, 2] >= 0
        if calendar is not None:
            calendar_years = calendar.astype("datetime64[Y]").astype(int) + 1970
            day_years = calendar_years[rows[:, 0]]
            keep &= day_years == decision_year
    return rows[keep]


def common_support_identity(rows: NDArray[np.int64]) -> str:
    """Deterministic identity of a row set (the common support set)."""

    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0:
        raise ValueError("stage6_common_support_rows_empty")
    digest = hashlib.sha256(rows.astype(np.int64).tobytes()).hexdigest()
    return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# Training health snapshot (r1 repairs: n_k_eff dimension, four residuals)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stage6TrainingHealth:
    """Every fail-closed field reserved by training_health_contract.json."""

    first_epoch_losses: dict[str, float]
    last_epoch_losses: dict[str, float]
    loss_improvement_fraction: dict[str, float]
    minimum_loss_improvement_fraction: float
    active_module_gradient_norms: dict[str, float]
    shared_encoder_gradient_angles: dict[str, float]
    soft_operator_occupancy: dict[str, float]
    n_observations: int
    n_k_eff: dict[str, object]
    n_k_eff_over_d_squared: dict[str, object]
    operator_condition_numbers: dict[str, float]
    perturbed_score_rank_correlation: float | None
    perturbed_operator_assignment_agreement: float | None
    residual_energy: dict[str, float]
    predicted_to_true_residual_median_ratio: float | None
    predicted_to_true_residual_q95_ratio: float | None
    residual_tail_ratio_q95_over_median: float | None
    input_ood_fraction: float
    gate_mean: float | None
    deterministic_replay_max_abs_delta: float | None
    common_support_digest: str | None
    four_residual_common_support: dict[str, dict[str, float | None]]

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_id": STAGE6_HEALTH_SCHEMA_ID,
            "first_epoch_losses": dict(self.first_epoch_losses),
            "last_epoch_losses": dict(self.last_epoch_losses),
            "loss_improvement_fraction": dict(self.loss_improvement_fraction),
            "minimum_loss_improvement_fraction": self.minimum_loss_improvement_fraction,
            "active_module_gradient_norms": dict(self.active_module_gradient_norms),
            "shared_encoder_gradient_angles": dict(self.shared_encoder_gradient_angles),
            "soft_operator_occupancy": dict(self.soft_operator_occupancy),
            "n_observations": self.n_observations,
            "n_k_eff": dict(self.n_k_eff),
            "n_k_eff_over_d_squared": dict(self.n_k_eff_over_d_squared),
            "operator_condition_numbers": dict(self.operator_condition_numbers),
            "perturbed_score_rank_correlation": self.perturbed_score_rank_correlation,
            "perturbed_operator_assignment_agreement": self.perturbed_operator_assignment_agreement,
            "residual_energy": dict(self.residual_energy),
            "predicted_to_true_residual_median_ratio": self.predicted_to_true_residual_median_ratio,
            "predicted_to_true_residual_q95_ratio": self.predicted_to_true_residual_q95_ratio,
            "residual_tail_ratio_q95_over_median": self.residual_tail_ratio_q95_over_median,
            "input_ood_fraction": self.input_ood_fraction,
            "gate_mean": self.gate_mean,
            "deterministic_replay_max_abs_delta": self.deterministic_replay_max_abs_delta,
            "common_support_digest": self.common_support_digest,
            "four_residual_common_support": {
                mode: dict(values)
                for mode, values in self.four_residual_common_support.items()
            },
            "production_authority": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


def _gradient_norms(model: nn.Module) -> dict[str, float]:
    norms: dict[str, float] = {}
    for name, parameter in model.named_parameters():
        if parameter.grad is not None:
            norms[name] = float(torch.norm(parameter.grad.detach()).item())
    return norms


def _component_gradient_angles(
    model: nn.Module,
    returns: Tensor,
    features: Tensor,
    targets: Tensor | None,
    target_mask: Tensor | None,
    *,
    device: torch.device,
) -> dict[str, float]:
    """Cosine angle between the three loss components' gradients, computed
    on the parameter names both components touch (shared-encoder view)."""

    model.zero_grad(set_to_none=True)
    output = cast(
        ReakaPaperTrainingOutput,
        model.training_objective(
            returns.to(device),
            features.to(device),
            targets=None if targets is None else targets.to(device),
            target_mask=None if target_mask is None else target_mask.to(device),
        ),
    )
    vectors: dict[str, dict[str, Tensor]] = {}
    for name, loss in (
        ("rec", output.reconstruction_loss),
        ("koop", output.koopman_loss),
        ("diff", output.diffusion_loss),
    ):
        model.zero_grad(set_to_none=True)
        if loss.requires_grad and loss.grad_fn is not None:
            loss.backward(retain_graph=True)
            vectors[name] = {
                parameter_name: parameter.grad.detach().reshape(-1)
                for parameter_name, parameter in model.named_parameters()
                if parameter.grad is not None
            }
        else:
            vectors[name] = {}
        model.zero_grad(set_to_none=True)
    angles: dict[str, float] = {}
    for left, right in (("rec", "koop"), ("rec", "diff"), ("koop", "diff")):
        left_map = vectors.get(left, {})
        right_map = vectors.get(right, {})
        shared = sorted(set(left_map) & set(right_map))
        if not shared:
            angles[f"{left}_vs_{right}"] = math.nan
            continue
        left_vec = torch.cat([left_map[name] for name in shared])
        right_vec = torch.cat([right_map[name] for name in shared])
        angles[f"{left}_vs_{right}"] = float(
            torch.nn.functional.cosine_similarity(
                left_vec.unsqueeze(0), right_vec.unsqueeze(0)
            ).item()
        )
    return angles


def _operator_condition_numbers(model: Stage6ReakaModel) -> dict[str, float]:
    matrices = model.operators.detach().cpu().numpy().astype(np.float64)
    result: dict[str, float] = {}
    for index in range(matrices.shape[0]):
        result[str(index)] = float(np.linalg.cond(matrices[index]))
    return result


def _quantile(values: NDArray[np.float64], q: float) -> float:
    values = values[np.isfinite(values)]
    if values.size == 0:
        return math.nan
    return float(np.quantile(values, q))


def _spearman(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
    if left.size < 2:
        return math.nan
    left_rank = pd.Series(left).rank(method="average").to_numpy(dtype=np.float64)
    right_rank = pd.Series(right).rank(method="average").to_numpy(dtype=np.float64)
    if float(np.std(left_rank)) < 1e-12 or float(np.std(right_rank)) < 1e-12:
        return math.nan
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def residual_summary(tensor: Tensor | None) -> dict[str, float | None]:
    """Energy / median / q95 / tail ratio of one residual tensor, or all
    None when the residual mode is absent from the model."""

    if tensor is None:
        return {
            "energy": None,
            "median_abs": None,
            "q95_abs": None,
            "tail_ratio": None,
        }
    flat = np.abs(tensor.detach().cpu().numpy().astype(np.float64).ravel())
    median = _quantile(flat, 0.50)
    q95 = _quantile(flat, 0.95)
    return {
        "energy": float(np.mean(np.square(flat))),
        "median_abs": median,
        "q95_abs": q95,
        "tail_ratio": (q95 / median) if median and median > 0 else None,
    }


def four_residual_common_support_evidence(
    *,
    true_residual: Tensor,
    advanced_latent: Tensor,
    zero_residual: Tensor | None = None,
    mlp_residual: Tensor | None = None,
    diffusion_residual: Tensor | None = None,
) -> dict[str, dict[str, float | None]]:
    """Auxiliary-probe residual evidence on the common support batch.

    r4: the ``mlp`` and ``diffusion`` tensors come from auxiliary probe
    heads fitted on the training prefix, NOT from formal frozen model arms
    retrained on the same config.  This block is explicitly downgraded to
    probe material: it carries ``authority: probe_material_only`` and must
    never be promoted to four-residual cross-arm acceptance authority.  A
    real four-residual cross-arm certificate requires independently
    retrained frozen arms bound by arm/checkpoint/model/support digests,
    which is not what this function produces.
    """

    if zero_residual is None:
        zero_residual = torch.zeros_like(true_residual)
    return {
        "true": residual_summary(true_residual),
        "linear_zero": residual_summary(zero_residual),
        "mlp_probe": residual_summary(mlp_residual),
        "diffusion_probe": residual_summary(diffusion_residual),
        "_advanced_energy": {
            "energy": float(
                torch.mean(torch.square(advanced_latent.detach())).item()
            ),
            "median_abs": None,
            "q95_abs": None,
            "tail_ratio": None,
        },
        "_authority": {
            "energy": None,
            "median_abs": None,
            "q95_abs": None,
            "tail_ratio": None,
            "level": "probe_material_only_not_formal_cross_arm_acceptance_authority",
        },
    }


# ---------------------------------------------------------------------------
# r2: real cross-mode residual evidence probes on the common support batch
# ---------------------------------------------------------------------------


def _train_residual_evidence_probes(
    *,
    train_latent: Tensor,
    train_residual: Tensor,
    latent: Tensor,
    true_residual: Tensor,
    model_config: ReakaPaperConfig,
    device: torch.device,
    seed: int,
    probe_steps: int = 40,
) -> tuple[Tensor, Tensor]:
    """Train real MLP and diffusion residual probes on the TRAINING-prefix
    support and measure them on the held-out common validation support.

    The probes fit only on ``(train_latent, train_residual)`` drawn from
    the training prefix rows (never the validation batch), then emit
    residuals on ``(latent, true_residual)`` from the common validation
    batch.  This keeps the measured validation support out of probe
    training (r3 repair: validation data is never a probe training set).
    Both probes are deterministic (seeded) and use the paper's
    ``residual_mlp`` head and conditional denoiser with the frozen linear
    beta schedule; the diffusion estimate uses the paper's one-step x0
    formula at the highest step index.
    """

    from factor_lab.factor_rotation.reaka_paper_v1 import (  # noqa: E402
        _ConditionalResidualDenoiser,
    )

    train_latent = train_latent.detach()
    train_residual = train_residual.detach()
    latent = latent.detach()
    true_residual = true_residual.detach()
    latent_dim = latent.shape[-1]

    # MLP probe (paper residual_mlp head structure), trained on the prefix.
    torch.manual_seed(seed)
    mlp = nn.Sequential(
        nn.Linear(latent_dim, model_config.denoiser_hidden_dim),
        nn.SiLU(),
        nn.Linear(model_config.denoiser_hidden_dim, latent_dim),
    ).to(device)
    optimizer = torch.optim.Adam(mlp.parameters(), lr=model_config.learning_rate)
    for _ in range(probe_steps):
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.mse_loss(mlp(train_latent), train_residual)
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        mlp_residual = mlp(latent).detach()

    # Diffusion probe (paper conditional denoiser + frozen beta schedule),
    # trained on the prefix, measured on the validation support.
    torch.manual_seed(seed)
    denoiser = _ConditionalResidualDenoiser(config=model_config).to(device)
    optimizer = torch.optim.Adam(
        denoiser.parameters(), lr=model_config.learning_rate
    )
    _, _, alpha_bar = _diffusion_schedule_tensors(model_config, device)
    train_batch = train_latent.shape[0]
    for _ in range(probe_steps):
        steps = torch.randint(
            0,
            model_config.diffusion_steps,
            (train_batch,),
            device=device,
        )
        noise = torch.randn_like(train_residual)
        selected_bar = alpha_bar[steps].view(train_batch, 1, 1)
        noisy = (
            torch.sqrt(selected_bar) * train_residual
            + torch.sqrt(1.0 - selected_bar) * noise
        )
        optimizer.zero_grad(set_to_none=True)
        predicted = denoiser(noisy, steps, train_latent)
        loss = torch.nn.functional.mse_loss(predicted, noise)
        loss.backward()
        optimizer.step()
    # Deterministic x0 residual estimate on the validation support at the
    # highest step index.
    with torch.no_grad():
        batch = latent.shape[0]
        inference_steps = torch.full(
            (batch,),
            model_config.diffusion_steps - 1,
            dtype=torch.long,
            device=device,
        )
        inference_bar = alpha_bar[inference_steps].view(batch, 1, 1)
        fixed_noise = torch.randn_like(true_residual)
        noisy = (
            torch.sqrt(inference_bar) * true_residual
            + torch.sqrt(1.0 - inference_bar) * fixed_noise
        )
        predicted = denoiser(noisy, inference_steps, latent)
        diffusion_residual = (
            (noisy - torch.sqrt(1.0 - inference_bar) * predicted)
            / torch.sqrt(inference_bar)
        ).detach()
    return mlp_residual, diffusion_residual


def _diffusion_schedule_tensors(
    config: ReakaPaperConfig,
    device: torch.device,
) -> tuple[Tensor, Tensor, Tensor]:
    beta = torch.linspace(
        config.beta_start,
        config.beta_end,
        steps=config.diffusion_steps,
        dtype=torch.float32,
        device=device,
    )
    alpha = 1.0 - beta
    return beta, alpha, torch.cumprod(alpha, dim=0)


def compute_stage6_training_health(
    *,
    model: Stage6ReakaModel,
    train_batch: tuple[Tensor, Tensor, Tensor, Tensor, Tensor],
    validation_batch: tuple[Tensor, Tensor, Tensor, Tensor, Tensor],
    validation_rows: NDArray[np.int64],
    first_epoch_losses: dict[str, float],
    last_epoch_losses: dict[str, float],
    device: torch.device,
    train_channel_min: NDArray[np.float32],
    train_channel_max: NDArray[np.float32],
    policy: Stage6FreezePolicy | None = None,
    replay_max_abs_delta: float | None = None,
    perturbed_score_rank_correlation: float | None = None,
    perturbed_operator_assignment_agreement: float | None = None,
    mlp_residual: Tensor | None = None,
    diffusion_residual: Tensor | None = None,
) -> Stage6TrainingHealth:
    """Compute every fail-closed health field on the common support batch."""

    frozen = policy or Stage6FreezePolicy()
    frozen.validate()
    model.eval()
    train_returns, train_features, _, train_targets, train_target_mask = train_batch
    val_returns, val_features, _, val_targets, val_target_mask = validation_batch
    with torch.no_grad():
        val_output = cast(
            ReakaPaperTrainingOutput,
            model.training_objective(
                val_returns.to(device),
                val_features.to(device),
                targets=val_targets.to(device),
                target_mask=val_target_mask.to(device),
            ),
        )
        weights = val_output.selector_weights.detach().cpu().numpy().astype(np.float64)
        # Per-operator Kish effective transition support: for each operator k
        # the soft-assignment weights w_tk are sample weights, and
        # n_k_eff[k] = (sum_t w_tk)^2 / sum_t (w_tk)^2 is the effective
        # number of transition samples assigned to that operator.  The
        # per-operator values, their min/median and the total are reported
        # together with each value divided by d^2.
        weights_flat = weights.reshape(-1, weights.shape[-1])
        n_observations = int(weights_flat.shape[0])
        per_operator_sum = weights_flat.sum(axis=0)
        per_operator_sq = np.sum(weights_flat**2, axis=0)
        n_k_eff_per_operator: dict[str, float] = {}
        for index in range(weights.shape[-1]):
            numerator = float(per_operator_sum[index]) ** 2
            n_k_eff_per_operator[str(index)] = (
                numerator / float(per_operator_sq[index])
                if float(per_operator_sq[index]) > 0
                else 0.0
            )
        values = np.asarray(
            [n_k_eff_per_operator[str(i)] for i in range(weights.shape[-1])],
            dtype=np.float64,
        )
        latent_dim = int(model.config.latent_dim)
        d_squared = float(latent_dim**2)
        n_k_eff: dict[str, object] = {
            "per_operator": {str(i): float(values[i]) for i in range(values.size)},
            "min": float(values.min()) if values.size else 0.0,
            "median": float(np.median(values)) if values.size else 0.0,
            "total": float(values.sum()) if values.size else 0.0,
        }
        n_k_eff_over_d_squared: dict[str, object] = {
            "per_operator": {
                str(i): float(values[i] / d_squared) for i in range(values.size)
            },
            "min": float(values.min() / d_squared) if values.size else 0.0,
            "median": float(np.median(values) / d_squared) if values.size else 0.0,
            "total": float(values.sum() / d_squared) if values.size else 0.0,
        }
        occupancy = {
            str(index): float(per_operator_sum[index] / n_observations)
            for index in range(weights.shape[-1])
        }
        gate_mean = (
            float(val_output.gate.mean().item())
            if val_output.gate.numel() > 0
            else None
        )
        true_residual = val_output.true_residual
        estimated_residual = val_output.estimated_residual
        true_flat = np.abs(true_residual.detach().cpu().numpy().astype(np.float64).ravel())
        est_flat = np.abs(estimated_residual.detach().cpu().numpy().astype(np.float64).ravel())
        true_median = _quantile(true_flat, 0.50)
        true_q95 = _quantile(true_flat, 0.95)
        est_median = _quantile(est_flat, 0.50)
        est_q95 = _quantile(est_flat, 0.95)
        true_energy = float(np.mean(np.square(true_flat)))
        est_energy = float(np.mean(np.square(est_flat)))
        advanced_energy = float(
            torch.mean(torch.square(val_output.advanced_latent.detach())).item()
        )
        median_ratio = (est_median / true_median) if true_median > 0 else None
        q95_ratio = (est_q95 / true_q95) if true_q95 > 0 else None
        tail_ratio = (true_q95 / true_median) if true_median > 0 else None
        four_residual = four_residual_common_support_evidence(
            true_residual=true_residual,
            advanced_latent=val_output.advanced_latent,
            mlp_residual=mlp_residual,
            diffusion_residual=diffusion_residual,
        )

    model.train()
    model.zero_grad(set_to_none=True)
    fresh_output = cast(
        ReakaPaperTrainingOutput,
        model.training_objective(
            train_returns.to(device),
            train_features.to(device),
            targets=train_targets.to(device),
            target_mask=train_target_mask.to(device),
        ),
    )
    fresh_output.total_loss.backward()
    gradient_norms = _gradient_norms(model)
    model.zero_grad(set_to_none=True)
    angles = _component_gradient_angles(
        model,
        train_returns,
        train_features,
        train_targets,
        train_target_mask,
        device=device,
    )
    condition_numbers = _operator_condition_numbers(model)

    val_values = val_features.detach().cpu().numpy().astype(np.float64)
    val_mask = validation_batch[2].detach().cpu().numpy().astype(bool)
    # OOD is measured on the value half of the mask-augmented feature axis;
    # the mask half is 0/1 by construction.
    value_width = int(val_mask.shape[2])
    value_range_min = train_channel_min[:value_width]
    value_range_max = train_channel_max[:value_width]
    in_range = (
        (val_values[:, :, :value_width] >= value_range_min)
        & (val_values[:, :, :value_width] <= value_range_max)
    )
    ood_fraction = (
        float((~in_range & val_mask).mean()) if val_mask.any() else 0.0
    )

    improvement: dict[str, float] = {}
    for key in ("total_loss", "reconstruction_loss", "koopman_loss", "diffusion_loss"):
        first = first_epoch_losses.get(key, math.nan)
        last = last_epoch_losses.get(key, math.nan)
        improvement[key] = (
            (first - last) / first
            if first and math.isfinite(first) and first > 0
            else math.nan
        )

    return Stage6TrainingHealth(
        first_epoch_losses=dict(first_epoch_losses),
        last_epoch_losses=dict(last_epoch_losses),
        loss_improvement_fraction=improvement,
        minimum_loss_improvement_fraction=0.05,
        active_module_gradient_norms=gradient_norms,
        shared_encoder_gradient_angles=angles,
        soft_operator_occupancy=occupancy,
        n_observations=n_observations,
        n_k_eff=n_k_eff,
        n_k_eff_over_d_squared=n_k_eff_over_d_squared,
        operator_condition_numbers=condition_numbers,
        perturbed_score_rank_correlation=perturbed_score_rank_correlation,
        perturbed_operator_assignment_agreement=perturbed_operator_assignment_agreement,
        residual_energy={
            "true": true_energy,
            "estimated": est_energy,
            "advanced": advanced_energy,
            "ratio_estimated_over_true": (est_energy / true_energy) if true_energy > 0 else math.nan,
            "ratio_true_over_advanced": (true_energy / advanced_energy) if advanced_energy > 0 else math.nan,
        },
        predicted_to_true_residual_median_ratio=median_ratio,
        predicted_to_true_residual_q95_ratio=q95_ratio,
        residual_tail_ratio_q95_over_median=tail_ratio,
        input_ood_fraction=ood_fraction,
        gate_mean=gate_mean,
        deterministic_replay_max_abs_delta=replay_max_abs_delta,
        common_support_digest=common_support_identity(validation_rows),
        four_residual_common_support=four_residual,
    )


# ---------------------------------------------------------------------------
# Post-training hard health certificate (r2: fail-closed adjudication)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stage6HealthCertificate:
    """Fail-closed adjudication of one fit's health snapshot against the
    frozen ``training_health_contract.json`` hard sanity limits.

    Missing evidence blocks (``value is None`` or NaN) instead of passing;
    ``economic_improvement_cannot_override_health_failure`` is structural.
    """

    fit: str
    status: str
    per_gate: dict[str, dict[str, object]]
    blocker_count: int
    production_authority: bool = False

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_id": "factorlab.reaka_stage6_health_certificate@2.0",
            "fit": self.fit,
            "status": self.status,
            "per_gate": {
                gate: dict(values) for gate, values in self.per_gate.items()
            },
            "blocker_count": self.blocker_count,
            "production_authority": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


def _gate_verdict(
    *,
    value: float | None,
    limit: float,
    kind: str,
    detail: object = None,
) -> dict[str, object]:
    """One hard-gate verdict; NaN/None blocks fail-closed."""

    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return {
            "value": value,
            "limit": limit,
            "kind": kind,
            "pass": False,
            "blocked": True,
            "reason": "evidence_missing",
            "detail": detail,
        }
    passed: bool
    if kind == "max":
        passed = float(value) <= limit
    elif kind == "min":
        passed = float(value) >= limit
    elif kind == "inclusive":
        passed = float(limit) <= float(value) <= float(detail) if detail is not None else False
    elif kind == "positive":
        passed = float(value) > 0
    else:
        raise ValueError(f"stage6_gate_kind_unknown:{kind}")
    return {
        "value": value,
        "limit": limit,
        "kind": kind,
        "pass": passed,
        "blocked": not passed,
        "reason": None if passed else f"hard_limit_{kind}_violated",
        "detail": detail,
    }


def evaluate_stage6_health_certificate(
    *,
    fit_label: str,
    health: Stage6TrainingHealth,
    operator_count: int,
    residual_mode: str = "diffusion",
    require_four_residual: bool = True,
    formal_cross_arm_certificate: dict[str, object] | None = None,
    expected_comparison_identity: dict[str, object] | None = None,
) -> Stage6HealthCertificate:
    """Adjudicate a health snapshot against the frozen hard sanity limits.

    Gate applicability is declared per arm type (r3 repair): a no-residual
    arm (``residual_mode == "none"``) has an estimated residual of zero by
    construction, so the predicted/true residual ratio gates are reported
    as ``not_applicable_no_residual_arm`` instead of being mechanically
    killed.  The residual ratio-to-advanced gate, the gate-mean gate, and
    the occupancy/condition/perturbation gates stay applicable to every
    neural arm; the four-residual evidence gate stays fail-closed unless
    ``require_four_residual`` is disabled for the parameter-free common
    root.

    MSE-trained MLP residuals estimate E[R | history], whose amplitude may
    correctly be much smaller than R when unpredictable noise dominates.
    Their median/q95 amplitude ratios are diagnostics, not distribution
    matching gates.  The legacy health snapshot has no historical-only
    prediction MSE on the same support as a zero-residual control, so MLP
    conditional-mean validation remains explicitly blocked pending that
    evidence.  Diffusion retains its scale gates, but those legacy
    teacher-forced measurements do not replace historical-only conditional
    distribution evidence in the downstream formal certificate.

    A formal cross-arm consumer must supply the full current comparison
    identity from its own frozen task/config/support.  The artifact cannot
    supply its own expected identity.  Its operator count and support are
    additionally checked against this call's operator_count and health.

    The frozen limits (``training_health_contract.json``):

    - maximum_operator_occupancy_exclusive_for_K_gt_1: 0.99
    - gate_mean_inclusive: [0.05, 0.95]
    - maximum_residual_to_advanced_energy_ratio: 2.0
    - predicted_to_true_residual_median_energy_ratio: [0.5, 2.0]
    - predicted_to_true_residual_q95_ratio: [0.5, 2.0]
    - maximum_input_ood_fraction: 0.05
    - minimum_loss_improvement_fraction: 0.05
    - maximum_operator_condition_number: 1e6
    - minimum_perturbed_score_rank_correlation: 0.95
    - minimum_perturbed_operator_assignment_agreement: 0.80
    - minimum_cpu_gpu_score_correlation: 0.999 (preflight-level; recorded)
    - minimum_cpu_gpu_top20_member_overlap: 0.98 (preflight-level; recorded)
    """

    gates: dict[str, dict[str, object]] = {}
    occupancy = health.soft_operator_occupancy
    if operator_count > 1:
        gates["operator_occupancy_exclusive"] = _gate_verdict(
            value=max(occupancy.values()) if occupancy else None,
            limit=0.99,
            kind="max",
            detail=occupancy,
        )
    else:
        gates["operator_occupancy_exclusive"] = {
            "value": None,
            "limit": 0.99,
            "kind": "max",
            "pass": True,
            "blocked": False,
            "reason": "not_applicable_K_eq_1",
            "detail": occupancy,
        }
    if health.gate_mean is not None:
        gates["gate_mean_inclusive"] = _gate_verdict(
            value=health.gate_mean,
            limit=0.05,
            kind="inclusive",
            detail=0.95,
        )
    else:
        gates["gate_mean_inclusive"] = {
            "value": None,
            "limit": 0.05,
            "kind": "inclusive",
            "pass": False,
            "blocked": True,
            "reason": "evidence_missing",
            "detail": 0.95,
        }
    residual = health.residual_energy
    gates["residual_to_advanced_energy_ratio"] = _gate_verdict(
        value=residual.get("ratio_true_over_advanced"),
        limit=2.0,
        kind="max",
        detail=residual,
    )
    if residual_mode == "none":
        gates["predicted_to_true_residual_median_ratio"] = {
            "value": None,
            "limit": 0.5,
            "kind": "inclusive",
            "pass": True,
            "blocked": False,
            "reason": "not_applicable_no_residual_arm",
            "detail": 2.0,
        }
        gates["predicted_to_true_residual_q95_ratio"] = {
            "value": None,
            "limit": 0.5,
            "kind": "inclusive",
            "pass": True,
            "blocked": False,
            "reason": "not_applicable_no_residual_arm",
            "detail": 2.0,
        }
    elif residual_mode == "mlp":
        for name, value in (
            ("predicted_to_true_residual_median_ratio", health.predicted_to_true_residual_median_ratio),
            ("predicted_to_true_residual_q95_ratio", health.predicted_to_true_residual_q95_ratio),
        ):
            gates[name] = {
                "value": value,
                "limit": None,
                "kind": "diagnostic",
                "pass": True,
                "blocked": False,
                "reason": "not_applicable_conditional_mean",
                "detail": {"estimand": "conditional_mean_of_residual", "amplitude_matching_required": False},
            }
        gates["conditional_mean_validation"] = {
            "value": None,
            "limit": "same_support_history_only_mean_error_evidence",
            "kind": "required_evidence",
            "pass": False,
            "blocked": True,
            "reason": "conditional_mean_validation_missing",
            "detail": {
                "estimand": "conditional_mean_of_residual",
                "available_statistics": "marginal_energies_and_quantiles_do_not_identify_prediction_MSE",
                "required_evidence": [
                    "history_only_argmax_forecast_residual_prediction",
                    "same_checkpoint_hard_selector_reference_residual",
                    "same_support_prediction_MSE_and_zero_residual_MSE",
                    "frozen_mean_error_comparison_rule_and_uncertainty",
                ],
            },
        }
    else:
        gates["predicted_to_true_residual_median_ratio"] = _gate_verdict(
            value=health.predicted_to_true_residual_median_ratio,
            limit=0.5,
            kind="inclusive",
            detail=2.0,
        )
        gates["predicted_to_true_residual_q95_ratio"] = _gate_verdict(
            value=health.predicted_to_true_residual_q95_ratio,
            limit=0.5,
            kind="inclusive",
            detail=2.0,
        )
        for name in ("predicted_to_true_residual_median_ratio", "predicted_to_true_residual_q95_ratio"):
            gates[name].update({
                "estimand": "conditional_residual_distribution",
                "measurement_source": "legacy_teacher_forced_training_objective",
                "history_only_distribution_validation_required": True,
            })
    gates["input_ood_fraction"] = _gate_verdict(
        value=health.input_ood_fraction,
        limit=0.05,
        kind="max",
    )
    gates["loss_improvement_fraction"] = _gate_verdict(
        value=health.loss_improvement_fraction.get("total_loss"),
        limit=0.05,
        kind="min",
        detail=health.loss_improvement_fraction,
    )
    condition_numbers = health.operator_condition_numbers
    gates["operator_condition_number"] = _gate_verdict(
        value=max(condition_numbers.values()) if condition_numbers else None,
        limit=1000000.0,
        kind="max",
        detail=condition_numbers,
    )
    gates["perturbed_score_rank_correlation"] = _gate_verdict(
        value=health.perturbed_score_rank_correlation,
        limit=0.95,
        kind="min",
    )
    gates["perturbed_operator_assignment_agreement"] = _gate_verdict(
        value=health.perturbed_operator_assignment_agreement,
        limit=0.80,
        kind="min",
    )
    four = health.four_residual_common_support
    mlp_probe = four.get("mlp_probe", {})
    diffusion_probe = four.get("diffusion_probe", {})
    # The probe block is auxiliary material only.  A real four-residual
    # cross-arm certificate requires independently retrained frozen arms
    # bound by arm/checkpoint/model/support digests; the probe values are
    # reported as diagnostic material and do not grant four-residual
    # acceptance authority, so they never block the certificate by
    # themselves.
    gates["four_residual_probe_values_present"] = {
        "value": None,
        "limit": None,
        "kind": "positive",
        "pass": bool(
            mlp_probe.get("energy") is not None
            and diffusion_probe.get("energy") is not None
        ),
        "blocked": False,
        "reason": "probe_material_only_not_cross_arm_acceptance_authority",
        "detail": {
            "mlp_probe_energy": mlp_probe.get("energy"),
            "diffusion_probe_energy": diffusion_probe.get("energy"),
        },
    }
    if require_four_residual:
        current_identity_present = isinstance(expected_comparison_identity, dict) and health.common_support_digest is not None
        current_identity_matches = bool(
            current_identity_present
            and expected_comparison_identity.get("operator_count") == operator_count
            and expected_comparison_identity.get("support_digest") == health.common_support_digest
        )
        formal_passed = current_identity_matches and formal_cross_arm_residual_certificate_valid(
            formal_cross_arm_certificate,
            expected_comparison_identity=expected_comparison_identity,
        )
        formal_reason = (
            None if formal_passed else (
                "formal_cross_arm_current_identity_missing" if not current_identity_present else
                "formal_cross_arm_current_identity_mismatch" if not current_identity_matches else
                "formal_cross_arm_certificate_missing_blocked_or_identity_mismatch"
            )
        )
        gates["formal_cross_arm_residual_certificate"] = {
            "value": (
                formal_cross_arm_certificate.get("canonical_digest")
                if isinstance(formal_cross_arm_certificate, dict)
                else None
            ),
            "limit": "passed_with_formal_cross_arm_acceptance_authority",
            "kind": "required_evidence",
            "pass": formal_passed,
            "blocked": not formal_passed,
            "reason": formal_reason,
            "detail": formal_cross_arm_certificate,
            "expected_comparison_identity": expected_comparison_identity,
        }
    else:
        gates["formal_cross_arm_residual_certificate"] = {
            "value": None,
            "limit": None,
            "kind": "required_evidence",
            "pass": True,
            "blocked": False,
            "reason": "not_applicable_individual_arm_health_stage",
            "detail": None,
        }
    # n_k_eff capacity diagnostic: comfortable needs every operator's
    # effective support / d^2 >= 5; this is reported, not a frozen
    # permanent threshold (capacity_diagnostic.permanent_threshold_claimed
    # is false), so it never blocks by itself.
    n_k_eff = health.n_k_eff
    gates["n_k_eff_capacity_diagnostic"] = {
        "value": n_k_eff.get("total"),
        "limit": None,
        "kind": "positive",
        "pass": True,
        "blocked": False,
        "reason": "diagnostic_only_not_a_permanent_threshold",
        "detail": n_k_eff,
    }
    blockers = [
        name for name, verdict in gates.items() if bool(verdict.get("blocked"))
    ]
    return Stage6HealthCertificate(
        fit=fit_label,
        status="blocked" if blockers else "passed",
        per_gate=gates,
        blocker_count=len(blockers),
    )


def evaluate_stage6r_integrity_certificate(
    *,
    fit_label: str,
    health: Stage6TrainingHealth,
    validation_learning_curve: tuple[dict[str, object], ...],
    model_parameters_finite: bool,
) -> dict[str, object]:
    """Stage 6R execution gate limited to numerical/data integrity.

    Predictive quality, the legacy five-percent random-initialization
    improvement, OOD, perturbation sensitivity, gate occupancy and operator
    usage remain visible diagnostics.  They cannot suppress scores or stop
    unrelated registered fits.  This deliberately leaves the historical
    ``evaluate_stage6_health_certificate`` semantics unchanged.
    """

    curve_values = [
        float(value)
        for point in validation_learning_curve
        for key, value in point.items()
        if key != "coverage_cycle" and isinstance(value, int | float)
    ]
    gradient_values = list(health.active_module_gradient_norms.values())
    condition_values = list(health.operator_condition_numbers.values())
    replay_delta = health.deterministic_replay_max_abs_delta
    gates: dict[str, dict[str, object]] = {
        "finite_validation_learning_curve": {
            "pass": bool(curve_values) and all(math.isfinite(v) for v in curve_values),
            "blocked": not (
                bool(curve_values) and all(math.isfinite(v) for v in curve_values)
            ),
            "detail": {"point_count": len(validation_learning_curve)},
        },
        "finite_model_parameters": {
            "pass": bool(model_parameters_finite),
            "blocked": not bool(model_parameters_finite),
            "detail": None,
        },
        "active_finite_gradient_present": {
            "pass": bool(gradient_values)
            and all(math.isfinite(v) for v in gradient_values)
            and any(v > 0.0 for v in gradient_values),
            "blocked": not (
                bool(gradient_values)
                and all(math.isfinite(v) for v in gradient_values)
                and any(v > 0.0 for v in gradient_values)
            ),
            "detail": {"active_gradient_count": len(gradient_values)},
        },
        "same_seed_deterministic_replay": {
            "pass": replay_delta is not None
            and math.isfinite(float(replay_delta))
            and float(replay_delta) <= 1e-7,
            "blocked": not (
                replay_delta is not None
                and math.isfinite(float(replay_delta))
                and float(replay_delta) <= 1e-7
            ),
            "detail": {"max_abs_delta": replay_delta, "limit": 1e-7},
        },
        "finite_operator_condition_measurement": {
            "pass": bool(condition_values)
            and all(math.isfinite(v) for v in condition_values),
            "blocked": not (
                bool(condition_values)
                and all(math.isfinite(v) for v in condition_values)
            ),
            "detail": dict(health.operator_condition_numbers),
        },
        "common_support_bound": {
            "pass": bool(health.common_support_digest),
            "blocked": not bool(health.common_support_digest),
            "detail": health.common_support_digest,
        },
        "random_initialization_loss_improvement": {
            "pass": True,
            "blocked": False,
            "detail": {
                "role": "diagnostic_only_not_quality_order_preserving",
                "value": health.loss_improvement_fraction.get("total_loss"),
                "legacy_limit": health.minimum_loss_improvement_fraction,
            },
        },
    }
    blockers = [name for name, verdict in gates.items() if verdict["blocked"]]
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6r_integrity_certificate@1.0",
        "fit": fit_label,
        "status": "blocked" if blockers else "passed",
        "per_gate": gates,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "scientific_role": "execution_integrity_only",
        "fresh_oos": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stage6FitConfig:
    """One frozen arm x task x capacity x seed fit inside one year."""

    arm_id: str
    task_id: str
    sequence_length: int
    latent_dim: int
    operator_count: int
    seed: int
    train_years: tuple[int, ...]
    validation_year: int
    device: str = "cpu"
    policy: Stage6FreezePolicy = field(default_factory=Stage6FreezePolicy)

    def validate(self) -> None:
        if self.arm_id not in MODEL_ARM_IDS:
            raise ValueError(f"stage6_arm_unknown:{self.arm_id}")
        if self.latent_dim not in LATENT_DIMENSIONS:
            raise ValueError(f"stage6_latent_dimension_not_frozen:{self.latent_dim}")
        if self.operator_count not in OPERATOR_COUNTS:
            raise ValueError(f"stage6_operator_count_not_frozen:{self.operator_count}")
        if self.seed not in SEEDS:
            raise ValueError(f"stage6_seed_not_frozen:{self.seed}")
        if not self.train_years or min(self.train_years) < YEAR_MIN or max(self.train_years) > YEAR_MAX:
            raise ValueError("stage6_train_years_out_of_range")
        if self.validation_year != max(self.train_years) + 1:
            raise ValueError("stage6_validation_year_must_follow_train_years")
        if self.validation_year < YEAR_MIN or self.validation_year > YEAR_MAX:
            raise ValueError("stage6_validation_year_out_of_range")
        self.policy.validate()

    def as_dict(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = asdict(self)
        payload["policy"] = self.policy.as_dict()
        payload["production_authority"] = False
        return payload


@dataclass(frozen=True, slots=True)
class Stage6FitResult:
    """A completed fit with every health field attached (no return ranking)."""

    config: Stage6FitConfig
    first_epoch_losses: dict[str, float]
    last_epoch_losses: dict[str, float]
    epoch_count: int
    stopped_early: bool
    health: Stage6TrainingHealth
    validation_score_rows: NDArray[np.int64]
    validation_scores: NDArray[np.float64]
    operator_ids: NDArray[np.int64]
    diagnostic_rows: NDArray[np.int64]
    diagnostic_scores: NDArray[np.float64]
    diagnostic_cross_year_count: int
    train_row_count: int
    validation_row_count: int
    diagnostic_row_count: int
    peak_rss_mib: float
    elapsed_seconds: float
    model_state_digest: str
    checkpoint_path: str | None
    health_certificate: dict[str, object] | None = None
    formal_arm_residual_evidence: dict[str, object] | None = None
    loss_reference_semantics: str = "first_training_epoch_vs_last_training_epoch"
    validation_learning_curve: tuple[dict[str, object], ...] = ()
    diagnostic_health_certificate: dict[str, object] | None = None
    training_order_policy: str = "row_permutation"
    precision_policy: str = "float32"

    def validate_artifact_schema(self) -> None:
        if self.validation_score_rows.ndim != 2 or self.validation_score_rows.shape[1] != ROW_WIDTH:
            raise ValueError("stage6_result_validation_rows_shape_invalid")
        if self.diagnostic_rows.ndim != 2 or self.diagnostic_rows.shape[1] != ROW_WIDTH:
            raise ValueError("stage6_result_diagnostic_rows_shape_invalid")
        if self.validation_score_rows.shape[0] != self.validation_scores.size:
            raise ValueError("stage6_result_validation_row_score_count_mismatch")
        if self.diagnostic_rows.shape[0] != self.diagnostic_scores.size:
            raise ValueError("stage6_result_diagnostic_row_score_count_mismatch")
        if self.validation_row_count != self.validation_score_rows.shape[0]:
            raise ValueError("stage6_result_validation_declared_count_mismatch")
        if self.diagnostic_row_count != self.diagnostic_rows.shape[0]:
            raise ValueError("stage6_result_diagnostic_declared_count_mismatch")
        certificate_status = (
            str(self.health_certificate.get("status"))
            if isinstance(self.health_certificate, dict)
            else None
        )
        if certificate_status == "blocked":
            if any(
                value != 0
                for value in (
                    self.validation_score_rows.size,
                    self.validation_scores.size,
                    self.operator_ids.size,
                    self.diagnostic_rows.size,
                    self.diagnostic_scores.size,
                    self.validation_row_count,
                    self.diagnostic_row_count,
                )
            ):
                raise ValueError("stage6_blocked_result_contains_usable_scores")
            if self.checkpoint_path is not None or self.formal_arm_residual_evidence is not None:
                raise ValueError("stage6_blocked_result_contains_usable_model_artifact")

    def as_dict(self) -> dict[str, object]:
        self.validate_artifact_schema()
        payload: dict[str, object] = {
            "schema_id": STAGE6_CERTIFICATE_SCHEMA_ID,
            "config": self.config.as_dict(),
            "first_epoch_losses": dict(self.first_epoch_losses),
            "last_epoch_losses": dict(self.last_epoch_losses),
            "epoch_count": self.epoch_count,
            "coverage_cycles_completed": self.epoch_count,
            "training_row_visit_count": self.train_row_count * self.epoch_count,
            "loss_reference_semantics": self.loss_reference_semantics,
            "validation_learning_curve": [
                dict(point) for point in self.validation_learning_curve
            ],
            "training_order_policy": self.training_order_policy,
            "precision_policy": self.precision_policy,
            "stopped_early": self.stopped_early,
            "health": self.health.as_dict(),
            "health_certificate": self.health_certificate,
            "diagnostic_health_certificate": self.diagnostic_health_certificate,
            "formal_arm_residual_evidence": self.formal_arm_residual_evidence,
            "validation_score_row_count": int(self.validation_score_rows.size // ROW_WIDTH),
            "diagnostic_score_row_count": int(self.diagnostic_rows.size // ROW_WIDTH),
            "diagnostic_cross_year_label_count": self.diagnostic_cross_year_count,
            "operator_id_count": int(self.operator_ids.size),
            "train_row_count": self.train_row_count,
            "validation_row_count": self.validation_row_count,
            "diagnostic_row_count": self.diagnostic_row_count,
            "peak_rss_mib": self.peak_rss_mib,
            "elapsed_seconds": self.elapsed_seconds,
            "model_state_digest": self.model_state_digest,
            "checkpoint_path": self.checkpoint_path,
            "common_support_contract": {
                "dates_symbols_and_costs_shared_through_immutable_tensor": True,
                "common_support_digest": self.health.common_support_digest,
                "label_convention": "t_plus_1_open_entry_h_day_close_exit_stage2_sealed",
                "portfolio_config": {
                    "product": "active_long_full_investment",
                    "portfolio_size_candidates": list(self.config.policy.portfolio_size_candidates),
                    "buy_cost_bps": self.config.policy.buy_cost_bps,
                    "sell_cost_bps": self.config.policy.sell_cost_bps,
                    "slippage_stress_multipliers": list(self.config.policy.slippage_stress_multipliers),
                    "capital_primary_cny": self.config.policy.capital_primary_cny,
                },
            },
            "production_authority": False,
            "fresh_oos": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _model_state_digest(model: nn.Module) -> str:
    parts = [
        parameter.detach().cpu().numpy().round(10).tobytes()
        for parameter in model.parameters()
    ]
    return "sha256:" + hashlib.sha256(b"".join(parts)).hexdigest()


def _save_checkpoint(
    *,
    model: nn.Module,
    config: Stage6FitConfig,
    directory: Path,
) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"state_dict": {key: value.cpu() for key, value in model.state_dict().items()}},
        directory / "model_state.pt",
    )
    (directory / "fit_config.json").write_text(
        json.dumps(config.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(directory / "model_state.pt")


def score_stage6_checkpoint(
    *,
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    rows_by_year: dict[int, NDArray[np.int64]],
    config: Stage6FitConfig,
    checkpoint_path: Path,
    score_year: int,
) -> tuple[NDArray[np.int64], NDArray[np.float64], NDArray[np.int64]]:
    """Replay one frozen checkpoint on exactly one natural year.

    Training-prefix normalization is reconstructed from the fit config.  The
    checkpoint is never updated.  Diffusion inference uses fixed per-batch
    noise derived from the frozen seed, so replay does not depend on ambient
    RNG state and the calendar year is not a model feature.
    """

    config.validate()
    if not YEAR_MIN <= score_year <= YEAR_MAX:
        raise ValueError(f"stage6_checkpoint_score_year_out_of_range:{score_year}")
    if spec.task_id != config.task_id:
        raise ValueError("stage6_checkpoint_task_id_mismatch")
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"stage6_checkpoint_missing:{checkpoint_path}")
    train_parts: list[NDArray[np.int64]] = []
    for year in config.train_years:
        raw = np.asarray(
            rows_by_year.get(year, np.empty((0, ROW_WIDTH), dtype=np.int64))
        )
        kept = filter_rows_by_exit_year(
            raw,
            allowed_years=config.train_years,
            decision_year=year,
            calendar=shared.calendar,
        )
        if kept.size:
            train_parts.append(kept)
    if not train_parts:
        raise ValueError("stage6_checkpoint_train_rows_missing")
    train_rows = np.concatenate(train_parts, axis=0)
    raw_score_rows = np.asarray(
        rows_by_year.get(score_year, np.empty((0, ROW_WIDTH), dtype=np.int64))
    )
    score_rows = filter_rows_by_exit_year(
        raw_score_rows,
        allowed_years=(score_year,),
        decision_year=score_year,
        calendar=shared.calendar,
    )
    if score_rows.size == 0:
        raise ValueError(f"stage6_checkpoint_score_rows_missing:{score_year}")
    return_mean, return_scale = train_prefix_return_stats(shared, train_rows)
    device = torch.device(config.device)
    _seed_everything(config.seed)
    model = build_stage6_reaka_model(
        feature_dim=spec.model_feature_dim,
        arm_id=config.arm_id,
        policy=config.policy,
        sequence_length=config.sequence_length,
        latent_dim=config.latent_dim,
        operator_count=config.operator_count,
    ).to(device)
    checkpoint = torch.load(
        checkpoint_path,
        map_location=device,
        weights_only=True,
    )
    state_dict = checkpoint.get("state_dict")
    if not isinstance(state_dict, dict):
        raise ValueError("stage6_checkpoint_state_dict_missing")
    model.load_state_dict(state_dict, strict=True)
    scores = np.zeros(score_rows.shape[0], dtype=np.float64)
    operator_ids = np.zeros(score_rows.shape[0], dtype=np.int64)
    diffusion = stage6_arm_spec(config.arm_id).residual_mode == "diffusion"
    model.eval()
    with torch.no_grad():
        for start in range(0, score_rows.shape[0], config.policy.batch_size):
            part = score_rows[start : start + config.policy.batch_size]
            returns, features, _, _, _ = assemble_windows(
                shared,
                spec,
                part,
                config.sequence_length,
                return_mean=return_mean,
                return_scale=return_scale,
            )
            returns = returns.to(device)
            features = features.to(device)
            if diffusion:
                generator = torch.Generator(device=device).manual_seed(
                    config.seed + start
                )
                initial_noise = torch.randn(
                    returns.shape[0],
                    returns.shape[1],
                    config.latent_dim,
                    generator=generator,
                    device=device,
                )
                reverse_noises = tuple(
                    torch.randn(
                        returns.shape[0],
                        returns.shape[1],
                        config.latent_dim,
                        generator=torch.Generator(device=device).manual_seed(
                            config.seed + 1000 + step + start
                        ),
                        device=device,
                    )
                    for step in range(config.policy.diffusion_steps)
                )
            else:
                initial_noise = None
                reverse_noises = None
            forecast = model.forecast(
                returns,
                features,
                initial_noise=initial_noise,
                reverse_noises=reverse_noises,
            )
            stop = start + part.shape[0]
            scores[start:stop] = (
                forecast.scores.detach().cpu().numpy().astype(np.float64)
            )
            operator_ids[start:stop] = (
                forecast.operator_ids[:, -1]
                .detach()
                .cpu()
                .numpy()
                .astype(np.int64)
            )
    return score_rows, scores, operator_ids


def _fit_transparent_arm(
    *,
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    rows_by_year: dict[int, NDArray[np.int64]],
    config: Stage6FitConfig,
    diagnostic_year: int,
) -> Stage6FitResult:
    """Common-root deterministic scoring (no neural carrier, no returns)."""

    validation_rows = np.asarray(
        rows_by_year.get(config.validation_year, np.empty((0, ROW_WIDTH), dtype=np.int64))
    )
    validation_rows = filter_rows_by_exit_year(
        validation_rows,
        allowed_years=(config.validation_year,),
        decision_year=config.validation_year,
        calendar=shared.calendar,
    )
    diagnostic_all = np.asarray(
        rows_by_year.get(diagnostic_year, np.empty((0, ROW_WIDTH), dtype=np.int64))
    )
    cross_year = int(
        (diagnostic_all[:, 2] != diagnostic_year).sum()
        if diagnostic_all.size
        else 0
    )
    diagnostic_rows = filter_rows_by_exit_year(
        diagnostic_all,
        allowed_years=(diagnostic_year,),
        decision_year=diagnostic_year,
        calendar=shared.calendar,
    )

    def _score(rows: NDArray[np.int64]) -> NDArray[np.float64]:
        scores = np.zeros(rows.shape[0], dtype=np.float64)
        for row_start in range(0, rows.shape[0], 8192):
            stop = min(row_start + 8192, rows.shape[0])
            part = rows[row_start:stop]
            channel_values = np.empty(
                (part.shape[0], len(spec.channels)), dtype=np.float32
            )
            channel_available = np.empty_like(channel_values, dtype=np.uint8)
            for position, channel in enumerate(spec.channels):
                factor = shared.base_rank_centered[
                    part[:, 0], part[:, 1], channel.factor_index
                ]
                available = shared.base_available[
                    part[:, 0], part[:, 1], channel.factor_index
                ]
                channel_values[:, position] = factor
                channel_available[:, position] = available
                if channel.pathway_id == "spatial_specialist" and channel.descriptor_index >= 0:
                    bins = shared.descriptor_bins[
                        part[:, 0], part[:, 1], channel.descriptor_index
                    ]
                    in_bins = np.isin(
                        bins, np.asarray(channel.quantile_bins, dtype=np.uint8)
                    )
                    channel_values[:, position] *= in_bins.astype(np.float32)
                    channel_available[:, position] &= in_bins.astype(np.uint8)
                if channel.pathway_id == "self_lagged_effectiveness_following" and channel.follow_ticket_index >= 0:
                    weights = shared.follow_weights[
                        part[:, 0], channel.follow_ticket_index
                    ]
                    finite = np.isfinite(weights)
                    channel_values[:, position] *= np.where(
                        finite, weights, 0.0
                    ).astype(np.float32)
                    channel_available[:, position] &= finite.astype(np.uint8)
                channel_values[:, position] *= np.float32(
                    channel.mechanism_vote_weight
                )
            scores[row_start:stop] = transparent_rank_scores(
                values=channel_values,
                availability=channel_available,
            )
        return scores

    result = Stage6FitResult(
        config=config,
        first_epoch_losses={},
        last_epoch_losses={},
        epoch_count=0,
        stopped_early=False,
        health=Stage6TrainingHealth(
            first_epoch_losses={},
            last_epoch_losses={},
            loss_improvement_fraction={},
            minimum_loss_improvement_fraction=0.05,
            active_module_gradient_norms={},
            shared_encoder_gradient_angles={},
            soft_operator_occupancy={},
            n_observations=0,
            n_k_eff={"per_operator": {}, "min": 0.0, "median": 0.0, "total": 0.0},
            n_k_eff_over_d_squared={"per_operator": {}, "min": 0.0, "median": 0.0, "total": 0.0},
            operator_condition_numbers={},
            perturbed_score_rank_correlation=None,
            perturbed_operator_assignment_agreement=None,
            residual_energy={},
            predicted_to_true_residual_median_ratio=None,
            predicted_to_true_residual_q95_ratio=None,
            residual_tail_ratio_q95_over_median=None,
            input_ood_fraction=0.0,
            gate_mean=None,
            deterministic_replay_max_abs_delta=None,
            common_support_digest=(
                common_support_identity(validation_rows)
                if validation_rows.size
                else None
            ),
            four_residual_common_support={},
        ),
        validation_score_rows=validation_rows,
        validation_scores=_score(validation_rows),
        operator_ids=np.empty(0, dtype=np.int64),
        diagnostic_rows=diagnostic_rows,
        diagnostic_scores=_score(diagnostic_rows),
        diagnostic_cross_year_count=cross_year,
        train_row_count=0,
        validation_row_count=int(validation_rows.shape[0]),
        diagnostic_row_count=int(diagnostic_rows.shape[0]),
        peak_rss_mib=_peak_rss_mib(),
        elapsed_seconds=0.0,
        model_state_digest="transparent_rank_parameter_free_common_root",
        checkpoint_path=None,
    )
    result.validate_artifact_schema()
    return result


def fit_stage6_arm(
    *,
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    rows_by_year: dict[int, NDArray[np.int64]],
    config: Stage6FitConfig,
    diagnostic_year: int | None = None,
    checkpoint_dir: Path | None = None,
    window_cache: object | None = None,
    loss_reference_semantics: str = "first_training_epoch_vs_last_training_epoch",
    adjudication_mode: Literal["legacy_fail_closed", "stage6r_integrity_only"] = (
        "legacy_fail_closed"
    ),
    validation_checkpoint_cycles: tuple[int, ...] | None = None,
    training_order_policy: Literal[
        "row_permutation", "contiguous_batch_permutation"
    ] = "row_permutation",
    precision_policy: Literal["float32", "autocast_float16"] = "float32",
) -> Stage6FitResult:
    """Fit one frozen arm on one year's frozen training prefix.

    r1 repairs: seed before construction, mask-augmented features, horizon
    targets, exit-year annual boundary discipline, genuine perturbation
    comparison, Kish ``n_k_eff``, common-support four-residual evidence and
    a replayable checkpoint.
    """

    started = time.perf_counter()
    config.validate()
    if adjudication_mode not in {"legacy_fail_closed", "stage6r_integrity_only"}:
        raise ValueError(f"stage6_adjudication_mode_unknown:{adjudication_mode}")
    if training_order_policy not in {
        "row_permutation",
        "contiguous_batch_permutation",
    }:
        raise ValueError(
            f"stage6_training_order_policy_unknown:{training_order_policy}"
        )
    if precision_policy not in {"float32", "autocast_float16"}:
        raise ValueError(f"stage6_precision_policy_unknown:{precision_policy}")
    if validation_checkpoint_cycles is not None:
        if (
            not validation_checkpoint_cycles
            or tuple(sorted(set(validation_checkpoint_cycles)))
            != validation_checkpoint_cycles
            or validation_checkpoint_cycles[0] <= 0
            or validation_checkpoint_cycles[-1] != config.policy.maximum_epochs
        ):
            raise ValueError("stage6_validation_checkpoint_cycles_invalid")
    if spec.task_id != config.task_id:
        raise ValueError("stage6_task_id_mismatch")
    if config.sequence_length not in spec.sequence_length_candidates:
        raise ValueError(f"stage6_sequence_length_not_frozen:{config.sequence_length}")
    diagnostic_year = diagnostic_year if diagnostic_year is not None else config.validation_year
    if not YEAR_MIN <= diagnostic_year <= YEAR_MAX:
        raise ValueError("stage6_diagnostic_year_out_of_range")
    spec_arm = stage6_arm_spec(config.arm_id)
    if spec_arm.is_transparent:
        return _fit_transparent_arm(
            shared=shared,
            spec=spec,
            rows_by_year=rows_by_year,
            config=config,
            diagnostic_year=diagnostic_year,
        )
    device = torch.device(config.device)
    use_amp = precision_policy == "autocast_float16"
    if use_amp and device.type != "cuda":
        raise ValueError("stage6_autocast_float16_requires_cuda_or_rocm")
    train_parts = []
    for year in config.train_years:
        rows = np.asarray(
            rows_by_year.get(year, np.empty((0, ROW_WIDTH), dtype=np.int64))
        )
        rows = filter_rows_by_exit_year(
            rows,
            allowed_years=config.train_years,
            decision_year=year,
            calendar=shared.calendar,
        )
        if rows.size:
            train_parts.append(rows)
    if not train_parts or any(part.size == 0 for part in train_parts):
        raise ValueError("stage6_train_rows_missing")
    train_rows = np.concatenate(train_parts, axis=0)
    validation_rows = np.asarray(
        rows_by_year.get(
            config.validation_year, np.empty((0, ROW_WIDTH), dtype=np.int64)
        )
    )
    validation_rows = filter_rows_by_exit_year(
        validation_rows,
        allowed_years=(config.validation_year,),
        decision_year=config.validation_year,
        calendar=shared.calendar,
    )
    if validation_rows.size == 0:
        raise ValueError("stage6_validation_rows_missing")
    # r2 repair 5: diagnostic rows must NOT carry labels exiting beyond the
    # diagnostic year; cross-year rows are counted and excluded from the
    # diagnostic pack (they are never written into the y-year evidence).
    diagnostic_all = np.asarray(
        rows_by_year.get(diagnostic_year, np.empty((0, ROW_WIDTH), dtype=np.int64))
    )
    cross_year = int(
        (diagnostic_all[:, 2] != diagnostic_year).sum()
        if diagnostic_all.size
        else 0
    )
    diagnostic_rows = filter_rows_by_exit_year(
        diagnostic_all,
        allowed_years=(diagnostic_year,),
        decision_year=diagnostic_year,
        calendar=shared.calendar,
    )
    return_mean, return_scale = train_prefix_return_stats(shared, train_rows)

    # r1 repair 3: the seed is set BEFORE model construction so the initial
    # weights are reproducible for the same config.
    _seed_everything(config.seed)
    model = build_stage6_reaka_model(
        feature_dim=spec.model_feature_dim,
        arm_id=config.arm_id,
        policy=config.policy,
        sequence_length=config.sequence_length,
        latent_dim=config.latent_dim,
        operator_count=config.operator_count,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.policy.learning_rate)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    rng = np.random.default_rng(config.seed)

    direct_cache_splits: set[str] = set()
    direct_load_split_indices = None
    if window_cache is not None:
        split_rows_match = getattr(window_cache, "split_rows_match", None)
        load_split_indices = getattr(window_cache, "load_split_indices", None)
        if split_rows_match is not None and load_split_indices is not None:
            direct_load_split_indices = load_split_indices
            if bool(split_rows_match("train", train_rows)):
                direct_cache_splits.add("train")
            if bool(split_rows_match("validation", validation_rows)):
                direct_cache_splits.add("validation")

    def _load_batch(
        rows: NDArray[np.int64],
        *,
        split: Literal["train", "validation"] | None = None,
        indices: NDArray[np.int64] | slice | None = None,
    ) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor]:
        if window_cache is not None:
            if (
                split in direct_cache_splits
                and indices is not None
                and direct_load_split_indices is not None
            ):
                cached = direct_load_split_indices(split, indices)
                return (
                    cached[0].to(device),
                    cached[1].to(device),
                    cached[2],
                    cached[3].to(device),
                    cached[4].to(device),
                )
            load_rows = getattr(window_cache, "load_rows", None)
            if load_rows is None:
                raise TypeError("stage6_window_cache_load_rows_missing")
            cached = load_rows(rows)
            if cached is not None:
                return (
                    cached[0].to(device),
                    cached[1].to(device),
                    cached[2],
                    cached[3].to(device),
                    cached[4].to(device),
                )
        returns, features, availability, targets, target_mask = assemble_windows(
            shared,
            spec,
            rows,
            config.sequence_length,
            return_mean=return_mean,
            return_scale=return_scale,
        )
        return (
            returns.to(device),
            features.to(device),
            availability.to(device),
            targets.to(device),
            target_mask.to(device),
        )

    first_epoch_losses: dict[str, float] = {}
    last_epoch_losses: dict[str, float] = {}
    pretraining_validation_losses: dict[str, float] = {}
    best_validation_losses: dict[str, float] = {}
    best_validation_loss = math.inf
    best_state: dict[str, Tensor] | None = None
    patience_left = config.policy.early_stopping_patience
    epoch_count = 0
    stopped_early = False
    validation_learning_curve: list[dict[str, object]] = []

    train_probe_rows = train_rows[
        rng.permutation(train_rows.shape[0])[: min(4096, train_rows.shape[0])]
    ]
    _, train_probe_features, _, _, _ = assemble_windows(
        shared,
        spec,
        train_probe_rows,
        config.sequence_length,
        return_mean=return_mean,
        return_scale=return_scale,
    )
    probe = train_probe_features.numpy().astype(np.float64)
    train_channel_min = probe.min(axis=(0, 1)).astype(np.float32)
    train_channel_max = probe.max(axis=(0, 1)).astype(np.float32)

    def _validation_components() -> dict[str, float]:
        totals = {
            "total_loss": 0.0,
            "reconstruction_loss": 0.0,
            "koopman_loss": 0.0,
            "diffusion_loss": 0.0,
        }
        cells = 0
        model.eval()
        with torch.no_grad():
            for start in range(
                0, validation_rows.shape[0], config.policy.batch_size
            ):
                rows = validation_rows[start : start + config.policy.batch_size]
                returns, features, _, targets, target_mask = _load_batch(
                    rows,
                    split="validation",
                    indices=slice(start, start + rows.shape[0]),
                )
                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.float16,
                    enabled=use_amp,
                ):
                    output = cast(
                        ReakaPaperTrainingOutput,
                        model.training_objective(
                            returns,
                            features,
                            targets=targets,
                            target_mask=target_mask,
                        ),
                    )
                count = returns.shape[0]
                totals["total_loss"] += float(output.total_loss.detach()) * count
                totals["reconstruction_loss"] += (
                    float(output.reconstruction_loss.detach()) * count
                )
                totals["koopman_loss"] += float(output.koopman_loss.detach()) * count
                totals["diffusion_loss"] += (
                    float(output.diffusion_loss.detach()) * count
                )
                cells += count
        return {key: value / max(cells, 1) for key, value in totals.items()}

    if loss_reference_semantics == "pretraining_validation_vs_best_coverage_validation":
        pretraining_validation_losses = _validation_components()
        validation_learning_curve.append(
            {"coverage_cycle": 0, **pretraining_validation_losses}
        )

    for epoch in range(1, config.policy.maximum_epochs + 1):
        epoch_count = epoch
        totals = {
            "total_loss": 0.0,
            "reconstruction_loss": 0.0,
            "koopman_loss": 0.0,
            "diffusion_loss": 0.0,
        }
        cells = 0
        model.train()
        if training_order_policy == "contiguous_batch_permutation":
            batch_starts = np.arange(
                0, train_rows.shape[0], config.policy.batch_size, dtype=np.int64
            )
            rng.shuffle(batch_starts)
            batch_indices: list[NDArray[np.int64] | slice] = [
                slice(
                    int(start),
                    min(int(start) + config.policy.batch_size, train_rows.shape[0]),
                )
                for start in batch_starts
            ]
        else:
            order = rng.permutation(train_rows.shape[0])
            batch_indices = [
                order[start : start + config.policy.batch_size]
                for start in range(0, order.size, config.policy.batch_size)
            ]
        for indices in batch_indices:
            rows = train_rows[indices]
            returns, features, _, targets, target_mask = _load_batch(
                rows,
                split="train",
                indices=indices,
            )
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(
                device_type=device.type,
                dtype=torch.float16,
                enabled=use_amp,
            ):
                output = cast(
                    ReakaPaperTrainingOutput,
                    model.training_objective(
                        returns,
                        features,
                        targets=targets,
                        target_mask=target_mask,
                    ),
                )
            scaler.scale(output.total_loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                max_norm=config.policy.gradient_clip_norm,
            )
            scaler.step(optimizer)
            scaler.update()
            count = returns.shape[0]
            totals["total_loss"] += float(output.total_loss.detach()) * count
            totals["reconstruction_loss"] += float(output.reconstruction_loss.detach()) * count
            totals["koopman_loss"] += float(output.koopman_loss.detach()) * count
            totals["diffusion_loss"] += float(output.diffusion_loss.detach()) * count
            cells += count
        last_epoch_losses = {
            key: value / max(cells, 1) for key, value in totals.items()
        }
        if epoch == 1:
            first_epoch_losses = dict(last_epoch_losses)
        should_validate = (
            validation_checkpoint_cycles is None
            or epoch in validation_checkpoint_cycles
        )
        if should_validate:
            validation_losses = _validation_components()
            validation_learning_curve.append(
                {"coverage_cycle": epoch, **validation_losses}
            )
            validation_loss = validation_losses["total_loss"]
            if epoch >= config.policy.minimum_epochs:
                if validation_loss < best_validation_loss:
                    best_validation_loss = validation_loss
                    best_state = {
                        name: parameter.detach().cpu().clone()
                        for name, parameter in model.named_parameters()
                    }
                    best_validation_losses = dict(validation_losses)
                    patience_left = config.policy.early_stopping_patience
                else:
                    patience_left -= 1
                    if patience_left <= 0:
                        stopped_early = True
                        break

    # r2 repair 7: restore the best validation state before health
    # evidence, checkpoint and scoring.
    if best_state is not None:
        with torch.no_grad():
            for name, parameter in model.named_parameters():
                parameter.copy_(best_state[name].to(parameter.device))

    # Deterministic single-batch replay with the same seed and batch order.
    replay_rows = train_rows[: min(256, train_rows.shape[0])]
    replay_losses: list[float] = []
    for _ in range(2):
        _seed_everything(config.seed)
        replay_returns, replay_features, _, replay_targets, replay_mask = _load_batch(
            replay_rows
        )
        with torch.no_grad():
            replay_output = cast(
                ReakaPaperTrainingOutput,
                model.training_objective(
                    replay_returns,
                    replay_features,
                    targets=replay_targets,
                    target_mask=replay_mask,
                ),
            )
        replay_losses.append(float(replay_output.total_loss.detach()))
    replay_delta = abs(replay_losses[0] - replay_losses[1])

    health_train_rows = train_rows[
        rng.permutation(train_rows.shape[0])[: min(512, train_rows.shape[0])]
    ]
    health_val_rows = validation_rows[: min(512, validation_rows.shape[0])]
    health_train_batch = _load_batch(health_train_rows)
    health_val_batch = _load_batch(health_val_rows)

    # r1 repair 4: baseline BEFORE perturbation, perturbed AFTER, restore.
    # r2 repair 6: diffusion arms use the SAME fixed inference noise for
    # both forecasts, so the comparison isolates parameter perturbation.
    perturbed_correlation: float | None = None
    perturbed_agreement: float | None = None
    if validation_rows.shape[0] >= 2:
        original_state = {
            name: parameter.detach().clone()
            for name, parameter in model.named_parameters()
        }
        diffusion = stage6_arm_spec(config.arm_id).residual_mode == "diffusion"
        if diffusion:
            generator = torch.Generator(device=device).manual_seed(config.seed)
            fixed_initial_noise = torch.randn(
                health_val_batch[0].shape[0],
                health_val_batch[0].shape[1],
                config.latent_dim,
                generator=generator,
                device=device,
            )
            fixed_reverse = tuple(
                torch.randn(
                    health_val_batch[0].shape[0],
                    health_val_batch[0].shape[1],
                    config.latent_dim,
                    generator=torch.Generator(device=device).manual_seed(
                        config.seed + 1000 + step
                    ),
                    device=device,
                )
                for step in range(config.policy.diffusion_steps)
            )
        else:
            fixed_initial_noise = None
            fixed_reverse = None
        model.eval()
        with torch.no_grad():
            base_forecast = model.forecast(
                health_val_batch[0],
                health_val_batch[1],
                initial_noise=fixed_initial_noise,
                reverse_noises=fixed_reverse,
            )
            base_scores = base_forecast.scores.detach().cpu().numpy().astype(np.float64)
            base_operators = (
                base_forecast.operator_ids[:, -1]
                .detach()
                .cpu()
                .numpy()
                .astype(np.int64)
            )
        with torch.no_grad():
            for parameter in model.parameters():
                magnitude = torch.abs(parameter).clamp(min=1e-6)
                parameter.add_(0.01 * magnitude * torch.randn_like(parameter))
        with torch.no_grad():
            perturbed_forecast = model.forecast(
                health_val_batch[0],
                health_val_batch[1],
                initial_noise=fixed_initial_noise,
                reverse_noises=fixed_reverse,
            )
            perturbed_scores = (
                perturbed_forecast.scores.detach().cpu().numpy().astype(np.float64)
            )
            perturbed_operators = (
                perturbed_forecast.operator_ids[:, -1]
                .detach()
                .cpu()
                .numpy()
                .astype(np.int64)
            )
        perturbed_correlation = _spearman(base_scores, perturbed_scores)
        if base_operators.size:
            perturbed_agreement = float(
                np.mean(base_operators == perturbed_operators)
            )
        with torch.no_grad():
            for name, parameter in model.named_parameters():
                parameter.copy_(original_state[name])

    # r3 repair: real cross-mode residual evidence.  The probes are fitted
    # on the TRAINING-prefix support (health_train_batch) and measured on
    # the held-out common validation support (health_val_batch), so the
    # measured support is never inside probe training.
    model.eval()
    with torch.no_grad():
        health_train_output = cast(
            ReakaPaperTrainingOutput,
            model.training_objective(
                health_train_batch[0],
                health_train_batch[1],
                targets=health_train_batch[3],
                target_mask=health_train_batch[4],
            ),
        )
        health_val_output = cast(
            ReakaPaperTrainingOutput,
            model.training_objective(
                health_val_batch[0],
                health_val_batch[1],
                targets=health_val_batch[3],
                target_mask=health_val_batch[4],
            ),
        )
    mlp_residual_probe, diffusion_residual_probe = _train_residual_evidence_probes(
        train_latent=health_train_output.latent,
        train_residual=health_train_output.true_residual,
        latent=health_val_output.latent,
        true_residual=health_val_output.true_residual,
        model_config=model.config,
        device=device,
        seed=config.seed,
    )

    health_first_losses = first_epoch_losses
    health_last_losses = last_epoch_losses
    if loss_reference_semantics == "pretraining_validation_vs_best_coverage_validation":
        if not pretraining_validation_losses or not best_validation_losses:
            raise RuntimeError("stage6_coverage_validation_reference_missing")
        health_first_losses = pretraining_validation_losses
        health_last_losses = best_validation_losses

    health = compute_stage6_training_health(
        model=model,
        train_batch=health_train_batch,
        validation_batch=health_val_batch,
        validation_rows=health_val_rows,
        first_epoch_losses=health_first_losses,
        last_epoch_losses=health_last_losses,
        device=device,
        train_channel_min=train_channel_min,
        train_channel_max=train_channel_max,
        policy=config.policy,
        replay_max_abs_delta=replay_delta,
        perturbed_score_rank_correlation=perturbed_correlation,
        perturbed_operator_assignment_agreement=perturbed_agreement,
        mlp_residual=mlp_residual_probe,
        diffusion_residual=diffusion_residual_probe,
    )

    # Validation and diagnostic scores (implementation only; the controller
    # owns their use).
    def _score_rows(
        rows: NDArray[np.int64],
    ) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
        scores = np.zeros(rows.shape[0], dtype=np.float64)
        operator_ids = np.zeros(rows.shape[0], dtype=np.int64)
        model.eval()
        with torch.no_grad():
            for start in range(0, rows.shape[0], config.policy.batch_size):
                part = rows[start : start + config.policy.batch_size]
                returns, features, _, _, _ = _load_batch(part)
                forecast = model.forecast(returns, features)
                stop = min(start + config.policy.batch_size, rows.shape[0])
                scores[start:stop] = (
                    forecast.scores.detach().cpu().numpy().astype(np.float64)
                )
                ids = (
                    forecast.operator_ids[:, -1]
                    .detach()
                    .cpu()
                    .numpy()
                    .astype(np.int64)
                )
                operator_ids[start:stop] = ids
        return scores, operator_ids

    # r2 repair 4: adjudicate the frozen hard sanity limits fail-closed and
    # attach the certificate to the fit result.
    legacy_certificate = evaluate_stage6_health_certificate(
        fit_label=(
            f"{config.task_id}__{config.arm_id}__L{config.sequence_length}"
            f"__d{config.latent_dim}__K{config.operator_count}__s{config.seed}"
        ),
        health=health,
        operator_count=config.operator_count,
        residual_mode=stage6_arm_spec(config.arm_id).residual_mode,
        # Individual-arm health is the prerequisite for formal aggregation.
        # The runner supplies and enforces the final formal cross-arm
        # certificate whenever the full REAKA arm is requested.
        require_four_residual=False,
    )
    legacy_certificate_payload = legacy_certificate.as_dict()
    if adjudication_mode == "stage6r_integrity_only":
        certificate_payload = evaluate_stage6r_integrity_certificate(
            fit_label=(
                f"{config.task_id}__{config.arm_id}__L{config.sequence_length}"
                f"__d{config.latent_dim}__K{config.operator_count}__s{config.seed}"
            ),
            health=health,
            validation_learning_curve=tuple(validation_learning_curve),
            model_parameters_finite=all(
                bool(torch.isfinite(parameter).all().item())
                for parameter in model.parameters()
            ),
        )
    else:
        certificate_payload = legacy_certificate_payload

    # Formal evidence is emitted by the fitted frozen arm itself, never by
    # the auxiliary probes.  Diffusion training noise is fixed so the arm
    # evidence can be reproduced from the checkpoint and seed.
    _seed_everything(config.seed + 7001)
    formal_steps: Tensor | None = None
    formal_noise: Tensor | None = None
    if stage6_arm_spec(config.arm_id).residual_mode == "diffusion":
        batch = health_val_batch[0].shape[0]
        formal_steps = torch.arange(batch, device=device) % config.policy.diffusion_steps
        generator = torch.Generator(device=device).manual_seed(config.seed + 7001)
        with torch.no_grad():
            probe_output = model.training_objective(
                health_val_batch[0],
                health_val_batch[1],
                targets=health_val_batch[3],
                target_mask=health_val_batch[4],
            )
        formal_noise = torch.randn(
            probe_output.true_residual.shape,
            generator=generator,
            device=device,
        )
    with torch.no_grad():
        formal_output = cast(
            ReakaPaperTrainingOutput,
            model.training_objective(
                health_val_batch[0],
                health_val_batch[1],
                targets=health_val_batch[3],
                target_mask=health_val_batch[4],
                diffusion_steps=formal_steps,
                diffusion_noise=formal_noise,
            ),
        )

    # r3 repair 1: a blocked health certificate is fail-closed.  The fit
    # produces only the blocked diagnostic evidence (health snapshot +
    # certificate); usable scores, operator ids and a replayable checkpoint
    # are withheld so the controller cannot adjudicate a failed model.  The
    # row arrays are emptied alongside the scores so the blocked result's
    # schema stays self-consistent (r4 repair: no row/score count
    # mismatch).
    if certificate_payload.get("status") == "blocked":
        # The row arrays are emptied alongside the scores so the blocked
        # result's schema stays self-consistent (r4 repair: no row/score
        # count mismatch).  ``validation_score_rows`` and
        # ``diagnostic_rows`` are rebound below to empty arrays.
        validation_scores = np.zeros(0, dtype=np.float64)
        operator_ids = np.zeros(0, dtype=np.int64)
        diagnostic_scores = np.zeros(0, dtype=np.float64)
        validation_score_rows = np.zeros((0, ROW_WIDTH), dtype=np.int64)
        diagnostic_score_rows = np.zeros((0, ROW_WIDTH), dtype=np.int64)
        checkpoint_path = None
        formal_arm_evidence = None
    else:
        validation_score_rows = validation_rows
        diagnostic_score_rows = diagnostic_rows
        validation_scores, operator_ids = _score_rows(validation_rows)
        if np.array_equal(diagnostic_rows, validation_rows):
            diagnostic_scores = validation_scores.copy()
        else:
            diagnostic_scores, _ = _score_rows(diagnostic_rows)
        checkpoint_path = None
        if checkpoint_dir is not None:
            checkpoint_path = _save_checkpoint(
                model=model,
                config=config,
                directory=checkpoint_dir,
            )
        formal_arm_evidence = Stage6FormalArmResidualEvidence(
            arm_id=config.arm_id,
            task_id=config.task_id,
            sequence_length=config.sequence_length,
            latent_dim=config.latent_dim,
            operator_count=config.operator_count,
            seed=config.seed,
            train_years=config.train_years,
            validation_year=config.validation_year,
            support_digest=common_support_identity(health_val_rows),
            model_state_digest=_model_state_digest(model),
            checkpoint_digest=(
                f"sha256:{sha256_file(Path(checkpoint_path))}"
                if checkpoint_path is not None
                else ""
            ),
            health_certificate_digest=str(certificate_payload["canonical_digest"]),
            health_certificate_status=str(certificate_payload["status"]),
            true_residual=residual_summary(formal_output.true_residual),
            estimated_residual=residual_summary(formal_output.estimated_residual),
            evidence_source="teacher_forced_training_objective",
            selector_mode="gumbel_soft",
            reference_residual_source="training_next_latent_minus_soft_advanced",
            history_only_inputs=False,
        ).as_dict()

    result = Stage6FitResult(
        config=config,
        first_epoch_losses=health_first_losses,
        last_epoch_losses=health_last_losses,
        epoch_count=epoch_count,
        stopped_early=stopped_early,
        health=health,
        validation_score_rows=validation_score_rows,
        validation_scores=validation_scores,
        operator_ids=operator_ids,
        diagnostic_rows=diagnostic_score_rows,
        diagnostic_scores=diagnostic_scores,
        diagnostic_cross_year_count=cross_year,
        train_row_count=int(train_rows.shape[0]),
        validation_row_count=int(validation_score_rows.shape[0]),
        diagnostic_row_count=int(diagnostic_score_rows.shape[0]),
        peak_rss_mib=_peak_rss_mib(),
        elapsed_seconds=time.perf_counter() - started,
        model_state_digest=_model_state_digest(model),
        checkpoint_path=checkpoint_path,
        health_certificate=certificate_payload,
        formal_arm_residual_evidence=formal_arm_evidence,
        loss_reference_semantics=loss_reference_semantics,
        validation_learning_curve=tuple(validation_learning_curve),
        diagnostic_health_certificate=(
            legacy_certificate_payload
            if adjudication_mode == "stage6r_integrity_only"
            else None
        ),
        training_order_policy=training_order_policy,
        precision_policy=precision_policy,
    )
    result.validate_artifact_schema()
    return result


def _peak_rss_mib() -> float:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except (ImportError, OSError):
        return math.nan


# ---------------------------------------------------------------------------
# One-year controller receipt chain (r1 repair: recomputed digest chain)
# ---------------------------------------------------------------------------


def _recomputed_canonical_digest(payload: dict[str, object]) -> str:
    """Recompute a payload's canonical digest from bytes, ignoring any
    self-reported digest field."""

    stripped = {key: value for key, value in payload.items() if key != "canonical_digest"}
    return canonical_digest(stripped)


def validate_prior_controller_receipt(
    *,
    receipt_path: Path,
    expected_year: int,
    expected_prior_year: int,
    freeze_manifest_digest: str,
    tensor_manifest_digest: str,
    prior_receipt_path: Path | None = None,
    prior_policy_snapshot_digest: str | None = None,
) -> dict[str, object]:
    """Validate the prior controller receipt with a recomputed digest chain.

    r3: the prior receipt's entity chain is MANDATORY.  When a previous
    receipt exists, its file must be supplied and its recomputed digest
    must match the receipt's ``prior_receipt_digest`` (no self-declared
    string is trusted).  The receipt must additionally bind the prior
    annual policy/model snapshot digest (the exact prior frozen policy,
    not merely the engineering freeze manifest); the engineering freeze
    digest stays bound as an independent field.  Any missing link, forged
    digest, unbound snapshot, or broken year chain fails closed.
    """

    if not receipt_path.exists():
        raise FileNotFoundError(
            f"stage6_prior_controller_receipt_missing:{receipt_path}"
        )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != STAGE6_YEAR_RECEIPT_SCHEMA_ID:
        raise ValueError("stage6_prior_receipt_schema_mismatch")
    if int(payload.get("year", -1)) != expected_prior_year:
        raise ValueError(
            f"stage6_prior_receipt_year_mismatch:{payload.get('year')}!={expected_prior_year}"
        )
    if payload.get("main_controller_sealed") is not True:
        raise ValueError("stage6_prior_receipt_not_sealed")
    if payload.get("main_controller_review_required_before_next_year") is not True:
        raise ValueError("stage6_prior_receipt_review_gate_unset")
    if expected_year != expected_prior_year + 1:
        raise ValueError("stage6_year_chain_must_advance_by_one")
    recomputed = _recomputed_canonical_digest(payload)
    declared = str(payload.get("canonical_digest", ""))
    if declared != recomputed:
        raise ValueError(
            f"stage6_prior_receipt_digest_tampered:{declared[:16]}!={recomputed[:16]}"
        )
    policy_digest = str(payload.get("policy_digest", ""))
    if policy_digest != freeze_manifest_digest:
        raise ValueError("stage6_prior_receipt_policy_digest_unbound")
    tensor_digest = str(payload.get("tensor_manifest_digest", ""))
    if tensor_digest != tensor_manifest_digest:
        raise ValueError("stage6_prior_receipt_tensor_digest_unbound")
    # r3: the prior-receipt entity chain is mandatory, and the prior annual
    # policy/model snapshot digest must be bound.
    prior_digest = str(payload.get("prior_receipt_digest", ""))
    if not prior_digest:
        raise ValueError("stage6_prior_receipt_link_digest_missing")
    if prior_receipt_path is None:
        raise ValueError("stage6_prior_receipt_entity_link_required")
    if not prior_receipt_path.exists():
        raise ValueError("stage6_prior_receipt_link_file_missing")
    prior_payload = json.loads(prior_receipt_path.read_text(encoding="utf-8"))
    prior_recomputed = _recomputed_canonical_digest(prior_payload)
    if prior_digest != prior_recomputed:
        raise ValueError(
            f"stage6_prior_receipt_link_tampered:{prior_digest[:16]}!={prior_recomputed[:16]}"
        )
    snapshot_digest = str(
        payload.get("current_policy_snapshot_digest")
        or payload.get("prior_policy_snapshot_digest", "")
    )
    if not snapshot_digest:
        raise ValueError("stage6_prior_policy_snapshot_digest_missing")
    # r4: the expected prior policy snapshot digest is REQUIRED whenever an
    # annual chain is validated; it is never optional.  A receipt whose
    # declared snapshot digest does not match the actual prior frozen
    # policy/model snapshot is rejected fail-closed.
    if prior_policy_snapshot_digest is None:
        raise ValueError("stage6_prior_policy_snapshot_digest_required")
    if snapshot_digest != prior_policy_snapshot_digest:
        raise ValueError(
            f"stage6_prior_policy_snapshot_digest_unbound:{snapshot_digest[:16]}"
        )
    return payload


# ---------------------------------------------------------------------------
# Small helpers shared by the scripts
# ---------------------------------------------------------------------------


def stage6_engine_scope_files(root: Path) -> dict[str, str]:
    """Digests of the six files inside the external code scope."""

    files = {
        "engine_module": root / "src/factor_lab/factor_rotation/reaka_stage6_daily_engine.py",
        "materialize_script": root / "scripts/factor_rotation/materialize_reaka_stage6_daily_inputs.py",
        "preflight_script": root / "scripts/factor_rotation/run_reaka_stage6_engineering_preflight.py",
        "one_year_script": root / "scripts/factor_rotation/prepare_reaka_stage6_one_year.py",
        "validator_script": root / "scripts/factor_rotation/validate_reaka_stage6_engineering_handoff.py",
        "test_module": root / "tests/unit/test_reaka_stage6_daily_engine.py",
    }
    return {key: sha256_file(path) for key, path in files.items()}


def paper_equation_parity_payload() -> dict[str, object]:
    """Equation 1-31 parity map against the implementation anchors."""

    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_paper_equation_parity@2.0",
        "strategy_id": STAGE6_STRATEGY_ID,
        "engine_module": "src/factor_lab/factor_rotation/reaka_stage6_daily_engine.py",
        "paper_engine_module": "src/factor_lab/factor_rotation/reaka_paper_v1.py",
        "equations": {
            "eq_1_2_overlapping_return_windows": {
                "implementation": "assemble_windows",
                "semantics": "returns 1:T and features share identical day offsets ending at the decision day",
                "engine_only": False,
            },
            "eq_3_6_return_and_feature_lstm_delay_embeddings": {
                "implementation": "ReakaPaperModel.return_encoder/feature_encoder",
                "semantics": (
                    "two independent LSTMs with shared window weights trained "
                    "end to end; the r1 feature axis appends availability "
                    "masks per the frozen input identity"
                ),
                "engine_only": False,
            },
            "eq_7_10_feature_controlled_elementwise_gate": {
                "implementation": "ReakaPaperModel.gate_net",
                "semantics": "latent = Hr*gate + Hx*(1-gate); gate disabled for without_gate arm",
                "engine_only": False,
            },
            "eq_11_15_selector_on_Z_and_Hy_gumbel_train_operator_mix": {
                "implementation": "ReakaPaperModel._transition",
                "semantics": "selector on [Z,Hy]; gumbel-softmax (tau=0.75) in training; one-hot argmax at inference",
                "engine_only": False,
            },
            "eq_16_21_conditional_ddpm_latent_residual": {
                "implementation": "ReakaPaperModel.residual_denoiser/_diffusion_schedule",
                "semantics": "conditional DDPM on Z+-Z_hat+; linear beta 1e-4->2e-2; 8 steps; reverse starts from Gaussian",
                "engine_only": False,
            },
            "eq_22_27_return_decoder_last_element_forecast": {
                "implementation": "Stage6ReakaModel.training_objective + forecast",
                "semantics": "decoder reconstructs the task's h-day label sequence; score is the last element",
                "engine_only": False,
            },
            "eq_28_31_equal_sum_Lrec_Lkoop_Ldiff": {
                "implementation": "Stage6ReakaModel.training_objective",
                "semantics": "L_total = L_rec + L_koop + L_diff with equal weights 1.0/1.0/1.0; L_rec cell-masked over valid h-day labels",
                "engine_only": False,
            },
            "inference_argmax_operator_selection": {
                "implementation": "ReakaPaperModel.forecast",
                "semantics": "argmax over selector logits then codebook lookup",
                "engine_only": False,
            },
        },
        "r1_repairs_bound": {
            "availability_mask_enters_model": (
                "feature axis = [values; masks], 2F model features per task "
                "channel"
            ),
            "horizon_bound_to_target": (
                "decoder reconstruction target = task h-day label sequence "
                "(T+1 open entry, h-day close exit); last element is the "
                "decision-day h-day forecast"
            ),
            "override_equivalence_anchor": (
                "training_objective with targets=None reproduces the parent "
                "paper objective exactly (unit-tested)"
            ),
            "paper_unspecified_assumptions": {
                "return_standardization": "training-prefix mean/scale inherited from the Round-3A adapter; paper silent",
                "validation_loss_proxy": "training-objective loss with gumbel softmax on validation rows",
                "per_day_cross_sectional_rank_centering": "prefix-independent by construction (a day's cross-section only)",
                "input_return_series": "intraday open-to-close simple return from the sealed Stage-2 open/close surfaces",
            },
        },
        "claims_forbidden": [
            "author_code_bit_exact_replication",
            "paper_metric_replication",
            "latent_operator_as_named_macro_state",
            "post2020_fresh_oos",
            "production_authority",
        ],
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


__all__ = [
    "CADENCE_INTERVALS",
    "FORMAL_CROSS_ARM_IDS",
    "HORIZON_INDEX",
    "MISSING_BIN",
    "PATHWAY_IDS",
    "ROW_WIDTH",
    "STAGE6_CERTIFICATE_SCHEMA_ID",
    "STAGE6_ENGINE_SCHEMA_ID",
    "STAGE6_FORMAL_CROSS_ARM_SCHEMA_ID",
    "STAGE6_HEALTH_SCHEMA_ID",
    "STAGE6_TENSOR_SCHEMA_ID",
    "STAGE6_YEAR_RECEIPT_SCHEMA_ID",
    "Stage6ArmSpec",
    "Stage6FitConfig",
    "Stage6FitResult",
    "Stage6FormalArmResidualEvidence",
    "Stage6ReakaModel",
    "Stage6SharedTensor",
    "Stage6TaskSpec",
    "Stage6TicketChannel",
    "Stage6TrainingHealth",
    "TRANSPARENT_ARM_ID",
    "TRAINABLE_ARM_IDS",
    "VALID_CADENCES",
    "VALID_HORIZONS",
    "VALID_LOOKBACKS",
    "VALID_QUANTILE_BINS",
    "assemble_latest_step",
    "assemble_windows",
    "build_stage6_reaka_model",
    "build_formal_cross_arm_residual_certificate",
    "common_support_identity",
    "compile_task_channels",
    "compute_stage6_training_health",
    "decision_day_positions",
    "filter_rows_by_exit_year",
    "fit_stage6_arm",
    "four_residual_common_support_evidence",
    "load_shared_tensor",
    "load_task_rows",
    "load_task_spec",
    "paper_equation_parity_payload",
    "score_stage6_checkpoint",
    "sha256_file",
    "stage6_arm_spec",
    "stage6_arm_specs",
    "stage6_engine_scope_files",
    "stage6_trainable_arm_ids",
    "train_prefix_return_stats",
    "transparent_rank_scores",
    "validate_prior_controller_receipt",
]
