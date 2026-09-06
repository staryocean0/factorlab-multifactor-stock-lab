#!/usr/bin/env python3
"""Recompute bounded R3 acceptance from a disclosed 98-row connector projection.

No row-level equity IC is recalculated here: local ICs are inputs. This script
checks the paired summaries and produces descriptive, not inferential, results.
It does not read raw arrays, fit models, select a new baseline or execute trades.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, statistics
from pathlib import Path
import numpy as np

MEASURES = ('k1_ic', 'reversal_mean10_ic', 'k1_spread', 'reversal_mean10_spread',
            'k1_top30_excess', 'reversal_mean10_top30_excess')

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    ref = json.loads((a.root/'reported_reference.json').read_text())
    with (a.root/'paired_projection.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ('day_position', 'phase', 'n'): row[key] = int(row[key])
        for key in MEASURES: row[key] = float(row[key])
    checks = []
    def check(name, result): checks.append({'name': name, 'passed': bool(result)})
    def eq(x, y): return math.isclose(x, y, rel_tol=0, abs_tol=1e-12)
    check('98_projection_pairs', len(rows) == 98)
    check('unique_clock_date', len({(r['clock'],r['date']) for r in rows}) == len(rows))
    check('two_expected_clocks', {r['clock'] for r in rows} == {'1430','1445'})
    check('numeric_fields_finite', all(math.isfinite(r[k]) for r in rows for k in MEASURES))
    results, aligned = {}, {}
    for clock in ('1430','1445'):
        group = sorted((r for r in rows if r['clock'] == clock),key=lambda r:r['day_position'])
        expected = ref[clock]
        check(clock+'_49_days',len(group)==expected['support_days'])
        check(clock+'_82321_observations',sum(r['n'] for r in group)==expected['support_rows'])
        check(clock+'_date_bounds', (group[0]['date'],group[-1]['date'])==('2017-01-06','2017-12-29'))
        check(clock+'_all_dates_2017',all(r['date'].startswith('2017-') for r in group))
        check(clock+'_all_n_at_least_30',all(r['n']>=30 for r in group))
        check(clock+'_D5_positions',all(y['day_position']-x['day_position']==5 for x,y in zip(group,group[1:])))
        check(clock+'_all_four_phases',{r['phase'] for r in group}=={0,1,2,3})
        check(clock+'_rankic_range',all(abs(r[k])<=1 for r in group for k in MEASURES[:2]))
        means = {k:statistics.mean(r[k] for r in group) for k in MEASURES}
        for k in MEASURES: check(clock+'_mean_'+k,eq(means[k],expected[k]))
        delta = np.array([r['k1_ic']-r['reversal_mean10_ic'] for r in group])
        check(clock+'_paired_ic_mean',eq(float(delta.mean()), expected['paired_ic_mean']))
        phase = {str(ph):statistics.mean(float(delta[i]) for i,r in enumerate(group) if r['phase']==ph) for ph in range(4)}
        for ph in phase: check(clock+'_phase_'+ph,eq(phase[ph],expected['paired_phase_means'][ph]))
        check(clock+'_formal_ic_parity',abs(means['k1_ic']-expected['formal_mean_rankic'])<=1e-4)
        check(clock+'_formal_spread_parity',abs(means['k1_spread']-expected['formal_mean_spread'])<=1e-4)
        for name, reported in expected['all_reported_delta'].items():
            check(clock+'_reported_delta_arithmetic_'+name,
                  eq(expected['all_reported_rankic']['K1']-expected['all_reported_rankic'][name],reported))
        check(clock+'_fixed_baseline_set',set(expected['all_reported_rankic'])=={'K1','last_epsilon','negative_last_epsilon','mean10_epsilon','negative_mean10_epsilon'})
        results[clock] = {'support_days':len(group),'support_rows':sum(r['n'] for r in group),
            'min_stocks':min(r['n'] for r in group),'max_stocks':max(r['n'] for r in group),
            'means':means, 'paired_rankic_mean':float(delta.mean()), 'paired_rankic_median':float(np.median(delta)),
            'paired_rankic_positive_days':int((delta>0).sum()), 'paired_rankic_negative_days':int((delta<0).sum()),
            'paired_rankic_zero_days':int((delta==0).sum()),'paired_rankic_phase_means':phase,
            'phase_day_counts':{str(ph):sum(r['phase']==ph for r in group) for ph in range(4)},
            'paired_decile_spread_mean':statistics.mean(r['k1_spread']-r['reversal_mean10_spread'] for r in group),
            'paired_decile_positive_days':sum(r['k1_spread']>r['reversal_mean10_spread'] for r in group),
            'paired_top30_mean':statistics.mean(r['k1_top30_excess']-r['reversal_mean10_top30_excess'] for r in group),
            'paired_top30_positive_days':sum(r['k1_top30_excess']>r['reversal_mean10_top30_excess'] for r in group),
            'quarter_rankic_delta_descriptive_only':{str(q):statistics.mean(float(delta[i]) for i,r in enumerate(group) if (int(r['date'][5:7])-1)//3+1==q) for q in range(1,5)},
            'pvalue':None, 'inferential_acceptance':False}
        aligned[clock] = group
    check('same_date_position_phase_n_across_clocks',
        all(tuple(r[k] for k in ('date','day_position','phase','n'))==tuple(s[k] for k in ('date','day_position','phase','n')) for r,s in zip(aligned['1430'],aligned['1445'])))
    corr = float(np.corrcoef(*[[r['k1_ic']-r['reversal_mean10_ic'] for r in aligned[c]] for c in ('1430','1445')])[0,1])
    result = {'task':ref['task'],'reviewed_commit':ref['source_commit'],
        'scope':ref['projection_scope'], 'checks':checks, 'passed':sum(r['passed'] for r in checks),
        'failed':sum(not r['passed'] for r in checks),'clock_results':results,
        'paired_delta_cross_clock_correlation_descriptive_only':corr,
        'projection_sha256':hashlib.sha256((a.root/'paired_projection.csv').read_bytes()).hexdigest(),
        'source_original_csv_rehashed_in_cloud':False,
        'real_equity_scores_or_labels_recomputed':False,'condition_increment_identified':False,
        'fresh_oos':False,'full_pit_certified':False,'production_authority':False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')
    print(json.dumps({'passed':result['passed'],'failed':result['failed'],'clock_results':results},ensure_ascii=False,indent=2))
    return int(result['failed']>0)

if __name__=='__main__': raise SystemExit(main())
