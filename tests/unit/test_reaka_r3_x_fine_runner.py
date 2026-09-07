from __future__ import annotations

import importlib.util
import json
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


def common_identity(m):
    return {
        "seed": 11, "clock": "1430",
        **{key: f"sha256:{key}" for key in m.coarse.PAIR_FIELDS},
    }


def write_e_reference(root: Path, m, *, change_field=None, future_reads=0, selected_cycle=2, manifest_match=True):
    common=common_identity(m)
    identity={"arm":"E", **common}
    if change_field:
        identity[change_field]="sha256:changed"
    model=root/"models/seed_11/E"
    (model/"checkpoint").mkdir(parents=True)
    losses={1:.9,2:.8,3:.85}
    fit={
        "seed":11,
        "cycles":[{"cycle":c,"canonical_train_loss":losses[c]} for c in (1,2,3)],
        "selected_cycle":selected_cycle,
        "selected_canonical_loss":losses[selected_cycle],
        "fit_rows":361628,
        "future_target_values_read":future_reads,
    }
    digest="sha256:checkpoint"
    (model/"fit_receipt.json").write_text(json.dumps({"fit":fit,"identity":identity,"checkpoint_state_digest":digest}))
    (model/"checkpoint/manifest.json").write_text(json.dumps({"state_digest":digest if manifest_match else "sha256:other"}))
    (model/"reload_spec.json").write_text(json.dumps({"seed":11,"device_name":"cpu","output_path":str(model/"scores.npz")}))
    return common


def test_budget_is_exactly_three_new_arms_times_two_clocks_times_three_seeds():
    m=load()
    assert m.NEW_ARMS == ("STATE_VALUE_PLUS_E","BETA_ONLY","BETA_RELIABILITY")
    assert m.MAX_NEW_FITS == 18
    assert m.MAX_TOTAL_CYCLES == 54
    assert m.REFERENCE_ARMS == ("F","E","H")
    assert m.ARM_ORDER == ("F","STATE_VALUE_PLUS_E","E","BETA_RELIABILITY","BETA_ONLY","H")


def test_source_stack_contract_uses_repository_root(monkeypatch, tmp_path):
    m=load(); seen=[]
    expected={
        "reaka_r3_x_decomposition.py":m.EXPECTED_X_DECOMP_GIT_BLOB,
        "reaka_r3_x_coarse_runner.py":m.EXPECTED_X_COARSE_GIT_BLOB,
    }
    def fake_blob(path):
        seen.append(path)
        return expected[path.name]
    monkeypatch.setattr(m,"_git_blob",fake_blob)
    out=m.validate_source_stack(tmp_path)
    assert out["x_decomposition"] == m.EXPECTED_X_DECOMP_GIT_BLOB
    assert seen == [
        tmp_path/"src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py",
        tmp_path/"src/factor_lab/factor_rotation/reaka_r3_x_coarse_runner.py",
    ]


def test_fine_daily_closes_rankic_and_secondary_to_coarse_paths():
    m=load(); scores,targets,rows=synthetic_scores()
    frame=m.daily_fine(scores,targets,rows)
    for prefix in ("", "decile_", "top30_"):
        state=frame[prefix+"STATE_VALUE_PLUS_E_minus_E"]+frame[prefix+"F_minus_STATE_VALUE_PLUS_E"]
        exposure=frame[prefix+"BETA_ONLY_minus_H"]+frame[prefix+"BETA_RELIABILITY_minus_BETA_ONLY"]+frame[prefix+"E_minus_BETA_RELIABILITY"]
        assert np.allclose(state,frame[prefix+"F_minus_E"])
        assert np.allclose(exposure,frame[prefix+"E_minus_H"])
        assert np.allclose(state+exposure,frame[prefix+"F_minus_H"])


def test_daily_secondary_matches_frozen_decile_and_top30_definition():
    m=load(); scores,targets,rows=synthetic_scores()
    frame=m.daily_fine(scores,targets,rows)
    assert np.allclose(frame["decile_F"], 27.0)
    assert np.allclose(frame["top30_F"], 0.0)
    assert np.allclose(frame["decile_H"], -27.0)


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


def test_accepted_E_reference_requires_frozen_identity_and_minimum_cycle(tmp_path):
    m=load(); common=write_e_reference(tmp_path,m)
    receipt=m.validate_e_reference_files(tmp_path,common,11,"1430")
    assert receipt["identity"]["arm"] == "E"
    assert receipt["fit"]["selected_cycle"] == 2


def test_accepted_E_reference_rejects_identity_drift(tmp_path):
    m=load(); common=write_e_reference(tmp_path,m,change_field="normalizer_digest")
    with pytest.raises(ValueError, match="normalizer_digest"):
        m.validate_e_reference_files(tmp_path,common,11,"1430")


def test_accepted_E_reference_rejects_future_target_or_nonminimum_checkpoint(tmp_path):
    m=load(); common=write_e_reference(tmp_path,m,future_reads=1)
    with pytest.raises(ValueError, match="future target"):
        m.validate_e_reference_files(tmp_path,common,11,"1430")
    other=tmp_path/"other"; common2=write_e_reference(other,m,selected_cycle=3)
    with pytest.raises(ValueError, match="checkpoint selection"):
        m.validate_e_reference_files(other,common2,11,"1430")


def test_selected_cycle_tie_requires_earliest_cycle():
    m=load()
    fit={
        "selected_cycle":2,"selected_canonical_loss":0.8,
        "cycles":[
            {"cycle":1,"canonical_train_loss":0.8},
            {"cycle":2,"canonical_train_loss":0.8},
            {"cycle":3,"canonical_train_loss":0.9},
        ],
    }
    assert m._selected_cycle_is_minimum(fit) is False
    fit["selected_cycle"]=1
    assert m._selected_cycle_is_minimum(fit) is True


def test_accepted_E_reference_rejects_checkpoint_manifest_mismatch(tmp_path):
    m=load(); common=write_e_reference(tmp_path,m,manifest_match=False)
    with pytest.raises(ValueError, match="checkpoint digest"):
        m.validate_e_reference_files(tmp_path,common,11,"1430")


def test_cli_has_mandatory_preflight_and_frozen_entrypoint_blobs():
    text=(ROOT/"scripts/reaka_r3_x_fine_compare.py").read_text()
    assert "--reload-fine-worker" in text
    assert "--reload-e-worker" not in text
    assert "--preflight-only" in text
    assert "EXPECTED_FINE_RUNNER_GIT_BLOB" in text
    assert "EXPECTED_FINE_PREFLIGHT_GIT_BLOB" in text
    assert text.index("validate_theme_entrypoints()") < text.index("preflight.run(") < text.index("fine.run(")


def test_no_monthly_arm_in_fine_runner():
    text=SRC.read_text()
    assert "F_plus_M_executed" in text
    assert '"F_plus_M_executed": False' in text
    assert "MONTHLY" not in repr(load().NEW_ARMS)
