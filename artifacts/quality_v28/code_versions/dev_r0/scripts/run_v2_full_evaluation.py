"""Frozen, capped V2 comparison + 10 synthetic operational scenarios.

Baseline is the SAME V2 corpus/pipeline with dense/MMR/rerank/judge disabled.
Gold labels never enter the agent. No tuning/retry after seeing final outputs.
Credentials stay in process memory. Approval actions affect isolated local DBs.
"""
import argparse, collections, csv, getpass, hashlib, json, os, shutil, statistics, sys, time
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.model import make_client
from casepilot.hybrid import HybridRetriever

VARIANTS={'baseline':{'dense':False,'mmr':False,'rerank':False,'judge':False},'full':{}}
FATAL={'budget_exhausted','provider_error','missing_credentials','embedding_index_not_ready'}

def hashes():
    files=list((ROOT/'src/casepilot').glob('*.py'))+list((ROOT/'schemas').glob('*.json'))+list((ROOT/'policies').glob('*.json'))
    files += [ROOT/n for n in ('data/corpus_v2.json','data/index_v2_manifest.json','eval/v2_final_cases.json',
        'eval/v2_final_scenarios.json','eval/v2_final_freeze.json','scripts/run_v2_full_evaluation.py')]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

def expect_error(fn,code):
    try: fn()
    except CasePilotError as exc:
        require(exc.code==code,'scenario_failure','خطای سناریو با انتظار مطابقت ندارد.'); return code
    raise CasePilotError('scenario_failure','اقدام ممنوع سناریو مسدود نشد.')

def scenario_run(plan,cases,client,hybrid,path,progress):
    case=cases[plan['case_id']]; cid=case['id']; store=Store(path); agent=Agent(store,client=client,hybrid=hybrid)
    outputs=[]; old=None; errors=[]; mode=plan['pattern']
    def turn(message,request,facts=None,checks=None):
        out=agent.turn(cid,message,request,facts or {},checks or []); outputs.append(out)
        progress({'scenario':plan['id'],'turn':len(outputs),'decision':out['decision'],'validation_error':out['validation_error']})
        if out['validation_error'] in FATAL: raise CasePilotError(out['validation_error'],'سناریو در سقف یا خطای درگاه متوقف شد.')
        return out
    try:
        turn(case['initial_message'],'scenario-start',case['initial_facts'],case['initial_checks'])
        for i,t in enumerate(plan['turns']):
            if mode=='stale' and i==1:
                p=outputs[-1]['proposal']; old=(p,store.review(cid,p['id'],p['hash'],'approve','بازبین برنامه‌ریزی‌شدهٔ آزمایش'))
            turn(t['message'],'follow-'+str(i),t.get('facts'),t.get('checks'))
        p=outputs[-1]['proposal']
        if mode=='correction':
            require(store.get(cid)['facts']['streamlit_version']=='1.49.0' and store.get(cid)['fact_history'],'scenario_failure','اصلاح حافظه ثبت نشده است.')
        if mode=='reject':
            store.review(cid,p['id'],p['hash'],'reject','بازبین برنامه‌ریزی‌شدهٔ آزمایش')
            require(not store.get(cid)['comments'],'scenario_failure','پس از رد نباید نظری ثبت شود.')
        else:
            if mode=='edit':
                first=store.review(cid,p['id'],p['hash'],'approve','بازبین برنامه‌ریزی‌شدهٔ آزمایش')
                edited=turn('توضیح تازه: پاسخ باید فقط درخواست بررسی باشد.','edited-input')['proposal']
                errors.append(expect_error(lambda:store.execute(cid,p['id'],first['approval_id']),'stale_approval'))
                changes=[{'type':'comment','body':'پاسخ ویرایش‌شده: لطفاً نتیجهٔ بررسی حداقلی را بفرستید.'},{'type':'status','value':'waiting_user'}]
                result=store.review(cid,edited['id'],edited['hash'],'edit','بازبین برنامه‌ریزی‌شدهٔ آزمایش',changes)
                p=next(x for x in store.get(cid)['proposals'] if x['id']==result['id'])
            if mode=='restart':
                store=Store(path); require(store.get(cid)['pending_proposal']==p['id'],'scenario_failure','پیشنهاد پس از بازگشایی پایگاه نمانده است.')
            if mode=='stale':
                previous,approval=old
                errors.append(expect_error(lambda:store.execute(cid,previous['id'],approval['approval_id']),'stale_approval'))
            approval=store.review(cid,p['id'],p['hash'],'approve','بازبین برنامه‌ریزی‌شدهٔ آزمایش')
            if mode=='cross_case':
                store.update('other-case','پروندهٔ دیگر')
                errors.append(expect_error(lambda:store.execute('other-case',p['id'],approval['approval_id']),'approval_required'))
                require(not store.get('other-case')['comments'],'scenario_failure','پروندهٔ دیگر تغییر کرد.')
            if mode in ('before_commit','after_commit'):
                code='tool_unavailable' if mode=='before_commit' else 'connection_lost'
                errors.append(expect_error(lambda:store.execute(cid,p['id'],approval['approval_id'],fail=mode),code))
                require(len(store.get(cid)['comments'])==(0 if mode=='before_commit' else 1),'scenario_failure','تعداد ثبت پس از قطع ارتباط نادرست است.')
            store.execute(cid,p['id'],approval['approval_id'])
            if mode in ('after_commit','duplicate'):
                require(store.execute(cid,p['id'],approval['approval_id'])['replayed'],'scenario_failure','اجرای مجدد یک‌باره نبود.')
            if mode=='duplicate':
                t=plan['turns'][-1]; replay=agent.turn(cid,t['message'],'follow-0',t.get('facts',{}),t.get('checks',[]))
                require(replay['request_replayed'],'scenario_failure','درخواست تکراری بازپخش نشد.')
            require(len(store.get(cid)['comments'])==1 and store.get(cid)['status']!='closed','scenario_failure','سناریو ثبت ایمن را رعایت نکرد.')
        return dict(plan,passed=True,turns=outputs,blocked_errors=errors,actual_comments=len(store.get(cid)['comments']),trace=store.traces())
    except CasePilotError as exc:
        return dict(plan,passed=False,error=exc.code,turns=outputs,blocked_errors=errors,actual_comments=len(store.get(cid)['comments']),trace=store.traces())

def aggregate(rows):
    result={}
    for split in ('dev','test_fresh'):
        result[split]={}
        for variant in VARIANTS:
            group=[r for r in rows if r['split']==split and r['variant']==variant]
            recalls=[r['source_recall_at_5'] for r in group if r['source_recall_at_5'] is not None]
            result[split][variant]={'n':len(group),'source_recall_at_5':statistics.mean(recalls) if recalls else None,
                'decision_rubric_proxy':statistics.mean(r['decision_in_allowed_set'] for r in group) if group else None,
                'median_latency_seconds':statistics.median(r['output']['latency_seconds'] for r in group) if group else None,
                'decisions':dict(collections.Counter(r['output']['decision'] for r in group)),
                'validation_failures':sum(r['output']['validation_error'] is not None for r in group),
                'repair_count':sum(r['output'].get('repair_count',0) for r in group),
                'model_judge_accept':sum((r['output'].get('judge') or {}).get('verdict')=='accept' for r in group)}
    return result

def run(mode,label,additional_cap):
    identifier(label); require(0<additional_cap<=.90,'invalid_budget','سقف اضافهٔ این اجرا حداکثر نود سنت است.')
    folder=ROOT/'artifacts/architecture_v2'/label
    require(not folder.exists(),'evaluation_exists','نتیجهٔ قبلی بازنویسی یا خودکار تکرار نمی‌شود.')
    cases=read_json(ROOT/'eval/v2_final_cases.json'); plans=read_json(ROOT/'eval/v2_final_scenarios.json')
    require(len(cases)==30 and len(plans)==10,'invalid_cases','ارزیابی کامل سی پرونده و ده سناریو می‌خواهد.')
    frozen=hashes(); client=make_client(mode); before=client.budget.report() if mode=='live' else {'requests':0,'confirmed_usd':0,'charged_or_reserved_usd':0,'calls':[]}
    if mode=='live': client.budget.cap=min(5,before['charged_or_reserved_usd']+additional_cap)
    config={'files':frozen,'variants':VARIANTS,'model':getattr(client,'model','test-fixture'),
        'judge_model':os.getenv('METIS_JUDGE_MODEL',getattr(client,'model','test-fixture')),
        'max_calls_per_turn':8,'max_turn_usd':.04,'max_turn_seconds':180,
        'max_output_tokens':getattr(client,'max_output',None),'additional_cap_usd':additional_cap,
        'input_rate':getattr(client,'ir',None),'output_rate':getattr(client,'orate',None)}
    folder.mkdir(parents=True); dbdir=ROOT/'runtime'/label; dbdir.mkdir(parents=True,exist_ok=True)
    for name,h in frozen.items():
        dest=folder/'frozen'/name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/name,dest)
        require(hashlib.sha256(dest.read_bytes()).hexdigest()==h,'configuration_changed','ثبت پیکربندی ناموفق بود.')
    hybrid=HybridRetriever(client); config['embedding']=hybrid.cache.embedder.identity
    rows=[]; scenarios=[]; traces={}; error=None; started=utcnow()
    write_json(folder/'evaluation_plan.json',{'started_at':started,'configuration':config,'configuration_hash':digest(config),
        'expected_outputs':60,'expected_scenarios':10,'cost_before':before,
        'protocol':'No prompt/retrieval/data changes after freeze. All delivered safe fallbacks included. Baseline uses same V2 corpus and role code with dense/MMR/rerank/judge disabled. Same current-snapshot evaluation policy. Scripted reviewer is not human review.'})
    def log(record): print(canonical(record),flush=True)
    def checkpoint():
        (folder/'answers.jsonl').write_text(''.join(canonical(r)+'\n' for r in rows),encoding='utf-8')
        write_json(folder/'multi_turn_results.json',scenarios); write_json(folder/'traces.json',traces)
        write_json(folder/'progress.json',{'at':utcnow(),'outputs':len(rows),'scenarios':len(scenarios),'error':error,'configuration_hash':digest(config)})
    try:
        for split in ('dev','test_fresh'):
            for variant,components in VARIANTS.items():
                store=Store(dbdir/(split+'_'+variant+'.sqlite3')); agent=Agent(store,client=client,hybrid=hybrid,components=components)
                for case in (c for c in cases if c['split']==split):
                    require(hashes()==frozen,'configuration_changed','پیکربندی حین ارزیابی تغییر کرد.')
                    log({'event':'case_start','case':case['id'],'split':split,'variant':variant})
                    out=agent.turn(case['id'],case['initial_message'],'final-eval-'+variant,case['initial_facts'],case['initial_checks'])
                    relevant=set(case['relevant_source_ids']); got={r['source_id'] for r in out['retrieved']}
                    rows.append({'id':case['id'],'split':split,'variant':variant,'category':case['category'],
                        'source_recall_at_5':len(relevant&got)/len(relevant) if relevant else None,
                        'decision_in_allowed_set':out['decision'] in case['allowed_decisions'],'output':out})
                    traces[split+'_'+variant]=store.traces(); checkpoint()
                    log({'event':'case_done','case':case['id'],'variant':variant,'decision':out['decision'],
                        'validation_error':out['validation_error'],'usage':out['usage']['charged_or_reserved_usd'] if mode=='live' else 0})
                    if out['validation_error'] in FATAL: raise CasePilotError(out['validation_error'],'خطای نهایی یا سقف اجرا رسید.')
        by_id={c['id']:c for c in cases}
        for plan in plans:
            require(hashes()==frozen,'configuration_changed','پیکربندی تغییر کرد.')
            scenario=scenario_run(plan,by_id,client,hybrid,dbdir/(plan['id']+'.sqlite3'),log); scenarios.append(scenario); checkpoint()
            if not scenario['passed'] and scenario.get('error') in FATAL: raise CasePilotError(scenario['error'],'سناریو متوقف شد.')
    except Exception as exc:
        error=exc.code if isinstance(exc,CasePilotError) else type(exc).__name__; log({'event':'stopped','error':error})
    finally:
        after=client.budget.report() if mode=='live' else before
        complete=len(rows)==60 and len(scenarios)==10 and error is None
        manifest={'started_at':started,'finished_at':utcnow(),'mode':mode,'architecture':'v2','complete':complete,'error':error,
            'configuration':config,'configuration_hash':digest(config),'configuration_unchanged':hashes()==frozen,
            'comparison_outputs':len(rows),'metrics':aggregate(rows),'scenarios':{'n':len(scenarios),'passed':sum(s['passed'] for s in scenarios)},
            'new_requests':after['requests']-before['requests'],'new_confirmed_usd':after['confirmed_usd']-before['confirmed_usd'],
            'new_charged_or_reserved_usd':after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],'cost_cumulative':after,
            'cumulative_cap_usd':client.budget.cap if mode=='live' else 0,'fresh_final_holdout_evaluation':mode=='live' and complete,
            'independent_human_review':False,'ai_review_pending':True,
            'limitations':['Decision-in-allowed-set is a route proxy, not answer accuracy. Source recall labels are approximate and AI-authored.',
                'Freshness refers to author acquisition/output exposure, not absence from model pretraining; unknown families may remain.',
                'Synthetic follow-ups and scripted approvals only in isolated local trackers. n8n instance untested.',
                'Offline embedder and judge are fixtures; offline metrics do not measure learned-model quality.',
                'Baseline disables four components together; this comparison cannot identify causal contribution of each component.']}
        checkpoint(); write_json(folder/'manifest.json',manifest)
        log({'event':'finished','complete':complete,'outputs':len(rows),'scenarios':manifest['scenarios'],
            'new_cost_usd':manifest['new_charged_or_reserved_usd'],'cumulative_usd':after['charged_or_reserved_usd']})
        return manifest

def main():
    p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['replay','live'],default='replay'); p.add_argument('--label',default='final_preflight')
    p.add_argument('--additional-cap-usd',type=float,default=.90); a=p.parse_args()
    key=''
    if a.mode=='live':
        require(not (ROOT/'artifacts/architecture_v2'/a.label).exists(),'evaluation_exists','خروجی موجود است.')
        url='https://api.metisai.ir/api/v1/meta/providers/pricing'
        with urlopen(url,timeout=20) as response: prices=json.load(response)
        chat=next(x for x in prices['llm'] if x['model']=='gpt-4.1-mini'); embed=next(x for x in prices['embedding'] if x['model']=='text-embedding-3-small')
        require(all(x['currency']=='USD' and x['fixedCallIncome']==0 for x in (chat,embed)),'invalid_prices','تعرفه سازگار نیست.')
        write_json(ROOT/'artifacts/architecture_v2/final_pricing_snapshot.json',{'at':utcnow(),'source':url,'models':[chat,embed]})
        os.environ.update(METIS_BASE_URL='https://api.metisai.ir/openai/v1',METIS_MODEL='gpt-4.1-mini',METIS_EMBEDDING_MODEL='text-embedding-3-small',
            CASEPILOT_INPUT_USD_PER_MILLION=str(chat['inputTokenUnitIncome']*1e6),CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['outputTokenUnitIncome']*1e6),
            CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['inputTokenUnitIncome']*1e6),CASEPILOT_MAX_OUTPUT_TOKENS='1000',
            CASEPILOT_BUDGET_USD='5',CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'))
        key=os.getenv('METIS_API_KEY') or getpass.getpass('Metis API key (hidden): '); os.environ['METIS_API_KEY']=key
    try: result=run(a.mode,a.label,a.additional_cap_usd)
    finally:
        if a.mode=='live': os.environ.pop('METIS_API_KEY',None); key=''
    return result['complete']
if __name__=='__main__': sys.exit(0 if main() else 1)
