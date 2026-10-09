"""Stage controls are local fixtures, never evidence of live model quality."""
import copy, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import CasePilotError
from casepilot.compact_review import contract, schema, decode, encode_fixture, PROMPT
from casepilot.review_contract import draft_units, review_spans
from casepilot.semantics import checked_semantic_review
from test_quality_v23 import answer
from test_quality_v25 import state, judge, FeatureControls

class JudgeContractTests(unittest.TestCase):
    def sample(self):
        a=answer(); s=state(); env,r=judge(a,s)
        c=contract(env,review_spans(s,[],a['claims']))
        return a,s,env,c,encode_fixture(r,c)
    def test_every_reason_schema_and_full_processor_agree(self):
        a,s,env,c,w=self.sample()
        self.assertEqual(checked_semantic_review(decode(w,c),a,[],s,env)['verdict'],'accept')
        for where in ('criterion','unit','novelty'):
            for value in ('','  ','\n'):
                bad=copy.deepcopy(w)
                if where=='criterion': bad['r'][0]=value
                elif where=='unit': bad['u']['u0']['r']=value
                else: bad['n']['r']=value
                with self.subTest(where=where,value=value), self.assertRaises(CasePilotError):
                    checked_semantic_review(decode(bad,c),a,[],s,env)
    def test_numeric_semantics_no_longer_accepted(self):
        a,s,env,c,w=self.sample()
        for key in ('k','a','s'):
            bad=copy.deepcopy(w); bad['u']['u0'][key]=0
            with self.assertRaises(CasePilotError): checked_semantic_review(decode(bad,c),a,[],s,env)
        self.assertNotIn('WIRE OVERRIDE',PROMPT)
        self.assertNotIn('Copy draft_version',PROMPT)
    def test_capacity_full_processing_and_boundaries(self):
        a,s=FeatureControls().proposal('GH16481')
        a.update(decision='ask',question='پرسش: کدام شرط پذیرش نامعلوم است؟',hypotheses=['فرضیه: علت هنوز تأیید نشده است.']*3)
        env,r=judge(a,s)
        for u,e in zip(env['units'],r['unit_reviews']):
            if u['field'].startswith('hypotheses.'):
                e.update(kind='hypothesis',premise=True); e['meaning'].update(act='technical',assertion_text=u['text'])
        c=contract(env,review_spans(s,[],a['claims'])); w=encode_fixture(r,c)
        out=checked_semantic_review(decode(w,c),a,[],s,env)
        self.assertEqual(len(out['unit_reviews']),11)
        self.assertNotEqual(out['verdict'],'accept') # valid contract, unsupported content
        self.assertNotEqual(out['failure_kind'],'judge_contract')
        too_many=copy.deepcopy(env); too_many['units'].append(env['units'][0])
        with self.assertRaises(CasePilotError): contract(too_many,review_spans(s,[]))

if __name__=='__main__': unittest.main()
