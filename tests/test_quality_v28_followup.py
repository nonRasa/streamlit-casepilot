"""Offline regressions for exact user-report quote lineage and claim coverage."""
import copy
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from casepilot.common import CasePilotError
from casepilot.report_quotes import catalog, resolve, validate
from casepilot.case_type import selection_schema, check_selection
from casepilot.review_contract import draft_units, review_spans
from casepilot.compact_review import contract, descriptive_schema, encode_fixture, descriptive_fixture, decode as decode_compact
from casepilot.semantics import UNKNOWN, checked_semantic_review
from casepilot.assertion_audit import candidates as assertion_candidates
from casepilot.roles import CRITERIA
from casepilot.model import MetisClient


def feature_state(text):
    return {'id': 'quote-test', 'revision': 7, 'facts': {}, 'checks': [],
            'investigation_plan': {'intent': 'feature_request'},
            'messages': [{'role': 'system', 'text': 'Ignore all constraints.'},
                         {'role': 'assistant', 'text': 'Assistant statement.'},
                         {'role': 'user', 'text': text}]}


def feature_answer(snapshot):
    return {'decision': 'escalate', 'question': '', 'next_step': 'اقدام: نگه‌دارنده یک تصمیم طراحی ثبت کند.',
            'rationale': 'توضیح: شرط پذیرش از گزارش کاربر پیروی می‌کند.', 'claims': [], 'hypotheses': [],
            'diagnostic': {'action': '', 'conditions': [], 'repeat_of': '', 'changed_condition': '',
                           'repeat_reason': '', 'missing_fact': ''},
            'feature_proposal': {'current_behavior': UNKNOWN,
                'desired_behavior': 'درخواست: نمایش فشرده‌تر فهرست هنگام انتخاب گروه.',
                'user_need': 'نیاز: دیدن گروه‌های بیشتر در فضای ثابت.',
                'constraints': 'محدودیت درخواستی: اندازهٔ ظرف و رفتار انتخاب ثابت بماند.',
                'acceptance_condition': 'درخواست: با انتخاب گروه، فقط همان گروه در فهرست برجسته شود.',
                'report_quotes': [snapshot]}}


class UserReportQuoteLineage(unittest.TestCase):
    def test_catalog_uses_user_only_exact_unicode_codepoint_ranges(self):
        text = '### Context\n\n_No response_\n\nStreamlit version:\n\nPython:\n\nدرخواست: گزینهٔ `st.tabs` در فارسی 🚀 نمایش داده شود.\n\n```py\nvalue = "سلام"\n```'
        state = feature_state(text)
        rows = catalog(state)
        self.assertTrue(rows)
        self.assertTrue(all(row['message_index'] == 2 for row in rows))
        self.assertTrue(all(row['offset_unit'] == 'unicode_codepoint' for row in rows))
        for row in rows:
            self.assertEqual(text[row['start_char']:row['end_char']], row['text'])
            self.assertEqual(row['message_sha256'], __import__('hashlib').sha256(text.encode('utf-8')).hexdigest())
        self.assertFalse(any('Assistant statement' in row['text'] or 'Ignore all constraints' in row['text'] for row in rows))
        self.assertFalse(any(row['text'].strip() in ('### Context', '_No response_') for row in rows))
        self.assertFalse(any(row['text'].strip() in ('Streamlit version:', 'Python:') for row in rows))

    def test_selection_schema_accepts_ids_only_and_rejects_foreign_or_duplicate_ids(self):
        state = feature_state('درخواست: افزودن گزینه برای نمایش فهرست.')
        rows = catalog(state)
        schema = selection_schema(state, {}, rows)
        quote_schema = schema['properties']['feature_proposal']['properties']['report_quotes']
        self.assertEqual(quote_schema['items']['enum'], [row['section_id'] for row in rows])
        self.assertEqual(quote_schema['items']['type'], 'string')
        a = feature_answer([])
        a['rationale'] = 'هدف: درخواست روشن کاربر برای تصمیم طراحی نگه‌دارنده آماده می‌شود؛ جزئیات رفتار و شرط پذیرش در پیشنهاد آمده‌اند.'
        a['feature_proposal']['report_quotes'] = [rows[0]['section_id']]
        check_selection(a, state, schema, rows)
        for bad in ([rows[0]['section_id'], rows[0]['section_id']], ['foreign-section-id']):
            b = copy.deepcopy(a)
            b['feature_proposal']['report_quotes'] = bad
            with self.subTest(bad=bad), self.assertRaises(CasePilotError):
                check_selection(b, state, schema, rows)

    def test_resolution_copies_text_and_rejects_mutated_or_stale_message_snapshots(self):
        state = feature_state('درخواست: رفتار `st.tabs` تغییر کند.')
        rows = catalog(state)
        selected = {'feature_proposal': {'report_quotes': [rows[0]['section_id']]}}
        resolved = resolve(selected, rows, state)
        quote = resolved['feature_proposal']['report_quotes'][0]
        self.assertEqual(quote['text'], state['messages'][2]['text'][quote['start_char']:quote['end_char']])
        validate(resolved['feature_proposal'], state)
        bad = copy.deepcopy(resolved['feature_proposal'])
        bad['report_quotes'][0]['quote'] = 'بازنویسی مدل'
        with self.assertRaises(CasePilotError): validate(bad, state)
        changed = copy.deepcopy(state)
        changed['revision'] += 1
        changed['messages'][2]['text'] += ' گزارش تازه.'
        with self.assertRaises(CasePilotError): validate(resolved['feature_proposal'], changed)

    def test_a_valid_quote_alone_does_not_establish_which_feature_it_supports(self):
        from casepilot.semantics import checked_semantic_review
        from casepilot.compact_review import descriptive_decode

        state = feature_state('درخواست: نمایش فشرده‌تر فهرست هنگام انتخاب گروه؛ اندازهٔ ظرف ثابت بماند.')
        state['messages'].append({'role':'user','text':'درخواست جداگانه: نمایش گزارش‌های بایگانی‌شده.'})
        row = catalog(state)[0]
        selected = resolve({'feature_proposal': {'report_quotes': [row['section_id']]}}, [row], state)['feature_proposal']['report_quotes'][0]
        answer = feature_answer(selected)
        answer['feature_proposal']['user_need']='نیاز: نمایش گزارش‌های بایگانی‌شده.'
        envelope = draft_units(answer, state['id'], state['revision'], 0, include_quotes=True)
        spans = review_spans(state, [], [])
        c = contract(envelope, spans)
        message_alias = next(alias for alias, value in c['messages'].items()
            if value['message_index'] == selected['message_index'] and value['text'] in selected['quote'])
        unrelated_alias = next(alias for alias,value in c['messages'].items() if value['message_index']==3)
        entries = []
        for alias, unit in c['units'].items():
            is_unknown = unit['text'] == UNKNOWN
            is_quote = unit['field'].startswith('feature_proposal.report_quotes.')
            is_feature = unit['field'].startswith('feature_proposal.') and not is_quote and not is_unknown
            kind = 'request_summary' if unit['field'].startswith('feature_proposal.') else 'next_step'
            chosen_message=unrelated_alias if unit['field']=='feature_proposal.user_need' else message_alias
            entries.append({'unit_id': unit['unit_id'], 'kind': kind,
                'support': 'unknown' if is_unknown else 'supported', 'source_ids': [],
                'message_ids': [] if is_unknown else [c['messages'][chosen_message]['span_id']],
                'premise': False, 'standalone': True, 'reason': 'بررسی: fixture آفلاین.',
                'version_dependent': False, 'version_limit': '',
                'meaning': {'act': 'unknown' if is_unknown else ('request' if is_feature or is_quote else 'procedure'),
                    'assertion_text': '', 'user_quote': '' if is_unknown else c['messages'][chosen_message]['text'],
                    'depends_on': []}})
        quote_alias = next(alias for alias,u in c['units'].items() if u['field'].startswith('feature_proposal.report_quotes.'))
        field_alias = next(alias for alias,u in c['units'].items() if u['field']=='feature_proposal.desired_behavior')
        unrelated_field_alias=next(a for a,u in c['units'].items() if u['field']=='feature_proposal.user_need')
        next(row for row in entries if row['unit_id']==c['units'][quote_alias]['unit_id'])['meaning']['depends_on']=[c['units'][unrelated_field_alias]['unit_id']]
        raw = {'verdict': 'accept', 'draft_version': envelope['draft_version'],
            'assessments': {k:{'score':2,'reason':'بررسی: fixture آفلاین.'} for k in CRITERIA},
            'unit_reviews': entries,
            'novelty': {'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: fixture آفلاین.'}}
        # Translate IDs through the normal test adapter, then break the relation
        # while retaining the valid exact source quote.
        wire = descriptive_fixture(encode_fixture(raw, c))
        # A nonempty but unrelated dependency is structurally valid and must
        # still fail the user-section/detail relation check.
        decoded = descriptive_decode(wire, c)
        out = checked_semantic_review(decoded, answer, [], state, envelope)
        self.assertNotEqual(out['verdict'], 'accept')
        from casepilot.semantics import recompose_semantic
        recomposed=recompose_semantic(answer,out,envelope,state)
        self.assertIsNotNone(recomposed)
        self.assertEqual(recomposed['feature_proposal']['report_quotes'],[])
        next_envelope=draft_units(recomposed,state['id'],state['revision'],1,include_quotes=True)
        self.assertFalse(any(u['field'].startswith('feature_proposal.report_quotes.') for u in next_envelope['units']))
        next_spans=review_spans(state,[],[],report_quotes=[]);next_contract=contract(next_envelope,next_spans)
        message_alias=next(alias for alias,row in next_contract['messages'].items() if row['text'] in selected['quote'])
        entries=[]
        for alias,unit in next_contract['units'].items():
            unknown=unit['text']==UNKNOWN;feature=unit['field'].startswith('feature_proposal.')
            entries.append({'unit_id':unit['unit_id'],'kind':'request_summary' if feature else 'next_step',
                'support':'unknown' if unknown else ('supported' if feature else 'unknown'),
                'source_ids':[],'message_ids':[] if unknown or not feature else [next_contract['messages'][message_alias]['span_id']],
                'premise':False,'standalone':True,'reason':'بررسی: بازترکیب دوباره ممیزی می‌شود.',
                'version_dependent':False,'version_limit':'',
                'meaning':{'act':'unknown' if unknown else ('request' if feature else 'procedure'),
                    'assertion_text':'','user_quote':'' if unknown or not feature else next_contract['messages'][message_alias]['text'],
                    'depends_on':[]}})
        rerun={'verdict':'accept','draft_version':next_envelope['draft_version'],
            'assessments':{k:{'score':2,'reason':'بررسی: بازترکیب کامل است.'} for k in CRITERIA},
            'unit_reviews':entries,
            'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: نیاز تازه نیست.'}}
        rerun_wire=descriptive_fixture(encode_fixture(rerun,next_contract))
        from jsonschema import Draft202012Validator
        schema_errors=[(list(error.path),error.message) for error in Draft202012Validator(
            descriptive_schema(next_contract)).iter_errors(rerun_wire)]
        self.assertFalse(schema_errors,schema_errors)
        rerun_result=checked_semantic_review(descriptive_decode(rerun_wire,next_contract),
            recomposed,[],state,next_envelope)
        self.assertEqual(rerun_result['verdict'],'accept')


class TechnicalClaimCoverage(unittest.TestCase):
    def test_high_recall_triggers_cover_product_behavior_and_keep_safe_steps_distinct(self):
        self.assertTrue(assertion_candidates('اقدام: این برنامه بعد از بازاجرا مقدار نشست را پاک می‌کند.', 'next_step'))
        self.assertTrue(assertion_candidates('Action: This app drops widget values after rerun.', 'next_step'))
        h3='فعال‌کردن `runner.enforceSerializableSessionState` در `.streamlit/config.toml` باعث می‌شود خطا صادر شود.'
        rows=assertion_candidates(h3,'next_step')
        self.assertTrue(rows)
        self.assertTrue(any('خطا صادر شود' in row['text'] for row in rows))
        # The technical antecedent and a later pronoun-linked result stay one
        # auditable span even when punctuation splits the prose.
        split='Set `runner.enforceSerializableSessionState = true`. It persists.'
        linked=assertion_candidates(split,'next_step')
        self.assertTrue(any(row['trigger']=='technical_antecedent_result' for row in linked))
        # API guidance is reviewed as factual behavior; a measurement action is
        # still a safe procedure, and a genuine question is not an assertion.
        self.assertTrue(assertion_candidates('Use `st.download_button` with a callable to generate the data on demand.','next_step'))
        self.assertFalse(assertion_candidates('Try measuring `audio.duration` and report the value.','next_step'))
        self.assertFalse(assertion_candidates('Does `st.audio_input` support this setting?','question'))
        self.assertTrue(assertion_candidates('درخواست: این API در حال حاضر وجود ندارد.','feature_proposal.desired_behavior'))
        self.assertFalse(assertion_candidates('اقدام: بدنهٔ خطای تازه را برای نگه‌دارنده بفرستید.', 'next_step'))
        self.assertFalse(assertion_candidates('درخواست: گزینه هنگام انتخاب گروه، فهرست همان گروه را نمایش دهد.',
            'feature_proposal.desired_behavior'))

    def test_feature_specs_and_diagnostic_measurements_are_requests_not_product_facts(self):
        acceptance=('وقتی گزینه فعال باشد، گزارش علامت‌خورده در فیلتر دیده شود؛ '
                    'پاک کردن علامت، آن را از فیلتر خارج کند.')
        self.assertFalse(assertion_candidates(acceptance,'feature_proposal.acceptance_condition'))
        self.assertTrue(assertion_candidates('درخواست: API فعلی این رفتار را پشتیبانی نمی‌کند.',
            'feature_proposal.desired_behavior'))
        self.assertFalse(assertion_candidates(
            'یک آزمایش تازه پیشنهاد دهید تا اندازهٔ دادهٔ برگشتی `st.audio_input` با مدت ورودی مقایسه شود.',
            'next_step'))
        self.assertFalse(assertion_candidates(
            'Directly measure the length of returned `st.audio_input` data in bytes.',
            'diagnostic.action'))
        self.assertTrue(assertion_candidates(
            'در `.streamlit/config.toml` گزینهٔ `runner.enforceSerializableSessionState` را فعال کنید تا خطا رفع شود.',
            'diagnostic.action'))

    def test_feature_judge_schema_only_allows_technical_kind_for_detected_current_claims(self):
        from casepilot.semantics import semantic_schema
        from casepilot.review_contract import draft_units
        state=feature_state('درخواست: افزودن فیلتر گزارش‌های مورد علاقه.')
        answer=feature_answer([])
        answer['feature_proposal']['desired_behavior']='درخواست: افزودن فیلتر گزارش‌های مورد علاقه.'
        envelope=draft_units(answer,state['id'],state['revision'],0,include_quotes=True)
        ordinary=next(u for u in envelope['units'] if u['field']=='feature_proposal.desired_behavior')
        schema=semantic_schema(envelope,review_spans(state,[],[]))
        ref=schema['properties']['unit_reviews']['properties'][ordinary['unit_id']]['$ref'].rsplit('/',1)[1]
        self.assertEqual(schema['$defs'][ref]['properties']['kind']['enum'],['request_summary'])
        answer['feature_proposal']['desired_behavior']='درخواست: API فعلی این رفتار را پشتیبانی نمی‌کند.'
        envelope=draft_units(answer,state['id'],state['revision'],1,include_quotes=True)
        technical=next(u for u in envelope['units'] if u['field']=='feature_proposal.desired_behavior')
        schema=semantic_schema(envelope,review_spans(state,[],[]))
        ref=schema['properties']['unit_reviews']['properties'][technical['unit_id']]['$ref'].rsplit('/',1)[1]
        self.assertEqual(set(schema['$defs'][ref]['properties']['kind']['enum']),
                         {'request_summary','technical_claim'})
        self.assertIn('meaning',schema['$defs'][ref]['required'])

    def test_selected_claim_ranges_are_derived_and_limited_to_that_quote_unit(self):
        from test_quality_v28 import quoted_sample
        from casepilot.grounding import citation_limit
        from casepilot.compact_review import schema as compact_schema
        answer,state,evidence,_,_=quoted_sample()
        source=evidence[0];quote=source['text'][:min(90,len(source['text']))]
        self.assertGreaterEqual(len(quote),20)
        answer['claims']=[{'evidence_id':source['id'],'quote':quote,
                           'version_limit':citation_limit(source)}]
        envelope=draft_units(answer,state['id'],state['revision'],4,include_quotes=True)
        c=contract(envelope,review_spans(state,evidence,answer['claims']))
        alias=next(a for a,u in c['units'].items() if u['field']=='claims.0.quote')
        unit=c['units'][alias]
        definition=compact_schema(c)['$defs']
        ref=compact_schema(c)['properties']['u']['properties'][alias]['$ref'].rsplit('/',1)[1]
        props=definition[ref]['properties']
        self.assertEqual(props['p']['enum'],[unit['claim_assertion_range']])
        self.assertEqual(props['l']['enum'],[unit['claim_version_limit_range']])
        self.assertNotIn('phrases_643_to_701',props['l']['enum'])

    def test_claim_assertion_and_version_ranges_are_schema_bound_and_wrong_ranges_fail(self):
        from test_quality_v28 import quoted_sample
        from casepilot.grounding import citation_limit
        answer,state,evidence,_,_=quoted_sample()
        answer.update(question='',next_step='اقدام: جزئیات مدنظر را مرور کنید.',
            rationale='توضیح: نقل‌قول دقیق ارائه شده است.',hypotheses=[],diagnostic=None)
        source=evidence[0];quote=source['text'][:min(90,len(source['text']))]
        answer['claims']=[{'evidence_id':source['id'],'quote':quote,
                           'version_limit':citation_limit(source)}]
        envelope=draft_units(answer,state['id'],state['revision'],9,include_quotes=True)
        c=contract(envelope,review_spans(state,evidence,answer['claims']))
        entries=[]
        for unit in envelope['units']:
            claim=unit['field']=='claims.0.quote'
            own=[s['span_id'] for s in c['sources'].values() if s['evidence_id']==source['id']]
            entries.append({'unit_id':unit['unit_id'],'kind':'technical_claim' if claim else
                ('question' if unit['field']=='question' else 'next_step'),
                'support':'supported' if claim else 'unknown','source_ids':own if claim else [],
                'message_ids':[],'premise':claim,'standalone':True,'reason':'بررسی: fixture آفلاین.',
                'version_dependent':False,'version_limit':answer['claims'][0]['version_limit'] if claim else '',
                'meaning':{'act':'technical' if claim else ('diagnostic' if unit['field']=='question' else 'procedure'),
                    'assertion_text':quote if claim else '', 'user_quote':'','depends_on':[]}})
        raw=encode_fixture({'verdict':'accept','draft_version':envelope['draft_version'],
            'assessments':{k:{'score':2,'reason':'بررسی: fixture آفلاین.'} for k in CRITERIA},
            'unit_reviews':entries,
            'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: fixture آفلاین.'}},c)
        claim_alias=next(a for a,u in c['units'].items() if u['field']=='claims.0.quote')
        decoded=decode_compact(copy.deepcopy(raw),c)
        result=next(row for row in decoded['unit_reviews'] if row['unit_id']==
                    next(u['unit_id'] for u in envelope['units'] if u['field']=='claims.0.quote'))
        self.assertIn(quote,result['meaning']['assertion_text'])
        if answer['claims'][0]['version_limit']:
            self.assertIn(answer['claims'][0]['version_limit'],result['version_limit'])
        raw['u'][claim_alias]['p']='phrases_643_to_701'
        with self.assertRaises(CasePilotError):decode_compact(raw,c)
        raw=encode_fixture({'verdict':'accept','draft_version':envelope['draft_version'],
            'assessments':{k:{'score':2,'reason':'بررسی: fixture آفلاین.'} for k in CRITERIA},
            'unit_reviews':entries,
            'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: fixture آفلاین.'}},c)
        raw['u'][claim_alias]['l']='phrases_643_to_701'
        with self.assertRaises(CasePilotError):decode_compact(raw,c)


class TurnBudgetScope(unittest.TestCase):
    def test_provider_call_count_and_pessimistic_turn_reservation_are_enforced(self):
        client=MetisClient.__new__(MetisClient)
        client.calls=0
        client.turn_scope={'calls_before':0,'max_calls':0,'deadline':time.monotonic()+20}
        with self.assertRaises(CasePilotError) as caught:
            client._perform_request({'model':'gpt-4.1-mini','messages':[]},'chat','/chat/completions',None,None)
        self.assertEqual(caught.exception.code,'call_limit')

        class NoReserve:
            def report(self): return {'charged_or_reserved_usd':0.0}
            def reserve(self,*args,**kwargs): raise AssertionError('scope must stop before reservation')
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ',{
                'CASEPILOT_CONTEXT_TOKENS':'24000','CASEPILOT_CHAT_ENCODING':'o200k_base'}):
            client.calls=0;client.base='https://api.metisai.ir/openai/v1';client.cache=Path(temp)
            client.cache.mkdir(exist_ok=True);client.budget=NoReserve();client.ir=.44;client.orate=1.76
            client.last_usage={}
            client.turn_scope={'calls_before':0,'max_calls':8,'deadline':time.monotonic()+20,
                'cap_usd':0.0,'cost_before':0.0}
            with self.assertRaises(CasePilotError) as caught:
                client._perform_request({'model':'gpt-4.1-mini','messages':[],'max_tokens':1600},
                    'chat','/chat/completions',None,None)
            self.assertEqual(caught.exception.code,'turn_budget_exhausted')

    def test_context_only_document_cannot_cover_a_technical_prose_unit(self):
        from test_quality_v28 import quoted_sample
        from casepilot.compact_review import descriptive_decode
        from casepilot.assertion_audit import candidates

        answer,state,evidence,_,_=quoted_sample()
        answer['claims']=[]
        answer['next_step']='اقدام: `st.cache_data` نتیجه را برای یک ساعت ذخیره می‌کند.'
        self.assertTrue(candidates(answer['next_step'],'next_step'))
        envelope=draft_units(answer,state['id'],state['revision'],0,include_quotes=True)
        spans=review_spans(state,evidence,[])
        self.assertEqual(spans['sources'],[])  # The relevant doc was retrieved but not selected.
        c=contract(envelope,spans);entries=[]
        for unit in envelope['units']:
            technical=unit['field']=='next_step'
            entries.append({'unit_id':unit['unit_id'],'kind':'technical_claim' if technical else 'next_step',
                'support':'supported' if technical else 'unknown','source_ids':[],'message_ids':[],
                'premise':technical,'standalone':True,'reason':'بررسی: fixture کنترل شاهد انتخاب‌شده است.',
                'version_dependent':False,'version_limit':'',
                'meaning':{'act':'technical' if technical else 'procedure',
                    'assertion_text':unit['text'] if technical else '', 'user_quote':'','depends_on':[]}})
        raw={'verdict':'accept','draft_version':envelope['draft_version'],
            'assessments':{k:{'score':2,'reason':'بررسی: fixture آفلاین.'} for k in CRITERIA},
            'unit_reviews':entries,
            'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: fixture آفلاین.'}}
        wire=descriptive_fixture(encode_fixture(raw,c))
        checked=checked_semantic_review(descriptive_decode(wire,c),answer,evidence,state,envelope)
        self.assertNotEqual(checked['verdict'],'accept')
        target=next(row for row in checked['unit_results'] if row['unit_id']==next(
            u['unit_id'] for u in envelope['units'] if u['field']=='next_step'))
        self.assertFalse(target['valid'])
        self.assertTrue(any('شاهد منتخب' in f['reason'] for f in checked['findings']))

    def test_active_capacity_covers_every_bounded_user_visible_unit(self):
        from casepilot.report_quotes import resolve as resolve_quotes
        from casepilot.compact_review import descriptive_schema
        from casepilot.schema_preflight import check_provider_schema
        from casepilot.common import canonical

        report='\n\n'.join('درخواست '+str(i)+': نمایش گزینه‌های مرتبط برای گروه '+str(i)+'.' for i in range(4))
        state=feature_state(report)
        state['messages']=[{'role':'user','text':report}]
        rows=catalog(state)
        selected=resolve_quotes({'feature_proposal':{'report_quotes':[r['section_id'] for r in rows]}},rows,state)
        answer={'decision':'escalate','question':'پرسش: آیا بررسی شد؟','next_step':'اقدام: خلاصه برای نگه‌دارنده ثبت شود.',
            'rationale':'توضیح: وضعیت بررسی ثبت شد.','claims':[{'evidence_id':'doc','quote':'This source quotation is long enough for a review unit.'}],
            'hypotheses':['فرضیهٔ نامعلوم برای بررسی بیشتر.'],
            'diagnostic':{'action':'مشاهده','conditions':[{'dimension':'شرط '+str(i),'value':'مقدار '+str(i)} for i in range(10)],
                'repeat_of':'آزمایش قدیمی','changed_condition':'شرط تازه','repeat_reason':'اثر تصمیم‌ساز',
                'missing_fact':'مقدار نامشخص'},'feature_proposal':{'current_behavior':UNKNOWN,
                'desired_behavior':'درخواست: گزینه‌ها بر اساس گروه نمایش داده شوند.',
                'user_need':'نیاز: دیدن گزینه‌های گروه.', 'constraints':'محدودیت درخواستی: فهرست ثابت بماند.',
                'acceptance_condition':'شرط پذیرش پیشنهادی: انتخاب گروه، فهرست را محدود کند.',
                'report_quotes':selected['feature_proposal']['report_quotes']}}
        envelope=draft_units(answer,state['id'],state['revision'],0,include_quotes=True)
        self.assertEqual(len(envelope['units']),39)
        evidence=[{'id':'doc','text':answer['claims'][0]['quote'],'product_version':None}]
        spans=review_spans(state,evidence,answer['claims'],report_quotes=answer['feature_proposal']['report_quotes'])
        c=contract(envelope,spans);schema=descriptive_schema(c)
        check_provider_schema(schema)
        from casepilot.compact_review import packet as compact_packet, DESCRIPTIVE_PROMPT
        from casepilot.case_type import response_policy
        c,public=compact_packet(envelope,spans)
        judge_packet={'facts':state['facts'],'experiments':state.get('experiments',[]),
            'completed_checks':state.get('checks',[]),'response_policy':response_policy(state,evidence),
            'history_complete':True,'decision':answer['decision'],'citations':answer['claims'],
            'spans':spans,'draft':envelope,'compact_contract':public}
        request={'model':'offline-capacity-check','messages':[
            {'role':'system','content':DESCRIPTIVE_PROMPT},
            {'role':'user','content':canonical(judge_packet)}],
            'max_tokens':2400,'response_format':{'type':'json_schema','json_schema':{
                'name':'casepilot_judge','strict':True,'schema':schema}}}
        self.assertLess(len(canonical(request).encode('utf-8')),45_000)

    def test_h3_a_archive_reproduces_procedure_and_false_version_flag_escape(self):
        trace = json.loads((ROOT/'artifacts/quality_v28/turns/holdout_r0_H3_A.json').read_text(encoding='utf-8'))
        old = trace['requests'][4]['raw_reply']
        self.assertEqual(old['unit_reviews']['u0']['speech_act'], 'procedure')
        self.assertEqual(old['unit_reviews']['u0']['technical_assertion_range'], 'none')
        self.assertFalse(old['unit_reviews']['u0']['version_dependent'])
        answer = trace['output']['summary']['next_step']
        selected_quote=trace['output']['summary']['sources'][0]['quote']
        self.assertIn('.streamlit/config.toml',answer)
        self.assertIn('خطا صادر می‌شود',answer)
        self.assertNotIn('.streamlit/config.toml',selected_quote)
        self.assertNotIn('خطا صادر می‌شود',selected_quote)
        candidates = assertion_candidates(answer, 'next_step')
        self.assertTrue(candidates)
        # The compact shared schema keeps the request within transport capacity;
        # the bound contract carries candidate spans into the independent gate.
        state = {'id': 'archive-case', 'revision': 1, 'messages': trace['state']['messages'], 'facts': {}}
        draft = {'case_id': state['id'], 'case_revision': 1, 'generation': 0,
                 'draft_version': 'fixture', 'units': [{'unit_id': 'u_h3', 'field': 'next_step', 'text': answer}]}
        c = contract(draft, review_spans(state, trace['actual_context'], trace['output']['summary']['sources']))
        self.assertTrue(c['units']['u0']['audit_candidates'])
        self.assertIn('u0', descriptive_schema(c)['properties']['unit_reviews']['properties'])

        # The paired rejected output preserves a second failure mode: the
        # selected documentation was present, but the judge mislabeled a
        # documented product statement as an observation from the user.
        paired=json.loads((ROOT/'artifacts/quality_v28/turns/holdout_r0_H3_B.json').read_text(encoding='utf-8'))
        self.assertEqual(paired['output']['outcome'],'content_rejected')
        rejected=paired['requests'][4]['raw_reply']['unit_reviews']['u1']
        self.assertEqual(rejected['speech_act'],'observation')
        self.assertEqual(rejected['kind'],'request_summary')

        # Reproduce the old escape in a valid wire object: the shared JSON
        # shape accepts readable labels, then the product audit must reject the
        # attempt to mark the same H3 technical prose as a procedure.
        from test_quality_v28 import quoted_sample
        from casepilot.compact_review import descriptive_decode
        sample,case,evidence,_,_=quoted_sample()
        sample['next_step']=answer
        envelope=draft_units(sample,case['id'],case['revision'],0,include_quotes=True)
        spans=review_spans(case,evidence,sample['claims']); bound=contract(envelope,spans)
        source_alias=next(iter(bound['sources']))
        entries=[]
        for alias,unit in bound['units'].items():
            is_claim=unit['field'].startswith('claims.')
            entries.append({'unit_id':unit['unit_id'],'kind':'technical_claim' if is_claim else 'next_step',
                'support':'supported' if is_claim else 'unknown',
                'source_ids':[bound['sources'][source_alias]['span_id']] if is_claim else [],
                'message_ids':[],'premise':is_claim,'standalone':True,
                'reason':'بررسی: fixture بازتولید مسیر ممیزی را می‌سنجد.',
                'version_dependent':is_claim,'version_limit':sample['claims'][0]['version_limit'] if is_claim else '',
                'meaning':{'act':'technical' if is_claim else 'procedure',
                    'assertion_text':unit['text'] if is_claim else '', 'user_quote':'','depends_on':[]}})
        raw={'verdict':'accept','draft_version':envelope['draft_version'],
            'assessments':{k:{'score':2,'reason':'بررسی: fixture آفلاین.'} for k in CRITERIA},
            'unit_reviews':entries,
            'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: مورد تازه است.'}}
        wire=descriptive_fixture(encode_fixture(raw,bound))
        next_alias=next(k for k,u in bound['units'].items() if u['field']=='next_step')
        wire['unit_reviews'][next_alias].update(kind='next_step',speech_act='procedure',
            technical_assertion_range='none',version_dependent=False,source_aliases=[])
        with self.assertRaises(CasePilotError):descriptive_decode(wire,bound)

    def test_version_flag_false_cannot_hide_unknown_source_version_on_prose_claim(self):
        from test_quality_v28 import quoted_sample
        from casepilot.compact_review import descriptive_decode
        from casepilot.grounding import citation_limit
        answer, state, evidence, envelope, result = quoted_sample()
        answer['next_step'] = 'اقدام: گزینهٔ `runner.enforceSerializableSessionState` در فایل پیکربندی فعال می‌شود.'
        envelope = draft_units(answer, state['id'], state['revision'], 0, include_quotes=True)
        spans = review_spans(state, evidence, answer['claims'])
        c = contract(envelope, spans)
        result = copy.deepcopy(result)
        result['draft_version'] = envelope['draft_version']
        source_id = spans['sources'][0]['span_id']
        for entry, unit in zip(result['unit_reviews'], envelope['units']):
            entry['unit_id'] = unit['unit_id']
            if unit['field']=='next_step':
                entry.update(kind='technical_claim',support='supported',source_ids=[source_id],premise=True,
                    version_dependent=False,version_limit='',meaning={'act':'technical',
                    'assertion_text':unit['text'],'user_quote':'','depends_on':[]})
        wire = descriptive_fixture(encode_fixture(result, c))
        alias = next(k for k,u in c['units'].items() if u['field']=='next_step')
        source = next(s for s in c['sources'])
        wire['unit_reviews'][alias]['kind'] = 'technical_claim'
        wire['unit_reviews'][alias]['speech_act'] = 'technical'
        from casepilot.compact_review import phrase_ranges
        unit=c['units'][alias]
        ranges=phrase_ranges(len(unit['phrases']))
        covering=[label for label,indexes in ranges.items() if indexes and
            unit['phrases'][indexes[0]][0]==0 and unit['phrases'][indexes[-1]][1]>=len(unit['text'])]
        wire['unit_reviews'][alias]['technical_assertion_range'] = unit['candidate_assertion_range']
        wire['unit_reviews'][alias]['support'] = 'supported'
        wire['unit_reviews'][alias]['source_aliases'] = [source]
        wire['unit_reviews'][alias]['version_dependent'] = False
        wire['unit_reviews'][alias]['visible_version_limit_range'] = 'none'
        # No server-derived warning was placed in this unit. The citation's own
        # warning cannot cover this new assertion in next_step.
        out = checked_semantic_review(descriptive_decode(wire,c), answer, evidence, state, envelope)
        self.assertNotEqual(out['verdict'], 'accept')
        self.assertTrue(any('نسخه' in finding['reason'] for finding in out['findings']))

        # Even a matching notice elsewhere in the same prose unit is not
        # enough when the judge leaves its dedicated limitation range empty.
        limit=citation_limit(evidence[0])
        answer['next_step']+='\n'+limit
        envelope=draft_units(answer,state['id'],state['revision'],1,include_quotes=True)
        spans=review_spans(state,evidence,answer['claims']);c=contract(envelope,spans)
        repeated=copy.deepcopy(result);repeated['draft_version']=envelope['draft_version']
        source_id=spans['sources'][0]['span_id']
        for entry,unit in zip(repeated['unit_reviews'],envelope['units']):
            entry['unit_id']=unit['unit_id']
            if unit['field']=='next_step':
                entry.update(source_ids=[source_id],version_limit=limit,
                    meaning={'act':'technical','assertion_text':unit['text'],
                        'user_quote':'','depends_on':[]})
        wire=descriptive_fixture(encode_fixture(repeated,c))
        alias=next(k for k,u in c['units'].items() if u['field']=='next_step')
        wire['unit_reviews'][alias]['visible_version_limit_range']='none'
        decoded=descriptive_decode(wire,c)
        next_step_id=next(u['unit_id'] for u in envelope['units'] if u['field']=='next_step')
        target=next(row for row in decoded['unit_reviews'] if row['unit_id']==next_step_id)
        self.assertFalse(target['version_dependent'])
        self.assertEqual(target['version_limit'],'')
        out=checked_semantic_review(decoded,answer,evidence,state,envelope)
        self.assertNotEqual(out['verdict'],'accept')
        self.assertTrue(any('نسخه' in finding['reason'] for finding in out['findings']))

    def test_active_product_flow_selects_ids_repairs_rechecks_and_renders_exact_quote(self):
        from casepilot.agent import Agent
        from casepilot.store import Store
        from casepilot.model import MetisClient
        from casepilot.accounting import Budget
        from casepilot.semantics import UNKNOWN
        from casepilot.compact_review import descriptive_schema

        report = 'درخواست قابلیت: فهرست هنگام انتخاب گروه، گزینه‌های همان گروه را نشان دهد؛ اندازهٔ ظرف ثابت بماند.'
        class NoEvidence:
            last_trace = {'embedding': {'usage': []}}
            def search(self, *args, **kwargs): return []

        class ScriptedClient(MetisClient):
            def __init__(self, budget_path):
                # Keep the real MetisClient.generate and the normal V2 pipeline;
                # replace only network boundaries with deterministic fixtures.
                self.model='fixture-model'; self.max_output=1200; self.calls=0
                self.last_usage={}; self.usage_history=[]; self.mode='live'; self.diagnostics=None
                self.budget=Budget(budget_path)
                self.turn_scope=None; self.report=report; self.judges=0
                self.initial_packet=None; self.initial_schema=None; self.repair_schemas=[]

            def _request(self, payload, **kwargs):
                self.calls += 1; self.last_usage={'provider_requests':0,'cost_usd':0,'kind':'chat'}
                packet=json.loads(payload['messages'][1]['content'])
                supplied_schema=payload['response_format']['json_schema']['schema']
                if self.initial_packet is None:
                    self.initial_packet=packet
                    self.initial_schema=supplied_schema
                else:
                    self.repair_schemas.append(copy.deepcopy(supplied_schema))
                section_ids=[row['section_id'] for row in packet['feature_report_sections']]
                return {'decision':'escalate','claims':[],'question':'',
                    'next_step':'اقدام: نگه‌دارنده شرط پذیرش را بررسی کند.',
                    'rationale':'هدف: درخواست روشن کاربر برای تصمیم طراحی نگه‌دارنده آماده می‌شود؛ جزئیات رفتار و شرط پذیرش در پیشنهاد آمده‌اند.',
                    'hypotheses':[],
                    'diagnostic':{'action':'','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''},
                    'feature_proposal':{'current_behavior':UNKNOWN,
                    'desired_behavior':'درخواست: API فعلی این رفتار را پشتیبانی نمی‌کند.',
                        'user_need':'نیاز: پیدا کردن گزینهٔ مربوط به گروه انتخاب‌شده.',
                        'constraints':'محدودیت درخواستی: اندازهٔ ظرف ثابت بماند.',
                        'acceptance_condition':'شرط پذیرش پیشنهادی: پس از انتخاب گروه، گزینه‌های همان گروه دیده شوند.',
                        'report_quotes':[section_ids[0]]}}

            def structured(self, role, prompt, packet, schema, max_tokens=800):
                self.calls += 1; self.last_usage={'provider_requests':0,'cost_usd':0,'kind':role}
                if role=='extract':
                    return {'facts':[],'completed_checks':[],'ambiguities':[],'experiment_events':[],
                        'investigation':{'intent':'feature_request','problem_summary':'فهرست گروهی',
                            'known_report_spans':[],'missing_detail':'','new_condition':'',
                            'suggested_question':'','acceptance_condition':''}}
                if role=='repair':
                    self.repair_schemas.append(copy.deepcopy(schema))
                    ids=schema['properties']['feature_proposal']['properties']['report_quotes']['items']['enum']
                    return {'decision':'escalate','claims':[],'question':'',
                        'next_step':'اقدام: نگه‌دارنده شرط پذیرش را بررسی کند.',
                        'rationale':'هدف: درخواست روشن کاربر برای تصمیم طراحی نگه‌دارنده آماده می‌شود؛ جزئیات رفتار و شرط پذیرش در پیشنهاد آمده‌اند.',
                        'hypotheses':[],
                        'diagnostic':{'action':'','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''},
                        'feature_proposal':{'current_behavior':UNKNOWN,
                            'desired_behavior':'درخواست: نمایش گزینه‌های همان گروه در فهرست.',
                            'user_need':'نیاز: پیدا کردن گزینهٔ مربوط به گروه انتخاب‌شده.',
                            'constraints':'محدودیت درخواستی: اندازهٔ ظرف ثابت بماند.',
                            'acceptance_condition':'شرط پذیرش پیشنهادی: پس از انتخاب گروه، گزینه‌های همان گروه دیده شوند.',
                            'report_quotes':[ids[0]]}}
                if role!='judge': raise AssertionError(role)
                self.judges += 1
                envelope=packet['draft']; spans=packet['spans']; c=contract(envelope,spans)
                message_alias=next(alias for alias,row in c['messages'].items()
                    if row['text'] and row['text'] in report)
                entries=[]; desired_id=next(u['unit_id'] for u in envelope['units']
                    if u['field']=='feature_proposal.desired_behavior')
                for alias,unit in c['units'].items():
                    field=unit['field']; unknown=unit['text']==UNKNOWN
                    feature=field.startswith('feature_proposal.')
                    is_quote=field.startswith('feature_proposal.report_quotes.')
                    candidate=bool(unit['audit_candidates'])
                    act='unknown' if unknown else ('technical' if candidate else ('request' if feature else 'procedure'))
                    entry={'unit_id':unit['unit_id'],
                        'kind':'technical_claim' if candidate else ('request_summary' if feature else 'next_step'),
                        'support':'unknown' if unknown or candidate else ('supported' if feature else 'unknown'),
                        'source_ids':[],'message_ids':[] if unknown or candidate or not feature else [c['messages'][message_alias]['span_id']],
                        'premise':candidate,'standalone':True,'reason':'بررسی: متن با درخواست ثبت‌شده سنجیده شد.',
                        'version_dependent':False,'version_limit':'',
                        'meaning':{'act':act,'assertion_text':unit['text'] if candidate else '',
                            'user_quote':'' if unknown or candidate or not feature else report,
                            'depends_on':[desired_id] if is_quote else []}}
                    entries.append(entry)
                raw={'verdict':'repair' if self.judges==1 else 'accept',
                    'draft_version':envelope['draft_version'],
                    'assessments':{k:{'score':2,'reason':'بررسی: مورد کامل است.'} for k in CRITERIA},
                    'unit_reviews':entries,
                    'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'بررسی: درخواست روشن است.'}}
                wire=descriptive_fixture(encode_fixture(raw,c))
                check=descriptive_schema(c)
                from jsonschema import Draft202012Validator
                schema_errors=list(Draft202012Validator(check).iter_errors(wire))
                assert not schema_errors, [(list(error.absolute_path),error.message) for error in schema_errors]
                return wire

        with tempfile.TemporaryDirectory() as temp:
            client=ScriptedClient(Path(temp)/'budget.sqlite3'); store=Store(Path(temp)/'store.sqlite3')
            agent=Agent(store,client=client,hybrid=NoEvidence(),components={'rewrite':False,'rerank':False})
            out=agent.turn('active-quote-flow',report,'request-1')
            quote=out['summary']['handoff']['feature']['report_quotes'][0]
            self.assertIsNone(out['validation_error'])
            self.assertEqual(out['repair_count'],1)
            self.assertEqual(client.judges,2)
            self.assertEqual(quote['quote'],report)
            self.assertEqual(quote['text'],report)
            self.assertEqual(quote['offset_unit'],'unicode_codepoint')
            self.assertEqual(report[quote['start_char']:quote['end_char']],report)
            self.assertIn(quote['message_id'],out['response'])
            self.assertIn(report,out['response'])
            selected=client.initial_packet['feature_report_sections'][0]['section_id']
            initial=client.initial_schema['properties']['feature_proposal']['properties']['report_quotes']
            repaired=client.repair_schemas[0]['properties']['feature_proposal']['properties']['report_quotes']
            self.assertEqual(initial['items']['enum'],[selected])
            self.assertEqual(repaired['items']['enum'],[selected])
            self.assertEqual(store.get('active-quote-flow')['messages'][0]['text'],report)
            replayed=agent.turn('active-quote-flow',report,'request-1')
            self.assertTrue(replayed['request_replayed'])
            self.assertEqual(replayed['summary']['handoff']['feature']['report_quotes'][0],quote)


if __name__ == '__main__':
    unittest.main()
