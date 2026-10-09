"""Lossless wire compression around the unchanged semantic acceptance gate."""
from copy import deepcopy
import re
from .common import digest, require
from .roles import obj, CRITERIA, BOUNDARY
from .review_contract import KINDS, SUPPORT

ACTS=('request','observation','diagnostic','procedure','technical','unknown')
VERSION='readable-semantic-4'
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
        'kinds':list(KINDS),'support_labels':list(SUPPORT),'acts':list(ACTS),
        'units':{a:{'unit_id':u['unit_id'],'phrases':u['phrases']} for a,u in c['units'].items()},
        'sources':{a:s['span_id'] for a,s in c['sources'].items()},
        'messages':{a:{k:v for k,v in m.items() if k!='text'} for a,m in c['messages'].items()}}
    return c,public

def schema(c):
    # Gateway rejects uniqueItems. Uniqueness is a relational reference invariant
    # checked by refs() below, like exact draft binding and phrase contiguity.
    def refs(keys): return {'type':'array','maxItems':min(3,len(keys)),'items':{'type':'string',**({'enum':list(keys)} if keys else {})}}
    def indices(n): return {'type':'string','enum':list(phrase_ranges(n))}
    short={'type':'string','maxLength':80}
    nonempty={'type':'string','minLength':1,'maxLength':80,'pattern':r'\S'}
    reviews={}
    for a,u in c['units'].items():
        allowed=['technical_claim'] if u['field'].startswith('claims.') else (['request_summary'] if u['field'].startswith('feature_proposal.') else (['hypothesis'] if u['field'].startswith('hypotheses.') else (['question','technical_claim'] if u['field']=='question' else list(KINDS))))
        reviews[a]=obj({'k':{'type':'string','enum':allowed},'a':{'type':'string','enum':list(ACTS)},
            's':{'type':'string','enum':list(SUPPORT)},'e':refs(c['sources']),'m':refs(c['messages']),
            'p':indices(len(u['phrases'])),'d':refs([x for x in c['units'] if x!=a]),
            'i':{'type':'boolean'},'v':{'type':'boolean'},'l':indices(len(u['phrases'])),'r':nonempty})
    return obj({'b':{'type':'string','enum':[c['binding']]},'v':{'type':'string','enum':['accept','repair','escalate']},
        'a':{'type':'array','minItems':6,'maxItems':6,'items':{'type':'integer','enum':[0,1,2]}},
        'r':{'type':'array','minItems':6,'maxItems':6,'items':nonempty},'u':obj(reviews),
        'n':obj({'u':{'type':'boolean'},'s':{'type':'string','enum':['new','repeated','unknown']},
            'm':refs(c['messages']),'l':{'type':'string','enum':['answers_requested_detail','equivalent_experiment','context_only','unknown']},'r':nonempty})})

def phrase_ranges(n):
    """Lossless contiguous-range catalog; duplicates/order cannot be expressed."""
    return {'none':[],**{f'phrases_{a}_to_{b}':list(range(a,b+1)) for a in range(n) for b in range(a,n)}}


PROMPT=BOUNDARY+'''
Return ONLY readable-semantic-4 matching the supplied schema. This is the sole active judge wire contract. Review the entire text of EVERY supplied unit, including assertions inside questions, proposals and hypotheses and claims.*.quote quotation units.
b=exact binding. v=verdict. a=six scores in criteria_order (0=defect,1=uncertain,2=adequate). r=six NONEMPTY Persian reasons, each <=80 characters, including successful checks. u=ALL u0/u1/... keys.
Per unit: k=readable kind label; a=readable speech-act label; s=readable support label. supported means direct entailment of the whole assertion, partial means incomplete, contradicted means opposite, unknown means no adequate evidence. Never emit numeric semantic codes.
e=source aliases ONLY s0/...; m=user phrase aliases ONLY m0/... supporting the SPECIFIC request/observation. No duplicate references are allowed in any list. An alias refers to the exact [start,end) substring of its span in spans.messages; blank headings/unrelated context do not support a detail.
p=ONE allowed range label for the technical assertion IN THIS unit, or "none". For example phrases_0_to_2 covers complete phrases 0,1,2; phrases_0_to_0 covers only phrase 0. Never emit arrays or duplicate/order phrase indices. Unit phrases are [start,end) slices covering its ENTIRE text; choose enough complete slices to contain the assertion. Never omit an assertion hidden in a request/question. l=ONE range label containing a visible version limitation, or "none". d=other unit aliases required as prerequisites. i=standalone; v=version-dependent. r=one short Persian reason <=80 characters. The server derives premise from p, resolves exact assertion text, exact user quotation and all full IDs; do not rewrite those texts.
Desired hypothetical behavior, a proposal constraint or acceptance condition describes a REQUEST, not a claim that a product already supports it. Use act=request, p="none" and exact user message aliases for a faithful proposal. Select p only for a separate assertion of existing behavior/API, guaranteed fix or proven cause; do not mark every prose unit as a technical assertion. Procedural design decisions have no technical premise. A field can still contain a hidden technical claim: classify and reject it when unsupported. A missing current behavior must stay unknown; a request to add an option does not prove that the option is currently absent.
n: u=useful, s=novelty status, m=user phrase aliases, l=relation, r=NONEMPTY reason. Find the requested detail or equivalent PERFORMED test across ALL supplied report/code/messages and experiments. Proposed checks and context_only do not prove repetition. If complete history is unavailable, novelty cannot be certified new.
Technical assertions, including hypotheses and assertions hidden in questions, require direct source support. Topic similarity and an issue report do not prove cause; official status does not prove relevance. Literal quotation membership is not entailment. A code import does not prove behavior or accessibility. A user observation cannot establish a product limit or guaranteed fix.
Each claims.*.quote unit is an actual selected technical quotation shown in the answer. Link it only to its OWN selected source, set act=technical, select p covering the ENTIRE quotation, and select l covering its visible provenance-derived version limitation if present. Check that it answers or meaningfully informs this user's question; an unrelated literal quote is a relevance defect. Procedural next steps may refer the reader to this separately reviewed quotation without reasserting its technical contents. Do not require an orphan-prone paraphrase in rationale merely to link a citation. A targeted question about a reported observation is diagnostic, not a product behavior assertion just because it names an API. Translation of a conditional acceptance criterion remains a request; it does not claim existing API availability.
reported_fact must be an exact user excerpt inside a text fence following گزارش کاربر:. Feature fields use request_summary and describe desired behavior/acceptance, never an existing API. Current behavior starts گزارش کاربر:. The canonical unknown feature detail may have unknown support and act=unknown. A procedural next step or missing-field question may have unknown support without a technical premise. A clear feature needs a specific design decision and acceptance condition, not a prototype or hypothetical API documentation.
Version-dependent claims need matching product_version or a visible limitation selected in l. Missing version is unknown; document date/revision is not product version. No version-dependent assertion means version_fit can be 2.
Dependencies list all required units; standalone=true only if independently useful. A changed draft always needs a fresh complete review. Accept only when all six scores are 2, all units are valid and the next step is useful. Contradiction, unsupported assertions, repeated questions/tests or orphan citations require repair/escalate. Keep contract failure separate from negative content judgement. No dropped units or guessed aliases. Every unit and novelty reason must contain non-whitespace text.
'''

def decode(raw,c):
    # Exactly the schema sent to the provider is the structural source of truth.
    from jsonschema import Draft202012Validator
    require(not any(Draft202012Validator(schema(c)).iter_errors(raw)),
            'judge_contract_error','خروجی داور با قرارداد ارسالی یکسان نیست.')
    def check(ok,detail='reference_or_binding'): require(ok,'judge_contract_error','قالب داور نامعتبر است: '+detail)
    def refs(value,catalog):
        check(isinstance(value,list) and len(value)<=3 and all(isinstance(x,str) and x in catalog for x in value),'unknown_reference')
        check(len(set(value))==len(value),'duplicate_reference')
        return [catalog[x] for x in value]
    def phrase(value,u):
        catalog=phrase_ranges(len(u['phrases']))
        check(isinstance(value,str) and value in catalog,'invalid_phrase_range')
        value=catalog[value]
        return u['text'][u['phrases'][value[0]][0]:u['phrases'][value[-1]][1]] if value else ''
    def reason(value,empty=False): check(isinstance(value,str) and len(value)<=80 and (empty or bool(value.strip()))); return value
    check(isinstance(raw,dict) and set(raw)=={'b','v','a','r','u','n'})
    check(raw['b']==c['binding'] and raw['v'] in ('accept','repair','escalate'))
    check(isinstance(raw['a'],list) and len(raw['a'])==6 and all(type(x) is int and x in (0,1,2) for x in raw['a']))
    check(isinstance(raw['r'],list) and len(raw['r'])==6)
    assessments={k:{'score':s,'reason':reason(r)} for k,s,r in zip(CRITERIA,raw['a'],raw['r'])}
    check(isinstance(raw['u'],dict) and set(raw['u'])==set(c['units']))
    entries=[]
    for a,u in c['units'].items():
        e=raw['u'][a]; check(isinstance(e,dict) and set(e)=={'k','a','s','e','m','p','d','i','v','l','r'})
        for key,catalog in [('k',KINDS),('a',ACTS),('s',SUPPORT)]: check(e[key] in catalog)
        check(type(e['i']) is bool and type(e['v']) is bool)
        src=refs(e['e'],c['sources']); msg=refs(e['m'],c['messages']); deps=refs(e['d'],{x:y for x,y in c['units'].items() if x!=a})
        assertion=phrase(e['p'],u)
        entries.append({'unit_id':u['unit_id'],'kind':e['k'],'support':e['s'],
            'source_ids':[s['span_id'] for s in src],'message_ids':list(dict.fromkeys(m['span_id'] for m in msg)),
            'premise':bool(assertion),'standalone':e['i'],'version_dependent':e['v'],'version_limit':phrase(e['l'],u),
            'reason':reason(e['r']),'meaning':{'act':e['a'],'assertion_text':assertion,
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
    def phrase(text,u):
        indexes=[i for i,(s,e) in enumerate(u['phrases']) if text and s<u['text'].find(text)+len(text) and e>u['text'].find(text)]
        return f'phrases_{indexes[0]}_to_{indexes[-1]}' if indexes else 'none'
    entries={}
    for e in result['unit_reviews']:
        a=um[e['unit_id']]; u=c['units'][a]; m=e['meaning']
        entries[a]={'k':e['kind'],'a':m['act'],'s':e['support'],
            'e':[sm[x] for x in e['source_ids']], 'm':messages(e['message_ids'],m['user_quote']),
            'p':phrase(m['assertion_text'],u),'d':[um[x] for x in m['depends_on']], 'i':e['standalone'],
            'v':e['version_dependent'],'l':phrase(e['version_limit'],u),'r':e['reason'][:80]}
    n=result['novelty']
    return {'b':c['binding'] if result['draft_version']==c['draft_version'] else result['draft_version'],'v':result['verdict'],'a':[result['assessments'][k]['score'] for k in CRITERIA],
        'r':[result['assessments'][k]['reason'][:80] for k in CRITERIA],
        'u':entries,'n':{'u':n['useful'],'s':n['status'],'m':messages(n['message_ids']),'l':n['relation'],'r':n['reason'][:80]}}
