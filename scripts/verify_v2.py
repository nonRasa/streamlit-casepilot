"""No-network audit of V2 configurations, evidence, judge gates and actual costs."""
import hashlib, json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.accounting import Budget
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.model import MetisClient
from casepilot.hybrid import HybridRetriever

def main():
    checks=[]
    def check(name,value):
        checks.append({'check':name,'passed':bool(value)})
        if not value: print('FAILED',name)
    corpus={r['id']:r for r in read_json(ROOT/'data/corpus_v2.json')}
    live=ROOT/'artifacts/architecture_v2/live'; newest=None; all_ledger_ids=set()
    for path in sorted(live.glob('*/manifest.json'),key=lambda p:p.stat().st_mtime):
        manifest=read_json(path); folder=path.parent; newest=path
        check(folder.name+' run labeled development',manifest['split']=='dev' and not manifest['fresh_final_holdout_evaluation'])
        for name,h in manifest['configuration']['files'].items():
            check(folder.name+' frozen '+name,hashlib.sha256((folder/'frozen'/name).read_bytes()).hexdigest()==h)
        rows=[json.loads(line) for line in (folder/'answers.jsonl').read_text(encoding='utf-8').splitlines() if line]
        check(folder.name+' saved every case',len(rows)==manifest['cases'])
        traces=read_json(folder/'traces.json'); check(folder.name+' no automatic write',not any(e['kind']=='action_committed' for e in traces))
        for row in rows:
            out=row['output']; label=folder.name+' '+row['id']
            check(label+' bounded',out['model_calls']<=8 and out['repair_count']<=1 and out['steps']<=14)
            check(label+' accepted or safe escalation',(not out['validation_error'] and out['judge']['verdict']=='accept') or (out['validation_error'] and out['decision']=='escalate' and not out['summary']['sources']))
            check(label+' proposal scoped',out['proposal']['case_id']==out['case_id'] and bool(out['proposal']['hash']))
            if not out['validation_error']:
                check(label+' judge all criteria passed',all(s==2 for s in out['judge']['scores'].values()) and not out['judge']['findings'])
            stages=out['usage']['stages']; actual=[u for u in stages if u.get('provider_requests')]
            check(label+' every request accounted',len(actual)==out['usage']['provider_requests'])
            check(label+' stage costs aggregate',abs(sum(u.get('cost_usd',0) for u in stages)-out['usage']['cost_usd'])<1e-12)
            all_ledger_ids.update(u['ledger_id'] for u in actual)
            allowed={r['id'] for r in out['retrieved']}
            for c in out['summary']['sources']:
                r=corpus.get(c['evidence_id'])
                check(label+' exact quote '+c['evidence_id'],r is not None and r['id'] in allowed and ' '.join(c['quote'].split()) in ' '.join(r['text'].split()) and c['source_id']==r['source_id'])
    check('at least one live development run',newest is not None)
    if newest:
        current=read_json(newest)
        check('latest run completed',current['complete'])
        check('latest run matches current implementation',all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in current['configuration']['files'].items()))
    budget_path=ROOT/'runtime/team_budget.sqlite3'; cost=Budget(budget_path).report()
    ids={r['id'] for r in cost['calls']}; check('live stage ledger IDs exist',all_ledger_ids<=ids)
    check('course cap respected',cost['charged_or_reserved_usd']<=5)
    check('operational half-dollar cap respected',cost['charged_or_reserved_usd']<=.50)
    build=read_json(ROOT/'artifacts/architecture_v2/embedding_build_live.json')
    check('real learned embedding build',build['mode']=='live' and build['dimensions']==1536 and build['chunks']==len(corpus) and build['identity']['model']=='text-embedding-3-small')
    embedding_rows=[u for u in build['cache']['usage'] if u.get('provider_requests')]
    check('embedding build ledger IDs exist',all(u['ledger_id'] in ids for u in embedding_rows))
    check('embedding build deduplicates',build['cache']['unique_missing']<build['chunks'])
    cache_audit={'performed':False,'reason':'Private runtime caches not present in exported submission.'}
    if (ROOT/'runtime/embeddings_live.sqlite3').exists() and (ROOT/'artifacts/live_cache').exists():
        with tempfile.TemporaryDirectory(prefix='casepilot-cache-audit-') as temp:
            env={'METIS_API_KEY':'offline-cache-audit-not-a-real-key','METIS_MODEL':'gpt-4.1-mini','METIS_BASE_URL':'https://api.metisai.ir/openai/v1',
                 'METIS_EMBEDDING_MODEL':'text-embedding-3-small','CASEPILOT_EMBEDDING_USD_PER_MILLION':'.022',
                 'CASEPILOT_INPUT_USD_PER_MILLION':'.44','CASEPILOT_OUTPUT_USD_PER_MILLION':'1.76','CASEPILOT_MAX_OUTPUT_TOKENS':'1000','CASEPILOT_BUDGET_USD':'.50'}
            with patch.dict(os.environ,env),patch('casepilot.model.build_opener',side_effect=AssertionError('NETWORK FORBIDDEN')) as network:
                client=MetisClient(Path(temp)/'budget.sqlite3'); agent=Agent(Store(Path(temp)/'tracker.sqlite3'),client=client,hybrid=HybridRetriever(client))
                case=next(c for c in read_json(ROOT/'eval/cases.json') if c['id']=='GH9218')
                first=agent.turn(case['id'],case['initial_message'],'cache-audit',case['initial_facts'],case['initial_checks'])
                before_calls=client.calls; again=agent.turn(case['id'],case['initial_message'],'cache-audit',case['initial_facts'],case['initial_checks'])
                check('real saved responses reused without network',network.call_count==0 and client.budget.report()['requests']==0 and first['validation_error'] is None)
                check('durable duplicate costs nothing',again['request_replayed'] and client.calls==before_calls and again['proposal']['hash']==first['proposal']['hash'])
                cache_audit={'performed':True,'network_requests':network.call_count,'new_paid_requests':client.budget.report()['requests'],'duplicate_model_invocations':client.calls-before_calls}
    result={'at':utcnow(),'architecture':'v2','passed':all(c['passed'] for c in checks),'checks':checks,'private_cache_audit':cache_audit,
            'latest_live_run':str(newest.parent.relative_to(ROOT)) if newest else None,'cost_cumulative':{k:v for k,v in cost.items() if k!='calls'},
            'limitations':['Mechanical/runtime audit, not independent human semantic review.','Development smoke is not a fresh final benchmark.','n8n instance import/run remains external.']}
    write_json(ROOT/'artifacts/architecture_v2/verification.json',result)
    print(canonical({k:result[k] for k in ('passed','latest_live_run','private_cache_audit')})); print('checks',len(checks)); return result['passed']

if __name__=='__main__': sys.exit(0 if main() else 1)
