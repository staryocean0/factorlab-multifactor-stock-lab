from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src/factor_lab/factor_rotation/reaka_r3_x_fine_runner.py"


def load():
    spec = importlib.util.spec_from_file_location("r3fine", SRC)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def synthetic_scores():
    rows=[]; targets=[]; values={k:[] for k in ("F","STATE_VALUE_PLUS_E","E","BETA_RELIABILITY","BETA_ONLY","H")}
    for day in (1,2):
        for i in range(30):
            rows.append([day,i,2018,day-1]); targets.append(float(i))
            base=float(i)
            values["H"].append(-base)
            values["BETA_ONLY"].append(-0.5*base)
            values["BETA_RELIABILITY"].append(0.25*base)
            values["E"].append(0.5*base)
            values["STATE_VALUE_PLUS_E"].append(0.75*base)
            values["F"].append(base)
    return {k:np.asarray(v,float) for k,v in values.items()}, np.asarray(targets,float), np.asarray(rows,int)


def test_budget_is_exactly_three_new_arms_times_two_clocks_times_three_seeds():
    m=load()
    assert m.NEW_ARMS == ("STATE_VALUE_PLUS_E","BETA_ONLY","BETA_RELIABILITY")
    assert m.MAX_NEW_FITS == 18
    assert m.MAX_TOTAL_CYCLES == 54
    assert m.REFERENCE_ARMS == ("F","E","H")


def test_fine_daily_closes_to_coarse_paths():
    m=load(); scores,targets,rows=synthetic_scores()
    frame=m.daily_fine(scores,targets,rows)
    state=frame["STATE_VALUE_PLUS_E_minus_E"]+frame["F_minus_STATE_VALUE_PLUS_E"]
    exposure=frame["BETA_ONLY_minus_H"]+frame["BETA_RELIABILITY_minus_BETA_ONLY"]+frame["E_minus_BETA_RELIABILITY"]
    assert np.allclose(state,frame["F_minus_E"])
    assert np.allclose(exposure,frame["E_minus_H"])
    assert np.allclose(state+exposure,frame["F_minus_H"])


def test_daily_requires_frozen_arm_order():
    m=load(); scores,targets,rows=synthetic_scores()
    bad=dict(scores); bad["EXTRA"]=bad["H"]
    with pytest.raises(ValueError, match="score arm order"):
        m.daily_fine(bad,targets,rows)


def test_reload_worker_refuses_reference_arm_before_runtime_import(tmp_path):
    m=load()
    with pytest.raises(ValueError, match="refuses"):
        m.reload_arm_worker(tmp_path,tmp_path,tmp_path,tmp_path,"F",11,tmp_path,tmp_path)


def test_xcoarse_reconstruction_checks_all_three_existing_contrasts(tmp_path):
    m=load()
    frame=pd.DataFrame({"day_position":[1,2],"F_minus_E":[.1,.2],"E_minus_H":[.3,.4],"F_minus_H":[.4,.6]})
    p=tmp_path/"paired.csv";frame.to_csv(p,index=False)
    m.verify_xcoarse_reconstruction(frame,p)
    changed=frame.copy();changed.loc[0,"E_minus_H"]+=.01
    with pytest.raises(ValueError, match="E_minus_H"):
        m.verify_xcoarse_reconstruction(changed,p)


def test_cli_has_only_generic_fine_reload_worker():
    text=(ROOT/"scripts/reaka_r3_x_fine_compare.py").read_text()
    assert "--reload-fine-worker" in text
    assert "--reload-e-worker" not in text


def test_no_monthly_arm_in_fine_runner():
    text=SRC.read_text()
    assert "F_plus_M_executed" in text
    assert '"F_plus_M_executed": False' in text
    assert "MONTHLY" not in repr(load().NEW_ARMS)
