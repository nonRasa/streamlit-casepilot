"""Offline, stage-bound measurements. No provider/client imports or replayed calls."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from casepilot.assertion_audit import candidates, covers
from casepilot.report_quotes import catalog, validate
from casepilot.common import digest
from casepilot.evidence import relation
from casepilot.grounding import citation_limit

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'artifacts/quality_v28_remaining'
DATA = ROOT/'eval/quality_v28_remaining'
VERSION = 'stage-bound-offline-v1'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def human_status(form, fields, hash_valid=True):
    complete = hash_valid and all(form.get(k) in ('pass', 'fail', 'not_applicable') for k in fields)
    return {'complete': complete,
            'accepted': all(form.get(k) == 'pass' for k in fields) if complete else None}


def quote_status(units, state, route, review=None, feature=None):
    rows = [u for u in units if u['field'].startswith('feature_proposal.report_quotes.')]
    if not rows:
        return {'status': 'not_selected' if route == 'feature_request' else 'not_required',
                'exact_text': None, 'snapshot_valid': None, 'semantic_relevance': None, 'quotes': []}
    try:
        sections = catalog(state) if state and isinstance(state.get('messages'),list) else None
    except Exception:
        sections = None
    results = []
    for unit in rows:
        matches = [s for s in sections or [] if s['text'] == unit['text']]
        results.append({'unit_id': unit['unit_id'], 'field': unit['field'], 'text': unit['text'],
            'status': 'unassessable' if sections is None else ('valid_exact' if matches else 'invalid'),
            'reason': 'state unavailable' if sections is None else (None if matches else 'not an exact selectable user section'),
            'matching_user_sections': matches,
            'historical_guard_unit_valid': unit['unit_id'] in review.get('valid_unit_ids', []) if review else None,
            'model_meaning': (review or {}).get('meanings', {}).get(unit['unit_id']),
            'semantic_relevance': None})
    snapshot = None; snapshot_reason = 'stored quote snapshot absent; exact membership does not recover original selection provenance'
    if feature is not None and state is not None:
        try:
            validate(feature, state); snapshot = True; snapshot_reason = None
        except Exception as exc:
            snapshot = False; snapshot_reason = str(exc)
    statuses = {r['status'] for r in results}
    status = 'invalid' if 'invalid' in statuses or snapshot is False else ('unassessable' if 'unassessable' in statuses else 'valid_exact')
    return {'status': status, 'exact_text': None if sections is None else all(r['status']=='valid_exact' for r in results),
            'snapshot_valid': snapshot, 'snapshot_reason': snapshot_reason,
            'semantic_relevance': None, 'quotes': results}


def coverage(payload, review, state, candidate_map):
    """Checks selected citations from THIS judge input, never final fallback sources.

    A model support label and a literal match are reported separately. Neither
    is promoted to independent entailment, relevance or a quality verdict.
    """
    units = payload.get('draft', {}).get('units', [])
    citations = payload.get('citations')
    spans = payload.get('spans', {}).get('sources')
    by_span = {s['span_id']: s for s in spans or []}
    entries = {e['unit_id']: e for e in (review or {}).get('unit_reviews', [])}
    findings = []
    for unit in units:
        for candidate in candidate_map.get(unit['unit_id'], []):
            entry = entries.get(unit['unit_id'])
            meaning = (review or {}).get('meanings', {}).get(unit['unit_id'])
            selected = []; versions = []; literal = None; bound = None
            if entry is not None and citations is not None and spans is not None:
                linked = [by_span.get(s) for s in entry.get('source_ids', [])]
                selected = [c for c in citations if any(s and s.get('evidence_id')==c.get('evidence_id') and s.get('text')==c.get('quote') for s in linked)]
                bound = bool(selected) and all(s is not None for s in linked)
                literal = all(s and any(c.get('evidence_id')==s.get('evidence_id') and c.get('quote')==s.get('text') for c in citations) for s in linked) if linked else False
                for source in linked if state is not None else []:
                    if not source: continue
                    rel = relation(source, (state or {}).get('facts', {}).get('streamlit_version'))
                    limit = citation_limit(dict(source, version_relation=rel)) if rel!='exact' else ''
                    versions.append({'evidence_id': source['evidence_id'], 'relation': rel,
                        'required_limit': limit,
                        'visible_in_same_unit': limit in unit['text'] if limit else True,
                        'selected_limit_covers_notice': limit in entry.get('version_limit', '') and entry.get('version_limit', '') in unit['text'] if limit else True})
            finding = {'unit_id': unit['unit_id'], 'field': unit['field'], 'candidate': candidate,
                'candidate_is_proven_unsupported': None,
                'assertion_range_covers_candidate': covers(candidate, meaning.get('assertion_text', '')) if meaning is not None else None,
                'selected_source_binding': bound, 'literal_selected_quote_match': literal,
                'selected_evidence_ids': [c['evidence_id'] for c in selected] if citations is not None and entry is not None else None,
                'model_support': entry.get('support') if entry else None,
                'model_speech_act': meaning.get('act') if meaning else None,
                'historical_guard_unit_valid': unit['unit_id'] in review.get('valid_unit_ids', []) if review else None,
                'independent_semantic_support': None, 'independent_source_relevance': None,
                'version_checks': versions if entry is not None and spans is not None and state is not None else None}
            findings.append(finding)
    complete = all(u['unit_id'] in candidate_map for u in units)
    return {'candidate_count': len(findings) if complete else None, 'candidate_catalog_complete': complete, 'candidate_reviews': findings,
            'semantic_quality_pass': None}


def judge_inputs(record):
    for i, request in enumerate(record.get('requests', [])):
        if request.get('kind') != 'judge': continue
        for m, message in enumerate(request.get('payload', {}).get('messages', [])):
            if message.get('role') != 'user': continue
            try: payload = json.loads(message['content'])
            except (ValueError, TypeError, KeyError): continue
            if 'draft' in payload:
                yield i, m, request, payload


def stage_record(record, payload, request, review, request_index, message_index):
    draft = payload['draft']; state = record.get('state')
    state_matches = bool(state and state.get('id')==draft.get('case_id') and state.get('revision')==draft.get('case_revision'))
    if review and review.get('draft_version') != draft.get('draft_version'): review = None
    contract = payload.get('compact_contract', {})
    old_candidates = {v['unit_id']: v.get('mandatory_claim_candidates', []) for v in contract.get('units', {}).values()}
    new_candidates = {u['unit_id']: candidates(u.get('audited_text', u['text']), u['field']) for u in draft['units']}
    historical = coverage(payload, review, state if state_matches else None, old_candidates)
    replay = coverage(payload, review, state if state_matches else None, new_candidates)
    quotes = quote_status(draft['units'], state if state_matches else None, record['output'].get('request_type'), review)
    return {'binding': {'draft_version': draft.get('draft_version'), 'case_id': draft.get('case_id'),
            'case_revision': draft.get('case_revision'), 'state_revision_matches': state_matches,
            'state_sha256': digest(state) if state else None, 'contract': contract.get('version'),
            'contract_binding': contract.get('binding'), 'selected_citations_sha256': digest(payload.get('citations')),
            'payload_path': f'$.requests[{request_index}].payload.messages[{message_index}].content (JSON)',
            'raw_verdict_path': f'$.requests[{request_index}].raw_reply'},
        'draft': {'units': draft['units'], 'report_quotes': quotes, 'selected_citations': payload.get('citations'),
                  'historical_candidate_coverage': historical},
        'judge_and_guard': {'raw_model_reply': request.get('raw_reply'),
            'guard_review': review, 'guard_available': review is not None,
            'model_semantic_quality_independently_verified': None},
        'local_control_replay': {'candidate_coverage_with_old_model_labels': replay,
            'changed_units': [{'unit_id': u['unit_id'], 'field': u['field'], 'text': u['text'],
                'historical_candidates': old_candidates.get(u['unit_id']), 'new_candidates': new_candidates[u['unit_id']]}
                for u in draft['units'] if old_candidates.get(u['unit_id']) != new_candidates[u['unit_id']]],
            'new_schema_model_output': 'not_evaluated', 'full_product_acceptance': None,
            'limitation': 'Old replies were constrained by historical schema. Only local candidate/coverage checks replayed; no regenerated judge, repair, recomposition or answer.'}}


def delivered(record, stages):
    output = record.get('output') or {}; summary = output.get('summary') or {}
    feature = (summary.get('handoff') or {}).get('feature') or {}
    # The handoff's reported_problem is user history, not a feature.report_quotes selection.
    units = [{'unit_id': 'delivered:'+str(i), 'field': 'feature_proposal.report_quotes.'+str(i),
              'text': q.get('quote', '')} for i,q in enumerate(feature.get('report_quotes', [])) if isinstance(q,dict)]
    quotes = quote_status(units, record.get('state'), output.get('request_type'), feature=feature if units else None)
    last = stages[-1] if stages else None
    if not units and last and last['draft']['report_quotes']['quotes']:
        quotes['status'] = 'removed_from_delivery'
    text = output.get('response')
    return {'binding': {'response_sha256': digest(text), 'summary_sha256': digest(summary),
                        'state_revision': (record.get('state') or {}).get('revision'),
                        'contract': None, 'contract_note': 'delivered text has no separately stored judge envelope'},
            'response': text, 'sources': summary.get('sources'), 'report_quotes': quotes,
            'local_candidates': candidates(text, 'delivered.response') if isinstance(text,str) else None,
            'candidate_note': 'Entire rendered response scanned; includes quoted user history and system status. Candidates are not confirmed product claims.',
            'independent_claim_coverage': None, 'usefulness': None,
            'fallback': output.get('validation_error') is not None if output else None,
            'draft_sources_removed': ([c.get('evidence_id') for c in last['draft']['selected_citations']
                if c.get('evidence_id') not in {s.get('evidence_id') for s in summary.get('sources', [])}]
                if last and last['draft']['selected_citations'] is not None and 'sources' in summary else None)}


def rescore(split, round_number, destination, retrieval_fn, human_fn):
    destination = Path(destination)
    if destination.exists(): raise FileExistsError('Refusing to overwrite a prior rescore: '+str(destination))
    prefix = 'holdout_r0' if split=='holdout' else 'dev_r'+str(round_number)
    labels_path = DATA/(split+'_labels.json'); labels = {r['id']:r for r in load(labels_path)}
    inputs = {str(labels_path.relative_to(ROOT)): sha(labels_path)}; rows = []
    humans, _, human_coverage = human_fn() if split=='holdout' else ({}, {}, {})
    for name in ('human_review_blind.json','human_review_key.json','human_review_completed.json'):
        path = RUN/name
        if path.exists(): inputs[str(path.relative_to(ROOT))]=sha(path)
    for path in sorted((RUN/'turns').glob(prefix+'_*.json')):
        record = load(path); trace_path = RUN/'traces'/path.name
        inputs[str(path.relative_to(ROOT))]=sha(path)
        traces = load(trace_path) if trace_path.exists() else []
        if trace_path.exists(): inputs[str(trace_path.relative_to(ROOT))]=sha(trace_path)
        reviews = {r['payload']['draft_version']:r['payload'] for r in traces if r.get('payload', {}).get('stage')=='judge' and 'draft_version' in r['payload']}
        output = record.get('output') or {}; last_review = output.get('judge') or {}
        if last_review.get('draft_version'): reviews[last_review['draft_version']]=last_review
        stages = [stage_record(record,p,req,reviews.get(p['draft'].get('draft_version')),i,m) for i,m,req,p in judge_inputs(record)]
        human = next((v for v in humans.values() if v['case_id']==record['case_id'] and v['variant']==record['variant']), {})
        rows.append({'artifact': str(path.relative_to(ROOT)), 'input_sha256': sha(path),
            'case_id':record['case_id'], 'variant':record['variant'], 'code_hash':record['code_hash'],
            'historical_outcome': {'product_accepted': bool(output and not record.get('failure') and output.get('validation_error') is None),
                'failure':record.get('failure'), 'validation_error':output.get('validation_error'),
                'outcome':output.get('outcome'), 'review_failures':output.get('review_failures'),
                'contract_error':any(f.get('kind')=='judge_contract' for f in output.get('review_failures',[])),
                'content_rejected': output.get('outcome')=='content_rejected'},
            'stages':stages, 'delivered':delivered(record,stages),
            'retrieval':retrieval_fn(record,labels[record['case_id']]),
            'human_review': {'complete':human.get('complete',False), 'accepted':human.get('accepted') if human.get('complete') else None},
            'historical_charged_or_reserved_usd':(record.get('turn_accounting') or {}).get('charged_or_reserved_usd')})
    report = {'version': VERSION, 'split':split, 'round':round_number,
        'input_hashes':inputs, 'implementation_hashes':{str(p.relative_to(ROOT)):sha(p) for p in
            [Path(__file__), ROOT/'scripts/score_quality_v28_remaining.py', ROOT/'src/casepilot/assertion_audit.py']},
        'turns':rows, 'historical_acceptances':sum(r['historical_outcome']['product_accepted'] for r in rows),
        'human_review_status':human_coverage, 'new_provider_requests':0, 'new_api_cost_usd':0,
        'real_quality_improvement':None, 'full_pipeline_replay':'not_evaluated'}
    # Verify every historical input is still byte-identical before publishing.
    assert all(sha(ROOT/p)==value for p,value in inputs.items())
    destination.mkdir(parents=True)
    (destination/'rescore.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    historical = deepcopy(report)
    replay_turns = []
    for turn in historical['turns']:
        replay_turns.append({'artifact':turn['artifact'], 'input_sha256':turn['input_sha256'],
            'stages':[{'binding':s['binding'], **s.pop('local_control_replay')} for s in turn['stages']]})
    replay = {k:v for k,v in report.items() if k not in ('turns','historical_acceptances','human_review_status')}
    replay.update(turns=replay_turns, mode='counterfactual_local_control_only', hypothetical_acceptances=None)
    for name, value in [('historical.json', historical), ('local_replay.json', replay)]:
        (destination/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report
