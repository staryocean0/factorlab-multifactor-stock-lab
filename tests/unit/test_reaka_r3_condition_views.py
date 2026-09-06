"""Synthetic interface checks only: not original-model integration or market fits."""
from pathlib import Path
import importlib.util
import inspect

import numpy as np
import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src/factor_lab/factor_rotation/reaka_r3_condition_views.py"
SPEC = importlib.util.spec_from_file_location("r3_condition_views", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def batch(dtype=np.float32):
    rng = np.random.default_rng(20260906)
    h = rng.normal(size=(4, 10)).astype(dtype)
    x = rng.normal(size=(4, 10, 71)).astype(dtype)
    x[:, :, 14:28] = rng.integers(0, 2, size=(4, 10, 14))
    x[:, :, 56:70] = rng.integers(0, 2, size=(4, 10, 14))
    x[:, :, 70] = 0
    return h, x


@pytest.mark.parametrize("arm", MODULE.ARMS)
def test_each_arm_keeps_history_and_does_not_mutate_sources(arm):
    h, x = batch()
    before_h, before_x = h.copy(), x.copy()
    hr, xr = MODULE.normalized_batch_view(h, x, arm)
    np.testing.assert_array_equal(hr, h)
    assert hr.dtype == h.dtype and xr.dtype == x.dtype
    assert not np.shares_memory(hr, h) and not np.shares_memory(xr, x)
    hr.fill(0); xr.fill(0)
    np.testing.assert_array_equal(h, before_h)
    np.testing.assert_array_equal(x, before_x)


def test_full_arm_is_exact_identity_before_future_runner_integration():
    _, x = batch()
    np.testing.assert_array_equal(MODULE.feature_view(x, "history_full"), x)


def test_history_only_removes_values_masks_reliability_and_placeholder():
    _, x = batch()
    assert np.count_nonzero(MODULE.feature_view(x, "history_only")) == 0


def test_history_only_is_invariant_to_every_removed_information_channel():
    _, x = batch()
    other = x.copy()
    other[:, :, :14] += 100
    other[:, :, 14:28] = 1 - other[:, :, 14:28]
    other[:, :, 28:56] -= 33
    other[:, :, 56:70] = 1 - other[:, :, 56:70]
    np.testing.assert_array_equal(MODULE.feature_view(x, "history_only"), MODULE.feature_view(other, "history_only"))


def test_bridge_removes_both_state_and_state_masks_only():
    _, x = batch()
    out = MODULE.feature_view(x, "history_exposure")
    assert not out[:, :, :28].any()
    np.testing.assert_array_equal(out[:, :, 28:], x[:, :, 28:])


def test_value_only_removal_is_not_history_only_control():
    _, x = batch()
    bad = x.copy()
    bad[:, :, :14] = 0
    bad[:, :, 28:56] = 0
    assert np.count_nonzero(bad[:, :, 14:28]) + np.count_nonzero(bad[:, :, 56:70]) > 0
    assert not np.array_equal(bad, MODULE.feature_view(x, "history_only"))


@pytest.mark.parametrize("shape", [(0, 10, 71), (2, 9, 71), (2, 10, 70), (10, 71)])
def test_wrong_shape_is_not_silently_adapted(shape):
    with pytest.raises(ValueError):
        MODULE.feature_view(np.zeros(shape, dtype=float), "history_only")


@pytest.mark.parametrize("channel", [0, 15, 28, 45, 60, 70])
def test_nonfinite_sources_fail_even_in_a_removed_channel(channel):
    _, x = batch()
    x[0, 0, channel] = np.nan
    with pytest.raises(ValueError):
        MODULE.feature_view(x, "history_only")


@pytest.mark.parametrize("channel", [14, 27, 56, 69])
def test_mask_encoding_is_checked(channel):
    _, x = batch()
    x[0, 0, channel] = 0.5
    with pytest.raises(ValueError):
        MODULE.feature_view(x, "history_full")


def test_age_is_a_zero_placeholder_not_a_new_availability_feature():
    _, x = batch()
    x[0, 0, 70] = 1
    with pytest.raises(ValueError):
        MODULE.feature_view(x, "history_full")


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_read_only_source_arrays_and_dtype_are_preserved(dtype):
    h, x = batch(dtype)
    h.setflags(write=False); x.setflags(write=False)
    a, b = MODULE.normalized_batch_view(h, x, "history_exposure")
    assert a.dtype == dtype and b.dtype == dtype
    assert a.flags.writeable and b.flags.writeable


def test_unknown_arm_and_integer_source_are_rejected():
    _, x = batch()
    with pytest.raises(ValueError):
        MODULE.feature_view(x, "without_gate")
    with pytest.raises(ValueError):
        MODULE.feature_view(x.astype(int), "history_only")


def test_bad_history_is_not_fixed_by_removing_features():
    h, x = batch()
    h[0, 0] = np.inf
    with pytest.raises(ValueError):
        MODULE.normalized_batch_view(h, x, "history_only")
    with pytest.raises(ValueError):
        MODULE.normalized_batch_view(np.ones((4, 9)), x, "history_only")


def test_no_target_argument_or_fit_side_effect():
    assert set(inspect.signature(MODULE.normalized_batch_view).parameters) == {"normalized_history", "normalized_features", "arm"}
    design = MODULE.describe_design()
    assert design["training_executed"] is False
    assert design["training_runner_integrated"] is False
    assert design["feature_increment_identified"] is False
    assert design["primary_arms"] == ["history_full", "history_only"]
    assert design["optional_bridge_arm"] == "history_exposure"


def test_channel_partition_is_exhaustive_without_overlap():
    channels = [i for lo, hi in MODULE.CHANNEL_GROUPS.values() for i in range(lo, hi)]
    assert channels == list(range(71))


# An explicitly synthetic carrier with the same encode call pattern, not a
# fake import of the production model or a claim of original-model integration.
import torch
from torch import nn


class SyntheticCarrier(nn.Module):
    def __init__(self):
        super().__init__()
        self.y = nn.Linear(1, 3)
        self.x = nn.Linear(71, 3)
        self.g = nn.Sequential(nn.Linear(3, 3), nn.Sigmoid())
        self.d = nn.Linear(3, 1)

    def _encode_and_gate(self, returns, features):
        hy, hx = self.y(returns.unsqueeze(-1)), self.x(features)
        gate = self.g(hx)
        return hy * gate + hx * (1 - gate)

    def training_objective(self, returns, features):
        a = self._encode_and_gate(returns[:, :-1], features[:, :-1])
        b = self._encode_and_gate(returns[:, 1:], features[:, 1:])
        return ((self.d(a).squeeze(-1) - returns[:, 1:]) ** 2).mean() + ((a - b) ** 2).mean()

    def forecast(self, returns, features):
        return self.d(self._encode_and_gate(returns, features))[:, -1, 0]


def test_subclass_full_view_preserves_state_keys_objective_and_forecast():
    h, x = map(torch.from_numpy, batch())
    torch.manual_seed(11)
    original = SyntheticCarrier()
    wrapped = MODULE.condition_model_class(SyntheticCarrier, "history_full")()
    wrapped.load_state_dict(original.state_dict())
    assert set(wrapped.state_dict()) == set(original.state_dict())
    assert sum(p.numel() for p in wrapped.parameters()) == sum(p.numel() for p in original.parameters())
    torch.testing.assert_close(wrapped.training_objective(h, x), original.training_objective(h, x), rtol=0, atol=0)
    torch.testing.assert_close(wrapped.forecast(h, x), original.forecast(h, x), rtol=0, atol=0)


def test_subclass_history_only_covers_both_training_windows_and_forecast():
    h, x = map(torch.from_numpy, batch())
    other = x.clone()
    other[:, :, :14] += 10; other[:, :, 28:56] -= 4
    other[:, :, 14:28] = 1 - other[:, :, 14:28]
    other[:, :, 56:70] = 1 - other[:, :, 56:70]
    model = MODULE.condition_model_class(SyntheticCarrier, "history_only")()
    torch.testing.assert_close(model.training_objective(h, x), model.training_objective(h, other), rtol=0, atol=0)
    torch.testing.assert_close(model.forecast(h, x), model.forecast(h, other), rtol=0, atol=0)
    model.training_objective(h, x).backward()  # Gradient check only, no optimizer/fit.
    assert torch.count_nonzero(model.x.weight.grad).item() == 0
    assert torch.count_nonzero(model.x.bias.grad).item() > 0


def test_subclass_bridge_excludes_state_masks_but_retains_exposures():
    h, x = map(torch.from_numpy, batch())
    other = x.clone(); other[:, :, :14] += 123; other[:, :, 14:28] = 1 - other[:, :, 14:28]
    model = MODULE.condition_model_class(SyntheticCarrier, "history_exposure")()
    torch.testing.assert_close(model.forecast(h, x), model.forecast(h, other), rtol=0, atol=0)
    changed_beta = x.clone(); changed_beta[:, :, 28:42] += 100
    assert not torch.equal(model.forecast(h, x), model.forecast(h, changed_beta))


def test_subclass_does_not_patch_original_or_silence_bad_input():
    original_method = SyntheticCarrier._encode_and_gate
    h, x = map(torch.from_numpy, batch())
    model = MODULE.condition_model_class(SyntheticCarrier, "history_only")()
    assert SyntheticCarrier._encode_and_gate is original_method
    x[0, 0, 0] = float("nan")
    with pytest.raises(ValueError):
        model.forecast(h, x)
    with pytest.raises(TypeError):
        MODULE.condition_model_class(object, "history_only")
