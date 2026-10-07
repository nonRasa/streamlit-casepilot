"""Offline/live comparison with explicit proxy metrics and immutable run manifests."""
from __future__ import annotations
import argparse, collections, hashlib, json, statistics, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.store import Store
from casepilot.agent import Agent
from casepilot.retrieval import Retriever
from casepilot.model import make_client

def expect_error(fn,code):
    try: fn()
    except CasePilotError as exc:
        assert exc.code==code,(exc.code,code); return exc.code
    raise AssertionError('Expected '+code)

def scenario_run(scenario,cases,retriever,client,tmp):
    cid=scenario['case_id']; case=cases[cid]; store=Store(tmp/(scenario['id']+'.sqlite3'))
    agent=Agent(store,retriever,client); turns=[]
    turns.append(agent.turn(cid,case['initial_message'],'start',case['initial_facts'],case['initial_checks']))
    mode=scenario['pattern']; old=None
    for index,turn in enumerate(scenario['turns']):
        if mode=='stale' and index==1:
            p=turns[-1]['proposal']; old=(p,store.review(cid,p['id'],p['hash'],'approve','بازبین آزمایشی'))
        turns.append(agent.turn(cid,turn['message'],'follow-'+str(index),turn.get('facts',{}),turn.get('checks',[])))
    p=turns[-1]['proposal']; errors=[]
    if mode=='correction':
        state=store.get(cid); assert state['facts']['streamlit_version']=='1.49.0' and state['fact_history']
    if mode=='reject':
        store.review(cid,p['id'],p['hash'],'reject','بازبین آزمایشی'); assert not store.get(cid)['comments']
        return {'id':scenario['id'],'passed':True,'pattern':mode,'actual_comments':0,'turns':turns,'trace':store.traces()}
    if mode=='edit':
        reviewed=store.review(cid,p['id'],p['hash'],'approve','بازبین آزمایشی')
        # Editing an already-approved proposal is prohibited; user gets a fresh proposal.
        edited=agent.turn(cid,'توضیح تازه: پاسخ باید فقط درخواست بررسی باشد.','edited-input',facts={})['proposal']
        errors.append(expect_error(lambda:store.execute(cid,p['id'],reviewed['approval_id']),'stale_approval'))
        changes=[{'type':'comment','body':'پاسخ ویرایش‌شده: لطفاً نتیجهٔ بررسی حداقلی را بفرستید.'},{'type':'status','value':'waiting_user'}]
        edit_result=store.review(cid,edited['id'],edited['hash'],'edit','بازبین آزمایشی',changes)
        p=next(x for x in store.get(cid)['proposals'] if x['id']==edit_result['id'])
    if mode=='restart': store=Store(store.path); agent=Agent(store,retriever,client); assert store.get(cid)['pending_proposal']==p['id']
    if mode=='stale':
        previous,approval=old
        errors.append(expect_error(lambda:store.execute(cid,previous['id'],approval['approval_id']),'stale_approval'))
    review=store.review(cid,p['id'],p['hash'],'approve','بازبین آزمایشی')
    if mode=='cross_case':
        store.update('other-case','پروندهٔ دیگر و مستقل')
        errors.append(expect_error(lambda:store.execute('other-case',p['id'],review['approval_id']),'approval_required'))
        assert not store.get('other-case')['comments']
    if mode in ('before_commit','after_commit'):
        error='tool_unavailable' if mode=='before_commit' else 'connection_lost'
        errors.append(expect_error(lambda:store.execute(cid,p['id'],review['approval_id'],fail=mode),error))
        expected=0 if mode=='before_commit' else 1; assert len(store.get(cid)['comments'])==expected
    result=store.execute(cid,p['id'],review['approval_id'])
    if mode in ('after_commit','duplicate'):
        retry=store.execute(cid,p['id'],review['approval_id']); assert retry['replayed']
    if mode=='duplicate':
        t=scenario['turns'][-1]
        again=agent.turn(cid,t['message'],'follow-0',t.get('facts',{}),t.get('checks',[])); assert again['request_replayed']
    assert len(store.get(cid)['comments'])==1
    assert store.get(cid)['status']!='closed'
    return {'id':scenario['id'],'passed':True,'pattern':mode,'actual_comments':1,'blocked_errors':errors,'execution':result,'turns':turns,'trace':store.traces()}

def run(split='all',mode='replay',limit=None,with_scenarios=True):
    cases=read_json(ROOT/'eval'/'cases.json'); selected=[c for c in cases if split=='all' or c['split']==split]
    if limit: selected=selected[:limit]
    retriever=Retriever(); client=make_client(mode); records=[]; scenarios=[]; started=utcnow(); start=time.perf_counter(); stopped=None
    with tempfile.TemporaryDirectory(prefix='casepilot-eval-') as folder:
        tmp=Path(folder)
        for method in ('baseline','final'):
            agent=Agent(Store(tmp/(method+'.sqlite3')),retriever,client)
            for c in selected:
                try:
                    out=agent.turn(c['id'],c['initial_message'],'eval-'+method,c['initial_facts'],c['initial_checks'],method)
                    relevant=set(c['relevant_source_ids']); got={x['source_id'] for x in out['retrieved']}
                    records.append({'id':c['id'],'split':c['split'],'category':c['category'],'method':method,
                                    'source_recall_at_5':len(relevant&got)/len(relevant) if relevant else None,
                                    'decision_in_allowed_set':out['decision'] in c['allowed_decisions'],
                                    'decision':out['decision'],'validation_error':out['validation_error'],'latency_seconds':out['latency_seconds'],
                                    'model_calls':out['model_calls'],'usage':out['usage'],'output':out})
                except CasePilotError as exc:
                    stopped=exc.code
                    if exc.code in ('budget_exhausted','provider_error'): break
                    raise
            if stopped: break
        if with_scenarios and not stopped:
            allcases={c['id']:c for c in cases}
            for scenario in read_json(ROOT/'eval'/'scenarios.json'):
                if split!='all' and scenario['split']!=split: continue
                if limit and scenario['case_id'] not in {c['id'] for c in selected}: continue
                try: scenarios.append(scenario_run(scenario,allcases,retriever,client,tmp))
                except CasePilotError as exc:
                    stopped=exc.code
                    if exc.code in ('budget_exhausted','provider_error'): break
                    raise
    metrics={}
    for method in ('baseline','final'):
        rows=[r for r in records if r['method']==method]
        labelled=[r['source_recall_at_5'] for r in rows if r['source_recall_at_5'] is not None]
        metrics[method]={'n':len(rows),'recall_labelled_n':len(labelled),'source_recall_at_5':statistics.mean(labelled) if labelled else None,
                         'decision_rubric_proxy':statistics.mean(r['decision_in_allowed_set'] for r in rows) if rows else None,
                         'validation_failures':sum(bool(r['validation_error']) for r in rows),
                         'median_latency_seconds':statistics.median(r['latency_seconds'] for r in rows) if rows else None,
                         'by_category':{cat:{'n':len(group),'decision_rubric_proxy':statistics.mean(r['decision_in_allowed_set'] for r in group)} for cat in ('answerable','ambiguous','escalate') if (group:=[r for r in rows if r['category']==cat])}}
    manifest={'started_at':started,'finished_at':utcnow(),'mode':mode,'split':split,'selected_cases':len(selected),'complete':len(records)==2*len(selected) and stopped is None,
              'stopped_reason':stopped,'elapsed_seconds':time.perf_counter()-start,'provider_execution':mode=='live',
              'limitations':['Replay is a deterministic test policy, not LLM quality evidence.','Decision set match is a permissive routing proxy, not correctness or usefulness.','Source-level qrels are prospective manual annotations; independent human review still required.','Test cases were seen during dataset authoring; this is not a blind external benchmark.'],
              'configuration_hash':digest({'schema':read_json(ROOT/'schemas'/'answer.schema.json') if (ROOT/'schemas'/'answer.schema.json').exists() else {},'snapshot':read_json(ROOT/'data'/'snapshot_manifest.json')['files'],'model':getattr(client,'model','deterministic-replay')}),
              'metrics':metrics,'scenarios':{'n':len(scenarios),'passed':sum(s['passed'] for s in scenarios)},
              'cost':client.budget.report() if mode=='live' else {'requests':0,'input_tokens':0,'output_tokens':0,'embedding_requests':0,'embedding_cost_usd':0,'charged_or_reserved_usd':0,'mode':'replay'}}
    run_label=split+(f'_sample_{limit}' if limit else '')
    outdir=ROOT/'artifacts'/('live' if mode=='live' else 'offline')/run_label; outdir.mkdir(parents=True,exist_ok=True)
    write_json(outdir/'evaluation_metrics.json',manifest)
    write_json(outdir/'multi_turn_results.json',scenarios)
    (outdir/'answers.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    if mode=='live':
        write_json(ROOT/'artifacts'/'live_run_manifest.json',{'status':'complete' if manifest['complete'] else 'partial','latest_run':str(outdir.relative_to(ROOT)),'provider_requests_cumulative':manifest['cost']['requests'],'stopped_reason':stopped,'n8n_status':'Not verified by local model evaluation; user imports and tests separately.'})
    emit={k:manifest[k] for k in ('mode','split','complete','stopped_reason','metrics','scenarios','cost')}; print(json.dumps(emit,ensure_ascii=False,indent=2))
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--split',choices=['dev','test','all'],default='dev'); p.add_argument('--mode',choices=['replay','live'],default='replay'); p.add_argument('--limit',type=int); p.add_argument('--no-scenarios',action='store_true')
    a=p.parse_args(); run(a.split,a.mode,a.limit,not a.no_scenarios)
