from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'scripts/reaka_r3_transfer_label_bridge.py'

def load():
    spec = importlib.util.spec_from_file_location('r3_label_bridge_test', P)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_future_h20_is_forward_twenty_positions_and_last_twenty_unlabelled():
    m=load()
    close=(np.arange(50,dtype=np.float32)+10)[:,None]
    out=m.future_h20(close)
    for t in range(30):
        assert out[t,0] == pytest.approx(float(close[t+20,0]/close[t,0]-1), abs=1e-7)
    assert np.isnan(out[-20:]).all()


def test_future_h20_does_not_use_beyond_t_plus_20():
    m=load()
    close=(np.arange(60,dtype=np.float32)+10)[:,None]
    changed=close.copy(); changed[41:]=99999
    a=m.future_h20(close); b=m.future_h20(changed)
    np.testing.assert_array_equal(a[:21], b[:21])


def test_anchor_selection_is_fixed_index_quantiles_of_2018_2020():
    m=load()
    cal=np.arange(np.datetime64('2017-01-01'),np.datetime64('2021-01-01'),dtype='datetime64[D]')
    d=np.arange(0,len(cal),5,dtype=np.int64)
    got=m.anchor_decisions(d,cal,5)
    years=cal[got].astype('datetime64[Y]').astype(int)+1970
    assert got.shape==(5,)
    assert (years>=2018).all() and (years<=2020).all()
    eligible=d[((cal[d].astype('datetime64[Y]').astype(int)+1970)>=2018)&((cal[d].astype('datetime64[Y]').astype(int)+1970)<=2020)]
    expected=eligible[np.unique(np.linspace(0,len(eligible)-1,5,dtype=np.int64))]
    np.testing.assert_array_equal(got,expected)


def test_anchor_selection_rejects_too_few():
    m=load()
    cal=np.arange(np.datetime64('2018-01-01'),np.datetime64('2018-01-20'),dtype='datetime64[D]')
    with pytest.raises(ValueError,match='insufficient'):
        m.anchor_decisions(np.array([0,5,10]),cal,5)


def test_maxdiff_checks_support_and_tolerance():
    m=load()
    a=np.array([1.,np.nan,3.]); b=np.array([1.+1e-8,np.nan,3.])
    assert m.maxdiff(a,b)['passed']
    c=np.array([1.,0.,3.])
    assert not m.maxdiff(a,c)['passed']
    d=np.array([1.1,np.nan,3.])
    assert not m.maxdiff(a,d)['passed']


def test_bridge_source_has_no_model_training_or_scoring_entrypoints():
    text=P.read_text(encoding='utf-8')
    for forbidden in ('fit_arm(', 'forecast(', 'score_no_labels(', 'load_state_tree(', 'checkpoint_root'):
        assert forbidden not in text
    assert 'contains_2026' in text
    assert 'target_anchor_checks.json' in text
    assert 'reused_accepted_arrays' in text
