"""کنترل‌های تشخیص، ظرفیت و رفتار؛ بدل توسعه، بدون هزینهٔ مدل."""
import copy,io,json,os,socket,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError,URLError
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import CasePilotError,read_json,canonical
from casepilot.model import MetisClient
from casepilot.compact_review import contract,encode_fixture,decode,schema,fragments
from casepilot.review_contract import draft_units,review_spans
from casepilot.semantics import checked_semantic_review,recompose_semantic
from casepilot.case_type import case_kind,selection_schema,check_selection
import test_quality_v25 as v25
state,judge,technical,CASES=v25.state,v25.judge,v25.technical,v25.CASES
from test_quality_v23 import answer

class Response:
    def __init__(self,raw,status=200): self.data=raw if isinstance(raw,bytes) else json.dumps(raw).encode();self.status=status
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return self.data

class DiagnosticsControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        env=patch.dict(os.environ,{'METIS_API_KEY':'test-secret-credential','METIS_MODEL':'test-model',
            'METIS_BASE_URL':'https://api.metisai.ir/openai/v1','CASEPILOT_INPUT_USD_PER_MILLION':'1',
            'CASEPILOT_OUTPUT_USD_PER_MILLION':'2','CASEPILOT_BUDGET_USD':'5'})
        env.start();self.addCleanup(env.stop)
        self.client=MetisClient(self.path/'budget.sqlite3');self.client.cache=self.path/'cache';self.client.cache.mkdir()
        self.client.diagnostics=self.path/'diagnostics'
    def invoke(self,response=None,error=None):
        with patch('casepilot.model.build_opener') as op:
            op.return_value.open.return_value=response;op.return_value.open.side_effect=error
            try: out=self.client.structured('judge','test',{}, {'type':'object'},1600)
            except CasePilotError as exc: out=exc.code
            self.assertEqual(op.return_value.open.call_count,1)
        return out
    def envelope(self,content='{}',finish='stop',usage=True):
        raw={'id':'request-safe','choices':[{'message':{'content':content},'finish_reason':finish}]}
        if usage: raw['usage']={'prompt_tokens':100,'completion_tokens':50}
        return raw
    def test_success_records_metadata_and_settles_once(self):
        self.assertEqual(self.invoke(Response(self.envelope())),{})
        d=self.client.last_usage['diagnostic'];self.assertEqual(d['finish_reason'],'stop');self.assertEqual(d['http_status'],200)
        self.assertEqual(d['role'],'judge');self.assertEqual(d['requested_max_output_tokens'],min(1600,self.client.max_output))
        self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)
        self.assertEqual(len(self.client.usage_history),1)
    def test_timeout_and_connection_separate_unknown_reserves(self):
        for error,code in [(socket.timeout('private'),'provider_timeout'),(URLError('private'),'provider_connection_error')]:
            with self.subTest(code=code): self.assertEqual(self.invoke(error=error),code)
        self.assertEqual(self.client.budget.report()['requests'],2)
        self.assertGreater(self.client.budget.report()['uncertain_reserved_usd'],0)
    def test_reported_truncation_rejects_even_parseable_json(self):
        self.assertEqual(self.invoke(Response(self.envelope(finish='length'))),'model_output_incomplete')
        self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)
        self.assertEqual(self.client.last_usage['diagnostic']['finish_reason'],'length')
    def test_invalid_content_with_valid_usage_retains_exact_cost(self):
        self.assertEqual(self.invoke(Response(self.envelope('{broken'))),'model_output_invalid')
        self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)
        self.assertEqual(self.client.budget.report()['uncertain_reserved_usd'],0)
    def test_invalid_envelope_does_not_invent_usage(self):
        self.assertEqual(self.invoke(Response(b'{bad')),'provider_response_invalid')
        self.assertIsNone(self.client.last_usage['diagnostic']['reported_usage'])
        self.assertGreater(self.client.budget.report()['uncertain_reserved_usd'],0)
    def test_missing_metadata_explicitly_unknown(self):
        raw=self.envelope(usage=False);raw.pop('id');raw['choices'][0].pop('finish_reason')
        self.assertEqual(self.invoke(Response(raw,status=None)),{})
        d=self.client.last_usage['diagnostic']
        for k in ('provider_request_id','reported_usage','http_status','finish_reason'):self.assertIsNone(d[k])
        self.assertTrue(self.client.last_usage['usage_unknown'])
    def test_token_count_alone_is_not_truncation_proof(self):
        raw=self.envelope();raw['choices'][0].pop('finish_reason');raw['usage']['completion_tokens']=self.client.max_output
        self.assertEqual(self.invoke(Response(raw)),{})
        self.assertIsNone(self.client.last_usage['diagnostic']['finish_reason'])
    def test_http_status_and_usage_preserved_without_retry(self):
        error=HTTPError('https://api.metisai.ir',429,'private',{},io.BytesIO(json.dumps(self.envelope()).encode()))
        self.assertEqual(self.invoke(error=error),'provider_http_error')
        self.assertEqual(self.client.last_usage['diagnostic']['http_status'],429)
        self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)
    def test_sample_is_bounded_and_sanitized_before_truncation(self):
        content='Authorization: Bearer test-secret-credential\npassword=private-password\n'+('x'*3000)+'tpsg-testlongcredential123456789'
        self.invoke(Response(self.envelope(content)))
        saved=read_json(Path(self.client.last_usage['diagnostic']['diagnostic_file']));text=canonical(saved)
        for secret in ('test-secret-credential','private-password','tpsg-testlongcredential123456789'):self.assertNotIn(secret,text)
        self.assertLessEqual(len(saved['sample']),2000);self.assertTrue(saved['sample_truncated'])
    def test_diagnostic_storage_failure_keeps_processing_error_and_cost(self):
        with patch('casepilot.model_diagnostics.write_json',side_effect=OSError):
            self.assertEqual(self.invoke(Response(self.envelope('{bad'))),'model_output_invalid')
        self.assertIsNone(self.client.last_usage['diagnostic']['diagnostic_file'])
        self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)

class CompactControls(unittest.TestCase):
    def setup_review(self,a=None,s=None,ev=()):
        a=a or answer();s=s or state();env,r=judge(a,s,ev);c=contract(env,review_spans(s,ev,a['claims']))
        return a,s,env,r,c,encode_fixture(r,c)
    def check(self,a,s,env,c,wire,ev=()):return checked_semantic_review(decode(wire,c),a,ev,s,env)
    def test_low_eight_and_maximum_units_full_coverage(self):
        for count in (3,8,11):
            a=answer()
            if count>=8:a['feature_proposal']={k:'درخواست: رفتار مشخص کاربر.' for k in ('current_behavior','desired_behavior','user_need','constraints','acceptance_condition')}
            if count==11:a['hypotheses']=['فرضیه: نامعلوم.']*3
            _,_,env,_,c,wire=self.setup_review(a)
            self.assertEqual(len(env['units']),count);self.assertEqual(len(decode(wire,c)['unit_reviews']),count)
            self.assertEqual(set(schema(c)['properties']['u']['required']),set(c['units']))
    def test_slices_cover_entire_text_without_cutting_tail(self):
        text=('ادعا: متن بلند با شرط و محدودیت؛\n'*90)+'انتهای مهم'
        self.assertEqual(''.join(text[s:e] for s,e in fragments(text)),text)
    def test_missing_stale_wrong_namespace_and_foreign_binding_stop(self):
        a,s,env,r,c,wire=self.setup_review()
        for kind in ('missing','stale','namespace','foreign','dependency','phrase','extra'):
            bad=copy.deepcopy(wire)
            if kind=='missing':bad['u'].pop('u0')
            if kind=='stale':bad['b']='old'
            if kind=='namespace':bad['u']['u0']['e']=['m0']
            if kind=='foreign':
                other=copy.deepcopy(s);other['id']='different';bad['b']=contract(env,review_spans(other,[]))['binding']
            if kind=='dependency':bad['u']['u0']['d']=['u0']
            if kind=='phrase':bad['u']['u0']['p']=[999]
            if kind=='extra':bad['u']['u99']=copy.deepcopy(bad['u']['u0'])
            with self.subTest(kind=kind),self.assertRaises(CasePilotError):decode(bad,c)
    def test_positive_question_and_real_feature_are_not_rejected(self):
        a,s,env,r,c,wire=self.setup_review();self.assertEqual(self.check(a,s,env,c,wire)['verdict'],'accept')
        a,s=v25.FeatureControls().proposal('GH16481');a,s,env,r,c,wire=self.setup_review(a,s)
        self.assertEqual(self.check(a,s,env,c,wire)['verdict'],'accept')
    def test_direct_source_passes_code_only_cause_still_fails(self):
        for text,claim,expected in [('The button target width is 24px.','توضیح: عرض هدف دکمه ۲۴ px است.','accept'),
            ('import streamlit as st','توضیح: بازاجرا باعث از دست رفتن واکنش دیالوگ می‌شود.','repair')]:
            a=answer();s=state();a['rationale']=claim;ev=[{'id':'doc','text':text,'product_version':'1.64.0'}];a['claims']=[{'evidence_id':'doc','quote':text}]
            env,r=technical(a,s,ev);c=contract(env,review_spans(s,ev,a['claims']))
            self.assertEqual(self.check(a,s,env,c,encode_fixture(r,c),ev)['verdict'],expected)
    def test_unsupported_premise_and_false_attribution_still_fail(self):
        a,s,env,r,c,wire=self.setup_review()
        bad=copy.deepcopy(wire);bad['u']['u0'].update(a=4,p=[0]);self.assertNotEqual(self.check(a,s,env,c,bad)['verdict'],'accept')
        bad=copy.deepcopy(wire);bad['u']['u2'].update(k=4,a=1,s=0,m=['m0']);self.assertNotEqual(self.check(a,s,env,c,bad)['verdict'],'accept')
    def test_rejected_prerequisite_removes_dependent_unit(self):
        a,s,env,r,c,wire=self.setup_review();wire['u']['u0'].update(a=4,p=[0]);wire['u']['u1']['d']=['u0']
        out=self.check(a,s,env,c,wire);self.assertNotIn(c['units']['u1']['unit_id'],out['valid_unit_ids'])
    def test_second_rejection_does_not_restore_bad_feature_constraint(self):
        a,s=v25.FeatureControls().proposal('GH16481');a,s,env,r,c,w=self.setup_review(a,s)
        target=next(k for k,u in c['units'].items() if u['field']=='feature_proposal.constraints');w['u'][target]['s']=1
        out=self.check(a,s,env,c,w);combined=recompose_semantic(a,out,env,s);self.assertIsNotNone(combined)
        a2,s2,e2,r2,c2,w2=self.setup_review(combined,s);w2['v']='escalate';w2['a'][3]=0;w2['r'][3]='فایده: این اقدام تصمیم‌ساز نیست.'
        self.assertNotEqual(self.check(a2,s2,e2,c2,w2)['verdict'],'accept');self.assertNotEqual(combined['feature_proposal']['constraints'],a['feature_proposal']['constraints'])
    def test_historical_semantic_reader_unchanged(self):
        a,s,env,r,c,w=self.setup_review();self.assertEqual(checked_semantic_review(r,a,[],s,env)['verdict'],'accept')

class CaseTypeControls(unittest.TestCase):
    def test_bug_schema_forbids_feature_but_keeps_expected_report(self):
        case=next(c for c in CASES if c['id']=='GH17011');s=state(case['initial_message']);before=copy.deepcopy(s)
        props=selection_schema(s)['properties']['feature_proposal']['properties']
        self.assertEqual(props['desired_behavior']['enum'],['']);self.assertEqual(props['report_quotes']['maxItems'],0)
        self.assertEqual(s,before);self.assertIn('The dialog to still be responsive',s['messages'][0]['text'])
        for version in ('1.64.0','1.57.0','1.58.0'):self.assertIn(version,s['messages'][0]['text'])
    def test_bug_violation_fails_without_silently_deleting(self):
        a,s=v25.FeatureControls().proposal('GH16481');s=state('Expected behavior: the dialog responds.');before=copy.deepcopy(a)
        with self.assertRaises(CasePilotError) as exc:check_selection(a,s)
        self.assertEqual(exc.exception.code,'case_type_contract_error');self.assertEqual(a,before)
    def test_feature_and_ambiguous_types_preserve_candidates(self):
        a,s=v25.FeatureControls().proposal('GH16481')
        for kind in ('feature_request','unknown','mixed'):
            s['investigation_plan']['intent']=kind;self.assertEqual(check_selection(a,s),a)
            self.assertNotIn('enum',selection_schema(s)['properties']['feature_proposal']['properties']['desired_behavior'])
    def test_explicit_conflict_becomes_mixed_and_no_plan_unknown(self):
        self.assertEqual(case_kind(state('Feature request: add an option.')),'mixed')
        from casepilot.routing import intent
        self.assertEqual(intent(state('Feature request: add an option.')),'mixed')
        self.assertEqual(case_kind({'messages':[{'text':'unclear'}]}),'unknown')
    def test_model_uses_typed_contract_and_enforces_provider_response(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);p=Path(temp.name)
        with patch.dict(os.environ,{'METIS_API_KEY':'test-key','METIS_MODEL':'test-model','METIS_BASE_URL':'https://api.metisai.ir/openai/v1','CASEPILOT_INPUT_USD_PER_MILLION':'1','CASEPILOT_OUTPUT_USD_PER_MILLION':'2','CASEPILOT_BUDGET_USD':'5'}):
            client=MetisClient(p/'budget.sqlite3');client.turn_scope={'deadline':time.monotonic()+180,'calls_before':0,'cost_before':0,'max_calls':8,'cap_usd':.04}
            a,s=v25.FeatureControls().proposal('GH16481');s=state();s['checks']=[]
            with patch.object(client,'_request',return_value=a) as request:
                with self.assertRaises(CasePilotError):client.generate(s,[])
                payload=request.call_args.args[0];self.assertEqual(json.loads(payload['messages'][1]['content'])['case_type'],'bug')
                self.assertEqual(payload['response_format']['json_schema']['schema']['properties']['feature_proposal']['properties']['desired_behavior']['enum'],[''])

if __name__=='__main__':unittest.main()
