from __future__ import annotations

from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import (
    FIXED_CONFIG,
)


def test_successor_is_one_fixed_nonsearch_configuration() -> None:
    assert FIXED_CONFIG["latent_dimension"] == 8
    assert FIXED_CONFIG["learning_rate"] == 0.03
    assert FIXED_CONFIG["max_cycles"] == 3
    assert FIXED_CONFIG["operator_count"] == 1
    assert FIXED_CONFIG["residual_identity"] == "r0_exact_zero"
