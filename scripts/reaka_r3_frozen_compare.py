#!/usr/bin/env python3
"""R3: compare existing 2017 frozen scores with fixed, no-fit baselines.

No torch/model import, fit, score regeneration, account replay or network.
Reports consumed-development comparisons, NOT PIT, fresh OOS or profitability.
Inputs are the exact R1/R2 artifacts; only files consumed here are hashed.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any
import numpy as np
from scipy.stats import rankdata

SEEDS = (11, 29, 47)
CLOCKS = ('1430', '1445')
INPUT_SHA = {
    '1430': '7b8050270c72894ff2e6c67f1fb4a5a5513ca46e8cc0b8c02ed7e0ce3523dfd3',
    '1445': 'e979fce98e3a6e67f6e5b2bef2701f100d2b174fcdef4539e417ba3aa0c9a7e7',
}
FORMAL_BLOB = {
    '1430': '57a1ab18761e39cb66001090ac1782bd8eda2d8d',
    '1445': 'ab75bd55f2a990dffc2036fa2f03a6295e88ec64',
}


def read_json(path: Path) -> dict[str, Any]:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f'duplicate JSON key: {key}')
            out[key] = value
        return out
    def invalid(value):
        raise ValueError(f'nonfinite JSON: {value}')
    obj = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique,
                     parse_constant=invalid)
    if not isinstance(obj, dict):
        raise ValueError('JSON object required')
    return obj


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return 'sha256:' + h.hexdigest()


def correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape or a.ndim != 1 or not len(a):
        raise ValueError('equal nonempty vectors required')
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError('explicit common finite support required')
    x, y = rankdata(a), rankdata(b)
    x, y = x - x.mean(), y - y.mean()
    denom = math.sqrt(float(x @ x) * float(y @ y))
    return float(x @ y / denom) if denom else None


def rankz_ensemble(scores: np.ndarray, days: np.ndarray) -> np.ndarray:
    """Original diagnose_cell: per-day rank-z each seed, then mean (NOT raw mean)."""
    scores, days = np.asarray(scores), np.asarray(days)
    if scores.ndim != 2 or scores.shape[1] != len(days) or not len(days):
        raise ValueError('seed x row scores and matching days required')
    if not np.isfinite(scores).all():
        raise ValueError('nonfinite frozen scores')
    z = np.empty_like(scores, dtype=float)
    for day in np.unique(days):
        take = days == day
        for i, row in enumerate(scores):
            r = rankdata(row[take], method='average')
            z[i, take] = (r - r.mean()) / max(float(r.std()), 1e-12)
    return z.mean(axis=0)


def baselines(history: np.ndarray) -> dict[str, np.ndarray]:
    h = np.asarray(history)
    if h.ndim != 2 or h.shape[1] != 10 or not np.isfinite(h).all():
        raise ValueError('ten finite H20-spaced history endpoints required')
    last, avg = h[:, -1], h.mean(axis=1)
    # All four are reported. Never pick an orientation after seeing review results.
    return {'last_epsilon': last, 'negative_last_epsilon': -last,
            'mean10_epsilon': avg, 'negative_mean10_epsilon': -avg}


def daily_comparisons(scores: dict[str, np.ndarray], target: np.ndarray,
                      rows: np.ndarray, calendar: np.ndarray) -> list[dict[str, Any]]:
    if 'K1' not in scores or len(rows) != len(target):
        raise ValueError('K1 and aligned target/rows required')
    if rows.ndim != 2 or rows.shape[1] < 4 or not len(rows):
        raise ValueError('nonempty day/symbol/year/phase coordinates required')
    if len(np.unique(rows[:, :2], axis=0)) != len(rows):
        raise ValueError('duplicate day/symbol coordinates')
    if not np.isfinite(target).all():
        raise ValueError('nonfinite target; choose and disclose common support first')
    for values in scores.values():
        if np.asarray(values).shape != target.shape or not np.isfinite(values).all():
            raise ValueError('all predictors must use identical finite support')
    output = []
    for day in np.unique(rows[:, 0]):
        take = rows[:, 0] == day
        local_rows, y = rows[take], target[take]
        phases = np.unique(local_rows[:, 3])
        if len(phases) != 1:
            raise ValueError('inconsistent phase within date')
        if len(y) < 30:
            raise ValueError('fewer than 30 stocks; report task failure, do not silently drop day')
        mean_y = float(y.mean())
        for name, vector in scores.items():
            s = vector[take]
            # Reproduce original stable argsort order: input review rows stay in original order.
            order = np.argsort(s, kind='mergesort')
            count = max(1, len(y) // 10)
            rankic = correlation(s, y)
            ties = len(np.unique(s)) != len(s)
            output.append({'day_position': int(day), 'date': str(calendar[day].astype('datetime64[D]')),
                'phase': int(phases[0]), 'predictor': name, 'n': len(y), 'rankic': rankic,
                'decile_spread': float(y[order[-count:]].mean() - y[order[:count]].mean()) if rankic is not None else None,
                'top30_mean': float(y[order[-30:]].mean()) if rankic is not None else None,
                'universe_mean': mean_y,
                'top30_minus_universe': float(y[order[-30:]].mean() - mean_y) if rankic is not None else None,
                'ties_present': ties})
    return output


def summarize(daily: list[dict[str, Any]]) -> dict[str, Any]:
    """Paired differences and phase means only; no iid p-values from overlapping H20."""
    out = {}
    incumbent = {r['date']: r for r in daily if r['predictor'] == 'K1'}
    for name in sorted({r['predictor'] for r in daily}):
        local = [r for r in daily if r['predictor'] == name]
        valid = [r for r in local if r['rankic'] is not None and incumbent[r['date']]['rankic'] is not None]
        diffs = [incumbent[r['date']]['rankic'] - r['rankic'] for r in valid]
        out[name] = {'days': len(local), 'valid_paired_rankic_days': len(valid),
            'mean_rankic': float(np.mean([r['rankic'] for r in valid])) if valid else None,
            'mean_K1_minus_baseline_rankic': float(np.mean(diffs)) if diffs else None,
            'mean_decile_spread': float(np.mean([r['decile_spread'] for r in valid])) if valid else None,
            'mean_top30_minus_universe': float(np.mean([r['top30_minus_universe'] for r in valid])) if valid else None,
            'paired_delta_by_phase': {str(p): float(np.mean([incumbent[r['date']]['rankic'] - r['rankic'] for r in valid if r['phase'] == p]))
                 for p in sorted({r['phase'] for r in valid})},
            'iid_standard_error_or_pvalue': None}
    return out


def run_clock(root: Path, clock: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    store = root / 'output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal' / clock
    fit = root / 'output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal' / clock
    manifest_path, formal_path = store / 'manifest.json', fit / 'formal.json'
    if file_sha(manifest_path) != 'sha256:' + INPUT_SHA[clock]:
        raise ValueError('input manifest identity changed; do not replace frozen inputs')
    data = formal_path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if blob != FORMAL_BLOB[clock]:
        raise ValueError('formal receipt identity changed')
    manifest, formal = read_json(manifest_path), read_json(formal_path)
    identities = []
    arrays = {}
    for name in ('calendar.npy', 'symbols.npy', 'inference_rows.npy', 'labelled_row_indices.npy',
                 'epsilon_history.npy', 'epsilon_future.npy'):
        path = store / name
        observed = file_sha(path)
        if observed != manifest['artifact_digests'][name]:
            raise ValueError(f'consumed array identity mismatch: {name}')
        identities.append({'relative_path': str(path.relative_to(root)), 'sha256': observed})
        arrays[name] = np.load(path, mmap_mode='r', allow_pickle=False)
    rows = np.asarray(arrays['inference_rows.npy'])
    labels = np.asarray(arrays['labelled_row_indices.npy'])
    if labels.ndim != 1 or not np.issubdtype(labels.dtype, np.integer) or len(np.unique(labels)) != len(labels) or (labels < 0).any() or (labels >= len(rows)).any():
        raise ValueError('invalid labelled indices')
    mask = np.zeros(len(rows), dtype=bool)
    mask[labels] = True
    idx = np.flatnonzero((rows[:, 2] == 2017) & mask)
    take = rows[idx]
    if not len(take) or np.any(take[:, 0] < 180) or np.any(take[:, 0] >= len(arrays['calendar.npy'])) or np.any(take[:, 1] < 0) or np.any(take[:, 1] >= len(arrays['symbols.npy'])):
        raise ValueError('invalid review support')
    cal = arrays['calendar.npy']
    if not np.all(cal[take[:, 0]].astype('datetime64[Y]').astype(int) + 1970 == 2017):
        raise ValueError('year coordinate mismatch')
    endpoints = take[:, 0, None] + np.arange(-180, 1, 20)[None, :]
    history = np.asarray(arrays['epsilon_history.npy'][endpoints, take[:, 1, None]], dtype=float)
    target = np.asarray(arrays['epsilon_future.npy'][take[:, 0], take[:, 1]], dtype=float)
    scores = []
    by_seed = {int(r['seed']): r for r in formal['seed_results']}
    if set(by_seed) != set(SEEDS):
        raise ValueError('unexpected seed inventory')
    for seed in SEEDS:
        path = fit / f'review_scores_seed_{seed}.npy'
        observed = file_sha(path)
        if observed != by_seed[seed]['review_score_digest']:
            raise ValueError(f'frozen score identity mismatch: {seed}')
        score = np.asarray(np.load(path, allow_pickle=False), dtype=float)
        if score.shape != (len(idx),):
            raise ValueError('frozen score length differs from review coordinates')
        scores.append(score)
        identities.append({'relative_path': str(path.relative_to(root)), 'sha256': observed})
    prediction = {'K1': rankz_ensemble(np.vstack(scores), take[:, 0]), **baselines(history)}
    daily = daily_comparisons(prediction, target, take, cal)
    result = summarize(daily)
    expected = formal['diagnostic']['ensemble_review_metrics']
    ic_error = result['K1']['mean_rankic'] - float(expected['mean_daily_rankic'])
    spread_error = result['K1']['mean_decile_spread'] - float(expected['mean_top_bottom_decile_spread'])
    # Persisted float32 scores may create tiny ties relative to in-memory scores.
    parity = abs(ic_error) <= 1e-4 and abs(spread_error) <= 1e-4 and result['K1']['days'] == int(expected['day_count'])
    for row in daily:
        row['clock'] = clock
    return {'clock': clock, 'status': 'completed_consumed_diagnostic' if parity else 'receipt_parity_mismatch',
            'support_rows': len(take), 'support_days': result['K1']['days'],
            'review_row_indices_sha256': 'sha256:' + hashlib.sha256(idx.astype('<i8').tobytes()).hexdigest(),
            'formal_blob': blob, 'input_manifest_sha256': 'sha256:' + INPUT_SHA[clock],
            'consumed_files': identities, 'results': result,
            'receipt_parity': {'mean_rankic_error': ic_error, 'mean_spread_error': spread_error,
                               'atol': 1e-4, 'passed': parity},
            'constant_zero_rankic': None,
            'constant_zero_role': 'undefined rank correlation; use universe-mean return comparator, not fake IC=0',
            'target': 'epsilon_future_raw_h20_financial_residual_not_total_stock_return',
            'fresh_oos': False, 'production_authority': False}, daily


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--factorlab-root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    root, out = args.factorlab_root.resolve(), args.output_dir.resolve()
    if out.exists() or out.is_relative_to(root / 'output') or out.is_relative_to(root / 'data'):
        raise ValueError('choose a NEW output directory outside sealed data/output trees')
    out.mkdir(parents=True)
    results, daily, failed, missing = [], [], False, False
    for clock in CLOCKS:
        try:
            result, rows = run_clock(root, clock)
            results.append(result)
            daily.extend(rows)
            failed |= result['status'] != 'completed_consumed_diagnostic'
        except FileNotFoundError as exc:
            missing = True
            results.append({'clock': clock, 'status': 'blocked_missing_input', 'detail': str(exc)})
        except (ValueError, KeyError, OSError, IndexError, TypeError) as exc:
            failed = True
            results.append({'clock': clock, 'status': 'failed', 'detail': f'{type(exc).__name__}: {exc}'})
    if daily:
        with (out / 'paired_daily.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(daily[0]))
            writer.writeheader(); writer.writerows(daily)
    code = 1 if failed else 2 if missing else 0
    report = {'task': 'LCL-R3-NOFIT-20260906-01', 'status': 'completed' if code == 0 else 'incomplete',
              'exit_code': code, 'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform(),
              'script_sha256': file_sha(Path(__file__)), 'checks': results,
              'sample_role': 'already_consumed_2017_review', 'fresh_oos': False,
              'training_or_frozen_inference_run': False, 'account_replay': False,
              'condition_feature_increment_identified': False, 'full_pit_certified': False,
              'limitations': ['No iid inference from H20 overlap or clocks/seeds.',
                              'No scale-calibrated MSE or total-return/profitability claim.',
                              'Baseline comparison is not a trained feature ablation.']}
    (out / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'exit_code': code, 'clocks': [{k: v.get(k) for k in ('clock','status','support_rows')} for v in results]}))
    return code

if __name__ == '__main__':
    raise SystemExit(main())
