"""Focused regression controls for review failure versus case escalation."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from casepilot.routing import handoff, proposed_status, proposal_actions, render_handoff
from casepilot.pipeline import repair_feedback
from casepilot.store import Store


class ReviewFailureOutcomeTests(unittest.TestCase):
    def test_repair_feedback_keeps_findings_without_duplicate_spans(self):
        findings=[{'criterion':'claim_support','unit_id':'u1','reason':'Unsupported claim.'},
                  {'criterion':'next_step_usefulness','reason':'Ask one detail.'}]
        review={'failure_kind':'answer_quality','findings':findings,
                'message_spans':[{'text':'x'*20000}],'unit_reviews':[{'text':'y'*20000}]}
        envelope={'units':[{'unit_id':'u1','field':'rationale'}]}
        compact=repair_feedback(review,envelope)
        self.assertEqual(len(compact['findings']),2)
        self.assertEqual(compact['findings'][0]['field'],'rationale')
        self.assertEqual(compact['findings'][1]['field'],None)
        self.assertNotIn('message_spans',compact)
        self.assertLess(len(str(compact).encode()),1000)

    def test_internal_failure_does_not_propose_case_status_change(self):
        for code in ('judge_contract_error', 'invalid_judge', 'judge_rejected',
                     'provider_response_invalid', 'deterministic_review_failed'):
            with self.subTest(code=code):
                self.assertIsNone(proposed_status('escalate', code))
                self.assertEqual(proposal_actions('Safe handoff', 'escalate', code),
                                 [{'type': 'comment', 'body': 'Safe handoff'}])

    def test_reviewed_case_decisions_keep_their_status(self):
        self.assertEqual(proposed_status('ask'), 'waiting_user')
        self.assertEqual(proposed_status('answer'), 'open')
        self.assertEqual(proposed_status('escalate'), 'escalated')
        self.assertEqual(proposal_actions('Reviewed', 'escalate')[-1],
                         {'type': 'status', 'value': 'escalated'})

    def test_internal_failure_handoff_preserves_reported_checks(self):
        state = {'id': 'case-a', 'messages': [{'role': 'user', 'text': 'App hangs on server.'}],
                 'facts': {'deployment': 'server'},
                 'checks': ['Reinstalled once; still hangs.', 'Works locally.',
                            'Reinstalled once; still hangs.'], 'experiments': []}
        packet = handoff(state, [], 'judge_contract_error')
        self.assertEqual(packet['escalation_basis'], 'internal_review_failure')
        self.assertEqual(packet['reported_checks'], ['Reinstalled once; still hangs.', 'Works locally.'])
        self.assertEqual(packet['valid_findings'], [])
        rendered = render_handoff(packet)
        self.assertIn('Works locally.', rendered)
        self.assertIn('نتیجهٔ مستقل تأیید نشده', rendered)
        self.assertNotIn('رفع مشکل تأیید شد', rendered)

    def test_first_turn_failure_asks_only_missing_streamlit_version(self):
        state = {'id':'case-a','messages':[{'role':'user','text':'3.5 GB upload kills the server.\nEDIT: I tried a Docker 4 GB limit, but it still failed.'}],
                 'facts':{},'checks':['Docker 4 GB limit also failed.'],'experiments':[],
                 'investigation_plan':{'intent':'bug'}}
        packet=handoff(state,[],'judge_rejected')
        self.assertIn('فقط نسخهٔ دقیق Streamlit',packet['maintainer_action'])
        self.assertNotIn('پایتون',packet['maintainer_action'])
        self.assertIn('Docker 4 GB',render_handoff(packet))
        self.assertEqual(packet['reported_attempts'],['EDIT: I tried a Docker 4 GB limit, but it still failed.'])
        self.assertIn('مستقلاً تأیید نشده',render_handoff(packet))
        self.assertEqual(packet['valid_findings'],[])

    def test_recovery_does_not_repeat_version_or_repurpose_feature(self):
        base={'id':'case-a','messages':[{'role':'user','text':'Upload kills server.'}],
              'facts':{},'checks':[],'experiments':[],'investigation_plan':{'intent':'bug'}}
        for change in ({'facts':{'streamlit_version':'1.50.0'}},
                       {'messages':[{'role':'user','text':'Streamlit version: 1.50.0; upload kills server.'}]},
                       {'messages':base['messages']+[{'role':'user','text':'Still fails.'}]},
                       {'investigation_plan':{'intent':'feature_request'}}):
            with self.subTest(change=change):
                packet=handoff(dict(base,**change),[],'judge_rejected')
                self.assertNotIn('فقط نسخهٔ دقیق Streamlit',packet['maintainer_action'])

    def test_simulated_approval_executes_comment_once_without_status_change(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'case.sqlite3')
            state = store.update('case-a', 'App hangs on server.', checks=['Works locally.'])
            payload = {'actions': proposal_actions('Internal review failed.', 'escalate', 'judge_contract_error'),
                       'source_ids': [], 'summary': {'escalation_basis': 'internal_review_failure'}}
            proposal = store.propose('case-a', state['revision'], payload)
            approval = store.review('case-a', proposal['id'], proposal['hash'], 'approve', 'test-reviewer')
            first = store.execute('case-a', proposal['id'], approval['approval_id'])
            second = store.execute('case-a', proposal['id'], approval['approval_id'])
            saved = store.get('case-a')
            self.assertEqual(saved['status'], 'open')
            self.assertEqual(len(saved['comments']), 1)
            self.assertFalse(first['replayed'])
            self.assertTrue(second['replayed'])


if __name__ == '__main__':
    unittest.main()
