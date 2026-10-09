"""Attempt only never-started operational scenarios with the unchanged campaign cap.

Original stopped manifest and scenario results remain byte-for-byte intact.
No comparison or failed scenario is rerun. Completion records are separate.
"""
import getpass,hashlib,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.accounting import Budget
from evaluate_quality import frozen_files

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation';plan=read_json(folder/'plan.json')
    require(not (folder/'completion_manifest.json').exists(),'exists','تکمیل موجود بازنویسی نمی‌شود.')
    require(frozen_files(True)==plan['files'],'changed','کد یا ورودی تغییر کرده است.')
    original=read_json(folder/'manifest.json');prior=read_json(folder/'multi_turn_results.json')
    missing=[x for x in read_json(ROOT/'eval/quality_scenarios.json') if x['id'] not in {s['id'] for s in prior}]
    require(len(missing)==1 and missing[0]['id']=='QS10','unexpected_scope','فقط سناریوی هرگز آغازنشده اجرا می‌شود.')
    campaign=read_json(ROOT/'artifacts/quality_revision/campaign.json');before=Budget(ROOT/'runtime/team_budget.sqlite3').report()
    cap=min(campaign['cumulative_cap_usd'],before['charged_or_reserved_usd']+.0196)
    prices=plan['prices'];chat=prices['chat'];embed=prices['embedding']
    os.environ.update(METIS_BASE_URL='https://api.metisai.ir/openai/v1',METIS_MODEL='gpt-4.1-mini',METIS_EMBEDDING_MODEL='text-embedding-3-small',
        CASEPILOT_INPUT_USD_PER_MILLION=str(chat['inputTokenUnitIncome']*1e6),CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['outputTokenUnitIncome']*1e6),
        CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['inputTokenUnitIncome']*1e6),CASEPILOT_MAX_OUTPUT_TOKENS='1600',
        CASEPILOT_BUDGET_USD='5',CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'))
    os.environ['METIS_API_KEY']=getpass.getpass('Metis API key (hidden): ')
    from casepilot.model import make_client
    from casepilot.hybrid import HybridRetriever
    from run_v2_full_evaluation import scenario_run
    results=[]
    try:
        client=make_client('live');client.budget.cap=cap;hybrid=HybridRetriever(client)
        for item in missing:
            require(frozen_files(True)==plan['files'],'changed','پیکربندی تغییر کرده است.')
            results.append(scenario_run(item,{x['id']:x for x in plan['cases']},client,hybrid,
                ROOT/'runtime/quality_missing_scenario'/(item['id']+'.sqlite3'),lambda x:print(canonical(x),flush=True)))
    finally:os.environ.pop('METIS_API_KEY',None)
    after=Budget(ROOT/'runtime/team_budget.sqlite3').report()
    write_json(folder/'missing_operational_results.json',results)
    write_json(folder/'completed_multi_turn_results.json',prior+results)
    m=dict(original);m.update(at=utcnow(),complete=len(prior+results)==10 and len(read_json(folder/'answers.json'))==40,
        configuration_unchanged=frozen_files(True)==plan['files'],scenarios={'n':len(prior+results),'passed':sum(s['passed'] for s in prior+results)},
        new_requests=after['requests']-plan['cost_before']['requests'],new_confirmed_usd=after['confirmed_usd']-plan['cost_before']['confirmed_usd'],
        new_charged_or_reserved_usd=after['charged_or_reserved_usd']-plan['cost_before']['charged_or_reserved_usd'],cost_cumulative=after,
        completion_cumulative_cap_usd=cap,
        completion_provenance={'original_complete':original['complete'],'only_previously_unstarted_scenarios':[x['id'] for x in missing],
            'cost_before_completion':before,'source_sha256':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in
                ('manifest.json','multi_turn_results.json','missing_operational_results.json','completed_multi_turn_results.json')}})
    m['limitations']=list(m['limitations'])+['Original run stopped on the temporary budget in QS09. Only previously unstarted QS10 attempted with remaining campaign funds; failed QS09/comparisons never rerun. Complete means all plans attempted, not all succeeded. Planned scenario initial turns may repeat uncached failed provider calls.']
    write_json(folder/'completion_manifest.json',m)
    print(canonical({k:m[k] for k in ('complete','configuration_unchanged','scenarios','new_charged_or_reserved_usd')}),flush=True)

if __name__=='__main__':main()
