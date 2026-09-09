from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reaka_r3_transfer_target_lineage_diag.py"


def load():
    spec = importlib.util.spec_from_file_location("r3_target_lineage_diag_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_structural_mature_anchors_exclude_tail_without_t_plus_20():
    m = load()
    cal = np.arange(np.datetime64("2017-01-01"), np.datetime64("2021-01-01"), dtype="datetime64[D]")
    decisions = np.arange(0, len(cal), 5, dtype=np.int64)
    got = m.structural_mature_anchors(decisions, cal, count=5, horizon=20)
    assert len(got) == 5
    assert (got + 20 < len(cal)).all()
    assert int(got[-1]) + 20 < len(cal)
    assert np.datetime64("2020-12-31") not in cal[got]


def test_anchor_choice_is_date_structure_only():
    m = load()
    cal = np.arange(np.datetime64("2017-01-01"), np.datetime64("2021-01-01"), dtype="datetime64[D]")
    decisions = np.arange(0, len(cal), 5, dtype=np.int64)
    first = m.structural_mature_anchors(decisions, cal, count=5)
    second = m.structural_mature_anchors(decisions.copy(), cal.copy(), count=5)
    np.testing.assert_array_equal(first, second)


def test_maxdiff_rejects_support_drift_and_numeric_drift():
    m = load()
    good = m.maxdiff(np.array([1.0, np.nan]), np.array([1.0 + 1e-8, np.nan]))
    assert good["passed"]
    support = m.maxdiff(np.array([1.0, np.nan]), np.array([1.0, 0.0]))
    assert not support["passed"] and support["support_mismatches"] == 1
    numeric = m.maxdiff(np.array([1.0, np.nan]), np.array([1.01, np.nan]))
    assert not numeric["passed"] and numeric["above_tolerance"] == 1


def test_maxdiff_shape_drift_is_not_silently_compared():
    m = load()
    out = m.maxdiff(np.zeros(2), np.zeros(3))
    assert out["passed"] is False
    assert out["shape_match"] is False


def test_required_future_raw_does_not_guess_alternative(tmp_path):
    m = load()
    (tmp_path / "some_future_1430_candidate.npy").write_bytes(b"not an npy")
    with pytest.raises(FileNotFoundError, match="Do not substitute"):
        m.find_required_future_raw(tmp_path, "1430")
    expected = tmp_path / "future_h20_raw_1430.npy"
    expected.write_bytes(b"identity only")
    assert m.find_required_future_raw(tmp_path, "1430") == expected


def test_self_test_runs_without_factorlab_or_market_arrays():
    m = load()
    result = m.self_test()
    assert result["status"] == "self_test_passed"
    assert len(result["anchors"]) == 5


def test_diagnostic_source_contains_no_scoring_or_sidecar_execution():
    text = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "score_no_labels(",
        "forecast(",
        "load_state_tree(",
        "build_label_sidecar(",
        "checkpoint_root",
        "--run",
    ):
        assert forbidden not in text
    assert "historical_artifact_replay_with_current_OT_code" in text
    assert "contains_2026_target" in text
    assert "structural_mature_anchors" in text


def test_diagnosis_precedence_is_conservative_in_source():
    text = SCRIPT.read_text(encoding="utf-8")
    replay = text.index('if not replay_future["passed"]')
    raw = text.index('elif not raw_future_compare["passed"]')
    basis = text.index('elif not basis_future_compare["passed"]')
    rebuilt = text.index('elif not rebuilt_future["passed"]')
    assert replay < raw < basis < rebuilt
    assert "historical_artifact_replay_failed_recover_historical_producer_or_membership_before_extension" in text
