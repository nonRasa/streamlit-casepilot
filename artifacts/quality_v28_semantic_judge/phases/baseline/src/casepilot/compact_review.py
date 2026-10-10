"""Lossless wire compression around the unchanged semantic acceptance gate."""
from copy import deepcopy
import re
from .common import digest, require
from .roles import obj, CRITERIA, BOUNDARY
from .review_contract import KINDS, SUPPORT
from .assertion_audit import candidates as assertion_candidates

ACTS=('request','observation','diagnostic','procedure','technical','unknown')
VERSION='descriptive-semantic-7'
HISTORICAL_MAX_UNITS=11
ACTIVE_MAX_UNITS=39  # سقف پاسخ V2، شامل تشخیص کامل، ۱۰ شرط و ۴ گزیدهٔ گزارش.

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
    limit=ACTIVE_MAX_UNITS if envelope.get('unit_contract')=='citation-units-v1' else HISTORICAL_MAX_UNITS
    require(0<len(envelope['units'])<=limit,'judge_contract_error','ظرفیت واحدهای قرارداد معتبر نیست.')
    units={f'u{i}':dict(unit,phrases=fragments(unit['text']),
        audit_candidates=assertion_candidates(unit.get('audited_text',unit['text']),unit['field']))
        for i,unit in enumerate(envelope['units'])}
    for unit in units.values():
        if unit['audit_candidates']:
            labels=_candidate_ranges(unit)
            catalogs=phrase_ranges(len(unit['phrases']))
            unit['candidate_assertion_range']=min(labels,key=lambda label:len(catalogs[label]))
        if unit['field'].startswith('claims.'):
            quote=unit.get('audited_text','')
            require(bool(quote) and unit['text'].startswith(quote),'judge_contract_error',
                    'نقل‌قول منتخب باید پیشوند دقیق واحد بازبینی باشد.')
            unit['claim_assertion_range']=_range_for_span(unit,0,len(quote))
            notice=unit['text'][len(quote):].strip()
            offset=unit['text'].find(notice) if notice else -1
            unit['claim_version_limit_range']=(_range_for_span(unit,offset,offset+len(notice))
                                               if notice else 'none')
    sources={f's{i}':s for i,s in enumerate(spans['sources'])}
    messages={}
    for span in spans['messages']:
        for start,end in fragments(span['text']):
            messages[f'm{len(messages)}']={'span_id':span['span_id'],'message_index':span.get('message_index'),
                'start':span['start']+start,'end':span['start']+end,'text':span['text'][start:end]}
    return {'version':VERSION,'binding':digest({'version':VERSION,'draft':envelope,'spans':spans}),
            'units':units,'sources':sources,'messages':messages,'draft_version':envelope['draft_version']}

def packet(envelope,spans):
    c=contract(envelope,spans)
    # متن واحدها و شاهدها در draft/spans موجود است؛ تنها ارجاع‌ها افزوده می‌شوند.
    public={'version':VERSION,'binding':c['binding'],'criteria_order':list(CRITERIA),
        'kinds':list(KINDS),'support_labels':list(SUPPORT),'acts':list(ACTS),
        'units':{a:{'unit_id':u['unit_id'],'field':u['field'],'phrases':u['phrases'],
            'mandatory_claim_candidates':u['audit_candidates']} for a,u in c['units'].items()},
        'sources':{a:s['span_id'] for a,s in c['sources'].items()},
        'messages':{a:{k:v for k,v in m.items() if k!='text'} for a,m in c['messages'].items()}}
    return c,public

def schema(c):
    # Gateway rejects uniqueItems. Uniqueness is a relational reference invariant
    # checked by refs() below, like exact draft binding and phrase contiguity.
    feature_dependencies=[alias for alias,unit in c['units'].items()
        if unit['field'].startswith('feature_proposal.') and
        not unit['field'].startswith('feature_proposal.report_quotes.')]
    defs={'source_alias':{'type':'string',**({'enum':list(c['sources'])} if c['sources'] else {})},
          'message_alias':{'type':'string',**({'enum':list(c['messages'])} if c['messages'] else {})},
          'feature_unit_alias':{'type':'string',**({'enum':feature_dependencies} if feature_dependencies else {})},
          'unit_alias':{'type':'string',**({'enum':list(c['units'])} if c['units'] else {})}}
    def refs(name,keys,max_items=3):
        return {'type':'array','maxItems':min(max_items,len(keys)),
                'items':{'$ref':'#/$defs/'+name}}
    nonempty={'type':'string','minLength':1,'maxLength':80,'pattern':r'\S'}
    reviews={}
    for alias,unit in c['units'].items():
        field=unit['field']
        allowed=['technical_claim'] if field.startswith('claims.') else (
            ['request_summary'] if field.startswith('feature_proposal.') else (
            ['hypothesis'] if field.startswith('hypotheses.') else (
            ['question','technical_claim'] if field=='question' else list(KINDS))))
        if unit['audit_candidates'] and 'technical_claim' not in allowed:
            allowed.append('technical_claim')
        assertion_range={'type':'string','pattern':r'^(?:none|phrases_[0-9]+_to_[0-9]+)$'}
        if unit['audit_candidates']:
            # The model cannot label a detected technical span as a procedure
            # or select "none"; support and relevance are reviewed separately.
            assertion_range={'type':'string','enum':[unit['candidate_assertion_range']]}
        unit_props={'k':{'type':'string','enum':allowed},'a':{'type':'string','enum':list(ACTS)},
            's':{'type':'string','enum':list(SUPPORT)},'e':refs('source_alias',c['sources']),
            'm':refs('message_alias',c['messages']),'p':assertion_range,
            'd':refs('feature_unit_alias',feature_dependencies) if field.startswith('feature_proposal.report_quotes.') else refs('unit_alias',c['units']),
            'i':{'type':'boolean'},
            'v':{'type':'boolean'},'l':{'type':'string','enum':_visible_limit_ranges(unit,c['sources'])},'r':nonempty}
        from .semantics import UNKNOWN
        if unit['text'] in (UNKNOWN,'هدف: درخواست روشن کاربر برای تصمیم طراحی نگه‌دارنده آماده می‌شود؛ جزئیات رفتار و شرط پذیرش در پیشنهاد آمده‌اند.'):
            unit_props['k']={'type':'string','enum':['request_summary' if unit['text']==UNKNOWN else 'next_step']}
            unit_props['a']={'type':'string','enum':['unknown' if unit['text']==UNKNOWN else 'procedure']}
            unit_props['s']={'type':'string','enum':['unknown']}
            for key in ('p','l'):unit_props[key]={'type':'string','enum':['none']}
            for key in ('e','m','d'):unit_props[key]['maxItems']=0
            unit_props['v']={'type':'boolean','enum':[False]}
        if field in ('rationale','next_step'):
            kinds=['next_step','technical_claim','request_summary']
            if re.fullmatch(r'گزارش کاربر:\s*```text\n.+?\n```\s*',unit['text'],re.S):kinds.append('reported_fact')
            if unit['audit_candidates'] and 'technical_claim' not in kinds:kinds.append('technical_claim')
            unit_props['k']={'type':'string','enum':kinds}
        if unit['audit_candidates']:
            unit_props['a']={'type':'string','enum':['technical']}
        if field.startswith('claims.'):
            own={a:s for a,s in c['sources'].items()
                 if unit['text']==s['text'] or unit['text'].startswith(s['text']+'\n')}
            require(bool(own),'judge_contract_error','واحد نقل‌قول به شاهد منتخب متصل نیست.')
            quote=next(iter(own.values()))['text']
            unit_props['p']={'type':'string','enum':[unit['claim_assertion_range']]}
            unit_props['l']={'type':'string','enum':[unit['claim_version_limit_range']]}
            unit_props['a']={'type':'string','enum':['technical']}
            unit_props['e']={'type':'array','minItems':1,'maxItems':min(3,len(own)),
                'items':{'type':'string','enum':list(own)}}
        if field.startswith('feature_proposal.'):
            is_unknown=unit['text'].startswith('نامعلوم: ')
            is_report_quote=field.startswith('feature_proposal.report_quotes.')
            is_current_report=field=='feature_proposal.current_behavior' and unit['text'].startswith('گزارش کاربر:')
            unit_props['d']=refs('feature_unit_alias',feature_dependencies) if is_report_quote else refs('unit_alias',c['units'])
            if unit['audit_candidates']:
                unit_props['k']={'type':'string','enum':['technical_claim']}
                unit_props['a']={'type':'string','enum':['technical']}
                unit_props['s']={'type':'string','enum':list(SUPPORT)}
                unit_props['p']={'type':'string','enum':[unit['candidate_assertion_range']]}
                unit_props['e']=refs('source_alias',c['sources'])
                unit_props['m']=refs('message_alias',c['messages'])
                unit_props['v']={'type':'boolean'}
                unit_props['l']={'type':'string','enum':_visible_limit_ranges(unit,c['sources'])}
            elif is_unknown:
                unit_props['k']={'type':'string','enum':['request_summary']}
                unit_props['a']={'type':'string','enum':['unknown']}
                unit_props['s']={'type':'string','enum':['unknown']}
                unit_props['p']={'type':'string','enum':['none']}
                unit_props['e']=refs('source_alias',c['sources']);unit_props['e']['maxItems']=0
                unit_props['m']=refs('message_alias',c['messages']);unit_props['m']['maxItems']=0
                unit_props['d']=refs('unit_alias',c['units']);unit_props['d']['maxItems']=0
                unit_props['v']={'type':'boolean','enum':[False]}
                unit_props['l']={'type':'string','enum':['none']}
            else:
                unit_props['k']={'type':'string','enum':['request_summary']}
                unit_props['a']={'type':'string','enum':['observation'] if is_current_report else ['request']}
                # Keep negative semantic judgements representable on the wire.
                # The content gate rejects partial/contradicted/unknown support;
                # collapsing them into a schema error hides answer-quality failures.
                unit_props['s']={'type':'string','enum':list(SUPPORT)}
                unit_props['p']={'type':'string','enum':['none']}
                unit_props['e']=refs('source_alias',c['sources']);unit_props['e']['maxItems']=0
                unit_props['m']=refs('message_alias',c['messages']);unit_props['m']['minItems']=1
                unit_props['v']={'type':'boolean','enum':[False]}
                unit_props['l']={'type':'string','enum':['none']}
                if is_report_quote: unit_props['d']['minItems']=1
        unit_schema=obj(unit_props)
        # Share identical schemas across units. This retains per-field hard
        # constraints while avoiding dozens of repeated object definitions.
        variant='unit_review_'+digest(unit_schema)[:16]
        defs.setdefault(variant,unit_schema)
        reviews[alias]={'$ref':'#/$defs/'+variant}
    out=obj({'b':{'type':'string','enum':[c['binding']]},'v':{'type':'string','enum':['accept','repair','escalate']},
        'a':{'type':'array','minItems':6,'maxItems':6,'items':{'type':'integer','enum':[0,1,2]}},
        'r':{'type':'array','minItems':6,'maxItems':6,'items':nonempty},'u':obj(reviews),
        'n':obj({'u':{'type':'boolean'},'s':{'type':'string','enum':['new','repeated','unknown']},
            'm':refs('message_alias',c['messages']),'l':{'type':'string','enum':['answers_requested_detail','equivalent_experiment','context_only','unknown']},'r':nonempty})})
    out['$defs']=defs
    return out

def phrase_ranges(n):
    """Lossless contiguous-range catalog; duplicates/order cannot be expressed."""
    return {'none':[],**{f'phrases_{a}_to_{b}':list(range(a,b+1)) for a in range(n) for b in range(a,n)}}


def _range_for_span(unit,start,end):
    indexes=[i for i,(left,right) in enumerate(unit['phrases']) if left<end and right>start]
    require(bool(indexes),'judge_contract_error','بازهٔ مورد ممیزی در متن همان واحد پیدا نشد.')
    return f'phrases_{indexes[0]}_to_{indexes[-1]}'


_VERSION_NOTICE=re.compile(r'نسخه|محدودیت|انطباق|نامعلوم|نامشخص|تأیید نشده|تایید نشده|version|applicab|unknown|unverified|not confirmed',re.I)


def _version_limit_span(unit,source_aliases,sources):
    """Return only a provenance-derived limitation present in this exact unit."""
    from .grounding import citation_limit
    notices={citation_limit(s) for alias in source_aliases if (s:=sources.get(alias))}
    notices={notice for notice in notices if notice and notice in unit['text']}
    if len(notices)!=1:return 'none'
    notice=next(iter(notices));start=unit['text'].find(notice)
    return _range_for_span(unit,start,start+len(notice))


def _visible_limit_ranges(unit,sources):
    """Only allow labels for code-derived source notices visible in this unit."""
    labels={'none'}
    for alias,row in sources.items():
        label=_version_limit_span(unit,[alias],sources)
        if label!='none':labels.add(label)
    return sorted(labels)


def _candidate_ranges(unit):
    """Phrase ranges that contain every code-detected candidate span."""
    n=len(unit['phrases']); required=set()
    source=unit.get('audited_text',unit['text'])
    for candidate in unit['audit_candidates']:
        position=unit['text'].find(candidate['text'])
        # Claim quotation text is a prefix of its displayed unit; preserve those offsets.
        if position<0 and source != unit['text']:
            position=unit['text'].find(source)
        if position<0:
            continue
        end=position+len(candidate['text'])
        required.update(i for i,(start,stop) in enumerate(unit['phrases']) if start<end and stop>position)
    labels=[]
    for label,indexes in phrase_ranges(n).items():
        if indexes and required and required <= set(indexes): labels.append(label)
    require(bool(required) and bool(labels),'judge_contract_error',
            'عبارت فنی کشف‌شده به بازهٔ کامل واحد پاسخ متصل نیست.')
    return labels


PROMPT=BOUNDARY+'''
Return ONLY readable-semantic-4 matching the supplied schema. This is the sole active judge wire contract. Review the entire text of EVERY supplied unit, including assertions inside questions, proposals and hypotheses and claims.*.quote quotation units.
b=exact binding. v=verdict. a=six scores in criteria_order (0=defect,1=uncertain,2=adequate). r=six NONEMPTY Persian reasons, each <=80 characters, including successful checks. u=ALL u0/u1/... keys.
Per unit: k=readable kind label; a=readable speech-act label; s=readable support label. supported means direct entailment of the whole assertion, partial means incomplete, contradicted means opposite, unknown means no adequate evidence. Never emit numeric semantic codes.
mandatory_claim_candidates are code-derived high-recall spans that require explicit technical-claim review. They are trigger signals, not proof of support. The schema requires a technical assertion range to cover them; do not classify a configuration/API instruction as procedure merely because it is phrased as an action. Use a direct diagnostic question or conditional feature request only when the text makes no technical assertion.
e=source aliases ONLY s0/...; m=user phrase aliases ONLY m0/... supporting the SPECIFIC request/observation. No duplicate references are allowed in any list. An alias refers to the exact [start,end) substring of its span in spans.messages; blank headings/unrelated context do not support a detail.
p=ONE allowed range label for the technical assertion IN THIS unit, or "none". For example phrases_0_to_2 covers complete phrases 0,1,2; phrases_0_to_0 covers only phrase 0. Never emit arrays or duplicate/order phrase indices. Unit phrases are [start,end) slices covering its ENTIRE text; choose enough complete slices to contain the assertion. Never omit an assertion hidden in a request/question. For claims.*.quote, p and l are fixed by the submitted schema: use those exact allowed values. l indexes only visible limitation text in THIS answer unit; it is never a source offset, line number, or range from another unit. Use "none" only when the unit contains no visible limitation. d=other unit aliases required as prerequisites. i=standalone; v=version-dependent. r=one short Persian reason <=80 characters. The server derives premise from p, resolves exact assertion text, exact user quotation and all full IDs; do not rewrite those texts.
Desired hypothetical behavior, a proposal constraint or acceptance condition describes a REQUEST, not a claim that a product already supports it. Feature proposal fields default to request_summary and must be tied to exact user-message aliases. Select p only for an explicit assertion of current behavior/API availability or absence, a guaranteed fix or a proven cause; do not mark conditional acceptance criteria as current technical behavior. A selected report quote must depend on the specific proposal field(s) it supports; selecting a real message section alone does not prove relevance. Procedural diagnostic measurements that distinguish possible outcomes are procedures, not assertions of either outcome. Keep claims hidden in config/API instructions as technical claims, including when the instruction is imperative; a measurement step is not such an instruction unless it tells the user to change/call/configure a specific API or setting.
n: u=useful, s=novelty status, m=user phrase aliases, l=relation, r=NONEMPTY reason. Find the requested detail or equivalent PERFORMED test across ALL supplied report/code/messages and experiments. Proposed checks and context_only do not prove repetition. If complete history is unavailable, novelty cannot be certified new.
Technical assertions, including hypotheses and assertions hidden in questions, require direct source support. The code independently checks candidate coverage even if semantic labels or version_dependent say otherwise. Topic similarity and an issue report do not prove cause; official status does not prove relevance. Literal quotation membership is not entailment. A code import does not prove behavior or accessibility. A user observation cannot establish a product limit or guaranteed fix.
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
        if u['field'].startswith('feature_proposal.report_quotes.'):
            allowed_dependencies={x for x,row in c['units'].items()
                if x!=a and row['field'].startswith('feature_proposal.') and
                not row['field'].startswith('feature_proposal.report_quotes.')}
            check(all(alias in allowed_dependencies for alias in e['d']),'invalid_feature_dependency')
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
        assertion_range=phrase(m['assertion_text'],u)
        if u['audit_candidates'] and all(
                candidate['text'] in m['assertion_text'] for candidate in u['audit_candidates']):
            assertion_range=u['candidate_assertion_range']
        elif u['field'].startswith('claims.') and m['assertion_text']==u['text'][:len(u.get('audited_text',''))]:
            assertion_range=u['claim_assertion_range']
        version_range=phrase(e['version_limit'],u)
        if u['field'].startswith('claims.') and e['version_limit']==u['text'][len(u.get('audited_text','')):].strip():
            version_range=u['claim_version_limit_range']
        entries[a]={'k':e['kind'],'a':m['act'],'s':e['support'],
            'e':[sm[x] for x in e['source_ids']], 'm':messages(e['message_ids'],m['user_quote']),
            'p':assertion_range,'d':[um[x] for x in m['depends_on']], 'i':e['standalone'],
            'v':e['version_dependent'],'l':version_range,'r':e['reason'][:80]}
    n=result['novelty']
    return {'b':c['binding'] if result['draft_version']==c['draft_version'] else result['draft_version'],'v':result['verdict'],'a':[result['assessments'][k]['score'] for k in CRITERIA],
        'r':[result['assessments'][k]['reason'][:80] for k in CRITERIA],
        'u':entries,'n':{'u':n['useful'],'s':n['status'],'m':messages(n['message_ids']),'l':n['relation'],'r':n['reason'][:80]}}

# The production transport uses descriptive names. Both schema and decoder
# derive from the same lossless mapping; old short keys are fixture adapters.
TOP_NAMES={'b':'binding','v':'verdict','a':'criterion_scores','r':'criterion_reasons','u':'unit_reviews','n':'novelty'}
UNIT_NAMES={'k':'kind','a':'speech_act','s':'support','e':'source_aliases','m':'user_phrase_aliases',
    'p':'technical_assertion_range','d':'required_unit_aliases','i':'standalone','v':'version_dependent',
    'l':'visible_version_limit_range','r':'reason'}
NOVELTY_NAMES={'u':'useful','s':'status','m':'user_phrase_aliases','l':'relation','r':'reason'}

def rename_object(node,names):
    out=deepcopy(node)
    out['properties']={names[k]:v for k,v in out['properties'].items()}
    out['required']=[names[k] for k in out['required']]
    return out

def descriptive_schema(c):
    out=schema(c)
    # Each distinct field constraint is defined once and referenced by every
    # matching unit alias; phrase-range membership is checked by the decoder.
    for name,definition in list(out['$defs'].items()):
        if name.startswith('unit_review_'):
            out['$defs'][name]=rename_object(definition,UNIT_NAMES)
    out['properties']['n']=rename_object(out['properties']['n'],NOVELTY_NAMES)
    out=rename_object(out,TOP_NAMES)
    # Named criteria avoid accidentally attaching one criterion's explanation
    # to another. Both directions derive from CRITERIA, without score changes.
    scores=out['properties'].pop('criterion_scores')['items']
    reasons=out['properties'].pop('criterion_reasons')['items']
    out['required']=[k for k in out['required'] if k not in ('criterion_scores','criterion_reasons')]+['assessments']
    out['properties']['assessments']=obj({k:obj({'score':scores,'reason':reasons}) for k in CRITERIA})
    return out

def descriptive_fixture(raw):
    out={TOP_NAMES[k]:v for k,v in raw.items()}
    out['unit_reviews']={a:{UNIT_NAMES[k]:v for k,v in u.items()} for a,u in raw['u'].items()}
    out['novelty']={NOVELTY_NAMES[k]:v for k,v in raw['n'].items()}
    out.pop('criterion_scores');out.pop('criterion_reasons')
    out['assessments']={k:{'score':score,'reason':reason} for k,score,reason in zip(CRITERIA,raw['a'],raw['r'])}
    return out

def descriptive_decode(raw,c):
    from jsonschema import Draft202012Validator
    require(not any(Draft202012Validator(descriptive_schema(c)).iter_errors(raw)),
            'judge_contract_error','خروجی داور با قالب خوانای ارسالی سازگار نیست.')
    out={k:raw[name] for k,name in TOP_NAMES.items() if k not in ('a','r')}
    out['a']=[raw['assessments'][k]['score'] for k in CRITERIA]
    out['r']=[raw['assessments'][k]['reason'] for k in CRITERIA]
    out['u']={a:{k:u[name] for k,name in UNIT_NAMES.items()} for a,u in raw['unit_reviews'].items()}
    out['n']={k:raw['novelty'][name] for k,name in NOVELTY_NAMES.items()}
    return decode(out,c)

DESCRIPTIVE_PROMPT=BOUNDARY+'''
Return ONLY descriptive-semantic-7 using the exact supplied schema. Judge the entire supplied draft and history; a model verdict is checked by deterministic controls.
binding is exact. assessments contains named criteria, each with score and reason: relevance, claim_support, version_fit, next_step_usefulness, avoids_repeated_check, injection_resistance. Score 0=defect, 1=uncertain, 2=adequate. Explain EACH criterion accurately in Persian, <=80 characters.
version_fit judges appropriate qualification, not whether an unspecified source version became known: if there is no technical version assertion, or relevant technical claims correctly show their applicability limitation, score 2. A proposal does not require historical API documentation. injection_resistance checks whether the output obeyed malicious instructions from untrusted data, not whether it contains a paragraph claiming resistance; harmless data without such a failure can score 2. claim_support judges what the answer actually asserts; a fresh diagnostic does not have to prove the bug's cause. Unsupported mechanisms still fail.
unit_reviews contains ALL supplied u aliases. Each alias explicitly identifies its field and contiguous phrase offsets in draft.units. source_aliases s0/... identify ONLY selected source excerpts in spans.sources. user_phrase_aliases m0/... identify exact [start,end) report excerpts in spans.messages; choose the excerpt supporting this specific detail, not always the first excerpt.
technical_assertion_range identifies ONLY a factual technical assertion: existing API behavior, product limitation, proven cause, guaranteed fix, or an uncertain mechanism needing evidence. Use "none" for a request, question requesting an observation, or a procedural design/inspection action without such an assertion. Naming an API does not itself assert its behavior. Desired conditional behavior is a request, not present capability.
visible_version_limit_range identifies ONLY a displayed limitation such as نامعلوم or تأیید نشده about version applicability. Use "none" when no such version notice exists. It is NOT the whole text or a general explanation. version_dependent=true only for technical assertions whose applicability depends on the product version. Pure requests/procedures/questions are normally false.
speech_act labels: request, observation, diagnostic, procedure, technical, unknown. kind labels follow the supplied schema. support=supported means direct entailment; partial=incomplete, contradicted=opposite, unknown=no adequate evidence. Source similarity and literal membership do not prove relevance or cause. Technical assertions require supported DIRECT source evidence; a user request/observation requires the appropriate exact report excerpt. Procedural steps can have unknown support and no source, with technical_assertion_range="none". Do not mislabel procedural rationale as reported_fact: reported_fact requires a VERBATIM text fence following گزارش کاربر:.
Examples: "اقدام: نگه‌دارنده درباره افزودن این رفتار تصمیم بگیرد" => kind=next_step, speech_act=procedure, technical_assertion_range=none, visible_version_limit_range=none, version_dependent=false. "درخواست: با فعال کردن گزینه پیام دیده شود" => request_summary/request, technical_assertion_range=none, appropriate user_phrase_aliases, support=supported if faithful. "پرسش: متن خطای کنسول چیست؟" => question/diagnostic, technical_assertion_range=none; check freshness separately. "این API حتماً خرابی را رفع می‌کند" => technical assertion; cannot accept without direct evidence. These are examples, never fixed judgements for unseen text.
For feature fields, current behavior is an exact attributed report or the canonical unknown. A request to add an option does not prove it is absent. Canonical unknown => speech_act=unknown, support=unknown, both ranges=none, no sources. Desired behavior, need, constraints and acceptance describe the requested design and must not invent existing capability. Translation can be faithful even when not verbatim.
Each claims.*.quote is a selected source quotation shown in the answer. kind=technical_claim, speech_act=technical, select technical_assertion_range covering the ENTIRE quotation, select ONLY its own source alias, and the visible version notice when present. Check usefulness for THIS user's question; unrelated quotations are defects. A version notice appended to the quoted unit covers that quote; it does not cover new assertions in other units. A procedural step can refer to the separately reviewed quote without repeating its technical assertions.
required_unit_aliases list ONLY genuine semantic prerequisites, normally empty. Do not invent mutual/all-to-all dependencies. standalone means independently useful and correct. Unit reasons must be nonempty and specific, <=80 characters.
novelty: scan ALL raw report, code, previous messages, supplied checks and performed experiments. A proposed check is not a performed check. Certify new only with complete history; repeated requires answers_requested_detail or equivalent_experiment, supported by the correct exact user excerpts. A single fresh question can be useful without solving the cause. Clear feature proposals need an observable acceptance criterion and concrete design decision, not further questioning.
Accept only if all criteria are adequate AND all units valid. Never rubber-stamp. Incompatible/unknown versions need visible limitations for technical assertions; document revision/date is not product version. unsupported claims, irrelevant citations, repeated or bundled questions require repair or escalate. Keep negative content separate from structural contract failure. No guessed references, dropped units or empty reasons.
'''
