"""Explicitly authorized embedding build only. Default is a zero-cost plan."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest,require
from casepilot.hybrid import HybridRetriever,embedding_text
from casepilot.model import ReplayClient,MetisClient
from evaluate_quality_v27_live import configure,credentials
from evaluate_quality_v25_live import ledger

def main():
    p=argparse.ArgumentParser();p.add_argument('--approved-cap-usd',type=float);args=p.parse_args()
    corpus=ROOT/'data/corpus_v3.json';manifest=read_json(corpus.with_suffix('.manifest.json'));rows=read_json(corpus)
    require(digest(rows)==manifest['corpus_hash'],'index_manifest_mismatch','هش ایندکس با صورت ساخت برابر نیست.')
    rate=next(p for p in read_json(ROOT/'artifacts/quality_v27/pricing.json')['models'] if p['model']=='text-embedding-3-small')['inputTokenUnitIncome']
    estimate=manifest['embedding_input_tokens_cl100k_base']*rate
    plan={'model':'text-embedding-3-small','texts':len(rows),'input_tokens':manifest['embedding_input_tokens_cl100k_base'],
          'estimated_cost_usd':estimate,'suggested_hard_cap_usd':.05,'corpus_hash':manifest['corpus_hash'],
          'provider_requests':0,'authorized':args.approved_cap_usd is not None}
    if args.approved_cap_usd is None:print(json.dumps(plan));return
    require(0<args.approved_cap_usd<=.05,'invalid_budget','سقف تأییدشدهٔ مستقل ساخت ایندکس باید حداکثر پنج سنت باشد.')
    target=ROOT/'artifacts/quality_v27/embedding_build_live.json'
    require(not target.exists(),'evaluation_exists','ساخت ثبت‌شده تکرار نمی‌شود.')
    before=ledger();configure(min(5,before['charged_or_reserved_usd']+args.approved_cap_usd));credentials()
    client=MetisClient();h=HybridRetriever(client,path=corpus);error=None
    try:
        h.cache.get_many([embedding_text(r) for r in h.chunks],allow_create=True)
    except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
    finally:
        after=ledger();client.key=''
        write_json(target,dict(plan,complete=error is None,error=error,
            confirmed_usd=after['confirmed_usd']-before['confirmed_usd'],
            charged_or_reserved_usd=after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],
            provider_requests=after['requests']-before['requests'],namespace=h.index_namespace))
    if error:raise SystemExit(error)
    print('Authorized index build complete; answer quality has not been verified.')

if __name__=='__main__':main()
