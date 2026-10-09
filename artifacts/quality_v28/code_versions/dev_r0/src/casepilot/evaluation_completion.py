"""Judgment-aware evaluator metrics; never imported by production roles.

Unjudged candidates are missing observations, not negative relevance labels.
Scores needing complete judgments are null until coverage is complete. The
condensed score is explicitly diagnostic, not an ordinary nDCG replacement.
"""
import math
from .common import digest


def candidate_key(row):
    return digest({'source':row['source_id'],'revision':row.get('revision'),
                   'span':row.get('source_span',row.get('lines')),'text':row['text']})


def retrieval_scores(candidates,context,label,judgments,k=5,context_tokens=0,budget=3000):
    top=candidates[:k]
    grades=[judgments.get(candidate_key(r),{}).get('grade') for r in top]
    known=[g for g in grades if g is not None]
    required=label['required_evidence']
    relevant=set(label['relevance'])
    sources={r['source_id'] for r in top}
    def coverage(rows):
        return (sum(any(r['source_id']==w['source_id'] and w['quote'] in r['text']
                        for r in rows) for w in required)/len(required)) if required else None
    # Chunk grades are distinct evidence relevance; repeated exact chunks were
    # deduplicated in the pool. IDCG is pooled, not variant-specific.
    ideal=sorted([j['grade'] for j in judgments.values() if j.get('grade') is not None],reverse=True)[:k]
    def dcg(gs): return sum((2**g-1)/math.log2(i+2) for i,g in enumerate(gs))
    denominator=dcg(ideal)
    ndcg=dcg(grades)/denominator if denominator and len(known)==len(top) else None
    return {'recall_at_k':len(sources&relevant)/len(relevant) if relevant else None,
            'ndcg_at_k':ndcg,'condensed_ndcg_diagnostic':dcg(known)/denominator if denominator else None,
            'judgment_coverage':len(known)/len(top) if top else 1,
            'unjudged_candidates':len(top)-len(known),
            'judged_irrelevant_fraction':sum(g==0 for g in known)/len(known) if known else None,
            'candidate_witness_coverage_at_k':coverage(top),
            'context_witness_coverage':coverage(context),
            'known_version_mismatches':sum(r.get('version_relation')=='mismatch' for r in context),
            'unknown_versions':sum(r.get('version_relation')=='unknown' for r in context),
            'context_tokens':context_tokens,'context_budget_ok':context_tokens<=budget,
            'source_ids':[r['source_id'] for r in top]}


def classify_failure(code,structural_valid=False):
    if code is None: return None
    if code=='model_output_incomplete': return 'truncation'
    if code.startswith('provider_'): return 'gateway'
    if code=='model_output_invalid': return 'json_syntax'
    if code in ('invalid_judge','judge_contract_error'):
        return 'semantic_consistency' if structural_valid else 'schema_or_reference'
    if code in ('budget_exhausted','turn_budget_exhausted','call_limit','turn_timeout','campaign_request_limit'):
        return 'resource_limit'
    return 'internal'
