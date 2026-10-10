import os, time, unittest
from unittest.mock import patch
import test_transport as transport
Response=transport.Response
from casepilot.common import CasePilotError
from casepilot.model import MetisEmbedder
from casepilot.roles import JUDGE

class EmbeddingTransportTests(unittest.TestCase):
    setUp=transport.TransportTests.setUp
    tearDown=transport.TransportTests.tearDown
    def test_embedding_index_order_accounting_and_cache(self):
        with patch.dict(os.environ,{'METIS_EMBEDDING_MODEL':'test-embedding','CASEPILOT_EMBEDDING_USD_PER_MILLION':'.1'}): embedder=MetisEmbedder(self.client)
        response={'data':[{'index':1,'embedding':[0.,1.]},{'index':0,'embedding':[1.,0.]}],'usage':{'prompt_tokens':100}}
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.return_value=Response(response)
            self.assertEqual(embedder.embed(['first','second']),[[1.,0.],[0.,1.]])
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url,'https://api.metisai.ir/openai/v1/embeddings')
            embedder.embed(['first','second']); self.assertEqual(opener.return_value.open.call_count,1)
        report=self.client.budget.report(); self.assertEqual(report['embedding_requests'],1); self.assertAlmostEqual(report['embedding_cost_usd'],.00001)
        self.assertEqual(report['calls'][0]['output_tokens'],0); self.assertEqual(len(self.client.usage_history),2)
    def test_foreign_or_duplicate_embedding_indexes_rejected_without_retry(self):
        with patch.dict(os.environ,{'METIS_EMBEDDING_MODEL':'test','CASEPILOT_EMBEDDING_USD_PER_MILLION':'.1'}): embedder=MetisEmbedder(self.client)
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.return_value=Response({'data':[{'index':2,'embedding':[1,0]}],'usage':{'prompt_tokens':10}})
            with self.assertRaises(CasePilotError) as err: embedder.embed(['text'])
            self.assertEqual(err.exception.code,'invalid_embedding'); self.assertEqual(opener.return_value.open.call_count,1)
        self.assertGreater(self.client.budget.report()['confirmed_usd'],0)
    def test_turn_cost_guard_stops_before_network_and_reservation(self):
        self.client.turn_scope={'calls_before':0,'cost_before':0,'max_calls':8,'cap_usd':.0000001,'deadline':time.monotonic()+180}
        with patch('casepilot.model.build_opener') as opener,self.assertRaises(CasePilotError) as err: self.client.generate(self.state,[])
        self.assertEqual(err.exception.code,'turn_budget_exhausted'); opener.assert_not_called(); self.assertEqual(self.client.budget.report()['requests'],0)
    def test_turn_call_guard_and_deadline_stop_before_network(self):
        for limit,deadline,expected in ((0,time.monotonic()+1,'call_limit'),(8,time.monotonic()-1,'turn_timeout')):
            self.client.turn_scope={'calls_before':self.client.calls,'cost_before':0,'max_calls':limit,'cap_usd':.04,'deadline':deadline}
            with patch('casepilot.model.build_opener') as opener,self.assertRaises(CasePilotError) as err: self.client.generate(self.state,[])
            self.assertEqual(err.exception.code,expected); opener.assert_not_called()
    def test_different_judge_model_requires_separate_rates(self):
        with patch.dict(os.environ,{'METIS_JUDGE_MODEL':'separate-judge'}),self.assertRaises(CasePilotError) as err:
            self.client.structured('judge','read only',{},JUDGE)
        self.assertEqual(err.exception.code,'missing_prices'); self.assertEqual(self.client.budget.report()['requests'],0)

if __name__=='__main__': unittest.main()
