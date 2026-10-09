"""Versioned experiment ledger; equivalence uses actions and execution dimensions."""
import re
from .common import digest, require

MEMORY_VERSION=3
ALIASES={
    'disable_rerun':('disable rerun','turn off rerun','without rerun','rerun disabled','بدون بازاجرا','خاموش کردن بازاجرا'),
    'remove_uploaded_file':('remove uploaded file','clear uploader','delete file from widget','پاک کردن فایل از ویجت'),
    'minimal_app':('minimal app','simplified app','simpler code','نمونه ساده','کد ساده تر'),
    'close_browser_tab':('close tab','close browser tab','بستن تب'),
    'pickle_outside_streamlit':('pickle outside streamlit','serialize outside app','پیکل بیرون برنامه')}

def normalize(value):
    value=value.casefold().replace('ي','ی').replace('ك','ک').replace('\u200c',' ')
    return ' '.join(re.sub(r'[^\w.=+-]+',' ',value).split())

def action_key(value):
    key=normalize(value).replace(' ','_')
    for canonical,aliases in ALIASES.items():
        if key==canonical or normalize(value) in map(normalize,aliases): return canonical
    return key

def condition_map(conditions):
    return {normalize(c['dimension']).replace(' ','_'):normalize(c['value']) for c in conditions}

def checked_events(events,message,existing):
    require(isinstance(events,list) and len(events)<=8,'invalid_experiment','فهرست آزمایش معتبر نیست.')
    by_id={e['id']:e for e in existing}; checked=[]
    for row in events:
        require(isinstance(row,dict) and set(row)=={'action','conditions','status','result','quote','supersedes'},'invalid_experiment','ساختار آزمایش معتبر نیست.')
        require(all(isinstance(row[k],str) and len(row[k])<=1000 for k in ('action','result','quote','supersedes')) and row['action'].strip(),'invalid_experiment','متن آزمایش معتبر نیست.')
        require(row['status'] in ('proposed','not_performed','performed_unknown','succeeded','failed','correction'),'invalid_experiment','وضعیت آزمایش معتبر نیست.')
        require(3<=len(row['quote'])<=1000 and row['quote'] in message,'invalid_experiment','منشأ آزمایش باید عبارت دقیق پیام جاری باشد.')
        require(not row['result'] or row['result'] in row['quote'],'invalid_experiment','نتیجه باید عبارت واقعی همان شاهد باشد؛ نتیجهٔ غایب جعل نمی‌شود.')
        require(row['status'] not in ('succeeded','failed','correction') or bool(row['result'].strip()),'invalid_experiment','نتیجهٔ موفق یا ناموفق نیازمند مشاهدهٔ صریح است.')
        require(isinstance(row['conditions'],list) and len(row['conditions'])<=10,'invalid_experiment','شرایط آزمایش معتبر نیست.')
        for c in row['conditions']:
            require(isinstance(c,dict) and set(c)=={'dimension','value','quote'} and all(isinstance(v,str) and 0<len(v)<=500 for v in c.values()),'invalid_experiment','شرط آزمایش معتبر نیست.')
            require(c['quote'] in message and c['value'].casefold() in c['quote'].casefold(),'invalid_experiment','مقدار شرط در شاهد کاربر نیست.')
        require(len(condition_map(row['conditions']))==len(row['conditions']),'invalid_experiment','شرط تکراری مجاز نیست.')
        if row['supersedes']:
            require(row['supersedes'] in by_id and action_key(row['action'])==by_id[row['supersedes']]['action_key'],'invalid_experiment','اصلاح فقط به آزمایش همان پرونده و همان اقدام مربوط می‌شود.')
        elif row['status']=='correction': require(False,'invalid_experiment','اصلاح باید به آزمایش قبلی اشاره کند.')
        checked.append(row)
    return checked

def migrate(state):
    """Read-compatible lazy migration, persists in the next update transaction."""
    if state.get('memory_version')==MEMORY_VERSION: return state
    state.setdefault('experiments',[])
    for i,text in enumerate(state.get('checks',[]) if state.get('memory_version',0)<2 else []):
        state['experiments'].append({'id':'legacy_'+digest({'case':state['id'],'i':i,'text':text})[:20],
            'action':text,'action_key':'legacy_unclassified','conditions':[], 'status':'performed_unknown',
            'result':'','quote':text,'supersedes':'','sequence':i+1,'case_revision':0,
            'provenance':{'kind':'legacy_check','message_index':None,'at':None},'equivalence_known':False})
    state['memory_version']=MEMORY_VERSION
    state.setdefault('fact_provenance',{})
    state.setdefault('version_roles',[])
    for index,m in enumerate(state.get('messages',[])):
        for row in version_roles(m['text']):
            entry=dict(row,message_index=index,kind='migrated_user_span')
            if entry not in state['version_roles']: state['version_roles'].append(entry)
        recovered=observed_comparisons(m['text'])
        recovered=[e for e in recovered if not any(x['quote']==e['quote'] and x['status']==e['status'] for x in state['experiments'])]
        view=dict(state,messages=state['messages'][:index+1])
        append_events(view,recovered,m.get('at'),'migrated_user_span')
    for key in ('streamlit_version','python_version'):
        current=[r for r in state['version_roles'] if r['key']==key and r['role']=='current']
        if not current: continue
        last=current[-1]; provenance=state['fact_provenance'].get(key,{})
        # Recover only a lost/ambiguous value, never overwrite a later correction.
        if state.get('facts',{}).get(key) is None and (provenance.get('message_index') or 0)<=last['message_index']:
            state.setdefault('facts',{})[key]=last['value']
            state['fact_provenance'][key]=dict(last,kind='migration_recovery')
    return state


def version_roles(message):
    """Narrow explicit-label parser; no maximum-version/current heuristic.

    Unlabelled mentions stay unknown. Parenthetical history is kept separately.
    Ranges are not singleton current environments. Model extraction still handles
    more varied prose; these verified patterns cover observed development failures.
    """
    from .evidence import VERSION
    output=[]
    names={'streamlit':'streamlit_version','python':'python_version'}
    for name,key in names.items():
        pattern=r'(?im)^\s*(?:[-*]\s*)?(?:(current|previous|compared|proposed|fixed|فعلی|قبلی|مقایسه|پیشنهادی|رفع)\s+)?'+name+r'(?:\s+version)?\s*[:=]\s*([^\n]+)'
        for m in re.finditer(pattern,message):
            label=(m[1] or 'current').lower(); line=m[2].replace('`','')
            role={'فعلی':'current','قبلی':'previous','مقایسه':'compared','پیشنهادی':'proposed','رفع':'fixed'}.get(label,label)
            versions=list(re.finditer(VERSION+r'(?![\w.+-])',line))
            for i,v in enumerate(versions):
                before=line[:v.start()]
                historical=bool(re.search(r'(?i)since|previous|before|قبلی|از نسخه',before))
                range_value=bool(re.search(r'\d\s*[-–]\s*\d',line)) or (len(versions)>1 and not re.search(r'(?i)since|previous|before|قبلی|از نسخه',line))
                output.append({'key':key,'value':v[0],'role':'previous' if historical else ('unknown' if range_value or i>0 else role),'quote':m[0].strip()})
        # Explicit later correction can lower the version number.
        pat=r'(?i)(?:correction|actually|اصلاح|در واقع)[^\n]{0,50}?'+name+r'(?: version)?\s*[:=]?\s*('+VERSION+r')(?![\w.+-])'
        for m in re.finditer(pat,message): output.append({'key':key,'value':m[1],'role':'current','quote':m[0],'correction':True})
    for event in observed_comparisons(message):
        output.append({'key':'streamlit_version','value':event['conditions'][0]['value'],'role':'compared','quote':event['quote'],'outcome':event['status']})
    return output


def observed_comparisons(message):
    """Recognize only explicit outcome followed by an executed version command."""
    from .evidence import VERSION
    events=[]
    pat=r'(?im)^(worked when ran with|stopped working at)\s*\n```[^\n]*\n([^`]+)```'
    for m in re.finditer(pat,message):
        command=m[2].strip(); v=re.search(r'streamlit==('+VERSION+r')(?![\w.+-])',command)
        script=re.search(r'streamlit run\s+(\S+)',command)
        if not v or not script: continue
        events.append({'action':'run '+script[1], 'conditions':[
            {'dimension':'streamlit_version','value':v[1],'quote':command},
            {'dimension':'app_variant','value':script[1],'quote':command}],
            'status':'succeeded' if m[1].lower().startswith('worked') else 'failed',
            'result':m[1], 'quote':m[0], 'supersedes':''})
    return events

def append_events(state,events,at,kind='user_report'):
    for row in events:
        if any(e['case_revision']==state['revision'] and e['provenance']['kind']==kind and all(e[k]==v for k,v in row.items()) for e in state['experiments']): continue
        sequence=len(state['experiments'])+1
        event=dict(row,id='exp_'+digest({'case':state['id'],'revision':state['revision'],'sequence':sequence,'event':row})[:20],
                   action_key=action_key(row['action']),sequence=sequence,case_revision=state['revision'],
                   provenance={'kind':kind,'message_index':len(state['messages'])-1,'at':at},equivalence_known=True)
        state['experiments'].append(event)

def active_experiments(state):
    events=state.get('experiments',[]); superseded={e['supersedes'] for e in events if e.get('supersedes')}
    return [e for e in events if e['id'] not in superseded]

def diagnostic_findings(answer,state):
    diagnostic=answer.get('diagnostic')
    if not diagnostic or answer['decision']!='ask': return []
    findings=[]
    def add(reason,criterion='avoids_repeated_check'): findings.append({'criterion':criterion,'reason':reason})
    missing=diagnostic['missing_fact']
    if missing and state.get('facts',{}).get(missing) not in (None,''):
        add('پرسش: مقدار این مشخصه قبلاً معلوم است.')
    action=action_key(diagnostic['action'])
    if not action: return findings
    conditions=condition_map(diagnostic['conditions'])
    performed=[e for e in active_experiments(state) if e.get('equivalence_known') and e['status'] in ('performed_unknown','succeeded','failed','correction') and e['action_key']==action]
    for event in performed:
        old=condition_map(event['conditions'])
        # Explicit differing dimensions demonstrate a new experiment. Missing
        # dimensions do not establish a meaningful change in execution conditions.
        changed={k for k in old.keys() & conditions.keys() if old[k]!=conditions[k]}
        if not changed:
            add('آزمایش: اقدام با شرایط معادل یا فاقد تغییر صریح قبلاً انجام شده است؛ '+event['id'])
        elif diagnostic['repeat_of']==event['id']:
            key=normalize(diagnostic['changed_condition']).replace(' ','_')
            if key not in changed or not diagnostic['repeat_reason'].strip() or diagnostic['repeat_reason'] not in answer['next_step']:
                add('تکرار: تغییر شرط و دلیل ارزش آن باید در قدم بعدی دیده شود.')
        else:
            add('تکرار: آزمایش قبلی و شرط تغییرکرده باید صریح معرفی شوند.')
    if diagnostic['repeat_of'] and diagnostic['repeat_of'] not in {e['id'] for e in performed}:
        add('تکرار: شناسهٔ آزمایش قبلی معتبر نیست.')
    return findings

def validate_diagnostic(d):
    if d is None: return
    require(isinstance(d,dict) and set(d)=={'action','conditions','repeat_of','changed_condition','repeat_reason','missing_fact'},'invalid_diagnostic','قرارداد قدم تشخیصی معتبر نیست.')
    require(all(isinstance(d[k],str) and len(d[k])<=700 for k in d if k!='conditions'),'invalid_diagnostic','متن قدم تشخیصی معتبر نیست.')
    require(isinstance(d['conditions'],list) and len(d['conditions'])<=10 and all(isinstance(c,dict) and set(c)=={'dimension','value'} and all(isinstance(v,str) and 0<len(v)<=500 for v in c.values()) for c in d['conditions']),'invalid_diagnostic','شرایط قدم تشخیصی معتبر نیست.')
    require(len(condition_map(d['conditions']))==len(d['conditions']),'invalid_diagnostic','شرط تکراری معتبر نیست.')
