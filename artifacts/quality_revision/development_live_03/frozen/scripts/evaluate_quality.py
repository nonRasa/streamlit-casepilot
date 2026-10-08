"""Capped quality campaign, paired fresh holdout and isolated old/new runtimes.

No changes after final freeze. Old runtime imports its preserved source, sharing
only the unchanged corpus, embedding cache and persistent team budget. Secrets
stay in process memory/environment. No public effects, no automatic API retry.
"""
import argparse,getpass,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'artifacts/architecture_v2/final_evaluation/frozen'

def install(previous=False):
    sys.path.insert(0,str((OLD if previous else ROOT)/'src'))
    import casepilot.common as common
    common.ROOT=ROOT
    return common

def frozen_files(final=False):
    files=list((ROOT/'src/casepilot').glob('*.py'))+list((ROOT/'schemas').glob('*.json'))+list((ROOT/'policies').glob('*.json'))
    files += [ROOT/'data/corpus_v2.json',ROOT/'data/index_v2_manifest.json',ROOT/'scripts/evaluate_quality.py']
    if final: files += [ROOT/'eval/quality_cases.json',ROOT/'eval/quality_scenarios.json',ROOT/'eval/quality_selection_manifest.json']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

def worker(settings_path,variant):
    common=install(variant=='previous')
    from casepilot.agent import Agent
    from casepilot.store import Store
    from casepilot.model import make_client
    from casepilot.hybrid import HybridRetriever
    common.ROOT=ROOT
    cfg=common.read_json(settings_path); folder=ROOT/cfg['folder']; cases=cfg['cases']
    client=make_client(cfg['mode'])
    if cfg['mode']=='live': client.budget.cap=cfg['cumulative_cap_usd']
    hybrid=HybridRetriever(client); store=Store(ROOT/'runtime'/folder.name/(variant+'.sqlite3'))
    import casepilot.pipeline as runtime_pipeline
    common.write_json(folder/(variant+'_runtime_provenance.json'),{'pipeline_path':str(Path(runtime_pipeline.__file__).resolve()),
        'pipeline_sha256':hashlib.sha256(Path(runtime_pipeline.__file__).read_bytes()).hexdigest(),'common_root':str(common.ROOT)})
    agent=Agent(store,client=client,hybrid=hybrid); rows=[]; scenarios=[]
    def log(x): print(common.canonical(x),flush=True)
    try:
        for case in cases:
            if frozen_files(cfg['phase']=='final')!=cfg['files']: raise RuntimeError('Configuration changed during evaluation')
            log({'event':'start','variant':variant,'case':case['id']})
            try:
                out=agent.turn(case['id'],case['initial_message'],'quality-'+variant,case.get('initial_facts',{}),case.get('initial_checks',[]))
                failure=None
            except common.CasePilotError as exc: out=None; failure=exc.code
            rows.append({'id':case['id'],'split':case['split'],'variant':variant,'output':out,'failure':failure})
            common.write_json(folder/(variant+'_answers.json'),rows)
            log({'event':'done','variant':variant,'case':case['id'],'error':failure or out['validation_error'],
                'decision':out['decision'] if out else None})
            if (failure or (out or {}).get('validation_error'))=='budget_exhausted':
                break
        if variant=='revised' and cfg['phase']=='final' and len(rows)==len(cases):
            # Existing scenario engine is operational only; approvals are scripted.
            sys.path.insert(0,str(ROOT/'scripts'))
            from run_v2_full_evaluation import scenario_run
            for plan in common.read_json(ROOT/'eval/quality_scenarios.json'):
                if frozen_files(True)!=cfg['files']: raise RuntimeError('Configuration changed')
                result=scenario_run(plan,{c['id']:c for c in cases},client,hybrid,ROOT/'runtime'/folder.name/(plan['id']+'.sqlite3'),log)
                scenarios.append(result); common.write_json(folder/'multi_turn_results.json',scenarios)
                if result.get('error') in ('budget_exhausted','turn_budget_exhausted'): break
    finally:
        common.write_json(folder/(variant+'_answers.json'),rows)
        common.write_json(folder/(variant+'_traces.json'),store.traces())
    return 0

def main():
    p=argparse.ArgumentParser(); p.add_argument('--worker',choices=['previous','revised']); p.add_argument('--settings')
    p.add_argument('--mode',choices=['replay','live'],default='replay'); p.add_argument('--phase',choices=['development','final'],default='development')
    p.add_argument('--label',default='development_preflight'); p.add_argument('--additional-cap-usd',type=float,default=.06)
    a=p.parse_args()
    if a.worker: return worker(a.settings,a.worker)
    c=install(); c.identifier(a.label); c.require(0<a.additional_cap_usd<=.65,'invalid_budget','سقف اضافه حداکثر شصت‌وپنج سنت است.')
    folder=ROOT/'artifacts/quality_revision'/a.label
    c.require(not folder.exists(),'evaluation_exists','نتیجهٔ موجود بازنویسی نمی‌شود.')
    if a.phase=='final': cases=c.read_json(ROOT/'eval/quality_cases.json')
    else:
        wanted={'GH9218','GH11528','GH12607','GH14593','GH14710'}
        cases=[dict(x,split='dev') for x in c.read_json(ROOT/'eval/v2_final_cases.json') if x['id'] in wanted]
    if a.mode=='live':
        url='https://api.metisai.ir/api/v1/meta/providers/pricing'
        with urlopen(url,timeout=20) as response: prices=json.load(response)
        chat=next(x for x in prices['llm'] if x['model']=='gpt-4.1-mini'); embed=next(x for x in prices['embedding'] if x['model']=='text-embedding-3-small')
        c.require(all(x['currency']=='USD' and x['fixedCallIncome']==0 for x in (chat,embed)),'invalid_prices','تعرفه سازگار نیست.')
        os.environ.update(METIS_BASE_URL='https://api.metisai.ir/openai/v1',METIS_MODEL='gpt-4.1-mini',METIS_EMBEDDING_MODEL='text-embedding-3-small',
            CASEPILOT_INPUT_USD_PER_MILLION=str(chat['inputTokenUnitIncome']*1e6),CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['outputTokenUnitIncome']*1e6),
            CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['inputTokenUnitIncome']*1e6),CASEPILOT_MAX_OUTPUT_TOKENS='1600',
            CASEPILOT_BUDGET_USD='5',CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'))
        os.environ['METIS_API_KEY']=os.getenv('METIS_API_KEY') or getpass.getpass('Metis API key (hidden): ')
    else: chat=embed=None
    from casepilot.accounting import Budget
    before=Budget(ROOT/'runtime/team_budget.sqlite3').report() if a.mode=='live' else {'requests':0,'confirmed_usd':0,'charged_or_reserved_usd':0,'calls':[]}
    campaign_path=ROOT/'artifacts/quality_revision/campaign.json'
    if a.mode=='live':
        if not campaign_path.exists(): c.write_json(campaign_path,{'at':c.utcnow(),'cost_before':before,'additional_cap_usd':.65,'cumulative_cap_usd':min(5,before['charged_or_reserved_usd']+.65)})
        campaign=c.read_json(campaign_path); cap=min(campaign['cumulative_cap_usd'],before['charged_or_reserved_usd']+a.additional_cap_usd)
    else: cap=0
    frozen=frozen_files(a.phase=='final'); folder.mkdir(parents=True)
    for name in frozen:
        dest=folder/'frozen'/name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/name,dest)
    # Explicitly preserve the old implementation; never import updated modules as old.
    if a.phase=='final':
        old_manifest=c.read_json(OLD.parent/'manifest.json')
        c.require(all(hashlib.sha256((OLD/name).read_bytes()).hexdigest()==sha for name,sha in old_manifest['configuration']['files'].items()),'old_snapshot_changed','نسخهٔ قبلی تغییر کرده است.')
    settings={'folder':folder.relative_to(ROOT).as_posix(),'phase':a.phase,'mode':a.mode,'cases':cases,'files':frozen,
        'cumulative_cap_usd':cap,'cost_before':before,'prices':{'chat':chat,'embedding':embed},'at':c.utcnow(),
        'protocol':'Final settings frozen before inference. Previous old source in isolated child process, unchanged corpus/cache/ledger. Fifteen paired fresh test reports. Development previous outputs reused without a paid retry. Synthetic operational approvals only. No post-test tuning. Separate AI review after execution.'}
    c.write_json(folder/'plan.json',settings); settings_path=folder/'plan.json'
    variants=['revised'] if a.phase=='development' else ['previous','revised']; error=None
    try:
        for variant in variants:
            wc=dict(settings)
            if variant=='previous': wc['cases']=[x for x in cases if x['split']=='test_fresh']
            worker_path=folder/(variant+'_plan.json'); c.write_json(worker_path,wc)
            proc=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--worker',variant,'--settings',str(worker_path)],cwd=ROOT,env=os.environ.copy())
            if proc.returncode: error='worker_failed'; break
    finally:
        os.environ.pop('METIS_API_KEY',None)
        after=Budget(ROOT/'runtime/team_budget.sqlite3').report() if a.mode=='live' else before
        rows=[]
        for variant in variants:
            path=folder/(variant+'_answers.json')
            if path.exists(): rows+=c.read_json(path)
        if a.phase=='final':
            oldrows=[json.loads(x) for x in (OLD.parent/'answers.jsonl').read_text(encoding='utf-8').splitlines() if x]
            rows += [dict(id=r['id'],split='dev',variant='previous',output=r['output'],failure=None,historical_reuse=True) for r in oldrows if r['split']=='dev' and r['variant']=='full']
        scenarios=c.read_json(folder/'multi_turn_results.json') if (folder/'multi_turn_results.json').exists() else []
        c.write_json(folder/'answers.json',rows)
        manifest={'at':c.utcnow(),'phase':a.phase,'mode':a.mode,'error':error,'configuration_hash':c.digest(frozen),
            'configuration_unchanged':frozen_files(a.phase=='final')==frozen,'attempted_comparisons':len(rows),'delivered_comparisons':sum(bool(r['output']) for r in rows),
            'complete':not error and len(rows)==(60 if a.phase=='final' else 5) and (a.phase!='final' or len(scenarios)==10),
            'scenarios':{'n':len(scenarios),'passed':sum(x['passed'] for x in scenarios)},
            'new_requests':after['requests']-before['requests'],'new_confirmed_usd':after['confirmed_usd']-before['confirmed_usd'],
            'new_charged_or_reserved_usd':after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],'cost_cumulative':after,
            'limitations':['AI-assisted labels/review are not independent humans. Public initial reports only, current corpus not historical replay.',
                'Fresh reports may be in model pretraining. Explicit families screened; unknown related issues remain possible.',
                'Previous development outputs reused from earlier execution with max output 1000, revised 1600. Fresh paired versions both 1600; old judge still internally capped at 800.',
                'Provider errors/fallbacks retained, no failed request retried. Completed processing does not mean all scenarios succeeded.']}
        c.write_json(folder/'manifest.json',manifest)
        print(c.canonical({k:v for k,v in manifest.items() if k not in ('cost_cumulative','limitations')}),flush=True)
    return 0 if manifest['complete'] else 1

if __name__=='__main__': sys.exit(main())
