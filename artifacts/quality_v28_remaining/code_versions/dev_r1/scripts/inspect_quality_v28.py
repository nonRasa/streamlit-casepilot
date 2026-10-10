"""Offline reconstruction of actual rejected V27 drafts/context, without APIs."""
import sys,json,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest
from casepilot.context_pack import pack_evidence
from casepilot.store import Store
from complete_quality_v27 import read_retrieval
from prepare_quality_v28 import RUN
from evaluate_quality_v25_live import sha

OLD=ROOT/'artifacts/quality_v27/completion_20261010'
def ledger_id(usage):
    if usage.get('ledger_id'):return usage['ledger_id']
    return ledger_id(usage['original_usage']) if isinstance(usage.get('original_usage'),dict) else None

def main():
    target=RUN/'forensics';target.mkdir(exist_ok=True)
    cache={}
    for p in (ROOT/'runtime/quality_v27/completion_20261010/cache').glob('*.json'):
        r=read_json(p);key=ledger_id(r['usage'])
        if key:cache[key]={'raw':r['raw_answer'],'cache_sha256':sha(p),'usage':r['usage']}
    inventory=[];bundles=[]
    for folder,stage in (('answers','initial'),('answer_repeats','development_fix')):
        for p in sorted((OLD/folder).glob('*.json')):
            row=read_json(p);out=row.get('output') or {};error=row['failure'] or out.get('validation_error')
            uid=stage+'_'+p.stem
            inv={'run':uid,'file':str(p.relative_to(ROOT)),'sha256':sha(p),'id':row['id'],'variant':row['variant'],
                'error':error,'technical_failure':error not in (None,'judge_rejected','unsupported_answer','deterministic_review_failed'),
                'content_rejected':error in ('judge_rejected','unsupported_answer','deterministic_review_failed'),
                'actual_agent_turn':bool(out),'reviewed_units':len((out.get('reviewed_draft') or {}).get('units',[]))}
            inventory.append(inv)
            if not out:continue
            db=ROOT/('runtime/quality_v27/completion_20261010/'+('repeat_' if stage=='development_fix' else '')+p.stem+'.sqlite3')
            state=Store(db).get(row['id']) if db.exists() else None
            retrieval=read_retrieval(row['id']);candidates=retrieval['variants'][row['variant']]['candidates']
            ranking=next((s for s in out['pipeline'] if s['stage']=='rerank'),None)
            chosen=[r for i in (ranking or {}).get('ids',[]) for r in candidates if r['id']==i]
            packet,packing=pack_evidence(chosen,max_tokens=3000,expand_parent=row['variant']=='C')
            observed=next((s for s in out['pipeline'] if s['stage']=='context_pack'),None)
            exact=bool(observed and observed['ids']==[r['id'] for r in packet] and observed['used_tokens']==packing['used_tokens'])
            if observed:assert exact,'Context reconstruction differs: '+uid
            roles=[]
            for usage in row['usage']:
                rid=ledger_id(usage);saved=cache.get(rid)
                roles.append({'role':usage.get('kind'),'ledger_id':rid,'raw_reply':saved['raw'] if saved else None,
                    'cache_sha256':saved['cache_sha256'] if saved else None,'usage':usage,'missing_raw_reply':saved is None})
            # Preserve every checked review, including pre-repair ones; the final
            # envelope may belong to a different generation.
            reviews=[s for s in out['pipeline'] if s['stage']=='judge']
            bundle={'run':uid,'origin':'Assistant offline reconstruction; not human or independent review',
                'input_state':state,'full_user_report':'\n\n'.join(m['text'] for m in state['messages']) if state else None,
                'actual_context':packet,'context_reconstruction_verified':exact,'context_was_reached':bool(observed),
                'initial_candidates':candidates,'selection':ranking,'raw_role_replies':roles,'checked_reviews':reviews,
                'reviewed_draft':out.get('reviewed_draft'),'final_response':out.get('response'),
                'final_error':error,'outcome':out.get('outcome'),'review_failures':out.get('review_failures'),
                'original_artifact':inv['file'],'original_artifact_sha256':inv['sha256']}
            write_json(target/(uid+'.json'),bundle);bundles.append(bundle)
    historical=[]
    for p in sorted((ROOT/'artifacts/quality_v27/contract_live_01/turns').glob('*.json')):
        r=read_json(p);o=r.get('output') or {};historical.append({'file':str(p.relative_to(ROOT)),'sha256':sha(p),
            'stage':r['stage'],'error':r['failure'] or o.get('validation_error'),'actual_agent_turn':bool(o)})
    for p in sorted((ROOT/'artifacts/quality_v27').rglob('*.json')):
        if 'code' in p.parts or 'code_versions' in p.parts:continue
        if p.parent.name=='judge' and p.name.startswith('attempt_') or 'same_draft_probe' in p.parts and p.parent.name=='results':
            r=read_json(p);historical.append({'file':str(p.relative_to(ROOT)),'sha256':sha(p),'kind':'stored_draft_judge',
                'contract_valid':r.get('contract_valid'),'error':r.get('failure')})
    selected=['development_fix_D01_A','initial_H03_A','initial_D03_A','development_fix_D03_A','initial_H02_C','initial_H09_A','initial_H09_B']
    write_json(target/'inventory.json',{'completion_runs':inventory,'earlier_v27_runs_and_probes':historical,
        'counts':dict(collections.Counter(x['error'] for x in inventory)),'selected_deep_review':selected,'provider_requests':0})
    write_json(target/'human_review.json',[{'alias':'review_'+digest(b['run'])[:12],
        'report':b['full_user_report'],'context':b['actual_context'],'draft':b['reviewed_draft'],
        'reason_for_review':'Separate a harmless request/procedural diagnostic from a hidden technical assertion; check witness relevance and novelty against full report.',
        'unsupported_claims':None,'repeated_check':None,'route_fit':None,'usefulness_0_to_3':None,'judge_false_positive_or_negative':None,'reviewer_origin':None}
        for b in bundles if b['run'] in selected])
    text=[]
    for b in bundles:
        if b['run'] not in selected:continue
        text+=['\nRUN '+b['run'],'REPORT '+str(b['full_user_report']),'SELECTION '+str((b['selection'] or {}).get('ids',[])),
            'DRAFT '+json.dumps(b['reviewed_draft'],ensure_ascii=False),
            'CHECKED '+json.dumps([{k:s.get(k) for k in ('attempt','verdict','assessments','findings','unit_reviews','meanings','unit_results')} for s in b['checked_reviews']],ensure_ascii=False)]
    (target/'selected_inspection.txt').write_text('\n'.join(text),encoding='utf8')
    print(json.dumps({'runs':len(inventory),'earlier_runs_or_probes':len(historical),'deep_review':len(selected),'counts':dict(collections.Counter(x['error'] for x in inventory)),'provider_requests':0}))

if __name__=='__main__':main()
