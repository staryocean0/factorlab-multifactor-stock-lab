#!/usr/bin/env python3
"""One-off cloud review of a published R2 summary and isolated audit predicates.

No FactorLab arrays, market data, model fitting or Actions are used. Tests execute
verbatim function/expression excerpts of local auditor blob a003fe75...; they are
NOT an end-to-end execution of that auditor. Pass means the reported observation
was reproduced, including deliberately demonstrating false-positive gates.
"""
from __future__ import annotations
import argparse, hashlib, json, math, platform, sys, tempfile
from pathlib import Path
from typing import Any
import numpy as np

SUMMARY_BLOB='89f89a3524c5643bd55ae7554f29210c9087328a'
AUDITOR_COMMIT='8ffdd90b5a664337058fad4a301f85ddfa6aa599'
AUDITOR_BLOB='a003fe75fbb127761b63b963c320deecd88de539'
# Verbatim isolated helper from scripts/reaka_r2_local_audit_v1.py:79-112.
DIGEST_ROW_SOURCE='''def digest_row(path: Path, expected: str | None, convention: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": str(path),
        "expected": expected,
        "convention": convention,
    }
    if not path.exists():
        row["status"] = "missing"
        return row
    row["size_bytes"] = path.stat().st_size
    row["raw_sha256"] = sha256_file(path)
    if expected is None:
        row["status"] = "present_unbound"
    elif convention == "raw_sha256":
        if row["raw_sha256"] == expected:
            row["status"] = "byte_match"
        elif path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            canonical = payload.get("canonical_digest")
            row["embedded_canonical_digest"] = canonical
            if canonical == expected:
                row["status"] = "byte_match"
                row["convention"] = "canonical_digest"
            else:
                row["status"] = "byte_mismatch"
        else:
            row["status"] = "byte_mismatch"
    else:
        row["raw_matches_recorded"] = row["raw_sha256"] == expected
        row["status"] = "present_unbound"
    return row
'''

def sha256_file(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()

def canonical(body):
    # Original producer canonicalization.py uses default ensure_ascii=True.
    return 'sha256:'+hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def strict_json(data):
    def pairs(items):
        obj={}
        for key,val in items:
            if key in obj: raise ValueError('duplicate key: '+key)
            obj[key]=val
        return obj
    def constant(value): raise ValueError('nonfinite JSON: '+value)
    return json.loads(data,object_pairs_hook=pairs,parse_constant=constant)

def review_summary(path):
    data=path.read_bytes()
    blob=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
    if blob!=SUMMARY_BLOB: raise ValueError('This receipt review is pinned to the submitted summary; input bytes changed')
    s=strict_json(data)
    checks=[]
    def check(name,ok): checks.append({'check':name,'passed':bool(ok)})
    def metric(name,e):
        ok=type(e['compared']) is int and e['compared']>0
        ok=ok and all(type(e[k]) is int and e[k]==0 for k in ('only_left_finite','only_right_finite','violations'))
        ok=ok and all(type(e[k]) in (int,float) and math.isfinite(e[k]) and e[k]>=0 for k in ('max_abs','p99_abs'))
        ok=ok and e['p99_abs']<=e['max_abs']
        check(name,ok)
    check('summary.no_full_PIT_claim',s['full_pit_certified'] is False)
    check('summary.declared_tolerance',s['tolerance']['atol']==1e-6 and s['tolerance']['rtol']==1e-5)
    check('A.reported_counts_only_not_file_rehash',s['A']['counts']=={'byte_match':81,'byte_mismatch':0,'present_unbound':0,'missing':0})
    for clock in ('14:30','14:45'):
        b=s['B']['clocks'][clock]
        metric('B.'+clock+'.history',b['history']); metric('B.'+clock+'.future',b['future'])
        check('B.'+clock+'.counts',b['inference_rows']-b['evaluation_rows']==b['inference_without_future'])
    sample=s['B']['datahub_sample']
    check('B.sample_declared_scope',sample['status']=='passed' and sample['mismatches']==0 and len(sample['predeclared_days'])==5 and len(sample['symbols'])==4)
    for suffix in ('1430','1445'):
        c=s['C_'+suffix]
        metric('C.'+suffix+'.history_stored_support',c['history_on_stored_support'])
        metric('C.'+suffix+'.future_stored_support',c['future_on_stored_support'])
        rows=c['ols_spot']['rows'];matches=[r for r in rows if r.get('match') is True]
        check('C.'+suffix+'.OLS_counts',len(matches)==c['ols_spot']['compared']==10 and len(rows)==16)
        for i,r in enumerate(matches):metric('C.'+suffix+'.OLS.'+str(i),r['error'])
        d=s['D_'+suffix]
        check('D.'+suffix+'.selection_consumed',d['selection_clock']['fresh_oos_claimed'] is False and d['selection_clock']['years_consumed_for_selection']==list(range(2009,2021)))
        for r in d['prefix']:
            metric('D.'+suffix+'.'+r['family']+'.prefix',r['prefix_vs_full'])
            metric('D.'+suffix+'.'+r['family']+'.stored',r['recomputed_vs_stored'])
        e=s['E_bind_'+suffix]['binding']
        metric('E.'+suffix+'.epsilon_history',e['epsilon_history_vs_ot1']);metric('E.'+suffix+'.epsilon_future',e['epsilon_future_vs_ot1'])
        check('E.'+suffix+'.axis_flags',all(e[k] is True for k in ('calendar_match_p61','symbol_match_p61','decision_match_p61','labelled_is_finite_future_subset')))
    e=s['E_infer'];metric('E.frozen_inference_slice',e['error'])
    check('E.slice_not_all',e['n']==e['error']['compared']==512 and e['review_len']==e['stored_review_len']==82321 and e['clock']=='14:30' and e['seed']==11 and e['retrained'] is False)
    f=s['F_stage4']
    check('F.duplicate_counts',f['pairing_rows']-f['pairing_unique_period_clock_role']==sum(v-1 for v in f['duplicate_keys'].values())==4)
    check('F.still_unaccepted',f['status']=='failed_historical_uniqueness' and f['deduplicated'] is False and f['conservation_verified'] is False)
    return {'input_git_blob':blob,'input_sha256':sha256_file(path),'checks':checks,'passed_checks':sum(x['passed'] for x in checks),'failed_checks':sum(not x['passed'] for x in checks),'scope':'published_summary_internal_consistency_not_reexecution_of_local_arrays'}

def predicate_counterexamples():
    result=[]
    def record(name,observed,expected,scope):
        ok=observed==expected
        result.append({'case':name,'observed':observed,'expected_reproduction':expected,'reproduced':bool(ok),'scope':scope})
        assert ok,name
    ns={'Path':Path,'Any':Any,'json':json,'sha256_file':sha256_file}
    exec(compile(DIGEST_ROW_SOURCE,'pinned_digest_row_excerpt','exec'),ns)
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory)/'changed.json'
        expected=canonical({'value':1})
        p.write_text(json.dumps({'value':999,'canonical_digest':expected}))
        old=ns['digest_row'](p,expected,'raw_sha256')
        record('A.stale_embedded_digest_is_accepted',old['status'],'byte_match','verbatim digest_row function; stale JSON body')
        record('A.actual_body_rehash_detects_change',canonical({'value':999})!=expected,True,'independent original canonicalization formula')
    # Exact relevant acceptance expressions from audit_p61/audit_ot1/audit_ot2.
    sample={'status':'blocked_missing_dependency'}
    record('B.missing_datahub_is_not_failed',sample['status']!='failed',True,'audit_p61 conjunct; other conjuncts may be true')
    ev=np.array([],dtype=np.int64);infer=np.array([[0,0,2009,0]]);infer_future=np.array([True])
    eval_ok=bool(len(ev)==0 or (int(ev.max())<len(infer) and bool(np.array_equal(np.sort(ev),np.flatnonzero(infer_future)))))
    record('B.empty_evaluation_list_is_accepted',eval_ok,True,'verbatim eval_ok expression despite one finite label')
    hist_stored={'violations':0,'compared':1,'only_left_finite':0,'only_right_finite':1}
    fut_stored=dict(hist_stored);ols={'status':'passed'}
    residual_cal_ok=residual_sym_ok=fold_ok=fit_check=True;uses_future=False
    passed=(residual_cal_ok and residual_sym_ok and fold_ok and (not uses_future) and fit_check and hist_stored['violations']==0 and fut_stored['violations']==0 and hist_stored['compared']>0 and fut_stored['compared']>0 and ols['status']=='passed')
    record('C.missing_reconstruction_support_is_accepted',passed,True,'audit_ot1 passed expression ignores only_*_finite')
    prefix_rows=[{'prefix_stable':True,'recomputed_vs_stored':{'violations':1}}];transport_clock=True;tools={'fresh_oos':False}
    passed=all(item['prefix_stable'] for item in prefix_rows) and transport_clock and tools.get('fresh_oos') is False
    record('D.stored_state_mismatch_is_ignored',passed,True,'audit_ot2 passed expression ignores recomputed_vs_stored')
    err={'compared':0,'violations':0,'only_left_finite':0,'only_right_finite':0}
    prefix_stable=err['violations']==0 and err['only_left_finite']==0 and err['only_right_finite']==0
    record('D.empty_comparison_is_prefix_stable',prefix_stable,True,'audit_ot2 prefix_stable expression lacks nonempty support check')
    record('time.end_label_does_not_make_open_strictly_later',(14*60+31)-1==14*60+30,True,'logical 1-minute end-labelled interval boundary; not empirical fill validation')
    return result

def small_bindings(root):
    specs=[('selected_tools_1430.json','8bb5a47e1439d13515f48b6f73cedc09e1a356ff'),('selected_tools_1445.json','632f23c7fe2f22d97c6b5b9f068a7c249fa54dea'),('ot2_manifest_1430.json','7d9dbd91ceb7442d756761b75e409510fed84625'),('ot2_manifest_1445.json','95ee7602bd222e70ff1386d1c5cdb7b0840813fa')]
    out=[];objects={}
    for name,blob in specs:
        p=root/name;data=p.read_bytes();actual=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        assert actual==blob,name
        obj=strict_json(data);computed=canonical({k:v for k,v in obj.items() if k!='canonical_digest'})
        assert computed==obj['canonical_digest'],name
        objects[name]=obj
        out.append({'file':name,'git_blob_sha1':actual,'raw_sha256':sha256_file(p),'computed_canonical':computed,'matches_embedded':True})
    for suffix in ('1430','1445'):
        assert objects['selected_tools_'+suffix+'.json']['canonical_digest']==objects['ot2_manifest_'+suffix+'.json']['selection_digest']
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary',type=Path,required=True)
    p.add_argument('--small-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    report={'schema_id':'factorlab.r2_cloud_review_checks@1.0','reviewed_commit':AUDITOR_COMMIT,'auditor_git_blob':AUDITOR_BLOB,'execution_location':'current_cloud_session','python':sys.version,'platform':platform.platform(),'numpy':np.__version__,'review_helper_sha256':sha256_file(Path(__file__)),'market_arrays_loaded':False,'github_actions_used':False}
    report['summary_review']=review_summary(a.summary)
    report['counterexamples']=predicate_counterexamples()
    report['small_original_bindings']=small_bindings(a.small_dir)
    report['all_declared_checks_completed']=report['summary_review']['failed_checks']==0
    report['full_pit_verified']=False;report['financial_acceptance']=False
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({'summary_checks':len(report['summary_review']['checks']),'failed':report['summary_review']['failed_checks'],'isolated_reproductions':len(report['counterexamples']),'original_json_bodies_verified':len(report['small_original_bindings']),'full_pit_verified':False},indent=2))
    return 0 if report['all_declared_checks_completed'] else 1
if __name__=='__main__':raise SystemExit(main())
