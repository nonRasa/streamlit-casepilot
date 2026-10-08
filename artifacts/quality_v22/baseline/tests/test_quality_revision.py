import sys,unittest,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.quality import technical_source,compact_context,retrieval_query,novelty_findings
from casepilot.agent import Agent,extract_facts,version_observations
from casepilot.model import ReplayClient
from casepilot.store import Store
from casepilot.accounting import Budget
from casepilot.roles import checked_quality_judge,CRITERIA
from casepilot.common import CasePilotError

class QualityRevisionTests(unittest.TestCase):
    def test_template_and_proposal_are_not_runtime_evidence(self):
        self.assertFalse(technical_source({'section':'Checklist','title':'Uploader crash','text':'I searched existing issues','kind':'issue'}))
        self.assertFalse(technical_source({'section':'Design','title':'Proposal: a new execution architecture','text':'A future runtime could do this.','kind':'issue'}))
        self.assertTrue(technical_source({'section':'Widget behavior','title':'Widgets','text':'Widgets with stable keys preserve identity.','kind':'docs'}))
    def test_labeled_environment_beats_historical_comparison(self):
        msg='It works in Streamlit 1.22.0 but not 1.24.0.\n- **Streamlit version:** `1.24.0`\n- Python version: 3.10'
        self.assertEqual(extract_facts(msg),{'streamlit_version':'1.24.0','python_version':'3.10'})
        self.assertEqual(version_observations('Python 3.11 versus Python 3.12')['python_version'],{'3.11','3.12'})
    def test_long_initial_report_keeps_tail_and_latest_correction(self):
        text='Upload loses memory\n'+('diagnostic details '*700)+'\nI already tried writing to disk.\nStreamlit version: 1.49.1'
        state={'messages':[{'text':text},{'text':'Correction: Streamlit 1.50.0'}],'facts':{'streamlit_version':'1.50.0'},'checks':[]}
        packed=compact_context(state)
        self.assertIn('I already tried writing to disk.',packed['messages'][0]['text'])
        self.assertIn('Correction:',packed['messages'][-1]['text'])
        self.assertEqual(packed['report_inventory']['authoritative_current_facts']['streamlit_version'],'1.50.0')
    def test_salient_query_excludes_checkbox_and_full_code(self):
        text='Cache serializing custom class fails\nI already tried pickle.\n```python\n'+('x = 1\n'*200)+'```\n- [x] I have searched existing issues\nDebug info\nPython version: 3.11'
        state={'messages':[{'text':text}],'facts':{},'checks':[]}
        query=retrieval_query(state,text)
        self.assertLessEqual(len(query),2200); self.assertNotIn('searched existing',query); self.assertNotIn('x = 1',query)
        self.assertIn('Cache serializing',query)
    def test_already_supplied_limit_and_outside_pickle_are_not_new_checks(self):
        state={'messages':[{'text':'Run --maxUploadSize=5000. I can confirm pickle works outside streamlit.'}]}
        for q in ('پرسش: آیا با تنظیم maxUploadSize آزمایش کرده‌اید؟','پرسش: آیا pickle خارج برنامه کار می‌کند؟'):
            self.assertTrue(novelty_findings({'decision':'ask','question':q,'next_step':q},state))
        q='پرسش: آیا با maxUploadSize=200 و همان فایل نتیجه متفاوت است؟'
        self.assertFalse(novelty_findings({'decision':'ask','question':q,'next_step':q},state))
    def review(self):
        return {'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: بررسی شد.'} for k in CRITERIA},
            'audit':{'claim_links':[],'question_novelty':{'requested_detail':'کد تابع','already_supplied_quote':'','why_new':'بدنهٔ تابع گزارش نشده است.'},'version_assumptions':'ادعای نسخه ندارد.'}}
    def test_claim_proof_cannot_be_overridden_by_accept_scores(self):
        out=self.review(); out['audit']['claim_links']=[{'evidence_id':'a','statement':'نامرتبط','supported':False,'reason':'این شاهد علت را ثابت نمی‌کند.'}]
        answer={'decision':'answer','claims':[{'evidence_id':'a','quote':'Some evidence long enough.'}]}
        self.assertEqual(checked_quality_judge(out,answer,[],{'messages':[{'text':'problem'}]})['verdict'],'repair')
    def test_repeated_quote_cannot_be_overridden_by_accept_scores(self):
        out=self.review(); out['audit']['question_novelty']['already_supplied_quote']='already supplied'
        answer={'decision':'ask','claims':[]}
        self.assertEqual(checked_quality_judge(out,answer,[],{'messages':[{'text':'Code already supplied.'}]})['verdict'],'repair')
    def test_invented_audit_quote_cannot_be_accepted(self):
        out=self.review(); out['audit']['question_novelty']['already_supplied_quote']='invented'
        reviewed=checked_quality_judge(out,{'decision':'ask','claims':[]},[],{'messages':[{'text':'problem'}]})
        self.assertEqual(reviewed['verdict'],'repair'); self.assertTrue(reviewed['findings'])
    def test_live_planner_contract_on_new_case_and_followup_without_network(self):
        from test_architecture_v2 import TinyHybrid
        with tempfile.TemporaryDirectory() as tmp:
            class StubClient(ReplayClient):
                mode='live'
                def __init__(self):
                    super().__init__(); self.budget=Budget(Path(tmp)/'budget.sqlite3'); self.usage_history=[]
                def structured(self,role,prompt,packet,schema,max_tokens):
                    self.calls+=1; self.last_usage={'provider_requests':0,'kind':role}
                    if role=='extract': return {'facts':[],'completed_checks':[],'ambiguities':[],
                        'investigation':{'intent':'bug','problem_summary':'widget key','known_report_spans':[],
                            'missing_detail':'helper body','new_condition':'','suggested_question':'پرسش: بدنهٔ تابع چیست؟','acceptance_condition':''}}
                    if role=='rerank': return {'ordered_ids':[x['id'] for x in packet['candidates']]}
                    if role=='judge':
                        out=QualityRevisionTests().review(); out['audit']['claim_links']=[{'evidence_id':x['evidence_id'],
                            'statement':packet['answer']['rationale'],'supported':True,'reason':'بدل آزمایشی قرارداد.'} for x in packet['answer']['claims']]
                        return out
                    raise AssertionError(role)
            client=StubClient(); agent=Agent(Store(Path(tmp)/'tracker.sqlite3'),client=client,hybrid=TinyHybrid())
            first=agent.turn('Q','Streamlit 1.49.0 widget key issue','first',{'reproducible':True})
            self.assertIsNone(first['validation_error']); self.assertEqual(first['summary']['investigation_plan']['intent'],'bug')
            second=agent.turn('Q','Correction: Streamlit 1.48.0','second')
            self.assertIsNone(second['validation_error']); self.assertEqual(second['summary']['facts']['streamlit_version'],'1.48.0')

if __name__=='__main__': unittest.main()
