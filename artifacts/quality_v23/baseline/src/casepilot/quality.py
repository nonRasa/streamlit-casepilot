"""V2.1 quality controls derived from development failures, never case IDs/labels.

The frozen V2 corpus is unchanged. Selection filters apply at query time so old
snapshots and the private embedding cache remain reproducible.
"""
import re
from .common import digest,canonical

REVISION = 'v2.2-quality'
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
    # Exact spans only, explicitly not established diagnoses or permissions.
    spans=[]
    for line in initial.splitlines():
        s=line.strip()
        if not s or BOILERPLATE.search(s): continue
        if re.search(r'(?i)\b(?:tried|tested|attempted|already|works?|fails?|doesn.t|didn.t|instead|workaround|expected|actual|memory|\d+\s*(?:GB|MB)|version)\b|امتحان|آزمایش|نسخه|حافظه|اصلاح',s):
            spans.append(s[:300])
    return {'reported_spans':spans[:10], 'code_blocks_present':len(code), 'mentioned_apis':apis,'known_constraints':constraints,
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
    if answer['decision']!='ask': return []
    q=answer['question']+' '+answer['next_step']; c=known_constraints(state); findings=[]
    def add(reason): findings.append({'criterion':'avoids_repeated_check','reason':reason})
    if c['upload_limit_spans'] and re.search(r'(?i)maxUploadSize',q) and not re.search(r'(?i)maxUploadSize\s*[=:]\s*\d+',q):
        add('تنظیم: حد آپلود قبلاً صریح آمده است: '+'؛ '.join(c['upload_limit_spans'])+'؛ تغییر آزمایش باید مقدار یا شرط تازهٔ مشخص داشته باشد.')
    if c['outside_pickle_result_spans'] and re.search(r'(?i)pickle|پیکل|پیکله',q) and re.search(r'(?i)outside|خارج|بیرون',q):
        add('آزمایش: نتیجهٔ پیکله بیرون برنامه قبلاً گزارش شده است: '+c['outside_pickle_result_spans'][0])
    if c['defined_classes'] and re.search(r'نمونه(?:ٔ|\s)*کامل.*کلاس|تعریف.*کلاس|ساختار.*کلاس|کد.*کلاس',q) and re.search(r'ارائه|بفرست|ارسال|نمونه.*کامل',q):
        add('کد: تعریف کلاس در گزارش موجود است؛ فقط بخشِ واقعاً ارائه‌نشده خواسته شود: '+', '.join(c['defined_classes']))
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
            'investigation_plan':plan,
            'messages':packed,'report_inventory':inventory,
            'context_truncated':any(x['truncated'] for x in packed) or len(packed)!=len(messages) or len(state.get('experiments',[]))>24}

def retrieval_query(state,message):
    """Bound embedding input around the problem, APIs and latest correction.

    Debug-info boilerplate/complete code no longer dominate similarity. Exact
    error identifiers and title retain priority. No issue number/source routing.
    """
    original=clean_report(state['messages'][0]['text']); title=original.splitlines()[0]
    body=re.split(r'(?im)^#{1,6}\s*(?:debug info|additional information|checklist|community voting)',original)[0]
    body=re.sub(r'```.*?```',' ',body,flags=re.S)
    body=re.sub(r'https?://\S+',' ',body)
    body=re.sub(r'(?m)^\s*[-*]?\s*\[[xX ]\].*$',' ',body)
    apis=report_inventory(state)['mentioned_apis']
    errors=list(dict.fromkeys(re.findall(r'\b[A-Z]\w*(?:Error|Exception)\b',original)))[:8]
    latest=clean_report(message) if len(state['messages'])>1 else ''
    pieces=[title[:350],'APIs: '+' '.join(apis[:16]),'Errors: '+' '.join(errors),
            'Latest: '+latest[:400] if latest else '',body[len(title):][:1100]]
    return '\n'.join(x for x in pieces if x.strip())[:2200]

def revision_hash(): return digest({'revision':REVISION})
