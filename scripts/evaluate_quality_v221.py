"""Offline, label-blind retrieval and quote-selection ablations on dev cases."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from casepilot.agent import extract_facts
from casepilot.hybrid import HybridRetriever
from casepilot.model import focused_quote_candidates, quote_candidates
from casepilot.pipeline import pack
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever


def summary(packets,cases):
    found=[set(x['source_id'] for x in packet)&set(case['relevant_source_ids'])
           for packet,case in zip(packets,cases)]
    return {'cases_with_labeled_source':sum(bool(x) for x in found),
            'labeled_source_hits':sum(len(x) for x in found),
            'official_chunks':sum(row['kind']=='docs' for packet in packets for row in packet),
            'mismatched_chunks':sum(row['version_relation']=='mismatch' for packet in packets for row in packet),
            'context_utf8_bytes':sum(len(row['text'].encode()) for packet in packets for row in packet)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live-answer',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    cases=[c for c in json.loads((ROOT/'eval/cases.json').read_text(encoding='utf-8')) if c['split']=='dev']
    lexical=Retriever(ROOT/'data/corpus_v2.json')
    hybrid=HybridRetriever.__new__(HybridRetriever)
    hybrid.lexical=lexical
    packets={'single_simple':[],'single_reserved':[],'split_simple':[],'split_reserved':[]}
    details=[]
    for case in cases:
        message=case['initial_message']
        facts={**extract_facts(message),**case.get('initial_facts',{})}
        query=retrieval_query({'messages':[{'text':message}],'facts':facts},message)
        version=facts.get('streamlit_version')
        candidates={name:[row for row in hybrid.search(query,k=8,version=version,components={'dense':False,'split_query':split})
                          if not(version and row['version_relation']=='mismatch')]
                    for name,split in [('single',False),('split',True)]}
        for name,rows in candidates.items():
            packets[name+'_simple'].append(pack(rows))
            packets[name+'_reserved'].append(pack(rows,query=query))
        details.append({'id':case['id'],'query':query,'candidates':{k:[r['id'] for r in v] for k,v in candidates.items()},
                        'packets':{k:[r['id'] for r in v[-1]] for k,v in packets.items()},
                        'labeled_sources':case['relevant_source_ids']})
    result={'split':'dev','mode':'offline_no_model','cases':len(cases),
            'metrics':{name:summary(value,cases) for name,value in packets.items()},
            'details':details}
    gh=next((i,c) for i,c in enumerate(cases) if c['id']=='GH9218')
    i,case=gh; query=details[i]['query']; doc=next(r for r in packets['single_reserved'][i]
                                             if r['source_id']=='docs:where-file-uploader-store-when-deleted')
    old=quote_candidates(doc['text']); focused=focused_quote_candidates(doc['text'],query)
    result['GH9218_quote_ablation']={'source_id':doc['source_id'],'old_count':len(old),'focused_count':len(focused),
        'old_first_quote_id':old[0]['quote_id'],'focused_first_quote_id':focused[0]['quote_id'],
        'old_first_has_bytesio_ram':'BytesIO' in old[0]['text'] and 'RAM' in old[0]['text'],
        'focused_first_has_bytesio_ram':'BytesIO' in focused[0]['text'] and 'RAM' in focused[0]['text'],
        'focused_quote_ids':[q['quote_id'] for q in focused]}
    if args.live_answer:
        answer=json.loads(args.live_answer.read_text(encoding='utf-8'))
        rerank=next(p['ids'] for p in answer['pipeline'] if p['stage']=='rerank')
        by_id={r['id']:r for r in hybrid.search(query,k=8,version=None,components={'dense':False})}
        ranked=[by_id[rid] for rid in rerank if rid in by_id]
        result['GH9218_saved_rerank_ablation']={
            'rerank_ids':rerank,
            'without_reserved':[r['source_id'] for r in pack(ranked)],
            'with_reserved':[r['source_id'] for r in pack(ranked,query=query)],
            'without_model_rerank':[r['source_id'] for r in packets['single_reserved'][i]]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
