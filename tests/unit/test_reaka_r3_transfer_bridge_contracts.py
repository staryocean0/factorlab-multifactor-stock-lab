"""Synthetic boundary contracts; no raw finance data or producer is fabricated."""
from pathlib import Path
import importlib.util
import sys
import numpy as np
import pandas as pd
import pytest

P=Path(__file__).resolve().parents[2]/'scripts/reaka_r3_transfer_source_bridge.py'
spec=importlib.util.spec_from_file_location('r3_bridge_contract_test', P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)


def test_finite_h20_values_are_actually_checked():
    p=(np.arange(26,dtype=np.float32)+1)[:,None]
    h=m.h20_history(p)
    for t in range(20,26):
        assert h[t,0]==np.float32(p[t,0]/p[t-20,0]-1)


def test_h20_does_not_read_later_prices():
    p=(np.arange(50,dtype=np.float32)+1)[:,None]
    q=p.copy();q[30:]=12345
    np.testing.assert_array_equal(m.h20_history(p)[:30],m.h20_history(q)[:30])


def test_tail_basis_preserves_original_finite_support_and_global_positions():
    dates=np.array(['2021-01-04','2021-01-05','2021-01-06'],dtype='datetime64[D]')
    basis=np.array([[[.1],[np.nan],[.2]]])
    f=m._basis_frame('1430',dates,basis,['market'],('fold_0',),start_position=3406)
    assert f.day_position.tolist()==[3406,3408]
    assert f.trading_day.tolist()==[pd.Timestamp('2021-01-04'),pd.Timestamp('2021-01-06')]
    assert f.available.tolist()==[True,True]
    assert np.isfinite(f.orthogonal_return).all()


@pytest.mark.parametrize('invalid',[np.nan,np.inf,-np.inf])
def test_original_finite_row_policy_rejects_nonfinite_support(invalid):
    b=np.array([[[.2],[invalid]]]);d=np.array(['2021-01-04','2021-01-05'],dtype='datetime64[D]')
    f=m._basis_frame('1430',d,b,['f'],('v',))
    assert len(f)==1


def test_basis_all_finite_values_unchanged():
    b=np.arange(8,dtype=float).reshape(2,2,2);d=np.array(['2021-01-04','2021-01-05'],dtype='datetime64[D]')
    f=m._basis_frame('1445',d,b,['f0','f1'],('v0','v1'),start_position=3406)
    for row in f.itertuples():
        assert row.orthogonal_return==b[int(row.variant_id[-1]),row.day_position-3406,int(row.factor_id[-1])]


def test_shape_drift_rejected():
    with pytest.raises(ValueError,match='identity'):
        m._basis_frame('1430',np.array(['2021-01-04'],dtype='datetime64[D]'),np.zeros((2,2,2)),['f'],('v',))


@pytest.mark.parametrize('effective',['2020-12-31','2021-01-04'])
def test_membership_cannot_take_effect_before_or_at_asof(effective):
    df=pd.DataFrame({'asof_date':['2021-01-04'],'effective_date':[effective]})
    with pytest.raises(ValueError,match='forward_effective'):
        m.validate_membership_timing(df,name='synthetic')


def test_valid_next_day_membership():
    df=pd.DataFrame({'asof_date':['2021-01-04'],'effective_date':['2021-01-05']})
    m.validate_membership_timing(df,name='synthetic')


def test_missing_member_date_rejected():
    df=pd.DataFrame({'asof_date':['2021-01-04'],'effective_date':[None]})
    with pytest.raises(ValueError,match='missing'):
        m.validate_membership_timing(df,name='synthetic')


def test_loader_calls_both_chronology_guards(monkeypatch):
    # Explicit synthetic read substitutes; no claim of real source or full PIT.
    bad=pd.DataFrame({'as_of_date':['2021-01-04'],'effective_date':['2021-01-04'],'symbol':['000001']})
    core=pd.DataFrame({'asof_date':['2021-01-04'],'effective_date':['2021-01-05'],'symbol':['000001'],'target_id':['SMALL']})
    monkeypatch.setattr(m.pd,'read_csv',lambda *a,**kw:bad)
    monkeypatch.setattr(m.pd,'read_parquet',lambda *a,**kw:core)
    with pytest.raises(ValueError,match='cloudridge'):
        m._load_memberships(np.array(['000001']),('IND',),'SMALL','LARGE')
    good=bad.copy();good['effective_date']='2021-01-05'
    core['effective_date']='2021-01-04'
    monkeypatch.setattr(m.pd,'read_csv',lambda *a,**kw:good)
    with pytest.raises(ValueError,match='core'):
        m._load_memberships(np.array(['000001']),('IND',),'SMALL','LARGE')
