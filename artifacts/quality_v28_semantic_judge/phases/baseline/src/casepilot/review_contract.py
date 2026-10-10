"""Bind every reviewed answer unit to the exact case/draft, never free text."""
import re
from .common import digest, require
from .evidence import relation

KINDS=('technical_claim','hypothesis','question','next_step','reported_fact','request_summary')
SUPPORT=('supported','partial','contradicted','unknown')


def bound_review_schema(envelope,spans):
    """Constrain generation to this draft's complete units and witness catalogs."""
    from copy import deepcopy
    from .roles import QUALITY_JUDGE, obj
    schema=deepcopy(QUALITY_JUDGE)
    props=schema['properties']
    props['draft_version']={'type':'string','enum':[envelope['draft_version']]}
    defs={}
    for name,rows in [('sources',spans['sources']),('messages',spans['messages'])]:
        ids=list(dict.fromkeys(r['span_id'] for r in rows))
        defs[name]={'type':'array','maxItems':3 if ids else 0,
                    'items':{'type':'string',**({'enum':ids} if ids else {})}}
    entry=props['unit_reviews']['items']['properties']
    entry.pop('unit_id')
    entry['source_ids']={'$ref':'#/$defs/sources'}
    entry['message_ids']={'$ref':'#/$defs/messages'}
    from .assertion_audit import candidates as assertion_candidates
    kinds={'general':KINDS,'question':('question','technical_claim'),
           'hypothesis':('hypothesis',),'feature':('request_summary',),
           'feature_technical':('request_summary','technical_claim')}
    for name,allowed in kinds.items():
        fields=deepcopy(entry);fields['kind']={'type':'string','enum':list(allowed)}
        defs[name]=obj(fields)
    reviews={}
    for u in envelope['units']:
        field=u['field']
        kind='feature' if field.startswith('feature_proposal.') else ('hypothesis' if field.startswith('hypotheses.') else ('question' if field=='question' else 'general'))
        if kind=='feature' and assertion_candidates(u.get('audited_text',u['text']),field):
            kind='feature_technical'
        reviews[u['unit_id']]={'$ref':'#/$defs/'+kind}
    props['unit_reviews']=obj(reviews)
    props['novelty']['properties']['message_ids']={'$ref':'#/$defs/messages'}
    schema['$defs']=defs
    return schema


def unpack_bound_review(result,envelope):
    """Unpack exact server-bound keys; never correct, infer or salvage bad IDs."""
    require(isinstance(result,dict),'judge_contract_error','ساختار داور معتبر نیست.')
    entries=result.get('unit_reviews'); expected={u['unit_id'] for u in envelope['units']}
    require(isinstance(entries,dict) and set(entries)==expected,'judge_contract_error','کلیدهای واحدهای داور ناقص، تکراری یا منقضی‌اند.')
    require(all(isinstance(e,dict) and 'unit_id' not in e for e in entries.values()),'judge_contract_error','شناسهٔ واحد باید فقط کلید همان واحد باشد.')
    return dict(result,unit_reviews=[dict(entries[u['unit_id']],unit_id=u['unit_id']) for u in envelope['units']])

def draft_units(answer,case_id,case_revision,generation,include_quotes=False):
    binding={'case':case_id,'revision':case_revision,'generation':generation,'answer':answer}
    if include_quotes:binding['unit_contract']='citation-units-v1'
    version=digest(binding)
    units=[]
    fields=[(k,answer[k]) for k in ('question','next_step','rationale')]
    fields += [('hypotheses.'+str(i),s) for i,s in enumerate(answer['hypotheses'])]
    # The active V2 envelope reviews every delivered diagnostic field.
    # Historical envelope reconstruction keeps its frozen field set.
    if include_quotes:
        diagnostic=answer.get('diagnostic') or {}
        fields += [('diagnostic.'+k,diagnostic[k]) for k in
                   ('action','repeat_of','changed_condition','repeat_reason','missing_fact') if diagnostic.get(k)]
        fields += [('diagnostic.conditions.'+str(i)+'.'+part,row[part])
                   for i,row in enumerate(diagnostic.get('conditions',[])) for part in ('dimension','value') if row.get(part)]
    fields += [('feature_proposal.'+k,v) for k,v in (answer.get('feature_proposal') or {}).items() if k!='report_quotes']
    fields += [('feature_proposal.report_quotes.'+str(i),q['quote'])
               for i,q in enumerate((answer.get('feature_proposal') or {}).get('report_quotes',[]))
               if isinstance(q,dict) and isinstance(q.get('quote'),str)]
    # Selected quotations are visible answer content, not mere context. Review
    # their relevance/support separately; do not demand a forbidden paraphrase
    # in the procedural rationale merely to attach a citation.
    from .grounding import claim_review_text
    if include_quotes:fields += [('claims.'+str(i)+'.quote',claim_review_text(c)) for i,c in enumerate(answer['claims'])]
    for field,text in fields:
        # Full fields are atomic review units: no omitted tail or lossy sentence split.
        if not text.strip(): continue
        unit={'unit_id':'u_'+digest({'draft':version,'field':field,'text':text})[:24],
              'field':field,'text':text,'start':0,'end':len(text)}
        if field.startswith('claims.'):
            unit['audited_text']=answer['claims'][int(field.split('.')[1])]['quote']
        units.append(unit)
    envelope={'draft_version':version,'case_id':case_id,'case_revision':case_revision,'generation':generation,'units':units}
    if include_quotes:envelope['unit_contract']='citation-units-v1'
    return envelope

def checked_review(result,answer,evidence,state,envelope,forced=()):
    from .roles import checked_judge
    def check(ok,message): require(ok,'judge_contract_error',message)
    check(envelope==draft_units(answer,envelope['case_id'],envelope['case_revision'],envelope['generation']),'واحدها با متن دقیق پاسخ جاری یکسان نیستند.')
    check(state.get('id',envelope['case_id'])==envelope['case_id'] and state.get('revision',envelope['case_revision'])==envelope['case_revision'],'ممیزی متعلق به پرونده و نسخهٔ جاری نیست.')
    check(isinstance(result,dict) and set(result)=={'verdict','assessments','draft_version','unit_reviews','novelty'},'ساختار قرارداد داور معتبر نیست.')
    check(result['draft_version']==envelope['draft_version'],'داوری متعلق به پیش‌نویس جاری نیست.')
    entries=result['unit_reviews']; allowed={u['unit_id']:u for u in envelope['units']}
    check(isinstance(entries,list) and len(entries)==len(allowed),'پوشش واحدهای پاسخ ناقص است.')
    check(all(isinstance(x,dict) and isinstance(x.get('unit_id'),str) for x in entries),'واحد ممیزی معتبر نیست.')
    check(set(x['unit_id'] for x in entries)==set(allowed),'شناسهٔ واحد ناشناخته یا تکراری است.')
    by_id={e['id']:e for e in evidence}; findings=list(forced)
    cited={c['evidence_id'] for c in answer['claims']}; linked=set()
    for entry in entries:
        check(set(entry)=={'unit_id','kind','support','links','reason','version_dependent','version_limit'},'فیلد ممیزی واحد معتبر نیست.')
        check(entry['kind'] in KINDS and entry['support'] in SUPPORT and isinstance(entry['reason'],str) and 0<len(entry['reason'])<=600,'حالت یا دلیل پشتیبانی معتبر نیست.')
        check(type(entry['version_dependent']) is bool and isinstance(entry['version_limit'],str) and len(entry['version_limit'])<=500,'قرارداد نسخه معتبر نیست.')
        check(isinstance(entry['links'],list) and len(entry['links'])<=3,'پیوند شاهد معتبر نیست.')
        unit=allowed[entry['unit_id']]
        if unit['field'].startswith('hypotheses'):
            check(entry['kind']=='hypothesis','فرضیه نمی‌تواند به پرسش تبدیل شود.')
        if unit['field']=='question': check(entry['kind'] in ('question','technical_claim'),'نوع پرسش معتبر نیست.')
        needs_source=entry['kind'] in ('technical_claim','hypothesis')
        if needs_source and (entry['support']!='supported' or not entry['links']):
            findings.append({'criterion':'claim_support','reason':'پشتیبانی: '+entry['support']+'؛ '+entry['reason']})
        for link in entry['links']:
            check(isinstance(link,dict) and set(link)=={'evidence_id','quote'},'ساختار پیوند شاهد معتبر نیست.')
            eid=link['evidence_id']; quote=link['quote']
            check(isinstance(eid,str) and eid in by_id,'شناسهٔ شاهد ناشناخته است.')
            check(isinstance(quote,str) and 20<=len(quote)<=1000 and quote in by_id[eid]['text'],'نقل‌قول ممیزی در منبع نیست.')
            linked.add(eid)
            if entry['version_dependent'] and relation(by_id[eid],state.get('facts',{}).get('streamlit_version'))!='exact':
                # Limitation must be visible in this exact answer unit, not merely in the audit.
                limit=entry['version_limit']
                if not limit.strip() or limit not in unit['text'] or not re.search(r'نامعلوم|نامشخص|تأیید نشده|تایید نشده|محدود',limit):
                    findings.append({'criterion':'version_fit','reason':'نسخه: سازگاری شاهد نامعلوم یا متفاوت است و محدودیت در پاسخ دیده نمی‌شود.'})
        if entry['support'] in ('partial','contradicted'):
            findings.append({'criterion':'claim_support','reason':'پشتیبانی: '+entry['reason']})
    if cited-linked: findings.append({'criterion':'claim_support','reason':'استناد: شاهد انتخاب‌شده به هیچ واحد پاسخ متصل نشده است.'})
    novelty=result['novelty']
    check(isinstance(novelty,dict) and set(novelty)=={'useful','new','reason','already_supplied_quote'},'قرارداد تازگی معتبر نیست.')
    check(type(novelty['useful']) is bool and type(novelty['new']) is bool and all(isinstance(novelty[k],str) and len(novelty[k])<=1000 for k in ('reason','already_supplied_quote')),'دلیل تازگی معتبر نیست.')
    quote=novelty['already_supplied_quote']
    if quote:
        check(any(quote in m['text'] for m in state.get('messages',[])),'شاهد تکرار در گزارش کاربر وجود ندارد.')
        stripped=re.sub(r'[`*_#-]','',quote).strip()
        empty_heading=r'(?i)(?:streamlit|python|operating system|browser)(?:\s+version)?\s*:\s*'
        check(any(line.strip() and not re.fullmatch(empty_heading,line.strip()) for line in stripped.splitlines()),'عنوان خالی محیط شاهد پاسخ‌داده‌شدن نیست.')
    if answer['decision']=='ask':
        if not novelty['new'] or quote: findings.append({'criterion':'avoids_repeated_check','reason':'تکرار: '+novelty['reason']})
        if not novelty['useful'] or not novelty['reason'].strip(): findings.append({'criterion':'next_step_usefulness','reason':'فایده: دلیل تصمیم‌ساز بودن پرسش مشخص نیست.'})
    reviewed=checked_judge({k:result[k] for k in ('verdict','assessments')},findings)
    return dict(reviewed,draft_version=envelope['draft_version'],unit_reviews=entries,novelty=novelty,
                failure_kind=None if reviewed['verdict']=='accept' else 'answer_quality')


def review_spans(state,evidence,claims=None,report_quotes=None):
    """Server-issued exact spans in disjoint case-bound namespaces.

    Offsets refer to the original message/source, never the truncated context.
    No model-generated quotation is needed in the current review contract.
    """
    output={'sources':[], 'messages':[]}
    def add(text,prefix,identity,metadata,target,offset=0):
        # Preserve full coverage with bounded, contiguous paragraphs/windows.
        for start in range(0,len(text),900):
            end=min(len(text),start+900); quote=text[start:end]
            sid=prefix+digest({'identity':identity,'start':offset+start,'end':offset+end,'text':quote})[:24]
            output[target].append(dict(metadata,span_id=sid,start=offset+start,end=offset+end,text=quote))
    for index,m in enumerate(state.get('messages',[])):
        if m.get('role','user')!='user': continue
        add(m['text'],'usr_',{'case':state.get('id'),'index':index,'text':m['text']},
            {'message_index':index},'messages')
    if report_quotes:
        from .report_quotes import validate as validate_report_quotes
        validate_report_quotes({'report_quotes':report_quotes},state)
        for row in report_quotes:
            index=row['message_index']; start=row['start_char']; end=row['end_char']
            message=state['messages'][index]; text=message['text']
            if not any(span.get('message_index')==index and span['start']<=start and end<=span['end']
                       for span in output['messages']):
                add(row['quote'],'usr_',{'case':state.get('id'),'index':index,
                    'message_sha256':row['message_sha256'],'start':start,'end':end,'text':row['quote']},
                    {'message_index':index},'messages',start)
    for e in evidence:
        quotes=[e['text']] if claims is None else [c['quote'] for c in claims if c['evidence_id']==e['id'] and c['quote'] in e['text']]
        for quote in quotes:
            add(quote,'src_',{'id':e['id'],'text':e['text']},
                {'evidence_id':e['id'],'product_version':e.get('product_version'),
                 'version_relation':relation(e,state.get('facts',{}).get('streamlit_version')),
                 'source_span':e.get('source_span'),'header_spans':e.get('header_spans',[])},'sources',e['text'].find(quote))
    return output


def checked_review_v23(result,answer,evidence,state,envelope,forced=()):
    """Literal validity, semantic support and uncertainty are separate results.

    The model supplies semantic judgements; membership alone never establishes
    entailment. Legacy checked_review is retained for historical trace readers.
    """
    from .roles import checked_judge
    def check(ok,msg): require(ok,'judge_contract_error',msg)
    check(envelope==draft_units(answer,state['id'],state['revision'],envelope['generation'],include_quotes=envelope.get('unit_contract')=='citation-units-v1'),'پیش‌نویس یا پرونده منقضی است.')
    check(isinstance(result,dict) and set(result)=={'verdict','assessments','draft_version','unit_reviews','novelty'},'ساختار داور معتبر نیست.')
    check(result['draft_version']==envelope['draft_version'],'نسخهٔ داوری منقضی است.')
    units={u['unit_id']:u for u in envelope['units']}; entries=result['unit_reviews']
    check(isinstance(entries,list) and len(entries)==len(units) and all(isinstance(e,dict) and isinstance(e.get('unit_id'),str) for e in entries),'پوشش واحدها ناقص است.')
    check({e['unit_id'] for e in entries}==set(units),'شناسهٔ واحد ناشناخته یا تکراری است.')
    quotes=((answer.get('feature_proposal') or {}).get('report_quotes',[])
            if envelope.get('unit_contract')=='citation-units-v1' else [])
    spans=review_spans(state,evidence,answer['claims'],report_quotes=quotes); sources={s['span_id']:s for s in spans['sources']}; messages={s['span_id']:s for s in spans['messages']}
    from .assertion_audit import candidates as assertion_candidates
    rows={e['id']:e for e in evidence}; findings=list(forced); valid=[]; linked=set(); unit_results=[]
    for e in entries:
        check(set(e)=={'unit_id','kind','support','source_ids','message_ids','premise','standalone','reason','version_dependent','version_limit'},'قرارداد واحد ناقص است.')
        check(e['kind'] in KINDS and e['support'] in SUPPORT and isinstance(e['reason'],str) and 0<len(e['reason'])<=600,'حالت پشتیبانی نامعتبر است.')
        check(all(type(e[k]) is bool for k in ('premise','standalone','version_dependent')) and isinstance(e['version_limit'],str),'قرارداد پیش‌فرض نامعتبر است.')
        for key,lookup in [('source_ids',sources),('message_ids',messages)]:
            check(isinstance(e[key],list) and len(e[key])<=3 and all(isinstance(s,str) and s in lookup for s in e[key]),'شاهد جعلی، منقضی یا از فضای اشتباه است.')
        u=units[e['unit_id']]; defects=[]
        if u['field']=='question': check(e['kind'] in ('question','technical_claim'),'نوع پرسش معتبر نیست.')
        if u['field'].startswith('hypotheses.'):
            check(e['kind']=='hypothesis','نوع فرضیه عوض شده است.')
        if u['field'].startswith('feature_proposal.'):
            allowed=('request_summary','technical_claim') if assertion_candidates(
                u.get('audited_text',u['text']),u['field']) else ('request_summary',)
            check(e['kind'] in allowed,'مشخصات درخواست یا ادعای فنی معتبر نیست.')
        if u['field'].startswith('claims.'):
            check(e['kind']=='technical_claim','نقل‌قول منتخب باید واحد ادعای فنی بررسی‌شده باشد.')
            claim=answer['claims'][int(u['field'].split('.')[1])]
            own_sources={sid for sid,s in sources.items() if s['evidence_id']==claim['evidence_id']}
            if not e['source_ids'] or not set(e['source_ids'])<=own_sources:
                defects.append('واحد نقل‌قول به شاهد منتخب همان ادعا متصل نیست.')
        technical=e['kind'] in ('technical_claim','hypothesis') or e['premise']
        # High-confidence attribution escape guard, in addition to semantic review.
        if e['kind'] in ('reported_fact','request_summary') and re.search(r'تضمین|علت قطعی|حتماً رفع|guarantee|definitely fixes',u['text'],re.I): technical=True
        if technical and (e['support']!='supported' or not e['source_ids']): defects.append('ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.')
        from .semantics import UNKNOWN
        explicit_unknown=(u['field'].startswith('feature_proposal.') and u['text']==UNKNOWN and
                          e['support']=='unknown' and not e['premise'] and not e['source_ids'])
        if e['kind'] in ('reported_fact','request_summary') and not explicit_unknown and (e['support']!='supported' or not e['message_ids']): defects.append('انتساب به کاربر شاهد مستقیم ندارد.')
        if e['kind']=='reported_fact':
            # Only an extractive attribution may use user evidence alone. A free
            # technical paraphrase must pass the technical-source contract.
            quoted=re.fullmatch(r'گزارش کاربر:\s*```text\n(.+?)\n```\s*',u['text'],re.S)
            exact=bool(quoted and any(quoted[1] in messages[s]['text'] for s in e['message_ids']))
            if not exact: defects.append('انتساب آزاد کافی نیست؛ گزارش کاربر باید عبارت دقیق و محصور پیام باشد، یا ادعای فنی جدا بررسی شود.')
        if e['support'] in ('partial','contradicted'): defects.append('پشتیبانی فقط جزئی یا متناقض است.')
        if e['source_ids'] and e['support']=='unknown': defects.append('رابطهٔ معنایی شاهد نامعلوم است.')
        for sid in e['source_ids']:
            eid=sources[sid]['evidence_id']
            if e['version_dependent'] and relation(rows[eid],state.get('facts',{}).get('streamlit_version'))!='exact':
                limit=e['version_limit']
                if not limit.strip() or limit not in u['text'] or not re.search(r'نامعلوم|نامشخص|تأیید نشده|تایید نشده|محدود',limit): defects.append('سازگاری نسخه نامعلوم است؛ محدودیت در واحد پاسخ نیست.')
        if defects:
            findings.extend({'criterion':'claim_support','unit_id':e['unit_id'],'reason':'شاهد: '+d} for d in defects)
        else:
            valid.append(e['unit_id'])
            if e['support']=='supported': linked.update(sources[s]['evidence_id'] for s in e['source_ids'])
        unit_results.append({'unit_id':e['unit_id'],'literal_valid':True,'semantic_support':e['support'],'valid':not defects})
    n=result['novelty']
    check(isinstance(n,dict) and set(n)=={'useful','status','message_ids','relation','reason'},'قرارداد تازگی ناقص است.')
    check(type(n['useful']) is bool and n['status'] in ('new','repeated','unknown') and n['relation'] in ('answers_requested_detail','equivalent_experiment','context_only','unknown') and isinstance(n['reason'],str) and 0<len(n['reason'])<=600,'حالت تازگی نامعتبر است.')
    check(isinstance(n['message_ids'],list) and len(n['message_ids'])<=3 and all(isinstance(s,str) and s in messages for s in n['message_ids']),'شاهد تکرار متعلق به پیام کاربر نیست.')
    # A real span can be mere context. Without a semantic connection no definite repeat.
    effective=n['status']
    if not n['message_ids'] or n['relation'] not in ('answers_requested_detail','equivalent_experiment'): effective='unknown' if n['status']=='repeated' else n['status']
    if n['message_ids'] and all(re.fullmatch(r'(?i)\s*(?:streamlit|python|browser)(?: version)?\s*:\s*',messages[s]['text']) for s in n['message_ids']): effective='unknown'
    if answer['decision']=='ask':
        if effective=='repeated': findings.append({'criterion':'avoids_repeated_check','reason':'تکرار: '+n['reason']})
        if not n['useful']: findings.append({'criterion':'next_step_usefulness','reason':'فایده: '+n['reason']})
    orphan={c['evidence_id'] for c in answer['claims']}-linked
    if orphan: findings.append({'criterion':'claim_support','reason':'استناد: منبع انتخاب‌شده هیچ واحد معتبر باقی‌مانده را پشتیبانی نمی‌کند.'})
    reviewed=checked_judge({k:result[k] for k in ('verdict','assessments')},findings)
    uncertain=any(x['semantic_support']=='unknown' for x in unit_results if not x['valid']) or (n['status']=='repeated' and effective=='unknown')
    return dict(reviewed,draft_version=envelope['draft_version'],unit_reviews=entries,unit_results=unit_results,
                valid_unit_ids=valid,source_spans=spans['sources'],linked_evidence_ids=sorted(linked),orphan_evidence_ids=sorted(orphan),
                novelty=dict(n,effective_status=effective),failure_kind=None if reviewed['verdict']=='accept' else ('insufficient_evidence' if uncertain else 'answer_quality'))


def recompose(answer,review,envelope,state=None):
    """Keep only individually valid, explicitly standalone units; rejudge required."""
    from copy import deepcopy
    keep=set(review['valid_unit_ids']) & {e['unit_id'] for e in review['unit_reviews'] if e['standalone']}
    fields={u['field'] for u in envelope['units'] if u['unit_id'] in keep}
    out=deepcopy(answer)
    feature=out.get('feature_proposal') or {}
    feature_fields={'feature_proposal.'+k for k in feature if k!='report_quotes'}
    from .routing import intent
    feature_handoff=bool(state and intent(state)=='feature_request' and len(feature_fields)==5 and feature_fields<=fields
        and ('next_step' not in fields or (out['decision']=='ask' and 'question' not in fields)
             or any(f['criterion']=='next_step_usefulness' for f in review['findings'])))
    if feature_handoff:
        # This new procedural step is only a draft. The pipeline MUST rejudge it.
        out.update(decision='escalate',question='',
            next_step='اقدام: نگه‌دارنده دربارهٔ افزودن رفتار درخواستی تصمیم طراحی بگیرد و امکان پذیرش را با این شرط بررسی کند: '+feature['acceptance_condition'],
            diagnostic={'action':'','conditions':[],'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''})
    elif 'next_step' not in fields or (out['decision']=='ask' and 'question' not in fields): return None
    out['rationale']=out['rationale'] if 'rationale' in fields else 'محدودیت: بخش فاقد پشتوانه حذف شده است؛ علت و رفع مشکل تأیید نشده‌اند.'
    out['hypotheses']=[h for i,h in enumerate(out['hypotheses']) if 'hypotheses.'+str(i) in fields]
    source_map={s['span_id']:s['evidence_id'] for s in review.get('source_spans',[])}
    retained_sources={source_map[s] for e in review['unit_reviews'] if e['unit_id'] in keep for s in e['source_ids'] if s in source_map}
    out['claims']=[c for c in out['claims'] if c['evidence_id'] in retained_sources]
    if any(v for k,v in (out.get('feature_proposal') or {}).items() if k!='report_quotes'):
        required={'feature_proposal.'+k for k in out['feature_proposal'] if k!='report_quotes'}
        if not required<=fields: return None
    return out if out!=answer else None
