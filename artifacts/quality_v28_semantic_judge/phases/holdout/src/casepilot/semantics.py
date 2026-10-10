"""بررسی گزارهٔ دقیق و منشأ؛ مدل داور مرجع حقیقت مستقل نیست."""
import re, ast
from copy import deepcopy
from .common import require
from .evidence import relation
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
    for name in ('general','question','hypothesis','feature','feature_technical'):
        definition=schema['$defs'][name]
        definition['properties']['meaning']=deepcopy(meaning)
        definition['required'].append('meaning')
    return schema

def source_adequacy(unit,source):
    """قید منفی محدود: کد و نام کتابخانه شاهد اندازه یا علت نیستند."""
    text=source['text'].strip()
    lines=[s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith('```')]
    code_only=False
    if lines:
        # Parse syntax without executing it. A documentation sentence starting
        # with st.foo is prose, not a code block merely due to its prefix.
        body='\n'.join(line for line in text.splitlines() if not line.strip().startswith('```'))
        try:code_only=bool(ast.parse(body).body)
        except (SyntaxError,ValueError,RecursionError):pass
    library_only=bool(re.search(r'glide.data.grid',text,re.I)) and not re.search(r'\b(?:px|target.size|WCAG|accessib|width|height)\b',text,re.I)
    if BEHAVIOR.search(unit) and (code_only or library_only):
        return 'unknown' if code_only else 'partial'
    return None

def checked_semantic_review(result,answer,evidence,state,envelope,forced=()):
    """حفظ قرارداد قبلی، همراه با عبارت قابل بازبینی برای پیش‌فرض و انتساب."""
    raw=deepcopy(result); meanings={}; extra=list(forced); vetoes={}
    units={u['unit_id']:u for u in envelope['units']}; evidence_by_id={row['id']:row for row in evidence}
    from .assertion_audit import candidates as assertion_candidates, covers as covers_candidate
    report_quotes=((answer.get('feature_proposal') or {}).get('report_quotes',[])
                   if envelope.get('unit_contract')=='citation-units-v1' else [])
    spans=review_spans(state,evidence,answer['claims'],report_quotes=report_quotes)
    messages={s['span_id']:s for s in spans['messages']}; sources={s['span_id']:s for s in spans['sources']}
    require(isinstance(raw,dict) and isinstance(raw.get('unit_reviews'),list),'judge_contract_error','واحدهای بررسی معتبر نیستند.')
    for entry in raw['unit_reviews']:
        require(isinstance(entry,dict) and isinstance(entry.get('unit_id'),str) and all(isinstance(entry.get(k),list) and all(isinstance(s,str) for s in entry[k]) for k in ('source_ids','message_ids')),'judge_contract_error','ساختار شاهدهای واحد معتبر نیست.')
        m=entry.pop('meaning',None); uid=entry.get('unit_id'); u=units.get(uid)
        core={'act','assertion_text','user_quote','depends_on'}
        require(u is not None and isinstance(m,dict) and core<=set(m)<=core|{'user_phrases'},'judge_contract_error','بررسی معنایی واحد ناقص یا منقضی است.')
        if 'user_phrases' in m:
            phrases=m['user_phrases']
            require(isinstance(phrases,list) and len(phrases)<=3,'judge_contract_error','فهرست گزیده‌های منتخب معتبر نیست.')
            for phrase in phrases:
                require(isinstance(phrase,dict) and set(phrase)=={'span_id','message_index','start','end','text'} and
                    phrase['span_id'] in entry['message_ids'] and phrase['span_id'] in messages,
                    'judge_contract_error','گزیدهٔ منتخب متعلق به شاهد این واحد نیست.')
                parent=messages[phrase['span_id']]
                start,end=phrase['start'],phrase['end']
                require(type(start) is int and type(end) is int and parent['start']<=start<end<=parent['end'] and
                    phrase['message_index']==parent['message_index'] and
                    parent['text'][start-parent['start']:end-parent['start']]==phrase['text'],
                    'judge_contract_error','متن و بازهٔ گزیدهٔ منتخب با پیام اصلی یکسان نیست.')
        require(m['act'] in ('request','observation','diagnostic','procedure','technical','unknown') and all(isinstance(m[k],str) and len(m[k])<=1800 for k in ('assertion_text','user_quote')),'judge_contract_error','نوع گزاره معتبر نیست.')
        require(isinstance(m['depends_on'],list) and len(m['depends_on'])<=3 and all(isinstance(s,str) and s in units and s!=uid for s in m['depends_on']) and len(set(m['depends_on']))==len(m['depends_on']),'judge_contract_error','وابستگی واحد جعلی یا منقضی است.')
        require(not m['assertion_text'] or m['assertion_text'] in u['text'],'judge_contract_error','عبارت پیش‌فرض در واحد پاسخ نیست.')
        require(not m['user_quote'] or (len(m['user_quote'].strip())>=3 and any(m['user_quote'] in messages[s]['text'] for s in entry.get('message_ids',[]) if s in messages)),'judge_contract_error','انتساب به عبارت واقعی پیام مشخص متصل نیست.')
        meanings[uid]=m
        def defect(reason): extra.append({'criterion':'claim_support','unit_id':uid,'reason':'معنا: '+reason})
        candidate_spans=assertion_candidates(u.get('audited_text',u['text']),u['field'])
        if candidate_spans:
            expected_kind='hypothesis' if u['field'].startswith('hypotheses.') else 'technical_claim'
            if entry.get('kind')!=expected_kind or m['act']!='technical':
                defect('برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند.')
            if not all(covers_candidate(candidate,m['assertion_text']) for candidate in candidate_spans):
                defect('بازهٔ ادعای فنی تمام عبارت‌های فنی این واحد را پوشش نمی‌دهد.')
            if entry.get('support')!='supported' or not entry.get('source_ids'):
                defect('هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.')
        if entry.get('premise') != bool(m['assertion_text']): defect('علامت پیش‌فرض با عبارت ادعای فنی سازگار نیست.')
        if m['act']=='technical' and not m['assertion_text']: defect('ادعای فنی باید عبارت دقیق داشته باشد.')
        if m['act'] in ('request','observation') and not m['user_quote'] and u['text']!=UNKNOWN: defect('درخواست یا مشاهده به عبارت مشخص کاربر متصل نیست.')
        if m['act']=='request' and not m['assertion_text']:
            # Conditional desired behavior is a request; current availability,
            # a guaranteed fix or proved cause remains a factual assertion.
            pattern=(r'تضمین|علت قطعی|حتماً رفع|guarantee|definitely fixes|(?:در حال حاضر|هم.?اکنون|currently).{0,45}(?:پشتیبانی|support)'
                     if u['field'].startswith('feature_proposal.') and not u['field'].endswith('current_behavior') else ASSERTION.pattern)
            if re.search(pattern,u['text'],re.I):defect('برچسب درخواست، ادعای محصول یا علت را پنهان کرده است.')
        if u['field'].startswith('claims.'):
            quote=answer['claims'][int(u['field'].split('.')[1])]['quote']
            if quote not in m['assertion_text']:defect('کل نقل‌قول منتخب باید در پیش‌فرض بررسی شود؛ حذف بخشی از ادعا مجاز نیست.')
        if m['act']=='observation' and entry.get('kind')!='reported_fact' and \
                u['field']!='feature_proposal.current_behavior':
            defect('مشاهدهٔ کاربر باید نقل‌قول محصور و منتسب باشد.')
        if m['act']=='unknown' and u['text']!=UNKNOWN: defect('معنای این واحد نامعلوم است و قابل پذیرش قطعی نیست.')
        if u['field']=='feature_proposal.current_behavior' and u['text']!=UNKNOWN and not u['text'].startswith('گزارش کاربر:'): defect('رفتار فعلی باید صریحاً وصف کاربر باشد.')
        if u['field']=='feature_proposal.current_behavior':
            # A request to add a feature does not entail its present absence.
            # This narrow veto detects an explicit negative API/existence claim;
            # it does not require technical docs for a proposed capability.
            absence=r'وجود ندارد|موجود نیست|در دسترس نیست|does not exist|not available|there is no'
            if re.search(absence,u['text'],re.I) and not re.search(absence,'\n'.join(m['text'] for m in state.get('messages',[])),re.I):
                defect('نبود قابلیت موجود از درخواست افزودن آن استنتاج شده؛ چنین مشاهده‌ای در گزارش کاربر نیست.')
        for sid in entry.get('source_ids',[]):
            if sid in sources:
                status=source_adequacy(u['text'],sources[sid])
                if status:
                    vetoes[uid]=status
                    defect('نوع شاهد از کل ادعای رفتار، علت یا اندازه پشتیبانی نمی‌کند؛ رابطه '+status+' است.')
                source=evidence_by_id.get(sources[sid]['evidence_id'])
                if source and (candidate_spans or m['act'] in ('technical','hypothesis')) and \
                        relation(source,state.get('facts',{}).get('streamlit_version'))!='exact':
                    from .grounding import citation_limit
                    expected=citation_limit(source)
                    if not expected or expected not in u['text'] or expected not in entry.get('version_limit',''):
                        defect('محدودیت نسخه از منشأ شاهد برای همین ادعای فنی در بازهٔ محدودیت انتخاب نشده است.')
    # Check the message and proposal-field relation for each selected report quote.
    for u in envelope['units']:
        if not u['field'].startswith('feature_proposal.report_quotes.'):
            continue
        uid=u['unit_id']; entry=next(e for e in raw['unit_reviews'] if e['unit_id']==uid)
        quote_index=int(u['field'].rsplit('.',1)[1]); quote_rows=answer['feature_proposal']['report_quotes']
        quote=quote_rows[quote_index] if quote_index<len(quote_rows) else None
        meaning=meanings[uid]; connected=False
        # A selected message fragment may contain the whole report section,
        # including adjacent heading text. Both are exact, same-message spans;
        # containment direction is not a semantic relevance decision.
        def contained(left,right):return bool(left and right) and (left in right or right in left)
        if isinstance(quote,dict) and u['text']==quote.get('quote') and contained(meaning.get('user_quote'),quote['quote']):
            quote_messages=[messages[s] for s in entry.get('message_ids',[]) if s in messages]
            same_message=any(row.get('message_index')==quote.get('message_index') for row in quote_messages)
            if same_message:
                for dependency in meaning.get('depends_on',[]):
                    dep_unit=units.get(dependency); dep_meaning=meanings.get(dependency,{})
                    if (dep_unit and dep_unit['field'].startswith('feature_proposal.') and
                            not dep_unit['field'].startswith('feature_proposal.report_quotes.') and
                            contained(dep_meaning.get('user_quote'),quote['quote'])):
                        connected=True; break
        if not connected:
            extra.append({'criterion':'relevance','unit_id':uid,
                'reason':'منشأ گزارش: نقل‌قول باید با عبارت پیام اصلی و مشخصهٔ پیشنهادی مرتبط باشد.'})
    if answer['decision']=='ask' and isinstance(raw.get('novelty'),dict) and raw['novelty'].get('status')!='new':
        extra.append({'criterion':'avoids_repeated_check','reason':'تازگی: تازگی سؤال در کل سابقه تأیید نشده است.'})
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
    feature['report_quotes']=[q for i,q in enumerate(feature.get('report_quotes',[]))
        if 'feature_proposal.report_quotes.'+str(i) in fields]
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
        next_step='اقدام: نگه‌دارنده دربارهٔ افزودن رفتار درخواستی تصمیم طراحی بگیرد و شرط پذیرش پیشنهادی را بازبینی کند.',
        diagnostic={'action':'','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''})
    return out if out!=answer else None
