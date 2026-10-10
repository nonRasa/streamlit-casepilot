"""Development-only, no-model comparison of draft evidence version filtering."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.agent import extract_facts
from casepilot.hybrid import HybridRetriever
from casepilot.pipeline import pack
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever


def main():
    cases = [c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['split'] == 'dev']
    searcher = HybridRetriever.__new__(HybridRetriever)
    searcher.lexical = Retriever(ROOT / 'data/corpus_v2.json')
    rows = []
    for case in cases:
        message = case['initial_message']
        facts = {**extract_facts(message), **case.get('initial_facts', {})}
        state = {'messages': [{'text': message}], 'facts': facts}
        candidates = searcher.search(retrieval_query(state, message), k=8, version=facts.get('streamlit_version'), components={'dense': False})
        before = pack(candidates)
        filtered = [r for r in candidates if not (facts.get('streamlit_version') and r.get('version_relation') == 'mismatch')]
        after = pack(filtered)
        rows.append({'id': case['id'], 'current_version': facts.get('streamlit_version'),
                     'before': [{'source_id': r['source_id'], 'version_relation': r.get('version_relation')} for r in before],
                     'after': [{'source_id': r['source_id'], 'version_relation': r.get('version_relation')} for r in after]})
    totals = {stage: {kind: sum(r['version_relation'] == kind for case in rows for r in case[stage])
                      for kind in ('exact', 'mismatch', 'unknown')} for stage in ('before', 'after')}
    print(json.dumps({'split': 'dev', 'method': 'no_dense_context_k5_before_model_rerank',
                      'cases': len(rows), 'totals': totals, 'rows': rows}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
