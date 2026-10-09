"""The rejected-review handoff preserves a supplied reproducer."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from casepilot.routing import handoff, proposed_status, recovery_action, render_handoff

class ReproducerHandoffTests(unittest.TestCase):
    def test_reported_code_and_comparison_survive_review_failure(self):
        case=next(c for c in json.loads((ROOT/'eval/cases.json').read_text(encoding='utf-8')) if c['id']=='GH11528')
        report=case['initial_message']
        state={'messages':[{'text':report}],'facts':{'streamlit_version':'1.44.0','python_version':'3.10'},'checks':[]}
        packet=handoff(state,[],'judge_rejected')
        shown=render_handoff(packet,max_chars=11500)
        self.assertIn('b = test()',packet['reported_problem'])
        self.assertIn('````text\n',shown)
        self.assertIn('b = test()\n```\n',shown)
        self.assertIn('`Streamlit 1.43.0`',packet['maintainer_action'])
        self.assertIn('`Streamlit 1.44.0`',packet['maintainer_action'])
        self.assertIn('ثبت کند',packet['maintainer_action'])
        self.assertIsNone(proposed_status('escalate','judge_rejected'))

    def test_no_version_comparison_keeps_generic_recovery(self):
        state={'messages':[{'text':'A code sample:\n```python\ndef test(): pass\n```'}],
               'facts':{'streamlit_version':'1.44.0'},'checks':[]}
        self.assertNotIn('محیط همسان',recovery_action(state,False))

if __name__=='__main__':
    unittest.main()
