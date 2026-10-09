"""Offline audit of the paired quality benchmark; never a semantic grade."""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.quality import technical_source
from quality_result_files import result_paths

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation'
    manifest_path,scenario_path=result_paths(folder)
    plan=read_json(folder/'plan.json'); m=read_json(manifest_path); cases=read_json(folder/'frozen/eval/quality_cases.json')
    rows=read_json(folder/'answers.json'); scenarios=read_json(scenario_path); corpus=read_json(folder/'frozen/data/corpus_v2.json')
    by_id={r['id']:r for r in corpus}; checks=[]; quotes=0; ledger_ids=set()
    def check(name,yes): checks.append({'check':name,'passed':bool(yes)})
    check('complete planned comparison and scenarios',m['complete'] and len(rows)==2*len(cases)==40 and len(scenarios)==10)
    check('runtime unchanged during final evaluation',m['configuration_unchanged'] and digest(plan['files'])==m['configuration_hash'])
    for name,sha in plan['files'].items():
        check('frozen '+name,hashlib.sha256((folder/'frozen'/name).read_bytes()).hexdigest()==sha)
        check('current '+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha)
    selection=read_json(folder/'frozen/eval/quality_selection_manifest.json'); test={c['issue_number'] for c in cases if c['split']=='test_fresh'}
    check('runtime frozen before holdout acquisition',all(plan['files'].get(name)==sha for name,sha in selection['files_before_acquisition'].items()))
    candidates=read_json(ROOT/'eval/quality_candidates.json')
    check('selected reports unchanged from acquisition',digest(candidates)==selection['selected_input_sha256'] and all(next(c for c in cases if c['id']==raw['id'])['initial_message']==raw['initial_message'] and next(c for c in cases if c['id']==raw['id'])['initial_facts']==raw['initial_facts'] for raw in candidates))
    check('15 never-acquired holdouts',len(test)==15 and not test&set(selection['known_issue_numbers']))
    check('heldout not indexed',not test&{r.get('issue_number') for r in corpus})
    check('heldout not explicitly referenced',not any(re.search(r'(?:issues/|pull/|#)'+str(n)+r'\b',r['text']) for n in test for r in corpus))
    for split in ('dev','test_fresh'):
        ids={c['id'] for c in cases if c['split']==split}
        for variant in ('previous','revised'):
            group=[r for r in rows if r['split']==split and r['variant']==variant]
            check(split+' '+variant+' distinct cases',len(group)==len(ids)==(5 if split=='dev' else 15) and {r['id'] for r in group}==ids)
    def audit(out,key,new=True):
        nonlocal quotes
        if not out: return
        check('bounds '+key,out['model_calls']<=8 and out['repair_count']<=1 and len(out['retrieved'])<=5)
        retrieved={r['id'] for r in out['retrieved']}
        if out['validation_error']: check('safe fallback '+key,out['decision']=='escalate' and not out['summary']['sources'])
        else:
            j=out.get('judge') or {}; check('model judge accepted '+key,j.get('verdict')=='accept' and all(x==2 for x in j.get('scores',{}).values()) and not j.get('findings'))
        for cite in out['summary']['sources']:
            quotes+=1; row=by_id.get(cite['evidence_id'])
            check('quote '+key,row and row['id'] in retrieved and cite['source_id']==row['source_id'] and ' '.join(cite['quote'].split()) in ' '.join(row['text'].split()))
            if out.get('quality_revision'): check('technical citation '+key,technical_source(dict(row,text=cite['quote'])))
        if out['mode']=='live' and new:
            check('turn cost '+key,out['usage']['charged_or_reserved_usd']<=.04+1e-12)
            ledger_ids.update(u['ledger_id'] for u in out['usage']['stages'] if u.get('provider_requests'))
    for r in rows: audit(r['output'],r['split']+'/'+r['variant']+'/'+r['id'],not r.get('historical_reuse'))
    for variant in ('previous','revised'):
        trace=read_json(folder/(variant+'_traces.json'))
        check('no comparison actions '+variant,not any(x['kind']=='action_committed' for x in trace))
        provenance=read_json(folder/(variant+'_runtime_provenance.json'))
        expected=ROOT/'artifacts/architecture_v2/final_evaluation/frozen/src/casepilot' if variant=='previous' else ROOT/'src/casepilot'
        check('isolated runtime '+variant,Path(provenance['pipeline_path']).resolve()==(expected/'pipeline.py').resolve())
    check('scenario pass count honest',m['scenarios']=={'n':10,'passed':sum(s['passed'] for s in scenarios)})
    for s in scenarios:
        effects=0 if s['pattern']=='reject' or not s['passed'] else 1
        check('effects '+s['id'],s['actual_comments']==effects and sum(e['kind']=='action_committed' for e in s['trace'])==effects)
        for i,out in enumerate(s['turns']): audit(out,s['id']+'/'+str(i+1))
    if m['mode']=='live':
        before_ids={x['id'] for x in plan['cost_before']['calls']}; new=[x for x in m['cost_cumulative']['calls'] if x['id'] not in before_ids]
        # A transport failure during extraction may have no delivered output;
        # its ledger entry still remains in the campaign and manifest totals.
        check('all delivered stages accounted',ledger_ids<={x['id'] for x in new})
        check('new ledger count',len(new)==m['new_requests'])
        check('all charges retained',all(x['status'] in ('confirmed','uncertain_reserved') for x in new))
        check('delta matches ledger',abs(sum(x['charged'] for x in new)-m['new_charged_or_reserved_usd'])<1e-12)
        campaign=read_json(ROOT/'artifacts/quality_revision/campaign.json')
        cap=m.get('completion_cumulative_cap_usd',plan['cumulative_cap_usd'])
        check('campaign and team cap',m['cost_cumulative']['charged_or_reserved_usd']<=cap<=campaign['cumulative_cap_usd']<=5)
        if m.get('completion_provenance'):
            old=read_json(folder/'multi_turn_results.json');missing=read_json(folder/'missing_operational_results.json');cp=read_json(folder/'missing_operational_plan.json')
            check('only previously missing scenario attempted',m['completion_provenance']['only_previously_unstarted_scenarios']==['QS10'] and [x['id'] for x in missing]==['QS10'] and scenarios==old+missing)
            check('remaining cap planned before completion',cp['prepared_before_key_entry_and_inference'] and cp['cumulative_cap_usd']==cap and cp['only_never_started']==['QS10'] and not cp['failed_QS09_rerun'] and not cp['comparison_rerun'])
    result={'at':utcnow(),'passed':all(x['passed'] for x in checks),'checks':checks,'quotes_checked':quotes,
        'answers_sha256':hashlib.sha256((folder/'answers.json').read_bytes()).hexdigest(),
        'scenarios_file':scenario_path.name,'scenarios_sha256':hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
        'limitations':'Mechanical checks, not semantic response quality, human review or n8n deployment.'}
    write_json(folder/'verification.json',result); print(canonical({k:v for k,v in result.items() if k!='checks'}))
    for x in checks:
        if not x['passed']: print('FAILED',x['check'])
    return result['passed']
if __name__=='__main__': sys.exit(0 if main() else 1)
