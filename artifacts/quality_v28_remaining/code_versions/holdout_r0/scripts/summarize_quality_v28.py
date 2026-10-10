"""Offline metrics and review packets for recorded real product turns."""
import sys,math,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest
from prepare_quality_v28 import RUN,DATA

def category(error):
    if error is None:return 'accepted'
    if error in ('judge_rejected','deterministic_review_failed','unsupported_answer'):return 'content_rejected'
    if error in ('judge_contract_error','invalid_judge','case_type_contract_error','invalid_citation','unsupported_quote'):return 'structural_rejected'
    return 'technical_unassessed'

def witness_present(row,witness,exact):
    return row.get('source_id',row.get('id'))==witness['source_id'] and (not exact or witness['quote'] in row['text'])

def retrieval_metrics(candidates,context,labels):
    refs=labels['required_evidence']
    if not refs:return {'reference_required':False,'source_recall_at_8':None,'exact_witness_recall_at_8':None,'exact_witness_context_coverage':None,'reference_ndcg_at_8':None}
    k=candidates[:8]
    ranks=[next((i+1 for i,r in enumerate(k) if witness_present(r,w,True)),None) for w in refs]
    # Deduplicate witness gains: overlapping chunks containing the SAME exact
    # reference do not create extra relevant documents or inflate DCG.
    gains=[];seen=set()
    for r in k:
        hits={i for i,w in enumerate(refs) if witness_present(r,w,True)}-seen
        gains.append(len(hits));seen.update(hits)
    ideal=sum(1/math.log2(i+2) for i in range(min(len(refs),len(k))))
    return {'reference_required':True,'source_recall_at_8':sum(any(witness_present(r,w,False) for r in k) for w in refs)/len(refs),
        'exact_witness_recall_at_8':sum(r is not None for r in ranks)/len(refs),
        'exact_witness_context_coverage':sum(any(witness_present(r,w,True) for r in context) for w in refs)/len(refs),
        'reference_ndcg_at_8':sum(g/math.log2(i+2) for i,g in enumerate(gains))/ideal if ideal else 0,
        'exact_witness_ranks':ranks,
        'ranking_scope':'Exact frozen reference only; not exhaustive relevance nDCG. Nonreference useful alternatives are unjudged.',
        'unjudged_nonreference_candidates':sum(not any(witness_present(r,w,False) for w in refs) for r in k)}

def metrics(record,label):
    out=record['output'] or {};error=record['failure'] or out.get('validation_error');kind=category(error)
    reviews=[x for x in out.get('pipeline',[]) if x['stage']=='judge'];requests=record['requests'];usage=record['usage']
    complete=bool(reviews) and kind not in ('structural_rejected','technical_unassessed')
    claims=out.get('summary',{}).get('sources',[])
    packed=any(x['stage']=='context_pack' for x in out.get('pipeline',[]))
    pack=record['packing'] if packed else None;draft=out.get('reviewed_draft')
    retrieval=retrieval_metrics(record['initial_candidates'],record['actual_context'],label)
    if not packed and retrieval['reference_required']:retrieval['exact_witness_context_coverage']=None
    if record['actual_query'] is None:
        retrieval={k:None if k not in ('reference_required',) else v for k,v in retrieval.items()}
    raw_verdicts=[x.get('raw_reply',{}).get('verdict',x.get('raw_reply',{}).get('v')) for x in requests if x['kind']=='judge' and isinstance(x.get('raw_reply'),dict)]
    return {'case_id':record['case_id'],'split':record['split'],'round':record['round'],'variant':record['variant'],
        'code_hash':record['code_hash'],'category':kind,'error':error,'contract_path_completed':complete,
        'product_gate_accepted':kind=='accepted','accepted_citations':len(claims),'quote_membership_valid':True if complete and claims else None,
        'raw_judge_verdicts':raw_verdicts,'checked_verdicts':[x['verdict'] for x in reviews],
        'guard_findings':[x['findings'] for x in reviews],
        'context_tokens':pack['used_tokens'] if pack else None,'context_budget_ok':pack['used_tokens']<=3000 if pack else None,
        'context_packing_items':pack.get('items',[]) if pack else None,
        'query_hash':digest(record['actual_query']),'candidate_hash':digest(record['initial_candidates']),
        'rerank_selection_hash':digest(next((x for x in out.get('pipeline',[]) if x['stage']=='rerank'),{})),
        'context_hash':digest(record['actual_context']),
        'retrieval':retrieval,
        'usage_cost':{'confirmed_usd':sum(x.get('cost_usd',0) for x in usage if x.get('provider_requests',0)>0 and not x.get('usage_unknown')),
            'unknown_reserved_usd':sum(x.get('reserved_usd',0) for x in usage if x.get('provider_requests',0)>0 and x.get('usage_unknown')),
            'provider_requests':sum(x.get('provider_requests',0) for x in usage),
            'cached_role_invocations':sum(x.get('mode')=='cached_live' for x in usage)},
        'latency_seconds':record['elapsed_seconds'],'reviewed_draft_available':bool(draft),
        'human_review':None,'independent_review':None,
        'final_content_metrics':{'unsupported_claims':None,'repeated_question_or_test':None,'route_fit':None,'usefulness_0_to_3':None},
        'final_content_explanation':'Detailed assistant adjudications separate from model/guard; a safe fallback is not a useful accepted answer.'}

def main():
    labels={x['id']:x for split in ('dev','holdout') for x in read_json(DATA/(split+'_labels.json'))}
    records={p.stem:read_json(p) for p in sorted((RUN/'turns').glob('*.json'))}
    results={stem:metrics(row,labels[row['case_id']]) for stem,row in records.items()}
    grouped={}
    for stem,r in results.items():
        key=r['split']+'_r'+str(r['round']);grouped.setdefault(key,[]).append(r)
    summary={group:{'nodes':len(rows),'categories':dict(collections.Counter(x['category'] for x in rows)),
        'contract_path_completed':sum(x['contract_path_completed'] for x in rows),
        'context_budget_ok':sum(x['context_budget_ok'] is True for x in rows),
        'confirmed_usd':sum(x['usage_cost']['confirmed_usd'] for x in rows),
        'unknown_reserved_usd':sum(x['usage_cost']['unknown_reserved_usd'] for x in rows)} for group,rows in grouped.items()}
    pairs=[]
    for stem,row in records.items():
        if row['variant']!='A' or row['retry_of']:continue
        other=records.get(stem[:-1]+'B')
        if not other:continue
        pairs.append({'pair':stem[:-2],'same_report':row['input_hash']==other['input_hash'],
            'same_query':row['actual_query']==other['actual_query'],'same_code':row['code_hash']==other['code_hash'],
            'same_extracted_facts':(row['state'] or {}).get('facts')==(other['state'] or {}).get('facts'),
            'same_investigation_plan':(row['state'] or {}).get('investigation_plan')==(other['state'] or {}).get('investigation_plan'),
            'candidate_inputs_differ':row['initial_candidates']!=other['initial_candidates'],
            'context_inputs_differ':row['actual_context']!=other['actual_context'],
            'interpretation':'Index changes candidate/context payloads; generated quote IDs and draft units may differ. Shared cache avoids identical calls; counts are not independent statistical replicates.'})
    write_json(RUN/'metrics.json',{'per_turn':results,'groups':summary,'paired_controls':pairs,
        'provider_requests':0,'human_review_completed':False,'independent_review_completed':False,
        'complete_relevance_ndcg':None,'nonreference_source_irrelevance':None,
        'warning':'Only exact-reference ranking is computed. Unknown relevance is not relabeled irrelevant; model verdict is not ground truth.'})
    packets=[]
    for stem,row in records.items():
        packets.append({'alias':'blind_'+digest(stem)[:12],'report':next(x['initial_message'] for x in read_json(DATA/(row['split']+'_inputs.json')) if x['id']==row['case_id']),
            'context':row['actual_context'],'draft':(row['output'] or {}).get('reviewed_draft'),
            'delivered_response':(row['output'] or {}).get('response'),
            'questions':'Check source relevance, factual entailment, version qualification, novelty across full report, proposal acceptance and useful next action.',
            'unsupported_claims':None,'repeated_question_or_test':None,'route_fit':None,'usefulness_0_to_3':None,'reviewer_origin':None})
    write_json(RUN/'human_review_blind.json',packets)
    write_json(RUN/'human_review_key.json',{p['alias']:stem for p,stem in zip(packets,records)})
    print(summary)

if __name__=='__main__':main()
