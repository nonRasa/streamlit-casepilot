"""Development-only V2 evaluation/ablations with frozen configuration and cost cap.

The old test set has been reviewed, so it cannot become a fresh final holdout by
renaming its results. This runner intentionally accepts development cases only.
"""
import argparse, hashlib, json, os, shutil, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.agent import Agent
from casepilot.model import make_client
from casepilot.store import Store
from casepilot.hybrid import HybridRetriever

VARIANTS={'full':{},'no_dense':{'dense':False},'no_mmr':{'mmr':False},'no_rerank':{'rerank':False},'no_judge':{'judge':False}}

def run(mode='replay',limit=2,variant='full',label='development',additional_cap=.10):
    identifier(label); require(variant in VARIANTS,'invalid_method','روش آزمایش معتبر نیست.')
    require(1<=limit<=15 and 0<additional_cap<=.25,'invalid_budget','حد نمونه یا هزینهٔ آزمایش معتبر نیست.')
    folder=ROOT/'artifacts/architecture_v2'/('live' if mode=='live' else 'offline')/(label+'_'+variant)
    require(not (folder/'manifest.json').exists() and not (folder/'answers.jsonl').exists(),'evaluation_exists','خروجی قبلی حفظ شد؛ برای اجرای تازه نام مجزا لازم است.')
    client=make_client(mode); before=client.budget.report() if mode=='live' else {'requests':0,'charged_or_reserved_usd':0,'confirmed_usd':0}
    if mode=='live': client.budget.cap=min(client.budget.cap,before['charged_or_reserved_usd']+additional_cap)
    hybrid=HybridRetriever(client); files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/casepilot').glob('*.py')}
    files['data/corpus_v2.json']=hashlib.sha256((ROOT/'data/corpus_v2.json').read_bytes()).hexdigest()
    for name in ('scripts/evaluate_v2.py','eval/cases.json','data/index_v2_manifest.json','policies/judge_rubric.json'):
        files[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    config={'files':files,'variant':variant,'components':VARIANTS[variant],'model':getattr(client,'model','test-fixture'),
            'embedding':hybrid.cache.embedder.identity,'judge_model':os.getenv('METIS_JUDGE_MODEL',getattr(client,'model','test-fixture')),
            'max_calls':8,'max_turn_usd':.04,'retrieval_k':8,'context_k':5}
    cases=[c for c in read_json(ROOT/'eval/cases.json') if c['split']=='dev'][:limit]; answers=[]; stopped=None
    folder.mkdir(parents=True,exist_ok=True)
    if mode=='live':
        for name,h in files.items():
            target=folder/'frozen'/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/name,target)
            require(hashlib.sha256(target.read_bytes()).hexdigest()==h,'configuration_changed','نسخهٔ ثبت‌شده با پیکربندی تطابق ندارد.')
    def checkpoint():
        (folder/'answers.jsonl').write_text(''.join(canonical(r)+'\n' for r in answers),encoding='utf-8')
        write_json(folder/'progress.json',{'at':utcnow(),'done':len(answers),'expected':len(cases),'configuration_hash':digest(config),'stopped_reason':stopped})
    with tempfile.TemporaryDirectory(prefix='casepilot-v2-eval-') as tmp:
        store=Store(Path(tmp)/'tracker.sqlite3'); agent=Agent(store,client=client,hybrid=hybrid,components=VARIANTS[variant])
        for case in cases:
            try:
                require(all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in files.items()),'configuration_changed','پیکربندی حین آزمایش تغییر کرد.')
                out=agent.turn(case['id'],case['initial_message'],'v2-eval',case['initial_facts'],case['initial_checks'])
                relevant=set(case['relevant_source_ids']); got={r['source_id'] for r in out['retrieved']}
                answers.append({'id':case['id'],'split':'dev','variant':variant,'source_recall_at_5':len(relevant&got)/len(relevant) if relevant else None,'output':out})
                checkpoint(); print(canonical({'case':case['id'],'decision':out['decision'],'model_calls':out['model_calls'],'validation_error':out['validation_error'],'usage':{k:v for k,v in out['usage'].items() if k!='stages'}}),flush=True)
                if out['validation_error'] in ('budget_exhausted','turn_budget_exhausted','provider_error','call_limit','turn_timeout','embedding_index_not_ready'):
                    stopped=out['validation_error']; break
            except CasePilotError as exc: stopped=exc.code; break
        write_json(folder/'traces.json',store.traces())
    after=client.budget.report() if mode=='live' else before
    manifest={'at':utcnow(),'architecture':'v2','mode':mode,'split':'dev','variant':variant,'complete':len(answers)==len(cases) and stopped is None,
              'stopped_reason':stopped,'configuration':config,'configuration_hash':digest(config),'cases':len(answers),
              'new_requests':after['requests']-before['requests'],'new_confirmed_usd':after['confirmed_usd']-before['confirmed_usd'],
              'new_charged_or_reserved_usd':after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],
              'cost_cumulative':after,'independent_human_review':False,'fresh_final_holdout_evaluation':False,
              'limitations':['Offline embeddings/reranking/judging are explicit fixtures, not learned-model quality results.',
                  'Model judge is a separate invocation, not an independent human or proof of correctness.',
                  'Existing test was seen during V1 AI review. A newly isolated holdout is required for a final V2 quality claim.']}
    checkpoint(); write_json(folder/'manifest.json',manifest); return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['replay','live'],default='replay'); p.add_argument('--limit',type=int,default=2)
    p.add_argument('--variant',choices=VARIANTS,default='full'); p.add_argument('--label',default='development'); p.add_argument('--additional-cap-usd',type=float,default=.10)
    a=p.parse_args(); r=run(a.mode,a.limit,a.variant,a.label,a.additional_cap_usd); print(canonical({k:v for k,v in r.items() if k not in ('configuration','cost_cumulative')})); sys.exit(0 if r['complete'] else 1)
