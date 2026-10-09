import copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.agent import Agent, extract_facts
from casepilot.common import CasePilotError
from casepilot.model import ReplayClient
from casepilot.roles import CRITERIA, checked_extraction, deterministic_findings
from casepilot.review_contract import draft_units, checked_review
from casepilot.memory import diagnostic_findings, active_experiments
from casepilot.store import Store
from casepilot.evidence import relation, temporal_status
from casepilot.routing import handoff, render_handoff
from test_architecture_v2 import TinyHybrid, row

def answer(decision='answer'):
    return {'decision':decision,'claims':[],'question':'پرسش: نسخهٔ دقیق محیط چیست؟' if decision=='ask' else '',
        'next_step':'بررسی: رفتار ستون را با شاهد مقایسه کنید.','rationale':'توضیح: شاهد دربارهٔ نوع ستون است.','hypotheses':[]}

def review(a,e,env):
    return {'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: آزمون قرارداد است.'} for k in CRITERIA},
        'draft_version':env['draft_version'],
        'unit_reviews':[{'unit_id':u['unit_id'],'kind':'question' if u['field']=='question' else ('next_step' if u['field']=='next_step' else 'technical_claim'),
            'support':'unknown' if u['field']=='question' else 'supported',
            'links':[] if u['field']=='question' else [{'evidence_id':e[0]['id'],'quote':e[0]['text']}],
            'reason':'توضیح: پشتیبانی آزمایشی.','version_dependent':False,'version_limit':''} for u in env['units']],
        'novelty':{'new':True,'useful':True,'reason':'پرسش: نسخه معلوم نیست.','already_supplied_quote':''}}

def diagnostic(action='disable_rerun',conditions=None):
    return {'action':action,'conditions':conditions or [],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''}

def event(action='disable rerun',status='failed',quote='I disabled rerun; memory remained.',conditions=None,supersedes=''):
    return {'action':action,'conditions':conditions or [],'status':status,'result':quote,'quote':quote,'supersedes':supersedes}

class JudgeContractTests(unittest.TestCase):
    def setUp(self):
        self.a=answer(); self.e=[row()]; self.a['claims']=[{'evidence_id':self.e[0]['id'],'quote':self.e[0]['text']}]
        self.state={'facts':{},'messages':[{'text':'Streamlit version:\nPython version:'}]}
        self.env=draft_units(self.a,'A',1,0); self.r=review(self.a,self.e,self.env)
    def check(self,r=None,a=None,env=None):
        return checked_review(r or self.r,a or self.a,self.e,self.state,env or self.env)
    def test_persian_answer_binds_by_id_not_english_quote(self):
        self.assertEqual(self.check()['verdict'],'accept')
        self.assertNotIn('statement',self.r['unit_reviews'][0])
    def test_unknown_unit_or_duplicate_cannot_be_accepted(self):
        for mode in ('unknown','duplicate'):
            r=copy.deepcopy(self.r); r['unit_reviews'][-1]['unit_id']='u_unknown' if mode=='unknown' else r['unit_reviews'][0]['unit_id']
            with self.subTest(mode=mode),self.assertRaises(CasePilotError) as err: self.check(r)
            self.assertEqual(err.exception.code,'judge_contract_error')
    def test_source_text_cannot_replace_unit_id(self):
        self.r['unit_reviews'][0]['unit_id']=self.e[0]['text']
        with self.assertRaises(CasePilotError): self.check()
    def test_same_text_repair_and_other_case_expire_old_ids(self):
        for env in (draft_units(self.a,'A',1,1),draft_units(self.a,'B',1,0),draft_units(self.a,'A',2,0)):
            with self.subTest(version=env['draft_version']),self.assertRaises(CasePilotError): self.check(env=env)
    def test_modified_draft_expires_review(self):
        a=copy.deepcopy(self.a); a['rationale']='توضیح: ادعای تغییرکرده.'
        with self.assertRaises(CasePilotError): self.check(a=a,env=draft_units(a,'A',1,0))
        with self.assertRaises(CasePilotError): self.check(a=a)
    def test_fabricated_quote_or_source_is_contract_failure(self):
        for key,value in [('quote','A fabricated quote longer than twenty characters.'),('evidence_id','foreign')]:
            r=copy.deepcopy(self.r); r['unit_reviews'][0]['links'][0][key]=value
            with self.subTest(key=key),self.assertRaises(CasePilotError) as err: self.check(r)
            self.assertEqual(err.exception.code,'judge_contract_error')
    def test_unsupported_status_is_answer_defect_not_contract_corruption(self):
        for status in ('partial','contradicted','unknown'):
            r=copy.deepcopy(self.r); r['unit_reviews'][-1]['support']=status
            out=self.check(r); self.assertEqual(out['verdict'],'repair'); self.assertEqual(out['failure_kind'],'answer_quality')
    def test_blank_headings_do_not_prevent_citation_free_question(self):
        a=answer('ask'); a['rationale']='توضیح: مقدار نسخه در گزارش خالی است.'
        env=draft_units(a,'A',1,0); r=review(a,self.e,env)
        for u in r['unit_reviews']: u.update(kind='question' if u['kind']=='question' else 'next_step',support='unknown',links=[])
        self.assertEqual(self.check(r,a,env)['verdict'],'accept')
    def test_every_full_field_is_preserved_in_units(self):
        a=answer('ask'); a['rationale']='توضیح: جملهٔ اول.\n\nادعا: جملهٔ دوم نیز باید بررسی شود.'
        env=draft_units(a,'A',1,0)
        self.assertEqual(next(u['text'] for u in env['units'] if u['field']=='rationale'),a['rationale'])
    def test_unknown_version_cannot_support_unqualified_version_claim(self):
        self.r['unit_reviews'][-1]['version_dependent']=True
        self.assertEqual(self.check()['verdict'],'repair')
    def test_visible_unknown_version_limitation_is_required(self):
        self.a['rationale']='محدودیت: سازگاری نسخهٔ منبع نامعلوم است.'
        self.env=draft_units(self.a,'A',1,0); self.r=review(self.a,self.e,self.env)
        self.r['unit_reviews'][-1].update(version_dependent=True,version_limit=self.a['rationale'])
        self.assertEqual(self.check()['verdict'],'accept')
    def test_forged_repetition_quote_is_contract_failure(self):
        self.r['novelty']['already_supplied_quote']='a nonexistent result'
        with self.assertRaises(CasePilotError): self.check()
    def test_blank_environment_heading_is_invalid_repetition_proof(self):
        self.r['novelty']['already_supplied_quote']='Streamlit version:'
        with self.assertRaises(CasePilotError) as err: self.check()
        self.assertEqual(err.exception.code,'judge_contract_error')

class ExperimentMemoryTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'tracker.sqlite3'; self.store=Store(self.path)
    def tearDown(self): self.tmp.cleanup()
    def test_paraphrased_repeat_is_blocked_after_restart(self):
        e=event(); self.store.update('A',e['quote'],experiment_events=[e])
        state=Store(self.path).get('A'); a=answer('ask'); a['diagnostic']=diagnostic('بدون بازاجرا')
        self.assertTrue(diagnostic_findings(a,state)); self.assertEqual(state['experiments'][0]['status'],'failed')
        self.assertEqual(state['experiments'][0]['provenance']['message_index'],0)
    def test_proposed_is_not_performed(self):
        e=event(status='proposed'); state=self.store.update('A',e['quote'],experiment_events=[e])
        a=answer('ask'); a['diagnostic']=diagnostic()
        self.assertFalse(diagnostic_findings(a,state))
    def test_unknown_result_still_means_test_was_performed(self):
        e=event(status='performed_unknown'); state=self.store.update('A',e['quote'],experiment_events=[e])
        a=answer('ask'); a['diagnostic']=diagnostic()
        self.assertTrue(diagnostic_findings(a,state))
    def test_changed_conditions_and_value_of_repeat_must_be_visible(self):
        q='I tried a file of 600MB; memory remained.'
        e=event('upload_memory',quote=q,conditions=[{'dimension':'input_size','value':'600MB','quote':q}])
        state=self.store.update('A',q,experiment_events=[e]); a=answer('ask')
        a['diagnostic']=diagnostic('upload_memory',[{'dimension':'input_size','value':'10MB'}])
        self.assertTrue(diagnostic_findings(a,state))
        a['diagnostic'].update(repeat_of=state['experiments'][0]['id'],changed_condition='input_size',repeat_reason='تفکیک: اثر اندازهٔ فایل سنجیده می‌شود.')
        a['next_step']+=a['diagnostic']['repeat_reason']
        self.assertFalse(diagnostic_findings(a,state))
        a['diagnostic']['conditions']=[]; self.assertTrue(diagnostic_findings(a,state))
    def test_correction_preserves_old_event_and_temporal_order(self):
        e=event(); first=self.store.update('A',e['quote'],experiment_events=[e]); eid=first['experiments'][0]['id']
        correction=event(status='correction',quote='Correction: memory was released.',supersedes=eid)
        self.store.update('A',correction['quote'],experiment_events=[correction])
        state=Store(self.path).get('A'); self.assertEqual(len(state['experiments']),2)
        self.assertEqual(active_experiments(state)[0]['supersedes'],eid)
        self.assertEqual(state['experiments'][1]['sequence'],2)
    def test_other_case_event_cannot_be_corrected_or_mixed(self):
        e=event(); a=self.store.update('A',e['quote'],experiment_events=[e])
        self.store.update('B','Other case')
        correction=event(status='correction',supersedes=a['experiments'][0]['id'])
        with self.assertRaises(CasePilotError): self.store.update('B',correction['quote'],experiment_events=[correction])
        self.assertFalse(Store(self.path).get('B')['experiments'])
    def test_user_retracts_execution_without_erasing_prior_report(self):
        e=event(); first=self.store.update('A',e['quote'],experiment_events=[e])
        corrected=event(status='not_performed',quote='Correction: I never actually ran it.',supersedes=first['experiments'][0]['id'])
        state=self.store.update('A',corrected['quote'],experiment_events=[corrected])
        a=answer('ask'); a['diagnostic']=diagnostic()
        self.assertFalse(diagnostic_findings(a,state)); self.assertEqual(len(state['experiments']),2)
    def test_invented_event_or_condition_does_not_mutate_case(self):
        self.store.update('A','Original report'); e=event()
        with self.assertRaises(CasePilotError): self.store.update('A','Other text',experiment_events=[e])
        self.assertEqual(self.store.get('A')['revision'],1)
        e['conditions']=[{'dimension':'browser','value':'Firefox','quote':e['quote']}]
        with self.assertRaises(CasePilotError): self.store.update('A',e['quote'],experiment_events=[e])
    def test_legacy_string_check_migrates_without_inventing_execution_conditions(self):
        self.store.update('A','Old report',checks=['Tried a test'])
        with self.store.connect() as db:
            old=json.loads(db.execute('SELECT state FROM cases WHERE id=?',('A',)).fetchone()[0]); old.pop('memory_version'); old.pop('experiments')
            db.execute('UPDATE cases SET state=? WHERE id=?',(json.dumps(old),'A'))
        state=Store(self.path).get('A'); self.assertEqual(state['memory_version'],3); self.assertFalse(state['experiments'][0]['equivalence_known'])
        self.store.update('A','Followup'); self.assertEqual(len(Store(self.path).get('A')['experiments']),1)
    def test_proposal_memory_does_not_grant_tracker_effect(self):
        state=self.store.update('A','Report'); self.store.remember_proposed_check('A',state['revision'],diagnostic(),'آزمایش پیشنهادی')
        self.assertEqual(Store(self.path).get('A')['experiments'][0]['status'],'proposed'); self.assertFalse(self.store.get('A')['comments'])

class VersionAndRouteTests(unittest.TestCase):
    def cases(self): return json.loads((ROOT/'eval/quality_cases.json').read_text(encoding='utf-8'))
    def test_GH13189_complete_nightly_is_preserved(self):
        c=next(c for c in self.cases() if c['id']=='GH13189')
        self.assertEqual(extract_facts(c['initial_message'])['streamlit_version'],'1.51.1.dev20251130')
        self.assertEqual(relation({'product_version':'1.51.1'},'1.51.1.dev20251130'),'mismatch')
    def test_prerelease_and_local_build_are_not_stable(self):
        for v in ('1.52.0rc2','1.52.0.dev20261001+build.8','1.52.0b1'):
            self.assertEqual(extract_facts('Streamlit version: '+v)['streamlit_version'],v)
            self.assertEqual(relation({'product_version':'1.52.0'},v),'mismatch')
    def test_model_cannot_truncate_nightly_version(self):
        quote='Streamlit version: 1.51.1.dev20251130'
        raw={'facts':[{'key':'streamlit_version','value':'1.51.1','quote':quote}],'completed_checks':[],'ambiguities':[]}
        self.assertNotIn('streamlit_version',checked_extraction(raw,quote)[0])
    def test_multiple_environment_versions_remain_ambiguous(self):
        self.assertNotIn('streamlit_version',extract_facts('Streamlit version: 1.52.1 and 1.52.0'))
    def test_recorded_development_contract_controls(self):
        fixture=json.loads((ROOT/'artifacts/quality_v22/development/judge_controls.json').read_text(encoding='utf-8'))
        for control in fixture['controls']:
            with self.subTest(control=control['name']):
                if control['expected']=='judge_contract_error':
                    with self.assertRaises(CasePilotError) as err: checked_review(control['result'],fixture['answer'],fixture['evidence'],{'facts':{},'messages':[]},fixture['draft'])
                    self.assertEqual(err.exception.code,control['expected'])
                else:
                    reviewed=checked_review(control['result'],fixture['answer'],fixture['evidence'],{'facts':{},'messages':[]},fixture['draft'])
                    self.assertEqual(reviewed['verdict'],control['expected'])
    def test_GH9218_headings_stay_unknown(self):
        c=next(c for c in self.cases() if c['id']=='GH9218'); self.assertNotIn('streamlit_version',extract_facts(c['initial_message']))
        raw={'facts':[{'key':'streamlit_version','value':'Streamlit version:','quote':'Streamlit version:'}],'completed_checks':[],'ambiguities':[]}
        self.assertNotIn('streamlit_version',checked_extraction(raw,c['initial_message'])[0])
    def test_GH12607_actual_report_completed_experiment_is_not_new(self):
        c=next(c for c in self.cases() if c['id']=='GH12607')
        quote='If I set the clear_on_submit=false and deactivate the st.rerun() I am able to delete the File in the Widget and only then the file gets deleted from the RAM.'
        e=event(action='disable_rerun',status='succeeded',quote=quote,conditions=[{'dimension':'clear_on_submit','value':'false','quote':quote}])
        with tempfile.TemporaryDirectory() as temp:
            state=Store(Path(temp)/'tracker.sqlite3').update('GH12607',c['initial_message'],experiment_events=[e])
            a=answer('ask'); a.update(question='پرسش: حافظه را بدون بازاجرا با کد ساده‌تر اندازه بگیرید.',diagnostic=diagnostic('turn off rerun',[{'dimension':'clear_on_submit','value':'false'}]))
            self.assertTrue(diagnostic_findings(a,state))
    def test_future_or_unknown_dates_are_excluded_in_historical_mode(self):
        self.assertEqual(temporal_status({'created_at':'2025-01-01T00:00:00Z','updated_at':'2026-01-01T00:00:00Z'},'2025-02-01T00:00:00Z'),'future')
        self.assertEqual(temporal_status({},'2025-02-01T00:00:00Z'),'unknown')
    def test_historical_filter_applies_to_lexical_only_and_hybrid(self):
        from casepilot.hybrid import HybridRetriever
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp); rows=[dict(row(),published_at='2024-01-01T00:00:00Z'),dict(row(),id='future',source_id='future',published_at='2026-01-01T00:00:00Z')]
            (p/'corpus.json').write_text(json.dumps(rows),encoding='utf-8')
            retriever=HybridRetriever(ReplayClient(),p/'corpus.json',p/'emb.sqlite3')
            for dense in (False,True):
                found=retriever.search('widget key',components={'dense':dense},as_of='2025-01-01T00:00:00Z')
                self.assertTrue(found); self.assertNotIn('future',{r['id'] for r in found})
    def test_feature_has_acceptance_and_never_reasks_clear_goal(self):
        from casepilot.routing import route_findings
        state={'messages':[{'text':'Feature request: compact upload button'}],'facts':{},'investigation_plan':{'intent':'feature_request','missing_detail':''}}
        a=answer('ask'); self.assertTrue(route_findings(a,state))
        a.update(decision='escalate',question='',feature_proposal={'current_behavior':'گزارش: دکمه بزرگ است.','desired_behavior':'نیاز: دکمه فشرده باشد.','user_need':'هدف: فضای کمتر.','constraints':'محدودیت: نامعلوم.','acceptance_condition':'پذیرش: عرض کمتر با آپلود یکسان.','report_quotes':['compact upload button']})
        self.assertFalse(route_findings(a,state)); packet=handoff(state,[],answer=a)
        self.assertIn('پذیرش',render_handoff(packet)); self.assertEqual(packet['request_type'],'feature_request')
    def test_handoff_retains_environment_experiments_unknowns_and_action(self):
        state={'messages':[{'text':'Upload kills server'}],'facts':{'deployment':'docker'},'experiments':[]}
        packet=handoff(state,[],error='provider_error'); text=render_handoff(packet)
        for part in ('docker','Upload kills server','مجهولات','اقدام','provider_error'): self.assertIn(part,text)
        self.assertIn('streamlit_version',packet['unknowns'])

class IntegratedContractTests(unittest.TestCase):
    def run_agent(self,judge_mode='valid'):
        from casepilot.accounting import Budget
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); path=Path(temp.name)
        class Client(ReplayClient):
            mode='live'
            def __init__(self): super().__init__(); self.budget=Budget(path/'budget.sqlite3'); self.usage_history=[]; self.max_output=1600
            def generate(self,*args,**kwargs):
                out=super().generate(*args,**kwargs)
                out.update(diagnostic=diagnostic(''),feature_proposal={**{k:'' for k in ('current_behavior','desired_behavior','user_need','constraints','acceptance_condition')},'report_quotes':[]})
                return out
            def structured(self,role,prompt,packet,schema,max_tokens):
                self.calls+=1; self.last_usage={'provider_requests':0,'kind':role}
                if role=='extract': return {'facts':[],'completed_checks':[],'ambiguities':[],'experiment_events':[],
                    'investigation':{'intent':'bug','problem_summary':'widget identity','known_report_spans':[], 'missing_detail':'','new_condition':'','suggested_question':'','acceptance_condition':''}}
                if role=='rerank': return {'ordered_ids':[r['id'] for r in packet['candidates']]}
                if role=='judge':
                    from review_helpers import current_review,wire_review
                    out=current_review(packet)
                    if judge_mode=='stale': out['draft_version']='old'
                    if judge_mode=='unsupported': out['unit_reviews'][-1]['support']='unknown'
                    return wire_review(out)
                if role=='repair': raise CasePilotError('provider_error','خرابی آزمایشی ابزار')
                raise AssertionError(role)
        store=Store(path/'tracker.sqlite3'); agent=Agent(store,client=Client(),hybrid=TinyHybrid())
        return agent,store
    def test_valid_contract_reaches_proposal_with_no_automatic_write(self):
        agent,store=self.run_agent(); out=agent.turn('A','Streamlit 1.49.0 widget issue','one',facts={'reproducible':True})
        self.assertIsNone(out['validation_error']); self.assertEqual(out['judge']['verdict'],'accept'); self.assertFalse(store.get('A')['comments'])
        self.assertEqual(Store(store.path).get('A')['investigation_plan']['problem_summary'],'widget identity')
    def test_corrupt_judge_is_logged_separately_without_retry(self):
        agent,store=self.run_agent('stale'); out=agent.turn('A','Streamlit 1.49.0 widget issue','one',facts={'reproducible':True})
        self.assertEqual(out['validation_error'],'judge_contract_error'); self.assertEqual(out['review_failures'][0]['kind'],'judge_contract')
        self.assertEqual(out['repair_count'],0); self.assertEqual(out['decision'],'escalate'); self.assertIsNotNone(out['summary']['handoff'])
        self.assertFalse(store.get('A')['comments'])
    def test_content_defect_and_repair_tool_failure_remain_recorded(self):
        agent,store=self.run_agent('unsupported'); out=agent.turn('A','Streamlit 1.49.0 widget issue','one',facts={'reproducible':True})
        self.assertEqual(out['review_failures'][0]['kind'],'insufficient_evidence'); self.assertEqual(out['validation_error'],'provider_error'); self.assertEqual(out['repair_count'],1)
    def test_stop_before_turn_save_resumes_same_revision_once(self):
        agent,store=self.run_agent(); original=store.save_turn
        with patch.object(store,'save_turn',side_effect=RuntimeError('simulated process stop')):
            with self.assertRaises(RuntimeError): agent.turn('A','Streamlit 1.49.0 widget issue','one',facts={'reproducible':True})
        agent=Agent(Store(store.path),client=agent.client,hybrid=TinyHybrid())
        out=agent.resume('A','one')
        self.assertEqual(store.get('A')['revision'],1); self.assertEqual(len(store.get('A')['messages']),1)
        again=agent.turn('A','Streamlit 1.49.0 widget issue','one',facts={'reproducible':True}); self.assertTrue(again['request_replayed'])
    def test_stop_before_extraction_preserves_input_for_resume(self):
        agent,store=self.run_agent(); original=agent.client.structured
        def unavailable(role,*args,**kwargs):
            if role=='extract': raise CasePilotError('budget_exhausted','توقف آزمایشی پیش از استخراج')
            return original(role,*args,**kwargs)
        with patch.object(agent.client,'structured',side_effect=unavailable),self.assertRaises(CasePilotError):
            agent.turn('A','Streamlit 1.49.0 widget issue','one',facts={'reproducible':True})
        job=Store(store.path).pending_turn('A','one')
        self.assertEqual(job['status'],'interrupted'); self.assertEqual(job['error'],'budget_exhausted')
        self.assertIn('widget issue',job['input']['message'])
        out=Agent(Store(store.path),client=agent.client,hybrid=TinyHybrid()).resume('A','one')
        self.assertIsNone(out['validation_error']); self.assertEqual(store.pending_turn('A','one')['status'],'completed')

if __name__=='__main__': unittest.main()
