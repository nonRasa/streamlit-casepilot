"""Structural generator constraints; ambiguity preserves candidate information."""
from copy import deepcopy
import re
from .common import require
from .semantics import FEATURE_KEYS

def case_kind(state):
    planned=state.get('investigation_plan',{}).get('intent')
    text='\n'.join(m['text'] for m in state.get('messages',[]) if m.get('role','user')=='user').casefold()
    if planned not in ('bug','feature_request','usage_question','unknown','mixed'):
        feature=bool(re.search(r'feature request|enhancement request|add an option|درخواست قابلیت|قابلیت جدید',text))
        bug=bool(re.search(r'bug report|traceback|regression|crashes|raises \w*error|گزارش خطا|خطا می‌دهد|پسرفت',text))
        usage=bool(re.search(r'how (?:do|can|to)|usage question|چگونه|چطور',text))
        return 'mixed' if feature and bug else ('feature_request' if feature else ('bug' if bug else ('usage_question' if usage else 'unknown')))
    # نشانهٔ صریح متعارض با تشخیص خطا، مانع پاک‌کردن خودکار درخواست می‌شود.
    if planned=='bug' and any(x in text for x in ('feature request','درخواست قابلیت')): return 'mixed'
    return planned

def response_policy(state,evidence):
    kind=case_kind(state)
    objectives={
        'feature_request':'Describe the requested change and observable acceptance criteria; propose a concrete maintainer design decision. Do not ask for the already clear goal, an implementation or documentation of a proposed API.',
        'bug':'Answer with direct compatible evidence if sufficient. Otherwise ask exactly one genuinely missing detail or propose a specific new discriminating experiment; never infer cause from a similar issue.',
        'usage_question':'Give a directly evidenced usage procedure. If the required behavior is not documented, identify the exact missing goal/version detail without inventing an API.',
        'mixed':'Preserve both the reported fault and requested change, label each, and clarify only a missing detail that changes the next decision.',
        'unknown':'State the narrow ambiguity and ask one discriminating question; do not force a bug or feature classification.'}
    return {'request_type':kind,'evidence_state':'selected' if evidence else 'no_relevant_evidence',
            'objective':objectives[kind],
            'claim_rule':'Technical source-dependent assertions need evidence; a proposed new capability is a request, not an assertion of existing support.',
            'novelty_scope':'Entire user report, code, all prior messages, supplied checks and performed experiments; an absent extracted field is not a missing fact.'}

def selection_schema(state):
    from .model import QUALITY_SELECTION
    out=deepcopy(QUALITY_SELECTION)
    feature=out['properties']['feature_proposal']['properties']
    if case_kind(state)=='bug':
        for k in FEATURE_KEYS: feature[k]={'type':'string','enum':['']}
        feature['report_quotes']['maxItems']=0
    return out

def check_selection(answer,state):
    if case_kind(state)!='bug': return answer
    feature=answer.get('feature_proposal') if isinstance(answer,dict) else None
    require(isinstance(feature,dict) and set(feature)==set(FEATURE_KEYS)|{'report_quotes'} and
        all(feature[k]=='' for k in FEATURE_KEYS) and feature['report_quotes']==[],
        'case_type_contract_error','قرارداد خطای صرف، مشخصات پیشنهاد قابلیت را خالی الزام می‌کند؛ اطلاعات گزارش محفوظ است.')
    return answer
