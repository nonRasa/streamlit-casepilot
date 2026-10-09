"""Bounded orchestration: read -> retrieve -> draft -> validate -> propose. Never auto-write."""
from __future__ import annotations
import re, threading, time
from .common import *
from .store import Store
from .retrieval import Retriever
from .model import make_client
from .grounding import validate_answer, fallback, render_response

def version_observations(message):
    from .memory import version_roles
    explicit=version_roles(message)
    from .evidence import VERSION
    plain=re.sub(r'```.*?```',' ',message,flags=re.S).replace('`','').replace('**','')
    patterns={
        'streamlit_version':r'(?i)(?:streamlit(?:-nightly)?(?:\s+version)?\s*[:|=]?\s*`?|streamlit==)('+VERSION+r')(?![\w.+-])',
        'python_version':r'(?i)python(?:\s+version)?\s*[:|=]?\s*`?('+VERSION+r')(?![\w.+-])',
    }
    values={}
    for key,pat in patterns.items():
        name='streamlit' if key=='streamlit_version' else 'python'
        labeled_lines=re.findall(r'(?im)^\s*(?:[-*]\s*)?'+name+r'\s+version\s*[:|=]\s*([^\n]*)',plain)
        labeled={v for line in labeled_lines for v in re.findall(r'('+VERSION+r')(?![\w.+-])',line)}
        roles=[r for r in explicit if r['key']==key]
        current=[r['value'] for r in roles if r['role']=='current']
        corrections=[r['value'] for r in roles if r.get('correction')]
        values[key]={corrections[-1]} if corrections else (set(current) if current else ({r['value'] for r in roles if r['role']=='unknown'} if roles else (labeled if labeled else set(re.findall(pat,plain)))))
    return values

def extract_facts(message):
    return {key:next(iter(values)) for key,values in version_observations(message).items() if len(values)==1}

class Agent:
    MAX_STEPS=14; MAX_MODEL_CALLS=8
    LEGACY_MAX_STEPS=5; LEGACY_MAX_MODEL_CALLS=1
    def __init__(self,store=None,retriever=None,client=None,mode='replay',architecture='v2',hybrid=None,components=None):
        self.store=store or Store(ROOT/'runtime'/'tracker.sqlite3')
        self.retriever=retriever or Retriever(); self.client=client or make_client(mode)
        require(architecture in ('v1','v2'),'invalid_architecture','نسخهٔ معماری معتبر نیست.')
        self.architecture=architecture; self.hybrid=hybrid; self.components=components
        self.lock=threading.RLock()

    def turn(self,case_id,message,request_id,facts=None,checks=None,method='final'):
        identifier(case_id); identifier(request_id); message=bounded_text(message)
        facts=facts_input(facts or {}); checks=checks or []
        require(isinstance(checks,list) and len(checks)<=30,'invalid_checks','بررسی‌ها معتبر نیستند.')
        checks=[bounded_text(x,'check',1000) for x in checks]
        require(method in ('baseline','final'),'invalid_method','روش اجرا معتبر نیست.')
        original={'message':message,'facts':facts,'checks':checks,'method':method}
        if self.architecture=='v2': original.update(architecture='v2',components=self.components)
        h=digest(original)
        with self.lock:
            prior=self.store.turn_result(case_id,request_id,h)
            if prior: return dict(prior,request_replayed=True)
            if self.architecture=='v2' and method=='final':
                from .pipeline import run
                self.store.begin_turn(case_id,request_id,h,{'message':message,'facts':facts,'checks':checks,'method':method})
                try: return run(self,case_id,message,request_id,facts,checks,h,self.components)
                except BaseException as exc:
                    self.store.interrupted_turn(case_id,request_id,getattr(exc,'code',type(exc).__name__))
                    raise
            start=time.perf_counter(); combined=extract_facts(message); combined.update(facts)
            state=self.store.update(case_id,message,combined,checks,request_id=request_id,input_hash=h)
            self.store.event(case_id,'tool_result',{'tool':'read_case','revision':state['revision']})
            # Latest correction and user message lead; old report remains available with bounded context.
            query=message+'\n'+' '.join(str(x) for x in state['facts'].values())+'\n'+state['messages'][0]['text'][:9000]
            evidence=self.retriever.search(query,k=5,method=method,version=state['facts'].get('streamlit_version'))
            self.store.event(case_id,'tool_result',{'tool':'search_evidence','ids':[x['id'] for x in evidence],'method':method})
            # Context size bounded before the client. No gold labels or future turns are in this state.
            packet=[]; size=0
            for row in evidence:
                if size+len(row['text'])>10000: break
                packet.append(row); size+=len(row['text'])
            calls_before=self.client.calls; validation_error=None
            try:
                answer=self.client.generate(state,packet,method)
                require(self.client.calls-calls_before<=self.LEGACY_MAX_MODEL_CALLS,'call_limit','سقف فراخوانی مدل رسیده است.')
                citations=validate_answer(answer,packet)
            except CasePilotError as exc:
                if exc.code in ('budget_exhausted','provider_error','missing_credentials','missing_prices','invalid_gateway'):
                    self.store.event(case_id,'model_error',{'code':exc.code}); raise
                validation_error=exc.code; answer=fallback(exc.code); citations=[]
            response=render_response(answer,citations,state['facts'],state['checks'])
            summary={'problem':state['messages'][0]['text'][:2500],'facts':state['facts'],
                     'unknowns':[k for k in ('streamlit_version','python_version','deployment','reproducible') if state['facts'].get(k) is None],
                     'completed_checks':state['checks'],'sources':citations,'decision':answer['decision'],
                     'next_step':answer['next_step'],'rationale':answer['rationale'],'hypotheses':answer['hypotheses']}
            from .routing import proposal_actions
            payload={'actions':proposal_actions(response,answer['decision'],validation_error),
                     'source_ids':[x['source_id'] for x in citations],'summary':summary}
            proposal=self.store.propose(case_id,state['revision'],payload)
            result={'case_id':case_id,'request_id':request_id,'mode':self.client.mode,'method':method,
                    'decision':answer['decision'],'response':response,'summary':summary,'proposal':proposal,
                    'retrieved':[ {k:x.get(k) for k in ('id','source_id','kind','url','section','product_version','retrieval_score')} for x in packet],
                    'architecture':'v1','steps':self.LEGACY_MAX_STEPS,'model_calls':self.client.calls-calls_before,
                    'usage':self.client.last_usage,'validation_error':validation_error,'latency_seconds':round(time.perf_counter()-start,6)}
            self.store.save_turn(case_id,request_id,h,result)
            self.store.event(case_id,'turn_completed',{k:v for k,v in result.items() if k not in ('response','summary','proposal')})
            return result

    def resume(self,case_id,request_id):
        job=self.store.pending_turn(case_id,request_id)
        return self.turn(case_id,request_id=request_id,**job['input'])
