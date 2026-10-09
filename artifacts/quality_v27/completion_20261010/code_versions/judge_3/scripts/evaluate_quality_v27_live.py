"""Authorized S0/S1-only smoke; no index build, no retry, no automatic tracker writes."""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/quality_v27'; RUN=BASE/'contract_live_01'
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_quality_v25_live import ledger,write,read,sha

def credentials():
    if os.getenv('METIS_API_KEY'): return
    local=ROOT/'.env'
    if local.exists():
        for line in local.read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith('METIS_API_KEY='):
                value=line.split('=',1)[1].strip().strip('"').strip("'")
                if value: os.environ['METIS_API_KEY']=value
    if not os.getenv('METIS_API_KEY') and os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
                value,_=winreg.QueryValueEx(key,'METIS_API_KEY')
                if value: os.environ['METIS_API_KEY']=value
        except OSError: pass
    if not os.getenv('METIS_API_KEY'): raise SystemExit('missing_secure_credential; provider_requests=0')

def configure(cap):
    prices=read(BASE/'pricing.json')['models']; by={p['model']:p for p in prices}
    chat=by['gpt-4.1-mini']; embed=by['text-embedding-3-small']
    assert all(p['currency']=='USD' and p['fixedCallIncome']==0 for p in (chat,embed))
    os.environ.update(METIS_MODEL=chat['model'],METIS_JUDGE_MODEL=chat['model'],METIS_EMBEDDING_MODEL=embed['model'],
        METIS_BASE_URL='https://api.metisai.ir/openai/v1',CASEPILOT_INPUT_USD_PER_MILLION=str(chat['inputTokenUnitIncome']*1e6),
        CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['outputTokenUnitIncome']*1e6),CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['inputTokenUnitIncome']*1e6),
        CASEPILOT_MAX_OUTPUT_TOKENS='1600',CASEPILOT_BUDGET_USD=str(cap),CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'))

def verify_frozen():
    for stage in ('S0','S1'):
        manifest=read(BASE/stage/'manifest.json')
        for name,value in manifest['files'].items():
            if sha(BASE/stage/'code'/name)!=value: raise SystemExit('frozen_stage_changed: '+stage)

def prepare():
    RUN.mkdir(parents=True,exist_ok=True)
    path=RUN/'authorization.json'
    if path.exists(): return read(path)
    before=ledger(); cases=read(ROOT/'artifacts/quality_v22/holdout/cases.json')
    chosen=[]
    for cid in ('GH17011','GH16481'):
        row=next(c for c in cases if c['id']==cid)
        chosen.append({k:row[k] for k in ('id','initial_message','initial_facts','initial_checks')})
    plan={'purpose':'Only readable judge contract: S0 versus S1; development-seen bug and feature',
          'authorization':'Explicit human approval in this chat on 2026-10-09; fresh additional cap $0.16',
          'additional_cap_usd':.16,'per_turn_cap_usd':.04,'max_total_calls':32,'max_output_tokens':1600,
          'model':'gpt-4.1-mini','embedding_model':'text-embedding-3-small',
          'cumulative_cap_usd':min(5,before['charged_or_reserved_usd']+.16),'cost_before':before,
          'order':[[cid,stage] for cid in ('GH17011','GH16481') for stage in ('S0','S1')],
          'cases':chosen,'corpus':'data/corpus_v2.json','corpus_sha256':sha(ROOT/'data/corpus_v2.json'),
          'stage_manifest_hashes':{s:sha(BASE/s/'manifest.json') for s in ('S0','S1')},
          'pricing_sha256':sha(BASE/'pricing.json'),'index_build_authorized':False,'stop_on_first_internal_failure':True,
          'automatic_retry':False,'human_review_completed':False,'independent_review_completed':False}
    write(path,plan); return plan

def load_stage(stage):
    source=BASE/stage/'code/src'; sys.path.insert(0,str(source))
    import casepilot.common as common
    common.ROOT=ROOT
    from casepilot.model import MetisClient
    from casepilot.hybrid import HybridRetriever
    return MetisClient,HybridRetriever

def worker(cid,stage):
    plan=read(RUN/'authorization.json'); verify_frozen()
    assert sha(ROOT/plan['corpus'])==plan['corpus_sha256']
    configure(plan['cumulative_cap_usd']); credentials()
    Client,Hybrid=load_stage(stage); client=Client()
    runtime=ROOT/'runtime/quality_v27/contract_live_01'/stage
    client.cache=runtime/'response_cache'; client.cache.mkdir(parents=True,exist_ok=True)
    client.diagnostics=runtime/'diagnostics'
    from casepilot.store import Store
    from casepilot.agent import Agent
    hybrid=Hybrid(client,path=ROOT/plan['corpus'])
    hybrid.load_vectors() # allow_create=False: cache gaps stop before any paid call
    output=None; failure=None; start=time.perf_counter()
    case=next(c for c in plan['cases'] if c['id']==cid)
    marker=RUN/'started'/(cid+'_'+stage+'.json'); result=RUN/'turns'/(cid+'_'+stage+'.json')
    assert not marker.exists() and not result.exists(),'No retry'
    write(marker,{'at':time.time(),'case':cid,'stage':stage})
    store=Store(runtime/(cid+'.sqlite3'))
    try:
        output=Agent(store,client=client,hybrid=hybrid).turn(cid,case['initial_message'],'v27-contract-'+stage,case['initial_facts'],case['initial_checks'])
    except Exception as exc: failure=getattr(exc,'code',type(exc).__name__)
    finally:
        write(result,{'id':cid,'stage':stage,'output':output,'failure':failure,'usage':client.usage_history,
                      'elapsed_seconds':time.perf_counter()-start})
        write(RUN/'traces'/(cid+'_'+stage+'.json'),store.traces())
        client.key=''; os.environ.pop('METIS_API_KEY',None)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--live',action='store_true'); p.add_argument('--worker',nargs=2)
    args=p.parse_args()
    if args.worker: worker(*args.worker); return
    plan=prepare(); verify_frozen(); configure(plan['cumulative_cap_usd']); credentials()
    Client,Hybrid=load_stage('S0'); client=Client(); h=Hybrid(client,path=ROOT/plan['corpus'])
    h.load_vectors(); client.key=''
    preflight={'provider_requests':0,'cached_index_ready':True,'secure_key_available':True,'frozen_stages_valid':True,
               'additional_cap_usd':.16,'index_build_authorized':False}
    write(RUN/'preflight.json',preflight)
    if not args.live: print(json.dumps(preflight)); return
    marker=RUN/'campaign_started.json'
    if marker.exists(): raise SystemExit('Campaign already started; automatic retry forbidden.')
    write(marker,{'at':time.time(),'authorization_sha256':sha(RUN/'authorization.json')})
    stop=None
    for cid,stage in plan['order']:
        assert sha(BASE/'pricing.json')==plan['pricing_sha256']
        print('Running authorized contract comparison: '+cid+' / '+stage,flush=True)
        proc=subprocess.run([sys.executable,'-X','utf8',__file__,'--worker',cid,stage],cwd=ROOT,env=os.environ.copy(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        file=RUN/'turns'/(cid+'_'+stage+'.json')
        if proc.returncode or not file.exists(): stop='worker_failed'; break
        result=read(file); out=result.get('output') or {}
        if result['failure'] or (out.get('validation_error') and out['validation_error'] not in ('judge_rejected','deterministic_review_failed','unsupported_answer')):
            stop=result['failure'] or out['validation_error']; break
    after=ledger(); before=plan['cost_before']; turns=[read(p) for p in sorted((RUN/'turns').glob('*.json'))]
    cost=after['charged_or_reserved_usd']-before['charged_or_reserved_usd']
    report={'turns_completed':len(turns),'planned_turns':4,'complete':len(turns)==4 and not stop,'stop_reason':stop,
            'confirmed_usd':after['confirmed_usd']-before['confirmed_usd'],
            'uncertain_reserved_usd':after['uncertain_reserved_usd']-before['uncertain_reserved_usd'],
            'charged_or_reserved_usd':cost,'hard_cap_usd':.16,'provider_requests':after['requests']-before['requests'],
            'model_calls':sum((r.get('output') or {}).get('model_calls',0) for r in turns),
            'index_rebuild_cost_usd':0,'human_review_completed':False,'independent_review_completed':False,
            'quality_success':False,'note':'Contract validity and content rejection are separate. No complete pair or human usefulness evidence means no improvement claim.'}
    write(RUN/'result.json',report)
    assert cost<=.16+1e-9 and report['provider_requests']<=32
    print(json.dumps(report,ensure_ascii=True))

if __name__=='__main__': main()
