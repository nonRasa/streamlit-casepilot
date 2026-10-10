"""کنترل‌های رفتاری دستیار؛ برچسب انسانی یا ارزیابی مدل تازه نیستند."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import CasePilotError
from casepilot.review_contract import draft_units,review_spans,unpack_bound_review,checked_review_v23
from casepilot.semantics import (UNKNOWN,prepare_feature,feature_context,semantic_schema,
    checked_semantic_review,recompose_semantic,source_adequacy)
from casepilot.roles import CRITERIA
from casepilot.routing import route_findings,handoff,render_handoff
from test_quality_v23 import answer

CASES=json.loads((ROOT/'artifacts/quality_v22/holdout/cases.json').read_text(encoding='utf-8'))

def state(report='Observed error after rerun. The helper body was not provided.',feature=False):
    return {'id':'control','revision':1,'facts':{},'messages':[{'role':'user','text':report}],
        'investigation_plan':{'intent':'feature_request' if feature else 'bug'}}

def judge(a,s,ev=(),generation=0):
    env=draft_units(a,s['id'],s['revision'],generation);spans=review_spans(s,ev,a['claims'])
    from casepilot.assertion_audit import candidates as assertion_candidates
    r={'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: برچسب ساختهٔ دستیار است.'} for k in CRITERIA},
       'draft_version':env['draft_version'],'unit_reviews':[],
       'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'توضیح: جزئیات تصمیم‌ساز هنوز ارائه نشده‌اند.'}}
    for u in env['units']:
        feature=u['field'].startswith('feature_proposal.');unknown=u['text']==UNKNOWN
        candidate=assertion_candidates(u.get('audited_text',u['text']),u['field'])
        current_report=u['field']=='feature_proposal.current_behavior' and u['text'].startswith('گزارش کاربر:')
        kind='technical_claim' if candidate else ('request_summary' if feature else ('question' if u['field']=='question' else 'next_step'))
        act='unknown' if unknown else ('technical' if candidate else ('observation' if current_report else ('request' if feature else ('diagnostic' if u['field']=='question' else 'procedure'))))
        entry={'unit_id':u['unit_id'],'kind':kind,
            'support':'unknown' if candidate or unknown else ('supported' if feature else 'unknown'),'source_ids':[],
            'message_ids':[spans['messages'][0]['span_id']] if feature and not unknown and not candidate else [],
            'premise':bool(candidate),'standalone':True,'reason':'توضیح: رابطهٔ موردی در کنترل توسعه مشخص شده است.',
            'version_dependent':False,'version_limit':'',
            'meaning':{'act':act,'assertion_text':u['text'] if candidate else '',
                'user_quote':spans['messages'][0]['text'][:200] if feature and not unknown and not candidate else '', 'depends_on':[]}}
        r['unit_reviews'].append(entry)
    return env,r

def technical(a,s,ev):
    env,r=judge(a,s,ev);e=next(e for e,u in zip(r['unit_reviews'],env['units']) if u['field']=='rationale')
    e.update(kind='technical_claim',support='supported',premise=True,source_ids=[review_spans(s,ev,a['claims'])['sources'][0]['span_id']])
    e['meaning'].update(act='technical',assertion_text=a['rationale'])
    return env,r

class SemanticControls(unittest.TestCase):
    def checked(self,a,s,ev=(),r=None,env=None):
        e,j=judge(a,s,ev);return checked_semantic_review(r or j,a,ev,s,env or e)

    def test_source_free_specific_observation_question_is_useful(self):
        a=answer();a['question']='پرسش: برای مشاهدهٔ خطای گزارش‌شده، کدام بخش لاگ هنوز ارائه نشده است؟'
        out=self.checked(a,state());self.assertEqual(out['verdict'],'accept');self.assertFalse(out['linked_evidence_ids'])

    def test_unsupported_cause_in_question_rejected(self):
        a=answer();a['question']='پرسش: آیا بازاجرا که علت قطعی خرابی است انجام شد؟';s=state();env,r=judge(a,s)
        r['unit_reviews'][0].update(premise=True)
        r['unit_reviews'][0]['meaning'].update(act='technical',assertion_text='علت قطعی خرابی است')
        self.assertNotEqual(self.checked(a,s,r=r,env=env)['verdict'],'accept')

    def test_request_label_cannot_hide_current_product_support(self):
        a=answer();a['rationale']='درخواست: محصول اکنون این رابط را پشتیبانی می‌کند.';s=state();env,r=judge(a,s)
        e=r['unit_reviews'][-1];e.update(kind='request_summary',support='supported',message_ids=[review_spans(s,[])['messages'][0]['span_id']])
        e['meaning'].update(act='request',user_quote=s['messages'][0]['text'])
        self.assertNotEqual(self.checked(a,s,r=r,env=env)['verdict'],'accept')

    def test_forged_attribution_phrase_is_contract_error(self):
        a=answer();s=state();env,r=judge(a,s);r['unit_reviews'][0]['meaning']['user_quote']='This never appeared'
        with self.assertRaises(CasePilotError):self.checked(a,s,r=r,env=env)

    def test_real_user_quote_does_not_verify_cause(self):
        a=answer();s=state('My guess: rerun definitely causes the error.');a['rationale']='گزارش: بازاجرا علت قطعی خرابی است.'
        env,r=judge(a,s);e=r['unit_reviews'][-1];e.update(kind='request_summary',support='supported',message_ids=[review_spans(s,[])['messages'][0]['span_id']])
        e['meaning'].update(act='request',user_quote=s['messages'][0]['text'])
        self.assertNotEqual(self.checked(a,s,r=r,env=env)['verdict'],'accept')

    def test_stale_wrong_namespace_and_foreign_case_witnesses_fail(self):
        a=answer();s=state();env,r=judge(a,s)
        for kind in ('draft','namespace','case'):
            bad=copy.deepcopy(r)
            if kind=='draft':bad['draft_version']='old'
            else:
                other=copy.deepcopy(s);other['id']='foreign'
                bad['unit_reviews'][0]['message_ids']=[env['units'][0]['unit_id'] if kind=='namespace' else review_spans(other,[])['messages'][0]['span_id']]
            with self.subTest(kind=kind),self.assertRaises(CasePilotError):self.checked(a,s,r=bad,env=env)

    def test_repeated_question_and_unknown_novelty_distinct(self):
        a=answer();s=state('The helper body is def helper(): return 1');env,r=judge(a,s)
        r['novelty'].update(status='repeated',relation='answers_requested_detail',message_ids=[review_spans(s,[])['messages'][0]['span_id']])
        self.assertNotEqual(self.checked(a,s,r=r,env=env)['verdict'],'accept')
        r['novelty']['relation']='context_only';out=self.checked(a,s,r=r,env=env)
        self.assertEqual(out['novelty']['effective_status'],'unknown')

    def test_code_import_and_real_dialog_do_not_support_rerun_cause(self):
        saved=json.loads((ROOT/'artifacts/quality_v24/live_comparison_01/ai_review_packets.json').read_text(encoding='utf-8'))['packets']
        p=next(p for p in saved if p['id']=='GH17011' and p['variant']=='revised')
        sources=[stage['source_spans'][0] for stage in p['result']['output']['pipeline'] if stage['stage']=='judge']
        for src in sources:
            a=answer();a['rationale']='توضیح: بازاجرا باعث از دست رفتن واکنش دیالوگ می‌شود.'
            ev=[{'id':'source','text':src['text'],'product_version':'1.64.0'}];a['claims']=[{'evidence_id':'source','quote':ev[0]['text']}]
            s=state();env,r=technical(a,s,ev);out=self.checked(a,s,ev,r,env)
            self.assertNotEqual(out['verdict'],'accept');self.assertEqual(out['unit_results'][-1]['model_semantic_support'],'supported')
            self.assertEqual(out['unit_results'][-1]['semantic_support'],'unknown')

    def test_real_glide_quote_does_not_prove_measurement_or_accessibility(self):
        ps=json.loads((ROOT/'artifacts/quality_v24/real_judge_failures.json').read_text(encoding='utf-8'))['packets']
        p=next(p for p in ps if p['id']=='GH17127');source=next(e for e in p['evidence'] if 'glide-data-grid' in e['text'])
        quote='`st.dataframe` provides additional functionality by using [glide-data-grid](https://github.com/glideapps/glide-data-grid) under the hood:'
        a=answer();a['rationale']='توضیح: اندازهٔ دکمه‌ها ۲۴ px و دسترس‌پذیری کافی است.';a['claims']=[{'evidence_id':source['id'],'quote':quote}]
        s=state();env,r=technical(a,s,[source]);self.assertNotEqual(self.checked(a,s,[source],r,env)['verdict'],'accept')

    def test_direct_documentation_and_syntax_code_positive(self):
        for text,claim in [('The button target width is 24px.','توضیح: عرض هدف دکمه ۲۴ px است.'),('import streamlit as st','توضیح: نمونه، واردکردن کتابخانه با نام `st` را نشان می‌دهد.')]:
            a=answer();a['rationale']=claim;ev=[{'id':'doc','text':text,'product_version':'1.64.0','version_relation':'exact'}];a['claims']=[{'evidence_id':'doc','quote':text}]
            s=state();s['facts']['streamlit_version']='1.64.0';env,r=technical(a,s,ev);self.assertEqual(self.checked(a,s,ev,r,env)['verdict'],'accept')

    def test_source_version_unknown_not_matching(self):
        a=answer();a['rationale']='توضیح: عرض هدف دکمه ۲۴ px است.';ev=[{'id':'doc','text':'The button target width is 24px.','product_version':None}];a['claims']=[{'evidence_id':'doc','quote':ev[0]['text']}]
        s=state();s['facts']['streamlit_version']='1.64.0';env,r=technical(a,s,ev);r['unit_reviews'][-1]['version_dependent']=True
        self.assertNotEqual(self.checked(a,s,ev,r,env)['verdict'],'accept')

    def test_rejected_prerequisite_removes_dependent_action(self):
        a=answer();s=state();env,r=judge(a,s);r['unit_reviews'][-1].update(premise=True)
        r['unit_reviews'][-1]['meaning'].update(act='technical',assertion_text=a['rationale'])
        r['unit_reviews'][1]['meaning']['depends_on']=[r['unit_reviews'][-1]['unit_id']]
        checked=self.checked(a,s,r=r,env=env)
        self.assertNotIn(r['unit_reviews'][1]['unit_id'],checked['valid_unit_ids'])
        self.assertIsNone(recompose_semantic(a,checked,env,s))

    def test_missing_required_semantic_field_rejected(self):
        a=answer();s=state();env,r=judge(a,s);r['unit_reviews'][0].pop('meaning')
        with self.assertRaises(CasePilotError):self.checked(a,s,r=r,env=env)

class FeatureControls(unittest.TestCase):
    def proposal(self,cid):
        report=next(c['initial_message'] for c in CASES if c['id']==cid);s=state(report,True);a=answer()
        if cid=='GH16481':
            f={'current_behavior':'گزارش کاربر: تب‌ها ظاهر خط زیرین دارند و راهکار شرطی کدنویسی بیشتری می‌خواهد.',
               'desired_behavior':'درخواست: سربرگ قرصی برای `st.tabs` با حفظ رفتار تب‌ها.',
               'user_need':'نیاز: نمایش جمع‌وجورتر برای فیلتر و داشبورد.',
               'constraints':'محدودیت درخواستی: رفتار و ظرف محتوا ثابت بماند و ظاهر پیش‌فرض حفظ شود.',
               'acceptance_condition':'پذیرش درخواستی: انتخاب حالت قرصی فقط ظاهر سربرگ را تغییر دهد.'}
        else:
            f={'current_behavior':'گزارش کاربر: زمان ذخیرهٔ کش را همراه نتیجه ذخیره می‌کند.',
               'desired_behavior':'درخواست: زمان آخرین ذخیرهٔ کش از تابع قابل دریافت باشد.',
               'user_need':'نیاز: تصمیم دربارهٔ تازگی داده و نمایش زمان آخرین به‌روزرسانی.',
               'constraints':'','acceptance_condition':'پذیرش درخواستی: دریافت زمان ذخیره به صورت مهر زمانی.'}
        f['report_quotes']=[report[report.index('### Summary'):report.index('### Why?')]]
        a.update(decision='escalate',question='',feature_proposal=f,next_step='اقدام: نگه‌دارنده دربارهٔ رفتار درخواستی تصمیم طراحی بگیرد و شرط پذیرش را بازبینی کند.')
        return prepare_feature(a,s),s

    def test_two_real_requests_keep_faithful_useful_content(self):
        for cid in ('GH16481','GH17133'):
            a,s=self.proposal(cid);env,r=judge(a,s);out=checked_semantic_review(r,a,[],s,env)
            self.assertEqual(out['verdict'],'accept');self.assertEqual(route_findings(a,s),[])
            packet=handoff(s,[],answer=a);text=render_handoff(packet)
            self.assertIn(a['feature_proposal']['desired_behavior'],text)
            self.assertIn(a['feature_proposal']['user_need'],text)
            self.assertIn('تصمیم طراحی',packet['maintainer_action'])
            if cid=='GH17133':self.assertEqual(a['feature_proposal']['constraints'],UNKNOWN)

    def test_blank_sections_are_not_known_constraints(self):
        sections=feature_context(state('### Constraints\n\n### Summary\nNeed timestamps\n### Additional Context\n_No response_',True))
        self.assertEqual([s['heading'] for s in sections],['Summary'])

    def test_missing_and_rejected_detail_can_be_preserved_as_unknown(self):
        a,s=self.proposal('GH16481');env,r=judge(a,s)
        rejected=next(e for e,u in zip(r['unit_reviews'],env['units']) if u['field']=='feature_proposal.constraints');rejected['support']='partial'
        r['assessments']['next_step_usefulness']['score']=0
        out=checked_semantic_review(r,a,[],s,env);combined=recompose_semantic(a,out,env,s)
        self.assertEqual(combined['feature_proposal']['desired_behavior'],a['feature_proposal']['desired_behavior'])
        self.assertEqual(combined['feature_proposal']['constraints'],UNKNOWN)
        self.assertNotIn('در گزارش تصریح نشده',combined['feature_proposal']['constraints'])
        new_env,new_review=judge(combined,s,generation=1)
        with self.assertRaises(CasePilotError):checked_semantic_review(r,combined,[],s,new_env)
        self.assertEqual(checked_semantic_review(new_review,combined,[],s,new_env)['verdict'],'accept')
        new_review['assessments']['relevance']['score']=0
        self.assertNotEqual(checked_semantic_review(new_review,combined,[],s,new_env)['verdict'],'accept')

    def test_unfaithful_desired_behavior_cannot_be_preserved(self):
        a,s=self.proposal('GH16481');env,r=judge(a,s)
        next(e for e,u in zip(r['unit_reviews'],env['units']) if u['field']=='feature_proposal.desired_behavior')['support']='contradicted'
        out=checked_semantic_review(r,a,[],s,env);self.assertIsNone(recompose_semantic(a,out,env,s))

    def test_implementation_demand_is_a_defect_even_with_five_fields(self):
        a,s=self.proposal('GH16481');a['next_step']='اقدام: لازم است کد پیاده‌سازی ویژگی پیشنهادی را ارائه کنید.'
        self.assertTrue(route_findings(a,s))

    def test_pipeline_unknown_recomposition_rechecked_once_and_second_rejection_blocks_delivery(self):
        import tempfile
        from casepilot.model import ReplayClient
        from casepilot.accounting import Budget
        from casepilot.agent import Agent
        from casepilot.store import Store
        from test_architecture_v2 import TinyHybrid
        from review_helpers import wire_review,bind_fixture_report_quotes
        a,s=self.proposal('GH16481')
        a['diagnostic']={'action':'','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''}
        for reject in (False,True):
            with self.subTest(reject=reject),tempfile.TemporaryDirectory() as temp:
                class Client(ReplayClient):
                    mode='live'
                    def __init__(self):
                        super().__init__();self.budget=Budget(Path(temp)/'budget.sqlite3');self.usage_history=[];self.max_output=1600;self.drafts=[];self.active_answer=None
                    def generate(self,*args):
                        self.calls+=1;self.last_usage={'provider_requests':0}
                        self.active_answer=bind_fixture_report_quotes(a,args[0]);return copy.deepcopy(self.active_answer)
                    def structured(self,role,prompt,packet,schema,max_tokens):
                        self.calls+=1;self.last_usage={'provider_requests':0}
                        if role=='extract':return {'facts':[],'completed_checks':[],'ambiguities':[],'experiment_events':[],
                            'investigation':{'intent':'feature_request','problem_summary':'requested visual variant','known_report_spans':[],
                                'missing_detail':'','new_condition':'','suggested_question':'','acceptance_condition':''}}
                        if role=='rerank':return {'ordered_ids':[e['id'] for e in packet['candidates']]}
                        if role=='judge':
                            env=packet['draft'];self.drafts.append(env['draft_version']);draft=copy.deepcopy(self.active_answer)
                            selected_texts={u['text'] for u in env['units'] if u['field'].startswith('feature_proposal.report_quotes.')}
                            draft['feature_proposal']['report_quotes']=[q for q in draft['feature_proposal']['report_quotes'] if q['quote'] in selected_texts]
                            for u in env['units']:
                                if u['field'].startswith('feature_proposal.') and not u['field'].startswith('feature_proposal.report_quotes.'):
                                    draft['feature_proposal'][u['field'].split('.')[1]]=u['text']
                                elif u['field'] in ('rationale','next_step','question'):draft[u['field']]=u['text']
                            _,r=judge(draft,s,generation=env['generation']);r['draft_version']=env['draft_version']
                            for entry,u in zip(r['unit_reviews'],env['units']):entry['unit_id']=u['unit_id']
                            if env['generation']==0:
                                next(e for e,u in zip(r['unit_reviews'],env['units']) if u['field']=='feature_proposal.constraints')['support']='partial'
                            elif reject:r['assessments']['relevance']['score']=0
                            return wire_review(r,packet)
                        raise AssertionError(role)
                client=Client();store=Store(Path(temp)/'store.sqlite3')
                output=Agent(store,client=client,hybrid=TinyHybrid()).turn(s['id'],s['messages'][0]['text'],'unique')
                self.assertEqual(len(client.drafts),2);self.assertNotEqual(*client.drafts);self.assertEqual(output['repair_count'],1)
                self.assertFalse(store.get(s['id'])['comments']);self.assertLessEqual(output['model_calls'],8)
                if reject:
                    self.assertEqual(output['validation_error'],'judge_rejected');self.assertFalse(output['summary']['handoff']['feature'])
                else:
                    self.assertIsNone(output['validation_error']);self.assertEqual(output['summary']['handoff']['feature']['constraints'],UNKNOWN)
                    self.assertTrue(output['summary']['handoff']['feature_origins'])

if __name__=='__main__':unittest.main()
