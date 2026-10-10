import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.grounding import validate_answer
from casepilot.routing import reported_regression_check
from casepilot.roles import deterministic_findings
from casepilot.agent import Agent
from casepilot.model import ReplayClient
from casepilot.store import Store
from test_architecture_v2 import TinyHybrid


class QualityV217Tests(unittest.TestCase):
    def state(self, report):
        return {'messages': [{'text': report}], 'facts': {'streamlit_version': '1.44.0'},
                'checks': [], 'experiments': []}

    def test_reported_regression_has_source_free_maintainer_action(self):
        case = next(c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH11528')
        state = self.state(case['initial_message'])
        answer = reported_regression_check(state)
        self.assertEqual(answer['decision'], 'escalate')
        self.assertEqual(answer['claims'], [])
        self.assertEqual(answer['question'], '')
        self.assertEqual(answer['hypotheses'], [])
        self.assertIn('`Streamlit 1.43.0`', answer['next_step'])
        self.assertIn('`Streamlit 1.44.0`', answer['next_step'])
        self.assertEqual(validate_answer(answer, []), [])
        self.assertEqual(deterministic_findings(answer, [], state), [])

    def test_missing_or_incomplete_reproducer_uses_ordinary_route(self):
        prefix = 'A regression from 1.43.0 to 1.44.0.\n'
        self.assertIsNone(reported_regression_check(self.state(prefix)))
        self.assertIsNone(reported_regression_check(self.state(prefix+'```python\ndef app():\n    ...\n```')))
        self.assertIsNone(reported_regression_check(self.state('Feature request: '+prefix+'```python\ndef app():\n    return 1\n```')))

    def test_performed_version_comparison_is_not_repeated(self):
        report = 'A regression from 1.43.0 to 1.44.0.\n```python\ndef app():\n    return 1\n```'
        state = self.state(report)
        state['experiments'] = [{'id':'e1','status':'failed','action_key':'compare_versions','conditions':[
            {'dimension':'version_pair','value':'1.43.0 -> 1.44.0'}]}]
        self.assertIsNone(reported_regression_check(state))
        state['experiments'] = []
        state['checks'] = ['I tested the same code in 1.43.0 and 1.44.0.']
        self.assertIsNone(reported_regression_check(state))
        state['checks'] = []
        state['experiments'] = [{'id':'e2','status':'failed','action_key':'compare_versions','conditions':[
            {'dimension':'version_pair','value':'1.42.0 -> 1.43.0'}]}]
        self.assertIsNotNone(reported_regression_check(state))

    def test_pipeline_records_rule_origin_without_model_draft_or_judge(self):
        case = next(c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH11528')
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(Store(Path(tmp) / 'tracker.sqlite3'), client=ReplayClient(), hybrid=TinyHybrid())
            output = agent.turn('R', case['initial_message'], 'first', {'streamlit_version': '1.44.0'})
        self.assertEqual(output['generation_kind'], 'rule_based_regression')
        self.assertEqual(output['model_calls'], 1)
        self.assertIsNone(output['judge'])
        self.assertIsNone(output['validation_error'])
        self.assertEqual(output['summary']['sources'], [])
        self.assertEqual(output['proposal']['status'], 'pending')
        self.assertEqual(next(s for s in output['pipeline'] if s['stage'] == 'draft')['status'], 'rule_based_regression')


if __name__ == '__main__':
    unittest.main()
