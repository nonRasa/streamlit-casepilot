import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from evaluate_quality_v28_semantic_judge import build_request,assess,authorization
from casepilot.common import CasePilotError
from casepilot.compact_review import encode_fixture,descriptive_fixture,descriptive_decode,contract
from casepilot.roles import CRITERIA
from casepilot.judge_presentation import inline_evidence
from score_quality_v28_semantic_judge import spans_cover

DATA=ROOT/'eval/quality_v28_semantic_judge/suite_v3'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def reference_fixture(case,label,built):
    refs={u['field']:u for u in label['units']};reviews=[]
    for u in built['envelope']['units']:
        r=refs[u['field']];technical=r['expected_act']=='technical'
        messages=[];quote=''
        if r['exact_user_witnesses']:
            quote=r['exact_user_witnesses'][0]['text']
            messages=[s['span_id'] for s in built['packet']['spans']['messages'] if quote in s['text']][:1]
        sources=[s['span_id'] for s in built['packet']['spans']['sources'] if any(
            w['evidence_id']==s['evidence_id'] and w['quote']==s['text'] for w in r['selected_source_witnesses'])]
        deps=[]
        if u['field'].startswith('feature_proposal.report_quotes.'):
            deps=[d['unit_id'] for d in built['envelope']['units'] if d['field']=='feature_proposal.desired_behavior']
        reviews.append({'unit_id':u['unit_id'],'kind':r['expected_kind'],'support':r['expected_support'],
            'source_ids':sources,'message_ids':messages,'premise':technical,'standalone':True,
            'reason':'بررسی: مرجع موقت فقط بدل آزمون مسیر است.','version_dependent':False,
            'version_limit':r['expected_version_limit'] if technical and r['expected_version_limit'] in u['text'] else '',
            'meaning':{'act':r['expected_act'],'assertion_text':u.get('audited_text',u['text']) if technical else '',
                'user_quote':quote,'depends_on':deps}})
    result={'verdict':'accept' if label['expected_accept'] else 'repair',
        'assessments':{c:{'score':2 if label['expected_accept'] else 1,'reason':'بررسی: بدل کنترل مسیر است.'} for c in CRITERIA},
        'draft_version':built['envelope']['draft_version'],'unit_reviews':reviews,
        'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: در سابقه پاسخ این سؤال نیست.'}}
    wire=descriptive_fixture(encode_fixture(result,built['bound']))
    # Fixture-only construction from interval witnesses, including partial
    # boundary fragments. Do not use the old substring adapter as a gold oracle.
    for alias,unit in built['bound']['units'].items():
        witnesses=refs[unit['field']]['exact_user_witnesses']
        wire['unit_reviews'][alias]['user_phrase_aliases']=[a for a,m in built['bound']['messages'].items()
            if any(m['message_index']==w['message_index'] and m['start']<w['end'] and w['start']<m['end'] for w in witnesses)][:3]
    return wire


class FixedDraftJudgeTests(unittest.TestCase):
    def test_frozen_pair_family_and_reference_separation(self):
        manifest=read(DATA/'manifest.json')
        for name,value in manifest['files'].items():self.assertEqual(hashlib.sha256((DATA/name).read_bytes()).hexdigest(),value)
        self.assertTrue(set(manifest['families']['dev']).isdisjoint(manifest['families']['holdout']))
        for split in ('dev','holdout'):
            cases=read(DATA/(split+'_inputs.json'));labels=read(DATA/(split+'_labels.json'))
            self.assertEqual(len(cases),12);self.assertEqual(len({r['pair_id'] for r in cases}),6)
            for case,label in zip(cases,labels):
                built=build_request(case,'inline-evidence-v1')
                payload=json.dumps(built['payload'],ensure_ascii=False)
                for forbidden in ('expected_support','expected_accept','semantic_explanation','reference_status'):
                    self.assertNotIn(forbidden,payload)
                for u in label['units']:
                    for witness in u['exact_user_witnesses']:
                        text=case['state']['messages'][witness['message_index']]['text']
                        self.assertEqual(text[witness['start']:witness['end']],witness['text'])
                    for witness in u['selected_source_witnesses']:
                        source=next(s for s in case['evidence'] if s['id']==witness['evidence_id'])
                        self.assertEqual(source['text'][witness['start']:witness['end']],witness['quote'])

    def test_inline_aliases_preserve_exact_text_and_binding(self):
        case=read(DATA/'dev_inputs.json')[0]
        a=build_request(case);b=build_request(case,'inline-evidence-v1')
        self.assertEqual(a['bound'],b['bound'])
        self.assertEqual(a['payload']['response_format'],b['payload']['response_format'])
        for alias,row in b['packet']['compact_contract']['messages'].items():
            self.assertEqual(row['text'],b['bound']['messages'][alias]['text'])
            original=case['state']['messages'][row['message_index']]['text']
            self.assertEqual(original[row['start']:row['end']],row['text'])

    def test_positive_negative_references_through_whole_guard_path(self):
        # Development only: holdout model results cannot influence this test.
        cases=read(DATA/'dev_inputs.json');labels=read(DATA/'dev_labels.json')
        for case,label in zip(cases,labels):
            built=build_request(case);raw=reference_fixture(case,label,built)
            checked=assess(raw,built,case)
            self.assertTrue(checked['contract_valid'],case['id'])
            self.assertIsNotNone(checked['guard'],case['id'])
            if not label['expected_accept']:self.assertNotEqual(checked['guard']['verdict'],'accept',case['id'])
            else:self.assertEqual(checked['guard']['verdict'],'accept',case['id'])

    def test_all_selected_user_fragments_survive_and_offsets_are_verified(self):
        case=read(DATA/'dev_inputs.json')[2];label=read(DATA/'dev_labels.json')[2]
        built=build_request(case);raw=reference_fixture(case,label,built)
        target=next(a for a,u in built['bound']['units'].items() if u['field']=='feature_proposal.desired_behavior')
        chosen=raw['unit_reviews'][target]['user_phrase_aliases'];self.assertGreater(len(chosen),1)
        decoded=descriptive_decode(raw,built['bound'])
        meaning=next(e['meaning'] for e in decoded['unit_reviews'] if e['unit_id']==built['bound']['units'][target]['unit_id'])
        self.assertEqual(len(meaning['user_phrases']),len(chosen))
        self.assertIn(label['units'][next(i for i,u in enumerate(label['units']) if u['field']=='feature_proposal.desired_behavior')]['exact_user_witnesses'][0]['text'],meaning['user_quote'])
        checked=assess(raw,built,case);self.assertEqual(checked['guard']['verdict'],'accept')
        from casepilot.semantics import checked_semantic_review
        bad=copy.deepcopy(decoded);bad['unit_reviews'][0]['meaning']['user_phrases']=[dict(meaning['user_phrases'][0],start=999)]
        with self.assertRaises(CasePilotError):checked_semantic_review(bad,case['answer'],case['evidence'],case['state'],built['envelope'])

    def test_network_blocked_for_local_packet_and_guard(self):
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            case=read(DATA/'dev_inputs.json')[6];label=read(DATA/'dev_labels.json')[6]
            built=build_request(case);checked=assess(reference_fixture(case,label,built),built,case)
            self.assertTrue(checked['contract_valid'])

    def test_noncontiguous_spans_do_not_invent_a_quote(self):
        witness={'message_index':0,'start':5,'end':15}
        self.assertFalse(spans_cover(witness,[{'message_index':0,'start':5,'end':8},{'message_index':0,'start':10,'end':15}]))
        self.assertTrue(spans_cover(witness,[{'message_index':0,'start':5,'end':10},{'message_index':0,'start':10,'end':15}]))

    def test_api_named_prose_is_not_code_and_code_is_not_behavior_proof(self):
        from casepilot.semantics import source_adequacy
        self.assertIsNone(source_adequacy('این گزینه باعث بازاجرا می‌شود.',{'text':'st.button triggers a rerun when clicked.'}))
        self.assertEqual(source_adequacy('این گزینه باعث بازاجرا می‌شود.',{'text':'import streamlit as st\nst.button("Run")'}),'unknown')

    def test_persian_behavior_cannot_hide_as_procedure_or_version_false(self):
        from casepilot.assertion_audit import candidates
        for text in ('گزینهٔ st.cache_data برای هر فراخواننده کپی جدا برمی‌گرداند.',
                     'این API مقدار را بازمی‌گرداند.', 'این فرم داده را می‌فرستد.'):
            self.assertTrue(candidates(text,'next_step'))
        case=read(DATA/'dev_inputs.json')[-1];label=read(DATA/'dev_labels.json')[-1]
        built=build_request(case);raw=reference_fixture(case,label,built)
        alias=next(a for a,u in built['bound']['units'].items() if u['field']=='next_step')
        raw['unit_reviews'][alias].update(kind='next_step',speech_act='procedure',technical_assertion_range='none',version_dependent=False)
        self.assertFalse(assess(raw,built,case)['contract_valid'])


if __name__=='__main__':unittest.main()
