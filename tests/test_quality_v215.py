import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.quality import novelty_findings
from casepilot.memory import normalize_version_comparison, validate_diagnostic
from casepilot.case_type import discard_unrequested_feature
from casepilot.common import CasePilotError


class QualityV215Tests(unittest.TestCase):
    def test_shown_reproducer_answers_method_presence_question(self):
        case = next(c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH11528')
        state = {'messages': [{'text': case['initial_message']}], 'facts': {}}
        answer = {'decision': 'ask', 'question': 'آیا کلاس Example در کد شامل __getstate__ یا __setstate__ است؟', 'next_step': ''}
        self.assertTrue(any('نمونهٔ بازتولید' in f['reason'] for f in novelty_findings(answer, state)))

    def test_real_class_difference_remains_a_valid_question(self):
        state = {'messages': [{'text': 'Reproducible Code Example\n```python\nclass Example:\n    def __init__(self):\n        pass\n```'}], 'facts': {}}
        answer = {'decision': 'ask', 'question': 'آیا کلاس واقعی با نمونهٔ Example تفاوت دارد و __getstate__ را تعریف می‌کند؟', 'next_step': ''}
        self.assertEqual(novelty_findings(answer, state), [])

    def test_incomplete_class_does_not_prove_absence(self):
        state = {'messages': [{'text': 'Reproducible Code Example\n```python\nclass Example:\n    def __init__(self):\n        ...\n```'}], 'facts': {}}
        answer = {'decision': 'ask', 'question': 'Does Example include __getstate__?', 'next_step': ''}
        self.assertEqual(novelty_findings(answer, state), [])

    def test_reported_version_pair_is_one_valid_condition(self):
        state = {'messages': [{'text': 'Upgrade from 1.43.0 to 1.44.0 failed.'}]}
        diagnostic = {'action': 'compare_versions', 'conditions': [
            {'dimension': 'streamlit_version', 'value': '1.43.0'},
            {'dimension': 'streamlit_version', 'value': '1.44.0'}],
            'repeat_of': '', 'changed_condition': 'streamlit_version', 'repeat_reason': '', 'missing_fact': ''}
        normalized = normalize_version_comparison(diagnostic, state)
        self.assertEqual(normalized['conditions'], [{'dimension': 'version_pair', 'value': '1.43.0 -> 1.44.0'}])
        self.assertEqual(normalized['changed_condition'], '')
        validate_diagnostic(normalized)
        self.assertEqual(len(diagnostic['conditions']), 2)

    def test_other_duplicates_and_unreported_versions_still_fail(self):
        state = {'messages': [{'text': 'Upgrade from 1.43.0 to 1.44.0 failed.'}]}
        for action, second in [('compare_versions', '1.45.0'), ('repeat_test', '1.44.0')]:
            diagnostic = {'action': action, 'conditions': [
                {'dimension': 'streamlit_version', 'value': '1.43.0'},
                {'dimension': 'streamlit_version', 'value': second}],
                'repeat_of': '', 'changed_condition': '', 'repeat_reason': '', 'missing_fact': ''}
            with self.assertRaises(CasePilotError):
                validate_diagnostic(normalize_version_comparison(diagnostic, state))

    def test_feature_payload_is_dropped_only_for_pure_bug(self):
        answer = {'feature_proposal': {'current_behavior': 'invented', 'desired_behavior': 'invented'}}
        bug = {'messages': [{'text': 'A reproducible error in Streamlit.'}]}
        typed_bug = {**bug, 'investigation_plan': {'intent': 'bug'}}
        feature = {'messages': [{'text': 'Feature request: add a new control.'}]}
        unclear = {'messages': [{'text': 'I want a control for this workflow.'}]}
        self.assertEqual(discard_unrequested_feature(answer, bug)['feature_proposal']['current_behavior'], '')
        self.assertEqual(discard_unrequested_feature(answer, typed_bug), answer)
        self.assertEqual(discard_unrequested_feature(answer, feature), answer)
        self.assertEqual(discard_unrequested_feature(answer, unclear), answer)


if __name__ == '__main__':
    unittest.main()
