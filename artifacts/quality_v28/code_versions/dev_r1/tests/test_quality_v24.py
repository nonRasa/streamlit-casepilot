"""شکست‌های واقعی ذخیره‌شده و کنترل‌های معنایی ساخته‌شده؛ بدون درخواست مدل."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import CasePilotError
from casepilot.model import quote_candidates,resolve_claims
from casepilot.review_contract import (bound_review_schema,unpack_bound_review,
    checked_review_v23,draft_units,review_spans,recompose)
from casepilot.routing import handoff,render_handoff
from review_helpers import wire_review
from test_quality_v23 import review

PACKETS=json.loads((ROOT/'artifacts/quality_v24/real_judge_failures.json').read_text(encoding='utf-8'))['packets']


def restored(p):
    lookup={(e['id'],q['quote_id']):q['text'] for e in p['evidence'] for q in quote_candidates(e['text'])}
    a=resolve_claims(copy.deepcopy(p['raw_draft']),lookup)
    assert draft_units(a,p['state']['id'],p['state']['revision'],0)==p['envelope']
    return a


class RealJudgeRegressions(unittest.TestCase):
    def test_original_three_failures_remain_rejected(self):
        expected={'GH17011':'پوشش واحدها ناقص','GH16481':'شاهد جعلی','GH17127':'شناسهٔ واحد ناشناخته'}
        for p in PACKETS:
            with self.subTest(case=p['id']),self.assertRaises(CasePilotError) as err:
                checked_review_v23(p['raw_judge'],restored(p),p['evidence'],p['state'],p['envelope'])
            self.assertEqual(err.exception.code,'judge_contract_error')
            self.assertIn(expected[p['id']],str(err.exception))

    def test_schema_requires_every_exact_unit_without_repeated_id_field(self):
        for p in PACKETS:
            a=restored(p);spans=review_spans(p['state'],p['evidence'],a['claims'])
            schema=bound_review_schema(p['envelope'],spans)
            obj=schema['properties']['unit_reviews']
            self.assertEqual(set(obj['required']),{u['unit_id'] for u in p['envelope']['units']})
            self.assertFalse(obj['additionalProperties'])
            self.assertEqual(schema['properties']['draft_version']['enum'],[p['envelope']['draft_version']])
            for name in ('sources','messages'):
                expected={s['span_id'] for s in spans[name]}
                definition=schema['$defs'][name]
                self.assertEqual(set(definition['items'].get('enum',[])),expected)
                if not expected:self.assertEqual(definition['maxItems'],0)
            for u in p['envelope']['units']:
                name=obj['properties'][u['unit_id']]['$ref'].split('/')[-1]
                fields=schema['$defs'][name]['properties']
                self.assertNotIn('unit_id',fields)
                if u['field'].startswith('feature_proposal.'):
                    self.assertEqual(fields['kind']['enum'],['request_summary'])

    def test_missing_misspelled_stale_and_duplicate_unit_fields_fail_closed(self):
        p=PACKETS[0];wire=wire_review(p['raw_judge']);ids=list(wire['unit_reviews'])
        for kind in ('missing','typo','duplicate_field','legacy_array'):
            bad=copy.deepcopy(wire)
            if kind=='missing':bad['unit_reviews'].pop(ids[0])
            if kind=='typo':bad['unit_reviews'][ids[0]+'x']=bad['unit_reviews'].pop(ids[0])
            if kind=='duplicate_field':bad['unit_reviews'][ids[0]]['unit_id']=ids[-1]
            if kind=='legacy_array':bad=p['raw_judge']
            with self.subTest(kind=kind),self.assertRaises(CasePilotError):unpack_bound_review(bad,p['envelope'])

    def test_forged_namespace_and_stale_draft_still_rejected_after_unpacking(self):
        p=PACKETS[0];a=restored(p);env,r=review(a,p['state'],p['evidence'])
        for kind in ('namespace','stale'):
            bad=wire_review(copy.deepcopy(r));entry=next(iter(bad['unit_reviews'].values()))
            if kind=='namespace':entry['message_ids']=[env['units'][0]['unit_id']]
            else:bad['draft_version']='old'
            with self.subTest(kind=kind),self.assertRaises(CasePilotError):
                checked_review_v23(unpack_bound_review(bad,env),a,p['evidence'],p['state'],env)

    def test_useful_question_passes_but_unsupported_premise_still_fails(self):
        from test_quality_v23 import answer
        a=answer();state={'id':'control','revision':1,'facts':{},'messages':[{'text':'helper() body is missing.'}]}
        env,r=review(a,state,[])
        good=checked_review_v23(unpack_bound_review(wire_review(r),env),a,[],state,env)
        self.assertEqual(good['verdict'],'accept')
        r['unit_reviews'][0]['premise']=True
        bad=checked_review_v23(unpack_bound_review(wire_review(r),env),a,[],state,env)
        self.assertNotEqual(bad['verdict'],'accept')
        self.assertEqual(bad['failure_kind'],'insufficient_evidence')

    def test_real_feature_can_survive_rejected_question_only_after_new_review(self):
        p=next(p for p in PACKETS if p['id']=='GH16481');a=restored(p)
        env,r=review(a,p['state'],p['evidence'])
        # Synthetic semantic labels, not a claim that the recorded model approved them.
        for entry in r['unit_reviews'][:3]:entry.update(premise=True,support='unknown')
        r['assessments']['next_step_usefulness']['score']=0
        checked=checked_review_v23(r,a,p['evidence'],p['state'],env)
        combined=recompose(a,checked,env,p['state'])
        self.assertIsNotNone(combined);self.assertEqual(combined['decision'],'escalate')
        self.assertEqual(combined['feature_proposal'],a['feature_proposal'])
        self.assertEqual(combined['question'],'');self.assertEqual(combined['claims'],[])
        new_env=draft_units(combined,p['id'],p['state']['revision'],1)
        with self.assertRaises(CasePilotError):checked_review_v23(r,combined,p['evidence'],p['state'],new_env)
        _,new_review=review(combined,p['state'],p['evidence'])
        new_review['draft_version']=new_env['draft_version']
        for entry,u in zip(new_review['unit_reviews'],new_env['units']):entry['unit_id']=u['unit_id']
        accepted=checked_review_v23(new_review,combined,p['evidence'],p['state'],new_env)
        self.assertEqual(accepted['verdict'],'accept')
        packet=handoff(p['state'],[],answer=combined);text=render_handoff(packet)
        for value in a['feature_proposal'].values():
            if isinstance(value,str):self.assertIn(value,text)
        self.assertEqual(packet['escalation_basis'],'feature_request')
        self.assertIn('تصمیم طراحی',packet['maintainer_action'])
        new_review['unit_reviews'][-1]['support']='partial'
        self.assertNotEqual(checked_review_v23(new_review,combined,p['evidence'],p['state'],new_env)['verdict'],'accept')

    def test_partial_feature_cannot_be_salvaged(self):
        p=next(p for p in PACKETS if p['id']=='GH16481');a=restored(p)
        env,r=review(a,p['state'],p['evidence'])
        r['unit_reviews'][0]['premise']=True;r['unit_reviews'][-1]['support']='partial'
        checked=checked_review_v23(r,a,p['evidence'],p['state'],env)
        self.assertIsNone(recompose(a,checked,env,p['state']))


if __name__=='__main__':unittest.main()
