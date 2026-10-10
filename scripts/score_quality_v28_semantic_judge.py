"""Per-unit provisional semantic metrics, separate from schema and guard outcomes."""
import argparse
import json
import hashlib
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import digest

RUN=ROOT/'artifacts/quality_v28_semantic_judge'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def spans_cover(witness, selected):
    cursor=witness['start']
    for row in sorted(selected,key=lambda r:r['start']):
        if row.get('message_index')!=witness.get('message_index'):continue
        if row['start']<=cursor<row['end']:cursor=max(cursor,row['end'])
    return cursor>=witness['end']


def score(phase,destination):
    dest=Path(destination)
    if dest.exists():raise FileExistsError(str(dest))
    data=ROOT/'eval/quality_v28_semantic_judge'/('suite_v2' if phase=='baseline' else 'suite_v3')
    split='holdout' if phase=='holdout' else 'dev'
    labels={r['id']:r for r in read(data/(split+'_labels.json'))}
    cases={r['id']:r for r in read(data/(split+'_inputs.json'))}
    items=[]
    for path in sorted((RUN/'phases'/phase).glob('[DH]*_?.json')):
        row=read(path);ref=labels[row['id']];case=cases[row['id']]
        assessment=row.get('assessment') or {};guard=assessment.get('guard')
        raw=row.get('raw_model_reply') or {};payload=row['payload']
        packet=json.loads(payload['messages'][1]['content']);aliases=packet['compact_contract']['units']
        uid_to_alias={r['unit_id']:a for a,r in aliases.items()}
        units=[]
        for expectation in ref['units']:
            alias=uid_to_alias.get(expectation['unit_id'])
            # Draft IDs depend on code version. Match by the exact field and text,
            # then bind to the unit actually sent, never to the reference's old ID.
            if alias is None:
                alias=next((a for a,u in aliases.items() if u['field']==expectation['field'] and
                    next(d['text'] for d in packet['draft']['units'] if d['unit_id']==u['unit_id'])==expectation['text']),None)
            actual=raw.get('unit_reviews',{}).get(alias) if alias else None
            selected_user=[];selected_sources=[]
            if actual:
                for m in actual.get('user_phrase_aliases',[]):
                    fragment=packet['compact_contract']['messages'].get(m)
                    if fragment:selected_user.append(fragment)
                source_ids={s['span_id']:s for s in packet['spans']['sources']}
                for s in actual.get('source_aliases',[]):
                    source=packet['compact_contract']['sources'].get(s)
                    source=source_ids.get(source) if isinstance(source,str) else source
                    if source:selected_sources.append(source)
            witness_status=None
            if expectation['exact_user_witnesses']:
                witness_status=all(spans_cover(w,selected_user) for w in expectation['exact_user_witnesses']) if actual else None
            if expectation['selected_source_witnesses']:
                witness_status=all(any(s['evidence_id']==w['evidence_id'] and s['text']==w['quote'] for s in selected_sources)
                    for w in expectation['selected_source_witnesses']) if actual else None
            expected_support=expectation['expected_support']
            allowed_support=[expected_support]
            if expectation['expected_act'] in ('procedure','diagnostic'):allowed_support=['unknown','supported']
            actual_uid=aliases[alias]['unit_id'] if alias else None
            units.append({'field':expectation['field'],'text':expectation['text'],'alias':alias,'unit_id':actual_uid,
                'expected_support':expected_support,'allowed_support':allowed_support,
                'actual_support':actual.get('support') if actual else None,
                'support_relation_correct':actual.get('support') in allowed_support if actual else None,
                'expected_act':expectation['expected_act'],'actual_act':actual.get('speech_act') if actual else None,
                'correct_witness_selection':witness_status,'selected_user_fragments':selected_user,
                'selected_sources':selected_sources,
                'structural_valid':expectation['structural_valid'],'quote_lineage_valid':expectation['quote_lineage_valid'],
                'expected_policy_valid':expectation['product_policy_valid'],
                'guard_unit_valid':actual_uid in guard.get('valid_unit_ids',[]) if guard and actual_uid else None,
                'reference_explanation':expectation['semantic_explanation']})
        outcome=raw.get('verdict');guard_outcome=guard.get('verdict') if guard else None
        semantic_valid=assessment.get('contract_valid') is True and not row.get('failure')
        # Initial fixture collection is diagnostically useful, but defective
        # positive references are excluded from definitive answer-error rates.
        reference_usable=phase!='baseline'
        invalid_model_units=[]
        for u in raw.get('unit_reviews',{}).values():
            bad=(u.get('support') in ('partial','contradicted') or
                 (u.get('support')=='unknown' and (u.get('speech_act')=='technical' or
                  (u.get('kind')=='request_summary' and u.get('speech_act')!='unknown'))))
            if bad:invalid_model_units.append(u)
        items.append({'id':row['id'],'family':ref['family'],'input_sha256':digest(case),
            'reference_status':'provisional agent authored, independently unreviewed' if reference_usable else 'fixture defect; diagnostic only',
            'reference_usable':reference_usable,'expected_accept':ref['expected_accept'],
            'model_verdict':outcome,'guard_verdict':guard_outcome,
            'semantic_metrics_eligible':semantic_valid,
            'contract_valid':assessment.get('contract_valid') if not row.get('failure') else None,
            'connection_or_provider_failure':row.get('failure'),
            'model_false_accept':outcome=='accept' and not ref['expected_accept'] if outcome and reference_usable and semantic_valid else None,
            'model_false_reject':outcome!='accept' and ref['expected_accept'] if outcome and reference_usable and semantic_valid else None,
            'guard_false_accept':guard_outcome=='accept' and not ref['expected_accept'] if guard_outcome and reference_usable else None,
            'guard_false_reject':guard_outcome!='accept' and ref['expected_accept'] if guard_outcome and reference_usable else None,
            'accept_with_rejected_model_units':outcome=='accept' and bool(invalid_model_units) if outcome and semantic_valid else None,
            'guard_findings':guard.get('findings') if guard else None,'units':units,
            'cost_usd':row.get('charged_or_reserved_usd'),'elapsed_seconds':row['elapsed_seconds']})
    metrics={}
    for name in ('model_false_accept','model_false_reject','guard_false_accept','guard_false_reject','accept_with_rejected_model_units'):
        rows=[x[name] for x in items if x[name] is not None]
        # Error rates use the appropriate positive/negative stratum denominator.
        if name.endswith('false_accept'):rows=[x[name] for x in items if not x['expected_accept'] and x[name] is not None]
        if name.endswith('false_reject'):rows=[x[name] for x in items if x['expected_accept'] and x[name] is not None]
        metrics[name]={'errors':sum(rows),'evaluated':len(rows),'rate':sum(rows)/len(rows) if rows else None}
    eligible_units=[u for x in items if x['semantic_metrics_eligible'] for u in x['units']]
    witnessed=[u for u in eligible_units if u['correct_witness_selection'] is not None]
    semantic_units=[u for u in eligible_units if u['expected_act'] in ('request','technical','observation')]
    metrics['unit_witness_selection']={'correct':sum(u['correct_witness_selection'] for u in witnessed),
        'evaluated':len(witnessed),'accuracy':sum(u['correct_witness_selection'] for u in witnessed)/len(witnessed) if witnessed else None}
    metrics['unit_support_relation']={'correct':sum(u['support_relation_correct'] for u in semantic_units),
        'evaluated':len(semantic_units),'accuracy':sum(u['support_relation_correct'] for u in semantic_units)/len(semantic_units) if semantic_units else None,
        'confusion':{expected:{actual:sum(u['expected_support']==expected and u['actual_support']==actual for u in semantic_units)
            for actual in ('supported','partial','contradicted','unknown')} for expected in ('supported','partial','contradicted','unknown')}}
    report={'phase':phase,'reference_is_independent':False,'independent_review_complete':False,
        'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reference_manifest_sha256':hashlib.sha256((data/'manifest.json').read_bytes()).hexdigest(),
        'input_artifact_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((RUN/'phases'/phase).glob('[DH]*_?.json'))},
        'metrics':metrics,'items':items,'per_family':{f:[x for x in items if x['family']==f] for f in sorted({x['family'] for x in items})},
        'quality_confirmed':False,'contract_errors':sum(x['contract_valid'] is False for x in items),
        'cost_usd':sum(x['cost_usd'] or 0 for x in items),
        'witness_metric_scope':'Exact selected catalog coverage; semantic support measured separately. A correct literal selection alone is not proof of relevance or entailment.',
        'interpretation':'Conditional on provisional unit references; connection/schema errors excluded from semantic denominators; guard failures are separate from raw verdict.'}
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['baseline','correction_1','correction_2','holdout']);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();r=score(a.phase,a.output);print(a.phase,'items',len(r['items']),'metrics',json.dumps(r['metrics']))
