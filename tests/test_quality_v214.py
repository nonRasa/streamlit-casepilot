import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.quality import novelty_findings, retrieval_query, report_inventory


class QualityV214Tests(unittest.TestCase):
    def test_reported_full_error_and_class_are_not_requested_again(self):
        case = next(c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH11528')
        state = {'messages': [{'text': case['initial_message']}], 'facts': {}}
        self.assertIn('UnserializableReturnValueError', report_inventory(state)['reported_error_spans'][0])
        for decision in ('ask', 'escalate'):
            answer = {'decision': decision, 'question': 'Please send the full error and complete class definition.', 'next_step': ''}
            reasons = novelty_findings(answer, state)
            self.assertGreaterEqual(len(reasons), 2)
            self.assertTrue(all(r['criterion'] == 'avoids_repeated_check' for r in reasons))

    def test_missing_error_or_class_can_still_be_requested(self):
        state = {'messages': [{'text': 'st.cache_data failed; the error text and class were omitted.'}], 'facts': {}}
        answer = {'decision': 'ask', 'question': 'Please send the full error and complete class definition.', 'next_step': ''}
        self.assertEqual(novelty_findings(answer, state), [])

    def test_specific_missing_class_detail_is_allowed(self):
        state = {'messages': [{'text': 'class Example:\n    def __init__(self, name):\n        self.name = name'}], 'facts': {}}
        answer = {'decision': 'ask', 'question': 'Please provide the missing __reduce__ method implementation.', 'next_step': ''}
        self.assertEqual(novelty_findings(answer, state), [])

    def test_query_preserves_technical_summary_after_checklist(self):
        case = next(c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH11528')
        msg = case['initial_message']
        query = retrieval_query({'messages': [{'text': msg}], 'facts': {}}, msg)
        self.assertIn('UnserializableReturnValueError', query)
        self.assertIn('1.43.0 to 1.44.0', query)
        self.assertIn('pickle dumps and loads works fine', query)
        self.assertNotIn('descriptive title', query)


if __name__ == '__main__':
    unittest.main()
