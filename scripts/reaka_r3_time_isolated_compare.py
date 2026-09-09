#!/usr/bin/env python3
"""Run the frozen R3 time-isolated matched F/H experiment locally."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
FACTORLAB_ROOT=Path(os.environ.get("FACTORLAB_ROOT","/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"))

def _bootstrap():
    """Load FactorLab numerical stack, then inject this theme's time-isolated modules."""
    import importlib.util
    src=str(FACTORLAB_ROOT/"src")
    if src not in sys.path:
        sys.path.insert(0,src)
    import factor_lab.factor_rotation as pkg
    theme=ROOT/"src/factor_lab/factor_rotation"
    for name in ("reaka_r3_condition_views","reaka_r3_time_isolation","reaka_r3_time_isolated_runner"):
        dest=f"factor_lab.factor_rotation.{name}"
        spec=importlib.util.spec_from_file_location(dest, theme/f"{name}.py")
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {name}")
        mod=importlib.util.module_from_spec(spec)
        sys.modules[dest]=mod
        spec.loader.exec_module(mod)
        setattr(pkg,name,mod)

_bootstrap()
from factor_lab.factor_rotation.reaka_r3_time_isolated_runner import prepare_store,reload_worker,run_clock

def sha_file(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return "sha256:"+h.hexdigest()
def strict(p:Path):
    def pairs(x):
        d={}
        for k,v in x:
            if k in d:raise ValueError(f"duplicate key:{k}")
            d[k]=v
        return d
    def bad(v):raise ValueError(f"nonfinite:{v}")
    x=json.loads(p.read_text(),object_pairs_hook=pairs,parse_constant=bad)
    if not isinstance(x,dict):raise ValueError("spec must be object")
    return x
def git_head():
    p=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True);return p.stdout.strip() if p.returncode==0 else "unavailable"
def digest(x):return "sha256:"+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def records(device):
    import pandas as pd, torch
    source={"git_commit":git_head(),"runner_sha256":sha_file(ROOT/"src/factor_lab/factor_rotation/reaka_r3_time_isolated_runner.py"),"cli_sha256":sha_file(Path(__file__))}
    env={"python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"pandas":pd.__version__,"torch":torch.__version__,"device":device,"cuda_available":bool(torch.cuda.is_available()),"pid":os.getpid()}
    return source,env
def run(spec_path:Path):
    s=strict(spec_path)
    if s.get("schema_id")!="factorlab.r3_time_isolated_run_spec@1.0":raise ValueError("wrong schema")
    out=Path(s["output_root"]).resolve()
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);device=str(s.get("device_name","cpu"))
    if device!="cpu":raise ValueError("frozen design requires identical CPU F/H backend")
    source,env=records(device);expected=s.get("expected_source_commit")
    if expected and source["git_commit"]!=expected:raise ValueError("source commit mismatch")
    (out/"source_snapshot.json").write_text(json.dumps(source,indent=2,ensure_ascii=False)+"\n");(out/"environment.json").write_text(json.dumps(env,indent=2,ensure_ascii=False)+"\n")
    cand=s.get("candidate") or {"candidate_id":"r3_time_isolated_d8_h8_k1_r0","latent_dimension":8,"hidden_dimension":8,"operator_count":1,"residual_identity":"r0_exact_zero","learning_rate":0.03}
    clocks=s.get("clocks")
    if not isinstance(clocks,dict) or set(clocks)!={"1430","1445"}:raise ValueError("both clocks required")
    result={}
    for suffix in ("1430","1445"):
        cfg=clocks[suffix];clock="14:30" if suffix=="1430" else "14:45";root=out/suffix
        prep=prepare_store(Path(cfg["ot_root"]),Path(cfg["p6_root"]),root/"prepared",clock)
        exp=run_clock(Path(prep["store_root"]),root/"experiment",suffix,cand,digest(source),digest(env),Path(__file__))
        result[suffix]={"prepared":prep,"result":exp}
    final={"schema_id":"factorlab.r3_time_isolated_run_result@1.0","status":"completed_consumed_historical_only","source":source,"environment":env,"clocks":result,"fresh_oos":False,"PIT_certified":False,"production_authority":False}
    (out/"result.json").write_text(json.dumps(final,indent=2,ensure_ascii=False,allow_nan=False)+"\n");return final
def main():
    p=argparse.ArgumentParser();p.add_argument("--spec",type=Path);p.add_argument("--reload-worker",type=Path);a=p.parse_args()
    try:
        if a.reload_worker:
            s=strict(a.reload_worker);x=reload_worker(Path(s["store_root"]),Path(s["checkpoint_root"]),Path(s["normalizer_path"]),Path(s["candidate_path"]),int(s["seed"]),str(s["arm"]),Path(s["indices_path"]),Path(s["output_path"]),str(s.get("device_name","cpu")));print(json.dumps(x));return 0
        if not a.spec:raise ValueError("--spec required")
        x=run(a.spec);print(json.dumps({"status":x["status"]},ensure_ascii=False));return 0
    except Exception as e:
        print(json.dumps({"status":"failed","error":f"{type(e).__name__}: {e}"},ensure_ascii=False));return 1
if __name__=="__main__":raise SystemExit(main())
