"""V2.1 quality controls derived from development failures, never case IDs/labels.

The frozen V2 corpus is unchanged. Selection filters apply at query time so old
snapshots and the private embedding cache remain reproducible.
"""
import re
from .common import digest

REVISION = 'v2.1-quality'
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
    # Exact spans only, explicitly not established diagnoses or permissions.
    spans=[]
    for line in initial.splitlines():
        s=line.strip()
        if not s or BOILERPLATE.search(s): continue
        if re.search(r'(?i)\b(?:tried|tested|attempted|already|works?|fails?|doesn.t|didn.t|instead|workaround|expected|actual|memory|\d+\s*(?:GB|MB)|version)\b|امتحان|آزمایش|نسخه|حافظه|اصلاح',s):
            spans.append(s[:300])
    return {'reported_spans':spans[:10], 'code_blocks_present':len(code), 'mentioned_apis':apis,
            'authoritative_current_facts':state.get('facts',{}),
            'correction_rule':'Latest structured facts supersede historical report values. The original report remains a reported observation, not independently verified truth.'}

def compact_context(state):
    """Keep the complete initial input (max 20k chars), prioritize corrections.

    Byte budget accounts for Persian text. Oversized reports use head AND tail,
    with explicit truncation. Inventory is exact reported spans, not gold labels.
    """
    messages=state.get('messages',[]); packed=[]; remaining=18000
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
            'messages':packed,'report_inventory':report_inventory(state),
            'context_truncated':any(x['truncated'] for x in packed) or len(packed)!=len(messages)}

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
