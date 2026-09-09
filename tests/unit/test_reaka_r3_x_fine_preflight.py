from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src/factor_lab/factor_rotation/reaka_r3_x_fine_preflight.py"
CLI = ROOT / "scripts/reaka_r3_x_fine_compare.py"


def load():
    spec = importlib.util.spec_from_file_location("r3fine_preflight", SRC)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_preflight_source_is_read_only_and_contains_no_fit_or_reload_call():
    text = SRC.read_text(encoding="utf-8")
    assert "fit_arm(" not in text
    assert "reload_arm_worker(" not in text
    assert "--reload-fine-worker" not in text
    assert '"new_fits": 0' in text
    assert '"new_inference": 0' in text


def test_run_checks_both_clocks_before_return(monkeypatch, tmp_path):
    m = load()
    calls = []
    monkeypatch.setattr(m.fine, "validate_source_stack", lambda root: {"source": "ok"})
    monkeypatch.setattr(m.coarse, "validate_runtime_identity", lambda *args: {"runtime": "ok"})
    monkeypatch.setattr(m.fine, "validate_xcoarse_reference", lambda *args: {"runtime_identity": {"xcoarse": "ok"}})

    def fake_clock(timeiso_root, xcoarse_root, clock):
        calls.append(clock)
        return {
            "clock": clock, "seeds": [], "paired_days": 142,
            "xcoarse_reconstruction_verified": True, "new_fits": 0, "new_inference": 0,
        }

    monkeypatch.setattr(m, "preflight_clock", fake_clock)
    out = m.run(tmp_path / "timeiso", tmp_path / "xcoarse", tmp_path / "theme", tmp_path / "factorlab", "commit")
    assert calls == ["1430", "1445"]
    assert out["reference_seed_pairs_checked"] == 6
    assert out["new_fits"] == 0
    assert out["new_inference"] == 0
    assert out["future_result_peeking"] is False


def test_preflight_clock_checks_all_three_seeds_and_reconstructs_xcoarse(monkeypatch, tmp_path):
    m = load()
    # The preflight test intentionally stubs numerical storage: it verifies control-flow
    # and that every accepted seed pair is bound before the coarse reconstruction gate.
    class PF:
        class IntradayK1InputStore:
            @staticmethod
            def load(path):
                return object()

    class TimeIso:
        @staticmethod
        def ensemble(items):
            return items[0]
        @staticmethod
        def attach_labels(store, payload):
            return payload

    monkeypatch.setattr(m.coarse, "_rt", lambda: (PF, None, TimeIso, None, None))
    monkeypatch.setattr(m.fine, "read_json", lambda path: {"identity": {"arm": "F" if "/F/" in str(path) else "H"}})
    seen = []

    def common(f, h):
        return {"pre_dmd_state_digest": "sha256:init", **{key: "x" for key in m.coarse.PAIR_FIELDS}}

    monkeypatch.setattr(m.coarse, "accepted_pair_common", common)

    def valid_e(root, common_identity, seed, clock):
        seen.append((clock, seed))
        return {"checkpoint_state_digest": f"sha256:{clock}:{seed}"}

    monkeypatch.setattr(m.fine, "validate_e_reference_files", valid_e)
    monkeypatch.setattr(m.fine, "_reference_paths", lambda *args: {"F": Path("F"), "E": Path("E"), "H": Path("H")})

    rows = np.array([[1, 0, 2018, 0]] * 30, dtype=np.int64)
    payload = {"indices": np.arange(30), "rows": rows, "scores": np.arange(30, dtype=float), "targets": np.arange(30, dtype=float)}
    monkeypatch.setattr(m.fine, "load_scores", lambda path: {k: np.array(v, copy=True) for k, v in payload.items() if k != "targets"})
    monkeypatch.setattr(m.coarse, "_same_score_coordinates", lambda *items: True)
    monkeypatch.setattr(TimeIso, "attach_labels", staticmethod(lambda store, item: {**item, "targets": payload["targets"]}))
    frame = pd.DataFrame({
        "day_position": [1], "F_minus_E": [0.1], "E_minus_H": [0.2], "F_minus_H": [0.3]
    })
    monkeypatch.setattr(m.coarse, "daily_triplet", lambda *args: frame)
    checked = []
    monkeypatch.setattr(m.fine, "verify_xcoarse_reconstruction", lambda got, path: checked.append((got.copy(), path)))

    out = m.preflight_clock(tmp_path / "timeiso", tmp_path / "xcoarse", "1430")
    assert seen == [("1430", 11), ("1430", 29), ("1430", 47)]
    assert out["paired_days"] == 1
    assert out["new_fits"] == 0 and out["new_inference"] == 0
    assert len(checked) == 1


def test_cli_makes_preflight_mandatory_before_fine_run():
    text = CLI.read_text(encoding="utf-8")
    assert "--preflight-only" in text
    pre = text.index("preflight.run(")
    fit = text.index("fine.run(")
    assert pre < fit
    assert "preflight_receipt" in text
