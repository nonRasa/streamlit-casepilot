"""Export actual final outputs without variant labels or runtime judge scores."""
import hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from quality_result_files import result_paths

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation'
    cases={c['id']:c for c in read_json(ROOT/'eval/quality_cases.json')}; packets=[]; mapping=[]
    def add(key,cid,out,kind,messages):
        rid=hashlib.sha256(('quality-review-v1:'+key).encode()).hexdigest()[:12]
        packets.append({'review_id':rid,'case_id':cid,'kind':kind,'initial_report':cases[cid]['initial_message'],
            'messages':messages,'facts':out['summary']['facts'] if out else {},'checks':out['summary']['completed_checks'] if out else [],
            'response':out['response'] if out else None,'next_step':out['summary']['next_step'] if out else None,
            'rationale':out['summary']['rationale'] if out else None,'hypotheses':out['summary']['hypotheses'] if out else [],
            'sources':out['summary']['sources'] if out else [],'output_sha256':digest(out)})
        mapping.append({'review_id':rid,'source_key':key,'output_sha256':digest(out)})
    for r in read_json(folder/'answers.json'):
        add(r['split']+'/'+r['variant']+'/'+r['id'],r['id'],r['output'],'comparison',[])
    for s in read_json(result_paths(folder)[1]):
        messages=[]
        for i,out in enumerate(s['turns']):
            if i>0:
                if i<=len(s['turns']) and i-1<len(next(x for x in read_json(ROOT/'eval/quality_scenarios.json') if x['id']==s['id'])['turns']):
                    original=next(x for x in read_json(ROOT/'eval/quality_scenarios.json') if x['id']==s['id'])['turns'][i-1]
                    messages.append(original)
                else: messages.append({'message':'توضیح تازه: پاسخ باید فقط درخواست بررسی باشد.'})
            add(s['id']+'/'+str(i+1),s['case_id'],out,'scenario',list(messages))
    write_json(folder/'ai_review_packets.json',sorted(packets,key=lambda x:x['review_id']))
    write_json(folder/'ai_review_assignment.json',mapping)
    print('Packets exported',len(packets))
if __name__=='__main__': main()
