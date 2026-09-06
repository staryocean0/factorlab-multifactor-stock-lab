#!/usr/bin/env python3
"""Recheck projected/summary evidence, not local stock arrays or model fits.

Inputs are expressly labeled extracts from commit 360eae62. No financial
acceptance, hash re-verification of local NPYs, or full-market rerun is implied.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main() -> int:
    data=json.loads((ROOT/'per_seed_metrics_extract.json').read_text())
    projected=list(csv.DictReader((ROOT/'seed47_rankic_projection.csv').open()))
    reference=json.loads((ROOT/'ensemble_reference_extract.json').read_text())
    checks=[]
    def check(name,ok,**detail):
        checks.append({'check':name,'passed':bool(ok),'detail':detail})
    def close(name,observed,expected):
        check(name, math.isfinite(observed) and math.isfinite(expected) and abs(observed-expected)<=1e-12,
              observed=observed,expected=expected,absolute_error=abs(observed-expected))
    keys={(r['clock'],r['seed']) for r in data['per_seed']}
    check('six_declared_cells_no_selection',keys=={(c,s) for c in ('1430','1445') for s in (11,29,47)} and len(data['per_seed'])==6)
    counts={}
    descriptive={}
    for clock in ('1430','1445'):
        rows=[r for r in projected if r['clock']==clock]
        days=[int(r['day_position']) for r in rows]
        n=[int(r['n']) for r in rows]
        phases=[int(r['phase']) for r in rows]
        check(clock+'_49_unique_dates',len(rows)==49 and len(set(days))==49)
        check(clock+'_same_declared_D5_grid',days==list(range(2435,2676,5)))
        check(clock+'_phase_support',Counter(phases)==Counter({0:12,1:12,2:13,3:12}))
        check(clock+'_support_count',sum(n)==82321 and min(n)==1447 and max(n)==1894)
        check(clock+'_calendar_endpoints',rows[0]['date']=='2017-01-06' and rows[-1]['date']=='2017-12-29' and all(r['date'].startswith('2017-') for r in rows))
        f=[float(r['f_rankic']) for r in rows]; h=[float(r['h_rankic']) for r in rows]
        check(clock+'_finite_rankic_bounds',all(math.isfinite(v) and -1<=v<=1 for v in f+h))
        delta=[a-b for a,b in zip(f,h)]
        target=next(r for r in data['per_seed'] if r['clock']==clock and r['seed']==47)
        close(clock+'_seed47_f_reaggregate',statistics.mean(f),target['f_rankic'])
        close(clock+'_seed47_h_reaggregate',statistics.mean(h),target['h_rankic'])
        close(clock+'_seed47_delta_reaggregate',statistics.mean(delta),target['reported_delta'])
        for phase in range(4):
            close(clock+f'_seed47_phase{phase}',statistics.mean(d for d,p in zip(delta,phases) if p==phase),target['phase_deltas'][phase])
        descriptive[clock]={'seed47_mean_delta':statistics.mean(delta),'seed47_median_delta':statistics.median(delta),
                            'seed47_positive_days':sum(d>0 for d in delta),'seed47_negative_days':sum(d<0 for d in delta),
                            'seed47_phase_delta':{str(p):statistics.mean(d for d,k in zip(delta,phases) if k==p) for p in range(4)}}
        counts[clock]=Counter(phases)
        reload=data['ensemble_reload'][clock]
        close(clock+'_F_ensemble_reload_vs_accepted',reload['F'],reference['clocks'][clock]['f_ic'])
        close(clock+'_H_ensemble_reload_vs_accepted',reload['H'],reference['clocks'][clock]['h_ic'])
        check(clock+'_reported_reload_gaps_zero',reload['f_gap']==0.0 and reload['h_gap']==0.0)
        close(clock+'_ensemble_F_minus_H',reload['F']-reload['H'],reference['clocks'][clock]['f_minus_h'])
    for row in data['per_seed']:
        key=f"{row['clock']}_seed{row['seed']}"
        close(key+'_subtraction',row['f_rankic']-row['h_rankic'],row['reported_delta'])
        close(key+'_phase_weighted_mean',sum(d*counts[row['clock']][i] for i,d in enumerate(row['phase_deltas']))/49,row['reported_delta'])
        check(key+'_finite_metrics',all(math.isfinite(row[k]) for k in ('f_rankic','h_rankic','reported_delta','f_spread','h_spread','f_top30_excess','h_top30_excess')))
        # A positive return is not an execution requirement. This checks the
        # report's factual description, not a demand to make the experiment win.
        check(key+'_reported_mean_positive_description',row['reported_delta']>0)
    summary={'task':'LCL-R3-COND-20260906-01','reviewed_commit':data['source_commit'],
             'status':'passed' if all(x['passed'] for x in checks) else 'failed',
             'checks':checks,'check_count':len(checks),'failure_count':sum(not x['passed'] for x in checks),
             'scope':'Six summary cells and 98 seed47 RankIC paired projections covering all dates of both clocks. Only seed47 was independently reaggregated daily in this follow-up. Not raw CSV bytes or individual-stock RankIC.',
             'descriptive':descriptive,'original_arrays_read':False,'new_training':False,'new_inference':False,
             'fresh_oos':False,'strict_input_only_effect_certified':False,'production_authority':False}
    for name in ('per_seed_metrics_extract.json','seed47_rankic_projection.csv','ensemble_reference_extract.json','projection_provenance.json'):
        summary.setdefault('local_extract_sha256',{})[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    (ROOT/'aggregation_checks.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:summary[k] for k in ('status','check_count','failure_count','descriptive')},indent=2))
    return int(summary['failure_count']>0)

if __name__=='__main__': raise SystemExit(main())
