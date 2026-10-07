from .common import *

def validate_answer(answer,evidence):
    require(isinstance(answer,dict) and set(answer)=={'decision','claims','question','next_step','rationale','hypotheses'},'invalid_model_output','ساختار پاسخ مدل معتبر نیست.')
    require(answer['decision'] in ('ask','answer','escalate'),'invalid_model_output','تصمیم مدل معتبر نیست.')
    for key in ('question','next_step','rationale'):
        require(isinstance(answer[key],str) and len(answer[key])<=1800,'invalid_model_output','متن پاسخ بیش از حد مجاز است.')
    require(bool(answer['next_step'].strip()),'invalid_model_output','قدم بعدی لازم است.')
    require(isinstance(answer['hypotheses'],list) and len(answer['hypotheses'])<=3 and all(isinstance(x,str) and len(x)<=700 for x in answer['hypotheses']),'invalid_model_output','فرضیه‌ها نامعتبرند.')
    require(isinstance(answer['claims'],list) and len(answer['claims'])<=3,'invalid_model_output','تعداد شاهدها نامعتبر است.')
    by_id={x['id']:x for x in evidence}; citations=[]
    for claim in answer['claims']:
        require(isinstance(claim,dict) and set(claim)=={'evidence_id','quote'},'invalid_citation','ساختار استناد نامعتبر است.')
        row=by_id.get(claim['evidence_id']); quote=claim['quote']
        require(row is not None and isinstance(quote,str) and 20<=len(quote)<=1000,'invalid_citation','منبع یا نقل‌قول نامعتبر است.')
        require(' '.join(quote.split()) in ' '.join(row['text'].split()),'unsupported_quote','نقل‌قول در شاهد دریافتی وجود ندارد.')
        citations.append({'evidence_id':row['id'],'source_id':row['source_id'],'quote':quote,
                          'url':row['url'],'section':row['section'],'lines':row['lines'],
                          'kind':row['kind'],'revision':row['revision'],'product_version':row.get('product_version')})
    if answer['decision']=='answer': require(bool(citations),'unsupported_answer','پاسخ فنی بدون شاهد پذیرفته نیست.')
    if answer['decision']=='ask': require(bool(answer['question'].strip()),'invalid_model_output','پرسش مشخص لازم است.')
    return citations

def fallback(code):
    return {'decision':'escalate','claims':[],'question':'',
            'next_step':'اقدام بعدی: نگه‌دارنده بستهٔ شواهد و خطای اعتبارسنجی را بررسی کند؛ اقدام خودکار انجام نشود.',
            'rationale':'محدودیت: پاسخ پیشنهادی از کنترل ساختار یا استناد عبور نکرد. کد خطا: `'+code+'`.', 'hypotheses':[]}

def render_response(answer,citations,facts,checks):
    rows=['پاسخ پیشنهادی: '+({'ask':answer['question'],'answer':answer['next_step'],'escalate':answer['next_step']}[answer['decision']])]
    for c in citations:
        label='گزارش یک کاربر؛ اثبات علت این پرونده نیست' if c['kind']=='issue' else 'متن رسمی؛ سازگاری نسخه باید بررسی شود'
        fence='`'*max(3,max((len(x) for x in __import__('re').findall(r'`+',c['quote'])),default=0)+1)
        rows.append(f"شاهد مستند: {label}.\n\nبخش منبع:\n\n```text\n{c['section']}\n```\n\nنسخهٔ منبع:\n\n```text\n{c['revision']}\n```\n\nمتن شاهد:\n\n{fence}text\n{c['quote']}\n{fence}\n\nنشانی منبع:\n\n```text\n{c['url']}\n```")
    rows.append(answer['rationale'] if answer['rationale'].startswith('محدودیت') else 'محدودیت: '+answer['rationale'])
    if answer['hypotheses']: rows.extend('فرضیهٔ تأییدنشده: '+x for x in answer['hypotheses'])
    rows.append('وضعیت: رفع مشکل تأیید نشده است؛ ثبت پاسخ فقط پس از تأیید نگه‌دارنده انجام می‌شود.' if facts.get('resolved') is not True else 'وضعیت: کاربر رفع مشکل را اعلام کرده است؛ تغییر وضعیت همچنان تأیید نگه‌دارنده می‌خواهد.')
    return '\n\n'.join(rows)
