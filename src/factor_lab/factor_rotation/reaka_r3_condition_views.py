"""R3 input-information controls for the existing 10 x 71 K1 interface.

This is NOT a trainer, a permission gate, or a feature-importance estimator.
Apply after the original training-prefix normalization, in EVERY data-consuming
path of a separately identified experiment (including DMD initialization and
checkpoint loss). Never apply only at review time and call it a trained control.
The original model, stores, training functions and frozen scores are untouched.
"""
from __future__ import annotations

from typing import Final
import numpy as np

FEATURE_DIM: Final = 71
SEQUENCE_POINTS: Final = 10
ARMS: Final = ("history_full", "history_only", "history_exposure")
# Original IntradayK1InputStore: [state, state_mask, beta, reliability,
# exposure_mask, age]. The last channel is a zero placeholder, NOT a mask.
CHANNEL_GROUPS: Final = {
    "state_values": (0, 14),
    "state_available": (14, 28),
    "stock_factor_exposures": (28, 42),
    "exposure_reliability": (42, 56),
    "exposure_available": (56, 70),
    "age_placeholder": (70, 71),
}


def feature_view(normalized_features: np.ndarray, arm: str) -> np.ndarray:
    """Return an independent array; do not mutate a memmap or the full arm.

    All arms use the same source-valid support. Invalid source values are not
    silently erased to make a reduced arm look valid. This helper accepts only
    the frozen original layout, whose masks stay binary and age stays zero.
    These are interface checks, not a PIT or provenance certificate.
    """
    if arm not in ARMS:
        raise ValueError(f"unknown R3 arm: {arm}")
    values = np.asarray(normalized_features)
    if values.ndim != 3 or values.shape[0] == 0 or values.shape[1:] != (SEQUENCE_POINTS, FEATURE_DIM):
        raise ValueError("expected nonempty batch x 10 x 71 normalized features")
    if values.dtype.kind != "f" or not np.isfinite(values).all():
        raise ValueError("all source features must be finite floating-point values")
    for lo, hi in ((14, 28), (56, 70)):
        mask = values[:, :, lo:hi]
        if not np.isin(mask, (0.0, 1.0)).all():
            raise ValueError("availability channels must keep the original binary encoding")
    if np.any(values[:, :, 70] != 0.0):
        raise ValueError("channel 70 must remain the original zero age placeholder")
    out = np.array(values, copy=True, order="C")
    if arm == "history_only":
        out.fill(0.0)  # Remove masks and reliability as well as values.
    elif arm == "history_exposure":
        out[:, :, :28] = 0.0  # Remove state values AND their availability.
    return out


def normalized_batch_view(
    normalized_history: np.ndarray,
    normalized_features: np.ndarray,
    arm: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Prepare a copied input batch. No labels or observation keys are accepted.

    A zero feature input still permits learned LSTM/gate biases; it is an
    information-removed same-topology control, not the legacy without_gate arm.
    History already contains factor-residualization information in every arm.
    """
    history = np.asarray(normalized_history)
    features = feature_view(normalized_features, arm)
    if history.shape != features.shape[:2] or history.dtype.kind != "f" or not np.isfinite(history).all():
        raise ValueError("history must be a finite floating batch x 10 array on identical support")
    return np.array(history, copy=True, order="C"), features


def describe_design() -> dict[str, object]:
    """Informational experiment recipe; calling it never starts or admits a fit."""
    return {
        "design_id": "R3-CONDITION-DESIGN-20260906-01",
        "feature_dim": FEATURE_DIM,
        "sequence_points": SEQUENCE_POINTS,
        "channel_groups_half_open": dict(CHANNEL_GROUPS),
        "primary_arms": ["history_full", "history_only"],
        "optional_bridge_arm": "history_exposure",
        "primary_contrast": "history_full_minus_history_only",
        "optional_contrasts": ["history_full_minus_history_exposure", "history_exposure_minus_history_only"],
        "apply_after": "original_fit_prefix_normalize_batch",
        "required_call_sites": ["DMD_initialization", "training_objective_inputs", "fit_prefix_checkpoint_loss", "review_forecast_inputs"],
        "same_topology_not_equal_effective_trainability": True,
        "training_runner_integrated": False,
        "training_executed": False,
        "feature_increment_identified": False,
        "fresh_oos": False,
        "production_authority": False,
    }


def condition_model_class(base_model_class: type, arm: str) -> type:
    """Create a local subclass intercepting the existing encoding choke point.

    Both Stage6 training windows and the inherited forecast call this method;
    DMD/checkpoint loss call training_objective on the same model. The caller
    must still use the original normalizer BEFORE invoking these methods and
    reproduce the original model initialization. No global function is patched.
    This factory adds no parameters/buffers and does not load or fit a model.
    Whole-run integration and actual source identity remain to be checked.
    """
    if arm not in ARMS:
        raise ValueError(f"unknown R3 arm: {arm}")
    if not isinstance(base_model_class, type) or not callable(getattr(base_model_class, "_encode_and_gate", None)):
        raise TypeError("base model must expose _encode_and_gate")
    import torch

    class ConditionViewModel(base_model_class):
        r3_condition_arm = arm

        def _encode_and_gate(self, returns, features):
            # Training uses 9-point shifted windows; forecasting uses 10 points.
            if not isinstance(features, torch.Tensor) or features.ndim != 3 or features.shape[0] == 0:
                raise ValueError("expected nonempty batch x sequence x feature tensor")
            if not 1 <= features.shape[1] <= SEQUENCE_POINTS or features.shape[2] != FEATURE_DIM:
                raise ValueError("encoding view expects 1..10 points and 71 channels")
            if not features.is_floating_point() or not bool(torch.isfinite(features).all()):
                raise ValueError("all original feature cells must be finite floating-point values")
            for lo, hi in ((14, 28), (56, 70)):
                masks = features[:, :, lo:hi]
                if not bool(((masks == 0) | (masks == 1)).all()):
                    raise ValueError("availability mask encoding drift")
            if bool((features[:, :, 70] != 0).any()):
                raise ValueError("age placeholder drift")
            if arm == "history_only":
                projected = torch.zeros_like(features)
            elif arm == "history_exposure":
                projected = torch.cat((torch.zeros_like(features[:, :, :28]), features[:, :, 28:]), dim=2)
            else:
                projected = features.clone()
            return super()._encode_and_gate(returns, projected)

    ConditionViewModel.__name__ = f"R3_{arm}_{base_model_class.__name__}"
    return ConditionViewModel
