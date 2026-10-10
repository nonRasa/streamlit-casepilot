"""Paired, development-only retrieval comparison; no provider calls."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.agent import extract_facts
from casepilot.hybrid import HybridRetriever
from casepilot.evidence import relation
from casepilot.pipeline import pack
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever


def main():
    cases = {c['id']: c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['split'] == 'dev'}
    baseline = json.loads((ROOT / 'artifacts/architecture_v2/offline/v216/version_filter_dev.json').read_text(encoding='utf-8'))
    searcher = HybridRetriever.__new__(HybridRetriever)
    searcher.lexical = Retriever(ROOT / 'data/corpus_v2.json')
    original_search = searcher.lexical.search
    # Simulate the discarded intervention without changing production retrieval.
    def filtered_search(query, k=5, method='final', version=None):
        candidates = original_search(query, k=k, method=method, version=version)
        return [r for r in candidates if not version or relation(r, version) != 'mismatch']
    searcher.lexical.search = filtered_search
    rows = []
    for previous in baseline['rows']:
        case = cases[previous['id']]
        message = case['initial_message']
        facts = {**extract_facts(message), **case.get('initial_facts', {})}
        state = {'messages': [{'text': message}], 'facts': facts}
        candidates = searcher.search(retrieval_query(state, message), k=8, version=facts.get('streamlit_version'), components={'dense': False})
        current = [{'source_id': r['source_id'], 'version_relation': r['version_relation']} for r in pack(candidates)]
        relevant = set(case['relevant_source_ids'])
        rows.append({'id': case['id'], 'version': facts.get('streamlit_version'), 'v216': previous['after'], 'v218': current,
                     'label_hits_v216': len(relevant & {r['source_id'] for r in previous['after']}),
                     'label_hits_v218': len(relevant & {r['source_id'] for r in current}),
                     'excluded_before_k': 'simulated'})
    result = {'split': 'dev', 'method': 'no_dense_context_k5_before_model_rerank', 'cases': len(rows),
              'provider_requests': 0, 'baseline': 'frozen v216 artifact',
              'treatment': 'filter version mismatches from the lexical top 100 before selecting k=8',
              'totals': {version: {'mismatch': sum(r['version_relation'] == 'mismatch' for c in rows for r in c[version]),
                                   'unknown': sum(r['version_relation'] == 'unknown' for c in rows for r in c[version]),
                                   'exact': sum(r['version_relation'] == 'exact' for c in rows for r in c[version]),
                                   'label_hits': sum(c['label_hits_' + version] for c in rows),
                                   'short_packets': sum(len(c[version]) < 5 for c in rows)} for version in ('v216', 'v218')},
              'rows': rows}
    output = ROOT / 'artifacts/architecture_v2/offline/v218/retrieval_comparison.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['totals'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
