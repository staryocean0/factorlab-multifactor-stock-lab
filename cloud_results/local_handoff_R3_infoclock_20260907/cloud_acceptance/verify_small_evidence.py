"""INFOCLOCK cloud small-evidence acceptance, not a raw-array/PIT rerun.

Usage: python checks.py --audit audit.json --spec run_spec.json \
 --script reaka_r3_information_clock_audit.py --output cloud_checks.json
All comparisons use bytes independently bound to Git blobs returned by GitHub.
"""
from __future__ import annotations
import argparse, ast, hashlib, importlib.util, json, platform, sys
from pathlib import Path
import numpy as np

EXPECTED={
 'audit':'a831728b311c00f3fbfa655e2236219b2e96be48',
 'spec':'3ef9cc032b7a799a3e9555538ea9e3c3e8064918',
 'script':'6e615bce1d81589fc38e1137038207c5ba27863e'}

def blob(b): return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def main():
 p=argparse.ArgumentParser();
 for key in EXPECTED: p.add_argument('--'+key, type=Path, required=True)
 p.add_argument('--output',type=Path,required=True); args=p.parse_args()
 checks=[]
 def ck(name, passed):
  ok=bool(passed); checks.append({'name':name,'passed':ok})
  if not ok: raise AssertionError(name)
 hashes={}
 for key in EXPECTED:
  data=getattr(args,key).read_bytes(); actual=blob(data)
  ck(key+'_exact_git_blob',actual==EXPECTED[key]); hashes[key]={'git_blob':actual,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
 audit=json.loads(args.audit.read_text()); spec=json.loads(args.spec.read_text())
 ck('scope_schema',audit['task_id']=='LCL-R3-INFOCLOCK-20260907-01' and audit['status']=='completed_with_limits')
 ck('zero_model_and_label_operations',all(audit[k]==0 for k in ('new_fits','new_inference','checkpoint_reload','future_labels_read','scores_read')))
 ck('no_financial_certification',all(audit[k] is False for k in ('PIT_certified','fresh_oos','production_authority','generalization_evaluation_executed')))
 ck('empty_time_evidence_is_unknown',spec['time_evidence']==[] and audit['time_evidence']=={'status':'unknown','rows':[],'PIT_certified':False})
 ck('both_clocks_reported',set(audit['clocks'])==set(spec['stores'])=={'1430','1445'})
 for c in ('1430','1445'):
  data=audit['clocks'][c]
  ck(c+'_seven_input_bindings_match_spec', len(data['input_raw_sha256'])==7 and data['input_raw_sha256']==spec['stores'][c]['expected_hashes'] and data['external_hash_bindings_checked']==sorted(data['input_raw_sha256']) and data['unbound_to_historical_receipt']==[])
  ck(c+'_calendar_end_and_no_extension',data['calendar_end']=='2020-12-31T00:00:00.000000000' and data['extension_rows_present'] is False)
  ck(c+'_overlapping_context_warning',data['all_counts_are_overlapping_contexts_not_independent_samples'] is True)
  for period, n, days, years in (('fit_context',361628,276,[2011,2016]),('consumed_discovery',408446,146,[2018,2020])):
   r=data['periods'][period]; prefix=c+'_'+period
   ck(prefix+'_support',r['years']==years and r['inference_rows']==n and r['decision_days']==days)
   ck(prefix+'_fold_checks',r['crossfold_endpoint_factor_checks']==days*10*14 and r['crossfold_differing_checks']==0 and r['within_same_fold_stock_variation_possible_by_schema'] is False)
   for typ in ('state_mask','state_values','masked_reliability'):
    s=r[typ]; label=prefix+'_'+typ
    ck(label+'_dimensions_and_slots',s['status']=='profiled' and s['context_slots_per_factor']==n*10 and all(len(s[k])==14 for k in ('min','max','mean','zero_fraction')))
    lo,hi,mean,zero=map(lambda k:np.array(s[k]),('min','max','mean','zero_fraction'))
    ck(label+'_finite_and_ordered',np.isfinite([lo,hi,mean,zero]).all() and (lo<=mean+1e-14).all() and (mean<=hi+1e-14).all() and (zero>=0).all() and (zero<=1).all())
    const=np.flatnonzero(lo==hi).tolist()
    ck(label+'_constant_flag_rederived',s['constant_factor_positions']==const and s['all_factor_channels_constant']==(len(const)==14))
    ck(label+'_zero_fraction_integer_compatible',np.allclose(zero*n*10,np.round(zero*n*10),atol=1e-7,rtol=0))
    if typ=='state_mask':
     ck(label+'_binary_means',np.allclose(mean+zero,1,atol=1e-14,rtol=0))
     ck(label+'_observed_constancy',const==([0] if period=='fit_context' else list(range(14))))
    if typ=='masked_reliability':
     ck(label+'_observed_range', (lo>=0).all() and (hi<=1).all() and const==[])
     implied_active=int(np.round((1-zero)*n*10).sum())
     ck(label+'_nonzero_matches_reported_active_on_this_support',implied_active==r['active_reliability_context_cells'])
     # Equality of marginal summaries is NOT cellwise equality of market/size values.
     ck(label+'_market_size_marginals_agree',all(s[k][0]==s[k][1] for k in ('min','max','mean','zero_fraction')))
  e=data['periods']['consumed_extension']
  ck(c+'_extension_empty_not_pass',e['years']==[2021,2025] and e['inference_rows']==e['decision_days']==0 and all(e[k]=={'status':'no_support','context_slots_per_factor':0} for k in ('state_mask','state_values','masked_reliability')))
 a=audit['clocks']['1430']; b=audit['clocks']['1445']
 ck('shared_masks_and_rows_digest',all(a['input_raw_sha256'][k]==b['input_raw_sha256'][k] for k in ('calendar.npy','inference_rows.npy','state_available.npy','exposure_decision_positions.npy','exposure_available.npy')))
 ck('actual_state_values_and_reliability_distinct',all(a['input_raw_sha256'][k]!=b['input_raw_sha256'][k] for k in ('state_values.npy','exposure_reliability.npy')))
 tree=ast.parse(args.script.read_text())
 imports={node.names[0].name.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.Import)}|{node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module}
 ck('no_model_runtime_import',not imports.intersection({'torch','factor_lab','tensorflow','jax'}))
 bound=importlib.util.spec_from_file_location('infoclock_review',args.script); mod=importlib.util.module_from_spec(bound); bound.loader.exec_module(mod)
 ck('only_seven_target_free_files',len(mod.FILES)==7 and all(not any(x in f for x in ('epsilon','score','label','checkpoint')) for f in mod.FILES))
 # Independent scalar reference on a small synthetic mixed-period store.
 rng=np.random.default_rng(1947); T=2500; N=7; F=14
 cal=np.arange(np.datetime64('2015-01-01'),np.datetime64('2015-01-01')+T)
 chosen=[200,220,1150,1170,2250]
 rows=np.array([[d,s,int(str(cal[d])[:4]),j%4] for j,d in enumerate(chosen) for s in range(N)],dtype=np.int64)
 masks=rng.integers(0,2,(6,T,F),dtype=np.uint8); state=rng.normal(size=(6,T,F)).astype(np.float32)
 rel=rng.uniform(0,1,(T,N,F)).astype(np.float32); em=rng.integers(0,2,(T,N,F),dtype=np.uint8)
 arrays=dict(zip(mod.FILES,[cal,rows,state,masks,np.arange(T,dtype=np.int64),rel,em]))
 before={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in arrays.items()}
 result=mod.profile_arrays(arrays,batch_size=3)
 for period,(year0,year1) in mod.PERIODS.items():
  lists={'state_mask':[],'state_values':[],'masked_reliability':[]}
  selected=[r for r in rows if year0<=r[2]<=year1]
  for d,s,_,_ in selected:
   for endpoint in range(int(d)-180,int(d)+1,20):
    lists['state_mask'].append([float(masks[s%5+1,endpoint,f]) for f in range(F)])
    lists['state_values'].append([float(state[s%5+1,endpoint,f]) for f in range(F)])
    lists['masked_reliability'].append([float(rel[endpoint,s,f]*em[endpoint,s,f]) for f in range(F)])
  for typ,v in lists.items():
   mat=np.array(v); got=result['periods'][period][typ]
   ck('synthetic_scalar_'+period+'_'+typ, np.allclose(mat.min(0),got['min']) and np.allclose(mat.max(0),got['max']) and np.allclose(mat.mean(0),got['mean']) and np.array_equal((mat==0).mean(0),got['zero_fraction']))
 ck('synthetic_inputs_not_mutated', before=={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in arrays.items()})
 # A fixed nonlinear map can change rankings with a constant feature. No market/model claim.
 h=np.array([-2.,-0.5,1.]); ck('constant_input_counterexample',not np.array_equal(np.argsort(h*h),np.argsort((h+1)**2)))
 slots=3616280
 zero_counts=np.round(np.array(a['periods']['fit_context']['state_mask']['zero_fraction'])*slots).astype(int)
 derived={'fit_mask_zero_context_counts_per_factor':zero_counts.tolist(),
 'fit_mask_zero_percent_market_size_industry':[0.,100*zero_counts[1]/slots,100*zero_counts[2]/slots],
 'discovery_mask_cells_per_clock':4084460*14,
 'support_note':'146 target-free inference days, not 142 labelled evaluation days; this audit does not read label support',
 'reliability_profile_note':'Raw masked reliability before fixed normalizer; identical marginal summaries do not imply cellwise identity.'}
 body={'schema_id':'factorlab.r3_infoclock_cloud_acceptance_checks@1.0','reviewed_commit':'879274409f79aceff72b0136c88138554a3c59a8','passed':len(checks),'failed':0,'scope':'Exact-byte small audit/spec plus isolated script and independent synthetic scalar checks. No original arrays, original manifests, producer rerun, model scores or PIT rerun.','inputs':hashes,'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()},'derived':derived,'checks':checks}
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(body,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 print(json.dumps({'passed':len(checks),'failed':0,'derived':derived},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
