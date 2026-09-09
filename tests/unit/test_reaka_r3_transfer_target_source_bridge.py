from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/reaka_r3_transfer_target_source_bridge.py"
LABEL = ROOT / "scripts/reaka_r3_transfer_label_bridge_v1_1.py"
R2 = ROOT / "scripts/reaka_r2_local_audit_v1.py"


def load():
    spec = importlib.util.spec_from_file_location("r3_entryopen_target_test", SOURCE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_future_target_is_entry_open_t_plus_20_over_t():
    m = load()
    entry = (np.arange(50, dtype=np.float32) + 100.0)[:, None]
    out = m.future_h20_from_entry_open(entry)
    for t in range(30):
        assert out[t, 0] == pytest.approx(float(entry[t + 20, 0] / entry[t, 0] - 1.0), abs=1e-7)
    assert np.isnan(out[-20:]).all()


def test_entry_event_is_first_valid_open_strictly_after_clock():
    m = load()
    day = pd.Timestamp("2024-01-02")
    frame = pd.DataFrame({
        "symbol": ["000001"] * 5,
        "trading_day": [day] * 5,
        "timestamp": [
            "2024-01-02T14:30:00Z", "2024-01-02T14:31:00Z", "2024-01-02T14:32:00Z",
            "2024-01-02T14:46:00Z", "2024-01-02T15:00:00Z",
        ],
        "open": [10.0, 10.1, 10.2, 10.4, 10.5],
    })
    pos = {"000001": 0}
    a = m.select_entry_open(frame, clock="14:30", wanted_days={day}, symbol_position=pos)
    b = m.select_entry_open(frame, clock="14:45", wanted_days={day}, symbol_position=pos)
    assert a.iloc[0].entry_open == pytest.approx(10.1)
    assert int(a.iloc[0].entry_minute) == 14 * 60 + 31
    assert b.iloc[0].entry_open == pytest.approx(10.4)
    assert int(b.iloc[0].entry_minute) == 14 * 60 + 46


def test_invalid_first_open_skips_to_next_valid_minute():
    m = load()
    day = pd.Timestamp("2024-01-02")
    frame = pd.DataFrame({
        "symbol": ["000001"] * 3,
        "trading_day": [day] * 3,
        "timestamp": ["2024-01-02T14:31:00Z", "2024-01-02T14:32:00Z", "2024-01-02T14:33:00Z"],
        "open": [np.nan, -1.0, 10.3],
    })
    got = m.select_entry_open(frame, clock="14:30", wanted_days={day}, symbol_position={"000001": 0})
    assert got.iloc[0].entry_open == pytest.approx(10.3)
    assert int(got.iloc[0].entry_minute) == 14 * 60 + 33


def test_conflicting_duplicate_minute_is_rejected():
    m = load()
    day = pd.Timestamp("2024-01-02")
    frame = pd.DataFrame({
        "symbol": ["000001", "000001"], "trading_day": [day, day],
        "timestamp": ["2024-01-02T14:31:00Z", "2024-01-02T14:31:00Z"],
        "open": [10.0, 11.0],
    })
    with pytest.raises(ValueError, match="ambiguous"):
        m.select_entry_open(frame, clock="14:30", wanted_days={day}, symbol_position={"000001": 0})


def test_structural_anchors_exclude_unmatured_2020_tail():
    m = load()
    cal = np.arange(np.datetime64("2017-01-01"), np.datetime64("2021-01-01"), dtype="datetime64[D]")
    d = np.arange(0, len(cal), 5, dtype=np.int64)
    got = m.structural_mature_anchors(d, cal, 5)
    assert (got + 20 < len(cal)).all()
    assert np.datetime64("2020-12-31") not in cal[got]


def test_price_gate_matches_r2_tolerance_but_target_gate_stays_1e7():
    m = load()
    price = m.price_diff(np.array([100.0]), np.array([100.0005]))
    assert price["passed"]
    target = m.maxdiff(np.array([0.1]), np.array([0.10001]))
    assert not target["passed"]


def test_bounded_calendar_stops_before_2026():
    m = load()
    cal = np.arange(np.datetime64("2007-01-04"), np.datetime64("2026-02-01"), dtype="datetime64[D]")
    got = m.bounded_calendar(cal)
    assert got[-1] == np.datetime64("2025-12-31")
    assert not (got >= np.datetime64("2026-01-01")).any()


def test_r2_auditor_freezes_entry_open_future_formula():
    text = R2.read_text(encoding="utf-8")
    assert 'recon_f[:-HORIZON] = open_[HORIZON:].astype(np.float64) / open_[:-HORIZON].astype(np.float64) - 1.0' in text
    assert 'implemented_and_independently_checked": "entry_open[t+20] / entry_open[t] - 1"' in text
    assert 'frame["time"].gt(clock)' in text
    assert 'frame["time"].le("15:00")' in text


def test_successor_label_bridge_requires_target_source_and_preserves_failed_v1():
    text = LABEL.read_text(encoding="utf-8")
    assert "--target-source-root" in text
    assert "verify_target_source(" in text
    assert "entry_open_t_plus_20_div_entry_open_t_minus_1" in text
    assert "structural_mature_anchors" in text
    assert "future_h20(close)" not in text
    assert (ROOT / "scripts/reaka_r3_transfer_label_bridge.py").exists()


def test_target_and_successor_sources_have_no_model_scoring_entrypoints():
    combined = SOURCE.read_text(encoding="utf-8") + LABEL.read_text(encoding="utf-8")
    for forbidden in ("score_no_labels(", "forecast(", "load_state_tree(", "checkpoint_root", "fit_arm("):
        assert forbidden not in combined
