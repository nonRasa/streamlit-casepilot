import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import CasePilotError
from casepilot.agent import extract_facts,Agent
from casepilot.store import Store
from casepilot.memory import migrate,version_roles,observed_comparisons,diagnostic_findings
from casepilot.review_contract import draft_units,review_spans,checked_review_v23,recompose
from casepilot.routing import handoff
from casepilot.roles import CRITERIA

PACKETS=json.loads((ROOT/'artifacts/quality_v22/live_comparison_01/ai_review_packets.json').read_text(encoding='utf-8'))['packets']
def packet(cid): return next(p for p in PACKETS if p['id']==cid and p['variant']=='revised')
def answer():
    return {'decision':'ask','question':'پرسش: بدنهٔ تابع کمکی چیست؟','next_step':'اقدام: فقط بدنهٔ تابع کمکی را بفرستید.',
        'rationale':'توضیح: برای بررسی، بدنهٔ تابع لازم است.','claims':[],'hypotheses':[]}
def review(a,state,evidence,technical=False):
    if technical and not a['claims']:a['claims']=[{'evidence_id':evidence[0]['id'],'quote':evidence[0]['text']}]
    env=draft_units(a,state['id'],state['revision'],0); spans=review_spans(state,evidence,a['claims'])
    r={'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: کنترل ساخته‌شدهٔ دستیار است.'} for k in CRITERIA},'draft_version':env['draft_version'],
        'unit_reviews':[], 'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'پرسش: ورودی لازم هنوز موجود نیست.'}}
    for u in env['units']:
        feature=u['field'].startswith('feature_proposal.')
        claim=technical and u['field']=='rationale'
        r['unit_reviews'].append({'unit_id':u['unit_id'],'kind':'request_summary' if feature else ('technical_claim' if claim else ('question' if u['field']=='question' else 'next_step')),
            'support':'supported' if feature or claim else 'unknown','source_ids':[spans['sources'][0]['span_id']] if claim else [],
            'message_ids':[spans['messages'][0]['span_id']] if feature else [],'premise':False,'standalone':True,
            'reason':'توضیح: کنترل معنایی از پیش ساخته‌شده است.','version_dependent':False,'version_limit':''})
    return env,r

class ReviewControls(unittest.TestCase):
    def setUp(self):
        self.a=answer();self.state={'id':'A','revision':1,'facts':{},'messages':[{'role':'user','text':'The example calls helper(); its body is not provided. Streamlit version:'}]}
        self.e=[{'id':'doc1','text':'The documented behavior of the helper is to return a table.', 'product_version':None}]
    def checked(self,r=None,a=None,env=None):
        a=a or self.a; default_env,default_r=review(a,self.state,self.e)
        return checked_review_v23(r or default_r,a,self.e,self.state,env or default_env)
    def test_useful_source_free_question_positive(self): self.assertEqual(self.checked()['verdict'],'accept')
    def test_direct_technical_support_positive(self):
        self.a['rationale']='توضیح: تابع جدول برمی‌گرداند.';env,r=review(self.a,self.state,self.e,True)
        self.assertEqual(self.checked(r,env=env)['verdict'],'accept')
    def test_partial_contradicted_unknown_are_not_direct_support(self):
        env,r=review(self.a,self.state,self.e,True)
        for status in ('partial','contradicted','unknown'):
            bad=copy.deepcopy(r);bad['unit_reviews'][-1]['support']=status
            out=self.checked(bad,env=env);self.assertNotEqual(out['verdict'],'accept');self.assertNotEqual(out['failure_kind'],'judge_contract')
    def test_fabricated_wrong_namespace_and_stale_ids(self):
        env,r=review(self.a,self.state,self.e,True);spans=review_spans(self.state,self.e)
        for sid in ('src_fake',spans['messages'][0]['span_id']):
            bad=copy.deepcopy(r);bad['unit_reviews'][-1]['source_ids']=[sid]
            with self.subTest(sid=sid),self.assertRaises(CasePilotError) as err:self.checked(bad,env=env)
            self.assertEqual(err.exception.code,'judge_contract_error')
        bad=copy.deepcopy(r);bad['draft_version']='old'
        with self.assertRaises(CasePilotError):self.checked(bad,env=env)
        # Same ID with mutated source text is no longer valid.
        self.e[0]['text']+=' changed'
        with self.assertRaises(CasePilotError):self.checked(r,env=env)
    def test_user_evidence_cannot_come_from_another_case(self):
        env,r=review(self.a,self.state,self.e);other=copy.deepcopy(self.state);other['id']='B'
        r['novelty'].update(status='repeated',relation='answers_requested_detail',message_ids=[review_spans(other,[])['messages'][0]['span_id']])
        with self.assertRaises(CasePilotError):self.checked(r,env=env)
    def test_real_quote_context_does_not_establish_repetition(self):
        env,r=review(self.a,self.state,self.e);sid=review_spans(self.state,[])['messages'][0]['span_id']
        r['novelty'].update(status='repeated',relation='context_only',message_ids=[sid])
        out=self.checked(r,env=env);self.assertEqual(out['novelty']['effective_status'],'unknown');self.assertEqual(out['verdict'],'accept')
    def test_missing_repeat_proof_remains_unknown(self):
        env,r=review(self.a,self.state,self.e);r['novelty'].update(status='repeated',relation='equivalent_experiment')
        self.assertEqual(self.checked(r,env=env)['novelty']['effective_status'],'unknown')
    def test_repetition_needs_real_message_and_relation(self):
        env,r=review(self.a,self.state,self.e);r['novelty'].update(status='repeated',relation='answers_requested_detail',message_ids=[review_spans(self.state,[])['messages'][0]['span_id']])
        self.assertNotEqual(self.checked(r,env=env)['verdict'],'accept')
    def test_reported_fact_without_user_witness_rejected(self):
        env,r=review(self.a,self.state,self.e);r['unit_reviews'][-1].update(kind='reported_fact',support='supported')
        self.assertEqual(self.checked(r,env=env)['verdict'],'repair')
    def test_GH17127_report_label_cannot_hide_guarantee(self):
        self.state['messages']=[{'text':packet('GH17127')['initial_report']}]
        self.a['rationale']='گزارش: استفاده از کتابخانه اندازهٔ صحیح و دسترس‌پذیری را تضمین می‌کند.'
        env,r=review(self.a,self.state,self.e);r['unit_reviews'][-1].update(kind='reported_fact',support='supported',message_ids=[review_spans(self.state,[])['messages'][0]['span_id']])
        self.assertEqual(self.checked(r,env=env)['verdict'],'repair')
    def test_question_with_unbacked_technical_premise_rejected(self):
        env,r=review(self.a,self.state,self.e);r['unit_reviews'][0].update(premise=True)
        self.assertEqual(self.checked(r,env=env)['verdict'],'repair')
    def test_unknown_source_version_requires_visible_limit(self):
        env,r=review(self.a,self.state,self.e,True);r['unit_reviews'][-1]['version_dependent']=True
        self.assertEqual(self.checked(r,env=env)['verdict'],'repair')
    def test_orphan_dropped_and_new_combination_must_be_rejudged(self):
        self.a['claims']=[{'evidence_id':'doc1','quote':self.e[0]['text']}]
        env,r=review(self.a,self.state,self.e);out=self.checked(r,env=env)
        combined=recompose(self.a,out,env);self.assertEqual(combined['claims'],[])
        new_env=draft_units(combined,'A',1,1)
        with self.assertRaises(CasePilotError):self.checked(r,a=combined,env=new_env)
        new_env,new_r=review(combined,self.state,self.e)
        self.assertEqual(self.checked(new_r,a=combined,env=new_env)['verdict'],'accept')

class MemoryRegressions(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'store.sqlite3';self.store=Store(self.path)
    def test_GH16631_current_survives_history(self):
        report=packet('GH16631')['initial_report'];self.assertEqual(extract_facts(report)['streamlit_version'],'1.61.1')
        state=self.store.update('A',report,extract_facts(report));self.assertTrue(any(r['role']=='previous' and r['value']=='1.60.0' for r in state['version_roles']))
        self.assertIn('1.61.1',state['fact_provenance']['streamlit_version']['quote'])
    def test_GH17011_pair_results_survive_restart_without_invented_environment(self):
        state=self.store.update('A',packet('GH17011')['initial_report']);state=Store(self.path).get('A')
        self.assertEqual(state['facts']['streamlit_version'],'1.64.0');self.assertEqual(len(state['experiments']),2)
        self.assertEqual([(e['conditions'][0]['value'],e['status']) for e in state['experiments']],[('1.57.0','succeeded'),('1.58.0','failed')])
        for e in state['experiments']:
            self.assertEqual(e['provenance']['message_index'],0);self.assertIn(e['result'],e['quote']);self.assertNotIn('python_version',{c['dimension'] for c in e['conditions']})
        self.assertEqual(Store(self.path).get('A')['experiments'],state['experiments'])
    def test_latest_lower_explicit_correction_wins(self):
        self.store.update('A','Streamlit version: 1.64.0');self.store.update('A','Correction: Streamlit 1.57.0')
        self.assertEqual(Store(self.path).get('A')['facts']['streamlit_version'],'1.57.0')
    def test_roles_are_distinct_not_largest(self):
        text='Current Streamlit version: 1.57.0\nPrevious Streamlit version: 1.60.0\nCompared Streamlit version: 1.59.0\nProposed Streamlit version: 1.64.0\nFixed Streamlit version: 1.62.0'
        self.assertEqual(extract_facts(text)['streamlit_version'],'1.57.0');self.assertEqual({r['role'] for r in version_roles(text)},{'current','previous','compared','proposed','fixed'})
    def test_comparison_not_execution_without_explicit_outcome(self):
        self.assertEqual(observed_comparisons('Try this:\n```\nuv run --with streamlit==1.58.0 streamlit run repro.py\n```'),[])
    def test_v2_migration_does_not_duplicate_experiments(self):
        state=self.store.update('A',packet('GH17011')['initial_report']);state['memory_version']=2;state['checks']=['legacy text']
        migrated=migrate(state);self.assertEqual(len(migrated['experiments']),2);self.assertEqual(migrate(migrated),migrated)
    def test_case_isolation_and_agent_proposal_not_performed(self):
        self.store.update('A',packet('GH17011')['initial_report']);self.store.update('B','Streamlit version:')
        self.assertEqual(Store(self.path).get('B')['experiments'],[]);self.assertEqual(Store(self.path).get('B')['facts'],{})
        d={'action':'disable rerun','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''}
        self.store.remember_proposed_check('B',1,d,'آزمایش: بازاجرا را خاموش کنید.')
        a=answer();a['diagnostic']=d;self.assertEqual(diagnostic_findings(a,Store(self.path).get('B')),[])

class FeatureRegressions(unittest.TestCase):
    def test_pipeline_rechecks_composition_and_does_not_keep_rejected_combination(self):
        from casepilot.model import ReplayClient
        from casepilot.accounting import Budget
        from test_architecture_v2 import TinyHybrid
        for reject_second in (False,True):
            with self.subTest(reject_second=reject_second),tempfile.TemporaryDirectory() as temp:
                p=packet('GH16481');feature=copy.deepcopy(next(x['raw_answer']['feature_proposal'] for x in p['raw_role_outputs'] if x['kind']=='chat'))
                feature['current_behavior']='گزارش کاربر: '+feature['current_behavior']
                class Client(ReplayClient):
                    mode='live'
                    def __init__(self):
                        super().__init__();self.usage_history=[];self.budget=Budget(Path(temp)/'budget.sqlite3');self.max_output=1600;self.generations=[]
                    def generate(self,state,evidence,method):
                        self.calls+=1;self.last_usage={'provider_requests':0}
                        a=answer();a.update(decision='escalate',question='',feature_proposal=feature,
                            claims=[{'evidence_id':evidence[0]['id'],'quote':evidence[0]['text']}],
                            diagnostic={'action':'','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''});return a
                    def structured(self,role,prompt,packet,schema,max_tokens):
                        self.calls+=1;self.last_usage={'provider_requests':0}
                        if role=='extract':return {'facts':[],'completed_checks':[],'ambiguities':[],'experiment_events':[],
                            'investigation':{'intent':'feature_request','problem_summary':'st.tabs pills','known_report_spans':[],
                                'missing_detail':'','new_condition':'','suggested_question':'','acceptance_condition':''}}
                        if role=='rerank':return {'ordered_ids':[r['id'] for r in packet['candidates']]}
                        if role=='judge':
                            env=packet['draft'];self.generations.append(env['generation'])
                            # Explicit contract fixture, no semantic inference/provider.
                            a=answer();a.update(decision='escalate',question='',feature_proposal=feature)
                            s={'id':'A','revision':1,'facts':{},'messages':[{'text':p['initial_report']}]}
                            _,r=review(a,s,[]);r['draft_version']=env['draft_version']
                            for e,u in zip(r['unit_reviews'],env['units']):e['unit_id']=u['unit_id']
                            if env['generation']==1 and reject_second:r['unit_reviews'][-1]['support']='partial'
                            from review_helpers import wire_review
                            return wire_review(r,packet)
                        raise AssertionError(role)
                client=Client();store=Store(Path(temp)/'store.sqlite3');out=Agent(store,client=client,hybrid=TinyHybrid()).turn('A',p['initial_report'],'one')
                self.assertEqual(client.generations,[0,1]);self.assertEqual(out['repair_count'],1);self.assertLessEqual(out['model_calls'],8)
                self.assertFalse(store.get('A')['comments'])
                if reject_second:
                    self.assertEqual(out['validation_error'],'judge_rejected');self.assertFalse(out['summary']['handoff']['feature'])
                else:
                    self.assertIsNone(out['validation_error']);self.assertEqual(out['summary']['handoff']['feature'],feature)
                    self.assertEqual(out['summary']['sources'],[])
    def test_actual_GH16481_GH17133_valid_feature_fields_survive_bad_citation(self):
        for cid in ('GH16481','GH17133'):
            p=packet(cid);raw=next(x['raw_answer'] for x in p['raw_role_outputs'] if x['kind']=='chat')
            a=answer();a.update(decision='escalate',question='',feature_proposal=raw['feature_proposal'])
            e=[{'id':'unrelated','text':'An unrelated documentation quotation about a library.', 'product_version':None}]
            a['claims']=[{'evidence_id':'unrelated','quote':e[0]['text']}]
            s={'id':cid,'revision':1,'facts':{},'messages':[{'text':p['initial_report']}],'investigation_plan':{'intent':'feature_request'}}
            env,r=review(a,s,e);checked=checked_review_v23(r,a,e,s,env);combined=recompose(a,checked,env)
            self.assertEqual(combined['feature_proposal'],raw['feature_proposal']);self.assertEqual(combined['claims'],[])
            env,r=review(combined,s,e);self.assertEqual(checked_review_v23(r,combined,e,s,env)['verdict'],'accept')
            self.assertEqual(handoff(s,[],answer=combined)['feature'],raw['feature_proposal'])
    def test_rejected_feature_field_prevents_whole_feature_salvage(self):
        p=packet('GH16481');raw=next(x['raw_answer'] for x in p['raw_role_outputs'] if x['kind']=='chat')
        a=answer();a.update(decision='escalate',question='',feature_proposal=raw['feature_proposal']);s={'id':'A','revision':1,'facts':{},'messages':[{'text':p['initial_report']}]}
        env,r=review(a,s,[]);r['unit_reviews'][-1]['support']='partial'
        self.assertIsNone(recompose(a,checked_review_v23(r,a,[],s,env),env))
    def test_internal_failure_does_not_establish_case_escalation_need(self):
        s={'messages':[{'text':'report'}],'facts':{}}
        self.assertEqual(handoff(s,[],'judge_contract_error')['escalation_basis'],'internal_review_failure')

if __name__=='__main__':unittest.main()
