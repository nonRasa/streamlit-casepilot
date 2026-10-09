"""Meaningful controls for the paid campaign's evaluator and budget boundaries."""
import sys,tempfile,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import CasePilotError
from casepilot.evaluation_completion import retrieval_scores,candidate_key,classify_failure
from complete_quality_v27 import CampaignBudget,FrozenCandidates
from casepilot.embeddings import EmbeddingCache


class CompletionControls(unittest.TestCase):
    def test_unjudged_not_negative_and_ndcg_not_claimed(self):
        row={'source_id':'a','text':'needed exact witness','revision':'r','source_span':[0,20]}
        label={'required_evidence':[{'source_id':'a','quote':'exact witness'}],'relevance':{'a':3}}
        scores=retrieval_scores([row],[row],label,{})
        self.assertIsNone(scores['ndcg_at_k']);self.assertIsNone(scores['judged_irrelevant_fraction'])
        self.assertEqual(scores['judgment_coverage'],0);self.assertEqual(scores['context_witness_coverage'],1)
        full=retrieval_scores([row],[row],label,{candidate_key(row):{'grade':3}})
        self.assertEqual(full['ndcg_at_k'],1);self.assertEqual(full['judgment_coverage'],1)

    def test_atomic_reservation_survives_unknown_and_phase_limit(self):
        with tempfile.TemporaryDirectory() as d:
            auth={'campaign':'test','hard_cap_usd':.03,'max_requests':2,'cost_before':{'charged_or_reserved_usd':0},
                  'phase_limits':{'judge':{'requests':1,'usd':.02},'index':{'requests':1,'usd':.02}}}
            b=CampaignBudget(Path(d)/'ledger.db',auth,'judge');cid=b.reserve(.02,'gpt-4.1-mini','judge');b.uncertain(cid)
            with self.assertRaises(CasePilotError):b.reserve(.001,'gpt-4.1-mini','judge')
            b2=CampaignBudget(b.path,auth,'index')
            with self.assertRaises(CasePilotError):b2.reserve(.02,'text-embedding-3-small','embedding')
            b2.reserve(.005,'text-embedding-3-small','embedding')
            self.assertAlmostEqual(b2.report()['charged_or_reserved_usd'],.025)

    def test_model_outside_approval_has_no_debit(self):
        with tempfile.TemporaryDirectory() as d:
            auth={'campaign':'t','hard_cap_usd':1,'max_requests':2,'cost_before':{'charged_or_reserved_usd':0},
                  'phase_limits':{'judge':{'requests':2,'usd':1}}}
            b=CampaignBudget(Path(d)/'db',auth,'judge')
            with self.assertRaises(CasePilotError):b.reserve(.01,'other-model','judge')
            self.assertEqual(b.report()['requests'],0)

    def test_embedding_resume_only_missing_text_and_new_namespace(self):
        class Embedder:
            identity={'provider':'live-test-double','model':'same-model'}
            last_usage={}
            def __init__(self):self.seen=[];self.fail=True
            def embed(self,texts):
                self.seen.append(list(texts))
                if self.fail and len(self.seen)==2:raise RuntimeError('simulated outage')
                return [[1.,2.] for _ in texts]
        with tempfile.TemporaryDirectory() as d:
            e=Embedder();c=EmbeddingCache(Path(d)/'db',e,namespace='new-structure')
            with self.assertRaises(RuntimeError):c.get_many(['a','b','c'],batch_size=2)
            e.fail=False;c.get_many(['a','b','c'],batch_size=2)
            self.assertEqual(e.seen,[['a','b'],['c'],['c']])
            self.assertEqual(c.last_stats['cache_hits'],2)
            old=EmbeddingCache(c.path,e,namespace='old-structure')
            with self.assertRaises(CasePilotError):old.get_many(['a'],allow_create=False)

    def test_BC_candidates_are_same_despite_generated_query(self):
        rows=[{'id':'exact'}];result={'query':'fixed','query_vector_hash':'real','variants':{
            'B':{'candidates':rows,'candidate_hash':'same','index':'v3','namespace':'new'},
            'C':{'candidates':rows,'candidate_hash':'same','index':'v3','namespace':'new'}}}
        b=FrozenCandidates(result,'B');c=FrozenCandidates(result,'C')
        self.assertEqual(b.search('summary A'),c.search('summary B'))
        self.assertEqual(b.last_trace['query_vector_hash'],c.last_trace['query_vector_hash'])

    def test_failure_categories_separate_contract_from_content(self):
        self.assertEqual(classify_failure('provider_http_error'),'gateway')
        self.assertEqual(classify_failure('model_output_incomplete'),'truncation')
        self.assertEqual(classify_failure('judge_contract_error'),'schema_or_reference')
        self.assertEqual(classify_failure('judge_contract_error',True),'semantic_consistency')
        self.assertIsNone(classify_failure(None))

    def test_generator_schema_binds_quote_to_its_actual_source(self):
        from casepilot.case_type import selection_schema
        from casepilot.schema_preflight import check_provider_schema
        from jsonschema import Draft202012Validator
        s={'messages':[{'text':'How do I configure upload size?'}]}
        wire=selection_schema(s,{'one':['q1'],'two':['q2']});check_provider_schema(wire)
        claim_schema=wire['properties']['claims']['items'];v=Draft202012Validator(claim_schema)
        self.assertTrue(v.is_valid({'evidence_id':'one','quote_id':'q1'}))
        for bad in ({'evidence_id':'one','quote_id':''},{'evidence_id':'one','quote_id':'q2'},
                    {'evidence_id':'invented','quote_id':'q1'}):
            self.assertFalse(v.is_valid(bad))
        self.assertEqual(selection_schema(s,{})['properties']['claims']['maxItems'],0)

    def test_clear_feature_is_proposal_without_repeated_goal_or_api_claim(self):
        from casepilot.case_type import selection_schema
        s={'messages':[{'text':'Feature request: add an option to resize a dialog. Acceptance: dragging changes width.'}],
           'investigation_plan':{'intent':'feature_request','missing_detail':'','suggested_question':''}}
        wire=selection_schema(s,{'unrelated':['q1']})
        self.assertEqual(wire['properties']['question']['enum'],[''])
        self.assertEqual(wire['properties']['decision']['enum'],['escalate'])
        self.assertEqual(wire['properties']['claims']['maxItems'],0)
        self.assertIn('enum',wire['properties']['rationale'])
        options=wire['properties']['feature_proposal']['properties']['current_behavior']['enum']
        self.assertFalse(any('وجود ندارد' in x for x in options))
        s['investigation_plan']['missing_detail']='Which of the two unspecified modes?'
        self.assertNotIn('enum',selection_schema(s)['properties']['question'])

    def test_contiguous_range_catalog_full_processor_and_invalid_legacy_lists(self):
        import copy
        from casepilot.compact_review import phrase_ranges,decode
        from casepilot.semantics import checked_semantic_review
        from test_quality_v27 import JudgeContractTests
        a,s,env,c,w=JudgeContractTests().sample()
        self.assertEqual(checked_semantic_review(decode(w,c),a,[],s,env)['verdict'],'accept')
        catalog=phrase_ranges(4)
        self.assertEqual(len(catalog),11)
        self.assertEqual(catalog['phrases_1_to_3'],[1,2,3])
        for value in ([0,0],[1,2,0],'phrases_0_to_999'):
            bad=copy.deepcopy(w);bad['u']['u0']['p']=value
            with self.assertRaises(CasePilotError):checked_semantic_review(decode(bad,c),a,[],s,env)

    def test_controlled_clock_produces_identical_rerank_state(self):
        from unittest.mock import patch
        from casepilot.store import Store
        from casepilot.pipeline import compact_state
        from casepilot.common import digest
        with tempfile.TemporaryDirectory() as d:
            states=[]
            for variant in ('B','C'):
                store=Store(Path(d)/(variant+'.db'))
                with patch('casepilot.store.utcnow',return_value='2026-10-10T00:00:00+00:00'):
                    states.append(store.update('case1','Streamlit 1.49.0. I already tested it.',{'streamlit_version':'1.49.0'},[]))
            self.assertEqual(digest(compact_state(states[0])),digest(compact_state(states[1])))

    def test_feature_request_cannot_prove_current_api_absence(self):
        from test_quality_v25 import FeatureControls,judge
        from casepilot.compact_review import contract,encode_fixture,decode
        from casepilot.review_contract import review_spans
        from casepilot.semantics import checked_semantic_review
        a,s=FeatureControls().proposal('GH16481')
        a['feature_proposal']['current_behavior']='گزارش کاربر: چنین قابلیت یا گزینه‌ای در حال حاضر وجود ندارد.'
        env,r=judge(a,s);c=contract(env,review_spans(s,[],[]));w=encode_fixture(r,c)
        out=checked_semantic_review(decode(w,c),a,[],s,env)
        self.assertNotEqual(out['verdict'],'accept')
        self.assertTrue(any('استنتاج شده' in f['reason'] for f in out['findings']))

    def test_frozen_split_has_twenty_witness_cases_and_no_families_overlap(self):
        base=ROOT/'eval/quality_v27_completion'
        dev=json.loads((base/'dev_inputs.json').read_text(encoding='utf8'))
        hold=json.loads((base/'holdout_inputs.json').read_text(encoding='utf8'))
        self.assertEqual(len(dev)+len(hold),24)
        self.assertFalse({i['family'] for i in dev}&{i['family'] for i in hold})
        labels=sum([json.loads((base/(s+'_labels.json')).read_text(encoding='utf8')) for s in ('dev','holdout')],[])
        self.assertEqual(sum(bool(l['required_evidence']) for l in labels),20)

if __name__=='__main__':unittest.main()
