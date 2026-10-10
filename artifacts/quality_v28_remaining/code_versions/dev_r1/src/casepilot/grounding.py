from .common import *

def citation_limit(row):
    """Visible applicability notice derived only from retrieved provenance."""
    if not row.get('product_version'):
        return 'محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است.'
    if row.get('version_relation')=='mismatch':
        return 'محدودیت: نسخهٔ منبع با نسخهٔ گزارش‌شده متفاوت است؛ انطباق این گزاره تأیید نشده است.'
    if row.get('version_relation')!='exact':
        return 'محدودیت: انطباق نسخهٔ محیط شما با نسخهٔ منبع نامعلوم است.'
    return ''

def claim_review_text(claim):
    return claim['quote']+('\n'+claim['version_limit'] if claim.get('version_limit') else '')

def validate_answer(answer,evidence,state=None):
    required={'decision','claims','question','next_step','rationale','hypotheses'}
    require(isinstance(answer,dict) and required<=set(answer)<=required|{'diagnostic','feature_proposal'},'invalid_model_output','ساختار پاسخ مدل معتبر نیست.')
    from .memory import validate_diagnostic
    from .routing import validate_feature
    validate_diagnostic(answer.get('diagnostic')); validate_feature(answer.get('feature_proposal'))
    if answer.get('feature_proposal') is not None and state is not None and \
            state.get('report_quote_contract')=='user-report-sections-v1':
        from .report_quotes import validate as validate_report_quotes
        validate_report_quotes(answer['feature_proposal'],state)
    require(answer['decision'] in ('ask','answer','escalate'),'invalid_model_output','تصمیم مدل معتبر نیست.')
    for key in ('question','next_step','rationale'):
        require(isinstance(answer[key],str) and len(answer[key])<=1800,'invalid_model_output','متن پاسخ بیش از حد مجاز است.')
    require(bool(answer['next_step'].strip()),'invalid_model_output','قدم بعدی لازم است.')
    require(isinstance(answer['hypotheses'],list) and len(answer['hypotheses'])<=3 and all(isinstance(x,str) and len(x)<=700 for x in answer['hypotheses']),'invalid_model_output','فرضیه‌ها نامعتبرند.')
    require(isinstance(answer['claims'],list) and len(answer['claims'])<=3,'invalid_model_output','تعداد شاهدها نامعتبر است.')
    by_id={x['id']:x for x in evidence}; citations=[]
    for claim in answer['claims']:
        require(isinstance(claim,dict) and set(claim) in ({'evidence_id','quote'},{'evidence_id','quote','version_limit'}),'invalid_citation','ساختار استناد نامعتبر است.')
        row=by_id.get(claim['evidence_id']); quote=claim['quote']
        require(row is not None and isinstance(quote,str) and 20<=len(quote)<=1000,'invalid_citation','منبع یا نقل‌قول نامعتبر است.')
        require('version_limit' not in claim or claim['version_limit']==citation_limit(row),'invalid_citation','محدودیت نسخه باید از منشأ همان شاهد مشتق شود.')
        require(' '.join(quote.split()) in ' '.join(row['text'].split()),'unsupported_quote','نقل‌قول در شاهد دریافتی وجود ندارد.')
        exact_offset=row['text'].find(quote)
        if 'source_span' in row:
            require(exact_offset>=0,'unsupported_quote','ارجاع ساختاری باید عین متن اصلی باشد.')
        start=row.get('source_span',[0])[0]+max(0,exact_offset)
        citations.append({'evidence_id':row['id'],'source_id':row['source_id'],'quote':quote,
                          'url':row['url'],'section':row['section'],'lines':row['lines'],
                          'kind':row['kind'],'revision':row['revision'],'product_version':row.get('product_version'),
                          'source_span':[start,start+len(quote)] if 'source_span' in row else None,
                          'source_sha256':row.get('source_sha256'),'header_spans':row.get('header_spans',[]),
                          'selected_child_ids':row.get('selected_child_ids',[row['id']]),'version_limit':citation_limit(row)})
    if answer['decision']=='answer': require(bool(citations),'unsupported_answer','پاسخ فنی بدون شاهد پذیرفته نیست.')
    if answer['decision']=='ask': require(bool(answer['question'].strip()),'invalid_model_output','پرسش مشخص لازم است.')
    return citations

def fallback(code):
    if code not in ('judge_rejected','unsupported_answer','deterministic_review_failed'):
        return {'decision':'escalate','claims':[],'question':'',
            'next_step':'وضعیت سامانه: پردازش پاسخ متوقف شد؛ گزارش و بررسی‌های شما محفوظ است. اپراتور باید مرحلهٔ شکست‌خورده با کد `'+code+'` را بررسی کند. ارسال دوبارهٔ اطلاعات پرونده لازم نیست.',
            'rationale':'محدودیت: این خطای داخلی دربارهٔ علت مشکل یا لزوم ارجاع آن به نگه‌دارنده نتیجه‌ای نمی‌دهد.', 'hypotheses':[]}
    return {'decision':'escalate','claims':[],'question':'',
            'next_step':'اقدام بعدی: نگه‌دارنده بستهٔ شواهد و خطای اعتبارسنجی را بررسی کند؛ اقدام خودکار انجام نشود.',
            'rationale':'محدودیت: پاسخ پیشنهادی از کنترل ساختار یا استناد عبور نکرد. کد خطا: `'+code+'`.', 'hypotheses':[]}

def render_response(answer,citations,facts,checks):
    rows=['پاسخ پیشنهادی: '+({'ask':answer['question'],'answer':answer['next_step'],'escalate':answer['next_step']}[answer['decision']])]
    for c in citations:
        label='گزارش یک کاربر؛ اثبات علت این پرونده نیست' if c['kind']=='issue' else 'متن رسمی؛ سازگاری نسخه باید بررسی شود'
        fence='`'*max(3,max((len(x) for x in __import__('re').findall(r'`+',c['quote'])),default=0)+1)
        rows.append(f"شاهد مستند: {label}.\n\nبخش منبع:\n\n```text\n{c['section']}\n```\n\nبازبینی سند:\n\n```text\n{c['revision']}\n```\n\nمتن شاهد:\n\n{fence}text\n{c['quote']}\n{fence}\n\n{c.get('version_limit','')}\n\nنشانی منبع:\n\n```text\n{c['url']}\n```")
    rows.append(answer['rationale'] if answer['rationale'].startswith('محدودیت') else 'محدودیت: '+answer['rationale'])
    if answer['hypotheses']: rows.extend('فرضیهٔ تأییدنشده: '+x for x in answer['hypotheses'])
    rows.append('وضعیت: رفع مشکل تأیید نشده است؛ ثبت پاسخ فقط پس از تأیید نگه‌دارنده انجام می‌شود.' if facts.get('resolved') is not True else 'وضعیت: کاربر رفع مشکل را اعلام کرده است؛ تغییر وضعیت همچنان تأیید نگه‌دارنده می‌خواهد.')
    return '\n\n'.join(rows)
