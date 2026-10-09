"""Audit provenance, costs, changed files and retrieval without regenerating answers."""
import hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json,write_json,utcnow
from evaluate_quality_v22 import frozen
BASE=ROOT/'artifacts/quality_v22'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    baseline=read_json(BASE/'baseline_manifest.json'); folder=BASE/'offline_comparison_01'; plan=read_json(folder/'plan.json')
    corpus={r['id']:r for r in read_json(ROOT/'data/corpus_v2.json')}
    labels={c['id']:c.get('relevant_source_ids',[]) for c in read_json(ROOT/'eval/quality_cases.json')}
    retrieval={}; literal={}
    for variant in ('previous','revised'):
        rows=read_json(folder/(variant+'_answers.json')); at8=[]; count=0; valid=0; unknown=0
        for row in rows:
            output=row['output']
            if not output: unknown+=1; continue
            gold=set(labels.get(row['id'],[]))
            trace=next((s for s in output['pipeline'] if s['stage']=='retrieve'),{})
            if gold:
                ids={corpus[i]['source_id'] for i in trace.get('candidates',[]) if i in corpus}
                at8.append(len(gold&ids)/len(gold))
            for citation in output['summary']['sources']:
                count+=1; source=corpus.get(citation['evidence_id'])
                if source and ' '.join(citation['quote'].split()) in ' '.join(source['text'].split()): valid+=1
        retrieval[variant]={'recall_at_8':sum(at8)/len(at8) if at8 else None,'denominator_cases':len(at8),'unknown_cases':len(rows)-len(at8),'labels':'prior seen non-independent development labels'}
        literal[variant]={'numerator':valid,'denominator':count,'unknown_outputs':unknown,'semantic_support_proven':False}
    ledger=ROOT/'runtime/team_budget.sqlite3'
    with sqlite3.connect('file:'+ledger.as_posix()+'?mode=ro',uri=True) as db:
        costs=db.execute('SELECT status,charged FROM calls').fetchall()
    after={'confirmed_usd':sum(v for s,v in costs if s=='confirmed'),'reserved_usd':sum(v for s,v in costs if s!='confirmed'),
           'charged_or_reserved_usd':sum(v for _,v in costs),'requests':len(costs),'ledger_sha256':sha(ledger),'panel_observed':False}
    before=baseline['cost_before']
    changed=[]
    for name,h in baseline['baseline_files'].items():
        p=ROOT/name
        if p.exists() and sha(p)!=h: changed.append({'path':name,'before_sha256':h,'after_sha256':sha(p)})
    for folder_name in ('src','tests','schemas','scripts','docs'):
        for p in (ROOT/folder_name).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.relative_to(ROOT).as_posix() not in baseline['baseline_files']:
                changed.append({'path':p.relative_to(ROOT).as_posix(),'before_sha256':None,'after_sha256':sha(p)})
    failures=[name for name,h in baseline['historical_files'].items() if not (ROOT/name).exists() or sha(ROOT/name)!=h]
    results_preserved=all((ROOT/'artifacts'/p.name).exists() and sha(ROOT/'artifacts'/p.name)==sha(p) for p in (BASE/'baseline/results').iterdir())
    report={'at':utcnow(),'historical_changed':failures,'historical_count':len(baseline['historical_files']),
        'older_general_results_preserved':results_preserved,'evaluation_frozen_unchanged':frozen()==plan['files'],
        'cost_after':after,'new_confirmed_usd':after['confirmed_usd']-before['confirmed_usd'],
        'new_reserved_usd':after['reserved_usd']-before['reserved_usd'],'new_requests':after['requests']-before['calls'],
        'ledger_bytes_unchanged':after['ledger_sha256']==before['ledger_sha256'],'retrieval':retrieval,'literal_citation_membership':literal,
        'changed_files':changed,'git_commit_or_publish':False,'human_review':False,'live_model_evaluation':False,'site_workflow_run':False}
    write_json(BASE/'final_audit.json',report)
    print(json.dumps({k:report[k] for k in ('historical_count','historical_changed','evaluation_frozen_unchanged','new_requests','ledger_bytes_unchanged')}))
    assert not failures and results_preserved and report['evaluation_frozen_unchanged'] and report['new_requests']==0 and report['ledger_bytes_unchanged']
if __name__=='__main__': main()
