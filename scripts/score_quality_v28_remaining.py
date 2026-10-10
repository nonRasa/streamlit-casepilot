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
    return {'recall_at_8_known_relevant_sources':len(candidate_sources&relevant)/len(relevant) if relevant and 'initial_candidates' in record else None,
        'candidate_exact_witness_coverage':candidate_witness/len(required) if required and 'initial_candidates' in record else None,
        'packed_context_exact_witness_coverage':context_witness/len(required) if required and 'packed_context' in record else None,
        'candidate_count':len(candidates) if 'initial_candidates' in record else None,'packed_context_source_ids':sorted(context_sources) if 'packed_context' in record else None,
        'unknown_version_sources':sum(row.get('version_relation')=='unknown' for row in context) if 'packed_context' in record else None,
        'mismatched_version_sources':sum(row.get('version_relation')=='mismatch' for row in context) if 'packed_context' in record else None,
        'context_tokens':record.get('packing',{}).get('used_tokens'),
        'context_budget_tokens':record.get('packing',{}).get('budget_tokens'),
        'context_budget_ok':(record['packing']['used_tokens']<=record['packing']['budget_tokens']) if all(k in (record.get('packing') or {}) for k in ('used_tokens','budget_tokens')) else None,
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
            **human_status(form,HUMAN_FIELDS,valid_hash)}
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


# Scoring is read-only with respect to historical runs. The stage-aware writer
# refuses existing destinations and records all input hashes.
from quality_v28_rescore import rescore, human_status


def score(split, round_number, destination=None):
    destination = destination or ROOT/'artifacts'/'quality_v28_offline_rescore'/('holdout' if split=='holdout' else 'dev_r'+str(round_number))
    return rescore(split, round_number, destination, retrieval_result, human_reviews)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('split',choices=['dev','holdout'])
    parser.add_argument('--round',type=int,default=0)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=score(args.split,args.round,args.output)
    print('turns='+str(len(result['turns']))+' historical_acceptances='+str(result['historical_acceptances']))
