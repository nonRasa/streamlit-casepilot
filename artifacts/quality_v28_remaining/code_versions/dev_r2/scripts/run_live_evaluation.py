"""Bounded complete evaluation, hidden credential, frozen configuration, no retries."""
import getpass,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.model import MetisClient
import evaluate

def fingerprints():
    paths=list((ROOT/'src/casepilot').glob('*.py'))+[ROOT/name for name in
          ('scripts/evaluate.py','scripts/run_live_evaluation.py','data/corpus.json','eval/cases.json','eval/scenarios.json','schemas/answer.schema.json','schemas/model_selection.schema.json')]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

def main():
    # Explicit constants for this run, shared across both methods/splits.
    os.environ.update(CASEPILOT_BUDGET_USD='0.50',CASEPILOT_MAX_OUTPUT_TOKENS='1000',
        METIS_MODEL='gpt-4.1-mini',METIS_BASE_URL='https://api.metisai.ir/openai/v1',
        CASEPILOT_INPUT_USD_PER_MILLION='0.44',CASEPILOT_OUTPUT_USD_PER_MILLION='1.76',
        CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'))
    overview=ROOT/'artifacts/live/full_evaluation.json'
    require(not overview.exists(),'evaluation_exists','نتیجهٔ اجرای قبلی حفظ شد؛ اجرای دوباره خودکار نیست.')
    for split in ('dev','test'):
        folder=ROOT/'artifacts/live'/split
        require(not (folder/'progress.json').exists() and not (folder/'evaluation_metrics.json').exists(),
                'evaluation_exists','خروجی قبلی موجود است؛ اجرا متوقف شد تا هزینه تکرار نشود.')
    frozen=fingerprints(); started=utcnow(); runs=[]; error=None
    key=getpass.getpass('Metis API key (hidden): '); os.environ['METIS_API_KEY']=key
    client=MetisClient(); before=client.budget.report(); invocations=0
    original_generate=client.generate
    def generate(state,evidence,method='final'):
        nonlocal invocations
        require(fingerprints()==frozen,'provider_error','کد یا دادهٔ اجرای قفل‌شده تغییر کرده است؛ اجرا متوقف شد.')
        require(invocations<83,'budget_exhausted','سقف تعداد فراخوانی این ارزیابی رسیده است.')
        invocations+=1; tick=time.perf_counter()
        print(canonical({'event':'model_start','invocation':invocations,'method':method}),flush=True)
        try: return original_generate(state,evidence,method)
        finally:
            print(canonical({'event':'model_end','invocation':invocations,'seconds':round(time.perf_counter()-tick,2),
                  'usage':client.last_usage,'cumulative_usd':client.budget.report()['charged_or_reserved_usd']}),flush=True)
    client.generate=generate
    evaluate.make_client=lambda mode: client
    plan_path=ROOT/'artifacts/live/evaluation_plan.json'
    plan=read_json(plan_path)
    plan.update(started_at=started,frozen_files=frozen,cost_before=before)
    write_json(plan_path,plan)
    try:
        for split in ('dev','test'):
            require(fingerprints()==frozen,'provider_error','پیکربندی تغییر کرده است.')
            print(canonical({'event':'split_start','split':split}),flush=True)
            # No tuning after development: test runs the same immutable configuration.
            result=evaluate.run(split,mode='live',with_scenarios=True)
            runs.append({'split':split,'complete':result['complete'],'configuration_hash':result['configuration_hash'],
                         'comparison_turns':sum(m['n'] for m in result['metrics'].values()),
                         'scenarios':result['scenarios'],'run_provider_requests':result['run_provider_requests'],
                         'run_confirmed_usd':result['run_confirmed_usd']})
            if not result['complete']: error=result['stopped_reason'] or 'incomplete'; break
    except Exception as exc:
        error=exc.code if isinstance(exc,CasePilotError) else type(exc).__name__
        print(canonical({'event':'stopped','error':error}),flush=True)
    finally:
        os.environ.pop('METIS_API_KEY',None); client.key=''; key=''
    cost=client.budget.report()
    complete=error is None and len(runs)==2 and all(r['complete'] and r['comparison_turns']==30 and r['scenarios']=={'n':5,'passed':5} for r in runs) and len({r['configuration_hash'] for r in runs})==1
    summary={'started_at':started,'finished_at':utcnow(),'complete':complete,'error':error,'runs':runs,
             'model_invocations':invocations,'new_provider_requests':cost['requests']-before['requests'],
             'new_confirmed_usd':cost['confirmed_usd']-before['confirmed_usd'],'cost_cumulative':cost,
             'request_limit':83,'cumulative_cap_usd':.50,'configuration_unchanged':fingerprints()==frozen,
             'limitations':['Operational scenario reviewer is scripted, not an independent human.','Synthetic follow-up turns are supplied sequentially, not historical user conversations.','Extractive quotes do not establish semantic correctness of free-text advice.','Token cost is calculated, not a verified account balance.']}
    write_json(overview,summary)
    write_json(ROOT/'artifacts/live_run_manifest.json',{'status':'complete' if complete else 'partial',
        'full_evaluation_complete':complete,'latest_run':'artifacts/live/full_evaluation.json',
        'provider_requests_cumulative':cost['requests'],'cost_usd_cumulative':cost['confirmed_usd'],
        'reason':error,'n8n_status':'Not verified on user instance.','human_review_status':'Pending independent review.'})
    print(canonical({'event':'finished','complete':complete,'new_requests':summary['new_provider_requests'],
                    'new_cost_usd':summary['new_confirmed_usd'],'total_cost_usd':cost['confirmed_usd']}),flush=True)
    return complete

if __name__=='__main__': sys.exit(0 if main() else 1)
