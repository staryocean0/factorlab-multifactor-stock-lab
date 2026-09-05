"""Small synthetic forward checks; no market inputs, optimization, or fitting."""
from __future__ import annotations

import pytest
import torch
from torch import nn

from factor_lab.factor_rotation.reaka_paper_v1 import (
    ReakaPaperConfig,
    ReakaPaperModel,
    reaka_paper_ablation,
)


def model(arm: str = "without_drc") -> ReakaPaperModel:
    torch.manual_seed(7301)
    return ReakaPaperModel(
        feature_dim=3,
        config=ReakaPaperConfig(latent_dim=2, network_hidden_dim=4, operator_count=2),
        ablation=reaka_paper_ablation(arm),
    ).eval()


class ConstantGate(nn.Module):
    def __init__(self, value: float):
        super().__init__()
        self.value = value

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.full_like(x, self.value)


@pytest.mark.parametrize("gate_value", [0.0, 0.3, 1.0])
def test_gate_weights_return_encoding_not_financial_factor_weights(gate_value):
    m = model()
    m.gate_net = ConstantGate(gate_value)
    with torch.no_grad():
        z, hy, hx, gate = m._encode_and_gate(torch.randn(2, 4), torch.randn(2, 4, 3))
    torch.testing.assert_close(z, gate_value * hy + (1 - gate_value) * hx)
    torch.testing.assert_close(gate, torch.full_like(gate, gate_value))


def test_argmax_fetches_matrix_and_preserves_column_vector_orientation():
    m = model()
    with torch.no_grad():
        m.operators.copy_(torch.tensor([[[1., 0.], [0., 1.]], [[1., 2.], [3., 4.]]]))
        m.selector.weight.zero_()
        m.selector.bias.copy_(torch.tensor([-1., 2.]))
        z = torch.tensor([[[2., 5.], [7., 11.]]])
        advanced, weights, ids = m._transition(z, torch.zeros_like(z), training_gumbel=False)
    torch.testing.assert_close(advanced, torch.tensor([[[12., 26.], [29., 65.]]]))
    assert ids.tolist() == [[1, 1]]
    assert weights.tolist() == [[[0., 1.], [0., 1.]]]


def test_soft_training_operator_is_convex_combination_on_observed_state():
    m = model()
    with torch.no_grad():
        z = torch.randn(2, 4, 2)
        advanced, weights, _ = m._transition(z, torch.zeros_like(z), training_gumbel=True)
        explicit = sum(weights[..., k, None] * (z @ m.operators[k].T) for k in range(2))
    assert bool((weights > 0).all())
    torch.testing.assert_close(weights.sum(-1), torch.ones(2, 4))
    torch.testing.assert_close(advanced, explicit)


def test_latent_residual_identity_and_zero_residual_ablation():
    m = model()
    with torch.no_grad():
        out = m.training_objective(torch.randn(2, 5), torch.randn(2, 5, 3))
    torch.testing.assert_close(out.advanced_latent + out.true_residual, out.next_latent)
    torch.testing.assert_close(out.estimated_residual, torch.zeros_like(out.estimated_residual))
    torch.testing.assert_close(out.corrected_latent, out.advanced_latent)
    torch.testing.assert_close(out.total_loss, out.reconstruction_loss + out.koopman_loss + out.diffusion_loss)


def test_similar_operators_can_be_indistinguishable_on_observed_support():
    # A real transition check: differing unused columns cannot prove distinct dynamics.
    m = model()
    z = torch.tensor([[[1., 0.], [2., 0.]]])
    with torch.no_grad():
        m.operators.copy_(torch.tensor([[[1., 2.], [0., 3.]], [[1., 20.], [0., 30.]]]))
        m.selector.weight.zero_()
        m.selector.bias.copy_(torch.tensor([1., -1.]))
        first = m._transition(z, torch.zeros_like(z), training_gumbel=False)[0]
        m.selector.bias.copy_(torch.tensor([-1., 1.]))
        second = m._transition(z, torch.zeros_like(z), training_gumbel=False)[0]
    assert not torch.equal(m.operators[0], m.operators[1])
    torch.testing.assert_close(first, second)
