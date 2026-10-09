"""Export actual final responses and visible inputs WITHOUT model judge scores."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
def main():
    folder=ROOT/'artifacts/architecture_v2/final_evaluation'
    cases={c['id']:c for c in read_json(folder/'frozen/eval/v2_final_cases.json')}
    rows=[json.loads(x) for x in (folder/'answers.jsonl').read_text(encoding='utf-8').splitlines() if x]
    packets=[]
    for r in rows:
        out=r['output']; c=cases[r['id']]
        packets.append({'review_id':r['split']+'/'+r['variant']+'/'+r['id'],'kind':'comparison','case_id':r['id'],
            'initial_report':c['initial_message'],'messages':[{'text':c['initial_message'],'facts':c['initial_facts'],'checks':c['initial_checks']}],
            'facts':out['summary']['facts'],'checks':out['summary']['completed_checks'],
            'response':out['response'],'next_step':out['summary']['next_step'],'rationale':out['summary']['rationale'],'hypotheses':out['summary']['hypotheses'],
            'sources':out['summary']['sources'],'validation_error':out['validation_error'],'output_sha256':digest(out)})
    for scenario in read_json(folder/'multi_turn_results.json'):
        c=cases[scenario['case_id']]; history=[{'text':c['initial_message'],'facts':c['initial_facts'],'checks':c['initial_checks']}]
        plan=next(s for s in read_json(folder/'frozen/eval/v2_final_scenarios.json') if s['id']==scenario['id'])
        additions=[{'text':t['message'],'facts':t.get('facts',{}),'checks':t.get('checks',[])} for t in plan['turns']]
        if scenario['pattern']=='edit': additions.append({'text':'توضیح تازه: پاسخ باید فقط درخواست بررسی باشد.','facts':{},'checks':[]})
        for i,out in enumerate(scenario['turns']):
            if i: history.append(additions[i-1])
            packets.append({'review_id':scenario['id']+'/'+str(i+1),'kind':'scenario','case_id':c['id'],
                'initial_report':c['initial_message'],'messages':list(history),'facts':out['summary']['facts'],
                'checks':out['summary']['completed_checks'],'response':out['response'],'next_step':out['summary']['next_step'],'rationale':out['summary']['rationale'],
                'hypotheses':out['summary']['hypotheses'],'sources':out['summary']['sources'],
                'validation_error':out['validation_error'],'output_sha256':digest(out)})
    write_json(folder/'ai_review_packets.json',packets); print('review packets',len(packets))
if __name__=='__main__': main()
