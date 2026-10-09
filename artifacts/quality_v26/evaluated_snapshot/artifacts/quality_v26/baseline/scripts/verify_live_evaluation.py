"""Audit saved real outputs, corpus quotes, traces, frozen files and ledger IDs; no API."""
import hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json,write_json,utcnow

def main():
    full=read_json(ROOT/'artifacts/live/full_evaluation.json'); plan=read_json(ROOT/'artifacts/live/evaluation_plan.json')
    cases={x['id']:x for x in read_json(ROOT/'eval/cases.json')}; corpus={x['id']:x for x in read_json(ROOT/'data/corpus.json')}
    checks=[]; quote_count=0; ledger_ids=set(); configurations=set(); validation_failures=0
    def check(name,value): checks.append({'check':name,'passed':bool(value)})
    check('full run completed',full['complete'] and full['configuration_unchanged'])
    check('shared cap respected',full['cost_cumulative']['charged_or_reserved_usd']<=full['cumulative_cap_usd']<=5)
    check('83 evaluation invocations',full['model_invocations']==83)
    historical=ROOT/'artifacts/architecture_v1/frozen'
    for name,h in plan['frozen_files'].items():
        path=historical/name if historical.exists() else ROOT/name
        check('historical V1 frozen '+name,hashlib.sha256(path.read_bytes()).hexdigest()==h)
    def quotes(out):
        nonlocal quote_count
        retrieved={x['id'] for x in out['retrieved']}
        for c in out['summary']['sources']:
            row=corpus.get(c['evidence_id'])
            check('quote '+c['evidence_id'],row is not None and c['evidence_id'] in retrieved and
                  ' '.join(c['quote'].split()) in ' '.join(row['text'].split()) and c['source_id']==row['source_id'])
            quote_count+=1
        check('bounded turn '+out['case_id'],out['model_calls']<=1 and out['steps']<=5)
        if out['validation_error']: check('invalid answer failed closed '+out['case_id'],out['decision']=='escalate' and not out['summary']['sources'])
    for split in ('dev','test'):
        folder=ROOT/'artifacts/live'/split
        metrics=read_json(folder/'evaluation_metrics.json'); configurations.add(metrics['configuration_hash'])
        rows=[json.loads(x) for x in (folder/'answers.jsonl').read_text(encoding='utf-8').splitlines() if x]
        scenario=read_json(folder/'multi_turn_results.json'); traces=read_json(folder/'traces.json')
        expected={c['id'] for c in cases.values() if c['split']==split}
        check(split+' all 30 outputs',len(rows)==30 and len({(r['id'],r['method']) for r in rows})==30)
        check(split+' complete 5 scenarios',metrics['complete'] and metrics['scenarios']=={'n':5,'passed':5} and len(scenario)==5)
        for method in ('baseline','final'):
            group=[r for r in rows if r['method']==method]
            check(split+' '+method+' 15 cases',{r['id'] for r in group}==expected and len(group)==15)
            check(split+' '+method+' no automatic writes',not any(e['kind']=='action_committed' for e in traces[method]))
            computed=[]
            for r in group:
                c=cases[r['id']]; out=r['output']; quotes(out)
                relevant=set(c['relevant_source_ids']); got={x['source_id'] for x in out['retrieved']}
                recall=len(relevant&got)/len(relevant) if relevant else None
                check('saved recall '+r['id']+' '+method,r['source_recall_at_5']==recall)
                check('saved route '+r['id']+' '+method,r['decision_in_allowed_set']==(r['decision'] in c['allowed_decisions']))
                if recall is not None: computed.append(recall)
            check(split+' '+method+' aggregate recall',abs(metrics['metrics'][method]['source_recall_at_5']-statistics.mean(computed))<1e-12)
            validation_failures+=metrics['metrics'][method]['validation_failures']
        events=[e for group in traces.values() for e in group]
        for s in scenario:
            check('scenario '+s['id'],s['passed'] and s['actual_comments']==(0 if s['pattern']=='reject' else 1))
            check('scenario one commit '+s['id'],sum(e['kind']=='action_committed' for e in s['trace'])==(0 if s['pattern']=='reject' else 1))
            for out in s['turns']: quotes(out)
            events.extend(s['trace'])
        for event in events:
            if event['kind']=='turn_completed':
                usage=event['payload']['usage']
                check('real provider result '+event['case_id'],usage['mode']=='live' and usage.get('provider_requests')==1)
                ledger_ids.add(usage['ledger_id'])
    check('same development/test configuration',len(configurations)==1)
    before_ids={x['id'] for x in plan['cost_before']['calls']}
    new_calls=[x for x in full['cost_cumulative']['calls'] if x['id'] not in before_ids]
    check('every evaluation request has a trace',ledger_ids=={x['id'] for x in new_calls} and len(new_calls)==83)
    check('evaluation token costs confirmed',all(x['status']=='confirmed' for x in new_calls))
    check('run cost matches ledger',abs(sum(x['charged'] for x in new_calls)-full['new_confirmed_usd'])<1e-12)
    result={'at':utcnow(),'architecture':'v1','not_a_v2_evaluation':True,'passed':all(x['passed'] for x in checks),'checks':checks,'quotes_checked':quote_count,
            'comparison_validation_failures':validation_failures,'new_requests_checked':len(new_calls),
            'limitation':'Mechanical evidence/trace audit; not independent human semantic quality review.'}
    write_json(ROOT/'artifacts/live/evaluation_verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
    for item in checks:
        if not item['passed']: print('FAILED',item['check'])
    return result['passed']

if __name__=='__main__': sys.exit(0 if main() else 1)
