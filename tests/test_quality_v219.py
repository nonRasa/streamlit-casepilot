import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.grounding import fallback


class RecoveryOutputTests(unittest.TestCase):
    def test_missing_version_has_one_specific_request(self):
        state = {'messages': [{'text': 'file_uploader with large file kills server\nStreamlit version:\n'}],
                 'facts': {}, 'checks': []}
        answer = fallback('judge_rejected', state)
        self.assertIn('نسخهٔ دقیق Streamlit', answer['next_step'])
        self.assertNotIn('بستهٔ شواهد', answer['next_step'])
        self.assertIn('judge_rejected', answer['rationale'])

    def test_regression_keeps_exact_comparison_without_claiming_result(self):
        state = {'messages': [{'text': 'Upgrade from 1.43.0 to 1.44.0 fails.\n```python\ndef run():\n    pass\n```'}],
                 'facts': {}, 'checks': []}
        action = fallback('judge_contract_error', state)['next_step']
        self.assertIn('1.43.0', action)
        self.assertIn('1.44.0', action)
        self.assertIn('هنوز مستقلاً انجام نشده', action)

    def test_feature_failure_does_not_request_bug_version(self):
        state = {'messages': [{'text': 'Feature request: add a new option to the widget.'}],
                 'facts': {}, 'checks': []}
        action = fallback('judge_rejected', state)['next_step']
        self.assertIn('تصمیم طراحی', action)
        self.assertNotIn('نسخهٔ دقیق', action)


if __name__ == '__main__':
    unittest.main()
