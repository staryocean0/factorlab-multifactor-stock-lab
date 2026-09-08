from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'src/factor_lab/factor_rotation/reaka_r3_transfer_score_preflight.py'

def load():
    spec=importlib.util.spec_from_file_location('r3_transfer_score_preflight_test',P)
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def test_sample_positions_fixed_spread_and_bounded():
    m=load(); x=m.sample_positions(1000)
    assert len(x)==64 and x[0]==0 and x[-1]==999 and np.all(np.diff(x)>0)

def test_sample_positions_small_file_uses_every_row():
    m=load(); np.testing.assert_array_equal(m.sample_positions(4),np.arange(4))

def test_sample_positions_rejects_empty():
    m=load()
    with pytest.raises(ValueError):m.sample_positions(0)

def test_reference_paths_are_only_four_registered_families():
    m=load(); t=Path('/t'); x=Path('/x')
    assert m.reference_paths(t,x,'1430',11,'F')[2] == Path('/t/1430/experiment/models/seed_11/F/scores.npz')
    assert m.reference_paths(t,x,'1445',47,'BETA_ONLY')[2] == Path('/x/1445/models/seed_47/BETA_ONLY/scores.npz')

def test_preflight_source_does_not_open_outcome_sidecars_or_new_period_scores():
    text=P.read_text(encoding='utf-8')
    assert 'label_sidecars' not in text
    assert 'epsilon_future' not in text
    assert 'prediction_indices' not in text
    assert 'score_no_labels' in text
    assert 'new_period_score_jobs' in text
