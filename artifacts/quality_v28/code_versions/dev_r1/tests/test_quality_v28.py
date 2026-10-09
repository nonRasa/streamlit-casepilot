"""Response-quality regressions: source units and request/fact boundaries."""
import copy,sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import CasePilotError
from casepilot.review_contract import draft_units,review_spans
from casepilot.compact_review import contract,encode_fixture,decode,schema
from casepilot.semantics import checked_semantic_review
from casepilot.grounding import citation_limit,validate_answer,render_response
from casepilot.model import resolve_claims
from casepilot.roles import CRITERIA
from test_quality_v23 import answer
from test_quality_v25 import state,judge

def quoted_sample():
    s=state('How can I submit two edited inputs together? Version unknown.')
    s['investigation_plan']={'intent':'usage_question'}
    text='Forms batch user input into a single rerun when the user submits the form. Unsubmitted changes are only sent to the Python backend when that form is submitted.'
    e=[{'id':'docs:forms:child','source_id':'docs:forms','kind':'docs','text':text,
        'product_version':None,'version_relation':'unknown','revision':'2026-01-01',
        'url':'https://example.invalid/forms','section':'Forms','lines':[1,1]}]
    a=answer();a.update(decision='answer',question='',next_step='اقدام: ورودی‌ها را طبق شاهد زیر گروه‌بندی کنید.',rationale='هدف: تغییرات ورودی با یک اقدام ارسال شوند.')
    a['claims']=[{'evidence_id':e[0]['id'],'quote':text,'version_limit':citation_limit(e[0])}]
    env=draft_units(a,s['id'],s['revision'],0,include_quotes=True);spans=review_spans(s,e,a['claims'])
    result={'verdict':'accept','draft_version':env['draft_version'],
      'assessments':{k:{'score':2,'reason':'کنترل: شاهد مرتبط و قدم مشخص است.'} for k in CRITERIA},
      'unit_reviews':[],'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'کنترل: سؤال تکراری ندارد.'}}
    for u in env['units']:
        quote=u['field'].startswith('claims.')
        result['unit_reviews'].append({'unit_id':u['unit_id'],'kind':'technical_claim' if quote else 'next_step',
            'support':'supported' if quote else 'unknown','source_ids':[spans['sources'][0]['span_id']] if quote else [],
            'message_ids':[],'premise':quote,'standalone':True,'reason':'کنترل: نقل‌قول یا اقدام بدون ادعای علت.',
            'version_dependent':quote,'version_limit':a['claims'][0]['version_limit'] if quote else '',
            'meaning':{'act':'technical' if quote else 'procedure','assertion_text':text if quote else '',
                'user_quote':'','depends_on':[]}})
    return a,s,e,env,result

def full(a,s,e,env,r):
    from casepilot.compact_review import descriptive_fixture,descriptive_decode
    c=contract(env,review_spans(s,e,a['claims']));wire=descriptive_fixture(encode_fixture(r,c))
    return checked_semantic_review(descriptive_decode(wire,c),a,e,s,env)

class ResponseQualityControls(unittest.TestCase):
    def test_descriptive_transport_preserves_meaning_and_rejects_old_keys(self):
        from casepilot.compact_review import descriptive_schema,descriptive_fixture,descriptive_decode,packet
        from jsonschema import Draft202012Validator
        a,s,e,env,r=quoted_sample();c,public=packet(env,review_spans(s,e,a['claims']))
        old=encode_fixture(r,c);wire=descriptive_fixture(old)
        self.assertFalse(list(Draft202012Validator(descriptive_schema(c)).iter_errors(wire)))
        self.assertEqual(decode(old,c),descriptive_decode(wire,c))
        self.assertTrue(all('field' in u for u in public['units'].values()))
        with self.assertRaises(CasePilotError):descriptive_decode(old,c)
    def test_selected_quote_is_reviewed_without_forbidden_prose_paraphrase(self):
        a,s,e,env,r=quoted_sample();out=full(a,s,e,env,r)
        self.assertEqual(out['verdict'],'accept');self.assertFalse(out['orphan_evidence_ids'])
        self.assertEqual(len(env['units']),3);self.assertTrue(env['units'][-1]['field'].startswith('claims.'))
        rendered=render_response(a,validate_answer(a,e),s['facts'],[])
        self.assertIn(a['claims'][0]['quote'],rendered);self.assertIn(citation_limit(e[0]),rendered)
        self.assertIn('بازبینی سند:',rendered)
    def test_missing_or_partial_quote_review_cannot_pass(self):
        a,s,e,env,r=quoted_sample()
        for failure in ('missing','partial','wrong_source','truncated_assertion'):
            bad=copy.deepcopy(r)
            if failure=='missing':bad['unit_reviews'].pop()
            elif failure=='partial':bad['unit_reviews'][-1]['support']='partial'
            elif failure=='wrong_source':bad['unit_reviews'][-1]['source_ids']=[]
            else:bad['unit_reviews'][-1]['meaning']['assertion_text']='Forms batch user input'
            with self.subTest(failure=failure):
                try:out=full(a,s,e,env,bad)
                except CasePilotError as exc:self.assertEqual(exc.code,'judge_contract_error')
                else:self.assertNotEqual(out['verdict'],'accept')
    def test_version_limit_is_server_derived_and_cannot_be_forged(self):
        a,s,e,env,r=quoted_sample();selected={'claims':[{'evidence_id':e[0]['id'],'quote_id':'q1'}]}
        resolved=resolve_claims(selected,{(e[0]['id'],'q1'):e[0]['text']},e)
        self.assertEqual(resolved['claims'][0]['version_limit'],citation_limit(e[0]))
        bad=copy.deepcopy(a);bad['claims'][0]['version_limit']='نسخهٔ جاری تأیید شد.'
        with self.assertRaises(CasePilotError):validate_answer(bad,e)
        e[0]['product_version']='1.2.0';e[0]['version_relation']='exact';self.assertEqual(citation_limit(e[0]),'')
        e[0]['version_relation']='mismatch';self.assertIn('متفاوت',citation_limit(e[0]))
    def test_nonfeature_schema_excludes_fabricated_feature_attribution(self):
        from casepilot.case_type import selection_schema,check_selection
        a=answer();a['feature_proposal']={k:'' for k in ('current_behavior','desired_behavior','user_need','constraints','acceptance_condition')};a['feature_proposal']['report_quotes']=[]
        s=state();s['investigation_plan']={'intent':'usage_question'}
        wire=selection_schema(s,{})
        self.assertEqual(wire['properties']['feature_proposal']['properties']['current_behavior']['enum'],[''])
        check_selection(a,s)
        a['feature_proposal']['current_behavior']='گزارش کاربر: ادعای ساخته‌شده.'
        with self.assertRaises(CasePilotError):check_selection(a,s)
    def test_conditional_request_does_not_assert_current_support_but_guarantee_does(self):
        import test_quality_v25 as prior
        a,s=prior.FeatureControls().proposal('GH16481')
        a['feature_proposal']['acceptance_condition']='درخواست: فقط هنگام فعال بودن گزینه، کشیدن باعث تغییر عرض می‌شود.'
        env,r=judge(a,s);self.assertEqual(full(a,s,[],env,r)['verdict'],'accept')
        a['feature_proposal']['acceptance_condition']='درخواست: این تغییر تضمین می‌کند علت قطعی خرابی حتماً رفع شود.'
        env,r=judge(a,s);self.assertNotEqual(full(a,s,[],env,r)['verdict'],'accept')
    def test_diagnostic_about_reported_api_is_not_a_source_dependent_cause(self):
        a=answer();s=state('The API returns an error; the traceback body was not supplied.')
        a['question']='پرسش: بدنهٔ خطای گزارش‌شدهٔ API را ارائه کنید.'
        env,r=judge(a,s);self.assertEqual(full(a,s,[],env,r)['verdict'],'accept')
        a['question']='پرسش: چون API علت قطعی خرابی است، بدنهٔ خطا را ارائه کنید.'
        env,r=judge(a,s);r['unit_reviews'][0].update(kind='technical_claim',premise=True)
        r['unit_reviews'][0]['meaning'].update(act='technical',assertion_text='API علت قطعی خرابی است')
        self.assertNotEqual(full(a,s,[],env,r)['verdict'],'accept')
    def test_new_protocol_frozen_disjoint_and_no_labels_in_inputs(self):
        rows=[]
        for split in ('dev','holdout'):
            inputs=json.loads((ROOT/'eval/quality_v28'/(split+'_inputs.json')).read_text())
            labels=json.loads((ROOT/'eval/quality_v28'/(split+'_labels.json')).read_text())
            self.assertEqual({x['expected_route'] for x in labels},{'bug','feature_request','usage_question'})
            self.assertTrue(all(set(x)=={'id','split','initial_message','initial_facts','initial_checks'} for x in inputs))
            rows.append({x['family'] for x in labels})
        self.assertFalse(rows[0]&rows[1])
    def test_new_campaign_budget_unknown_and_query_limits_are_durable(self):
        from evaluate_quality_v28 import QualityBudget
        auth={'campaign':'test-v28','hard_cap_usd':.03,'max_requests':3,'max_query_embeddings':1,
            'cost_before':{'charged_or_reserved_usd':0},'phase_limits':{'answers':{'requests':3,'usd':.03}}}
        with tempfile.TemporaryDirectory() as temp:
            b=QualityBudget(Path(temp)/'budget.sqlite3',auth,'answers')
            rid=b.reserve(.01,'text-embedding-3-small','embedding');b.uncertain(rid)
            b=QualityBudget(b.path,auth,'answers')
            with self.assertRaises(CasePilotError):b.reserve(.001,'text-embedding-3-small','embedding')
            with self.assertRaises(CasePilotError):b.reserve(.021,'gpt-4.1-mini','judge')
            with self.assertRaises(CasePilotError):b.reserve(.001,'different-model','chat')
            self.assertEqual(b.report()['requests'],1);self.assertAlmostEqual(b.report()['uncertain_reserved_usd'],.01)
    def test_recording_retriever_passes_real_query_and_results_without_injection(self):
        from evaluate_quality_v28 import ObservedHybrid
        from casepilot.hybrid import HybridRetriever
        result=[{'id':'actual-result'}];h=object.__new__(ObservedHybrid)
        with patch.object(HybridRetriever,'search',return_value=result) as search:
            self.assertIs(h.search('actual product query',k=8,version=None),result)
        search.assert_called_once_with('actual product query',k=8,version=None)
        self.assertEqual(h.observed_query,'actual product query')

if __name__=='__main__':unittest.main()
