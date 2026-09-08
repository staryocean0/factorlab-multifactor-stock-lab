from __future__ import annotations
import importlib.util
import json
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

def test_archived_batch_context_replay_preserves_original_geometry():
    m=load()
    batch=4
    idx=np.arange(10,dtype=np.int64)
    rows=np.column_stack((idx,idx%3,np.full(10,2020),idx%4)).astype(np.int64)

    # Deliberately batch-shape-dependent synthetic scorer. Archived values were
    # produced in 4,4,2 row batches; sparse-only replay would differ.
    archived_scores=np.empty(10,float)
    for start in range(0,10,batch):
        stop=min(start+batch,10)
        archived_scores[start:stop]=idx[start:stop].astype(float)+0.01*(stop-start)
    archived={'indices':idx,'rows':rows,'scores':archived_scores}

    def score_batch(indices):
        positions=np.asarray(indices,dtype=np.int64)
        return {'indices':positions,
                'rows':rows[positions],
                'scores':positions.astype(float)+0.01*len(positions)}

    pick=np.array([0,3,4,7,8,9],dtype=np.int64)
    out=m.replay_sampled_in_archived_batch_context(
        archived,pick,batch_size=batch,score_batch=score_batch)
    np.testing.assert_array_equal(out['rows'],rows[pick])
    np.testing.assert_allclose(out['scores'],archived_scores[pick],rtol=0,atol=0)
    assert out['comparison_rows']==6
    assert out['context_rows_replayed']==10
    assert out['historical_batches_replayed']==3
    assert out['batch_size']==4

def test_archived_batch_context_rejects_bad_replay_rows():
    m=load(); idx=np.arange(4,dtype=np.int64); rows=np.column_stack((idx,idx,idx,idx))
    archived={'indices':idx,'rows':rows,'scores':idx.astype(float)}
    def bad(indices):
        return {'indices':indices,'rows':rows[np.asarray(indices)][::-1],
                'scores':np.asarray(indices,float)}
    with pytest.raises(ValueError,match='row drift'):
        m.replay_sampled_in_archived_batch_context(
            archived,np.array([0,3]),batch_size=4,score_batch=bad)

def test_embedded_F_receipt_is_read_only_fallback(tmp_path):
    m=load(); timeiso=tmp_path/'timeiso'; root=timeiso/'1430/experiment'; root.mkdir(parents=True)
    receipt={'fit':{'future_target_values_read':0},
             'identity':{'clock':'1430','seed':11,'arm':'F'},
             'checkpoint_state_digest':'sha256:x'}
    (root/'result.json').write_text(json.dumps({'seed_receipts':{'F':[receipt]}}))
    missing=timeiso/'1430/experiment/models/seed_11/F/fit_receipt.json'
    got,origin=m.read_reference_receipt(timeiso,missing,'1430',11,'F',lambda p: {})
    assert got==receipt
    assert origin=='accepted_timeiso_seed_receipts_F'
    assert not missing.exists()

def test_preflight_source_does_not_open_outcome_sidecars_or_new_period_scores():
    text=P.read_text(encoding='utf-8')
    assert 'label_sidecars' not in text
    assert 'epsilon_future' not in text
    assert 'prediction_indices' not in text
    assert 'score_no_labels' in text
    assert 'new_period_score_jobs' in text
    assert 'BATCH_SIZE' in text
    assert 'ATOL = 1e-7' in text
