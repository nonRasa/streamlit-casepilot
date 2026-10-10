"""Offline isolated baseline comparison; no mode that can spend API credit."""
import argparse,hashlib,json,os,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/'artifacts/quality_v22'

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen():
    files=list((ROOT/'src/casepilot').glob('*.py'))+list((ROOT/'schemas').glob('*.json'))+[ROOT/'data/corpus_v2.json',Path(__file__),ROOT/'docs/QUALITY_V22_PROTOCOL_FA.md',BASE/'holdout/cases.json']
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)}

def worker(folder,variant):
    source=BASE/'baseline/src' if variant=='previous' else ROOT/'src'
    sys.path.insert(0,str(source))
    import casepilot.common as c
    c.ROOT=ROOT
    from casepilot.agent import Agent
    from casepilot.store import Store
    from casepilot.model import ReplayClient
    from casepilot.hybrid import HybridRetriever
    import casepilot.pipeline as pipeline
    assert Path(pipeline.__file__).is_relative_to(source)
    plan=read(folder/'plan.json')
    # Fixture execution has no reason to use any network.
    import socket
    def deny(*args,**kwargs): raise RuntimeError('Offline evaluation forbids network')
    socket.socket.connect=deny
    client=ReplayClient()
    hybrid=HybridRetriever(client,cache_path=ROOT/'runtime/quality_v22/fixture_vectors.sqlite3')
    store=Store(ROOT/'runtime/quality_v22'/folder.name/(variant+'.sqlite3'))
    agent=Agent(store,client=client,hybrid=hybrid); results=[]
    try:
        for case in plan['cases']:
            if frozen()!=plan['files']: raise RuntimeError('Frozen code/input changed')
            started=time.perf_counter(); output=None; error=None
            try: output=agent.turn(case['id'],case['initial_message'],'offline-'+variant,case['initial_facts'],case['initial_checks'])
            except Exception as exc: error=getattr(exc,'code',type(exc).__name__)
            results.append({'id':case['id'],'split':case['split'],'variant':variant,'output':output,'error':error,'elapsed_seconds':time.perf_counter()-started})
            write(folder/(variant+'_answers.json'),results)
    finally:
        write(folder/(variant+'_traces.json'),store.traces())
        write(folder/(variant+'_provenance.json'),{'pipeline_path':str(Path(pipeline.__file__).resolve()),'pipeline_sha256':sha(Path(pipeline.__file__)),
             'mode':'replay','provider_requests':0,'cost_usd':0,'network_disabled':True,'completed':len(results),'max_calls':pipeline.MAX_CALLS,'max_turn_usd':pipeline.MAX_TURN_USD})

SEMANTIC=['inappropriate_acceptance','false_rejection_of_useful_draft','unnecessary_escalation','necessary_escalation',
          'repeated_question_or_experiment','existing_and_missing_information','version_semantic_fit','citation_semantic_support','feature_proposal_quality']
def main(label):
    folder=BASE/label
    if folder.exists(): raise SystemExit('نتیجهٔ موجود بازنویسی نمی‌شود.')
    selection=read(BASE/'holdout/selection.json')
    if not selection['complete']: raise SystemExit('انتخاب تازه ناقص است؛ آزمون نهایی اجرا نشد.')
    dev=read(ROOT/'eval/quality_cases.json'); fresh=read(BASE/'holdout/cases.json')
    def visible(case,split): return {k:case.get(k,{} if k=='initial_facts' else [] if k=='initial_checks' else '') for k in ('id','initial_message','initial_facts','initial_checks')}|{'split':split}
    cases=[visible(c,'development_seen') for c in dev]+[visible(c,'unseen_replay_only') for c in fresh]
    plan={'at':time.time(),'mode':'replay','cases':cases,'files':frozen(),'input_sha256':hashlib.sha256(json.dumps(cases,sort_keys=True).encode()).hexdigest(),
          'baseline_manifest_sha256':sha(BASE/'baseline_manifest.json'),'protocol_sha256':sha(ROOT/'docs/QUALITY_V22_PROTOCOL_FA.md'),
          'limits':{'max_calls':8,'max_turn_usd':.04,'deadline_seconds':180,'repairs':1},'paid_budget_usd':0,'no_regeneration':True}
    write(folder/'plan.json',plan)
    for variant in ('previous','revised'):
        proc=subprocess.run([sys.executable,__file__,'--worker',variant,'--folder',str(folder)],cwd=ROOT,capture_output=True,text=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        (folder/(variant+'_worker.log')).write_text(proc.stdout+proc.stderr,encoding='utf-8')
        if proc.returncode: write(folder/'worker_failure.json',{'variant':variant,'returncode':proc.returncode}); break
    results={v:read(folder/(v+'_answers.json')) if (folder/(v+'_answers.json')).exists() else [] for v in ('previous','revised')}
    summary={}
    labels={c['id']:c.get('relevant_source_ids',[]) for c in dev}
    for variant,rows in results.items():
        for split in ('development_seen','unseen_replay_only'):
            group=[r for r in rows if r['split']==split]; outputs=[r['output'] for r in group if r['output']]
            recalls=[]
            for r in group:
                gold=labels.get(r['id']); out=r['output']
                if gold and out: recalls.append(len(set(gold)&{s['source_id'] for s in out['retrieved'][:5]})/len(set(gold)))
            summary[variant+':'+split]={'attempted':len(group),'delivered':len(outputs),'expected':sum(c['split']==split for c in cases),
                'decisions':{d:sum(o['decision']==d for o in outputs) for d in ('ask','answer','escalate')},
                'validation_errors':{str(code):sum(o['validation_error']==code for o in outputs) for code in {o['validation_error'] for o in outputs}},
                'median_latency_seconds':statistics.median(r['elapsed_seconds'] for r in group) if group else None,
                'fixture_calls':sum(o['model_calls'] for o in outputs),'provider_requests':0,'confirmed_usd':0,'reserved_usd':0,
                'retrieval_recall_at_5':{'value':statistics.mean(recalls) if recalls else None,'denominator_cases':len(recalls),'unknown':len(group)-len(recalls),'label_source':'prior non-independent development annotations'},
                'semantic_metrics':{m:{'numerator':None,'denominator':0,'unknown':len(group),'value':None} for m in SEMANTIC},
                'actionable_handoff_structure':{'numerator':sum(bool(o['summary'].get('handoff')) for o in outputs if o['decision']=='escalate'),
                    'denominator':sum(o['decision']=='escalate' for o in outputs),'meaning_reviewed':False}}
    write(folder/'metrics.json',{'mode':'replay','frozen_unchanged':frozen()==plan['files'],'summary':summary,
          'live_model_evaluation':False,'human_review':False,'independent_review':False,'site_workflow_run':False,
          'limitation':'Fixture behavior and lexical source labels are not semantic response accuracy. Unknown semantic metrics are not zero errors.'})
    # Preserve a blank independent-review form; no generated labels disguised as human judgement.
    import csv
    with (folder/'human_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['case_id','variant','response_sha256']+SEMANTIC+['reason','reviewer'])
        for variant,rows in results.items():
            for r in rows:
                if r['output']: w.writerow([r['id'],variant,hashlib.sha256(r['output']['response'].encode()).hexdigest()]+['']*(len(SEMANTIC)+2))
    print(json.dumps({'comparisons':sum(len(r) for r in results.values()),'paid_requests':0,'frozen_unchanged':frozen()==plan['files']}))
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--label',default='offline_comparison_01'); p.add_argument('--worker',choices=['previous','revised']); p.add_argument('--folder',type=Path); a=p.parse_args()
    if a.worker: worker(a.folder,a.worker)
    else: main(a.label)
