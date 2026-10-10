import json, unittest
from unittest.mock import patch
import test_transport
from casepilot.model import quote_candidates, resolve_claims
from casepilot.grounding import validate_answer
from casepilot.common import CasePilotError


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.text='When you upload using [`st.file_uploader`](/develop/api-reference/widgets/st.file_uploader), data remain in RAM.'
        self.row={'id':'docs:upload:000','text':self.text,'source_id':'docs:upload','url':'https://docs.streamlit.io/','section':'Upload','lines':[1,1],'kind':'docs','revision':'snapshot','product_version':None}
        self.answer={'decision':'answer','claims':[{'evidence_id':self.row['id'],'quote_id':'q1'}],
                     'question':'','next_step':'بررسی: نتیجهٔ نمونه را مقایسه کنید.','rationale':'محدودیت: علت هنوز قطعی نیست.','hypotheses':[]}
        self.lookup={(self.row['id'],'q1'):self.text}

    def test_markdown_link_is_materialized_verbatim_and_validated(self):
        answer=resolve_claims(self.answer,self.lookup)
        citations=validate_answer(answer,[self.row])
        self.assertEqual(citations[0]['quote'],self.text)
        self.assertEqual(self.answer['claims'][0]['quote_id'],'q1')

    def test_previous_link_stripping_failure_still_rejected(self):
        answer=resolve_claims(self.answer,self.lookup)
        answer['claims'][0]['quote']=self.text.replace('(/develop/api-reference/widgets/st.file_uploader)','')
        with self.assertRaises(CasePilotError) as err: validate_answer(answer,[self.row])
        self.assertEqual(err.exception.code,'unsupported_quote')

    def test_unknown_source_and_cross_source_quote_rejected(self):
        lookup=dict(self.lookup,**{})
        lookup[('docs:other','q2')]='A quotation available only in another document.'
        for claim in ({'evidence_id':'invented','quote_id':'q1'},
                      {'evidence_id':self.row['id'],'quote_id':'q2'}):
            with self.subTest(claim=claim), self.assertRaises(CasePilotError) as err:
                resolve_claims(dict(self.answer,claims=[claim]),lookup)
            self.assertEqual(err.exception.code,'invalid_citation')

    def test_free_text_and_malformed_selection_rejected(self):
        for claim in ({'evidence_id':self.row['id'],'quote':self.text},
                      {'evidence_id':self.row['id'],'quote_id':['q1']},
                      {'evidence_id':self.row['id'],'quote_id':'q1','quote':'invented'}):
            with self.subTest(claim=claim), self.assertRaises(CasePilotError):
                resolve_claims(dict(self.answer,claims=[claim]),self.lookup)

    def test_candidates_are_bounded_original_spans_with_stable_ids(self):
        text='# Heading\n\n'+self.text+'\n\n'+('متن فارسی `Streamlit` با فاصله. '*100)+'\n\n'+('x'*1800)
        options=quote_candidates(text)
        self.assertEqual(options,quote_candidates(text))
        self.assertEqual(options[0]['text'],self.text)
        self.assertEqual([q['quote_id'] for q in options],['q'+str(i+1) for i in range(len(options))])
        self.assertTrue(all(20<=len(q['text'])<=700 and q['text'] in text for q in options))


class SelectionTransportTests(unittest.TestCase):
    setUp=test_transport.TransportTests.setUp
    tearDown=test_transport.TransportTests.tearDown
    def test_packet_selection_round_trip_and_cache(self):
        text='When you upload using [`st.file_uploader`](/develop/api-reference/widgets/st.file_uploader), data remain in RAM.'
        row={'id':'docs:upload:000','text':text}
        selected=dict(self.answer,claims=[{'evidence_id':row['id'],'quote_id':'q1'}])
        data={'choices':[{'message':{'content':json.dumps(selected)}}],'usage':{'prompt_tokens':100,'completion_tokens':50}}
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.return_value=test_transport.Response(data)
            out=self.client.generate(self.state,[row])
            packet=json.loads(json.loads(opener.return_value.open.call_args.args[0].data)['messages'][1]['content'])
            response_format=json.loads(opener.return_value.open.call_args.args[0].data)['response_format']
            self.assertEqual(response_format['type'],'json_schema')
            self.assertTrue(response_format['json_schema']['strict'])
            self.assertEqual(packet['evidence'][0]['quote_candidates'][0]['text'],text)
            self.assertEqual(out['claims'],[{'evidence_id':row['id'],'quote':text}])
            self.assertEqual(self.client.generate(self.state,[row]),out)
            self.assertEqual(opener.return_value.open.call_count,1)

    def test_invalid_selection_keeps_usage_and_does_not_retry(self):
        selected=dict(self.answer,claims=[{'evidence_id':'invented','quote_id':'q1'}])
        data={'choices':[{'message':{'content':json.dumps(selected)}}],'usage':{'prompt_tokens':100,'completion_tokens':50}}
        with patch('casepilot.model.build_opener') as opener:
            opener.return_value.open.return_value=test_transport.Response(data)
            with self.assertRaises(CasePilotError) as err: self.client.generate(self.state,[])
            self.assertEqual(err.exception.code,'invalid_citation')
            self.assertEqual(opener.return_value.open.call_count,1)
            with self.assertRaises(CasePilotError): self.client.generate(self.state,[])
            self.assertEqual(opener.return_value.open.call_count,1)
            self.assertEqual(self.client.last_usage['mode'],'cached_live')
        self.assertAlmostEqual(self.client.budget.report()['confirmed_usd'],.0002)
        self.assertEqual(len(list(self.client.cache.glob('*.json'))),1)
