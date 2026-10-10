"""Reapply only deterministic guards to recorded model selections; no new judgement."""
import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import CasePilotError,digest
from casepilot.semantics import checked_semantic_review
from evaluate_quality_v28_semantic_judge import implementation_hash,sha,read,write,RUN,DATA


def replay(phase,destination):
    cases={c['id']:c for c in read(DATA/('holdout_inputs.json' if phase=='holdout' else 'dev_inputs.json'))}
    if phase=='baseline':
        cases={c['id']:c for c in read(ROOT/'eval/quality_v28_semantic_judge/suite_v2/dev_inputs.json')}
    results=[];inputs={}
    for path in sorted((RUN/'phases'/phase).glob('[DH]*_?.json')):
        row=read(path);inputs[str(path.relative_to(ROOT))]=sha(path)
        packet=json.loads(row['payload']['messages'][1]['content'])
        semantic=deepcopy((row.get('assessment') or {}).get('semantic_result'))
        old=(row.get('assessment') or {}).get('guard')
        if not semantic:
            results.append({'id':row['id'],'old_guard':old,'new_guard':None,'status':'not_evaluated_original_contract_or_connection_failure'});continue
        aliases=packet['compact_contract']['units'];units={u['unit_id']:a for a,u in aliases.items()}
        parent={m['span_id']:m for m in packet['spans']['messages']}
        for entry in semantic['unit_reviews']:
            alias=units[entry['unit_id']]
            selected=row['raw_model_reply']['unit_reviews'][alias]['user_phrase_aliases']
            phrases=[]
            for name in selected:
                fragment=packet['compact_contract']['messages'][name]
                p=parent[fragment['span_id']]
                phrases.append({**{k:fragment[k] for k in ('span_id','message_index','start','end')},
                    'text':p['text'][fragment['start']-p['start']:fragment['end']-p['start']]})
            ordered=sorted(phrases,key=lambda p:(p['message_index'],p['start']))
            contiguous=bool(ordered) and all(a['span_id']==b['span_id'] and a['end']==b['start'] for a,b in zip(ordered,ordered[1:]))
            entry['meaning']['user_phrases']=phrases
            if contiguous:entry['meaning']['user_quote']=''.join(p['text'] for p in ordered)
        case=cases[row['id']];new=None;error=None
        try:new=checked_semantic_review(semantic,case['answer'],case['evidence'],case['state'],packet['draft'])
        except CasePilotError as exc:error=exc.code
        results.append({'id':row['id'],'raw_model_reply_sha256':digest(row['raw_model_reply']),
            'old_guard':old,'new_guard':new,'error':error,
            'new_model_contract_output':'not_evaluated','status':'guard_only_counterfactual_on_original_model_output'})
    report={'phase':phase,'implementation_hash':implementation_hash(),'input_hashes':inputs,
        'script_sha256':sha(Path(__file__)),'provider_requests':0,'cost_usd':0,'results':results,
        'limitation':'Decoded old model decisions plus exact original phrase selections; no model regeneration under the new schema, no invented judgement.'}
    write(Path(destination),report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=replay(a.phase,a.output);print('Offline guard replays',len(r['results']))
