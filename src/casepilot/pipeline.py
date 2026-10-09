"""V2 bounded roles: extract -> retrieve -> rerank -> draft -> judge -> repair once.

Model roles never receive tracker approval/execute tools. The only final effect is
a hashed proposal. Independent invocation is not independent human evaluation.
"""
import re, time
from .common import *
from .model import SYSTEM, SCHEMA, QUALITY_SELECTION, quote_candidates, resolve_claims
from .grounding import validate_answer, fallback, render_response
from .hybrid import HybridRetriever
from .roles import *
from .quality import compact_context, retrieval_query, report_inventory, REVISION
from .review_contract import draft_units, checked_review_v23, review_spans, recompose, bound_review_schema, unpack_bound_review
from .routing import handoff, render_handoff, proposal_actions
from .semantics import semantic_schema, checked_semantic_review, prepare_feature, recompose_semantic
from .compact_review import packet as compact_review_packet, schema as compact_review_schema, decode as decode_compact_review, PROMPT as COMPACT_JUDGE_PROMPT
from .case_type import case_kind, selection_schema, check_selection
from .model_diagnostics import PROVIDER_FAILURES

MAX_CALLS=8
MAX_TURN_USD=.04

def compact_state(state):
    return compact_context(state)

def evidence_packet(rows):
    return [{k:r.get(k) for k in ('id','source_id','kind','title','section','text','revision','product_version','version_relation','temporal_status','source_authority','url')} for r in rows]

def pack(rows,max_bytes=10000,k=5):
    selected=[]; size=0; seen=set()
    for row in rows:
        cost=len(row['text'].encode())
        if cost>max_bytes-size or row['sha256'] in seen: continue
        selected.append(row); size+=cost; seen.add(row['sha256'])
        if len(selected)==k: break
    return selected

def fixture_role(role,packet):
    """Transparent fixtures for control-flow tests; they do not score model quality."""
    if role=='extract':
        from .agent import extract_facts
        message=packet['message']; facts=extract_facts(message)
        return {'facts':[{'key':k,'value':str(v),'quote':message[:1800]} for k,v in facts.items() if str(v) in message[:1800]],'completed_checks':[],'ambiguities':[]}
    if role=='rewrite': return {'query':packet['query'][:1800]}
    if role=='rerank': return {'ordered_ids':[r['id'] for r in packet['candidates']]}
    if role=='judge': return {'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: بدل آزمایشی؛ داوری معنایی مدل نیست.'} for k in CRITERIA}}
    raise CasePilotError('unknown_role','نقش مدل شناخته‌شده نیست.')

def repair_feedback(review,envelope):
    """Keep every actionable finding without duplicating the judge's full spans."""
    fields={u['unit_id']:u['field'] for u in envelope['units']}
    return {'failure_kind':review.get('failure_kind'),
            'findings':[dict(f,field=fields.get(f.get('unit_id'))) for f in review['findings']]}

def run(agent,case_id,message,request_id,facts,checks,input_hash,components=None):
    options={'dense':True,'mmr':True,'rerank':True,'judge':True,'rewrite':True,'quality':True}; options.update(components or {})
    start=time.perf_counter(); client=agent.client; before=client.calls; stages=[]; usages=[]
    usage_start=len(getattr(client,'usage_history',[]))
    budget_before=client.budget.report()['charged_or_reserved_usd'] if client.mode=='live' else 0
    client.turn_scope={'calls_before':before,'cost_before':budget_before,'max_calls':MAX_CALLS,'cap_usd':MAX_TURN_USD,'deadline':time.monotonic()+180}
    def event(stage,detail):
        stages.append({'stage':stage,**detail}); agent.store.event(case_id,'pipeline_stage',stages[-1])
    def role(name,prompt,packet,schema,max_tokens=800):
        require(client.calls-before<MAX_CALLS,'call_limit','سقف فراخوانی این نوبت رسیده است.')
        require(time.monotonic()<client.turn_scope['deadline'],'turn_timeout','زمان مجاز این نوبت تمام شده است.')
        try:
            if client.mode=='live': return client.structured(name,prompt,packet,schema,max_tokens)
            client.calls+=1; client.last_usage={'mode':'replay','provider_requests':0,'cost_usd':0,'kind':name}
            return fixture_role(name,packet)
        finally: usages.append(dict(client.last_usage))
    def draft(state,evidence,feedback=None):
        require(client.calls-before<MAX_CALLS,'call_limit','سقف فراخوانی این نوبت رسیده است.')
        try:
            if feedback is None:
                generated=client.generate(state,evidence,'final')
                require(client.mode!='live' or (isinstance(generated,dict) and {'diagnostic','feature_proposal'}<=set(generated)),'invalid_model_output','قرارداد تشخیص و قابلیت در پاسخ واقعی ناقص است.')
                return prepare_feature(generated,state)
            if client.mode!='live': return client.generate(state,evidence,'final')
            lookup={}; sources=[]
            for row in evidence:
                candidates=quote_candidates(row['text']); sources.append(dict({k:row.get(k) for k in ('id','kind','section','product_version','version_relation')},quote_candidates=candidates))
                lookup.update({(row['id'],q['quote_id']):q['text'] for q in candidates})
            selected=client.structured('repair',SYSTEM+'\nCorrect the specific review findings once. Do not repair or guess invalid IDs. Select fresh exact candidates. If support is lacking, ask a new discriminating question or escalate.',
                {'case_type':case_kind(state),'state':compact_state(state),'evidence':sources,'feedback':feedback},selection_schema(state),client.max_output)
            return prepare_feature(resolve_claims(check_selection(selected,state),lookup),state)
        finally: usages.append(dict(client.last_usage))
    try:
        from .agent import extract_facts, version_observations
        extracted={}; extracted_checks=[]; ambiguities=[]; investigation={}; experiment_events=[]
        try:
            if client.mode=='live':
                try: previous=agent.store.get(case_id)
                except CasePilotError as exc:
                    if exc.code!='not_found': raise
                    previous={'messages':[]}
                combined='\n\n'.join(x['text'] for x in previous['messages'])
                # Latest input is the only source for new facts; historical
                # context is provided separately for novelty, never permissions.
                inventory=report_inventory({'messages':previous['messages']+[{'text':message}],'facts':facts})
                raw=role('extract',QUALITY_EXTRACT_PROMPT,{'message':message,'prior_context':combined[-12000:],'explicit_facts':facts,'reported_inventory':inventory,'prior_experiments':previous.get('experiments',[])[-24:]},QUALITY_EXTRACTION,1200)
                require(isinstance(raw,dict) and 'experiment_events' in raw,'invalid_extraction','حافظهٔ ساخت‌یافته در خروجی استخراج وجود ندارد.')
                experiment_events=raw.pop('experiment_events')
                investigation=checked_investigation(raw.pop('investigation'),message)
                from .memory import checked_events
                experiment_events=checked_events(experiment_events,message,previous.get('experiments',[]))
            else: raw=role('extract',EXTRACT_PROMPT,{'message':message,'explicit_facts':facts},EXTRACTION)
            extracted,extracted_checks,ambiguities=checked_extraction(raw,message)
            event('extract',{'status':'ok','keys':sorted(extracted),'facts_with_quotes':raw['facts'],'checks':extracted_checks,'ambiguities':ambiguities})
        except CasePilotError as exc:
            if exc.code in PROVIDER_FAILURES|{'budget_exhausted','turn_budget_exhausted','call_limit','turn_timeout'}: raise
            event('extract',{'status':'fallback','error':exc.code})
            experiment_events=[]
        extracted.update(extract_facts(message))
        for key,values in version_observations(message).items():
            if len(values)>1:
                extracted[key]=None; ambiguities.append('ابهام: بیش از یک مقدار صریح برای '+key+' وجود دارد.')
        extracted.update(facts)
        state=agent.store.update(case_id,message,extracted,list(dict.fromkeys(checks+extracted_checks))[:30],request_id=request_id,input_hash=input_hash,experiment_events=experiment_events)
        investigation=investigation or state.get('investigation_plan',{})
        state['investigation_plan']=investigation
        agent.store.save_plan(case_id,state['revision'],investigation)
        event('read_case',{'revision':state['revision']})
        answer=None; packet=[]; validation_error=None; judge=None; repair_count=0; review_failures=[]; envelope=None
        try:
            query=((investigation.get('problem_summary','')+'\n') if investigation else '')+retrieval_query(state,message)
            # One rewrite only for cross-language query; never an unbounded retrieval loop.
            if options['rewrite'] and re.search(r'[\u0600-\u06ff]',message):
                try:
                    rewritten=role('rewrite',REWRITE_PROMPT,{'query':query[:8000],'facts':state['facts']},REWRITE,400)
                    require(isinstance(rewritten,dict) and set(rewritten)=={'query'} and isinstance(rewritten['query'],str) and 1<=len(rewritten['query'])<=1800,'invalid_rewrite','بازنویسی جست‌وجو معتبر نیست.')
                    query=rewritten['query']+'\n'+query[:2200]; event('rewrite',{'status':'ok','query':rewritten['query']})
                except CasePilotError as exc:
                    if exc.code in PROVIDER_FAILURES|{'budget_exhausted','turn_budget_exhausted','call_limit','turn_timeout'}: raise
                    event('rewrite',{'status':'fallback','error':exc.code})
            if agent.hybrid is None: agent.hybrid=HybridRetriever(client)
            search_args={'k':8,'version':state['facts'].get('streamlit_version'),'components':options}
            if options.get('as_of'): search_args['as_of']=options['as_of']
            candidates=agent.hybrid.search(query,**search_args)
            retrieval_trace=agent.hybrid.last_trace; event('retrieve',retrieval_trace)
            usages.extend(retrieval_trace.get('embedding',{}).get('usage',[]))
            if candidates and options['rerank']:
                try:
                    ranked=role('rerank',RERANK_PROMPT,{'state':compact_state(state),'candidates':evidence_packet(candidates)},RERANK,350)
                    candidates=rerank_ids(ranked,candidates); event('rerank',{'status':'ok','ids':[r['id'] for r in candidates]})
                except CasePilotError as exc:
                    if exc.code in PROVIDER_FAILURES|{'budget_exhausted','turn_budget_exhausted','call_limit','turn_timeout'}: raise
                    event('rerank',{'status':'fallback','error':exc.code,'ids':[r['id'] for r in candidates]})
            packet=pack(candidates); event('context_pack',{'ids':[r['id'] for r in packet],'utf8_bytes':sum(len(r['text'].encode()) for r in packet)})
            answer=draft(state,packet); event('draft',{'status':'produced'})
            # Invalid individual quotes cannot silently survive, nor erase other
            # fields before the separate semantic review of the full remainder.
            retained=[]
            for claim in answer.get('claims',[]):
                try:
                    validate_answer(dict(answer,decision='escalate',claims=[claim]),packet)
                    retained.append(claim)
                except CasePilotError as exc:
                    if exc.code not in ('invalid_citation','unsupported_quote'): raise
                    event('drop_invalid_citation',{'code':exc.code})
            answer['claims']=retained
            forced=deterministic_findings(answer,packet,state)
            if options['judge']:
                for attempt in range(2):
                    envelope=draft_units(answer,case_id,state['revision'],attempt)
                    jp={'facts':state['facts'],'experiments':state.get('experiments',[])[-12:],
                        'decision':answer['decision'],'citations':answer['claims'],
                        'spans':review_spans(state,packet,answer['claims']),'draft':envelope}
                    if client.mode=='live':
                        try:
                            compact_contract,public_contract=compact_review_packet(envelope,jp['spans'])
                            jp['compact_contract']=public_contract
                            raw_review=role('judge',COMPACT_JUDGE_PROMPT,jp,compact_review_schema(compact_contract),1600)
                            judge=checked_semantic_review(decode_compact_review(raw_review,compact_contract),answer,packet,state,envelope,forced)
                            judge['wire_contract']=public_contract['version']
                        except CasePilotError as exc:
                            if exc.code in ('invalid_judge','judge_contract_error'):
                                review_failures.append({'kind':'judge_contract','code':exc.code,'reason':redact(str(exc))[:600],'draft_version':envelope['draft_version']})
                                if getattr(client,'diagnostics',None) and isinstance(client.last_usage.get('diagnostic'),dict):
                                    from .model_diagnostics import persist
                                    diagnostic=client.last_usage['diagnostic']
                                    diagnostic.update(status='contract_failed',failure_code=exc.code)
                                    diagnostic['diagnostic_file']=persist(client.diagnostics,diagnostic,canonical(raw_review),client.key)
                                event('judge_contract_failure',review_failures[-1])
                            raise
                    else: judge=checked_judge(role('judge',JUDGE_PROMPT,jp,JUDGE),forced)
                    event('judge',{'attempt':attempt+1,**judge,'evaluation_kind':'model' if client.mode=='live' else 'test_fixture'})
                    if judge['verdict']=='accept': break
                    review_failures.append({'kind':judge.get('failure_kind','answer_quality'),'draft_version':envelope['draft_version'],'findings':judge['findings']})
                    if attempt==1:
                        validation_error='judge_rejected'; answer=fallback(validation_error); break
                    repair_count+=1
                    preserved=recompose_semantic(answer,judge,envelope,state) if client.mode=='live' else None
                    if preserved:
                        answer=preserved; event('recompose',{'attempt':repair_count,'requires_recheck':True,'retained_fields':[u['field'] for u in envelope['units'] if u['unit_id'] in judge['valid_unit_ids']]})
                    elif judge['verdict']=='escalate':
                        validation_error='judge_rejected'; answer=fallback(validation_error); break
                    else:
                        answer=draft(state,packet,repair_feedback(judge,envelope)); event('repair',{'attempt':repair_count})
                    forced=deterministic_findings(answer,packet,state)
            elif forced:
                validation_error='deterministic_review_failed'; answer=fallback(validation_error)
            citations=validate_answer(answer,packet)
        except CasePilotError as exc:
            # Stop without retries or an unchecked technical answer. No write is granted.
            validation_error=exc.code; answer=fallback(exc.code); citations=[]
            event('safe_escalation',{'error':exc.code})
        require(client.calls-before<=MAX_CALLS,'call_limit','سقف فراخوانی این نوبت نقض شده است.')
        response=render_response(answer,citations,state['facts'],state['checks'])
        handoff_packet=handoff(state,citations,validation_error,answer,review=judge) if answer['decision']=='escalate' else None
        if handoff_packet: response+='\n\n'+render_handoff(handoff_packet,max_chars=max(1500,11500-len(response)))
        summary={'problem':state['messages'][0]['text'][:2500],'facts':state['facts'],
                 'unknowns':[k for k in ('streamlit_version','python_version','deployment','reproducible') if state['facts'].get(k) is None],
                 'completed_checks':state['checks'],'sources':citations,'decision':answer['decision'],'next_step':answer['next_step'],
                 'rationale':answer['rationale'],'hypotheses':answer['hypotheses'],'ambiguities':ambiguities,'judge':judge}
        summary['investigation_plan']=investigation
        summary.update(experiments=state.get('experiments',[]),memory_version=state.get('memory_version'),handoff=handoff_packet,review_failures=review_failures)
        proposal=agent.store.propose(case_id,state['revision'],{'actions':proposal_actions(response,answer['decision'],validation_error),
                    'source_ids':[c['source_id'] for c in citations],'summary':summary})
        agent.store.remember_proposed_check(case_id,state['revision'],answer.get('diagnostic'),answer['next_step'])
        event('prepare_proposal',{'id':proposal['id'],'hash':proposal['hash'],'auto_execute':False})
        if client.mode=='live': usages=client.usage_history[usage_start:]
        usage={'mode':client.mode,'provider_requests':sum(u.get('provider_requests',0) for u in usages),
               'cost_usd':sum(u.get('cost_usd',0) for u in usages),'reserved_usd':sum(u.get('reserved_usd',0) for u in usages if u.get('usage_unknown')),
               'stages':usages}
        # Ledger delta also accounts for retrieval failures before a vector is returned.
        if client.mode=='live':
            usage['charged_or_reserved_usd']=client.budget.report()['charged_or_reserved_usd']-budget_before
        result={'case_id':case_id,'request_id':request_id,'architecture':'v2','quality_revision':REVISION,'mode':client.mode,'method':'final','components':options,
                'decision':answer['decision'],'response':response,'summary':summary,'proposal':proposal,
                'retrieved':[{k:r.get(k) for k in ('id','source_id','kind','url','section','product_version','version_relation','temporal_status','source_authority','retrieval_score')} for r in packet],
                'steps':len(stages),'model_calls':client.calls-before,'max_calls':MAX_CALLS,'repair_count':repair_count,'judge':judge,'pipeline':stages,
                'usage':usage,'validation_error':validation_error,'review_failures':review_failures,'reviewed_draft':envelope,'latency_seconds':round(time.perf_counter()-start,6)}
        agent.store.save_turn(case_id,request_id,input_hash,result)
        agent.store.event(case_id,'turn_completed',{k:v for k,v in result.items() if k not in ('response','summary','proposal','pipeline')})
        return result
    finally: client.turn_scope=None
