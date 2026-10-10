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

def clear_feature(state):
    plan=state.get('investigation_plan',{})
    return case_kind(state)=='feature_request' and not plan.get('missing_detail') and not plan.get('suggested_question')


def reported_current_options(state):
    from .semantics import UNKNOWN
    options=[UNKNOWN]
    for message in state.get('messages',[]):
        if message.get('role','user')!='user':continue
        for sentence in re.split(r'(?<=[.!?؟])\s+|\n',message['text']):
            if len(sentence)<=500 and re.search(r'\bdefault\b|\bcurrently\b|current behavior|پیش.?فرض|رفتار فعلی|در حال حاضر',sentence,re.I):
                options.append('گزارش کاربر:\n```text\n'+sentence+'\n```')
    return list(dict.fromkeys(options))


def selection_schema(state,quote_catalog=None,report_quote_catalog=None):
    from .model import QUALITY_SELECTION
    out=deepcopy(QUALITY_SELECTION)
    feature=out['properties']['feature_proposal']['properties']
    if case_kind(state) in ('bug','usage_question'):
        for k in FEATURE_KEYS: feature[k]={'type':'string','enum':['']}
        feature['report_quotes']['maxItems']=0
    if report_quote_catalog is not None:
        ids=[row['section_id'] for row in report_quote_catalog]
        if case_kind(state)!='feature_request' or not ids:
            feature['report_quotes']={'type':'array','maxItems':0,'items':{'type':'string'}}
        else:
            feature['report_quotes']={'type':'array','maxItems':4,
                'items':{'type':'string','enum':ids}}
    if case_kind(state)=='feature_request':
        feature['current_behavior']={'type':'string','enum':reported_current_options(state)}
    if quote_catalog is not None:
        choices=[]
        for evidence_id,quote_ids in quote_catalog.items():
            if quote_ids:
                choices.append({'type':'object','additionalProperties':False,'required':['evidence_id','quote_id'],
                    'properties':{'evidence_id':{'type':'string','enum':[evidence_id]},
                                  'quote_id':{'type':'string','enum':quote_ids}}})
        if choices:out['properties']['claims']['items']={'anyOf':choices}
        else:out['properties']['claims']['maxItems']=0
    if clear_feature(state):
        # A fully specified proposal has no open reporter question. This route
        # describes requested behavior; asserting existing technical support is
        # a different route. The semantic guard still checks every prose unit.
        out['properties']['decision']={'type':'string','enum':['escalate']}
        out['properties']['question']={'type':'string','enum':['']}
        out['properties']['rationale']={'type':'string','enum':[
            'هدف: درخواست روشن کاربر برای تصمیم طراحی نگه‌دارنده آماده می‌شود؛ جزئیات رفتار و شرط پذیرش در پیشنهاد آمده‌اند.']}
        out['properties']['claims']['maxItems']=0
        out['properties']['hypotheses']['maxItems']=0
    return out

def check_selection(answer,state,wire_schema=None,report_quote_catalog=None):
    if wire_schema is not None:
        from jsonschema import Draft202012Validator
        require(not any(Draft202012Validator(wire_schema).iter_errors(answer)),
                'case_type_contract_error','خروجی تولید با قالب دقیق ارسالی و شناسه‌های مجاز سازگار نیست.')
    if report_quote_catalog is not None:
        feature=(answer or {}).get('feature_proposal') if isinstance(answer,dict) else None
        ids=feature.get('report_quotes') if isinstance(feature,dict) else None
        allowed={row['section_id'] for row in report_quote_catalog}
        if case_kind(state) in ('bug','usage_question'):
            require(ids==[],'case_type_contract_error','درخواست غیرقابلیت نباید نقل‌قول گزارش قابلیت داشته باشد.')
        else:
            require(isinstance(ids,list) and len(ids)<=4 and all(isinstance(x,str) and x in allowed for x in ids),
                    'case_type_contract_error','نقل‌قول قابلیت باید شناسهٔ مجاز کاتالوگ جاری باشد.')
            require(len(ids)==len(set(ids)),'case_type_contract_error','شناسهٔ نقل‌قول تکراری است.')
    if case_kind(state) not in ('bug','usage_question'): return answer
    feature=answer.get('feature_proposal') if isinstance(answer,dict) else None
    require(isinstance(feature,dict) and set(feature)==set(FEATURE_KEYS)|{'report_quotes'} and
        all(feature[k]=='' for k in FEATURE_KEYS) and feature['report_quotes']==[],
        'case_type_contract_error','درخواست غیرقابلیت، مشخصات پیشنهاد قابلیت را خالی الزام می‌کند؛ اطلاعات گزارش محفوظ است.')
    return answer
