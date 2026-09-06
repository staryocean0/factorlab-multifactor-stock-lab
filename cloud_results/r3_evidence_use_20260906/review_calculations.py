#!/usr/bin/env python3
"""Recompute descriptive arithmetic from explicitly extracted historical fields.
No stock arrays, fitting, forecast regeneration or statistical acceptance.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def calculate(observations):
    checks, clocks = [], {}
    for clock, item in observations['clocks'].items():
        computed_se = item['daily_rankic_std'] / math.sqrt(item['day_count'])
        positive = sum(v > 0 for v in item['phase_mean_rankic'].values())
        checks.append({'id': clock+'_se_formula', 'passed': abs(computed_se-item['daily_rankic_se']) < 1e-14})
        checks.append({'id': clock+'_phase_count', 'passed': positive == item['positive_phase_count'] == 4})
        checks.append({'id': clock+'_valid_correlation', 'passed': -1 <= item['mean_daily_rankic'] <= 1})
        clocks[clock] = {
            'mean_rankic': item['mean_daily_rankic'], 'residual_decile_spread_percent': 100*item['mean_top_bottom_decile_spread'],
            'recomputed_naive_se': computed_se,
            'naive_mean_over_se_not_valid_significance_claim': item['mean_daily_rankic']/computed_se,
            'phase_min': min(item['phase_mean_rankic'].values()), 'phase_max': max(item['phase_mean_rankic'].values()),
        }
    clocks_delta = observations['clocks']['1445']['mean_daily_rankic']-observations['clocks']['1430']['mean_daily_rankic']
    return {'checks': checks, 'failures': sum(not x['passed'] for x in checks), 'clocks': clocks,
            'clock_rankic_difference_not_paired_test': clocks_delta,
            'adjacent_H20_overlap_fraction_for_D5_endpoints': (20-5)/20,
            'raw_row_count_not_independent_samples': True,
            'claims_not_computed': ['IC versus no-fit baselines', 'condition-feature incremental predictive effect',
                                    'paired uncertainty intervals', 'total-return or net-account alpha'],
            'scientific_acceptance': False, 'full_pit_certified': False, 'fresh_oos': False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, default=Path(__file__).with_name('source_observations.json'))
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    if a.output.exists(): raise FileExistsError('new output required')
    data=a.input.read_bytes(); r=calculate(json.loads(data))
    r['observations_sha256']=hashlib.sha256(data).hexdigest()
    a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False))
    return 1 if r['failures'] else 0

if __name__=='__main__':raise SystemExit(main())
