"""Print candidate official passages for manual development-set span annotation."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.agent import extract_facts
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever, tokens

cases = [c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['split'] == 'dev']
retriever = Retriever(ROOT / 'data/corpus_v2.json')
for case in cases:
    message = case['initial_message']
    facts = {**extract_facts(message), **case.get('initial_facts', {})}
    query = retrieval_query({'messages': [{'text': message}], 'facts': facts}, message)
    terms = set(tokens(query))
    relevant = [r for r in retriever.chunks if r['source_id'] in case['relevant_source_ids']]
    relevant.sort(key=lambda r: (-len(terms & set(tokens(r['text']))), r['id']))
    print('\n##', case['id'], message.splitlines()[0])
    for row in relevant[:3]:
        print(row['source_id'], row['id'], row['section'])
        print(row['text'][:1000].replace('\n', ' '))
