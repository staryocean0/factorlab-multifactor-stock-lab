from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "src/factor_lab/factor_rotation/reaka_r3_x_coarse_runner.py"


def load():
    spec = importlib.util.spec_from_file_location("r3coarse", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def receipt(arm="F"):
    identity = {"arm": arm, "seed": 11, "clock": "1430"}
    for key in load().PAIR_FIELDS:
        identity[key] = "sha256:" + "a" * 64
    return {"identity": identity}


def test_budget_is_E_only_six_fits():
    m = load()
    assert m.MAX_NEW_FITS == 6
    assert m.MAX_CYCLES_PER_FIT == 3
    text = MOD.read_text()
    assert 'new_arm": "E"' in text
    assert '"rerun_F": 0' in text and '"rerun_H": 0' in text


def test_accepted_pair_common_requires_every_frozen_field():
    m = load(); f = receipt("F"); h = receipt("H")
    common = m.accepted_pair_common(f, h)
    assert common["seed"] == 11
    h["identity"]["normalizer_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="normalizer"):
        m.accepted_pair_common(f, h)


def test_pid_not_part_of_stable_environment_match_but_versions_are():
    m = load()
    a = {k: str(k) for k in m.STABLE_ENV_FIELDS}; b = dict(a)
    a["pid"] = 1; b["pid"] = 2
    assert m.stable_environment_issues(a, b) == []
    b["torch"] = "different"
    assert m.stable_environment_issues(a, b) == ["torch"]


def test_score_coordinate_mismatch_is_hard_error():
    m = load()
    a = {"indices": np.arange(2), "rows": np.zeros((2,4), int), "scores": np.ones(2)}
    b = {"indices": np.arange(3), "rows": np.zeros((3,4), int), "scores": np.ones(3)}
    assert not m._same_score_coordinates(a, b)


def test_daily_triplet_and_summary_keep_both_ordered_contrasts():
    m = load(); rows=[]; target=[]; f=[]; e=[]; h=[]
    for day in (1,2):
        for i in range(30):
            rows.append([day,i,2018,day-1]); target.append(float(i)); f.append(float(i)); e.append(float(i)+0.01); h.append(float(-i))
    frame=m.daily_triplet(np.array(f),np.array(e),np.array(h),np.array(target),np.array(rows))
    s=m.summarize_daily(frame)
    assert set(("F_minus_E","E_minus_H","F_minus_H")) <= set(s)
    assert s["E_minus_H"]["mean"] > 0


def test_accepted_fh_reconstruction_detects_changed_result(tmp_path):
    m = load()
    frame=pd.DataFrame({"day_position":[1,2],"F_minus_H":[0.1,0.2]})
    p=tmp_path/"accepted.csv";pd.DataFrame({"day_position":[1,2],"delta":[0.1,0.3]}).to_csv(p,index=False)
    with pytest.raises(ValueError, match="reconstruction"):
        m.verify_accepted_fh_reconstruction(frame,p)


def test_cli_has_only_E_reload_worker_and_no_FH_run_spec_arm():
    text=(ROOT/"scripts/reaka_r3_x_coarse_compare.py").read_text()
    assert "--reload-e-worker" in text
    assert "--reload-f-worker" not in text and "--reload-h-worker" not in text
