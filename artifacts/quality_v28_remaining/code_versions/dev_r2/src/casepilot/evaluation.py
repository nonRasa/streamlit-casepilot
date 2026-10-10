"""Evaluator-side metrics. Production roles must never import reference labels."""
import math

def retrieval_metrics(rows,label,k=5,context_tokens=0,budget_tokens=3000):
    # Top k chunks; duplicates retain their rank but receive no duplicate gain.
    top=rows[:k]; ids=list(dict.fromkeys(r['source_id'] for r in top))
    relevant={s for s,g in label['relevance'].items() if g>0}
    irrelevant=set(label['judged_irrelevant_source_ids'])
    seen=set(); gains=[]
    for row in top:
        sid=row['source_id']; gains.append(label['relevance'].get(sid,0) if sid not in seen else 0); seen.add(sid)
    dcg=sum((2**g-1)/math.log2(i+2) for i,g in enumerate(gains))
    ideal=sum((2**g-1)/math.log2(i+2) for i,g in enumerate(sorted(label['relevance'].values(),reverse=True)[:k]))
    required=label['required_evidence']
    covered=sum(any(r['source_id']==w['source_id'] and w['quote'] in r['text'] for r in rows) for w in required)
    versions=[r.get('version_relation','unknown') for r in rows]
    return {'recall_at_k':len(set(ids)&relevant)/len(relevant) if relevant else None,
            'ndcg_at_k':dcg/ideal if ideal else None,
            'judged_irrelevant_fraction':len(set(ids)&irrelevant)/len(ids) if ids else 0,
            'unjudged_fraction':sum(s not in relevant|irrelevant for s in ids)/len(ids) if ids else 0,
            'required_evidence_coverage':covered/len(required) if required else None,
            'known_version_mismatches':versions.count('mismatch'),'unknown_versions':versions.count('unknown'),
            'context_tokens':context_tokens,'context_budget_ok':context_tokens<=budget_tokens,'source_ids':ids}

def answer_metrics(result,label,evaluation_kind='fixture'):
    review=result.get('judge') or {}; findings=review.get('findings',[])
    error=result.get('validation_error')
    return {'evaluation_kind':evaluation_kind,
            'contract_valid':False if error in ('judge_contract_error','invalid_judge','model_output_invalid','model_output_incomplete') else (True if review else None),
            'unsupported_claim_findings':sum(f.get('criterion')=='claim_support' for f in findings),
            'repeated_question_or_test_findings':sum(f.get('criterion')=='avoids_repeated_check' for f in findings),
            'route_fit':result.get('request_type')==label['expected_route'] if 'request_type' in result else None,
            'usefulness_human':None,'independent_review':None,
            'cost_usd':result.get('usage',{}).get('charged_or_reserved_usd',result.get('usage',{}).get('cost_usd',0)),
            'internal_error':result.get('outcome')=='internal_error',
            'limitations':'Counts are reported judge findings, not an independent semantic truth label; fixture acceptance is not model quality.'}
