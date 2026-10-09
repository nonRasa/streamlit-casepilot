"""زوج یگانه با توقف فوری؛ کلید فقط در حافظه و ورودی پنهان."""
import argparse,csv,getpass,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from urllib.request import urlopen
from evaluate_quality_v25_live import ledger,configuration,pair_fits,sha
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/quality_v26';FOLDER=BASE/'live_comparison_01'
CAP=2.004717190;STAGE_START=1.704717190
STOP={'provider_error','provider_timeout','provider_connection_error','provider_http_error','provider_response_invalid',
      'model_output_invalid','model_output_incomplete','model_output_blocked','judge_contract_error','invalid_judge',
      'case_type_contract_error','budget_exhausted','turn_budget_exhausted','turn_timeout','call_limit','context_limit','invalid_model_output'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(p)
def frozen():
    paths=[]
    for root in (ROOT/'src',ROOT/'tests',ROOT/'schemas',ROOT/'policies',BASE/'baseline'):
        paths.extend(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths+=list((ROOT/'data').glob('*.json'))
    paths+=[Path(__file__),ROOT/'scripts/evaluate_quality_v26_offline.py',ROOT/'scripts/evaluate_quality_v25_live.py',
        ROOT/'docs/QUALITY_V26_PROTOCOL_FA.md',BASE/'baseline_manifest.json',BASE/'offline_metrics.json',BASE/'capacity.json',
        BASE/'frozen_offline_tests/test_results.json',FOLDER/'authorization_plan.json',FOLDER/'review_rubric.json',ROOT/'artifacts/quality_v22/holdout/cases.json']
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}
def preflight():
    auth=read(FOLDER/'authorization_plan.json')
    assert all(sha(ROOT/n)==v for n,v in auth['production_files'].items()),'Production changed'
    assert read(BASE/'frozen_offline_tests/test_results.json')['passed'] and read(BASE/'offline_metrics.json')['live_gate_passed']
    assert not (FOLDER/'comparison_plan.json').exists() and not (ROOT/'runtime/quality_v26/live_comparison_01').exists(),'No retry'
    before=ledger();assert pair_fits(before['charged_or_reserved_usd'],CAP),'Insufficient full-pair capacity'
    return before
def worker(variant):
    plan=read(FOLDER/'comparison_plan.json');assert frozen()==plan['files'],'Frozen files changed'
    source=BASE/'baseline/src' if variant=='previous' else ROOT/'src';sys.path.insert(0,str(source))
    import casepilot.common as common
    common.ROOT=ROOT
    from casepilot.agent import Agent
    from casepilot.model import MetisClient
    from casepilot.store import Store
    from casepilot.hybrid import HybridRetriever
    import casepilot.pipeline as pipeline
    assert Path(pipeline.__file__).is_relative_to(source) and pipeline.MAX_CALLS==8 and pipeline.MAX_TURN_USD==.04
    path=FOLDER/'turns'/('GH17011_'+variant+'.json');started_path=FOLDER/'started'/(variant+'.json')
    assert not path.exists() and not started_path.exists(),'No retry'
    os.environ.update(configuration(plan['pricing'],CAP));client=MetisClient();client.budget.cap=CAP
    store=Store(ROOT/'runtime/quality_v26/live_comparison_01'/(variant+'.sqlite3'));agent=Agent(store,client=client,hybrid=HybridRetriever(client))
    output=None;failure=None;start=time.perf_counter();write(started_path,{'variant':variant,'at':time.time(),'no_retry':True})
    try:
        case=plan['case'];output=agent.turn(case['id'],case['initial_message'],'live-v26-'+variant,case['initial_facts'],case['initial_checks'])
    except Exception as exc:failure=getattr(exc,'code',type(exc).__name__)
    finally:
        write(path,{'id':'GH17011','variant':variant,'split':'development_seen','output':output,'failure':failure,
            'usage':client.usage_history,'elapsed_seconds':time.perf_counter()-start,'pipeline_sha256':sha(Path(pipeline.__file__))})
        write(FOLDER/(variant+'_traces.json'),store.traces());client.key=''
def summarize(plan,stop):
    after=ledger();rows=[read(p) for p in sorted((FOLDER/'turns').glob('*.json'))];before=plan['cost_before']
    manifest={'complete':len(rows)==2 and not stop,'stop_reason':stop,'attempted':len(rows),'paired_cases':int(len(rows)==2),
        'not_started':[v for v in ('revised','previous') if not any(r['variant']==v for r in rows)],
        'new_requests':after['requests']-before['requests'],'new_confirmed_usd':after['confirmed_usd']-before['confirmed_usd'],
        'new_uncertain_reserved_usd':after['uncertain_reserved_usd']-before['uncertain_reserved_usd'],
        'new_charged_or_reserved_usd':after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],
        'remaining_stage_usd':CAP-after['charged_or_reserved_usd'],'stage_charged_or_reserved_usd':after['charged_or_reserved_usd']-STAGE_START,
        'cumulative_cap_usd':CAP,'cost_before':before,'cost_after':after,'frozen_unchanged':frozen()==plan['files'],
        'human_review':False,'independent_review':False,'panel_balance_observed':False,'site_workflow_run':False}
    write(FOLDER/'manifest.json',manifest)
    with (FOLDER/'human_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['پرونده','نسخه','هش پاسخ','فایده','دلیل','بازبین'])
        for r in rows:
            if r['output']:w.writerow([r['id'],r['variant'],hashlib.sha256(r['output']['response'].encode()).hexdigest(),'','',''])
    return manifest
def main():
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--worker',choices=['previous','revised']);args=p.parse_args()
    if args.worker:worker(args.worker);return
    before=preflight()
    if not args.live:print(json.dumps({'passed':True,'provider_requests':0,'planned_pairs':1,'remaining_stage_usd':CAP-before['charged_or_reserved_usd']},ensure_ascii=False));return
    url='https://api.metisai.ir/api/v1/meta/providers/pricing'
    with urlopen(url,timeout=20) as response:prices=json.load(response)
    chat=next(x for x in prices['llm'] if x['model']=='gpt-4.1-mini');embed=next(x for x in prices['embedding'] if x['model']=='text-embedding-3-small')
    assert all(x['currency']=='USD' and x['fixedCallIncome']==0 for x in (chat,embed))
    assert chat['inputTokenUnitIncome']>0 and chat['outputTokenUnitIncome']>0 and embed['inputTokenUnitIncome']>0
    key=os.getenv('METIS_API_KEY')
    if not key:
        if not sys.stdin.isatty():raise SystemExit('توقف: ورودی پنهان تعاملی لازم است.')
        key=getpass.getpass('Metis API key (hidden): ')
    assert key and key.strip(),'Missing credential'
    before=ledger();assert pair_fits(before['charged_or_reserved_usd'],CAP),'Insufficient full-pair capacity'
    case=next(c for c in read(ROOT/'artifacts/quality_v22/holdout/cases.json') if c['id']=='GH17011')
    case={k:case[k] for k in ('id','initial_message','initial_facts','initial_checks')}
    env=os.environ.copy();env.update(configuration({'chat':chat,'embedding':embed},CAP),METIS_API_KEY=key);key=''
    plan={'mode':'live','at':time.time(),'case':case,'input_sha256':hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest(),
        'order':['revised','previous'],'files':frozen(),'cost_before':before,'cumulative_cap_usd':CAP,'original_stage_start_usd':STAGE_START,
        'new_allocation_usd':0,'max_pair_usd':.08,'pricing':{'source':url,'chat':chat,'embedding':embed},
        'model':'gpt-4.1-mini','max_output_tokens':1600,'limits':{'max_calls':8,'max_turn_usd':.04,'deadline_seconds':180,'repairs':1},
        'stop_codes':sorted(STOP),'stop_immediately_on_failure':True,'no_retry':True,'no_post_test_tuning':True,
        'human_labels_before_inference':False,'rubric_before_inference':True,'authorization':'درخواست همین دور در باقی‌ماندهٔ مرحلهٔ موجود'}
    write(FOLDER/'comparison_plan.json',plan);stop=None
    try:
        for v in plan['order']:
            assert frozen()==plan['files'],'Frozen files changed'
            print('اجرا: GH17011 / '+v,flush=True)
            proc=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--worker',v],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            path=FOLDER/'turns'/('GH17011_'+v+'.json')
            if not path.exists():write(path,{'id':'GH17011','variant':v,'output':None,'failure':'worker_failed','usage':[],'provider_outcome_unknown':True})
            row=read(path);code=row.get('failure') or (row.get('output') or {}).get('validation_error')
            if proc.returncode or row.get('failure') or code in STOP:stop=code or 'worker_failed';break
            summarize(plan,stop)
    except KeyboardInterrupt:stop='interrupted_without_retry'
    finally:
        env.pop('METIS_API_KEY',None);m=summarize(plan,stop)
        print(json.dumps({k:m[k] for k in ('complete','stop_reason','paired_cases','new_requests','new_charged_or_reserved_usd','frozen_unchanged')},ensure_ascii=False),flush=True)
if __name__=='__main__':
    if not __debug__:raise SystemExit('توقف: اجرای بدون کنترل مجاز نیست.')
    main()
