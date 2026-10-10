"""Offline regression controls for stage attribution and assertion discovery."""
import copy
import json
import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.assertion_audit import candidates
from casepilot.report_quotes import catalog, resolve
from quality_v28_rescore import quote_status, coverage, human_status, judge_inputs, stage_record, delivered


class DiscoveryTests(unittest.TestCase):
    def test_question_punctuation_and_paraphrases(self):
        for stem in ('آیا می‌توانید زمان شروع `st.toast` نسبت به rerun را ثبت کنید',
                     'کدام پیام خطا در نسخهٔ فعلی نمایش داده شد',
                     'Could you provide the error message from st.toast',
                     'What timestamp did you record for the rerun'):
            for suffix in ('؟','؟.','?','?…','؟!','؟.  ','؟.\n','？。','؟.»','?")'):
                for field in ('question','next_step'):
                    with self.subTest(stem=stem,suffix=suffix,field=field):
                        self.assertEqual(candidates(stem+suffix,field),[])

    def test_observation_actions(self):
        for text in ('ثبت زمان دقیق شروع اعلان و مقایسه آن با rerun صفحه.',
                     'لطفاً یک مشاهده جدید از زمان‌بندی `st.toast` ثبت کنید.',
                     'Record the timestamp and error message from st.toast.',
                     'یک مشاهده تجربی که زمان طول عمر اعلان نسبت به rerun را جدا کند.'):
            self.assertEqual(candidates(text,'next_step'),[],text)

    def test_hidden_assertions_never_exempt_by_question_or_action(self):
        for text in ('آیا rerun باعث حذف داده می‌شود؟.',
                     'آیا استفاده از st.fake تضمین رفع خطا است؟',
                     'Try st.fake to configure the API.',
                     'Check the config; it definitely fixes the problem.',
                     'لطفاً تنظیم گزینهٔ api را برای رفع قطعی خطا تغییر دهید.',
                     'Set st.imaginary to true.',
                     'Record the timestamp, and the API returns cached data.',
                     'Record the timestamp because this API removes the state.',
                     'آیا زمان خطا را ثبت کردید و این API داده را حذف می‌کند؟.',
                     'Record the error message. This API always fixes the error.'):
            self.assertTrue(candidates(text,'next_step'),text)

    def test_exact_unicode_offsets_and_no_mutation(self):
        text='  ثبت زمان `st.toast` 🧪؟.\n  این API باعث حذف دادهٔ فارسی می‌شود.  '
        saved=text
        rows=candidates(text,'next_step')
        self.assertTrue(rows)
        for row in rows:self.assertEqual(text[row['start']:row['end']],row['text'])
        self.assertEqual(text,saved)

    def test_historical_punctuation_regression(self):
        r=json.loads((ROOT/'artifacts/quality_v28_remaining/turns/holdout_r0_H2_A.json').read_text(encoding='utf-8'))
        question=next(u['text'] for u in r['output']['reviewed_draft']['units'] if u['field']=='question')
        self.assertTrue(question.endswith('؟.'))
        self.assertEqual(candidates(question,'question'),[])
        self.assertEqual(candidates(question[:-1],'question'),[])


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.state={'id':'test','revision':1,'messages':[{'role':'user','text':'درخواست: افزودن API پیشنهادی 🧪.'}]}
        section=catalog(self.state)[0]
        self.feature=resolve({'feature_proposal':{'report_quotes':[section['section_id']]}},[section],self.state)['feature_proposal']
        self.units=[{'unit_id':'u','field':'feature_proposal.report_quotes.0','text':section['text']}]

    def test_quote_statuses_not_conflated(self):
        self.assertEqual(quote_status([],self.state,'feature_request')['status'],'not_selected')
        self.assertEqual(quote_status([],self.state,'bug_report')['status'],'not_required')
        self.assertEqual(quote_status(self.units,None,'feature_request')['status'],'unassessable')
        result=quote_status(self.units,self.state,'feature_request',feature=self.feature)
        self.assertTrue(result['snapshot_valid']);self.assertIsNone(result['semantic_relevance'])
        bad=copy.deepcopy(self.units);bad[0]['text']='بازنویسی درخواست'
        self.assertEqual(quote_status(bad,self.state,'feature_request')['status'],'invalid')
        changed=copy.deepcopy(self.state);changed['revision']=2
        self.assertFalse(quote_status(self.units,changed,'feature_request',feature=self.feature)['snapshot_valid'])

    def test_failed_human_review_is_completed(self):
        self.assertEqual(human_status({'a':'pass','b':'fail'},['a','b']),{'complete':True,'accepted':False})
        self.assertEqual(human_status({'a':'pass'},['a','b']),{'complete':False,'accepted':None})

    def test_coverage_uses_own_selected_sources_and_unknowns(self):
        text='The API returns a string.'
        p={'draft':{'units':[{'unit_id':'u','field':'next_step','text':text}]},
           'citations':[{'evidence_id':'e','quote':text}],
           'spans':{'sources':[{'span_id':'s','evidence_id':'e','text':text,'product_version':'1.0'}]}}
        j={'unit_reviews':[{'unit_id':'u','source_ids':['s'],'support':'supported'}],
           'meanings':{'u':{'act':'technical','assertion_text':text}},'valid_unit_ids':['u']}
        c={'u':[{'text':text,'start':0,'end':len(text)}]}
        row=coverage(p,j,self.state,c)['candidate_reviews'][0]
        self.assertTrue(row['selected_source_binding']);self.assertTrue(row['assertion_range_covers_candidate'])
        self.assertIsNone(row['independent_semantic_support'])
        p['citations'][0]['quote']='The API exists.'
        self.assertFalse(coverage(p,j,self.state,c)['candidate_reviews'][0]['selected_source_binding'])
        p.pop('citations')
        self.assertIsNone(coverage(p,j,self.state,c)['candidate_reviews'][0]['selected_source_binding'])
        self.assertIsNone(coverage(p,None,self.state,c)['candidate_reviews'][0]['assertion_range_covers_candidate'])

    def test_h1_a_exact_draft_removed_from_delivery(self):
        r=json.loads((ROOT/'artifacts/quality_v28_remaining/turns/holdout_r0_H1_A.json').read_text(encoding='utf-8'))
        i,m,req,p=list(judge_inputs(r))[-1]
        stage=stage_record(r,p,req,r['output']['judge'],i,m)
        q=stage['draft']['report_quotes']
        self.assertEqual(q['status'],'valid_exact')
        self.assertTrue(q['quotes'][0]['historical_guard_unit_valid'])
        self.assertIsNone(q['snapshot_valid']) # Envelope has text, not original snapshot.
        self.assertEqual(delivered(r,[stage])['report_quotes']['status'],'removed_from_delivery')
        self.assertFalse(r['output']['summary']['handoff']['feature'])

    def test_wrong_revision_review_not_reused(self):
        r=json.loads((ROOT/'artifacts/quality_v28_remaining/turns/holdout_r0_H1_A.json').read_text(encoding='utf-8'))
        i,m,req,p=list(judge_inputs(r))[-1]; j=copy.deepcopy(r['output']['judge']);j['draft_version']='foreign'
        stage=stage_record(r,p,req,j,i,m)
        self.assertFalse(stage['judge_and_guard']['guard_available'])
        r['state']['revision']+=1
        self.assertEqual(stage_record(r,p,req,None,i,m)['draft']['report_quotes']['status'],'unassessable')

    def test_end_to_end_read_only_offline_rescore(self):
        from score_quality_v28_remaining import score
        from quality_v28_rescore import sha
        with tempfile.TemporaryDirectory() as tmp, patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            dest=Path(tmp)/'report'
            report=score('holdout',0,dest)
            self.assertEqual(report['historical_acceptances'],0)
            self.assertEqual(report['new_provider_requests'],0)
            for path,value in report['input_hashes'].items():self.assertEqual(sha(ROOT/path),value)
            historical=json.loads((dest/'historical.json').read_text(encoding='utf-8'))
            replay=json.loads((dest/'local_replay.json').read_text(encoding='utf-8'))
            self.assertNotIn('local_control_replay',historical['turns'][0]['stages'][0])
            self.assertIsNone(replay['hypothetical_acceptances'])
            self.assertTrue(all(t['retrieval']['ndcg_at_8'] is None for t in report['turns']))
            self.assertTrue(all(t['retrieval']['recall_at_8_known_relevant_sources'] is None for t in report['turns']))
            self.assertTrue(all(not t['human_review']['complete'] and t['human_review']['accepted'] is None for t in report['turns']))
            with self.assertRaises(FileExistsError):score('holdout',0,dest)


if __name__=='__main__': unittest.main()
