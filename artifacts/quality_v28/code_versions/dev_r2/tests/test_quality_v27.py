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
    def test_provider_unsupported_schema_fails_locally_duplicates_still_fail(self):
        from casepilot.schema_preflight import check_provider_schema
        a,s,env,c,w=self.sample(); check_provider_schema(schema(c))
        with self.assertRaises(CasePilotError): check_provider_schema({'type':'array','uniqueItems':True})
        # A relational duplicate remains forbidden even without uniqueItems.
        w['n']['m']=['m0','m0']
        with self.assertRaises(CasePilotError): checked_semantic_review(decode(w,c),a,[],s,env)
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
    def test_unrelated_official_document_has_no_reserved_slot(self):
        import tempfile
        from casepilot.parent_child import chunks
        from casepilot.common import write_json
        from casepilot.hybrid import HybridRetriever
        from casepilot.model import ReplayClient
        def source(sid,kind,text,version=None):
            return chunks({'id':sid,'title':sid,'kind':kind,'text':text,'url':'https://example.invalid',
                           'revision':'snapshot','product_version':version})
        rows=source('issue:target','issue','The lunar widget throws TargetKeyError during the lunar callback.')
        rows+=source('docs:unrelated','docs','A color palette defines red blue and green theme colors.','1.49.0')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'corpus.json';write_json(path,rows)
            h=HybridRetriever(ReplayClient(),path,Path(tmp)/'vectors.sqlite3')
            result=h.search('lunar TargetKeyError callback',k=1,version='1.49.0')
        self.assertEqual(result[0]['source_id'],'issue:target')
        self.assertEqual(result[0]['version_relation'],'unknown')
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
        pid=max({r['parent_id'] for r in rows},key=lambda p:sum(r['parent_id']==p for r in rows))
        same=[r for r in rows if r['parent_id']==pid]
        children,base=pack_evidence(same,max_tokens=1200,expand_parent=False)
        expanded,trace=pack_evidence(same,max_tokens=1200,expand_parent=True)
        self.assertGreater(len(children),1); self.assertEqual(len(expanded),1)
        self.assertEqual(set(expanded[0]['selected_child_ids']),{r['id'] for r in same})
        self.assertEqual(text[slice(*expanded[0]['source_span'])],expanded[0]['text'])
        self.assertLessEqual(trace['used_tokens'],1200)
        tight,trace=pack_evidence(same,max_tokens=250,expand_parent=True)
        self.assertLessEqual(trace['used_tokens'],250)
        self.assertTrue(any('budget' in r.get('reason','') for r in trace['items']))

class ResponseRouteTests(unittest.TestCase):
    def test_explicit_and_ambiguous_routes(self):
        from casepilot.case_type import case_kind,response_policy
        for text,expected in [('Feature request: add an option for export.','feature_request'),
                              ('Bug report: application crashes.','bug'),('How do I set the page title?','usage_question'),
                              ('Bug report: regression. Feature request: add an option.','mixed'),('Please help.','unknown')]:
            s={'messages':[{'text':text}]}
            self.assertEqual(case_kind(s),expected)
            self.assertEqual(response_policy(s,[])['request_type'],expected)
    def test_novelty_uses_earlier_raw_code_and_later_messages(self):
        from casepilot.quality import novelty_findings
        s={'facts':{},'messages':[{'text':'Code:\n```python\nclass Payload:\n    pass\n```'},
                                 {'text':'I confirmed pickle outside Streamlit works.'}]}
        a=answer();a.update(decision='ask',question='پرسش: تعریف کامل کلاس را بفرستید.',next_step='تعریف کلاس را ارسال کنید.')
        self.assertTrue(novelty_findings(a,s))
        a.update(question='پرسش: pickle را خارج برنامه آزمایش کنید.',next_step='pickle را بیرون برنامه اجرا کنید.')
        self.assertTrue(novelty_findings(a,s))
    def test_unknown_novelty_is_not_certified_new(self):
        a=answer();s=state();env,r=judge(a,s);r['novelty']['status']='unknown'
        c=contract(env,review_spans(s,[],a['claims']))
        self.assertNotEqual(checked_semantic_review(decode(encode_fixture(r,c),c),a,[],s,env)['verdict'],'accept')
    def test_internal_failure_and_evidence_shortage_have_different_text(self):
        from casepilot.grounding import fallback
        self.assertIn('خطای داخلی',fallback('evidence_selection_error')['rationale'])
        self.assertNotEqual(fallback('evidence_selection_error'),fallback('unsupported_answer'))

class EvaluationMetricTests(unittest.TestCase):
    def test_standard_top_k_does_not_pull_sixth_chunk_into_fifth_rank(self):
        from casepilot.evaluation import retrieval_metrics
        rows=[{'source_id':'noise','text':'noise'}]*5+[{'source_id':'required','text':'witness'}]
        label={'relevance':{'required':3},'judged_irrelevant_source_ids':['noise'],
               'required_evidence':[{'source_id':'required','quote':'witness'}]}
        metrics=retrieval_metrics(rows,label,k=5)
        self.assertEqual(metrics['recall_at_k'],0);self.assertEqual(metrics['ndcg_at_k'],0)
        self.assertEqual(metrics['judged_irrelevant_fraction'],1)
    def test_no_required_evidence_is_not_a_fake_perfect_recall(self):
        from casepilot.evaluation import retrieval_metrics
        m=retrieval_metrics([],{'relevance':{},'judged_irrelevant_source_ids':[],'required_evidence':[]})
        self.assertIsNone(m['recall_at_k']); self.assertIsNone(m['ndcg_at_k']);self.assertIsNone(m['required_evidence_coverage'])
    def test_family_isolation_and_no_labels_in_sut_inputs(self):
        from casepilot.common import read_json
        dev=read_json(ROOT/'eval/quality_v27/dev_inputs.json');holdout=read_json(ROOT/'eval/quality_v27/holdout_inputs.json')
        self.assertFalse({x['family'] for x in dev}&{x['family'] for x in holdout})
        for row in dev+holdout:
            self.assertFalse({'expected_route','expected_behavior','relevance','required_evidence'} & set(row))
    def test_provider_schema_preflight_precedes_any_paid_request(self):
        from casepilot.model import MetisClient
        from unittest.mock import patch
        client=object.__new__(MetisClient);client.last_usage={};client.usage_history=[];client.calls=0
        with patch('casepilot.model.build_opener',side_effect=AssertionError('network forbidden')):
            with self.assertRaises(CasePilotError) as e:
                client._request({'response_format':{'type':'json_schema','json_schema':{'schema':{'type':'array','uniqueItems':True}}}})
        self.assertEqual(e.exception.code,'unsupported_provider_schema');self.assertEqual(client.calls,0)

if __name__=='__main__': unittest.main()
