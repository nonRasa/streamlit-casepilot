"""One explicit, tightly capped embedding build + development smoke, hidden key.

Uses the public Metis pricing endpoint to verify rates; never persists the key.
No retry, no test-set evaluation, no automatic tracker approval.
"""
import argparse, getpass, json, os, subprocess, sys
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.accounting import Budget
import evaluate_v2

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--label',default='smoke'); parser.add_argument('--skip-build',action='store_true'); parser.add_argument('--additional-cap-usd',type=float,default=.15); args=parser.parse_args()
    identifier(args.label); require(0<args.additional_cap_usd<=.15,'invalid_budget','سقف این نمونه حداکثر پانزده سنت است.')
    target=ROOT/'artifacts/architecture_v2/live'/(args.label+'_full')
    require(not (target/'manifest.json').exists() and not (target/'answers.jsonl').exists(),'evaluation_exists','آزمایش قبلی حفظ شد؛ اجرای دوباره خودکار نیست.')
    url='https://api.metisai.ir/api/v1/meta/providers/pricing'
    with urlopen(url,timeout=20) as response: prices=json.load(response)
    chat=next(x for x in prices['llm'] if x['model']=='gpt-4.1-mini')
    embedding=next(x for x in prices['embedding'] if x['model']=='text-embedding-3-small')
    require(all(x['currency']=='USD' and x['fixedCallIncome']==0 for x in (chat,embedding)),'invalid_prices','تعرفهٔ درگاه با حسابداری فعلی سازگار نیست.')
    snapshot={'at':utcnow(),'source':url,'page':'https://docs.metisai.ir/pricing/','models':[chat,embedding]}
    write_json(ROOT/'artifacts/architecture_v2/pricing_snapshot.json',snapshot)
    budget=Budget(ROOT/'runtime/team_budget.sqlite3'); before=budget.report(); cumulative=min(.50,before['charged_or_reserved_usd']+args.additional_cap_usd)
    os.environ.update(METIS_BASE_URL='https://api.metisai.ir/openai/v1',METIS_MODEL='gpt-4.1-mini',METIS_EMBEDDING_MODEL='text-embedding-3-small',
        CASEPILOT_INPUT_USD_PER_MILLION=str(chat['inputTokenUnitIncome']*1e6),CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['outputTokenUnitIncome']*1e6),
        CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embedding['inputTokenUnitIncome']*1e6),CASEPILOT_BUDGET_USD=str(cumulative),
        CASEPILOT_MAX_OUTPUT_TOKENS='1000',CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'))
    os.environ['METIS_API_KEY']=os.getenv('METIS_API_KEY') or getpass.getpass('Metis API key (hidden): ')
    try:
        if not args.skip_build:
            print(canonical({'event':'embedding_build_start','maximum_additional_total_usd':args.additional_cap_usd,'maximum_build_usd':min(.08,args.additional_cap_usd)}),flush=True)
            subprocess.run([sys.executable,'-X','utf8','scripts/build_index.py','--live','--additional-cap-usd',str(min(.08,args.additional_cap_usd))],cwd=ROOT,check=True)
        print(canonical({'event':'development_smoke_start','cases':2,'maximum_additional_smoke_usd':min(.07,args.additional_cap_usd)}),flush=True)
        result=evaluate_v2.run('live',2,'full',args.label,min(.07,args.additional_cap_usd))
        after=budget.report(); print(canonical({'event':'finished','complete':result['complete'],'new_charged_or_reserved_usd':after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],'total_charged_or_reserved_usd':after['charged_or_reserved_usd']}),flush=True)
        return result['complete']
    finally: os.environ.pop('METIS_API_KEY',None)

if __name__=='__main__': sys.exit(0 if main() else 1)
