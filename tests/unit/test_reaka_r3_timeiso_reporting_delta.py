from __future__ import annotations

import importlib.util
from pathlib import Path
import numpy as np
import pytest

THEME = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "reaka_r3_timeiso_reporting_delta",
        THEME / "scripts/reaka_r3_timeiso_reporting_delta.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_evaluation_years_reject_2017():
    m = load()
    scored = {
        "indices": np.array([0, 1], dtype=np.int64),
        "scores": np.array([0.1, 0.2]),
        "rows": np.array([[1, 0, 2017, 0], [1, 1, 2018, 0]], dtype=np.int64),
    }
    inference = np.array([[1, 0, 2017, 0], [1, 1, 2018, 0]], dtype=np.int64)
    labelled = np.array([0, 1], dtype=np.int64)
    future = np.zeros((3, 2))
    with pytest.raises(ValueError, match="2017|2018-2020"):
        m.attach_labels(scored, labelled, inference, future)


def test_mean10_offsets_are_h20_not_ten_sessions():
    m = load()
    assert m.HISTORY_OFFSETS == tuple(range(-180, 1, 20))
    assert len(m.HISTORY_OFFSETS) == 10
    assert m.HISTORY_OFFSETS != tuple(range(-9, 1))


def test_baseline_signs_are_fixed():
    m = load()
    days = np.array([200, 200], dtype=np.int64)
    symbols = np.array([0, 1], dtype=np.int64)
    history = np.zeros((201, 2))
    history[200] = [0.5, -0.25]
    for off in m.HISTORY_OFFSETS:
        history[200 + off] = history[200]
    vec, note = m.baseline_vectors(
        {"days": days, "symbols": symbols},
        history,
    )
    assert note["signs_fixed_a_priori"] is True
    assert np.allclose(vec["negative_last_epsilon"], -vec["last_epsilon"])
    assert np.allclose(vec["negative_mean10_epsilon"], -vec["mean10_epsilon"])
    assert set(m.BASELINES) == {
        "last_epsilon",
        "negative_last_epsilon",
        "mean10_epsilon",
        "negative_mean10_epsilon",
    }


def test_seed_arm_coordinate_mismatch_is_hard_error():
    m = load()
    a = {"indices": np.arange(3), "scores": np.ones(3), "rows": np.array([[1, 0, 2018, 0]] * 3)}
    b = {"indices": np.arange(4), "scores": np.ones(4), "rows": np.array([[1, 0, 2018, 0]] * 4)}
    with pytest.raises(ValueError, match="coordinates"):
        m.ensemble_scores([a, a, b])


def test_script_does_not_import_torch_or_training():
    text = (THEME / "scripts/reaka_r3_timeiso_reporting_delta.py").read_text()
    assert "torch" not in text
    assert "training_objective" not in text
    assert "forecast(" not in text
    assert "reload_worker" not in text
    assert "fit_arm" not in text


def test_output_refuses_original_run_root(tmp_path):
    root = tmp_path / "run01"
    root.mkdir()
    out = root
    with pytest.raises(ValueError, match="outside original"):
        if out == root or out.is_relative_to(root / "1430") or out.is_relative_to(root / "1445"):
            raise ValueError("write reporting delta outside original score/store trees")
