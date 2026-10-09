"""Audit V2 final outputs, source spans, freeze, operational actions and ledger offline."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from run_v2_full_evaluation import aggregate

def main(label='final_evaluation'):
    identifier(label); folder=ROOT/'artifacts/architecture_v2'/label
    manifest=read_json(folder/'manifest.json'); plan=read_json(folder/'evaluation_plan.json')
    cases={c['id']:c for c in read_json(folder/'frozen/eval/v2_final_cases.json')}
    corpus=read_json(folder/'frozen/data/corpus_v2.json'); by_id={c['id']:c for c in corpus}
    rows=[json.loads(x) for x in (folder/'answers.jsonl').read_text(encoding='utf-8').splitlines() if x]
    scenarios=read_json(folder/'multi_turn_results.json'); traces=read_json(folder/'traces.json'); checks=[]; ledger_ids=set(); quotes=0
    def check(name,value): checks.append({'check':name,'passed':bool(value)})
    check('all planned outputs and scenarios processed',manifest['complete'] and len(rows)==60 and len(scenarios)==10)
    check('configuration unchanged',manifest['configuration_unchanged'] and digest(manifest['configuration'])==manifest['configuration_hash']==plan['configuration_hash'])
    for name,h in manifest['configuration']['files'].items():
        check('frozen '+name,hashlib.sha256((folder/'frozen'/name).read_bytes()).hexdigest()==h)
        # The old final run is now a preserved historical benchmark. Its own
        # exact frozen runtime is authoritative, not a subsequently edited app.
    test={c['issue_number'] for c in cases.values() if c['split']=='test_fresh'}
    old={c['issue_number'] for c in read_json(ROOT/'eval/cases.json')}
    acquired={c['number'] for c in read_json(ROOT/'data/issues_snapshot.json')}
    check('15 newly acquired holdouts',len(test)==15 and not test&old and not test&acquired)
    check('no indexed holdout source',not test&{c.get('issue_number') for c in corpus})
    import re
    check('no explicit holdout references in corpus',not any(re.search(r'(?:issues/|pull/|#)'+str(n)+r'\b',r['text']) for n in test for r in corpus))
    def output(out,key):
        nonlocal quotes
        check('bounded '+key,out.get('architecture')=='v2' and out['model_calls']<=8 and out['repair_count']<=1 and len(out['retrieved'])<=5)
        retrieved={r['id'] for r in out['retrieved']}
        for cite in out['summary']['sources']:
            row=by_id.get(cite['evidence_id']); quotes+=1
            check('quote '+key+' '+cite['evidence_id'],row is not None and row['id'] in retrieved and row['source_id']==cite['source_id'] and ' '.join(cite['quote'].split()) in ' '.join(row['text'].split()))
        if out['validation_error']:
            check('failed closed '+key,out['decision']=='escalate' and not out['summary']['sources'])
        if out['components']['judge'] and not out['validation_error']:
            judge=out.get('judge') or {}
            check('full output judged '+key,judge.get('verdict')=='accept' and all(v==2 for v in judge.get('scores',{}).values()) and not judge.get('findings'))
        if manifest['mode']=='live':
            check('turn spending bound '+key,out['usage']['charged_or_reserved_usd']<=.04+1e-12)
            for usage in out['usage']['stages']:
                if usage.get('provider_requests'): ledger_ids.add(usage['ledger_id'])
    for split in ('dev','test_fresh'):
        expected={c['id'] for c in cases.values() if c['split']==split}
        for variant in ('baseline','full'):
            group=[r for r in rows if r['split']==split and r['variant']==variant]
            check('15 distinct '+split+' '+variant,len(group)==15 and {r['id'] for r in group}==expected)
            check('no comparison actions '+split+' '+variant,not any(e['kind']=='action_committed' for e in traces[split+'_'+variant]))
            for r in group:
                out=r['output']; output(out,split+'/'+variant+'/'+r['id']); c=cases[r['id']]
                relevant=set(c['relevant_source_ids']); got={x['source_id'] for x in out['retrieved']}
                check('saved recall '+r['id']+variant,r['source_recall_at_5']==(len(relevant&got)/len(relevant) if relevant else None))
                check('saved route '+r['id']+variant,r['decision_in_allowed_set']==(out['decision'] in c['allowed_decisions']))
    check('aggregate metrics reproduce',aggregate(rows)==manifest['metrics'])
    check('ten scenarios recorded with honest pass count',manifest['scenarios']=={'n':10,'passed':sum(s['passed'] for s in scenarios)})
    for scenario in scenarios:
        expected=0 if scenario['pattern']=='reject' or not scenario['passed'] else 1
        check('bounded effects '+scenario['id'],scenario['actual_comments']==expected and sum(e['kind']=='action_committed' for e in scenario['trace'])==expected)
        if not scenario['passed']:
            check('failed scenario preserved '+scenario['id'],scenario.get('error') in ('provider_error','budget_exhausted','embedding_index_not_ready','scenario_failure') and scenario['turns'])
        for i,out in enumerate(scenario['turns']): output(out,scenario['id']+'/'+str(i+1))
    if manifest['mode']=='live':
        before={r['id'] for r in plan['cost_before']['calls']}; new=[r for r in manifest['cost_cumulative']['calls'] if r['id'] not in before]
        check('all new requests accounted',ledger_ids=={r['id'] for r in new} and len(new)==manifest['new_requests'])
        check('charges confirmed or conservatively reserved',all(r['status'] in ('confirmed','uncertain_reserved') for r in new))
        if manifest.get('continuation_helper_sha256'):
            check('continuation helper preserved',hashlib.sha256((folder/'frozen/scripts/resume_v2_full_evaluation.py').read_bytes()).hexdigest()==manifest['continuation_helper_sha256'])
            interrupted=read_json(folder/'interrupted_manifest.json')
            check('original interruption retained',not interrupted['complete'] and interrupted['error']=='provider_error')
        check('run delta matches ledger',abs(sum(r['charged'] for r in new)-manifest['new_charged_or_reserved_usd'])<1e-12)
        check('incremental budget',manifest['new_charged_or_reserved_usd']<=manifest['configuration']['additional_cap_usd']<=.90)
        check('team budget',manifest['cost_cumulative']['charged_or_reserved_usd']<=manifest['cumulative_cap_usd']<=5)
    result={'at':utcnow(),'passed':all(c['passed'] for c in checks),'checks':checks,'quotes_checked':quotes,'new_requests_checked':len(ledger_ids),
        'answers_sha256':hashlib.sha256((folder/'answers.jsonl').read_bytes()).hexdigest(),
        'scenario_answers_sha256':hashlib.sha256((folder/'multi_turn_results.json').read_bytes()).hexdigest(),
        'limitations':'Mechanical audit, not semantic review, independent human review or n8n execution.'}
    write_json(folder/'verification.json',result)
    print(canonical({k:v for k,v in result.items() if k!='checks'}))
    for c in checks:
        if not c['passed']: print('FAILED',c['check'])
    return result['passed']
if __name__=='__main__': sys.exit(0 if main(sys.argv[1] if len(sys.argv)>1 else 'final_evaluation') else 1)
