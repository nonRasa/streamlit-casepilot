"""Generate portable schemas, n8n JSON, notebook and request examples. No credentials."""
import argparse, json, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import write_json
from casepilot.model import SCHEMA
from casepilot.roles import EXTRACTION, REWRITE, RERANK, JUDGE, JUDGE_PROMPT
from notebook_v2 import notebook

def node(name,kind,parameters,x,y,version=2,credentials=None):
    row={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'casepilot/'+name)),'name':name,'type':'n8n-nodes-base.'+kind,'typeVersion':version,'position':[x,y],'parameters':parameters}
    if credentials: row['credentials']={'httpHeaderAuth':{'id':'','name':credentials}}
    if kind=='webhook': row['webhookId']=str(uuid.uuid5(uuid.NAMESPACE_URL,'casepilot-webhook/'+name))
    return row

def workflow(base_url):
    nodes=[]; connections={}
    for index,(route,review,required,optional) in enumerate([
        ('turn',False,['case_id','message','request_id'],['facts','checks','method']),
        ('review',True,['case_id','proposal_id','proposal_hash','decision','reviewer'],['edited_actions']),
        ('execute',True,['case_id','proposal_id','approval_id'],[]) ]):
        y=index*320; prefix=route.title()
        incoming='CasePilot Reviewer Webhook' if review else 'CasePilot Operator Webhook'
        backend='CasePilot Reviewer API' if review else 'CasePilot Operator API'
        names=[prefix+' Webhook',prefix+' Validate',prefix+' Python API',prefix+' Response']
        js="const b=$json.body; const required="+json.dumps(required)+"; const optional="+json.dumps(optional)+";\nif(!b || typeof b!=='object' || Array.isArray(b) || required.some(k=>!(k in b)) || Object.keys(b).some(k=>!required.includes(k)&&!optional.includes(k))) throw new Error('Invalid request fields');\nif(typeof b.case_id!=='string'||! /^[A-Za-z0-9_-]{1,80}$/.test(b.case_id)) throw new Error('Invalid case ID');\nreturn [{json:{body:b}}];"
        nodes.extend([
            node(names[0],'webhook',{'httpMethod':'POST','path':'casepilot-'+route,'authentication':'headerAuth','responseMode':'responseNode','options':{}},0,y,credentials=incoming),
            node(names[1],'code',{'mode':'runOnceForAllItems','jsCode':js},240,y),
            node(names[2],'httpRequest',{'method':'POST','url':base_url.rstrip('/')+'/api/'+route,
                 'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth',
                 'sendBody':True,'specifyBody':'json','jsonBody':'={{ JSON.stringify($json.body) }}',
                 'options':{'timeout':210000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'json'}}}},500,y,4.2,backend),
            node(names[3],'respondToWebhook',{'respondWith':'json','responseBody':'={{ $json.body }}','options':{'responseCode':'={{ $json.statusCode }}'}},760,y,1.4)
        ])
        for a,b in zip(names,names[1:]): connections[a]={'main':[[{'node':b,'type':'main','index':0}]]}
    audit='Turn Pipeline Contract'
    js="""const r=$json; const b=r.body;
if(r.statusCode>=200 && r.statusCode<300) {
  if(!b || !b.proposal || !b.proposal.id || !b.proposal.hash) throw new Error('Missing scoped proposal');
  if(b.method==='final') {
    if(b.architecture!=='v2' || !Array.isArray(b.pipeline) || b.model_calls>8 || b.repair_count>1) throw new Error('Invalid bounded pipeline result');
    if(b.quality_revision!=='v2.2-quality') throw new Error('Unsupported quality contract');
    if(!b.validation_error && (!b.judge || b.judge.verdict!=='accept')) throw new Error('Unchecked draft rejected');
    if(!b.validation_error && b.mode==='live' && (!b.reviewed_draft || b.judge.draft_version!==b.reviewed_draft.draft_version)) throw new Error('Stale draft review');
    if(b.validation_error && (b.decision!=='escalate' || b.summary.sources.length)) throw new Error('Unsafe fallback rejected');
    if(b.decision==='escalate' && (!b.summary.handoff || !b.summary.handoff.maintainer_action)) throw new Error('Missing actionable handoff');
    if(b.validation_error==='judge_contract_error' && !b.review_failures.some(x=>x.kind==='judge_contract')) throw new Error('Missing contract failure trace');
  }
}
return [{json:r}];"""
    nodes.append(node(audit,'code',{'mode':'runOnceForAllItems','jsCode':js},740,0))
    next(n for n in nodes if n['name']=='Turn Response')['position']=[1000,0]
    connections['Turn Python API']={'main':[[{'node':audit,'type':'main','index':0}]]}
    connections[audit]={'main':[[{'node':'Turn Response','type':'main','index':0}]]}
    return {'name':'CasePilot V2 — Reviewed RAG, Human Review, Execute','nodes':nodes,'connections':connections,'active':False,
            'settings':{'executionOrder':'v1','saveDataSuccessExecution':'none','saveDataErrorExecution':'none','saveManualExecutions':False,'executionTimeout':240},
            'pinData':{},'tags':[], 'meta':{'templateCredsSetupCompleted':False}}

def main(base):
    answer_schema=json.loads(json.dumps(SCHEMA))
    answer_schema['properties']['claims']['items']['required']=['evidence_id','quote']
    answer_schema['properties']['claims']['items']['properties']={'evidence_id':{'type':'string'},'quote':{'type':'string','minLength':20,'maxLength':1000}}
    write_json(ROOT/'schemas'/'answer.schema.json',answer_schema)
    write_json(ROOT/'schemas'/'model_selection.schema.json',SCHEMA)
    for name,schema in [('extraction',EXTRACTION),('rewrite',REWRITE),('rerank',RERANK),('judge',JUDGE)]:
        write_json(ROOT/'schemas'/(name+'.schema.json'),schema)
    write_json(ROOT/'policies'/'judge_rubric.json',{'architecture':'v2','prompt':JUDGE_PROMPT,'schema':'schemas/judge.schema.json',
        'acceptance':'all six criteria score 2, no findings, deterministic gates pass','repair_limit':1,'repeat_judge_after_repair':True,
        'human_comparison':'Independent human scores on the same V2 outputs remain required. Historical V1 AI review is not human ground truth.',
        'can_approve_or_execute':False})
    write_json(ROOT/'policies'/'tool_manifest.json',{'tools':[
        {'name':'read_case','implementation':'Store.get','input':{'case_id':'string'},'output':'case state, pending proposal, comments','errors':['invalid_id','not_found'],'write':False},
        {'name':'search_evidence','implementation':'HybridRetriever.search','input':{'query':'string','k':'integer <= 8','version':'string or null'},'output':'versioned candidates; at most 5 enter final context','errors':['invalid_input','embedding_index_not_ready','budget_exhausted'],'write':False},
        {'name':'prepare_proposal','implementation':'Store.propose','input':{'case_id':'string','revision':'integer','payload':'validated actions and summary'},'output':'proposal id, hash, revision','errors':['invalid_action','conflict'],'write':'internal draft only'},
        {'name':'review_proposal','implementation':'Store.review','input':{'decision':'approve | reject | edit','proposal_hash':'string','reviewer':'authenticated actor'},'output':'approval or replacement draft','errors':['stale_approval','proposal_changed','already_reviewed'],'write':'internal approval only'},
        {'name':'execute_approved','implementation':'Store.execute','input':{'case_id':'string','proposal_id':'string','approval_id':'string'},'output':'stored effects and idempotent result','errors':['approval_required','approval_expired','stale_approval','resolution_unconfirmed'],'write':'local tracker only'}]})
    write_json(ROOT/'policies'/'execution_policy.json',{'architecture':'v2','max_steps_per_turn':14,'max_model_calls_per_turn':8,'max_repair_attempts':1,'max_turn_usd':.04,'max_turn_seconds':180,'max_user_turns_per_case':100,'max_candidates':8,'max_retrieved_chunks':5,'max_context_utf8_bytes':10000,'max_message_characters':20000,'max_actions':3,'approval_ttl_seconds':900,'team_budget_usd':5,'default_operational_cap_usd':.50,'auto_execute':False,'allowed_gateway_host':'api.metisai.ir','writes':'local SQLite only'})
    write_json(ROOT/'workflows'/'casepilot_main.json',workflow(base))
    write_json(ROOT/'CasePilot_project.ipynb',notebook())
    from update_quality_v22_notebook import main as update_notebook
    from export_quality_v22_contracts import main as export_contracts
    update_notebook(); export_contracts()
    write_json(ROOT/'examples'/'turn.json',{'case_id':'demo-1','request_id':'example-turn-1','message':'مقدار session_state پس از تغییر صفحه از بین می‌رود.','facts':{},'checks':[]})
    write_json(ROOT/'examples'/'review.json',{'case_id':'demo-1','proposal_id':'COPY_FROM_TURN_RESULT','proposal_hash':'COPY_FROM_TURN_RESULT','decision':'reject','reviewer':'نگه‌دارنده'})
    write_json(ROOT/'examples'/'execute.json',{'case_id':'demo-1','proposal_id':'COPY_FROM_TURN_RESULT','approval_id':'COPY_FROM_REVIEW_RESULT'})
    if not (ROOT/'artifacts'/'live_run_manifest.json').exists():
        write_json(ROOT/'artifacts'/'live_run_manifest.json',{'status':'not_run','provider_requests':0,'reason':'No execution result exists.','n8n_status':'JSON generated; user imports and verifies on their own instance.'})
    print('وضعیت: نوت‌بوک، قراردادها و گردش‌کار ساخته شدند.')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--backend-url',default='https://YOUR-CASEPILOT-BACKEND.example'); p.add_argument('--workflow-only',action='store_true'); args=p.parse_args()
    if args.workflow_only:
        write_json(ROOT/'workflows/casepilot_main.json',workflow(args.backend_url)); print('وضعیت: فقط گردش‌کار بازسازی شد؛ نوت‌بوک حفظ شد.')
    else: main(args.backend_url)
