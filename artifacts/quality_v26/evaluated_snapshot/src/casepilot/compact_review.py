"""Lossless wire compression around the unchanged semantic acceptance gate."""
from copy import deepcopy
import re
from .common import digest, require
from .roles import obj, CRITERIA, SEMANTIC_JUDGE_PROMPT
from .review_contract import KINDS, SUPPORT

ACTS=('request','observation','diagnostic','procedure','technical','unknown')
VERSION='compact-semantic-1'
MAX_UNITS=11  # سه متن اصلی، سه فرضیه و پنج مشخصه؛ سقف تولید واقعی ۹ است.

def fragments(text):
    """Contiguous coverage, including punctuation and whitespace; no omitted tail."""
    rows=[]; start=0
    while start<len(text):
        end=min(len(text),start+120)
        stops=list(re.finditer(r'[.!?؟؛\n](?:\s|$)|،\s',text[start:end]))
        if end<len(text) and stops and stops[-1].end()>=20: end=start+stops[-1].end()
        rows.append([start,end]); start=end
    return rows

def contract(envelope,spans):
    require(0<len(envelope['units'])<=MAX_UNITS,'judge_contract_error','ظرفیت واحدهای قرارداد معتبر نیست.')
    units={f'u{i}':dict(unit,phrases=fragments(unit['text'])) for i,unit in enumerate(envelope['units'])}
    sources={f's{i}':s for i,s in enumerate(spans['sources'])}
    messages={}
    for span in spans['messages']:
        for start,end in fragments(span['text']):
            messages[f'm{len(messages)}']={'span_id':span['span_id'],'start':start,'end':end,'text':span['text'][start:end]}
    return {'version':VERSION,'binding':digest({'version':VERSION,'draft':envelope,'spans':spans}),
            'units':units,'sources':sources,'messages':messages,'draft_version':envelope['draft_version']}

def packet(envelope,spans):
    c=contract(envelope,spans)
    # متن واحدها و شاهدها در draft/spans موجود است؛ تنها ارجاع‌ها افزوده می‌شوند.
    public={'version':VERSION,'binding':c['binding'],'criteria_order':list(CRITERIA),
        'kind_order':list(KINDS),'support_order':list(SUPPORT),'act_order':list(ACTS),
        'units':{a:{'unit_id':u['unit_id'],'phrases':u['phrases']} for a,u in c['units'].items()},
        'sources':{a:s['span_id'] for a,s in c['sources'].items()},
        'messages':{a:{k:v for k,v in m.items() if k!='text'} for a,m in c['messages'].items()}}
    return c,public

def schema(c):
    def refs(keys): return {'type':'array','maxItems':min(3,len(keys)),'items':{'type':'string',**({'enum':list(keys)} if keys else {})}}
    def indices(n): return {'type':'array','maxItems':n,'items':{'type':'integer','minimum':0,'maximum':max(0,n-1)}}
    short={'type':'string','maxLength':80}
    reviews={}
    for a,u in c['units'].items():
        allowed=[KINDS.index('request_summary')] if u['field'].startswith('feature_proposal.') else ([KINDS.index('hypothesis')] if u['field'].startswith('hypotheses.') else ([KINDS.index('question'),KINDS.index('technical_claim')] if u['field']=='question' else list(range(len(KINDS)))))
        reviews[a]=obj({'k':{'type':'integer','enum':allowed},'a':{'type':'integer','enum':list(range(len(ACTS)))},
            's':{'type':'integer','enum':list(range(len(SUPPORT)))},'e':refs(c['sources']),'m':refs(c['messages']),
            'p':indices(len(u['phrases'])),'d':refs([x for x in c['units'] if x!=a]),
            'i':{'type':'boolean'},'v':{'type':'boolean'},'l':indices(len(u['phrases'])),'r':short})
    return obj({'b':{'type':'string','enum':[c['binding']]},'v':{'type':'string','enum':['accept','repair','escalate']},
        'a':{'type':'array','minItems':6,'maxItems':6,'items':{'type':'integer','enum':[0,1,2]}},
        'r':{'type':'array','minItems':6,'maxItems':6,'items':short},'u':obj(reviews),
        'n':obj({'u':{'type':'boolean'},'s':{'type':'string','enum':['new','repeated','unknown']},
            'm':refs(c['messages']),'l':{'type':'string','enum':['answers_requested_detail','equivalent_experiment','context_only','unknown']},'r':short})})

PROMPT=SEMANTIC_JUDGE_PROMPT+'''
WIRE OVERRIDE: Return ONLY compact-semantic-1 matching the schema. The checks above are unchanged; use the compact_contract mappings, never old long IDs in output.
b=exact binding. v=verdict. a=six scores in criteria_order. r=six Persian reasons, EMPTY for score2 and one decision-making sentence <=80 characters for a lower score. u=ALL u0/u1/... keys.
Per unit: k=index in kind_order; a=index in act_order; s=index in support_order; e=source aliases ONLY s0/...; m=user phrase aliases ONLY m0/... supporting the SPECIFIC request/observation. An alias refers to the exact [start,end) substring of its span in spans.messages; blank headings/unrelated context do not support a detail.
p=ordered contiguous phrase indices of the technical assertion IN THIS unit, or [] when none. Unit phrases are [start,end) slices covering its ENTIRE text; choose enough complete slices to contain the assertion. Never omit an assertion hidden in a request/question. l=contiguous unit phrase indices containing a visible version limitation, or []. d=other unit aliases required as prerequisites. i=standalone; v=version-dependent. r=one short Persian reason <=80 characters. The server derives premise from p, resolves exact assertion text, exact user quotation and all full IDs; do not rewrite those texts.
n: u=useful, s=novelty status, m=user phrase aliases, l=relation, r=short reason. All earlier semantic, attribution, dependency, version, novelty and six-score checks apply. No dropped units and no guessed aliases. Empty successful score reasons only reduce repetition; they do not reduce checks.
'''

def decode(raw,c):
    def check(ok): require(ok,'judge_contract_error','قالب فشردهٔ داور ناقص، منقضی یا دارای ارجاع نامعتبر است.')
    def refs(value,catalog):
        check(isinstance(value,list) and len(value)<=3 and all(isinstance(x,str) and x in catalog for x in value) and len(set(value))==len(value))
        return [catalog[x] for x in value]
    def phrase(value,u):
        check(isinstance(value,list) and len(value)<=len(u['phrases']) and all(type(x) is int and 0<=x<len(u['phrases']) for x in value))
        check(not value or value==list(range(value[0],value[-1]+1)))
        return u['text'][u['phrases'][value[0]][0]:u['phrases'][value[-1]][1]] if value else ''
    def reason(value,empty=False): check(isinstance(value,str) and len(value)<=80 and (empty or bool(value.strip()))); return value
    check(isinstance(raw,dict) and set(raw)=={'b','v','a','r','u','n'})
    check(raw['b']==c['binding'] and raw['v'] in ('accept','repair','escalate'))
    check(isinstance(raw['a'],list) and len(raw['a'])==6 and all(type(x) is int and x in (0,1,2) for x in raw['a']))
    check(isinstance(raw['r'],list) and len(raw['r'])==6)
    assessments={k:{'score':s,'reason':reason(r,empty=s==2) or 'بررسی: ایرادی گزارش نشده است.'} for k,s,r in zip(CRITERIA,raw['a'],raw['r'])}
    check(isinstance(raw['u'],dict) and set(raw['u'])==set(c['units']))
    entries=[]
    for a,u in c['units'].items():
        e=raw['u'][a]; check(isinstance(e,dict) and set(e)=={'k','a','s','e','m','p','d','i','v','l','r'})
        for key,catalog in [('k',KINDS),('a',ACTS),('s',SUPPORT)]: check(type(e[key]) is int and 0<=e[key]<len(catalog))
        check(type(e['i']) is bool and type(e['v']) is bool)
        src=refs(e['e'],c['sources']); msg=refs(e['m'],c['messages']); deps=refs(e['d'],{x:y for x,y in c['units'].items() if x!=a})
        assertion=phrase(e['p'],u)
        entries.append({'unit_id':u['unit_id'],'kind':KINDS[e['k']],'support':SUPPORT[e['s']],
            'source_ids':[s['span_id'] for s in src],'message_ids':list(dict.fromkeys(m['span_id'] for m in msg)),
            'premise':bool(assertion),'standalone':e['i'],'version_dependent':e['v'],'version_limit':phrase(e['l'],u),
            'reason':reason(e['r']),'meaning':{'act':ACTS[e['a']],'assertion_text':assertion,
                'user_quote':msg[0]['text'] if msg else '', 'depends_on':[d['unit_id'] for d in deps]}})
    n=raw['n']; check(isinstance(n,dict) and set(n)=={'u','s','m','l','r'} and type(n['u']) is bool)
    check(n['s'] in ('new','repeated','unknown') and n['l'] in ('answers_requested_detail','equivalent_experiment','context_only','unknown'))
    msg=refs(n['m'],c['messages'])
    return {'verdict':raw['v'],'assessments':assessments,'draft_version':c['draft_version'],'unit_reviews':entries,
        'novelty':{'useful':n['u'],'status':n['s'],'message_ids':list(dict.fromkeys(m['span_id'] for m in msg)), 'relation':n['l'],'reason':reason(n['r'])}}

def encode_fixture(result,c):
    """Explicit test/evaluation adapter; never used to salvage provider output."""
    um={u['unit_id']:a for a,u in c['units'].items()}; sm={s['span_id']:a for a,s in c['sources'].items()}
    def messages(ids,quote=''):
        return [a for a,m in c['messages'].items() if m['span_id'] in ids and (not quote or quote in m['text'] or m['text'] in quote)][:3]
    def phrase(text,u): return [i for i,(s,e) in enumerate(u['phrases']) if text and s<u['text'].find(text)+len(text) and e>u['text'].find(text)]
    entries={}
    for e in result['unit_reviews']:
        a=um[e['unit_id']]; u=c['units'][a]; m=e['meaning']
        entries[a]={'k':KINDS.index(e['kind']),'a':ACTS.index(m['act']),'s':SUPPORT.index(e['support']),
            'e':[sm[x] for x in e['source_ids']], 'm':messages(e['message_ids'],m['user_quote']),
            'p':phrase(m['assertion_text'],u),'d':[um[x] for x in m['depends_on']], 'i':e['standalone'],
            'v':e['version_dependent'],'l':phrase(e['version_limit'],u),'r':e['reason'][:80]}
    n=result['novelty']
    return {'b':c['binding'] if result['draft_version']==c['draft_version'] else result['draft_version'],'v':result['verdict'],'a':[result['assessments'][k]['score'] for k in CRITERIA],
        'r':[result['assessments'][k]['reason'][:80] if result['assessments'][k]['score']<2 else '' for k in CRITERIA],
        'u':entries,'n':{'u':n['useful'],'s':n['status'],'m':messages(n['message_ids']),'l':n['relation'],'r':n['reason'][:80]}}
