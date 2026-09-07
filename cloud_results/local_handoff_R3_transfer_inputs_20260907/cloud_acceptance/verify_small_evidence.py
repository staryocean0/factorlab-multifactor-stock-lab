"""Recompute the uploaded small receipts; no raw financial arrays or models.

Run with --results pointing at local_handoff_R3_transfer_inputs_20260907.
These checks validate reported identities/arithmetic, not the upstream producer.
"""
from pathlib import Path
import argparse,hashlib,json
from datetime import date

def sha(p): return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text(encoding='utf-8'))

def run(root):
    res=load(root/'result.json');checks=[];year_summary={}
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
    check('schema',res['schema_id']=='factorlab.r3_transfer_input_result@1.0')
    check('clocks',set(res['clocks'])=={'1430','1445'})
    check('not_scored',res['status']=='prepared_features_only_not_scored' and not res['generalization_evaluation_executed'])
    check('no_network_execution',all(res[k]==0 for k in ('new_model_fits','new_inference','checkpoint_reload')))
    check('no_promoted_claims',all(res[k] is False for k in ('future_labels_read','fresh_oos','PIT_certified','production_authority')))
    bodies={}
    for c,r in res['clocks'].items():
        m=load(root/c/'manifest.json');b=load(root/c/'bundle.json');d=load(root/c/'daily_support.json');p=load(root/c/'producer_sources.json');bodies[c]=d
        check(c+'_manifest_matches_main',m==r)
        check(c+'_bundle_raw_identity',sha(root/c/'bundle.json')==r['bindings']['bundle_manifest'])
        check(c+'_daily_raw_identity',sha(root/c/'daily_support.json')==r['artifact_digests']['daily_support.json'])
        check(c+'_source_snapshot_raw_identity',sha(root/c/'producer_sources.json')==b['artifact_digests']['producer_sources.json'])
        check(c+'_frozen_bindings_in_bundle',all(b[k]==r['bindings'][v] for k,v in [('reference_manifest_sha256','reference_manifest'),('frozen_selection_sha256','selection'),('frozen_normalizer_sha256','normalizer')]))
        check(c+'_frozen_files_in_store',r['artifact_digests']['normalizer.json']==r['bindings']['normalizer'] and r['artifact_digests']['frozen_selection.json']==r['bindings']['selection'])
        check(c+'_source_arrays_preserved_after_identity_mapping',all(b['artifact_digests'][n]==r['artifact_digests'][n] for n in ('calendar.npy','symbols.npy','exposure_decision_positions.npy','epsilon_history.npy','state_values.npy','state_available.npy','stock_factor_exposures.npy','exposure_reliability.npy','exposure_available.npy')))
        check(c+'_shape',r['symbol_count']==3982 and r['factor_count']==14 and r['feature_dim']==71 and r['sequence_points']==10)
        check(c+'_deadline',r['calendar_start']=='2007-01-04' and r['calendar_end']=='2025-12-31')
        check(c+'_copied_not_independent_prefix',b['historical_prefix_origin']==r['historical_prefix_origin']=='reused_accepted_arrays' and r['prefix_check_is_independent_producer_replay'] is False)
        check(c+'_no_refits_or_targets',b['selection_refit'] is False and b['normalizer_refit'] is False and b['labels_used_for_features'] is False)
        check(c+'_producer_roles',len(p['files'])==6 and len({f['role'] for f in p['files']})==6 and sorted(f['role'] for f in p['files'])==r['producer_sources']['roles'])
        expected={'epsilon_history':3406*3982,'state_values':6*3406*14,'state_available':6*3406*14,'stock_factor_exposures':584*3982*14,'exposure_reliability':584*3982*14,'exposure_available':584*3982*14}
        check(c+'_reported_prefix_cell_counts',all(r['prefix_checks'][k]['historical_cells_compared']==v and r['prefix_checks'][k]['passed'] is True for k,v in expected.items()))
        check(c+'_full_daily_lattice',len(d)==242 and [x['day_position'] for x in d]==list(range(3410,4616,5)))
        dates=[date.fromisoformat(x['date']) for x in d]
        check(c+'_dates_unique_increasing_bounded',dates==sorted(set(dates)) and dates[0]>=date(2021,1,1) and dates[-1]<=date(2025,12,31))
        check(c+'_support_conservation',all(x['universe']==3982 and x['included']+x['history_missing']+x['current_exposure_missing']==3982 and min(x['included'],x['history_missing'],x['current_exposure_missing'])>=0 for x in d))
        check(c+'_prediction_rows_recomputed',sum(x['included'] for x in d)==r['rows']['prediction_rows']==931677)
        check(c+'_maturity_rows_recomputed',sum(x['included'] for x in d if x['day_position']+20<4618)==r['rows']['maturity_eligible_rows']==916077)
        check(c+'_not_finite_target_claim',r['rows']['maturity_is_not_finite_target_or_event_availability'] is True and r['rows']['labels_used_for_support'] is False)
        check(c+'_old_rows_retained',r['rows']['original_rows_preserved']==853732)
        year_summary[c]={str(y):{'days':len([x for x in d if x['date'].startswith(str(y))]),'rows':sum(x['included'] for x in d if x['date'].startswith(str(y)))} for y in range(2021,2026)}
    check('same_two_clock_daily_tables',bodies['1430']==bodies['1445'])
    check('membership_hashes_not_in_producer_snapshot',all(all(f['path'].endswith('.py') for f in load(root/c/'producer_sources.json')['files']) for c in res['clocks']))
    # Last check is an observation about scope, not a positive raw-source certificate.
    return {'checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'daily_rows_per_clock':242,'by_year':year_summary,'unmatured_rows':931677-916077,'unmatured_days':4,'raw_arrays_rehashed':False,'original_producer_reexecuted':False,'source_boundary_accepted':False}

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--results',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    body=run(args.results)
    with args.output.open('x',encoding='utf-8') as f:json.dump(body,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:body[k] for k in ('passed','failed','daily_rows_per_clock','unmatured_rows')},ensure_ascii=False))
    raise SystemExit(int(body['failed']>0))
