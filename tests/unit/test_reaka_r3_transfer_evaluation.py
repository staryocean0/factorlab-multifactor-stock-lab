from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "src/factor_lab/factor_rotation/reaka_r3_transfer_evaluation.py"

def load():
    spec = importlib.util.spec_from_file_location("r3_transfer_eval_test", MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

def writej(path, body):
    path.write_text(json.dumps(body), encoding="utf-8")

def sha(path):
    return load().sha_file(path)

def make_feature(root: Path, years=(2020,2021,2025)):
    root.mkdir(parents=True)
    cal = np.arange(np.datetime64("2020-12-01"), np.datetime64("2026-01-01"), dtype="datetime64[D]")
    np.save(root/"calendar.npy", cal.astype("datetime64[ns]"))
    syms=np.array(["000001","000002","000003"])
    np.save(root/"symbols.npy", syms)
    writej(root/"factor_ids.json", {"factor_ids":[f"f{i}" for i in range(14)]})
    rows=[]
    for d in [40, 50, 100, len(cal)-30, len(cal)-10]:
        for s in range(3):
            y=int(str(cal[d])[:4])
            if y>=2021:
                rows.append([d,s,y,0])
    rows=np.array(rows,dtype=np.int64)
    np.save(root/"inference_rows.npy", rows)
    pred=np.arange(len(rows), dtype=np.int64)
    np.save(root/"prediction_indices.npy", pred)
    mature=pred[rows[:,0]+20<len(cal)]
    np.save(root/"maturity_eligible_indices.npy", mature)
    writej(root/"normalizer.json", {"fit_end_year":2016,"target_used":False,
        "return_mean":0.,"return_scale":1.,"beta_mean":0.,"beta_scale":1.,"reliability_mean":0.,"reliability_scale":1.})
    manifest={"schema_id":"factorlab.r3_transfer_feature_store@1.0","status":"prepared_features_only_not_scored",
        "calendar_end":"2025-12-31","new_model_fits":0,"labels_read":False}
    writej(root/"manifest.json",manifest)
    return cal, syms, rows

def make_reference(root: Path, cal, syms):
    root.mkdir(parents=True)
    refcal=cal[:35]
    np.save(root/"calendar.npy", refcal.astype("datetime64[ns]"))
    np.save(root/"symbols.npy", syms)
    writej(root/"factor_ids.json",{"factor_ids":[f"f{i}" for i in range(14)]})
    eps=np.full((len(refcal),len(syms)),np.nan,np.float32)
    eps[10:]=0.25
    np.save(root/"epsilon_future.npy",eps)
    writej(root/"manifest.json",{"artifact_digests":{}})
    return eps

def make_label_bundle(root: Path, cal, syms, ref_eps):
    root.mkdir(parents=True)
    np.save(root/"calendar.npy",cal.astype("datetime64[ns]"))
    order=np.array([2,0,1])
    np.save(root/"symbols.npy",syms[order])
    writej(root/"factor_ids.json",{"factor_ids":[f"f{i}" for i in range(14)]})
    folds=np.array([2,0,1],dtype=np.int64)
    np.save(root/"symbol_fold_ids.npy",folds)
    base=np.full((len(cal),len(syms)),np.nan,np.float32)
    base[:len(ref_eps)] = ref_eps
    for d in range(35,len(cal)):
        base[d]=np.array([d,d+1,d+2],np.float32)
    eps=base[:,order]
    np.save(root/"epsilon_future.npy",eps)
    writej(root/"producer_sources.json",{"schema_id":"x"})
    m=load()
    artifacts={n:m.sha_file(root/n) for n in ("calendar.npy","symbols.npy","factor_ids.json","symbol_fold_ids.npy","epsilon_future.npy","producer_sources.json")}
    bundle={"schema_id":m.LABEL_SCHEMA,"clock":"1430","calendar_end":"2025-12-31","contains_2026":False,
        "target_definition":"H20_financial_residual_epsilon_future_K1_v1","horizon_trading_positions":20,
        "labels_used_for_features":False,"fold_policy":"explicit_incumbent_symbol_position_mod5",
        "artifact_digests":artifacts}
    writej(root/"bundle.json",bundle)
    return bundle

def test_score_plan_is_exactly_24_and_label_free(tmp_path):
    m=load()
    jobs=m.make_score_jobs(tmp_path/"timeiso",tmp_path/"xfine",tmp_path/"features",tmp_path/"out",tmp_path/"repo",tmp_path/"fl")
    assert len(jobs)==24
    assert {(j["clock"],j["seed"],j["arm"]) for j in jobs} == {(c,s,a) for c in m.CLOCKS for s in m.SEEDS for a in m.ARMS}
    assert all(not any("label" in k.lower() or "target" in k.lower() for k in j) for j in jobs)

def test_label_sidecar_maps_symbols_checks_prefix_and_excludes_unmatured(tmp_path):
    m=load()
    f=tmp_path/"feature"; cal,syms,rows=make_feature(f)
    r=tmp_path/"ref"; make_reference(r,cal,syms)
    b=tmp_path/"bundle"; make_label_bundle(b,cal,syms,np.load(r/"epsilon_future.npy"))
    out=tmp_path/"side"
    result=m.build_label_sidecar(f,b,r,out,expected_bundle_sha256=m.sha_file(b/"bundle.json"),
        expected_reference_manifest_sha256=m.sha_file(r/"manifest.json"))
    assert result["status"]=="prepared_postscore_labels_not_model_input"
    eval_idx=np.load(out/"evaluation_indices.npy")
    assert np.all(rows[eval_idx,0]+20<len(cal))
    assert result["uses_2026_to_complete_2025"] is False
    assert result["prefix_check"]["passed"]

def test_label_prefix_drift_is_hard_error(tmp_path):
    m=load()
    f=tmp_path/"feature"; cal,syms,_=make_feature(f)
    r=tmp_path/"ref"; ref=make_reference(r,cal,syms)
    b=tmp_path/"bundle"; make_label_bundle(b,cal,syms,ref)
    eps=np.load(b/"epsilon_future.npy")
    eps[20,1]+=1
    np.save(b/"epsilon_future.npy",eps)
    bundle=json.loads((b/"bundle.json").read_text())
    bundle["artifact_digests"]["epsilon_future.npy"]=m.sha_file(b/"epsilon_future.npy")
    writej(b/"bundle.json",bundle)
    with pytest.raises(ValueError,match="historical target prefix"):
        m.build_label_sidecar(f,b,r,tmp_path/"side",expected_bundle_sha256=m.sha_file(b/"bundle.json"),
            expected_reference_manifest_sha256=m.sha_file(r/"manifest.json"))

def test_2026_label_bundle_rejected(tmp_path):
    m=load()
    f=tmp_path/"feature"; cal,syms,_=make_feature(f)
    r=tmp_path/"ref"; ref=make_reference(r,cal,syms)
    b=tmp_path/"bundle"; make_label_bundle(b,cal,syms,ref)
    body=json.loads((b/"bundle.json").read_text()); body["contains_2026"]=True; writej(b/"bundle.json",body)
    with pytest.raises(ValueError,match="2026"):
        m.build_label_sidecar(f,b,r,tmp_path/"side",expected_bundle_sha256=m.sha_file(b/"bundle.json"),
            expected_reference_manifest_sha256=m.sha_file(r/"manifest.json"))

def test_daily_transfer_primary_and_secondaries():
    m=load()
    rows=[]; y=[]; scores={a:[] for a in m.ARMS}
    for day in (10,20):
        for i in range(40):
            rows.append([day,i,2022,day//10%4]); y.append(float(i))
            scores["F"].append(float(i))
            scores["STATE_VALUE_PLUS_E"].append(float(-i))
            scores["BETA_ONLY"].append(float(-i))
            scores["BETA_RELIABILITY"].append(float(i))
    frame=m.daily_transfer({a:np.array(scores[a]) for a in m.ARMS},np.array(y),np.array(rows))
    assert (frame["F_minus_STATE_VALUE_PLUS_E"]>0).all()
    assert (frame["BETA_RELIABILITY_minus_BETA_ONLY"]>0).all()
    assert (frame["decile_F_minus_STATE_VALUE_PLUS_E"]>0).all()
    assert (frame["top30_BETA_RELIABILITY_minus_BETA_ONLY"]>0).all()

def test_evaluation_join_requires_exact_rows():
    m=load()
    score={"indices":np.array([0,1,2]),"rows":np.array([[1,0,2022,0],[1,1,2022,0],[1,2,2022,0]]),"scores":np.ones(3)}
    side={"evaluation_indices":np.array([0,2]),"rows":np.array([[1,0,2022,0],[1,2,2022,0]]),"targets":np.ones(2)}
    assert m._select_evaluation(score,side).tolist()==[0,2]
    side["rows"][1,1]=99
    with pytest.raises(ValueError,match="rows disagree"):
        m._select_evaluation(score,side)

def test_seed_ensemble_is_daily_rankz_equal_weight():
    m=load()
    rows=np.array([[1,0],[1,1],[1,2],[2,0],[2,1],[2,2]])
    idx=np.arange(6)
    items=[]
    for shift in (0,10,100):
        items.append({"indices":idx,"rows":rows,"scores":np.array([1,2,3,3,2,1],float)+shift})
    out=m._ensemble_seed_scores(items)
    assert np.allclose(out[:3],m.rankz(np.array([1,2,3])))
    assert np.allclose(out[3:],m.rankz(np.array([3,2,1])))

def test_combined_clock_is_equal_clock_average(tmp_path):
    m=load()
    for c,vals in (("1430",[0.1,0.2]),("1445",[0.3,0.4])):
        d=tmp_path/c;d.mkdir()
        frame=pd.DataFrame({"day_position":[1,2],"year":[2022,2022],"phase":[0,1],
            m.PRIMARY[0]:vals,m.PRIMARY[1]:vals,
            "decile_"+m.PRIMARY[0]:vals,"decile_"+m.PRIMARY[1]:vals,
            "top30_"+m.PRIMARY[0]:vals,"top30_"+m.PRIMARY[1]:vals})
        frame.to_csv(d/"paired_daily.csv",index=False)
    out=m.combine_clocks(tmp_path,tmp_path)
    combined=pd.read_csv(tmp_path/"combined_daily.csv")
    assert np.allclose(combined[m.PRIMARY[0]],[0.2,0.3])
    assert out["days"]==2

def test_worker_source_contains_no_label_open():
    m=load()
    import inspect
    text=inspect.getsource(m.run_score_worker)
    assert "label_bundle" not in text
    assert "epsilon_future" not in text
    assert "targets" not in text

def test_sidecar_is_postscore_only_contract(tmp_path):
    m=load()
    assert m.SIDECAR_SCHEMA == "factorlab.r3_transfer_label_sidecar@1.0"

def test_block_ci_rejects_short_input():
    m=load()
    with pytest.raises(ValueError):
        m.block_ci(np.array([1.,2.]),4)

def test_label_fold_identity_rejected(tmp_path):
    m=load()
    f=tmp_path/"feature"; cal,syms,_=make_feature(f)
    r=tmp_path/"ref"; ref=make_reference(r,cal,syms)
    b=tmp_path/"bundle"; make_label_bundle(b,cal,syms,ref)
    folds=np.load(b/"symbol_fold_ids.npy"); folds[0]=4; np.save(b/"symbol_fold_ids.npy",folds)
    body=json.loads((b/"bundle.json").read_text());body["artifact_digests"]["symbol_fold_ids.npy"]=m.sha_file(b/"symbol_fold_ids.npy");writej(b/"bundle.json",body)
    with pytest.raises(ValueError,match="fold identity"):
        m.build_label_sidecar(f,b,r,tmp_path/"side",expected_bundle_sha256=m.sha_file(b/"bundle.json"),
            expected_reference_manifest_sha256=m.sha_file(r/"manifest.json"))

def test_label_sidecar_cli_fresh_process(tmp_path):
    m=load()
    f=tmp_path/"feature"; cal,syms,_=make_feature(f)
    r=tmp_path/"ref"; ref=make_reference(r,cal,syms)
    b=tmp_path/"bundle"; make_label_bundle(b,cal,syms,ref)
    spec={"feature_store":str(f),"label_bundle":str(b),"reference_label_store":str(r),
          "output_root":str(tmp_path/"side"),"label_bundle_sha256":m.sha_file(b/"bundle.json"),
          "reference_manifest_sha256":m.sha_file(r/"manifest.json")}
    sp=tmp_path/"spec.json";sp.write_text(json.dumps(spec))
    cli=ROOT/"scripts/reaka_r3_transfer_evaluate.py"
    proc=__import__("subprocess").run([sys.executable,str(cli),"--build-label-sidecar",str(sp)],
                                      capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr+proc.stdout
    assert (tmp_path/"side/manifest.json").exists()
