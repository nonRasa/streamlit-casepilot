"""Bind every reviewed answer unit to the exact case/draft, never free text."""
import re
from .common import digest, require
from .evidence import relation

KINDS=('technical_claim','hypothesis','question','next_step','reported_fact','request_summary')
SUPPORT=('supported','partial','contradicted','unknown')

def draft_units(answer,case_id,case_revision,generation):
    version=digest({'case':case_id,'revision':case_revision,'generation':generation,'answer':answer})
    units=[]
    fields=[(k,answer[k]) for k in ('question','next_step','rationale')]
    fields += [('hypotheses.'+str(i),s) for i,s in enumerate(answer['hypotheses'])]
    for field,text in fields:
        # Full fields are atomic review units: no omitted tail or lossy sentence split.
        if not text.strip(): continue
        units.append({'unit_id':'u_'+digest({'draft':version,'field':field,'text':text})[:24],
                      'field':field,'text':text,'start':0,'end':len(text)})
    return {'draft_version':version,'case_id':case_id,'case_revision':case_revision,'generation':generation,'units':units}

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
