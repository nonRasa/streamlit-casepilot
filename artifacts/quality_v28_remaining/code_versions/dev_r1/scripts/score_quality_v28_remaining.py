"""Score frozen V28 follow-up product runs; never tune on holdout output."""
import argparse
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,require
from casepilot.assertion_audit import candidates as assertion_candidates,covers
from casepilot.evidence import relation
from casepilot.grounding import citation_limit
from casepilot.report_quotes import validate as validate_report_quotes
from casepilot.evaluation_completion import candidate_key
from prepare_quality_v28_remaining import DATA,RUN,sha

HUMAN_FIELDS=('report_quote_lineage','report_quote_relevance','technical_claim_coverage',
    'selected_quote_support','version_limit_per_unit','answer_route_and_usefulness',
    'fresh_nonrepeated_question_or_test')


def dcg(grades):
    return sum((2**grade-1)/math.log2(rank+2) for rank,grade in enumerate(grades))


def quote_result(record,output,expected_route):
    feature=((output.get('summary') or {}).get('handoff') or {}).get('feature') or {}
    if expected_route!='feature_request' and not feature:
        return {'snapshot_exact_and_current':None,'exact_text_rendered':None,
            'semantic_detail_link_present':None,'quote_count':0,
            'passed_structural_and_semantic_gate':True}
    if not feature:
        return {'snapshot_exact_and_current':False,'exact_text_rendered':False,
            'semantic_detail_link_present':False,'quote_count':0,
            'passed_structural_and_semantic_gate':False}
    state=record.get('state') or {}
    quotes=feature.get('report_quotes',[])
    try:
        validate_report_quotes(feature,state)
        exact=True
    except Exception:
        exact=False
    displayed=all(isinstance(row,dict) and row.get('quote') and row['quote'] in output.get('response','')
        for row in quotes)
    draft=output.get('reviewed_draft') or {}
    review=output.get('judge') or {}
    units={row['field']:row for row in draft.get('units',[])}
    meanings=review.get('meanings',{})
    valid=set(review.get('valid_unit_ids',[]))
    linked=True
    for index,quote in enumerate(quotes):
        unit=units.get('feature_proposal.report_quotes.'+str(index))
        if not unit or unit['unit_id'] not in valid:
            linked=False;continue
        meaning=meanings.get(unit['unit_id'],{})
        if quote.get('quote') not in meaning.get('user_quote',''):
            linked=False;continue
        targets=meaning.get('depends_on',[])
        if not any(field.startswith('feature_proposal.') and
                    not field.startswith('feature_proposal.report_quotes.') and
                    other.get('unit_id') in targets and
                    meanings.get(other['unit_id'],{}).get('user_quote') and
                    meanings[other['unit_id']]['user_quote'] in quote.get('quote','')
                    for field,other in units.items()):
            linked=False
    return {'snapshot_exact_and_current':exact,'exact_text_rendered':displayed,
        'semantic_detail_link_present':linked,'quote_count':len(quotes),
        'passed_structural_and_semantic_gate':exact and displayed and linked}


def candidate_result(record,output):
    draft=output.get('reviewed_draft') or {}; review=output.get('judge') or {}
    units=draft.get('units',[]); entries={row.get('unit_id'):row for row in review.get('unit_reviews',[])}
    meanings=review.get('meanings',{}); valid=set(review.get('valid_unit_ids',[]))
    spans={row['span_id']:row for row in review.get('source_spans',[])}
    citations={row.get('evidence_id'):row for row in (output.get('summary') or {}).get('sources',[])}
    facts=(record.get('state') or {}).get('facts',{})
    assessed=[]
    for unit in units:
        candidates=assertion_candidates(unit.get('audited_text',unit['text']),unit['field'])
        for candidate in candidates:
            uid=unit['unit_id'];entry=entries.get(uid,{});meaning=meanings.get(uid,{})
            source_evidence={spans[sid]['evidence_id'] for sid in entry.get('source_ids',[]) if sid in spans}
            selected=source_evidence&set(citations)
            full_coverage=covers(candidate,meaning.get('assertion_text',''))
            nonexact=[]
            for eid in selected:
                citation=citations[eid]
                row={'product_version':citation.get('product_version')}
                rel=relation(row,facts.get('streamlit_version'))
                if rel!='exact':
                    limit=citation_limit(dict(row,version_relation=rel))
                    nonexact.append({'evidence_id':eid,'relation':rel,
                        'visible_in_this_unit':limit in unit['text'] and entry.get('version_limit')==limit})
            supported=(entry.get('support')=='supported' and bool(selected) and
                meaning.get('act')=='technical' and full_coverage and uid in valid and
                all(row['visible_in_this_unit'] for row in nonexact))
            assessed.append({'unit_id':uid,'field':unit['field'],'candidate':candidate['text'],
                'kind':entry.get('kind'),'speech_act':meaning.get('act'),
                'assertion_range_covers_candidate':full_coverage,
                'selected_output_source_ids':sorted(selected),'support_label':entry.get('support'),
                'unit_valid':uid in valid,'version_checks':nonexact,'gate_passed':supported})
    return {'candidate_count':len(assessed),'candidate_gate_pass_count':sum(row['gate_passed'] for row in assessed),
        'all_candidates_pass':all(row['gate_passed'] for row in assessed),
        'candidate_reviews':assessed}


def retrieval_result(record,label):
    candidates=record.get('initial_candidates',[]); context=record.get('packed_context',[])
    required=label.get('required_evidence',[])
    relevant={row['source_id'] for row in required}
    candidate_sources={row.get('source_id') for row in candidates}
    context_sources={row.get('source_id') for row in context}
    candidate_witness=sum(any(row.get('source_id')==gold['source_id'] and gold['quote'] in row.get('text','')
        for row in candidates) for gold in required)
    context_witness=sum(any(row.get('source_id')==gold['source_id'] and gold['quote'] in row.get('text','')
        for row in context) for gold in required)
    facts=(record.get('state') or {}).get('facts',{})
    return {'recall_at_8_known_relevant_sources':len(candidate_sources&relevant)/len(relevant) if relevant else None,
        'candidate_exact_witness_coverage':candidate_witness/len(required) if required else None,
        'packed_context_exact_witness_coverage':context_witness/len(required) if required else None,
        'candidate_count':len(candidates),'packed_context_source_ids':sorted(context_sources),
        'unknown_version_sources':sum(row.get('version_relation')=='unknown' for row in context),
        'mismatched_version_sources':sum(row.get('version_relation')=='mismatch' for row in context),
        'context_tokens':record.get('packing',{}).get('used_tokens'),
        'context_budget_tokens':record.get('packing',{}).get('budget_tokens'),
        'context_budget_ok':record.get('packing',{}).get('used_tokens',10**9)<=record.get('packing',{}).get('budget_tokens',0),
        # nDCG/irrelevant-pool metrics require complete independent grades.
        'ndcg_at_8':None,'judged_irrelevant_fraction':None,
        'candidate_judgment_coverage':0,'relevance_labels_pending':True}


def human_reviews():
    packet=read_json(RUN/'human_review_blind.json')
    key=read_json(RUN/'human_review_key.json')
    require(packet['suite_manifest_sha256']==sha(DATA/'manifest.json') and
        key['suite_manifest_sha256']==sha(DATA/'manifest.json') and
        packet['holdout_code_hash']==key['holdout_code_hash'],
        'review_suite_mismatch','فرم انسانی برای مجموعهٔ دیگری است.')
    responses=read_json(RUN/'human_review_completed.json') if (RUN/'human_review_completed.json').exists() else {}
    answer_key={row['blind_id']:row for row in key['answer_items']}
    answer_forms={row['blind_id']:row.get('review_form',{}) for row in packet['answer_items']}
    answer_status={}
    for blind_id,meta in answer_key.items():
        form=responses.get('answer_items',{}).get(blind_id,answer_forms[blind_id])
        path=RUN/'turns'/meta['artifact']
        valid_hash=path.exists() and sha(path)==meta['artifact_sha256']
        answer_status[blind_id]={'case_id':meta['case_id'],'variant':meta['variant'],
            'artifact_hash_valid':valid_hash,
            'complete':valid_hash and all(form.get(name)=='pass' for name in HUMAN_FIELDS)}
    grades={}; pool_pending=0; pool_count=0
    retrieval_key={row['evidence_alias']:row for row in key['retrieval_candidates']}
    for pool in packet['retrieval_pools']:
        edited={row['evidence_alias']:row for row in pool['review_form']['candidate_grades']}
        filled=responses.get('retrieval_pools',{}).get(pool['blind_pool_id'],{}).get('candidate_grades',{})
        for item in pool['review_form']['candidate_grades']:
            alias=item['evidence_alias'];pool_count+=1
            form=filled.get(alias,edited.get(alias,{}))
            grade=form.get('relevance_grade')
            if type(grade) is int and 0<=grade<=3:
                grades[(retrieval_key[alias]['case_id'],retrieval_key[alias]['candidate_key'])]=grade
            else:pool_pending+=1
    return answer_status,grades,{'retrieval_judgments_complete':pool_count>0 and pool_pending==0,
        'judged_candidates':pool_count-pool_pending,'candidate_pool_size':pool_count}


def score(split,round_number):
    selection=read_json(RUN/'selection.json') if (RUN/'selection.json').exists() else None
    if split=='holdout':
        require(selection is not None,'holdout_unselected','نسخهٔ توسعه باید پیش از ارزیابی نهایی منجمد شود.')
    labels=read_json(DATA/(split+'_labels.json')); label_map={row['id']:row for row in labels}
    run_label='holdout_r0' if split=='holdout' else 'dev_r'+str(round_number)
    records=[]
    for path in sorted((RUN/'turns').glob(run_label+'_*.json')):
        if path.name.endswith('_connection_retry.json'):continue
        record=read_json(path); label=label_map.get(record['case_id'])
        if label is None:continue
        if split=='holdout':
            require(record['code_hash']==selection['active_hash'],'holdout_hash_mismatch',
                'نسخهٔ محصول با snapshot منتخب development یکسان نیست.')
        output=record.get('output') or {}; failures=output.get('review_failures',[])
        contract_failure=any(row.get('kind')=='judge_contract' for row in failures)
        completed=record.get('failure') is None and output
        answer={'turn_completed':bool(completed),'failure':record.get('failure'),
            'validation_error':output.get('validation_error'),
            'contract_failure':contract_failure,
            'content_rejection':output.get('outcome')=='content_rejected',
            'product_accepted':bool(completed and output.get('validation_error') is None),
            'request_type':output.get('request_type'),
            'expected_route':label['expected_route'],
            'route_match':output.get('request_type')==label['expected_route'],
            'report_quote':quote_result(record,output,label['expected_route']),
            'technical_claim_coverage':candidate_result(record,output)}
        records.append({'case_id':record['case_id'],'variant':record['variant'],'index':record['index'],
            'code_hash':record['code_hash'],'answer':answer,
            'retrieval':retrieval_result(record,label),
            'requests':len(record.get('requests',[])),
            'provider_requests':sum(row.get('usage',{}).get('provider_requests',0) for row in record.get('requests',[])),
            'charged_or_reserved_usd':sum(row.get('usage',{}).get('cost_usd',0)+row.get('usage',{}).get('reserved_usd',0)
                for row in record.get('requests',[]))})
    answer_reviews,grades,human_coverage=human_reviews() if split=='holdout' and (RUN/'human_review_blind.json').exists() else ({},{},{'retrieval_judgments_complete':False,'judged_candidates':0,'candidate_pool_size':0})
    for row in records:
        if split=='holdout':
            matching=[value for value in answer_reviews.values() if value['case_id']==row['case_id'] and value['variant']==row['variant']]
            row['independent_human_review_complete']=bool(matching and matching[0]['complete'])
        else:row['independent_human_review_complete']=False
        candidates=read_json(RUN/'turns'/(run_label+'_'+row['case_id']+'_'+row['variant']+'.json')).get('initial_candidates',[])
        selected=[grades.get((row['case_id'],candidate_key(item))) for item in candidates[:8]]
        if selected and all(grade is not None for grade in selected):
            label_pool=[grade for (case_id,_),grade in grades.items() if case_id==row['case_id']]
            ideal=sorted(label_pool,reverse=True)[:8];denom=dcg(ideal)
            row['retrieval']['ndcg_at_8']=dcg(selected)/denom if denom else None
            row['retrieval']['candidate_judgment_coverage']=len(selected)/len(candidates[:8])
            row['retrieval']['judged_irrelevant_fraction']=sum(grade==0 for grade in selected)/len(selected)
            row['retrieval']['relevance_labels_pending']=False
    strict_runs=(len(records)==4 and all(row['answer']['product_accepted'] and
        row['answer']['route_match'] and row['answer']['report_quote']['passed_structural_and_semantic_gate'] and
        row['answer']['technical_claim_coverage']['all_candidates_pass'] and
        row['independent_human_review_complete'] for row in records)) if split=='holdout' else False
    report={'split':split,'development_round':round_number if split=='dev' else None,
        'selected_code_hash':selection['active_hash'] if selection else None,
        'turns':records,'human_review_status':human_coverage,
        'overall_quality_success':strict_runs,
        'quality_success_rule':'Holdout فقط: چهار اجرای کامل، پذیرش محصول، مسیر درست، snapshot و پیوند نقل‌قول معتبر، پوشش همهٔ نامزدهای فنی و فرم انسانی کامل برای هر چهار خروجی. داوری کامل nDCG مستقل گزارش می‌شود و با کیفیت پاسخ یکی نیست.'}
    write_json(RUN/(split+'_score.json'),report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('split',choices=['dev','holdout'])
    parser.add_argument('--round',type=int,default=0)
    args=parser.parse_args()
    result=score(args.split,args.round)
    print('turns='+str(len(result['turns']))+' quality_success='+str(result['overall_quality_success']))
