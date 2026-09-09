#!/usr/bin/env python3
"""Recompute the bounded cloud F/H review; never train or access FactorLab.

F/B use the previous accepted projection. H uses all 98 rows transcribed from
this delivery's connector text. These are numerical projections, not the raw
588-row CSV, and do not certify run-time arrays or cross-backend equivalence.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def audit(root: Path) -> dict:
    ref = json.loads((root / 'reported_reference.json').read_text())
    def load(name):
        with (root / name).open(newline='') as stream:
            return list(csv.DictReader(stream))
    prior = load('prior_paired_projection.csv')
    hrows = load('h_projection.csv')
    key = lambda row: (row['clock'], int(row['day_position']))
    checks = []
    def check(name, ok, detail=None):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})
    def close(name, observed, expected):
        check(name, np.isfinite(observed) and abs(observed-expected) <= 1e-12,
              {'observed': float(observed), 'expected': float(expected)})
    check('prior_unique_keys', len({key(r) for r in prior}) == len(prior))
    check('H_unique_keys', len({key(r) for r in hrows}) == len(hrows))
    check('same_complete_projection_keys', {key(r) for r in prior} == {key(r) for r in hrows})
    check('98_H_records', len(hrows) == 98)
    check('two_expected_clocks', {r['clock'] for r in hrows} == {'1430','1445'})
    lookup = {key(r): r for r in hrows}
    result, time_deltas = {}, {}
    for clock in ('1430','1445'):
        p = sorted((r for r in prior if r['clock'] == clock), key=lambda r:int(r['day_position']))
        h = [lookup[key(r)] for r in p]
        a = lambda rows, col: np.asarray([float(r[col]) for r in rows], dtype=float)
        f_ic, h_ic = a(p,'k1_ic'), a(h,'h_ic')
        f_sp, h_sp = a(p,'k1_spread'), a(h,'h_spread')
        f_top, h_top = a(p,'k1_top30_excess'), a(h,'h_top30_excess')
        phase = a(p,'phase').astype(int)
        di, ds, dt = f_ic-h_ic, f_sp-h_sp, f_top-h_top
        c = ref['clocks'][clock]
        check(clock+'.dates', len(p) == c['days'])
        check(clock+'.support_counts_match', all(int(x['n']) == int(y['n']) for x,y in zip(p,h)))
        check(clock+'.support_sum', sum(int(r['n']) for r in h) == c['rows'])
        check(clock+'.finite_metrics', np.isfinite(np.column_stack([f_ic,h_ic,f_sp,h_sp,f_top,h_top])).all())
        check(clock+'.rankic_range', (abs(f_ic)<=1).all() and (abs(h_ic)<=1).all())
        check(clock+'.D5_spacing', (np.diff(a(p,'day_position'))==5).all())
        check(clock+'.all_phases', set(phase) == {0,1,2,3})
        check(clock+'.2017_support', all(r['date'].startswith('2017-') for r in p))
        close(clock+'.H_ic', h_ic.mean(), c['H_ic'])
        close(clock+'.delta_ic', di.mean(), c['delta_ic'])
        close(clock+'.H_spread', h_sp.mean(), c['H_spread'])
        close(clock+'.H_top30', h_top.mean(), c['H_top30'])
        phases = []
        for q in range(4):
            v = float(di[phase == q].mean()); phases.append(v)
            close(clock+f'.phase_{q}', v, c['phase_delta'][q])
        close(clock+'.phase_weighted_identity', sum(v*int((phase==q).sum()) for q,v in enumerate(phases))/len(p), di.mean())
        close(clock+'.mean_difference_identity', f_ic.mean()-h_ic.mean(), di.mean())
        baseline = a(p,'reversal_mean10_ic')
        result[clock] = {
            'days': len(p), 'support_rows': sum(int(r['n']) for r in h),
            'F_rankic':float(f_ic.mean()), 'H_rankic':float(h_ic.mean()),
            'F_minus_H_rankic':float(di.mean()), 'paired_median':float(np.median(di)),
            'rankic_win_days':int((di>0).sum()), 'phase_delta':phases,
            'spread_delta':float(ds.mean()), 'spread_win_days':int((ds>0).sum()),
            'top30_excess_delta':float(dt.mean()), 'top30_win_days':int((dt>0).sum()),
            'H_minus_original_mean_reversal':float((h_ic-baseline).mean()),
            'backend_equivalence_verified':False, 'pure_X_increment_certified':False,
        }
        check(clock+'.majority_increment_statement_not_supported',
              (h_ic-baseline).mean() < di.mean())
        time_deltas[clock] = di
    fits = ref['fits']
    check('six_seed_clock_pairs', {(x['clock'],x['seed']) for x in fits} == {(c,s) for c in ('1430','1445') for s in (11,29,47)} and len(fits)==6)
    for fit in fits:
        tag = f"{fit['clock']}.seed{fit['seed']}"
        values = np.asarray(fit['canonical'], dtype=float)
        check(tag+'.3_finite_cycles', len(values)==3 and np.isfinite(values).all())
        check(tag+'.earliest_min_cycle', int(np.argmin(values))+1 == fit['selected'])
        check(tag+'.loss_below_pre', values[fit['selected']-1] < fit['pre'])
    d = ref['mean10_dtype_observation']
    close('single_reported_tie_change_explains_mean_delta',
          (d['new_ic']-d['old_ic'])/d['days'], d['new_mean']-d['old_mean'])
    report = {
        'reviewed_commit':ref['reviewed_commit'], 'scope':__doc__.strip(),
        'checks':checks, 'check_count':len(checks),
        'failures':sum(not x['passed'] for x in checks), 'results':result,
        'cross_clock_delta_correlation':float(np.corrcoef(time_deltas['1430'],time_deltas['1445'])[0,1]),
        'projection_file_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('prior_paired_projection.csv','h_projection.csv','reported_reference.json')},
        'full_pit_certified':False,'fresh_oos':False,'production_authority':False,
        'training_executed':False,'equity_level_metrics_recomputed':False,
    }
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=audit(args.root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'checks':report['check_count'],'failures':report['failures'],'results':report['results']},ensure_ascii=False))
    return 1 if report['failures'] else 0

if __name__=='__main__':
    raise SystemExit(main())
