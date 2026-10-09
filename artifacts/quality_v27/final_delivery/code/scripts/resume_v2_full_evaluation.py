"""Continue ONLY unprocessed cases with the original immutable runtime configuration.

The delivered provider-error fallback remains in the comparison; it is NOT retried.
Original manifest and failed-request reservation are retained. No prompt/data edits.
"""
import getpass,hashlib,json,os,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.model import make_client
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.hybrid import HybridRetriever
from run_v2_full_evaluation import hashes, aggregate, scenario_run, VARIANTS

def main():
    folder=ROOT/'artifacts/architecture_v2/final_evaluation'; prior=read_json(folder/'manifest.json'); plan=read_json(folder/'evaluation_plan.json')
    require(not prior['complete'] and not (folder/'continuation_plan.json').exists(),'evaluation_exists','ادامهٔ این اجرا قبلاً ثبت شده یا اجرا کامل است.')
    frozen=plan['configuration']['files']; require(hashes()==frozen,'configuration_changed','کد یا دادهٔ اصلی تغییر کرده است.')
    config=plan['configuration']; prices=read_json(ROOT/'artifacts/architecture_v2/final_pricing_snapshot.json')
    embed=next(x for x in prices['models'] if x['model']=='text-embedding-3-small')
    os.environ.update(METIS_BASE_URL='https://api.metisai.ir/openai/v1',METIS_MODEL=config['model'],METIS_EMBEDDING_MODEL=embed['model'],
        CASEPILOT_INPUT_USD_PER_MILLION=str(config['input_rate']),CASEPILOT_OUTPUT_USD_PER_MILLION=str(config['output_rate']),
        CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['inputTokenUnitIncome']*1e6),CASEPILOT_MAX_OUTPUT_TOKENS=str(config['max_output_tokens']),
        CASEPILOT_BUDGET_USD=str(prior['cumulative_cap_usd']),CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'))
    os.environ['METIS_API_KEY']=os.getenv('METIS_API_KEY') or getpass.getpass('Metis API key (hidden): ')
    client=make_client('live'); hybrid=HybridRetriever(client)
    rows=[json.loads(x) for x in (folder/'answers.jsonl').read_text(encoding='utf-8').splitlines() if x]
    done={(r['split'],r['variant'],r['id']) for r in rows}; scenarios=read_json(folder/'multi_turn_results.json'); traces=read_json(folder/'traces.json')
    cases=read_json(ROOT/'eval/v2_final_cases.json'); plans=read_json(ROOT/'eval/v2_final_scenarios.json')
    shutil.copy2(folder/'manifest.json',folder/'interrupted_manifest.json')
    helper_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    shutil.copy2(__file__,folder/'frozen/scripts/resume_v2_full_evaluation.py')
    write_json(folder/'continuation_plan.json',{'at':utcnow(),'original_configuration_hash':plan['configuration_hash'],
        'helper_sha256':helper_hash,'outputs_already_done':len(rows),'not_retried':[r['id'] for r in rows if r['output']['validation_error']=='provider_error'],
        'policy':'Continue unprocessed cases only; original runtime/labels/limits unchanged. Keep failed delivered answers and uncertain costs.'})
    error=None
    def log(record): print(canonical(record),flush=True)
    def checkpoint():
        (folder/'answers.jsonl').write_text(''.join(canonical(r)+'\n' for r in rows),encoding='utf-8')
        write_json(folder/'multi_turn_results.json',scenarios); write_json(folder/'traces.json',traces)
        write_json(folder/'progress.json',{'at':utcnow(),'outputs':len(rows),'scenarios':len(scenarios),'error':error,'configuration_hash':plan['configuration_hash']})
    try:
        for split in ('dev','test_fresh'):
            for variant,components in VARIANTS.items():
                store=Store(ROOT/'runtime/final_evaluation'/(split+'_'+variant+'.sqlite3')); agent=Agent(store,client=client,hybrid=hybrid,components=components)
                for case in (c for c in cases if c['split']==split):
                    if (split,variant,case['id']) in done: continue
                    require(hashes()==frozen,'configuration_changed','پیکربندی تغییر کرده است.')
                    log({'event':'case_start','case':case['id'],'split':split,'variant':variant})
                    out=agent.turn(case['id'],case['initial_message'],'final-eval-'+variant,case['initial_facts'],case['initial_checks'])
                    relevant=set(case['relevant_source_ids']); got={r['source_id'] for r in out['retrieved']}
                    rows.append({'id':case['id'],'split':split,'variant':variant,'category':case['category'],
                        'source_recall_at_5':len(relevant&got)/len(relevant) if relevant else None,'decision_in_allowed_set':out['decision'] in case['allowed_decisions'],'output':out})
                    traces[split+'_'+variant]=store.traces(); checkpoint()
                    log({'event':'case_done','case':case['id'],'variant':variant,'decision':out['decision'],'validation_error':out['validation_error']})
                    if out['validation_error'] in ('budget_exhausted','embedding_index_not_ready'): raise CasePilotError(out['validation_error'],'اجرای باقی‌مانده ممکن نیست.')
        by_id={c['id']:c for c in cases}; completed={s['id'] for s in scenarios}
        for scenario in plans:
            if scenario['id'] in completed: continue
            require(hashes()==frozen,'configuration_changed','پیکربندی تغییر کرده است.')
            result=scenario_run(scenario,by_id,client,hybrid,ROOT/'runtime/final_evaluation'/(scenario['id']+'.sqlite3'),log)
            scenarios.append(result); checkpoint()
            if result.get('error') in ('budget_exhausted','embedding_index_not_ready'): raise CasePilotError(result['error'],'سقف اجرا رسید.')
    except Exception as exc:
        error=exc.code if isinstance(exc,CasePilotError) else type(exc).__name__; log({'event':'stopped','error':error})
    finally:
        os.environ.pop('METIS_API_KEY',None); client.key=''
        after=client.budget.report(); before=plan['cost_before']; complete=len(rows)==60 and len(scenarios)==10 and error is None
        prior.update(finished_at=utcnow(),complete=complete,error=error,configuration_unchanged=hashes()==frozen,
            comparison_outputs=len(rows),metrics=aggregate(rows),scenarios={'n':len(scenarios),'passed':sum(s['passed'] for s in scenarios)},
            new_requests=after['requests']-before['requests'],new_confirmed_usd=after['confirmed_usd']-before['confirmed_usd'],
            new_charged_or_reserved_usd=after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],cost_cumulative=after,
            fresh_final_holdout_evaluation=complete,transport_interruption_preserved=True,
            provider_error_outputs=[{'case':r['id'],'variant':r['variant']} for r in rows if r['output']['validation_error']=='provider_error'],
            continuation_helper_sha256=helper_hash)
        prior['limitations'].append('One delivered transport-error fallback retained without retry; unknown request reservation is not treated as zero. Continuation ran only unprocessed cases with the original frozen runtime configuration.')
        checkpoint(); write_json(folder/'manifest.json',prior)
        log({'event':'finished','complete':complete,'outputs':len(rows),'scenarios':prior['scenarios'],
            'new_charged_or_reserved_usd':prior['new_charged_or_reserved_usd'],'total_charged_or_reserved_usd':after['charged_or_reserved_usd']})
    return prior['complete']
if __name__=='__main__': sys.exit(0 if main() else 1)
