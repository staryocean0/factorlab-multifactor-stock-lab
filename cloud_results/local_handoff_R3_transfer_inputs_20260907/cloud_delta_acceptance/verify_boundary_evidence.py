"""Verify the uploaded SMALL B1--B3 receipt, not the original financial arrays.

The 1e-12 basis check is a disclosed cloud-review numerical diagnostic, NOT a
pre-registered model-performance threshold. Exactness is never rewritten.
Member dates/counts do not establish source identity or generating-rule parity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

BASIS_DIAGNOSTIC_ATOL = 1e-12
FAMILIES = ('factor_basis_at_last_d5', 'beta', 'reliability', 'available', 'epsilon_at_last_d5')
EXPECTED_CELLS = dict(zip(FAMILIES, (84, 55748, 55748, 55748, 3982)))


def read_json(path: Path) -> dict[str, Any]:
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError(f'duplicate key {k}')
            out[k] = v
        return out
    def bad_constant(value):
        raise ValueError(f'nonfinite JSON constant {value}')
    value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant)
    if not isinstance(value, dict):
        raise ValueError('JSON object required')
    return value


def evaluate(body: dict[str, Any]) -> dict[str, Any]:
    checks = []
    def require(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise ValueError(name)
    def natural(name, value):
        require(name, type(value) is int and value >= 0)
        return value
    def flag(name, value, expected):
        require(name, type(value) is bool and value is expected)
    require('schema', body.get('schema_id') == 'factorlab.r3_transfer_boundary_delta@1.0')
    require('task', body.get('task_id') == 'LCL-R3-TRANSFER-INPUT-20260907-01')
    for name in ('new_model_fits', 'new_inference', 'checkpoint_reload'):
        require(name, natural(name + '_type', body.get(name)) == 0)
    for name in ('full_bridge_rerun', 'PIT_certified', 'fresh_oos', 'production_authority'):
        flag(name, body.get(name), False)
    for name in ('original_source_bundles_untouched', 'original_run01_untouched'):
        flag(name, body.get(name), True)
    b2 = body['B2_membership']
    flag('membership_violations_flag', b2.get('any_timing_violation_on_used_snapshot'), False)
    membership = {}
    for source in ('cloudridge', 'core'):
        x = b2[source]
        names = ('rows_after_full_file_read', 'rows_asof_before_2026', 'rows_discarded_because_asof_ge_2026', 'rows_mapped_to_incumbent_3982')
        raw, before, dropped, mapped = [natural(source + '/' + k, x.get(k)) for k in names]
        require(source + '/row_accounting', raw == before + dropped)
        require(source + '/nonempty_mapped_support', 0 < mapped <= before <= raw)
        for k in ('missing_dates', 'effective_le_asof_violations'):
            require(source + '/' + k, natural(source + '/' + k + '_type', x.get(k)) == 0)
        flag(source + '/reported_forward_effective', x.get('forward_effective_ok'), True)
        # These are extrema of the selected rows, not a recreation of each row.
        lo, hi = (datetime.fromisoformat(x[k]) for k in ('used_asof_min', 'used_asof_max'))
        require(source + '/reported_asof_range', lo <= hi < datetime(2026, 1, 1))
        membership[source] = {'mapped_rows': mapped, 'excluded_by_cohort_after_cutoff': before - mapped,
                              'excluded_by_asof_cutoff': dropped}
    targets = b2['core_target_filter']
    require('core_target_identity_count', len(targets) == len(set(targets)) == 14)
    require('size_targets', {'SIZE_FACTOR_CORE:SMALL', 'SIZE_FACTOR_CORE:LARGE'} <= set(targets))
    require('two_clocks', set(body['clocks']) == {'1430', '1445'})
    seam_exact_flags = []
    seam_summary = {}
    for clock in ('1430', '1445'):
        x = body['clocks'][clock]
        b1 = x['B1_state_tail']
        for k in ('tail_cells', 'tail_finite', 'tail_nonfinite'):
            natural(clock + '/B1/' + k, b1.get(k))
        require(clock + '/B1/shape_count', b1['tail_cells'] == 6 * 1212 * 14)
        require(clock + '/B1/finite_accounting', b1['tail_cells'] == b1['tail_finite'] + b1['tail_nonfinite'])
        require(clock + '/B1/nonfinite_zero', b1['tail_nonfinite'] == 0)
        for key, length in (('nonfinite_by_factor', 14), ('nonfinite_by_variant', 6)):
            require(clock + '/B1/' + key, len(b1[key]) == length and all(type(v) is int and v == 0 for v in b1[key]))
        flag(clock + '/B1/all_finite', b1.get('all_tail_finite'), True)
        flag(clock + '/B1/rebuild_flag', b1.get('state_rebuild_required'), False)
        s = x['B3_seam']
        require(clock + '/B3/last_index', s.get('last_old_d5_index') == 3405)
        require(clock + '/B3/last_date', s.get('last_old_d5_date') == '2020-12-31')
        flag(clock + '/B3/not_copied_comparison', s.get('copied_prefix_not_used_as_independent_replay'), True)
        results = {}
        for name in FAMILIES:
            y = s[name]  # Missing entries must fail, not be skipped by comprehension.
            flag(clock + '/' + name + '/shape', y.get('shape_match'), True)
            flag(clock + '/' + name + '/support', y.get('support_equal'), True)
            require(clock + '/' + name + '/cells', natural(clock + '/' + name + '/cells_type', y.get('cells')) == EXPECTED_CELLS[name])
            n = natural(clock + '/' + name + '/finite_type', y.get('both_finite'))
            require(clock + '/' + name + '/nonempty', 0 < n <= y['cells'])
            err = y.get('max_abs_diff_finite')
            require(clock + '/' + name + '/finite_error', type(err) in (int, float) and math.isfinite(err) and err >= 0)
            require(clock + '/' + name + '/exact_flag', type(y.get('exact')) is bool and y['exact'] == (err == 0))
            threshold = BASIS_DIAGNOSTIC_ATOL if name == 'factor_basis_at_last_d5' else 0.0
            require(clock + '/' + name + '/difference_limit', err <= threshold)
            seam_exact_flags.append(y['exact'])
            results[name] = {'both_finite': n, 'max_abs_diff_finite': err, 'exact': y['exact']}
        require(clock + '/B3/local_ols_count', s.get('ols_decision_points_this_check') == 1)
        require(clock + '/B3/projection_days', s.get('basis_projection_days_this_check') == 4618 - 120)
        seam_summary[clock] = results
    flag('all_exact_flag_not_rewritten', body.get('seam_all_exact'), all(seam_exact_flags))
    return {
        'schema_id': 'factorlab.r3_boundary_cloud_review_checks@1.0',
        'decision': 'bounded_feature_artifact_reuse_not_provenance_certification',
        'task_status': 'completed_with_limits',
        'new_local_supplement_required': False,
        'frozen_scoring_interface_development_may_continue': True,
        'checks_passed': len(checks), 'checks': checks,
        'basis_diagnostic_atol': BASIS_DIAGNOSTIC_ATOL,
        'basis_tolerance_is_posthoc_numerical_review_not_performance_test': True,
        'seam_all_exact': all(seam_exact_flags), 'seam_summary': seam_summary,
        'membership_counts': membership,
        'B2_chronology_and_read_scope_disclosure_received': True,
        'B2_bounded_snapshot_content_identity_established': False,
        'B2_original_membership_generation_rule_equivalence_established': False,
        'original_success_status_not_used_as_acceptance': True,
        'known_2026_member_rows_were_read_before_filtering': True,
        'new_array_rewrite_required_by_checked_B1_B3': False,
        'scoring_executed_by_this_review': False,
        'strict_same_definition_provenance_certified': False,
        'scope': 'Exact uploaded small receipt arithmetic and flags only; no raw-array replay or source membership regeneration.',
        'PIT_certified': False, 'fresh_oos': False, 'production_authority': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        b = args.input.read_bytes()
        result = evaluate(read_json(args.input))
        result['input_git_blob'] = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
        result['input_sha256'] = hashlib.sha256(b).hexdigest()
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        print(json.dumps({'decision': result['decision'], 'checks_passed': result['checks_passed']}))
        return 0  # Successful *review computation*, not permission to score.
    except (KeyError, ValueError, TypeError, OSError) as exc:
        print(json.dumps({'status': 'invalid_evidence', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
