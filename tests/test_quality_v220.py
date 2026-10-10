"""Regression test for directly relevant official evidence reaching the draft."""
import json
import unittest
from pathlib import Path

from casepilot.hybrid import HybridRetriever
from casepilot.pipeline import pack
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever

ROOT=Path(__file__).resolve().parents[1]


class DirectEvidenceSelectionTests(unittest.TestCase):
    def test_upload_ram_guide_survives_issue_heavy_rerank(self):
        case=next(c for c in json.loads((ROOT/'eval/cases.json').read_text(encoding='utf-8')) if c['id']=='GH9218')
        message=case['initial_message']
        query=retrieval_query({'messages':[{'text':message}],'facts':{}},message)
        hybrid=HybridRetriever.__new__(HybridRetriever)
        hybrid.lexical=Retriever(ROOT/'data/corpus_v2.json')
        candidates=hybrid.search(query,k=8,components={'dense':False})
        # A model reranker may place official sources last; the final packet
        # must still retain the directly named source.
        issues=[r for r in candidates if r['kind']=='issue']
        docs=[r for r in candidates if r['kind']=='docs']
        packet=pack(issues+docs,query=query)
        sources=[r['source_id'] for r in packet]
        self.assertIn('docs:where-file-uploader-store-when-deleted',sources)
        self.assertIn('api:file_uploader',sources)
        self.assertEqual(packet[0]['kind'],'docs')


if __name__=='__main__': unittest.main()
