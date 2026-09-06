from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
import torch
from factor_lab.factor_rotation import reaka_r3_time_isolated_runner as r

class FakeOT:
    def __init__(self): self.calls=[]
    def build_candidate_states(self,h,decision_clock): return pd.DataFrame({'x':[1]})
    def evaluate_annual_tools(self,candidate_states,future_basis,decision_dates,year):
        self.calls.append((year,list(decision_dates)))
        if not len(decision_dates): return pd.DataFrame()
        return pd.DataFrame({'economic_family_id':['market','size','industry'],'tool_id':['t','t','t'],'supported':[True]*3,'incremental_net_vs_naked':[1.]*3,'candidate_net':[1.]*3})
    def select_one_tool_per_family(self,annual): return pd.DataFrame({'economic_family_id':['market','size','industry'],'tool_id':['t','t','t']})

class TinyStore:
    def __init__(self):
        rows=[]
        for year,day in [(2016,10),(2018,30),(2019,40),(2020,50)]:
            for s in range(60): rows.append([day,s,year,day%4])
        self.inference_rows=np.asarray(rows,np.int64);self.labelled_row_indices=np.arange(len(rows),dtype=np.int64);self.epsilon_future=np.zeros((60,60),np.float32)
        for row in self.inference_rows:self.epsilon_future[row[0],row[1]]=row[1]/100
        self.batch_used=False
    def assemble_inputs(self,indices):
        n=len(indices);h=np.ones((n,10),np.float32)+self.inference_rows[np.asarray(indices),1,None].astype(np.float32)/100
        f=np.zeros((n,10,71),np.float32);f[:,:,14:28]=1;f[:,:,56:70]=1;return h,f
    def assemble_batch(self,indices): self.batch_used=True;raise AssertionError('labels read in scoring')

class TinyModel(torch.nn.Module):
    def __init__(self,feature_dim=71,config=None,arm_id=None): super().__init__();self.w=torch.nn.Parameter(torch.tensor(.5));self.config=config or SimpleNamespace(learning_rate=.01);self.arm_id=arm_id
    def training_objective(self,returns,features):
        p=self.w*returns.mean(1)+features.mean((1,2))*.1;return SimpleNamespace(total_loss=((p-1)**2).mean(),latent=p[:,None,None],next_latent=p[:,None,None])
    def forecast(self,returns,features): return SimpleNamespace(scores=self.w*returns.mean(1)+features.mean((1,2))*.1)

class FakeTr:
    FEATURE_DIM=71;BATCH_SIZE=64
    def build_model(self,candidate,seed): torch.manual_seed(seed);return TinyModel(config=SimpleNamespace(learning_rate=float(candidate['learning_rate'])))
    def state_digest(self,m): return str(float(m.w.detach()))
    def split_indices(self,store): return {'train':np.flatnonzero(store.inference_rows[:,2]<=2016)}
    def initialize_dmd(self,*a,**kw): return {'ok':True}
    def canonical_loss(self,model,store,normalizer,indices,device):
        h,f=store.assemble_inputs(indices[:64]);return float(model.training_objective(torch.from_numpy(h),torch.from_numpy(f)).total_loss.detach())
    def load_state_tree(self,model,root): model.w.data.copy_(torch.tensor(float((root/'w.txt').read_text())))

class FakePF:
    def normalize_batch(self,h,f,n): return h,f

def condition(base,view):
    class C(base): pass
    return C

def runtime(): return FakeOT(),FakePF(),FakeTr(),condition,TinyModel

def test_maturity_uses_calendar_positions():
    cal=np.arange(np.datetime64('2016-11-01'),np.datetime64('2017-02-01'),dtype='datetime64[D]');got=r.mature_positions(cal,np.array([1,30,60]),20);assert 60 not in got

def test_prefix_selector_never_receives_2017(monkeypatch):
    cal=np.arange(np.datetime64('2009-01-01'),np.datetime64('2017-03-01'),dtype='datetime64[D]');pos=np.arange(0,len(cal),50,dtype=np.int64);ot=FakeOT();monkeypatch.setattr(r,'_rt',lambda:(ot,None,None,None,None));selected,annual=r.select_prefix(pd.DataFrame(),pd.DataFrame(),cal,pos,'14:30');assert len(selected)==3 and len(annual)>0;assert all(y<=2016 for y,_ in ot.calls);assert all(all(d.year<=2016 for d in ds) for _,ds in ot.calls)

def test_matched_models_share_initial_state(monkeypatch):
    monkeypatch.setattr(r,'_rt',runtime);f,h,d=r.matched_models({'learning_rate':.01},11);assert float(f.w.detach())==float(h.w.detach()) and d==str(float(f.w.detach()))

def test_fit_uses_only_prefix(monkeypatch):
    monkeypatch.setattr(r,'_rt',runtime);store=TinyStore();_,receipt=r.fit_arm(TinyModel(config=SimpleNamespace(learning_rate=.01)),store,{},11,2);assert receipt['fit_rows']==60 and receipt['future_target_values_read']==0 and receipt['selected_cycle'] in (1,2)

def test_scoring_never_calls_assemble_batch(monkeypatch):
    monkeypatch.setattr(r,'_rt',runtime);store=TinyStore();s=r.score_no_labels(TinyModel(),store,{},r.prediction_indices(store));assert not store.batch_used and len(s['scores'])==180

def test_labels_attach_after_scores(monkeypatch):
    monkeypatch.setattr(r,'_rt',runtime);store=TinyStore();s=r.score_no_labels(TinyModel(),store,{},r.prediction_indices(store));p=r.attach_labels(store,s);assert len(p['targets'])==180 and np.isfinite(p['targets']).all()

def test_paired_daily_common_support():
    rows=np.vstack([np.column_stack([np.full(40,d),np.arange(40),np.full(40,2018),np.zeros(40)]) for d in (1,2)]);y=np.tile(np.arange(40),2).astype(float);out=r.paired_daily(y,-y,y,rows);assert len(out)==2 and (out.delta>0).all()

def test_rankz_constant_zero(): assert np.all(r.rankz(np.ones(5))==0)

def test_scores_never_overwrite(tmp_path):
    p=tmp_path/'x.npz';x={'indices':np.array([1]),'scores':np.array([.1]),'rows':np.array([[1,2,2018,0]])};r.save_scores(p,x)
    with pytest.raises(FileExistsError):r.save_scores(p,x)

def test_reload_launcher_starts_new_process(tmp_path):
    worker=tmp_path/'w.py';spec=tmp_path/'s.json';spec.write_text('{}');worker.write_text("import sys,pathlib;pathlib.Path(sys.argv[2]).with_suffix('.done').write_text(str(__import__('os').getpid()))");r.launch_worker(worker,spec);assert spec.with_suffix('.done').exists()
