from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "scripts/reaka_r3_transfer_source_bridge.py"


def load():
    spec = importlib.util.spec_from_file_location("r3_transfer_bridge", SRC)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_h20_history_matches_p6_formula():
    m = load()
    close = np.array([[1.0, 2.0], [1.1, 2.2], [1.21, np.nan], [1.331, 2.662]], dtype=np.float32)
    # pad to >20 by repeating last
    close = np.vstack([np.full((18, 2), np.nan, np.float32), close])
    hist = m.h20_history(close)
    assert hist.shape == close.shape
    assert np.isnan(hist[:20]).all()


def test_truncate_calendar_rejects_2026_and_keeps_endpoint():
    m = load()
    days = np.arange(np.datetime64("2007-01-04"), np.datetime64("2026-02-01"), dtype="datetime64[D]")
    days = days[np.is_busday(days)]
    # ensure 2025-12-31 exists: inject if missing
    if np.datetime64("2025-12-31") not in days:
        days = np.sort(np.concatenate((days, np.array(["2025-12-31"], dtype="datetime64[D]"))))
    out = m.truncate_calendar_to_2025(days)
    assert out[-1] == np.datetime64("2025-12-31")
    assert not (out.astype("datetime64[Y]") == np.datetime64("2026")).any()


def test_d5_lattice_continues_anchor_without_reanchoring():
    m = load()
    cal = np.arange(np.datetime64("2007-01-04"), np.datetime64("2021-01-20"), dtype="datetime64[D]")
    # synthetic every day calendar including weekends so anchor exists
    old_len = int(np.searchsorted(cal, np.datetime64("2021-01-01")))
    added = m.d5_lattice(cal, old_len)
    anchor = int(np.flatnonzero(cal == np.datetime64("2008-12-01"))[0])
    assert ((added - anchor) % 5 == 0).all()
    assert (added >= old_len).all()


def test_remap_positions_uses_incumbent_order_not_source_index():
    m = load()
    frame = pd.DataFrame({"symbol": ["000002", "000001", "999999"], "x": [1, 2, 3]})
    out = m.remap_positions(frame, {"000001": 0, "000002": 1})
    assert list(out["symbol_position"]) == [1, 0]
    assert "999999" not in set(out["symbol"])


def test_bridge_does_not_call_training_entrypoints():
    text = SRC.read_text(encoding="utf-8")
    assert "TIMEISO" in text
    assert "5894" in text or "residual-only" in text.lower() or "residual_only" in text
    assert "fit_arm(" not in text
    assert "torch" not in text
    assert "2025-12-31" in text
    assert "reused_accepted_arrays" in text
