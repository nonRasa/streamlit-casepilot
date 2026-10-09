"""Selection controls for capped development-only V2 runs."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_v2 import select_development_cases
from casepilot.common import CasePilotError

CASES=[{'id':'D1','split':'dev'},{'id':'D2','split':'dev'},{'id':'T1','split':'test'}]

class DevelopmentSelectionTests(unittest.TestCase):
    def test_explicit_selection_preserves_order(self):
        self.assertEqual([c['id'] for c in select_development_cases(CASES,2,['D2','D1'])],['D2','D1'])
        self.assertEqual([c['id'] for c in select_development_cases(CASES,1)],['D1'])

    def test_holdout_unknown_duplicate_and_empty_ids_are_rejected(self):
        for ids in (['T1'],['missing'],['D1','D1'],[],['D1','D2']):
            with self.subTest(ids=ids),self.assertRaises(CasePilotError):
                select_development_cases(CASES,1,ids)

if __name__=='__main__':
    unittest.main()
