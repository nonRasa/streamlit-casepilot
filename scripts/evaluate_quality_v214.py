"""Offline, development-only lexical retrieval comparison for v2.14."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever
from casepilot.hybrid import HybridRetriever


def main():
    old_path = ROOT / 'artifacts/architecture_v2/live/v212_isolated_no_dense/frozen/src/casepilot/quality.py'
    spec = importlib.util.spec_from_file_location('casepilot.quality_v211_frozen', old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    hybrid_path = ROOT / 'artifacts/architecture_v2/live/v212_isolated_no_dense/frozen/src/casepilot/hybrid.py'
    hybrid_spec = importlib.util.spec_from_file_location('casepilot.hybrid_v212_frozen', hybrid_path)
    old_hybrid = importlib.util.module_from_spec(hybrid_spec)
    hybrid_spec.loader.exec_module(old_hybrid)
    cases = [c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['split'] == 'dev']
    retriever = Retriever(ROOT / 'data/corpus_v2.json')
    before = old_hybrid.HybridRetriever.__new__(old_hybrid.HybridRetriever)
    after = HybridRetriever.__new__(HybridRetriever)
    before.lexical = after.lexical = retriever
    rows = []
    for c in cases:
        message = c['initial_message']
        state = {'messages': [{'text': message}], 'facts': c.get('initial_facts', {})}
        expected = set(c['relevant_source_ids'])
        results = {}
        for label, query_fn, searcher in [('before', old.retrieval_query, before), ('after', retrieval_query, after)]:
            found = [r['source_id'] for r in searcher.search(query_fn(state, message), k=5, version=state['facts'].get('streamlit_version'), components={'dense': False})]
            results[label] = {'found': found, 'hits': len(expected.intersection(found)), 'relevant': len(expected)}
        rows.append({'id': c['id'], **results})
    totals = {label: {'hits': sum(r[label]['hits'] for r in rows), 'relevant': sum(r[label]['relevant'] for r in rows)} for label in ('before', 'after')}
    print(json.dumps({'split': 'dev', 'method': 'production_no_dense_k5', 'cases': len(rows), 'totals': totals, 'rows': rows}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
