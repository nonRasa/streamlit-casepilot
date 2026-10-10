"""Focused source spans and optional split lexical retrieval."""
import json
import unittest
from pathlib import Path

from casepilot.hybrid import HybridRetriever, split_lexical_queries
from casepilot.model import focused_quote_candidates
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever

ROOT=Path(__file__).resolve().parents[1]


class EvidenceExperimentTests(unittest.TestCase):
    def test_memory_quote_is_exact_and_keeps_ie_abbreviation(self):
        rows=json.loads((ROOT/'data/corpus_v2.json').read_text(encoding='utf-8'))
        row=next(r for r in rows if r['source_id']=='docs:where-file-uploader-store-when-deleted')
        case=next(c for c in json.loads((ROOT/'eval/cases.json').read_text(encoding='utf-8')) if c['id']=='GH9218')
        query=retrieval_query({'messages':[{'text':case['initial_message']}],'facts':{}},case['initial_message'])
        quotes=focused_quote_candidates(row['text'],query)
        self.assertIn('BytesIO buffer in Python memory (i.e. RAM, not disk)',quotes[0]['text'])
        self.assertTrue(all(q['text'] in row['text'] for q in quotes))
        self.assertFalse(any(q['text'].startswith('http') for q in quotes))

    def test_split_query_retains_title_and_official_evidence(self):
        case=next(c for c in json.loads((ROOT/'eval/cases.json').read_text(encoding='utf-8')) if c['id']=='GH9218')
        query=retrieval_query({'messages':[{'text':case['initial_message']}],'facts':{}},case['initial_message'])
        names,symptoms=split_lexical_queries(query)
        self.assertIn('file_uploader',names)
        self.assertIn('server getting killed',symptoms)
        hybrid=HybridRetriever.__new__(HybridRetriever)
        hybrid.lexical=Retriever(ROOT/'data/corpus_v2.json')
        rows=hybrid.search(query,k=8,components={'dense':False,'split_query':True})
        self.assertIn('docs:where-file-uploader-store-when-deleted',{r['source_id'] for r in rows})


if __name__=='__main__': unittest.main()
