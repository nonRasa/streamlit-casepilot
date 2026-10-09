"""Two judge requests against one frozen draft; separate explicit authorization."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/quality_v27';RUN=BASE/'same_draft_probe'
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_quality_v27_live import credentials,configure
from evaluate_quality_v25_live import ledger,read,write,sha

def worker(stage,live=False):
    sys.path.insert(0,str(BASE/stage/'code/src'))
    import casepilot.common as common
    common.ROOT=ROOT
    from casepilot.compact_review import packet,schema,PROMPT,decode
    from casepilot.review_contract import review_spans
    from casepilot.semantics import checked_semantic_review
    from casepilot.roles import deterministic_findings
    item=read(RUN/'input.json');plan=read(RUN/'plan.json')
    assert common.digest(item)==plan['input_hash']
    for name,hash_value in read(BASE/stage/'manifest.json')['files'].items():
        assert sha(BASE/stage/'code'/name)==hash_value
    a=item['answer'];s=item['state'];ev=item['evidence'];env=item['envelope']
    spans=review_spans(s,ev,a['claims']);c,public=packet(env,spans)
    jp={'facts':s['facts'],'experiments':s['experiments'],'decision':a['decision'],'citations':a['claims'],
        'spans':spans,'draft':env,'compact_contract':public}
    wire_schema=schema(c)
    assert 'uniqueItems' not in common.canonical(wire_schema)
    import tiktoken
    payload={'model':'gpt-4.1-mini','messages':[{'role':'system','content':PROMPT},{'role':'user','content':common.canonical(jp)}],
        'max_tokens':1600,'response_format':{'type':'json_schema','json_schema':{'name':'casepilot_judge','strict':True,'schema':wire_schema}}}
    input_tokens=len(tiktoken.get_encoding('o200k_base').encode(common.canonical(payload),disallowed_special=()))
    size=len(common.canonical(payload).encode());assert size<=45000
    reservation=((size+500)*.44+1600*1.76)*1.2/1e6
    assert reservation<=.02
    if not live:
        write(RUN/'prepared'/(stage+'.json'),{'stage':stage,'input_tokens_local':input_tokens,'request_bytes':size,
             'worst_case_reservation_usd':reservation,'request_hash':common.digest(payload),'schema':wire_schema,'packet':jp,'prompt':PROMPT})
        print(json.dumps({'stage':stage,'input_tokens':input_tokens,'reservation':reservation,'provider_requests':0}));return
    auth=read(RUN/'authorization.json');assert auth['plan_sha256']==sha(RUN/'plan.json')
    assert auth['hard_cap_usd']==.04 and auth['max_requests']==2
    prepared=read(RUN/'prepared'/(stage+'.json'));assert prepared['request_hash']==common.digest(payload)
    target=RUN/'results'/(stage+'.json');assert not target.exists()
    marker=RUN/'started'/(stage+'.json');assert not marker.exists()
    configure(auth['cumulative_cap_usd']);credentials()
    from casepilot.model import MetisClient
    client=MetisClient();client.cache=ROOT/'runtime/quality_v27/same_draft_probe'/stage/'cache';client.cache.mkdir(parents=True,exist_ok=True)
    client.diagnostics=client.cache.parent/'diagnostics'
    before=client.budget.report()['charged_or_reserved_usd']
    client.turn_scope={'calls_before':0,'cost_before':before,'max_calls':1,'cap_usd':.02,'deadline':time.monotonic()+90}
    write(marker,{'at':time.time(),'stage':stage});raw=None;checked=None;failure=None
    try:
        raw=client.structured('judge',PROMPT,jp,wire_schema,1600)
        checked=checked_semantic_review(decode(raw,c),a,ev,s,env,deterministic_findings(a,ev,s))
    except Exception as exc:failure=getattr(exc,'code',type(exc).__name__)
    finally:
        write(target,{'stage':stage,'raw_review':raw,'checked':checked,'failure':failure,'usage':client.usage_history,
              'input_hash':plan['input_hash'],'model':'gpt-4.1-mini','contract_valid':checked is not None})
        client.key='';os.environ.pop('METIS_API_KEY',None)

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['S0','S1_compatible']);p.add_argument('--live',action='store_true');args=p.parse_args()
    if args.worker:worker(args.worker,args.live);return
    plan=read(RUN/'plan.json')
    if args.live:
        auth=read(RUN/'authorization.json')
        assert auth['plan_sha256']==sha(RUN/'plan.json')
        marker=RUN/'campaign_started.json';assert not marker.exists(),'No retry'
        write(marker,{'at':time.time(),'authorization_sha256':sha(RUN/'authorization.json')})
    stop=None
    for stage in plan['variants']:
        command=[sys.executable,'-X','utf8',__file__,'--worker',stage]+(['--live'] if args.live else [])
        proc=subprocess.run(command,cwd=ROOT,stdout=subprocess.DEVNULL if args.live else None,stderr=subprocess.DEVNULL if args.live else None)
        if proc.returncode:stop='worker_failed';break
        if args.live and read(RUN/'results'/(stage+'.json'))['failure']:
            stop=read(RUN/'results'/(stage+'.json'))['failure'];break
    if args.live:
        after=ledger();before=auth['cost_before'];rows=[read(p) for p in (RUN/'results').glob('*.json')]
        result={'attempted':len(rows),'planned':2,'complete':len(rows)==2 and not stop,'stop_reason':stop,
                'contract_valid':sum(r['contract_valid'] for r in rows),'provider_requests':after['requests']-before['requests'],
                'confirmed_usd':after['confirmed_usd']-before['confirmed_usd'],
                'uncertain_reserved_usd':after['uncertain_reserved_usd']-before['uncertain_reserved_usd'],
                'charged_or_reserved_usd':after['charged_or_reserved_usd']-before['charged_or_reserved_usd'],
                'hard_cap_usd':.04,'human_review':False,'quality_success':False}
        write(RUN/'result.json',result);assert result['charged_or_reserved_usd']<=.04+1e-9 and result['provider_requests']<=2
        print(json.dumps(result))

if __name__=='__main__':main()
