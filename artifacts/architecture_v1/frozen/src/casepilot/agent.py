"""Bounded orchestration: read -> retrieve -> draft -> validate -> propose. Never auto-write."""
from __future__ import annotations
import re, threading, time
from .common import *
from .store import Store
from .retrieval import Retriever
from .model import make_client
from .grounding import validate_answer, fallback, render_response

def extract_facts(message):
    result={}
    patterns={
        'streamlit_version':r'(?i)(?:streamlit(?:\s+version)?\s*[:|=]?\s*`?|streamlit==)(\d+\.\d+(?:\.\d+)?)',
        'python_version':r'(?i)python(?:\s+version)?\s*[:|=]?\s*`?(\d+\.\d+(?:\.\d+)?)',
    }
    for key,pat in patterns.items():
        matches=re.findall(pat,message)
        if len(set(matches))==1: result[key]=matches[0]
    return result

class Agent:
    MAX_STEPS=5; MAX_MODEL_CALLS=1
    def __init__(self,store=None,retriever=None,client=None,mode='replay'):
        self.store=store or Store(ROOT/'runtime'/'tracker.sqlite3')
        self.retriever=retriever or Retriever(); self.client=client or make_client(mode)
        self.lock=threading.RLock()

    def turn(self,case_id,message,request_id,facts=None,checks=None,method='final'):
        identifier(case_id); identifier(request_id); message=bounded_text(message)
        facts=facts_input(facts or {}); checks=checks or []
        require(method in ('baseline','final'),'invalid_method','روش اجرا معتبر نیست.')
        original={'message':message,'facts':facts,'checks':checks,'method':method}
        h=digest(original)
        with self.lock:
            prior=self.store.turn_result(case_id,request_id,h)
            if prior: return dict(prior,request_replayed=True)
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
                require(self.client.calls-calls_before<=self.MAX_MODEL_CALLS,'call_limit','سقف فراخوانی مدل رسیده است.')
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
            status={'ask':'waiting_user','answer':'open','escalate':'escalated'}[answer['decision']]
            payload={'actions':[{'type':'comment','body':response},{'type':'status','value':status}],
                     'source_ids':[x['source_id'] for x in citations],'summary':summary}
            proposal=self.store.propose(case_id,state['revision'],payload)
            result={'case_id':case_id,'request_id':request_id,'mode':self.client.mode,'method':method,
                    'decision':answer['decision'],'response':response,'summary':summary,'proposal':proposal,
                    'retrieved':[ {k:x.get(k) for k in ('id','source_id','kind','url','section','product_version','retrieval_score')} for x in packet],
                    'steps':self.MAX_STEPS,'model_calls':self.client.calls-calls_before,
                    'usage':self.client.last_usage,'validation_error':validation_error,'latency_seconds':round(time.perf_counter()-start,6)}
            self.store.save_turn(case_id,request_id,h,result)
            self.store.event(case_id,'turn_completed',{k:v for k,v in result.items() if k not in ('response','summary','proposal')})
            return result
