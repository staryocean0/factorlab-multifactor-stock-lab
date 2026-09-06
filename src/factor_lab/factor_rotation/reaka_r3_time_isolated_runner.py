"""R3 time-isolated matched F/H runner adapters.

Connects the existing OT2 selector, K1 store builder and K1 training numerics.
Synthetic integration is not market/PIT evidence.
"""
from __future__ import annotations
import hashlib, json, math, os, shutil, subprocess, sys
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np, pandas as pd
from scipy.stats import rankdata, spearmanr

H=20; FREEZE=2016; EVAL=(2018,2020); SEEDS=(11,29,47)
VIEWS={"F":"history_full","H":"history_only"}

def _rt():
    from factor_lab.factor_rotation import reaka_intraday_orthogonal_ot_v1 as ot
    from factor_lab.factor_rotation import reaka_intraday_k1_preflight_v1 as pf
    from factor_lab.factor_rotation import reaka_intraday_k1_training_v1 as tr
    from factor_lab.factor_rotation.reaka_r3_condition_views import condition_model_class
    from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel
    return ot,pf,tr,condition_model_class,Stage6ReakaModel

def sha(b:bytes)->str:return "sha256:"+hashlib.sha256(b).hexdigest()
def jdig(x:Mapping[str,Any])->str:return sha(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode())
def writej(p:Path,x:Mapping[str,Any]): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+"\n")

def mature_positions(calendar, decisions, horizon=H):
    cal=np.asarray(calendar,dtype="datetime64[ns]"); pos=np.asarray(decisions,dtype=np.int64)
    if cal.ndim!=1 or pos.ndim!=1 or not len(cal):raise ValueError("invalid calendar/decisions")
    if len(pos) and ((pos<0).any() or (pos>=len(cal)).any() or np.any(np.diff(pos)<=0)):raise ValueError("decisions must increase")
    years=cal.astype("datetime64[Y]").astype(int)+1970; m=pos+horizon
    keep=(m<len(cal))&(years[pos]>=2009)&(years[pos]<=FREEZE)
    keep&=np.where(m<len(cal),years[np.minimum(m,len(cal)-1)]<=FREEZE,False)
    return pos[keep]

def select_prefix(history_basis,future_basis,calendar,decisions,clock):
    ot,*_=_rt(); dates=pd.DatetimeIndex(np.asarray(calendar)[mature_positions(calendar,decisions)])
    states=ot.build_candidate_states(history_basis,decision_clock=clock); parts=[]
    for y in range(2009,FREEZE+1):
        d=dates[dates.year==y]
        if len(d):
            x=ot.evaluate_annual_tools(candidate_states=states,future_basis=future_basis,decision_dates=d,year=y)
            if len(x):parts.append(x)
    if not parts:raise ValueError("no mature prefix metrics")
    annual=pd.concat(parts,ignore_index=True); selected=ot.select_one_tool_per_family(annual)
    if set(selected.economic_family_id.astype(str))!={"market","size","industry"}:raise ValueError("selector families incomplete")
    return selected,annual

def prepare_store(ot_root:Path,p6_root:Path,out:Path,clock:str):
    ot,pf,*_=_rt(); ot1=ot_root/"ot1"
    hb=pd.read_parquet(ot1/"factor_basis_history.parquet"); fb=pd.read_parquet(ot1/"factor_basis_future.parquet")
    with np.load(ot1/"stock_residual_surfaces.npz",allow_pickle=False) as z: cal=np.asarray(z["calendar"],dtype="datetime64[ns]")
    dec=np.asarray(np.load(p6_root/"decision_positions.npy",allow_pickle=False),dtype=np.int64)
    sel,annual=select_prefix(hb,fb,cal,dec,clock); selected_states=ot.build_selected_states(history_basis=hb,selections=sel,decision_clock=clock)
    sdir=out/"selection";sdir.mkdir(parents=True);annual.to_parquet(sdir/"annual_metrics.parquet",index=False);sel.to_json(sdir/"selected_tools.json",orient="records",indent=2)
    selected_states.to_parquet(sdir/"selected_factor_states.parquet",index=False); sd=sha((sdir/"selected_tools.json").read_bytes())
    overlay=out/"_ot_overlay";(overlay/"ot2").mkdir(parents=True);os.symlink(ot1.resolve(),overlay/"ot1",target_is_directory=True)
    selected_states.to_parquet(overlay/"ot2/selected_factor_states.parquet",index=False)
    try: manifest=pf.materialize_store(output_root=out/"store",ot_root=overlay,p6_root=p6_root,contract_digest=sd,decision_clock=clock)
    finally: shutil.rmtree(overlay,ignore_errors=True)
    return {"store_root":str(out/"store"),"selection_digest":sd,"selected_tools":sel.to_dict(orient="records"),"manifest":manifest}

def matched_models(candidate:Mapping[str,Any],seed:int):
    _,_,tr,view,Base=_rt(); base=tr.build_model(candidate,seed=seed); init={k:v.detach().cpu().clone() for k,v in base.state_dict().items()}; d=tr.state_digest(base); out=[]
    for arm in ("F","H"):
        cls=view(Base,VIEWS[arm]); m=cls(feature_dim=tr.FEATURE_DIM,config=base.config,arm_id="fixed_k_no_residual");m.load_state_dict(init)
        if tr.state_digest(m)!=d:raise ValueError("pre-DMD mismatch")
        out.append(m)
    return out[0],out[1],d

def fit_arm(model,store,normalizer,seed,cycles=3,device="cpu"):
    _,pf,tr,_,_=_rt();import torch
    dev=torch.device(device);model=model.to(dev);train=np.asarray(tr.split_indices(store)["train"],dtype=np.int64)
    if not len(train) or np.any(store.inference_rows[train,2]>FREEZE):raise ValueError("fit rows exceed freeze")
    dmd=tr.initialize_dmd(model,store=store,normalizer=normalizer,train_indices=train,device=dev); opt=torch.optim.Adam(model.parameters(),lr=float(model.config.learning_rate),weight_decay=0.0)
    best=(math.inf,None,None); rows=[]
    for cycle in range(1,cycles+1):
        rng=np.random.default_rng(seed*10000+cycle);order=train[rng.permutation(len(train))];model.train();tot=0.;seen=0
        for start in range(0,len(order),tr.BATCH_SIZE):
            take=order[start:start+tr.BATCH_SIZE];h,x=store.assemble_inputs(take);h,x=pf.normalize_batch(h,x,normalizer);opt.zero_grad(set_to_none=True)
            loss=model.training_objective(torch.from_numpy(h).to(dev),torch.from_numpy(x).to(dev)).total_loss
            if not bool(torch.isfinite(loss)):raise RuntimeError("nonfinite loss")
            loss.backward();opt.step();tot+=float(loss.detach().cpu())*len(take);seen+=len(take)
        c=float(tr.canonical_loss(model,store=store,normalizer=normalizer,indices=train,device=dev));rows.append({"cycle":cycle,"mean_train_loss":tot/seen,"canonical_train_loss":c})
        if c<best[0]:best=(c,cycle,{k:v.detach().cpu().clone() for k,v in model.state_dict().items()})
    model.load_state_dict(best[2]);return model,{"seed":seed,"cycles":rows,"selected_cycle":best[1],"selected_canonical_loss":best[0],"DMD_initialization":dmd,"fit_rows":len(train),"future_target_values_read":0}

def prediction_indices(store):
    y=np.asarray(store.inference_rows[:,2],dtype=np.int64);return np.flatnonzero((y>=EVAL[0])&(y<=EVAL[1])).astype(np.int64)

def score_no_labels(model,store,normalizer,indices,device="cpu"):
    _,pf,tr,_,_=_rt();import torch
    dev=torch.device(device);model=model.to(dev);model.eval();scores=[];rows=[]
    with torch.no_grad():
        for start in range(0,len(indices),tr.BATCH_SIZE):
            take=indices[start:start+tr.BATCH_SIZE];h,x=store.assemble_inputs(take);h,x=pf.normalize_batch(h,x,normalizer);v=model.forecast(torch.from_numpy(h).to(dev),torch.from_numpy(x).to(dev)).scores.detach().cpu().numpy().astype(float)
            if not np.isfinite(v).all():raise RuntimeError("nonfinite score")
            scores.append(v);rows.append(np.asarray(store.inference_rows[take],dtype=np.int64))
    return {"indices":np.asarray(indices),"scores":np.concatenate(scores),"rows":np.concatenate(rows)}

def attach_labels(store,scored):
    idx=np.asarray(scored["indices"],dtype=np.int64);flag=np.zeros(len(store.inference_rows),bool);flag[np.asarray(store.labelled_row_indices,dtype=np.int64)]=True;idx2=idx[flag[idx]];rows=np.asarray(store.inference_rows[idx2],dtype=np.int64);y=np.asarray(store.epsilon_future[rows[:,0],rows[:,1]],dtype=float)
    if not np.isfinite(y).all():raise ValueError("nonfinite target")
    return {"indices":idx2,"scores":np.asarray(scored["scores"])[flag[idx]],"rows":rows,"targets":y}
def rankz(v):
    r=rankdata(v);z=r-r.mean();s=z.std();return z/s if s>0 else np.zeros_like(z)
def ensemble(items):
    if not items:raise ValueError("empty ensemble")
    idx=np.asarray(items[0]["indices"]);rows=np.asarray(items[0]["rows"]);stack=np.stack([np.asarray(x["scores"],float) for x in items]);out=np.zeros(len(idx))
    for x in items[1:]:
        if not np.array_equal(idx,x["indices"]) or not np.array_equal(rows,x["rows"]):raise ValueError("seed coordinates differ")
    for d in np.unique(rows[:,0]):m=rows[:,0]==d;out[m]=np.mean(np.stack([rankz(x[m]) for x in stack]),axis=0)
    return {"indices":idx,"rows":rows,"scores":out}
def paired_daily(f,h,y,rows):
    out=[]
    for d in np.unique(rows[:,0]):
        m=rows[:,0]==d
        if m.sum()<30:continue
        a=float(spearmanr(f[m],y[m]).statistic);b=float(spearmanr(h[m],y[m]).statistic)
        if math.isfinite(a) and math.isfinite(b):out.append({"day_position":int(d),"rankic_F":a,"rankic_H":b,"delta":a-b,"phase":int(rows[m,3][0]),"n":int(m.sum())})
    if not out:raise ValueError("no paired days")
    return pd.DataFrame(out)
def block_ci(v,block,draws=5000,seed=61207):
    x=np.asarray(v,float);rng=np.random.default_rng(seed);starts=np.arange(len(x)-block+1);n=math.ceil(len(x)/block);means=[]
    if len(x)<block or block<=0:raise ValueError("invalid block")
    for _ in range(draws):means.append(np.concatenate([x[s:s+block] for s in rng.choice(starts,n,replace=True)])[:len(x)].mean())
    return {"mean":float(x.mean()),"lower":float(np.quantile(means,.025)),"upper":float(np.quantile(means,.975)),"block_length":block,"draws":draws,"seed":seed}
def save_scores(p:Path,x):
    if p.exists():raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(p,indices=x["indices"],scores=x["scores"],rows=x["rows"])
def reload_worker(store_root,checkpoint,normalizer_path,candidate_path,seed,arm,indices_path,out,device="cpu"):
    _,pf,tr,_,_=_rt();store=pf.IntradayK1InputStore.load(store_root);cand=json.loads(candidate_path.read_text());norm=json.loads(normalizer_path.read_text());f,h,_=matched_models(cand,seed);m=f if arm=="F" else h;tr.load_state_tree(m,checkpoint);s=score_no_labels(m,store,norm,np.load(indices_path,allow_pickle=False),device);save_scores(out,s);return {"score_count":len(s["scores"]),"target_values_read":0,"state_digest":tr.state_digest(m)}
def launch_worker(script:Path,spec:Path):
    p=subprocess.run([sys.executable,str(script),"--reload-worker",str(spec)],capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr[-1000:])
def pair_issues(a,b):
    fields=("seed","clock","recipe_digest","source_digest","environment_digest","selection_digest","normalizer_digest","train_rows_digest","prediction_rows_digest","pre_dmd_state_digest","batch_order_digest")
    return [k for k in fields if a.get(k)!=b.get(k)]
def run_clock(store_root:Path,out:Path,clock:str,candidate:Mapping[str,Any],source_digest:str,environment_digest:str,reload_script:Path,seeds=SEEDS,cycles=3):
    _,pf,tr,_,_=_rt();store=pf.IntradayK1InputStore.load(store_root);norm=pf.normalizer_from_store(store);writej(out/"normalizer.json",norm);writej(out/"candidate.json",candidate);pred=prediction_indices(store);out.mkdir(parents=True,exist_ok=True);np.save(out/"prediction_indices.npy",pred,allow_pickle=False)
    train=np.asarray(tr.split_indices(store)["train"],dtype=np.int64);man=json.loads((store_root/"manifest.json").read_text());sd=str(man.get("contract_digest",man.get("selection_digest","")));sd=sd if sd.startswith("sha256:") else sha(sd.encode());common={"source_digest":source_digest,"environment_digest":environment_digest,"selection_digest":sd,"normalizer_digest":sha((out/"normalizer.json").read_bytes()),"train_rows_digest":sha(np.asarray(store.inference_rows[train]).tobytes()),"prediction_rows_digest":sha(np.asarray(store.inference_rows[pred]).tobytes())}
    scores={"F":[],"H":[]};receipts={"F":[],"H":[]}
    for seed in seeds:
        f,h,pre=matched_models(candidate,seed);pre=pre if str(pre).startswith("sha256:") else sha(str(pre).encode());batch=sha(json.dumps({"seed":seed,"cycles":cycles,"rule":"seed*10000+cycle"},sort_keys=True).encode())
        for arm,m in (("F",f),("H",h)):
            root=out/"models"/f"seed_{seed}"/arm;m,fit=fit_arm(m,store,norm,seed,cycles);ck=root/"checkpoint";tr.save_state_tree(m,ck);spec={"store_root":str(store_root),"checkpoint_root":str(ck),"normalizer_path":str(out/"normalizer.json"),"candidate_path":str(out/"candidate.json"),"seed":seed,"arm":arm,"indices_path":str(out/"prediction_indices.npy"),"output_path":str(root/"scores.npz"),"device_name":"cpu"};writej(root/"reload_spec.json",spec);launch_worker(reload_script,root/"reload_spec.json")
            with np.load(root/"scores.npz",allow_pickle=False) as z:s={k:np.asarray(z[k]) for k in ("indices","scores","rows")};scores[arm].append(s)
            ident={"arm":arm,"seed":seed,"clock":clock,"recipe_digest":jdig(candidate),**common,"pre_dmd_state_digest":pre,"batch_order_digest":batch};receipts[arm].append({"fit":fit,"identity":ident,"checkpoint_state_digest":json.loads((ck/"manifest.json").read_text())["state_digest"]})
        if pair_issues(receipts["F"][-1]["identity"],receipts["H"][-1]["identity"]):raise ValueError("pair identity mismatch")
    F=attach_labels(store,ensemble(scores["F"]));Hh=attach_labels(store,ensemble(scores["H"]));
    if not np.array_equal(F["indices"],Hh["indices"]):raise ValueError("label support mismatch")
    d=paired_daily(F["scores"],Hh["scores"],F["targets"],F["rows"]);d.to_csv(out/"paired_daily.csv",index=False);ci={str(b):block_ci(d.delta,b) for b in (4,8,12) if b<=len(d)};res={"schema_id":"factorlab.r3_time_isolated_clock_result@1.0","clock":clock,"prediction_rows":len(pred),"labelled_rows":len(F["indices"]),"days":len(d),"mean_delta_rankic":float(d.delta.mean()),"median_delta_rankic":float(d.delta.median()),"win_days":int((d.delta>0).sum()),"bootstrap":ci,"seed_receipts":receipts,"fresh_oos":False,"PIT_certified":False,"production_authority":False};writej(out/"result.json",res);return res
