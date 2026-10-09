"""Authorized real-product evaluation; no frozen candidates or gold in Agent."""
import argparse,sys,os,json,sqlite3,secrets,math,shutil,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,require,canonical,utcnow,digest
from casepilot.accounting import Budget
from casepilot.model import MetisClient
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.hybrid import HybridRetriever
from casepilot.context_pack import pack_evidence
from casepilot.tokenization import count_tokens
from casepilot.schema_preflight import check_provider_schema
from casepilot.roles import QUALITY_EXTRACTION,RERANK
from casepilot.case_type import selection_schema
from complete_quality_v27 import active_hash
from evaluate_quality_v27_live import credentials
from evaluate_quality_v25_live import sha
from prepare_quality_v28 import RUN,DATA

class QualityBudget(Budget):
    def __init__(self,path,auth,phase):
        self.auth=auth;self.phase=phase
        super().__init__(path,min(5,auth['cost_before']['charged_or_reserved_usd']+auth['hard_cap_usd']))
        with self.db() as db:db.execute('CREATE TABLE IF NOT EXISTS completion_calls(campaign TEXT,id TEXT PRIMARY KEY,phase TEXT)')
    def reserve(self,amount,model,kind='chat'):
        require(math.isfinite(amount) and amount>0,'invalid_price','Invalid reservation')
        require(model==('text-embedding-3-small' if kind=='embedding' else 'gpt-4.1-mini'),'campaign_model_changed','Model outside approval')
        limit=self.auth['phase_limits'][self.phase]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            all_spent=db.execute('SELECT COALESCE(SUM(charged),0) FROM calls').fetchone()[0]
            rows=db.execute('SELECT c.charged,m.phase,c.kind FROM calls c JOIN completion_calls m ON c.id=m.id WHERE m.campaign=?',(self.auth['campaign'],)).fetchall()
            phase=[x for x in rows if x[1]==self.phase]
            require(len(rows)<self.auth['max_requests'] and len(phase)<limit['requests'],'campaign_request_limit','Approved requests exhausted')
            require(kind!='embedding' or sum(x[2]=='embedding' for x in rows)<self.auth['max_query_embeddings'],'query_embedding_limit','Approved query embeddings exhausted')
            require(kind!='embedding' or self.phase=='answers','index_rebuild_not_authorized','Only query embeddings within a product turn are authorized')
            require(all_spent+amount<=self.cap and sum(x[0] for x in rows)+amount<=self.auth['hard_cap_usd'] and sum(x[0] for x in phase)+amount<=limit['usd'],'budget_exhausted','Approved budget exhausted')
            rid=secrets.token_hex(12)
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?)',(rid,utcnow(),model,amount,amount,'reserved',None,None,kind))
            db.execute('INSERT INTO completion_calls VALUES(?,?,?)',(self.auth['campaign'],rid,self.phase))
            return rid

def verify():
    auth=read_json(RUN/'authorization.json')
    require(auth['hard_cap_usd']==1.2 and auth['max_requests']==228 and auth['max_dev_correction_rounds']==2,'invalid_budget','Approval scope changed')
    assert sha(DATA/'manifest.json')==auth['manifest_sha256'] and sha(RUN/'pricing.json')==auth['pricing_sha256']
    manifest=read_json(DATA/'manifest.json')
    for name,h in manifest['files'].items():assert sha(DATA/name)==h
    for v,h in manifest['corpus_hashes'].items():assert sha(ROOT/('data/corpus_'+v+'.json'))==h
    assert sha(ROOT/'data/corpus_v3.sources.json')==manifest['sources_sha256']
    return auth

def client(phase):
    auth=verify();prices={x['model']:x for x in read_json(RUN/'pricing.json')['models']};chat=prices['gpt-4.1-mini'];embed=prices['text-embedding-3-small']
    assert all(x['currency']=='USD' and x['fixedCallIncome']==0 for x in (chat,embed))
    os.environ.update(METIS_MODEL='gpt-4.1-mini',METIS_JUDGE_MODEL='gpt-4.1-mini',METIS_EMBEDDING_MODEL='text-embedding-3-small',
        METIS_BASE_URL='https://api.metisai.ir/openai/v1',CASEPILOT_INPUT_USD_PER_MILLION=str(chat['inputTokenUnitIncome']*1e6),
        CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['outputTokenUnitIncome']*1e6),CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['inputTokenUnitIncome']*1e6),
        CASEPILOT_MAX_OUTPUT_TOKENS='1600',CASEPILOT_BUDGET_USD=str(min(5,auth['cost_before']['charged_or_reserved_usd']+1.2)),
        CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'),CASEPILOT_CHAT_ENCODING='o200k_base',CASEPILOT_CONTEXT_TOKENS='24000',CASEPILOT_INDEX_FORMAT='v2')
    credentials();cl=MetisClient();cl.budget=QualityBudget(cl.budget.path,auth,phase)
    private=ROOT/'runtime/quality_v28';cl.cache=private/'cache';cl.cache.mkdir(parents=True,exist_ok=True);cl.diagnostics=private/'diagnostics'
    cl.audit=[];original=cl._perform_request
    def observed(payload,kind='chat',endpoint='/chat/completions',input_rate=None,output_rate=None):
        if kind=='embedding':require(isinstance(payload.get('input'),list) and len(payload['input'])==1,'index_rebuild_not_authorized','No corpus embedding requests authorized')
        req={'kind':kind,'endpoint':endpoint,'payload':payload,'payload_hash':digest(payload),'input_tokens':count_tokens(canonical(payload),encoding='o200k_base')}
        cl.audit.append(req)
        try:
            req['raw_reply']=original(payload,kind,endpoint,input_rate,output_rate);return req['raw_reply']
        except Exception as exc:req['failure']=getattr(exc,'code',type(exc).__name__);raise
        finally:req['usage']=dict(cl.last_usage)
    cl._perform_request=observed
    return cl

class ObservedHybrid(HybridRetriever):
    """Record the actual query/results without modifying normal retrieval."""
    def search(self,query,**kwargs):
        self.observed_query=query;self.observed_kwargs=kwargs
        self.observed_candidates=super().search(query,**kwargs)
        return self.observed_candidates

def snapshot(label):
    target=RUN/'code_versions'/label
    if (target/'manifest.json').exists():
        m=read_json(target/'manifest.json');assert m['active_hash']==active_hash();return m['active_hash']
    files={}
    for folder in ('src','schemas','policies','scripts','tests'):
        for p in (ROOT/folder).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts:continue
            rel=p.relative_to(ROOT);q=target/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);files[str(rel)]=sha(p)
    write_json(target/'manifest.json',{'active_hash':active_hash(),'files':files,'provider_requests':0});return active_hash()

def preflight():
    verify();cl=client('answers');stats={}
    for v in ('v2','v3'):
        h=ObservedHybrid(cl,ROOT/('data/corpus_'+v+'.json'));vectors=h.load_vectors()
        assert len(vectors)==len(h.chunks) and all(len(x)==1536 and all(math.isfinite(y) for y in x) for x in vectors)
        stats[v]={'rows':len(vectors),'namespace':h.index_namespace,'cache_only':True,'model_identity':h.cache.embedder.identity}
    assert not cl.audit,'Preflight must not create embeddings'
    check_provider_schema(QUALITY_EXTRACTION);check_provider_schema(RERANK)
    for case in read_json(DATA/'dev_inputs.json')+read_json(DATA/'holdout_inputs.json'):
        s={'id':case['id'],'revision':1,'facts':case['initial_facts'],'messages':[{'role':'user','text':case['initial_message']}]}
        check_provider_schema(selection_schema(s,{}))
    write_json(RUN/'preflight.json',{'index_caches':stats,'active_hash':active_hash(),'provider_requests':0,'gold_outside_product_packets':True})
    print('Existing real vectors and six input schemas verified offline; no provider calls.')

def run_split(split,round_number,hypothesis=None):
    require(round_number in (0,1,2),'invalid_round','Only two development correction rounds authorized')
    if split=='holdout':
        chosen=read_json(RUN/'selection.json');assert chosen['active_hash']==active_hash()
        require(round_number==0,'holdout_not_fresh','No holdout tuning/repeats authorized')
    elif round_number:
        require(bool(hypothesis),'missing_hypothesis','A corrective round needs a recorded effective-change hypothesis')
        previous=read_json(RUN/'code_versions'/('dev_r'+str(round_number-1))/'manifest.json')
        require(previous['active_hash']!=active_hash(),'blind_content_retry','No content retry without effective code change')
        write_json(RUN/('round_'+str(round_number)+'_hypothesis.json'),{'hypothesis':hypothesis,'previous_hash':previous['active_hash'],'active_hash':active_hash()})
    checked_round=chosen['development_round'] if split=='holdout' else round_number
    tests=read_json(RUN/('offline_round'+str(checked_round)+'.json'))
    require(tests['passed'] and tests['active_code_hash']==active_hash(),'offline_preflight_required','Run relevant offline checks for this exact code first')
    pf=read_json(RUN/'preflight.json');assert pf['active_hash']==active_hash()
    label=split+'_r'+str(round_number);code=snapshot(label);cl=client('answers')
    for case in read_json(DATA/(split+'_inputs.json')):
        for variant,index in (('A','v2'),('B','v3')):
            stem=label+'_'+case['id']+'_'+variant;path=RUN/'turns'/(stem+'.json')
            if path.exists():continue
            require(not (RUN/'started'/(stem+'.json')).exists(),'interrupted_turn','Interrupted marker retained; retry only via bounded connection retry')
            attempts=[p for p in (RUN/'started').glob('*.json')] if (RUN/'started').exists() else []
            require(len(attempts)<28,'campaign_turn_limit','Approved turn slots exhausted')
            write_json(RUN/'started'/(stem+'.json'),{'code_hash':code,'input_hash':digest(case),'status':'started'})
            run_one(cl,case,variant,index,stem,code,split,round_number)
    accounting()

def run_one(cl,case,variant,index,stem,code,split,round_number,retry_of=None):
    usage_start=len(cl.usage_history);audit_start=len(cl.audit);out=None;error=None;start=time.perf_counter()
    store=Store(ROOT/('runtime/quality_v28/'+stem+'.sqlite3'));hybrid=ObservedHybrid(cl,ROOT/('data/corpus_'+index+'.json'))
    agent=Agent(store,client=cl,hybrid=hybrid,components={'parent_context':False,'context_tokens':3000,'rewrite':False})
    try:
        # Equal metadata for paired reports; no facts, queries, vectors or
        # candidates are overridden. Every product role/tool runs normally.
        with patch('casepilot.store.utcnow',return_value='2026-10-10T00:00:00+00:00'):
            out=agent.turn('V28_'+case['id'],case['initial_message'],'product-eval',case['initial_facts'],case['initial_checks'])
    except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
    context=[];packing=None;state=None
    if out:
        state=store.get('V28_'+case['id']);selection=next((x for x in out['pipeline'] if x['stage']=='rerank'),None)
        candidates=getattr(hybrid,'observed_candidates',[])
        rows=[r for cid in (selection or {}).get('ids',[]) for r in candidates if r['id']==cid]
        context,packing=pack_evidence(rows,max_tokens=3000,expand_parent=False)
        observed=next((x for x in out['pipeline'] if x['stage']=='context_pack'),None)
        if observed:assert observed['ids']==[x['id'] for x in context] and observed['used_tokens']==packing['used_tokens']
    record={'case_id':case['id'],'split':split,'round':round_number,'variant':variant,'index':index,'code_hash':code,
        'input_hash':digest(case),'output':out,'failure':error,'actual_query':getattr(hybrid,'observed_query',None),
        'retrieval_kwargs':getattr(hybrid,'observed_kwargs',None),'retrieval_trace':hybrid.last_trace,
        'initial_candidates':getattr(hybrid,'observed_candidates',[]),'actual_context':context,'packing':packing,'state':state,
        'requests':cl.audit[audit_start:],'usage':cl.usage_history[usage_start:],'elapsed_seconds':time.perf_counter()-start,
        'retry_of':retry_of,'human_review':None,'independent_review':None}
    write_json(RUN/'turns'/(stem+'.json'),record);write_json(RUN/'traces'/(stem+'.json'),store.traces())
    print(stem+': '+str(error or (out or {}).get('validation_error') or 'reviewed'),flush=True)

def retry(stem):
    original=read_json(RUN/'turns'/(stem+'.json'));error=original['failure'] or (original['output'] or {}).get('validation_error')
    require(error in ('provider_connection_error','provider_timeout'),'non_connection_retry','Only connection/timeout retry authorized')
    retries=read_json(RUN/'connection_retries.json') if (RUN/'connection_retries.json').exists() else []
    require(len(retries)<4 and stem not in [x['original'] for x in retries],'connection_retry_limit','One retry per failed node; four total')
    require(original['code_hash']==active_hash(),'retry_code_changed','Code changed; use a development correction round instead')
    case=next(x for x in read_json(DATA/(original['split']+'_inputs.json')) if x['id']==original['case_id'])
    target=stem+'_connection_retry';retries.append({'original':stem,'retry':target});write_json(RUN/'connection_retries.json',retries)
    write_json(RUN/'started'/(target+'.json'),{'code_hash':active_hash(),'input_hash':digest(case),'status':'connection_retry'})
    run_one(client('answers'),case,original['variant'],original['index'],target,active_hash(),original['split'],original['round'],stem);accounting()

def select(round_number,reason):
    require(bool(reason),'missing_selection_reason','Select from recorded development evidence')
    assert read_json(RUN/'code_versions'/('dev_r'+str(round_number))/'manifest.json')['active_hash']==active_hash()
    if (RUN/'selection.json').exists():raise SystemExit('Selection already frozen; cannot tune after holdout.')
    paths=list((RUN/'turns').glob('dev_r'+str(round_number)+'_*.json'))
    require(len(paths)>=6,'incomplete_development','Complete all independent development nodes before selection')
    write_json(RUN/'selection.json',{'development_round':round_number,'active_hash':active_hash(),'reason':reason,
        'dev_artifacts':{p.name:sha(p) for p in paths},'holdout_manifest_sha256':sha(DATA/'manifest.json'),
        'default_changed':False,'selected_for_evaluation_only':True})
    print('Code selected from development and frozen before holdout; default remains v2.')

def probe(stem,reason):
    """One authorized judge-only diagnosis on an unchanged stored draft."""
    from copy import deepcopy
    from casepilot.compact_review import packet,descriptive_schema,descriptive_decode,DESCRIPTIVE_PROMPT
    from casepilot.review_contract import draft_units
    from casepilot.semantics import prepare_feature,checked_semantic_review
    from casepilot.roles import deterministic_findings
    require(bool(reason),'missing_hypothesis','A stored-draft probe needs a diagnostic hypothesis')
    rows=list((RUN/'probes').glob('*.json')) if (RUN/'probes').exists() else []
    require(len(rows)<4,'probe_limit','Only four stored-draft probes authorized')
    original=read_json(RUN/'turns'/(stem+'.json'))
    require(original['split']=='dev','holdout_probe_not_authorized','No tuning probes on holdout')
    first=next(x for x in original['requests'] if x['kind']=='judge')
    jp=json.loads(first['payload']['messages'][1]['content']);env=jp['draft']
    a=prepare_feature(deepcopy(next(x['raw_reply'] for x in original['requests'] if x['kind']=='chat')),original['state'])
    a['claims']=jp['citations'];state=original['state'];evidence=original['actual_context']
    assert draft_units(a,env['case_id'],env['case_revision'],env['generation'],include_quotes=True)==env
    c,public=packet(env,jp['spans']);jp['compact_contract']=public
    wire=descriptive_schema(c);check_provider_schema(wire)
    cl=client('probes');before=cl.budget.report()['charged_or_reserved_usd']
    cl.turn_scope={'calls_before':cl.calls,'cost_before':before,'max_calls':1,'cap_usd':.02,'deadline':time.monotonic()+90}
    n=len(rows)+1;target=RUN/'probes'/('probe_'+str(n)+'.json')
    # Persist before request so an interruption cannot make the probe free/reusable.
    write_json(target,{'status':'started','original':stem,'hypothesis':reason,'code_hash':active_hash()})
    raw=None;checked=None;error=None
    try:
        raw=cl.structured('judge',DESCRIPTIVE_PROMPT,jp,wire,2400)
        checked=checked_semantic_review(descriptive_decode(raw,c),a,evidence,state,env,deterministic_findings(a,evidence,state))
    except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
    write_json(target,{'status':'finished','original':stem,'hypothesis':reason,'code_hash':active_hash(),
        'draft_hash':digest(env),'original_draft_hash':digest(json.loads(first['payload']['messages'][1]['content'])['draft']),
        'raw_review':raw,'checked':checked,'failure':error,'requests':cl.audit,'usage':cl.usage_history,
        'human_review':None,'independent_review':None})
    print('Stored-draft probe: '+str(error or checked['verdict']));accounting()

def accounting():
    auth=verify();budget=QualityBudget(ROOT/'runtime/team_budget.sqlite3',auth,'answers')
    with budget.db() as db:
        rows=db.execute('SELECT c.charged,c.status,m.phase,c.kind FROM calls c JOIN completion_calls m ON c.id=m.id WHERE m.campaign=?',(auth['campaign'],)).fetchall()
    confirmed=sum(x[0] for x in rows if x[1]=='confirmed');unknown=sum(x[0] for x in rows if x[1]!='confirmed')
    report={'requests':len(rows),'query_embedding_requests':sum(x[3]=='embedding' for x in rows),'confirmed_usd':confirmed,
        'unknown_reserved_usd':unknown,'charged_or_reserved_usd':confirmed+unknown,'hard_cap_usd':1.2,
        'index_rebuild_requests':0,'historical_before':auth['cost_before'],
        'by_kind':{k:{'requests':sum(x[3]==k for x in rows),'confirmed_usd':sum(x[0] for x in rows if x[3]==k and x[1]=='confirmed'),
            'unknown_reserved_usd':sum(x[0] for x in rows if x[3]==k and x[1]!='confirmed')} for k in sorted({x[3] for x in rows})}}
    write_json(RUN/'accounting.json',report);print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['preflight','dev','holdout','retry','select','probe','accounting']);p.add_argument('--round',type=int,default=0);p.add_argument('--hypothesis');p.add_argument('--stem');p.add_argument('--reason');a=p.parse_args()
    if a.phase=='preflight':preflight()
    elif a.phase=='dev':run_split('dev',a.round,a.hypothesis)
    elif a.phase=='holdout':run_split('holdout',0)
    elif a.phase=='retry':retry(a.stem)
    elif a.phase=='select':select(a.round,a.reason)
    elif a.phase=='probe':probe(a.stem,a.reason)
    else:accounting()
