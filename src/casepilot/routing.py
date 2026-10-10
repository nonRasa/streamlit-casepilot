"""Actionable, attributed handoff without fabricating a cause or result."""
from .common import require
from .memory import active_experiments

def proposed_status(decision, validation_error=None):
    """An internal review failure cannot decide that the user's case needs escalation."""
    if validation_error:
        return None
    return {'ask':'waiting_user','answer':'open','escalate':'escalated'}[decision]

def proposal_actions(response, decision, validation_error=None):
    actions=[{'type':'comment','body':response}]
    status=proposed_status(decision,validation_error)
    if status is not None:
        actions.append({'type':'status','value':status})
    return actions

def intent(state):
    planned=state.get('investigation_plan',{}).get('intent')
    if planned:
        from .case_type import case_kind
        return case_kind(state)
    text=state.get('messages',[{'text':''}])[0]['text'].casefold()
    return 'feature_request' if any(s in text for s in ('feature request','enhancement','درخواست قابلیت')) else 'bug'

def recovery_action(state,feature):
    """One source-free question for a first-turn review failure, never a diagnosis."""
    if not feature and len(state.get('messages',[]))==1:
        import re
        report=state['messages'][0]['text']
        versions=re.search(r'(?i)\bfrom\s+(\d+(?:\.\d+){1,3})\s+to\s+(\d+(?:\.\d+){1,3})\b',report)
        has_code=bool(re.search(r'(?is)```[^\n]*\n.*?\bdef\s+\w+\s*\(',report))
        if versions and has_code:
            before,after=versions.groups()
            return ('اقدام: نگه‌دارنده کد بازتولید درج‌شده در گزارش را با '
                    '`Streamlit '+before+'` و `Streamlit '+after+'` در محیط همسان '
                    'اجرا و نتیجهٔ هر اجرا و تفاوت مشاهده‌شده را ثبت کند؛ '
                    'این بازتولید هنوز مستقلاً انجام نشده و علت یا رفع تأیید نشده است.')
    if not feature and len(state.get('messages',[]))==1 and not state.get('facts',{}).get('streamlit_version'):
        from .agent import version_observations
        report=state['messages'][0]['text']
        if not version_observations(report)['streamlit_version']:
            return ('اقدام: فقط نسخهٔ دقیق Streamlit در محیطی که خطا رخ می‌دهد '
                    'از گزارش‌دهنده خواسته شود؛ این داده برای سنجش سازگاری شاهد لازم است. '
                    'علت یا رفع مشکل هنوز تأیید نشده است.')
    return 'اقدام: گزارش و بررسی‌های ثبت‌شده را بازبینی کنید؛ برای بازتولید مستقل، نخست فقط مجهول تصمیم‌ساز را مشخص کنید.'

def reported_regression_check(state):
    """Source-free maintainer check for a first-turn version regression report.

    The report identifies a comparison to run, not its result or root cause.
    Already-performed comparisons must continue through the ordinary route.
    """
    import re
    if intent(state)!='bug' or len(state.get('messages',[]))!=1: return None
    report=state['messages'][0]['text']
    versions=re.search(r'(?i)\bfrom\s+(\d+(?:\.\d+){1,3})\s+to\s+(\d+(?:\.\d+){1,3})\b',report)
    code_blocks=re.findall(r'```[^\n]*\n(.*?)```',report,re.S)
    complete_code=any(re.search(r'(?m)^\s*def\s+\w+\s*\(',block) and
                      not re.search(r'(?i)\.\.\.|pseudo.code|TODO|omitted',block) for block in code_blocks)
    if not versions or versions[1]==versions[2] or not complete_code: return None
    before,after=versions.groups()
    for event in active_experiments(state):
        if event.get('status') not in ('performed_unknown','succeeded','failed','correction'): continue
        values=[c.get('value','') for c in event.get('conditions',[])]
        if (before in values and after in values or
            before+' -> '+after in values or after+' -> '+before in values): return None
    for check in state.get('checks',[]):
        if before in check and after in check and re.search(r'(?i)\b(?:ran|tested|executed|compared)\b|اجرا|آزمایش|مقایسه',check): return None
    return {'decision':'escalate','claims':[],'question':'',
            'next_step':recovery_action(state,False),
            'rationale':'محدودیت: اختلاف نسخه و خطا گزارش کاربر است؛ نتیجهٔ مقایسهٔ کنترل‌شده ثبت نشده و علت یا رفع تأیید نشده است.',
            'hypotheses':[],
            'diagnostic':{'action':'compare_versions','conditions':[{'dimension':'version_pair','value':before+' -> '+after}],
                          'repeat_of':'','changed_condition':'','repeat_reason':'','missing_fact':''}}

def reported_attempts(state):
    """Exact first-person attempt lines, never interpreted as verified results."""
    import re
    lines=[]; fenced=False
    for message in state.get('messages',[]):
        for line in message['text'].splitlines():
            if re.match(r'^\s*(```|~~~)',line): fenced=not fenced; continue
            if not fenced and re.search(r'(?i)\b(?:I|we)\s+(?:tried|tested|attempted)\b|(?:من|ما).{0,20}(?:آزمایش|امتحان|تست)\s*کرد',line):
                value=line.strip()[:500]
                if value and value not in lines: lines.append(value)
    return lines[:5]

def handoff(state,citations,error=None,answer=None,review=None):
    plan=state.get('investigation_plan',{}); feature=intent(state)=='feature_request'
    proposal=(answer or {}).get('feature_proposal',{})
    if intent(state) in ('unknown','mixed') and any(v for k,v in proposal.items() if k!='report_quotes'):
        feature=True
    # Never introduce an unreviewed extractor paraphrase into the final handoff.
    summary=state['messages'][0]['text'][:5000]
    from .semantics import UNKNOWN
    unknown=([k for k,v in proposal.items() if k!='report_quotes' and v==UNKNOWN] if feature else
             [k for k in ('streamlit_version','python_version','deployment','reproducible') if state.get('facts',{}).get(k) in (None,'')])
    return {'request_type':intent(state),'reported_problem':summary,'environment':state.get('facts',{}),
            'experiments':active_experiments(state),'evidence':citations,'unknowns':unknown,
            'reported_checks':list(dict.fromkeys(state.get('checks',[])))[:30],
            'reported_attempts':reported_attempts(state),
            'escalation_basis':'internal_review_failure' if error else ('feature_request' if feature else 'case_needs_maintainer'),
            'valid_findings':[] if error else [{'field':k,'text':v} for k,v in {**{k:(answer or {}).get(k,'') for k in ('next_step','rationale')},**{k:v for k,v in proposal.items() if k!='report_quotes' and v!=UNKNOWN}}.items() if v],
            'limitations':['محدودیت: علت و رفع مشکل مستقلاً تأیید نشده‌اند.']+(['محدودیت: کد توقف `'+error+'`؛ خطای داخلی ضرورت ارجاع پرونده را اثبات نمی‌کند.'] if error else []),
            'maintainer_action':(answer or {}).get('next_step') if not error and answer else ('اقدام: امکان افزودن رفتار درخواستی و شرط پذیرش را بررسی و تصمیم طراحی را ثبت کنید.' if feature else recovery_action(state,feature)),
            'feature':proposal if feature else {},
            'feature_origins':[] if error or not review else [
                {'unit_id':e['unit_id'],'message_ids':e['message_ids'],'quote':review.get('meanings',{}).get(e['unit_id'],{}).get('user_quote','')}
                for e in review.get('unit_reviews',[]) if e['kind']=='request_summary' and e['unit_id'] in review.get('valid_unit_ids',[])]}

def validate_feature(value):
    if value is None: return
    require(isinstance(value,dict) and set(value)=={'current_behavior','desired_behavior','user_need','constraints','acceptance_condition','report_quotes'},'invalid_feature','قرارداد پیشنهاد قابلیت معتبر نیست.')
    require(all(isinstance(value[k],str) and len(value[k])<=1000 for k in value if k!='report_quotes'),'invalid_feature','متن پیشنهاد قابلیت معتبر نیست.')
    require(isinstance(value['report_quotes'],list) and len(value['report_quotes'])<=4 and all(isinstance(s,str) and len(s)<=800 for s in value['report_quotes']),'invalid_feature','شواهد قابلیت معتبر نیست.')

def route_findings(answer,state):
    if intent(state)!='feature_request': return []
    feature=answer.get('feature_proposal') or {}
    findings=[]
    import re
    text=' '.join(answer.get(k,'') for k in ('question','next_step','rationale'))
    if re.search(r'پیاده‌سازی|نمونه.*(?:کد|اجرا)|مستندات.*(?:رابط|ویژگی)',text) and re.search(r'ارائه|ارسال|لازم است|نیاز به|وجود دارد',text):
        findings.append({'criterion':'next_step_usefulness','reason':'قابلیت: نبود پیاده‌سازی پیشنهادی الزام به تهیهٔ آن توسط درخواست‌کننده نیست.'})
    if answer['decision']=='ask' and not state.get('investigation_plan',{}).get('missing_detail'):
        findings.append({'criterion':'next_step_usefulness','reason':'قابلیت: هدف روشن کاربر دوباره پرسیده شده است.'})
    if not all(feature.get(k,'').strip() for k in ('current_behavior','desired_behavior','user_need','constraints','acceptance_condition')):
        findings.append({'criterion':'next_step_usefulness','reason':'قابلیت: رفتار فعلی، مطلوب، نیاز، محدودیت و شرط پذیرش باید مشخص یا صریحاً نامعلوم باشند.'})
    quotes=feature.get('report_quotes',[])
    if not quotes or not all(q and any(q in m['text'] for m in state.get('messages',[])) for q in quotes):
        findings.append({'criterion':'relevance','reason':'قابلیت: پیشنهاد به عبارت دقیق گزارش متصل نیست.'})
    return findings

def render_handoff(packet,max_chars=8000):
    import json, re
    def fenced(value,language):
        marker='`'*max(3,max((len(m.group()) for m in re.finditer(r'`+',value)),default=0)+1)
        return marker+language+'\n'+value+'\n'+marker
    env='؛ '.join(k+'='+str(v) for k,v in packet['environment'].items()) or 'نامعلوم'
    events=packet['experiments']
    lines=['ارجاع: خلاصهٔ قابل بررسی برای نگه‌دارنده.',
           'مسئلهٔ گزارش‌شده:\n\n'+fenced(packet['reported_problem'],'text'),
           'محیط گزارش‌شده:\n\n'+fenced(env,'text')]
    if events:
        lines.append('بررسی‌های گزارش‌شده:\n\n```json\n'+json.dumps([{'action':e['action'][:120],'conditions':str(e['conditions'])[:200],'status':e['status'],'result':e['result'][:250],'provenance':e['provenance']} for e in events[-5:]],ensure_ascii=False,indent=2)+'\n```')
        if len(events)>5: lines.append('ادامه: پنج بررسی آخر نمایش داده شده‌اند؛ سابقهٔ کامل در خلاصهٔ ساخت‌یافتهٔ پیشنهاد محفوظ است.')
    else: lines.append('بررسی‌ها: آزمایش ساخت‌یافتهٔ انجام‌شده ثبت نشده است.')
    checks=packet.get('reported_checks',[])
    if checks:
        lines.append('بررسی‌های گزارش‌شدهٔ کاربر (نتیجهٔ مستقل تأیید نشده):\n\n```text\n'+'\n'.join('- '+str(x)[:300] for x in checks)+'\n```')
    attempts=packet.get('reported_attempts',[])
    if attempts:
        lines.append('اقدام‌های نقل‌شده از گزارش کاربر (اجرا و نتیجه مستقلاً تأیید نشده):\n\n```text\n'+'\n'.join('- '+x for x in attempts)+'\n```')
    lines.append('مجهولات:\n\n```text\n'+', '.join(packet['unknowns'])+'\n```')
    lines.append('شواهد: '+('تعداد '+str(len(packet['evidence']))+' استناد اعتبارسنجی‌شده در همین پاسخ.' if packet['evidence'] else 'شاهد فنی پذیرفته‌شده در این نوبت موجود نیست.'))
    if packet['feature']:
        for key,label in [('current_behavior','رفتار فعلی'),('desired_behavior','رفتار مطلوب'),('user_need','نیاز کاربر'),('constraints','محدودیت‌ها'),('acceptance_condition','پذیرش')]:
            lines.append(label+': '+packet['feature'][key])
    tail='\n\n'.join([packet['maintainer_action']]+packet['limitations'])
    body='\n\n'.join(lines)
    if len(body)+len(tail)+2>max_chars:
        # Render fewer sections intact; never cut through a fenced JSON block.
        budget=max_chars-len(tail)-100; kept=[]
        for line in lines:
            if len('\n\n'.join(kept+[line]))<=budget: kept.append(line)
        body='\n\n'.join(kept)+'\n\nادامه: جزئیات کامل در خلاصهٔ ساخت‌یافتهٔ پیشنهاد محفوظ است.'
    return body+'\n\n'+tail
