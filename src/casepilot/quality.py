"""V2.1 quality controls derived from development failures, never case IDs/labels.

The frozen V2 corpus is unchanged. Selection filters apply at query time so old
snapshots and the private embedding cache remain reproducible.
"""
import re
from .common import digest,canonical

REVISION = 'v2.16-version-matched-evidence-and-plan'
NONTECH = re.compile(r'(?i)^(checklist|related issues|additional context|community|voting|references|related pr|other issues)\b')
BOILERPLATE = re.compile(r'(?i)searched.*(?:existing|similar).*issues|descriptive title|provided sufficient information|vote.*(?:issue|feature)|thumbs.up|community voting|please add.*reaction')
FUTURE = re.compile(r'(?i)\b(?:proposal|proposed architecture|future architecture|design proposal|execution model proposal)\b')

def technical_source(row):
    """Exclude template-only/proposal chunks, retain mixed technical paragraphs."""
    if NONTECH.search(row.get('section','').strip()): return False
    lines=[x.strip() for x in row['text'].splitlines() if x.strip() and not x.lstrip().startswith('#')]
    if not lines or all(BOILERPLATE.search(x) or re.fullmatch(r'[-*\[\]xX .]+',x) for x in lines): return False
    if FUTURE.search(row.get('title','')) and row.get('kind')!='docs': return False
    return True

def clean_report(text):
    """Remove administrative checkbox lines; never remove actual code/checks."""
    output=[]; fenced=False
    for line in text.splitlines():
        if re.match(r'^\s*(```|~~~)',line): fenced=not fenced
        if not fenced and BOILERPLATE.search(line): continue
        output.append(line)
    return '\n'.join(output).strip()

def report_inventory(state):
    messages=state.get('messages',[]); initial=messages[0]['text'] if messages else ''
    code=re.findall(r'```[^\n]*\n(.*?)```',initial,re.S)
    apis=list(dict.fromkeys(re.findall(r'\bst\.[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?',initial)))[:45]
    constraints=known_constraints(state)
    error_spans=[s.strip()[:700] for s in initial.splitlines() if re.search(r'\b[A-Za-z_]\w*(?:Error|Exception)\s*:',s)][:3]
    # Exact spans only, explicitly not established diagnoses or permissions.
    spans=[]
    for line in initial.splitlines():
        s=line.strip()
        if not s or BOILERPLATE.search(s): continue
        if re.search(r'(?i)\b(?:tried|tested|attempted|already|works?|fails?|doesn.t|didn.t|instead|workaround|expected|actual|memory|\d+\s*(?:GB|MB)|version)\b|امتحان|آزمایش|نسخه|حافظه|اصلاح',s):
            spans.append(s[:300])
    return {'reported_spans':spans[:10], 'reported_error_spans':error_spans,
            'code_blocks_present':len(code), 'mentioned_apis':apis,'known_constraints':constraints,
            'authoritative_current_facts':state.get('facts',{}),
            'correction_rule':'Latest structured facts supersede historical report values. The original report remains a reported observation, not independently verified truth.'}

def known_constraints(state):
    text='\n'.join(x['text'] for x in state.get('messages',[]))
    return {'upload_limit_spans':re.findall(r'(?i)(?:server\.)?maxUploadSize\s*[=:]\s*\d+',text),
            'memory_size_spans':re.findall(r'(?i)\b\d+(?:\.\d+)?\s*g(?:iga)?b\b',text),
            'defined_classes':list(dict.fromkeys(re.findall(r'(?m)^\s*class\s+(\w+)',text)))[:20],
            'defined_functions':list(dict.fromkeys(re.findall(r'(?m)^\s*def\s+(\w+)\s*\(',text)))[:30],
            'outside_pickle_result_spans':[s.strip()[:600] for s in text.splitlines() if re.search(r'(?i)pickle',s) and re.search(r'(?i)outside|بیرون',s) and re.search(r'(?i)works|confirm|success|موفق',s)][:3],
            'closed_tab_result_spans':[s.strip()[:600] for s in text.splitlines() if re.search(r'(?i)clos(?:e|ed|ing).*tab|بستن.*تب',s) and re.search(r'(?i)still|remain|even|doesn.t|not|هنوز|نمی',s)][:3]}

def novelty_findings(answer,state):
    """High precision checks for explicit supplied constraints, not diagnoses."""
    if answer['decision'] not in ('ask','escalate'): return []
    q=answer['question']+' '+answer['next_step']; c=known_constraints(state); findings=[]
    report='\n'.join(x['text'] for x in state.get('messages',[]))
    def add(reason): findings.append({'criterion':'avoids_repeated_check','reason':reason})
    full_error=bool(re.search(r'(?im)^\s*(?:full error|complete error|خطای کامل)\s*:',report) and
                    re.search(r'\b[A-Za-z_]\w*(?:Error|Exception)\s*:',report))
    asks_error=bool(re.search(r'(?i)(?:send|provide|share|paste|show|ارسال|بفرست|ارائه|بگذار|در اختیار).{0,100}(?:full|complete|کامل).{0,30}(?:error|exception|خطا|ارور)|(?:full|complete|کامل).{0,30}(?:error|exception|خطا|ارور).{0,120}(?:send|provide|share|paste|show|ارسال|بفرست|ارائه)|(?:خطا|ارور)ی?\s*کامل.{0,100}(?:ارسال|بفرست|ارائه)',q))
    if full_error and asks_error:
        add('خطا: متن کامل خطا با نام استثنا در گزارش آمده است؛ تنها بخش واقعاً غایب را بخواهید.')
    asks_class=bool(re.search(r'(?i)(?:send|provide|share|paste|show|ارسال|بفرست|ارائه).{0,100}(?:class|کلاس)|(?:class|کلاس).{0,100}(?:send|provide|share|paste|show|ارسال|بفرست|ارائه)',q))
    if c['defined_classes'] and asks_class and re.search(r'(?i)(?:full|complete|entire|definition|source|کامل|تعریف)',q):
        add('کد: تعریف کلاس در گزارش موجود است: '+', '.join(c['defined_classes']))
    # A complete fenced reproducer can answer whether its shown class defines
    # named special methods. It does not establish what a different real class does.
    methods=set(re.findall(r'__\w+__',q))
    asks_presence=bool(re.search(r'(?i)\b(?:does|has|contains|include|whether)\b|آیا|شامل|دارد',q))
    asks_actual_difference=bool(re.search(r'(?i)\b(?:actual|real|different|differs|production)\b|واقعی|اصلی|تفاوت|متفاوت',q))
    if methods and asks_presence and not asks_actual_difference and re.search(r'(?i)reproducible code example|نمونه.{0,25}بازتولید',report):
        for block in re.findall(r'```[^\n]*\n(.*?)```',report,re.S):
            for name in c['defined_classes']:
                if not re.search(r'(?i)\b'+re.escape(name)+r'\b',q): continue
                match=re.search(r'(?ms)^class\s+'+re.escape(name)+r'\b[^\n]*\n(?P<body>.*?)(?=^\S|\Z)',block)
                if match and re.search(r'(?m)^\s+def\s+',match['body']) and not re.search(r'\.\.\.|TODO|omitted',match['body'],re.I):
                    if all(not re.search(r'(?m)^\s+def\s+'+re.escape(method)+r'\s*\(',match['body']) for method in methods):
                        add('کد: نمونهٔ بازتولید، تعریف کلاس '+name+' را نشان می‌دهد و متدهای نام‌برده در آن نیستند؛ فقط تفاوتِ مشخص با کلاس واقعی را می‌توان پرسید.')
                    break
    if c['upload_limit_spans'] and re.search(r'(?i)maxUploadSize',q) and not re.search(r'(?i)maxUploadSize\s*[=:]\s*\d+',q):
        add('تنظیم: حد آپلود قبلاً صریح آمده است: '+'؛ '.join(c['upload_limit_spans'])+'؛ تغییر آزمایش باید مقدار یا شرط تازهٔ مشخص داشته باشد.')
    if c['outside_pickle_result_spans'] and re.search(r'(?i)pickle|پیکل|پیکله',q) and re.search(r'(?i)outside|خارج|بیرون',q):
        add('آزمایش: نتیجهٔ پیکله بیرون برنامه قبلاً گزارش شده است: '+c['outside_pickle_result_spans'][0])
    if c['closed_tab_result_spans'] and re.search(r'بست|بستن|close',q,re.I) and re.search(r'تب|tab',q,re.I):
        add('آزمایش: نتیجهٔ بستن تب قبلاً آمده است: '+c['closed_tab_result_spans'][0])
    targets=sum(bool(re.search(p,q,re.I)) for p in [r'نسخه.*(?:streamlit|استریم)',r'نسخه.*(?:python|پایتون)',r'سیستم.?عامل',r'مرورگر',r'maxUploadSize'])
    if targets>1: findings.append({'criterion':'next_step_usefulness','reason':'پرسش: چند مشخصهٔ محیط یکجا خواسته شده‌اند؛ فقط یک مجهول یا یک آزمایش تمایزدهنده درخواست شود.'})
    return findings

def compact_context(state):
    """Keep the complete initial input (max 20k chars), prioritize corrections.

    Byte budget accounts for Persian text. Oversized reports use head AND tail,
    with explicit truncation. Inventory is exact reported spans, not gold labels.
    """
    inventory=report_inventory(state); plan=state.get('investigation_plan',{})
    experiments=state.get('experiments',[])[-24:]
    messages=state.get('messages',[]); packed=[]; remaining=max(6000,18000-len(canonical({'inventory':inventory,'plan':plan,'experiments':experiments}).encode()))
    for m in reversed(messages[1:][-6:]):
        raw=m['text']; text=raw.encode()[:min(3500,remaining)].decode('utf-8',errors='ignore')
        packed.insert(0,{'text':text,'truncated':text!=raw}); remaining-=len(text.encode())
    if messages:
        raw=clean_report(messages[0]['text']); b=raw.encode()
        if len(b)>remaining:
            half=max(0,(remaining-100)//2)
            text=b[:half].decode('utf-8',errors='ignore')+'\n[REPORT MIDDLE TRUNCATED]\n'+b[-half:].decode('utf-8',errors='ignore')
        else: text=raw
        packed.insert(0,{'text':text,'truncated':text!=raw})
    return {'facts':state.get('facts',{}),'completed_checks':state.get('checks',[])[-30:],
            'experiments':state.get('experiments',[])[-24:], 'memory_version':state.get('memory_version'),
            'fact_provenance':state.get('fact_provenance',{}),
            'version_roles':state.get('version_roles',[])[-20:],
            'investigation_plan':plan,
            'messages':packed,'report_inventory':inventory,
            'context_truncated':any(x['truncated'] for x in packed) or len(packed)!=len(messages) or len(state.get('experiments',[]))>24}

def retrieval_query(state,message):
    """Bound embedding input around the problem, APIs and latest correction.

    Debug-info boilerplate/complete code no longer dominate similarity. Exact
    error identifiers and title retain priority. No issue number/source routing.
    """
    original=clean_report(state['messages'][0]['text']); title=original.splitlines()[0]
    # A checklist commonly precedes Summary. Skip that section rather than
    # truncating the entire technical report at its first heading.
    body=re.sub(r'(?ims)^#{1,6}\s*checklist\b.*?(?=^#{1,6}\s|\Z)',' ',original)
    body=re.split(r'(?im)^#{1,6}\s*(?:debug info|additional information|community voting)',body)[0]
    body=re.sub(r'```.*?```',' ',body,flags=re.S)
    body=re.sub(r'https?://\S+',' ',body)
    body=re.sub(r'(?m)^\s*[-*]?\s*\[[xX ]\].*$',' ',body)
    apis=report_inventory(state)['mentioned_apis']
    errors=list(dict.fromkeys(re.findall(r'\b[A-Z]\w*(?:Error|Exception)\b',original)))[:8]
    latest=clean_report(message) if len(state['messages'])>1 else ''
    pieces=[title[:350],'APIs: '+' '.join(apis[:16]),'Errors: '+' '.join(errors),
            'Latest: '+latest[:400] if latest else '',body[len(title):][:850]]
    return '\n'.join(x for x in pieces if x.strip())[:2200]

def revision_hash(): return digest({'revision':REVISION})
