"""بررسی گزارهٔ دقیق و منشأ؛ مدل داور مرجع حقیقت مستقل نیست."""
import re
from copy import deepcopy
from .common import require
from .review_contract import bound_review_schema, checked_review_v23, review_spans

FEATURE_KEYS=('current_behavior','desired_behavior','user_need','constraints','acceptance_condition')
UNKNOWN='نامعلوم: این مشخصه هنوز در پیشنهاد اعتبارسنجی نشده؛ نگه‌دارنده آن را تعیین کند.'
ASSERTION=re.compile(r'تضمین|علت قطعی|حتماً رفع|پشتیبانی می‌کند|پشتیبانی نمی‌کند|باعث.{0,40}(?:می‌شود|است)|guarantee|definitely fixes|(?:does not|currently) support',re.I)
BEHAVIOR=re.compile(r'علت|باعث|بازاجرا|rerun|non.responsive|واکنش|اندازه|دسترس|\bpx\b|accessib|WCAG|رفع|fix|cause|reset',re.I)

def semantic_schema(envelope,spans):
    from .roles import obj
    schema=bound_review_schema(envelope,spans)
    ids=[u['unit_id'] for u in envelope['units']]
    meaning=obj({'act':{'type':'string','enum':['request','observation','diagnostic','procedure','technical','unknown']},
        'assertion_text':{'type':'string'}, 'user_quote':{'type':'string'},
        'depends_on':{'type':'array','maxItems':3,'items':{'type':'string','enum':ids}}})
    for name in ('general','question','hypothesis','feature'):
        definition=schema['$defs'][name]
        definition['properties']['meaning']=deepcopy(meaning)
        definition['required'].append('meaning')
    return schema

def source_adequacy(unit,source):
    """قید منفی محدود: کد و نام کتابخانه شاهد اندازه یا علت نیستند."""
    text=source['text'].strip()
    lines=[s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith('```')]
    code_only=bool(lines) and all(re.match(r'(?:import |from |@|def |class |with |if |else:|return |st\.|\w+\s*=|#|[\[\]{}])',s) for s in lines)
    library_only=bool(re.search(r'glide.data.grid',text,re.I)) and not re.search(r'\b(?:px|target.size|WCAG|accessib|width|height)\b',text,re.I)
    if BEHAVIOR.search(unit) and (code_only or library_only):
        return 'unknown' if code_only else 'partial'
    return None

def checked_semantic_review(result,answer,evidence,state,envelope,forced=()):
    """حفظ قرارداد قبلی، همراه با عبارت قابل بازبینی برای پیش‌فرض و انتساب."""
    raw=deepcopy(result); meanings={}; extra=list(forced); vetoes={}
    units={u['unit_id']:u for u in envelope['units']}
    spans=review_spans(state,evidence,answer['claims'])
    messages={s['span_id']:s for s in spans['messages']}; sources={s['span_id']:s for s in spans['sources']}
    require(isinstance(raw,dict) and isinstance(raw.get('unit_reviews'),list),'judge_contract_error','واحدهای بررسی معتبر نیستند.')
    for entry in raw['unit_reviews']:
        require(isinstance(entry,dict) and isinstance(entry.get('unit_id'),str) and all(isinstance(entry.get(k),list) and all(isinstance(s,str) for s in entry[k]) for k in ('source_ids','message_ids')),'judge_contract_error','ساختار شاهدهای واحد معتبر نیست.')
        m=entry.pop('meaning',None); uid=entry.get('unit_id'); u=units.get(uid)
        require(u is not None and isinstance(m,dict) and set(m)=={'act','assertion_text','user_quote','depends_on'},'judge_contract_error','بررسی معنایی واحد ناقص یا منقضی است.')
        require(m['act'] in ('request','observation','diagnostic','procedure','technical','unknown') and all(isinstance(m[k],str) and len(m[k])<=1800 for k in ('assertion_text','user_quote')),'judge_contract_error','نوع گزاره معتبر نیست.')
        require(isinstance(m['depends_on'],list) and len(m['depends_on'])<=3 and all(isinstance(s,str) and s in units and s!=uid for s in m['depends_on']) and len(set(m['depends_on']))==len(m['depends_on']),'judge_contract_error','وابستگی واحد جعلی یا منقضی است.')
        require(not m['assertion_text'] or m['assertion_text'] in u['text'],'judge_contract_error','عبارت پیش‌فرض در واحد پاسخ نیست.')
        require(not m['user_quote'] or (len(m['user_quote'].strip())>=3 and any(m['user_quote'] in messages[s]['text'] for s in entry.get('message_ids',[]) if s in messages)),'judge_contract_error','انتساب به عبارت واقعی پیام مشخص متصل نیست.')
        meanings[uid]=m
        def defect(reason): extra.append({'criterion':'claim_support','unit_id':uid,'reason':'معنا: '+reason})
        if entry.get('premise') != bool(m['assertion_text']): defect('علامت پیش‌فرض با عبارت ادعای فنی سازگار نیست.')
        if m['act']=='technical' and not m['assertion_text']: defect('ادعای فنی باید عبارت دقیق داشته باشد.')
        if m['act'] in ('request','observation') and not m['user_quote'] and u['text']!=UNKNOWN: defect('درخواست یا مشاهده به عبارت مشخص کاربر متصل نیست.')
        if m['act']=='request' and ASSERTION.search(u['text']) and not m['assertion_text']: defect('برچسب درخواست، ادعای محصول یا علت را پنهان کرده است.')
        if m['act']=='observation' and entry.get('kind')!='reported_fact': defect('مشاهدهٔ کاربر باید نقل‌قول محصور و منتسب باشد.')
        if m['act']=='unknown' and u['text']!=UNKNOWN: defect('معنای این واحد نامعلوم است و قابل پذیرش قطعی نیست.')
        if u['field']=='feature_proposal.current_behavior' and u['text']!=UNKNOWN and not u['text'].startswith('گزارش کاربر:'): defect('رفتار فعلی باید صریحاً وصف کاربر باشد.')
        for sid in entry.get('source_ids',[]):
            if sid in sources:
                status=source_adequacy(u['text'],sources[sid])
                if status:
                    vetoes[uid]=status
                    defect('نوع شاهد از کل ادعای رفتار، علت یا اندازه پشتیبانی نمی‌کند؛ رابطه '+status+' است.')
    checked=checked_review_v23(raw,answer,evidence,state,envelope,extra)
    invalid={f['unit_id'] for f in extra if 'unit_id' in f}
    checked['valid_unit_ids']=[s for s in checked['valid_unit_ids'] if s not in invalid]
    # حذف وابستگی به واحد مردود تا رسیدن به مجموعهٔ پایدار.
    keep=set(checked['valid_unit_ids'])
    while True:
        reduced={s for s in keep if set(meanings[s]['depends_on'])<=keep}
        if reduced==keep: break
        keep=reduced
    checked['valid_unit_ids']=sorted(keep)
    source_ids={s['span_id']:s['evidence_id'] for s in spans['sources']}
    checked['linked_evidence_ids']=sorted({source_ids[s] for e in raw['unit_reviews'] if e['unit_id'] in keep and e['support']=='supported' for s in e['source_ids']})
    checked['orphan_evidence_ids']=sorted({c['evidence_id'] for c in answer['claims']}-set(checked['linked_evidence_ids']))
    for row in checked['unit_results']:
        row['valid']=row['unit_id'] in keep
        row['meaning']=meanings[row['unit_id']]
        row['model_semantic_support']=row['semantic_support']
        if row['unit_id'] in vetoes: row['semantic_support']=vetoes[row['unit_id']]
    if invalid and checked['failure_kind'] is None: checked['failure_kind']='answer_quality'
    if checked['verdict']!='accept' and 'unknown' in vetoes.values(): checked['failure_kind']='insufficient_evidence'
    checked['meanings']=meanings
    checked['message_spans']=spans['messages']
    return checked

def prepare_feature(answer,state):
    """فقط مقدار خالی را مجهول کن؛ هیچ مقدار یا ترجمه‌ای را جعل نکن."""
    from .routing import intent
    out=deepcopy(answer)
    if intent(state)=='feature_request':
        feature=out.get('feature_proposal')
        if isinstance(feature,dict):
            for k in FEATURE_KEYS:
                if k in feature and not feature[k].strip(): feature[k]=UNKNOWN
    return out

def feature_context(state):
    """بخش‌های دقیق گزارش برای تولید؛ عنوان خالی اطلاعات محسوب نمی‌شود."""
    sections=[]
    for index,message in enumerate(state.get('messages',[])):
        if message.get('role','user')!='user': continue
        text=message['text']; matches=list(re.finditer(r'(?m)^#{1,4}\s+(.+)$',text))
        for i,m in enumerate(matches):
            end=matches[i+1].start() if i+1<len(matches) else len(text)
            body=text[m.end():end].strip()
            if body and body.casefold() not in ('_no response_','n/a') and not re.search(r'checklist',m[1],re.I):
                sections.append({'message_index':index,'heading':m[1],'quote':body[:1800],'reported_only':True})
    return sections[-12:]

def recompose_semantic(answer,review,envelope,state):
    from .routing import intent
    from .review_contract import recompose
    keep=set(review['valid_unit_ids']) & {e['unit_id'] for e in review['unit_reviews'] if e['standalone']}
    while True:
        reduced={s for s in keep if set(review.get('meanings',{}).get(s,{}).get('depends_on',[]))<=keep}
        if reduced==keep: break
        keep=reduced
    if intent(state)!='feature_request': return recompose(answer,dict(review,valid_unit_ids=sorted(keep)),envelope,state)
    fields={u['field'] for u in envelope['units'] if u['unit_id'] in keep}
    if 'feature_proposal.desired_behavior' not in fields: return None
    out=deepcopy(answer); feature=out.get('feature_proposal') or {}
    for key in FEATURE_KEYS:
        if 'feature_proposal.'+key not in fields: feature[key]=UNKNOWN
    out['feature_proposal']=feature
    preserve_rationale='rationale' in fields and not any(f['criterion']=='next_step_usefulness' for f in review['findings'])
    source_map={s['span_id']:s['evidence_id'] for s in review.get('source_spans',[])}
    retained_ids={e['unit_id'] for e in review['unit_reviews'] if e['unit_id'] in keep and
                  (preserve_rationale or not any(u['unit_id']==e['unit_id'] and u['field']=='rationale' for u in envelope['units']))}
    retained_sources={source_map[s] for e in review['unit_reviews'] if e['unit_id'] in retained_ids for s in e['source_ids'] if s in source_map}
    out.update(decision='escalate',question='',claims=[c for c in out['claims'] if c['evidence_id'] in retained_sources],
        hypotheses=[h for i,h in enumerate(out['hypotheses']) if 'hypotheses.'+str(i) in fields],
        rationale=out['rationale'] if preserve_rationale else 'محدودیت: پیشنهاد شرح درخواست کاربر است؛ وجود رابط، علت یا امکان‌پذیری فنی تأیید نشده است.',
        next_step='اقدام: نگه‌دارنده دربارهٔ افزودن این رفتار تصمیم طراحی بگیرد: '+feature['desired_behavior']+'\nپذیرش: '+feature['acceptance_condition'],
        diagnostic={'action':'','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''})
    return out if out!=answer else None
