"""Reproducible, development-only comparison of no-dense evidence selection."""
import collections
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from casepilot.agent import extract_facts
from casepilot.evidence import annotate
from casepilot.hybrid import HybridRetriever
from casepilot.pipeline import pack
from casepilot.quality import retrieval_query, technical_source
from casepilot.retrieval import Retriever


def previous_candidates(retriever,query,version):
    rows=[r for r in retriever.search(query,k=100,method='baseline',version=version) if technical_source(r)]
    apis=list(dict.fromkeys(re.findall(r'\bst\.([A-Za-z_]\w*)',query)))[:8]
    chosen=[]; ids=set()
    for api in apis:
        match=next((r for r in rows if r['source_id']=='api:'+api and r['id'] not in ids),None)
        if match and len(chosen)<2:
            chosen.append(match); ids.add(match['id'])
    counts=collections.Counter(r['source_id'] for r in chosen)
    for row in rows:
        if len(chosen)>=8: break
        if row['id'] in ids or counts[row['source_id']]>=2: continue
        chosen.append(row); ids.add(row['id']); counts[row['source_id']]+=1
    return [annotate(r,version) for r in chosen]


def score(rows,cases):
    return {
        'cases_with_labeled_source':sum(bool(set(r['sources'])&set(c['relevant_source_ids'])) for r,c in zip(rows,cases)),
        'labeled_source_hits':sum(len(set(r['sources'])&set(c['relevant_source_ids'])) for r,c in zip(rows,cases)),
        'official_chunks':sum(r['official_chunks'] for r in rows),
        'mismatched_chunks':sum(r['mismatched_chunks'] for r in rows),
        'unknown_version_chunks':sum(r['unknown_version_chunks'] for r in rows),
        'context_utf8_bytes':sum(r['context_utf8_bytes'] for r in rows),
    }


def describe(packet):
    return {'sources':[r['source_id'] for r in packet],
            'official_chunks':sum(r['kind']=='docs' for r in packet),
            'mismatched_chunks':sum(r['version_relation']=='mismatch' for r in packet),
            'unknown_version_chunks':sum(r['version_relation']=='unknown' for r in packet),
            'context_utf8_bytes':sum(len(r['text'].encode('utf-8')) for r in packet)}


def main():
    cases=[c for c in json.loads((ROOT/'eval/cases.json').read_text(encoding='utf-8')) if c['split']=='dev']
    lexical=Retriever(ROOT/'data/corpus_v2.json')
    hybrid=HybridRetriever.__new__(HybridRetriever)
    hybrid.lexical=lexical
    before=[]; after=[]; details=[]
    for case in cases:
        message=case['initial_message']
        facts={**extract_facts(message),**case.get('initial_facts',{})}
        query=retrieval_query({'messages':[{'text':message}],'facts':facts},message)
        version=facts.get('streamlit_version')
        old=[r for r in previous_candidates(lexical,query,version) if not(version and r['version_relation']=='mismatch')]
        new=[r for r in hybrid.search(query,k=8,version=version,components={'dense':False}) if not(version and r['version_relation']=='mismatch')]
        a=describe(pack(old)); b=describe(pack(new,query=query))
        before.append(a); after.append(b)
        details.append({'id':case['id'],'before':a,'after':b,
                        'labeled_before':sorted(set(a['sources'])&set(case['relevant_source_ids'])),
                        'labeled_after':sorted(set(b['sources'])&set(case['relevant_source_ids']))})
    result={'split':'dev','mode':'offline_no_model_no_rerank','cases':len(cases),
            'before':score(before,cases),'after':score(after,cases),'details':details}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
