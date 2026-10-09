"""Resumable, budget-guarded V27 completion campaign. No implicit authorization.

Commands perform one explicit phase; independent cases continue after failures.
All evaluation labels stay evaluator-side, outside Agent/role packets.
"""
import argparse,json,os,sys,time,sqlite3,secrets,math,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest,canonical,require,utcnow
from casepilot.accounting import Budget
from casepilot.model import MetisClient
from casepilot.hybrid import HybridRetriever,embedding_text
from casepilot.embeddings import normalize,unit
from casepilot.context_pack import pack_evidence
from casepilot.evaluation_completion import candidate_key,retrieval_scores,classify_failure
from evaluate_quality_v27_live import credentials
from evaluate_quality_v25_live import ledger,sha
from prepare_quality_v27_completion import RUN,DATA


def active_hash():
    return digest({str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src').rglob('*.py'))})


class CampaignBudget(Budget):
    """Atomic global + campaign + phase request and cost reservations.

    Shares the existing ledger so unknown reservations survive process failure.
    The campaign mapping is inserted in the same transaction as its debit.
    Counts are actual provider requests, never cached/offline invocations.
    """
    def __init__(self,path,auth,phase):
        self.auth=auth;self.phase=phase
        super().__init__(path,min(5,auth['cost_before']['charged_or_reserved_usd']+auth['hard_cap_usd']))
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS completion_calls(campaign TEXT,id TEXT PRIMARY KEY,phase TEXT)')

    def reserve(self,amount,model,kind='chat'):
        require(amount>0,'invalid_price','Invalid reservation.')
        expected='text-embedding-3-small' if kind=='embedding' else 'gpt-4.1-mini'
        require(model==expected,'campaign_model_changed','Model outside approval.')
        limit=self.auth['phase_limits'][self.phase]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            all_spent=db.execute('SELECT COALESCE(SUM(charged),0) FROM calls').fetchone()[0]
            rows=db.execute('SELECT c.charged,m.phase FROM calls c JOIN completion_calls m ON c.id=m.id WHERE m.campaign=?',(self.auth['campaign'],)).fetchall()
            phase_rows=[x for x in rows if x[1]==self.phase]
            require(len(rows)<self.auth['max_requests'] and len(phase_rows)<limit['requests'],
                    'campaign_request_limit','Approved request limit reached.')
            require(all_spent+amount<=self.cap and sum(x[0] for x in rows)+amount<=self.auth['hard_cap_usd']
                    and sum(x[0] for x in phase_rows)+amount<=limit['usd'],
                    'budget_exhausted','Approved campaign/phase budget exhausted.')
            cid=secrets.token_hex(12)
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?)',(cid,utcnow(),model,amount,amount,'reserved',None,None,kind))
            db.execute('INSERT INTO completion_calls VALUES(?,?,?)',(self.auth['campaign'],cid,self.phase))
            return cid


def authorize():
    """Records the exact approval received in this conversation, not a CLI grant."""
    path=RUN/'authorization.json'
    if path.exists():return read_json(path)
    before=ledger()
    require(before['charged_or_reserved_usd']+1.10<=5,'invalid_budget','Course aggregate limit insufficient.')
    auth={'campaign':'completion_20261010','approval':'Human explicitly approved this exact scope and $1.10 in this chat on 2026-10-10',
          'hard_cap_usd':1.10,'max_requests':343,'max_samples':24,'max_answer_turns':24,
          'max_development_repeat_turns':6,'max_contract_attempts':3,
          'phase_limits':{'judge':{'requests':3,'usd':.06},'index':{'requests':100,'usd':.05},
                          'retrieval':{'requests':48,'usd':.03},'answers':{'requests':192,'usd':.96}},
          'cost_before':{k:before[k] for k in ('requests','confirmed_usd','uncertain_reserved_usd','charged_or_reserved_usd')},
          'pricing_sha256':sha(RUN/'pricing.json'),'protocol_sha256':sha(DATA/'protocol.json'),
          'manifest_sha256':sha(DATA/'manifest.json'),'corpus_hashes':read_json(RUN/'preflight.json')['corpus_hashes']}
    write_json(path,auth);return auth


def verify():
    auth=read_json(RUN/'authorization.json')
    require(auth['hard_cap_usd']==1.10 and auth['max_requests']==343,'invalid_budget','Approval changed.')
    assert sha(DATA/'manifest.json')==auth['manifest_sha256'] and sha(DATA/'protocol.json')==auth['protocol_sha256']
    for name,h in read_json(DATA/'manifest.json')['files'].items():assert sha(DATA/name)==h
    for v,h in auth['corpus_hashes'].items():assert sha(ROOT/('data/corpus_'+v+'.json'))==h
    assert sha(RUN/'pricing.json')==auth['pricing_sha256']
    return auth


def client(phase):
    auth=verify();prices={p['model']:p for p in read_json(RUN/'pricing.json')['models']}
    a=prices['gpt-4.1-mini'];e=prices['text-embedding-3-small']
    assert all(p['currency']=='USD' and p['fixedCallIncome']==0 for p in (a,e))
    os.environ.update(METIS_MODEL=a['model'],METIS_JUDGE_MODEL=a['model'],METIS_EMBEDDING_MODEL=e['model'],
        METIS_BASE_URL='https://api.metisai.ir/openai/v1',CASEPILOT_INPUT_USD_PER_MILLION=str(a['inputTokenUnitIncome']*1e6),
        CASEPILOT_OUTPUT_USD_PER_MILLION=str(a['outputTokenUnitIncome']*1e6),
        CASEPILOT_EMBEDDING_USD_PER_MILLION=str(e['inputTokenUnitIncome']*1e6),CASEPILOT_MAX_OUTPUT_TOKENS='1600',
        CASEPILOT_BUDGET_USD=str(min(5,auth['cost_before']['charged_or_reserved_usd']+1.10)),
        CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'),CASEPILOT_CHAT_ENCODING='o200k_base',
        CASEPILOT_INDEX_FORMAT='v2')
    credentials();c=MetisClient();c.budget=CampaignBudget(c.budget.path,auth,phase)
    private=ROOT/'runtime/quality_v27/completion_20261010'
    c.cache=private/'cache';c.cache.mkdir(parents=True,exist_ok=True);c.diagnostics=private/'diagnostics'
    return c


def code_snapshot(label):
    target=RUN/'code_versions'/label
    if target.exists(): return active_hash()
    import shutil
    for parent in ('src','schemas','policies','scripts'):
        for p in (ROOT/parent).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.json','.md'):
                q=target/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
    write_json(target/'manifest.json',{'active_hash':active_hash(),
        'files':{str(p.relative_to(target)):sha(p) for p in target.rglob('*') if p.is_file()}})
    return active_hash()


def judge(attempt=1,hypothesis=None):
    from casepilot.compact_review import packet,schema,PROMPT,decode
    from casepilot.review_contract import review_spans
    from casepilot.semantics import checked_semantic_review
    from casepilot.roles import deterministic_findings
    from casepilot.schema_preflight import check_provider_schema
    from casepilot.tokenization import count_tokens
    assert 1<=attempt<=3
    target=RUN/'judge'/('attempt_'+str(attempt)+'.json')
    if target.exists():print('Judge attempt already recorded.');return
    if attempt>1:
        prev=read_json(RUN/'judge'/('attempt_'+str(attempt-1)+'.json'))
        assert prev['failure'] and (prev['code_hash']!=active_hash() or hypothesis),'No blind retry.'
    item=read_json(RUN/'judge_input.json');a=item['answer'];s=item['state'];ev=item['evidence'];env=item['envelope']
    spans=review_spans(s,ev,a['claims']);c,public=packet(env,spans)
    jp={'facts':s['facts'],'experiments':s['experiments'],'completed_checks':s.get('checks',[]),'history_complete':True,
        'decision':a['decision'],'citations':a['claims'],'spans':spans,'draft':env,'compact_contract':public}
    wire=schema(c);check_provider_schema(wire)
    payload={'model':'gpt-4.1-mini','messages':[{'role':'system','content':PROMPT},{'role':'user','content':canonical(jp)}],
        'max_tokens':1600,'response_format':{'type':'json_schema','json_schema':{'name':'casepilot_judge','strict':True,'schema':wire}}}
    assert len(canonical(payload).encode())<=45000 and count_tokens(canonical(payload),encoding='o200k_base')+1728<=24000
    raw=None;checked=None;error=None;decoded=False
    code=code_snapshot('judge_'+str(attempt));cl=client('judge');before=cl.budget.report()['charged_or_reserved_usd']
    cl.turn_scope={'calls_before':cl.calls,'cost_before':before,'max_calls':1,'cap_usd':.02,'deadline':time.monotonic()+90}
    write_json(RUN/'judge'/('started_'+str(attempt)+'.json'),{'at':utcnow(),'hypothesis':hypothesis,'code_hash':code})
    try:
        raw=cl.structured('judge',PROMPT,jp,wire,1600)
        result=decode(raw,c);decoded=True
        checked=checked_semantic_review(result,a,ev,s,env,deterministic_findings(a,ev,s))
    except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
    finally:
        write_json(target,{'attempt':attempt,'input_hash':digest(item),'request_hash':digest(payload),'code_hash':code,
            'hypothesis':hypothesis,'raw_review':raw,'checked':checked,'structural_valid':decoded,
            'contract_valid':checked is not None,'content_verdict':checked.get('verdict') if checked else None,
            'failure':error,'failure_category':classify_failure(error,decoded),'usage':cl.usage_history,
            'repro':{'prompt':PROMPT,'packet':jp,'schema':wire}})
        cl.key='';os.environ.pop('METIS_API_KEY',None)
    print(json.dumps({'attempt':attempt,'contract_valid':checked is not None,'content_verdict':checked.get('verdict') if checked else None,'failure':error}))


def embeddings():
    """Each successful batch is committed immediately by EmbeddingCache."""
    cl=client('index');h=HybridRetriever(cl,path=ROOT/'data/corpus_v3.json')
    texts=[embedding_text(r) for r in h.chunks];error=None;start=len(cl.usage_history)
    attempts=list((RUN/'embedding').glob('attempt_*.json')) if (RUN/'embedding').exists() else []
    assert len(attempts)<3,'At most two corrective resumes, within 100 requests.'
    try:
        vectors=h.cache.get_many(texts,allow_create=True)
        assert len(vectors)==len(h.chunks) and len({len(v) for v in vectors})==1 and len(vectors[0])==1536
        # Check every actual cache address against this live model + namespace +
        # normalized embedding text, not merely a total sqlite row count.
        with h.cache.db() as db:
            entries={k:json.loads(v) for k,v in db.execute('SELECT key,vector FROM vectors')}
        binding=[{'id':r['id'],'embedding_text_hash':digest(normalize(t)),'cache_key':h.cache.key(t),
                  'vector_hash':digest(unit(entries[h.cache.key(t)]))} for r,t in zip(h.chunks,texts)]
        assert all(math.isfinite(v) for vec in vectors for v in vec)
        write_json(RUN/'embedding'/'coverage.json',{'complete':True,'rows':len(vectors),'unique_cache_keys':len({b['cache_key'] for b in binding}),
            'dimensions':1536,'identity':h.cache.embedder.identity,'namespace':h.index_namespace,
            'corpus_hash':digest(h.chunks),'bindings':binding,'build_does_not_activate_default':True})
    except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
    finally:
        write_json(RUN/'embedding'/('attempt_'+str(len(attempts)+1)+'.json'),{'at':utcnow(),'failure':error,
            'usage':cl.usage_history[start:],'complete':error is None,'namespace':h.index_namespace})
        cl.key='';os.environ.pop('METIS_API_KEY',None)
    print(json.dumps({'embedding_complete':error is None,'failure':error,'requests':len(cl.usage_history)-start}))


def load_cases():
    return sum([read_json(DATA/(s+'_inputs.json')) for s in ('dev','holdout')],[])


def retrieve():
    cl=client('retrieval');hs={v:HybridRetriever(cl,path=ROOT/('data/corpus_'+v+'.json')) for v in ('v2','v3')}
    readiness={}
    for v,h in hs.items():
        try:h.load_vectors();readiness[v]=True
        except Exception as exc:readiness[v]=getattr(exc,'code',type(exc).__name__)
    write_json(RUN/'retrieval_readiness.json',readiness)
    for case in load_cases():
        target=RUN/'retrieval'/(case['id']+'.json')
        if target.exists():continue
        query=case['initial_message'];version=case['initial_facts'].get('streamlit_version');start=len(cl.usage_history)
        result={'id':case['id'],'split':case['split'],'query':query,'query_hash':digest(query),'version':version,
                'variants':{},'code_hash':active_hash()}
        try:
            # Same real model and exact vector for both index formats; B/C use
            # one persisted candidate list, not two independent searches.
            qvector=hs['v2'].cache.get_many([query])[0];result['query_vector_hash']=digest(qvector)
            for v,h in hs.items():
                if readiness[v] is not True:result['variants'][v]={'failure':readiness[v]};continue
                candidates=h.search(query,k=8,version=version,query_vector=qvector)
                modes=('A',) if v=='v2' else ('B','C')
                for mode in modes:
                    packet,trace=pack_evidence(candidates,max_tokens=3000,expand_parent=mode=='C')
                    result['variants'][mode]={'candidates':candidates,'candidate_hash':digest(candidates),
                        'context':packet,'packing':trace,'index':v,'namespace':h.index_namespace}
            if 'B' in result['variants'] and 'C' in result['variants']:
                assert result['variants']['B']['candidate_hash']==result['variants']['C']['candidate_hash']
        except Exception as exc:result['failure']=getattr(exc,'code',type(exc).__name__)
        result['usage']=cl.usage_history[start:];write_json(target,result)
        print('Retrieval '+case['id']+' recorded',flush=True)
    cl.key='';os.environ.pop('METIS_API_KEY',None)


class FrozenCandidates:
    """Controlled evaluation adapter; Agent still runs every production role.

    Retrieval is a preceding, paid, recorded phase. An extract-generated summary
    cannot change candidates in this comparison. Generated query is retained as
    trace data so the intervention is transparent.
    """
    def __init__(self,result,variant):self.result=result;self.variant=variant;self.last_trace={}
    def search(self,query,**kwargs):
        r=self.result['variants'][self.variant]
        self.last_trace={'method':'controlled_persisted_live_hybrid','candidate_hash':r['candidate_hash'],
            'candidates':[x['id'] for x in r['candidates']],'query':self.result['query'],
            'query_vector_hash':self.result['query_vector_hash'],'generated_query_not_used':query,
            'embedding':{'usage':[]},'index':r['index'],'namespace':r['namespace']}
        return r['candidates']


def answers():
    from casepilot.agent import Agent
    from casepilot.store import Store
    cases={c['id']:c for c in load_cases()};chosen=read_json(DATA/'protocol.json')['answer_cases']
    code=code_snapshot('answers_initial');cl=client('answers')
    for cid in chosen:
        retpath=RUN/'retrieval'/(cid+'.json')
        if not retpath.exists():continue
        retrieval=read_json(retpath)
        for variant in ('A','B','C'):
            target=RUN/'answers'/(cid+'_'+variant+'.json')
            if target.exists():continue
            output=None;error=None;start=len(cl.usage_history);case=cases[cid]
            trace=None
            try:
                assert variant in retrieval['variants'] and 'failure' not in retrieval['variants'][variant]
                store=Store(ROOT/('runtime/quality_v27/completion_20261010/'+cid+'_'+variant+'.sqlite3'))
                agent=Agent(store,client=cl,hybrid=FrozenCandidates(retrieval,variant),
                    components={'parent_context':variant=='C','context_tokens':3000,'rewrite':False})
                output=agent.turn(cid,case['initial_message'],'completion-initial',case['initial_facts'],case['initial_checks'])
                trace=store.traces()
            except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
            write_json(target,{'id':cid,'variant':variant,'split':case['split'],'output':output,'failure':error,
                'failure_category':classify_failure(error or (output or {}).get('validation_error')),
                'usage':cl.usage_history[start:],'code_hash':code,'retrieval_hash':digest(retrieval),
                'human_review':None,'independent_review':None})
            if trace is not None:write_json(RUN/'answer_traces'/(cid+'_'+variant+'.json'),trace)
            print('Answer '+cid+' / '+variant+' recorded: '+str(error or (output or {}).get('validation_error')),flush=True)
    cl.key='';os.environ.pop('METIS_API_KEY',None)


def pool():
    """Build blind packets only; no grade inferred from missing labels."""
    for case in load_cases():
        path=RUN/'retrieval'/(case['id']+'.json')
        if not path.exists():continue
        ret=read_json(path);unique={}
        for variant in ret['variants'].values():
            for row in variant.get('candidates',[])[:8]:
                unique[candidate_key(row)]=row
            # Parent context can introduce additional assertions; review those
            # exact windows too, with no variant ID supplied to the annotator.
            for row in variant.get('context',[]):unique[candidate_key(row)]=row
        packet={'id':case['id'],'report':case['initial_message'],'product_version':case['initial_facts'].get('streamlit_version'),
            'candidates':[dict({k:r.get(k) for k in ('source_id','revision','product_version','source_span','lines','title','section','text')},
                               candidate_key=key) for key,r in sorted(unique.items())],
            'instructions':'Judge actual exact text relevance 0=irrelevant,1=topic only,2=useful partial,3=direct needed evidence; null=unjudged. Do not infer relevance from official source status. Record origin.'}
        target=RUN/'blind_pool'/(case['id']+'.json')
        if not target.exists():write_json(target,packet)
    print('Deduplicated source-window pool exported without variant names.')


def accounting():
    auth=verify();b=Budget(ROOT/'runtime/team_budget.sqlite3',5)
    with b.db() as db:
        db.row_factory=sqlite3.Row
        rows=[dict(r) for r in db.execute('SELECT c.*,m.phase FROM calls c JOIN completion_calls m ON c.id=m.id WHERE m.campaign=?',(auth['campaign'],))]
    result={'hard_cap_usd':auth['hard_cap_usd'],'requests':len(rows),
        'confirmed_usd':sum(r['charged'] for r in rows if r['status']=='confirmed'),
        'unknown_reserved_usd':sum(r['charged'] for r in rows if r['status']!='confirmed'),
        'charged_or_reserved_usd':sum(r['charged'] for r in rows),
        'phases':{p:{'requests':sum(r['phase']==p for r in rows),
                    'confirmed_usd':sum(r['charged'] for r in rows if r['phase']==p and r['status']=='confirmed'),
                    'unknown_reserved_usd':sum(r['charged'] for r in rows if r['phase']==p and r['status']!='confirmed')}
                  for p in auth['phase_limits']},'historical_before':auth['cost_before']}
    assert result['requests']<=343 and result['charged_or_reserved_usd']<=1.10+1e-9
    write_json(RUN/'accounting.json',result);print(json.dumps(result))


def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['authorize','judge','embeddings','retrieve','answers','pool','accounting'])
    p.add_argument('--attempt',type=int,default=1);p.add_argument('--hypothesis');a=p.parse_args()
    if a.phase=='judge':judge(a.attempt,a.hypothesis)
    else:globals()[{'authorize':'authorize','embeddings':'embeddings','retrieve':'retrieve','answers':'answers','pool':'pool','accounting':'accounting'}[a.phase]]()

if __name__=='__main__':main()
