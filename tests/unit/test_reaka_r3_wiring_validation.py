"""Actual successor guard tests; synthetic collaborators, no FactorLab fits.

The wiring body is extracted verbatim except for replacing local imports with
explicit synthetic collaborators. This is NOT full numerical-module integration.
"""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import numpy as np
import pytest
import torch

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/reaka_r3_condition_compare.py'
SPEC=importlib.util.spec_from_file_location('r3_wiring_successor_under_test', SCRIPT)
assert SPEC and SPEC.loader
RUNNER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def good_receipt():
    return {k: 0.0 for k in ('f_wrap_loss_gap','f_wrap_latent_gap','h_x_loss_gap','h_x_latent_gap','h_x_forecast_gap')} | {'f_forecast_finite':True}


def test_real_guard_accepts_finite_zero_and_keeps_original_thresholds():
    report=good_receipt()
    report['f_wrap_loss_gap']=1e-6
    for name in ('f_wrap_latent_gap','h_x_latent_gap','h_x_forecast_gap'):
        report[name]=1e-5
    RUNNER.validate_wiring_receipt(report)


@pytest.mark.parametrize('name', ['f_wrap_loss_gap','f_wrap_latent_gap','h_x_loss_gap','h_x_latent_gap','h_x_forecast_gap'])
@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-float('inf'),None,-1.0,True])
def test_real_guard_rejects_nonfinite_or_invalid_gap(name,bad):
    report=good_receipt();report[name]=bad
    with pytest.raises(ValueError):
        RUNNER.validate_wiring_receipt(report)


@pytest.mark.parametrize('bad',[False,0,1,None])
def test_real_guard_requires_true_finite_forecast(bad):
    report=good_receipt();report['f_forecast_finite']=bad
    with pytest.raises(ValueError):
        RUNNER.validate_wiring_receipt(report)


def test_real_guard_rejects_missing_or_excessive_gap():
    for op in ('missing','excessive'):
        report=good_receipt()
        if op=='missing': del report['h_x_forecast_gap']
        else: report['h_x_forecast_gap']=2e-5
        with pytest.raises(ValueError): RUNNER.validate_wiring_receipt(report)


def wiring_with_synthetic_outputs(value: float):
    node=next(n for n in ast.parse(SCRIPT.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='wiring_check')
    node.body=[n for n in node.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
    code=compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(SCRIPT),'exec')
    class SyntheticModel:
        def to(self,device): return self
        def training_objective(self,r,x):
            return SimpleNamespace(total_loss=torch.tensor(value),latent=torch.full((8,9,8),value))
        def forecast(self,r,x): return SimpleNamespace(scores=torch.full((8,),value))
    class SyntheticStore:
        inference_rows=np.array([[200+i,i,2016,i%4] for i in range(8)])
        def assemble_inputs(self,indices):
            return np.zeros((8,10),dtype=np.float32),np.zeros((8,10,71),dtype=np.float32)
    env={'np':np,'torch':torch,'Any':Any,'FIXED_CONFIG':{},
         'split_indices':lambda store:{'train':np.arange(8)},
         'normalize_batch':lambda h,x,n:(h,x),
         'build_model':lambda *a,**kw:SyntheticModel(),
         'build_controlled_model':lambda *a,**kw:SyntheticModel(),
         'validate_wiring_receipt':RUNNER.validate_wiring_receipt}
    exec(code,env)
    return env['wiring_check'](SyntheticStore(),{},torch.device('cpu'))


def test_actual_wiring_body_calls_guard_and_keeps_finite_control():
    report=wiring_with_synthetic_outputs(0.)
    assert report['passed'] is True
    assert report['2017_metrics_read'] is False


@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_actual_wiring_body_rejects_the_old_false_pass_counterexample(value):
    with pytest.raises(ValueError): wiring_with_synthetic_outputs(value)
