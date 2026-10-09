"""Structural generator constraints; ambiguity preserves candidate information."""
from copy import deepcopy
from .common import require
from .semantics import FEATURE_KEYS

def case_kind(state):
    planned=state.get('investigation_plan',{}).get('intent')
    if planned not in ('bug','feature_request','usage_question','unknown','mixed'): return 'unknown'
    text='\n'.join(m['text'] for m in state.get('messages',[]) if m.get('role','user')=='user').casefold()
    # نشانهٔ صریح متعارض با تشخیص خطا، مانع پاک‌کردن خودکار درخواست می‌شود.
    if planned=='bug' and any(x in text for x in ('feature request','درخواست قابلیت')): return 'mixed'
    return planned

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
