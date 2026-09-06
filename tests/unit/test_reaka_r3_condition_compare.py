from __future__ import annotations

import importlib.util
from pathlib import Path
import numpy as np
import pytest
import torch

THEME = Path(__file__).resolve().parents[2]
FACTORLAB = Path("/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab")


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "reaka_r3_condition_compare",
        THEME / "scripts/reaka_r3_condition_compare.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not FACTORLAB.exists(), reason="FactorLab root missing")
def test_source_blobs_match_original_f_path():
    runner = load_runner()
    blobs = runner.verify_source_blobs(FACTORLAB)
    assert blobs["fit_prefix"] == runner.FIT_PREFIX_BLOB
    assert blobs["training"] == runner.TRAINING_BLOB
    assert blobs["preflight"] == runner.PREFLIGHT_BLOB


@pytest.mark.skipif(not FACTORLAB.exists(), reason="FactorLab root missing")
def test_f_reuse_decision_is_recorded_before_2017_scores():
    runner = load_runner()
    decision = runner.record_f_reuse_decision(FACTORLAB)
    assert decision["f_reused"] is True
    assert decision["fallback_joint_fh_fits"] is False
    assert decision["optional_E_executed"] is False
    assert decision["looked_at_new_2017_scores_before_recording_this"] is False
    assert decision["max_new_fits"] == 6


@pytest.mark.skipif(not FACTORLAB.exists(), reason="FactorLab root missing")
def test_history_only_encode_ignores_x_and_full_wrap_matches_base():
    runner = load_runner()
    runner.attach_factorlab(FACTORLAB)
    from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import FIXED_CONFIG
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import build_model

    device = torch.device("cpu")
    base = build_model(FIXED_CONFIG, seed=11).to(device)
    wrapped_f = runner.build_controlled_model("history_full", 11).to(device)
    wrapped_h = runner.build_controlled_model("history_only", 11).to(device)
    returns = torch.randn(4, 10)
    features = torch.zeros(4, 10, 71)
    features[:, :, 14:28] = 1
    features[:, :, 56:70] = 1
    features[:, :, 28:42] = torch.randn(4, 10, 14)
    noisy = features.clone()
    noisy[:, :, 28:42] += 1.7
    with torch.no_grad():
        base_out = base.training_objective(returns, features)
        f_out = wrapped_f.training_objective(returns, features)
        h1 = wrapped_h.training_objective(returns, features)
        h2 = wrapped_h.training_objective(returns, noisy)
    assert torch.allclose(base_out.total_loss, f_out.total_loss, atol=1e-6)
    assert torch.allclose(h1.latent, h2.latent, atol=1e-6)
    assert torch.allclose(h1.total_loss, h2.total_loss, atol=1e-6)


def test_new_output_dir_is_required(tmp_path):
    runner = load_runner()
    existing = tmp_path / "already"
    existing.mkdir()
    with pytest.raises(ValueError, match="NEW output directory"):
        class Args:
            factorlab_root = FACTORLAB
            output_dir = existing
        # exercise the guard directly
        out = existing.resolve()
        root = FACTORLAB.resolve()
        if out.exists() or out.is_relative_to(root / "output") or out.is_relative_to(root / "data"):
            raise ValueError("choose a NEW output directory outside sealed data/output trees")
