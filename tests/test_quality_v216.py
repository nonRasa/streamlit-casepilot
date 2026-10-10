import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.common import CasePilotError
from casepilot.roles import checked_investigation


def plan(span, question):
    return {'intent': 'bug', 'problem_summary': 'serialization error',
            'known_report_spans': [span], 'missing_detail': 'full error',
            'new_condition': '', 'suggested_question': question,
            'acceptance_condition': ''}


class QualityV216Tests(unittest.TestCase):
    def test_trims_only_exact_report_span_and_drops_repeated_plan_question(self):
        case = next(c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH11528')
        report = case['initial_message']
        span = 'I noticed in the upgrade from 1.43.0 to 1.44.0 that we are getting UnserializableReturnValueError'
        result = checked_investigation(plan(' '+span, 'لطفاً خطای کامل را ارسال کنید.'), report)
        self.assertEqual(result['known_report_spans'], [span])
        self.assertEqual(result['suggested_question'], '')
        self.assertEqual(result['missing_detail'], '')
        bundled = checked_investigation(plan(span, 'آیا می‌توانید لاگ کامل خطا یا stack trace را برای بررسی بیشتر ارسال کنید؟'), report)
        self.assertEqual(bundled['suggested_question'], '')

    def test_invented_span_still_fails_and_new_question_survives(self):
        report = 'A crash occurred after changing the widget key.'
        with self.assertRaises(CasePilotError):
            checked_investigation(plan('A crash was fixed.', 'Which browser?'), report)
        with self.assertRaises(CasePilotError):
            checked_investigation(plan('   ', 'Which browser?'), report)
        result = checked_investigation(plan(' '+report, 'Which browser?'), report)
        self.assertEqual(result['known_report_spans'], [report])
        self.assertEqual(result['suggested_question'], 'Which browser?')


if __name__ == '__main__':
    unittest.main()
