"""Review-schema counterexamples using the uploaded small receipt; no markets."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT/'cloud_results/local_handoff_R3_transfer_inputs_20260907'
P = EVIDENCE/'cloud_delta_acceptance/verify_boundary_evidence.py'
s = importlib.util.spec_from_file_location('boundary_review', P)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)

@pytest.fixture
def body():
    return m.read_json(EVIDENCE/'boundary_checks.json')


def test_actual_report_values_close_B1_B3_but_not_member_provenance(body):
    x=m.evaluate(body)
    assert x['decision']=='bounded_feature_artifact_reuse_not_provenance_certification'
    assert x['scoring_executed_by_this_review'] is False
    assert x['seam_all_exact'] is False
    assert x['B2_chronology_and_read_scope_disclosure_received'] is True


def test_success_label_is_never_a_seam_override(body):
    body['clocks']['1430']['B3_seam']['beta'].update(max_abs_diff_finite=.25, exact=False)
    with pytest.raises(ValueError, match='difference_limit'):
        m.evaluate(body)


@pytest.mark.parametrize('kind', ['missing','shape','empty','support','nan','inf','exact_lie','large_basis','drifted_beta','cells','bool_count'])
def test_seam_counterexamples_rejected(body,kind):
    seam=body['clocks']['1430']['B3_seam']; x=seam['beta']
    if kind=='missing': del seam['beta']
    elif kind=='shape': x['shape_match']=False
    elif kind=='empty': x['both_finite']=0
    elif kind=='support': x['support_equal']=False
    elif kind=='nan': x['max_abs_diff_finite']=float('nan')
    elif kind=='inf': x['max_abs_diff_finite']=float('inf')
    elif kind=='exact_lie': x['exact']=False
    elif kind=='large_basis': seam['factor_basis_at_last_d5']['max_abs_diff_finite']=.1
    elif kind=='drifted_beta': x.update(max_abs_diff_finite=1e-15,exact=False)
    elif kind=='cells': x['cells']=50000
    elif kind=='bool_count': x['both_finite']=True
    with pytest.raises((ValueError,KeyError)):
        m.evaluate(body)


@pytest.mark.parametrize('kind', ['counts','no_support','missing_date','violation','date2026','targets'])
def test_member_report_checks_do_not_silently_pass(body,kind):
    x=body['B2_membership']['core']
    if kind=='counts': x['rows_after_full_file_read']+=1
    elif kind=='no_support': x['rows_mapped_to_incumbent_3982']=0
    elif kind=='missing_date': x['missing_dates']=1
    elif kind=='violation': x['effective_le_asof_violations']=1
    elif kind=='date2026': x['used_asof_max']='2026-01-02 00:00:00'
    elif kind=='targets': body['B2_membership']['core_target_filter'].pop()
    with pytest.raises(ValueError): m.evaluate(body)


def test_false_all_exact_not_upgraded(body):
    body['seam_all_exact']=True
    with pytest.raises(ValueError,match='all_exact'):m.evaluate(body)


def test_b1_nonfinite_counts_must_really_close(body):
    body['clocks']['1445']['B1_state_tail']['tail_nonfinite']=1
    with pytest.raises(ValueError):m.evaluate(body)


def test_unscored_is_not_synonymous_with_zero_bool_count(body):
    body['new_model_fits']=False
    with pytest.raises(ValueError):m.evaluate(body)


@pytest.mark.parametrize('text',['{"a":1,"a":2}', '{"a": NaN}', '[]'])
def test_json_not_silently_coerced(tmp_path,text):
    p=tmp_path/'x.json';p.write_text(text)
    with pytest.raises(ValueError):m.read_json(p)
