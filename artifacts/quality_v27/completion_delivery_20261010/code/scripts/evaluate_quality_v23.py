"""Seen-input extraction replay; no provider, no independent quality labels."""
import argparse,json,os,subprocess,sys,tempfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/quality_v23'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def metric(n,d,u=0):return {'numerator':n,'denominator':d,'unknown':u}
def worker(variant):
    source=BASE/'baseline/src' if variant=='previous' else ROOT/'src';sys.path.insert(0,str(source))
    import casepilot.common as common;common.ROOT=ROOT
    from casepilot.agent import extract_facts,version_observations
    from casepilot.roles import checked_extraction
    from casepilot.memory import checked_events
    from casepilot.store import Store
    packets=read(ROOT/'artifacts/quality_v22/live_comparison_01/ai_review_packets.json')['packets'];rows=[]
    with tempfile.TemporaryDirectory() as temp:
        store=Store(Path(temp)/'replay.sqlite3')
        for p in packets:
            if p['variant']!='revised':continue
            raw=next((x['raw_answer'] for x in p['raw_role_outputs'] if x['kind']=='extract' and isinstance(x.get('raw_answer'),dict) and 'facts' in x['raw_answer']),{'facts':[],'completed_checks':[],'ambiguities':[]})
            message=p['initial_report'];facts={};events=[]
            try:
                facts,_,_=checked_extraction({k:raw[k] for k in ('facts','completed_checks','ambiguities')},message)
                events=checked_events(raw.get('experiment_events',[]),message,[])
            except common.CasePilotError: facts={};events=[]
            facts.update(extract_facts(message))
            for key,values in version_observations(message).items():
                if len(values)>1:facts[key]=None
            state=store.update(p['id'],message,facts,experiment_events=events)
            rows.append({'id':p['id'],'facts':state['facts'],'experiments':state['experiments'],'version_roles':state.get('version_roles',[])})
    print(json.dumps(rows,ensure_ascii=False))
def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['previous','revised']);args=p.parse_args()
    if args.worker:worker(args.worker);return
    folder=BASE/'development_01';folder.mkdir(exist_ok=False)
    output={}
    for variant in ('previous','revised'):
        run=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__)),'--worker',variant],capture_output=True,text=True,encoding='utf-8',check=True)
        output[variant]=json.loads(run.stdout);write(folder/(variant+'_memory_replay.json'),output[variant])
    metrics={}
    for variant,rows in output.items():
        a=next(r for r in rows if r['id']=='GH16631');b=next(r for r in rows if r['id']=='GH17011')
        pairs={(next((c['value'] for c in e['conditions'] if c['dimension']=='streamlit_version'),None),e['status']) for e in b['experiments']}
        metrics[variant]={'target_current_version':metric(int(a['facts'].get('streamlit_version')=='1.61.1'),1),
            'target_compared_results':metric(sum(x in pairs for x in [('1.57.0','succeeded'),('1.58.0','failed')]),2),
            'other_version_accuracy':metric(None,0,14),
            'semantic_response_quality':metric(None,0,15)}
    improved=metrics['revised']['target_current_version']['numerator']>metrics['previous']['target_current_version']['numerator'] and metrics['revised']['target_compared_results']['numerator']>metrics['previous']['target_compared_results']['numerator']
    write(folder/'metrics.json',{'split':'development_seen','provider_requests':0,'replay_kind':'same saved extractor outputs through two actual code versions; no generator/judge inference',
        'independent':False,'human':False,'baseline_head':read(BASE/'baseline_manifest.json')['head'],'cases':15,'metrics':metrics,'targeted_improvement':improved,
        'limitations':['برچسب دو خطای شناخته‌شده را همین دستیار ساخته است؛ صحت همهٔ پرونده‌ها ارزیابی مستقل ندارد.','حفظ بخش پاسخ با کنترل رفتاری جدا سنجیده می‌شود؛ این بازپخش ادعای فایدهٔ مدل واقعی ندارد.']})
    print(json.dumps({'targeted_improvement':improved,'metrics':metrics},ensure_ascii=False))
if __name__=='__main__':main()
