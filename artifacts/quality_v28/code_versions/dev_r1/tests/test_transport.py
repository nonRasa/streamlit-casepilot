import json, os, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.model import MetisClient
from casepilot.server import create_server
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.retrieval import Retriever

class Response:
    def __init__(self,data): self.data=json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return self.data

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'METIS_API_KEY':'test-not-a-real-key','METIS_MODEL':'test-model',
            'METIS_BASE_URL':'https://api.metisai.ir/openai/v1','CASEPILOT_INPUT_USD_PER_MILLION':'1','CASEPILOT_OUTPUT_USD_PER_MILLION':'2','CASEPILOT_BUDGET_USD':'5'})
        self.env.start(); self.client=MetisClient(self.path/'budget.sqlite3'); self.client.cache=self.path/'cache'; self.client.cache.mkdir()
        self.client.diagnostics=self.path/'diagnostics'
        self.state={'facts':{},'checks':[],'messages':[{'text':'hello'}]}
        self.answer={'decision':'ask','claims':[],'question':'پرسش: نسخه چیست؟','next_step':'بررسی نسخه','rationale':'ابهام در نسخه','hypotheses':[]}
    def tearDown(self): self.env.stop(); self.tmp.cleanup()
    def test_request_and_confirmed_cost_cached(self):
        data={'choices':[{'message':{'content':json.dumps(self.answer)}}],'usage':{'prompt_tokens':100,'completion_tokens':50}}
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.return_value=Response(data)
            self.assertEqual(self.client.generate(self.state,[]),self.answer)
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.metisai.ir/openai/v1/chat/completions')
            self.assertEqual(json.loads(request.data)['model'],'test-model')
            self.client.generate(self.state,[]); self.assertEqual(opener.return_value.open.call_count,1)
        self.assertEqual(self.client.last_usage['mode'],'cached_live'); self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)
        self.assertNotIn('test-not-a-real-key',''.join(p.read_text() for p in self.client.cache.glob('*.json')))
    def test_timeout_keeps_reservation_no_retry(self):
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError('private provider error')
            with self.assertRaises(CasePilotError) as raised: self.client.generate(self.state,[])
            self.assertNotIn('private',str(raised.exception)); self.assertEqual(opener.return_value.open.call_count,1)
        self.assertGreater(self.client.budget.report()['uncertain_reserved_usd'],0)
    def test_missing_usage_keeps_reservation(self):
        data={'choices':[{'message':{'content':json.dumps(self.answer)}}]}
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.return_value=Response(data); self.client.generate(self.state,[])
        self.assertTrue(self.client.last_usage['usage_unknown']); self.assertGreater(self.client.budget.report()['uncertain_reserved_usd'],0)
    def test_bad_json_does_not_erase_known_cost(self):
        data={'choices':[{'message':{'content':'invalid JSON'}}],'usage':{'prompt_tokens':100,'completion_tokens':50}}
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.return_value=Response(data)
            with self.assertRaises(CasePilotError): self.client.generate(self.state,[])
        self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.retriever=Retriever()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'tracker.sqlite3')
        self.server=create_server('127.0.0.1',0,Agent(self.store,self.retriever),user_token='u'*32,review_token='r'*32)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_address[1])
    def tearDown(self): self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()
    def post(self,path,body,token='u'*32):
        req=Request(self.base+path,json.dumps(body).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+token})
        try:
            with urlopen(req,timeout=10) as response: return response.status,json.load(response)
        except HTTPError as error: return error.code,json.load(error)
    def test_operator_cannot_approve_or_execute(self):
        code,out=self.post('/api/turn',{'case_id':'A','request_id':'r1','message':'session_state widget'})
        self.assertEqual(code,200); p=out['proposal']
        code,result=self.post('/api/review',{'case_id':'A','proposal_id':p['id'],'proposal_hash':p['hash'],'decision':'approve','reviewer':'operator'})
        self.assertEqual(code,401); self.assertFalse(self.store.get('A')['comments'])
    def test_approve_execute_and_retry(self):
        _,out=self.post('/api/turn',{'case_id':'A','request_id':'r1','message':'session_state widget'})
        p=out['proposal']; code,review=self.post('/api/review',{'case_id':'A','proposal_id':p['id'],'proposal_hash':p['hash'],'decision':'approve','reviewer':'human-test'},'r'*32)
        self.assertEqual(code,200)
        body={'case_id':'A','proposal_id':p['id'],'approval_id':review['approval_id']}
        self.assertEqual(self.post('/api/execute',body,'r'*32)[0],200)
        self.assertTrue(self.post('/api/execute',body,'r'*32)[1]['replayed']); self.assertEqual(len(self.store.get('A')['comments']),1)
    def test_body_cannot_claim_reviewer_role(self):
        code,out=self.post('/api/turn',{'case_id':'A','request_id':'r1','message':'widget','approved':True})
        self.assertEqual(code,400); self.assertEqual(out['error'],'invalid_input')
    def test_health_does_not_reveal_tokens(self):
        with urlopen(self.base+'/health') as response: data=response.read().decode()
        self.assertNotIn('u'*32,data); self.assertNotIn('r'*32,data)
