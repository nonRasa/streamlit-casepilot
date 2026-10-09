"""Stage controls are local fixtures, never evidence of live model quality."""
import copy, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import CasePilotError
from casepilot.compact_review import contract, schema, decode, encode_fixture, PROMPT
from casepilot.review_contract import draft_units, review_spans
from casepilot.semantics import checked_semantic_review
from test_quality_v23 import answer
from test_quality_v25 import state, judge
import test_quality_v25 as v25

class JudgeContractTests(unittest.TestCase):
    def sample(self):
        a=answer(); s=state(); env,r=judge(a,s)
        c=contract(env,review_spans(s,[],a['claims']))
        return a,s,env,c,encode_fixture(r,c)
    def test_every_reason_schema_and_full_processor_agree(self):
        a,s,env,c,w=self.sample()
        self.assertEqual(checked_semantic_review(decode(w,c),a,[],s,env)['verdict'],'accept')
        for where in ('criterion','unit','novelty'):
            for value in ('','  ','\n'):
                bad=copy.deepcopy(w)
                if where=='criterion': bad['r'][0]=value
                elif where=='unit': bad['u']['u0']['r']=value
                else: bad['n']['r']=value
                with self.subTest(where=where,value=value), self.assertRaises(CasePilotError):
                    checked_semantic_review(decode(bad,c),a,[],s,env)
    def test_numeric_semantics_no_longer_accepted(self):
        a,s,env,c,w=self.sample()
        for key in ('k','a','s'):
            bad=copy.deepcopy(w); bad['u']['u0'][key]=0
            with self.assertRaises(CasePilotError): checked_semantic_review(decode(bad,c),a,[],s,env)
        self.assertNotIn('WIRE OVERRIDE',PROMPT)
        self.assertNotIn('Copy draft_version',PROMPT)
    def test_capacity_full_processing_and_boundaries(self):
        a,s=v25.FeatureControls().proposal('GH16481')
        a.update(decision='ask',question='پرسش: کدام شرط پذیرش نامعلوم است؟',hypotheses=['فرضیه: علت هنوز تأیید نشده است.']*3)
        env,r=judge(a,s)
        for u,e in zip(env['units'],r['unit_reviews']):
            if u['field'].startswith('hypotheses.'):
                e.update(kind='hypothesis',premise=True); e['meaning'].update(act='technical',assertion_text=u['text'])
        c=contract(env,review_spans(s,[],a['claims'])); w=encode_fixture(r,c)
        out=checked_semantic_review(decode(w,c),a,[],s,env)
        self.assertEqual(len(out['unit_reviews']),11)
        self.assertNotEqual(out['verdict'],'accept') # valid contract, unsupported content
        self.assertNotEqual(out['failure_kind'],'judge_contract')
        too_many=copy.deepcopy(env); too_many['units'].append(env['units'][0])
        with self.assertRaises(CasePilotError): contract(too_many,review_spans(s,[]))

class EvidenceSelectionTests(unittest.TestCase):
    def test_subset_and_empty_do_not_restore_dropped_official_document(self):
        from casepilot.roles import rerank_ids
        rows=[{'id':'issue','kind':'issue'}, {'id':'irrelevant-official','kind':'docs'}, {'id':'old-version','product_version':'1.0'}]
        self.assertEqual(rerank_ids({'ordered_ids':['issue']},rows),rows[:1])
        self.assertEqual(rerank_ids({'ordered_ids':[]},rows),[])
        for bad in ({'ordered_ids':['foreign']},{'ordered_ids':['issue','issue']},{'ordered_ids':None},{}):
            with self.assertRaises(CasePilotError): rerank_ids(bad,rows)
    def test_full_pipeline_valid_empty_is_not_internal_error(self):
        import tempfile
        from unittest.mock import patch
        from casepilot import pipeline
        from casepilot.agent import Agent
        from casepilot.store import Store
        from casepilot.model import ReplayClient
        from test_architecture_v2 import TinyHybrid
        original=pipeline.fixture_role
        with tempfile.TemporaryDirectory() as tmp:
            agent=Agent(Store(Path(tmp)/'case.sqlite3'),client=ReplayClient(),hybrid=TinyHybrid())
            with patch.object(pipeline,'fixture_role',side_effect=lambda n,p: {'ordered_ids':[]} if n=='rerank' else original(n,p)):
                out=agent.turn('empty','A widget problem','one')
        self.assertEqual(out['retrieved'],[])
        self.assertIsNone(out['validation_error'])
        self.assertIn('no_relevant_evidence',[s.get('status') for s in out['pipeline']])

class StructuralTests(unittest.TestCase):
    def source(self,text,kind='docs'):
        return {'id':'sample','kind':kind,'title':'Sample','text':text,'revision':'2026-10-09',
                'url':'https://example.invalid/source','product_version':None}
    def test_actual_multilingual_tokens_and_short_report(self):
        from casepilot.parent_child import chunks
        from casepilot.tokenization import count_tokens
        text='# Problem\r\n\r\nنسخه نامعلوم است.\r\n\r\n# Expected\r\nThe button should respond.'
        rows=chunks(self.source(text,'issue'))
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['text'],text)
        self.assertEqual(rows[0]['token_count'],count_tokens(text))
        self.assertLess(rows[0]['token_count'],len(text.encode()))
        self.assertIsNone(rows[0]['product_version']) # date is not product version
    def test_spans_hierarchy_table_headers_and_code_boundaries(self):
        from casepilot.parent_child import chunks
        text='# Parent\n## Child\n\n```python\n'+''.join('def function_'+str(i)+'():\n    return '+repr('sample '*8)+'\n\n' for i in range(12))+'```\n\n| Name | Value |\n| --- | --- |\n'+''.join('| row'+str(i)+' | '+('value '*8)+'|\n' for i in range(25))
        rows=chunks(self.source(text),child_tokens=90,parent_tokens=250)
        self.assertEqual(rows,chunks(self.source(text),90,250))
        self.assertTrue(any(r['header_spans'] for r in rows))
        self.assertTrue(any(r['section_path']==['Sample','Parent','Child'] for r in rows))
        for r in rows:
            a,b=r['source_span']; self.assertEqual(text[a:b],r['text'])
            p=r['parent']; a,b=p['source_span']; self.assertEqual(text[a:b],p['text'])
            self.assertEqual(r['parent_id'],p['id'])
            for h in r['header_spans']:
                self.assertEqual(text[slice(*h['source_span'])],h['text'])
        changed=chunks(dict(self.source(text),revision='next'),90,250)
        self.assertNotEqual(rows[0]['id'],changed[0]['id'])
    def test_token_budget_omissions_and_exact_citation_offsets(self):
        from casepilot.parent_child import chunks
        from casepilot.context_pack import pack_evidence
        from casepilot.grounding import validate_answer
        text='# Section\n\n'+('A useful exact source sentence with sufficient content.\n\n'*40)
        rows=chunks(self.source(text),80,240)
        selected,trace=pack_evidence(rows,max_tokens=350)
        self.assertLessEqual(trace['used_tokens'],350)
        self.assertTrue(any(e['status']=='omitted' for e in trace['items']))
        r=selected[0]; q='A useful exact source sentence with sufficient content.'
        a=answer(); a['claims']=[{'evidence_id':r['id'],'quote':q}]
        c=validate_answer(a,selected)[0]
        self.assertEqual(text[slice(*c['source_span'])],q)
    def test_cache_namespace_invalidates_same_text(self):
        from casepilot.embeddings import EmbeddingCache,FixtureEmbedder
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cache.db'; old=EmbeddingCache(path,FixtureEmbedder())
            old.get_many(['same text'])
            new=EmbeddingCache(path,FixtureEmbedder(),namespace='new-structure')
            with self.assertRaises(CasePilotError): new.get_many(['same text'],allow_create=False)
    def test_parent_expansion_merges_siblings_and_never_exceeds_budget(self):
        from casepilot.parent_child import chunks
        from casepilot.context_pack import pack_evidence
        text='# Section\n\n'+('Detailed context sentence with enough words to exercise token windows. '*50)
        rows=chunks(self.source(text),100,250)
        same=[r for r in rows if r['parent_id']==rows[0]['parent_id']]
        children,base=pack_evidence(same,max_tokens=1200,expand_parent=False)
        expanded,trace=pack_evidence(same,max_tokens=1200,expand_parent=True)
        self.assertGreater(len(children),1); self.assertEqual(len(expanded),1)
        self.assertEqual(set(expanded[0]['selected_child_ids']),{r['id'] for r in same})
        self.assertEqual(text[slice(*expanded[0]['source_span'])],expanded[0]['text'])
        self.assertLessEqual(trace['used_tokens'],1200)
        tight,trace=pack_evidence(same,max_tokens=250,expand_parent=True)
        self.assertLessEqual(trace['used_tokens'],250)
        self.assertTrue(any('budget' in r.get('reason','') for r in trace['items']))

if __name__=='__main__': unittest.main()
