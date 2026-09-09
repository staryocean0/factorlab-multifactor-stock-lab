from pathlib import Path
import importlib.util
import json
import hashlib
import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/reaka_r3_frozen_compare.py'
spec = importlib.util.spec_from_file_location('r3_compare', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture_rows():
    cal = np.arange('2017-01-01', '2017-01-31', dtype='datetime64[D]')
    rows = np.array([[d, s, 2017, k % 4] for k, d in enumerate((0,5,10,15)) for s in range(40)])
    y = np.tile(np.linspace(-.2,.2,40),4)
    return cal, rows, y


def test_constant_has_undefined_not_zero_rankic():
    assert m.correlation(np.zeros(40), np.arange(40)) is None


def test_common_addition_does_not_change_rank():
    x = np.arange(40, dtype=float)
    assert m.correlation(x, x + 73) == pytest.approx(1)


def test_per_day_rankz_ensemble_is_invariant_to_seed_scale():
    scores = np.array([[1,2,3,4,2,3,1,4],[3,2,1,4,4,2,3,1]],dtype=float)
    days = np.repeat([1,2],4)
    expected = m.rankz_ensemble(scores, days)
    scaled = scores.copy(); scaled[0] = scaled[0] * 100 + 9
    assert np.allclose(expected, m.rankz_ensemble(scaled,days))
    assert not np.allclose(expected, scaled.mean(axis=0))


def test_both_baseline_signs_recorded_without_selection():
    h = np.arange(100).reshape(10,10)
    b = m.baselines(h)
    assert len(b) == 4
    assert np.array_equal(b['negative_last_epsilon'], -h[:,-1])
    assert np.array_equal(b['mean10_epsilon'], h.mean(axis=1))


def test_missing_history_cannot_silently_shrink_support():
    h = np.zeros((3,10));h[0,0]=np.nan
    with pytest.raises(ValueError): m.baselines(h)


def test_constant_benchmark_does_not_select_arbitrary_stocks():
    cal, rows,y=fixture_rows()
    daily=m.daily_comparisons({'K1':y,'constant':np.ones(len(y))},y,rows,cal)
    c=[r for r in daily if r['predictor']=='constant']
    assert len(c)==4
    assert all(r['rankic'] is None and r['decile_spread'] is None and r['top30_mean'] is None for r in c)


def test_paired_delta_and_phase_counts():
    cal,rows,y=fixture_rows()
    summary=m.summarize(m.daily_comparisons({'K1':y,'reversed':-y},y,rows,cal))
    assert summary['reversed']['mean_K1_minus_baseline_rankic']==pytest.approx(2)
    assert len(summary['reversed']['paired_delta_by_phase'])==4
    assert summary['K1']['days']==4
    assert summary['K1']['iid_standard_error_or_pvalue'] is None


@pytest.mark.parametrize('defect',['duplicate','nonfinite','wrong_length','wrong_phase'])
def test_malformed_support_fails(defect):
    cal,rows,y=fixture_rows();scores={'K1':y.copy()}
    if defect=='duplicate':rows[1]=rows[0]
    if defect=='nonfinite':scores['K1'][0]=np.nan
    if defect=='wrong_length':scores['K1']=scores['K1'][:-1]
    if defect=='wrong_phase':rows[1,3]=3
    with pytest.raises(ValueError):m.daily_comparisons(scores,y,rows,cal)


def test_json_duplicates_rejected(tmp_path):
    p=tmp_path/'x.json';p.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError):m.read_json(p)


def test_independent_synthetic_end_to_end(tmp_path,monkeypatch):
    # Synthetic file schema only. No claim to reproduce original market artifacts.
    store=tmp_path/'output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal/1430'
    fit=tmp_path/'output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal/1430'
    store.mkdir(parents=True);fit.mkdir(parents=True)
    cal=np.arange('2016-07-01','2017-06-01',dtype='datetime64[D]')
    days=[190,195,200,205]
    rows=np.array([[d,s,2017,k] for k,d in enumerate(days) for s in range(40)],dtype=np.int64)
    history=np.tile(np.linspace(-.2,.2,40),(len(cal),1)).astype(np.float32)
    future=history.copy()
    objects={'calendar.npy':cal,'symbols.npy':np.array([str(i) for i in range(40)]),
        'inference_rows.npy':rows,'labelled_row_indices.npy':np.arange(len(rows)),
        'epsilon_history.npy':history,'epsilon_future.npy':future}
    digests={}
    for name,arr in objects.items():np.save(store/name,arr);digests[name]=m.file_sha(store/name)
    manifest=store/'manifest.json';manifest.write_text(json.dumps({'artifact_digests':digests}))
    monkeypatch.setitem(m.INPUT_SHA,'1430',m.file_sha(manifest)[7:])
    seed_results=[]
    ss=[]
    for seed in m.SEEDS:
        scores=future[rows[:,0],rows[:,1]];ss.append(scores)
        p=fit/f'review_scores_seed_{seed}.npy';np.save(p,scores)
        seed_results.append({'seed':seed,'review_score_digest':m.file_sha(p)})
    pred=m.rankz_ensemble(np.array(ss),rows[:,0])
    daily=m.daily_comparisons({'K1':pred},future[rows[:,0],rows[:,1]],rows,cal)
    computed=m.summarize(daily)['K1']
    form={'seed_results':seed_results,'diagnostic':{'ensemble_review_metrics':{
        'mean_daily_rankic':computed['mean_rankic'], 'mean_top_bottom_decile_spread':computed['mean_decile_spread'],'day_count':4}}}
    fp=fit/'formal.json';fp.write_text(json.dumps(form))
    raw=fp.read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    monkeypatch.setitem(m.FORMAL_BLOB,'1430',blob)
    result, daily=m.run_clock(tmp_path,'1430')
    assert result['status']=='completed_consumed_diagnostic'
    assert result['support_rows']==160 and len(daily)==20
    assert result['fresh_oos'] is False
    (fit/'review_scores_seed_11.npy').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='score identity'):m.run_clock(tmp_path,'1430')
