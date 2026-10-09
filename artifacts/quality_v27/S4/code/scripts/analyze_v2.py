"""Source-level Recall/MRR/nDCG on saved development outputs; zero model calls."""
import json, math, statistics, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *

def source_metrics(retrieved,relevant):
    relevant=set(relevant)
    if not relevant: return {'recall_at_5':None,'mrr_at_5':None,'ndcg_at_5':None}
    seen=set(); gains=[]
    for row in retrieved[:5]:
        sid=row['source_id']; gains.append(int(sid in relevant and sid not in seen)); seen.add(sid)
    recall=sum(gains)/len(relevant)
    mrr=next((1/rank for rank,gain in enumerate(gains,1) if gain),0)
    dcg=sum(gain/math.log2(rank+1) for rank,gain in enumerate(gains,1))
    ideal=sum(1/math.log2(rank+1) for rank in range(1,min(5,len(relevant))+1))
    return {'recall_at_5':recall,'mrr_at_5':mrr,'ndcg_at_5':dcg/ideal}

def main():
    cases={c['id']:c for c in read_json(ROOT/'eval/cases.json')}; rows=[]
    paths=list((ROOT/'artifacts/architecture_v2/offline').glob('final_ablation_*/manifest.json'))
    paths+=list((ROOT/'artifacts/architecture_v2/live').glob('smoke_contract_full/manifest.json'))
    for path in sorted(paths):
        manifest=read_json(path); answers=[json.loads(line) for line in (path.parent/'answers.jsonl').read_text(encoding='utf-8').splitlines() if line]
        scores=[source_metrics(r['output']['retrieved'],cases[r['id']]['relevant_source_ids']) for r in answers]
        group={'run':path.parent.name,'mode':manifest['mode'],'variant':manifest['variant'],'case_ids':[r['id'] for r in answers],
               'configuration_hash':manifest['configuration_hash'],'model_invocations':sum(r['output']['model_calls'] for r in answers),
               'new_requests':manifest['new_requests'],'new_charged_or_reserved_usd':manifest['new_charged_or_reserved_usd']}
        for metric in ('recall_at_5','mrr_at_5','ndcg_at_5'):
            values=[s[metric] for s in scores if s[metric] is not None]; group[metric]=statistics.mean(values) if values else None
        rows.append(group)
    result={'at':utcnow(),'unit':'source_id; duplicate chunks do not earn duplicate gain; ranks are final top-5 chunk slots',
            'results':rows,'limitations':['No section-level gold labels exist; source qrels are used rather than inventing section labels.',
                'Offline variants compare fixture wiring on the same two development inputs, not learned semantic model quality.',
                'Only the full live configuration ran on two development cases; no paid live ablation or final holdout claim.']}
    write_json(ROOT/'artifacts/architecture_v2/retrieval_analysis.json',result)
    print(canonical({'runs':len(rows),'provider_requests':0,'unit':result['unit']}))

if __name__=='__main__': main()
