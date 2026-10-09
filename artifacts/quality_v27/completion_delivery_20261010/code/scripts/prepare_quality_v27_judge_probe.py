"""Prepare same-draft judge comparison without a model call or new authorization."""
import hashlib, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json,write_json,digest,canonical
from casepilot.model import quote_candidates,resolve_claims
from casepilot.review_contract import draft_units
BASE=ROOT/'artifacts/quality_v27';TARGET=BASE/'same_draft_probe'

def prepare():
    if (TARGET/'plan.json').exists():raise SystemExit('Probe already frozen.')
    result=read_json(BASE/'contract_live_01/turns/GH17011_S1.json')['output']
    plan=read_json(BASE/'contract_live_01/authorization.json')
    initial=next(c for c in plan['cases'] if c['id']=='GH17011')
    corpus={r['id']:r for r in read_json(ROOT/'data/corpus_v2.json')}
    evidence=[dict(corpus[r['id']],**{k:v for k,v in r.items() if k not in ('id','source_id')}) for r in result['retrieved']]
    cache=[read_json(p) for p in (ROOT/'runtime/quality_v27/contract_live_01/S1/response_cache').glob('*.json')]
    raw=next(r['raw_answer'] for r in cache if r['usage']['kind']=='chat')
    answer=resolve_claims(raw,{(e['id'],q['quote_id']):q['text'] for e in evidence for q in quote_candidates(e['text'])})
    state={'id':'GH17011','revision':1,'messages':[{'role':'user','text':initial['initial_message']}],
        'facts':result['summary']['facts'],'checks':result['summary']['completed_checks'],
        'experiments':result['summary']['experiments'],'investigation_plan':result['summary']['investigation_plan']}
    env=draft_units(answer,'GH17011',1,0)
    assert env==result['reviewed_draft'],'Reconstructed draft differs'
    # Freeze compatibility-only fix on top of S1; all other production files match S1.
    fixed=BASE/'S1_compatible/code'
    shutil.copytree(BASE/'S1/code',fixed,dirs_exist_ok=False)
    shutil.copyfile(ROOT/'src/casepilot/compact_review.py',fixed/'src/casepilot/compact_review.py')
    files={p.relative_to(fixed).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in fixed.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    write_json(BASE/'S1_compatible/manifest.json',{'parent':'S1','change':'gateway compatibility only; uniqueItems removed, duplicate-reference validator preserved','files':files})
    packet={'state':state,'answer':answer,'evidence':evidence,'envelope':env}
    write_json(TARGET/'input.json',packet)
    write_json(TARGET/'plan.json',{'authorization_status':'pending_explicit_scope_approval','purpose':'Judge identical captured draft to isolate wire contract from upstream generation/retrieval randomness',
        'variants':['S0','S1_compatible'],'model':'gpt-4.1-mini','max_requests':2,'max_output_tokens_each':1600,
        'estimated_input_tokens_total':12000,'estimated_output_tokens_total':2200,
        'estimated_cost_usd':.0092,'hard_cap_usd':.04,'per_request_cap_usd':.02,
        'embedding_requests':0,'generation_requests':0,'automatic_retry':False,
        'input_hash':digest(packet),'parent_live_attempt':'contract_live_01','human_review_completed':False})
    print('Same-draft probe frozen; 0 provider requests; explicit scope approval required.')

if __name__=='__main__':prepare()
