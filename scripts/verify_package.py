"""Verify data isolation, hashes, notebook cells, workflow graph and artifact honesty."""
import ast, hashlib, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from check_mapbox_tokens import scan

def main():
    checks=[]
    def check(name,condition):
        checks.append({'check':name,'passed':bool(condition)})
        if not condition: print('FAILED',name)
    check('no Mapbox tokens in deliverable text',not scan(ROOT,include_archives=False))
    manifest=read_json(ROOT/'data'/'snapshot_manifest.json'); cases=read_json(ROOT/'eval'/'cases.json'); corpus=read_json(ROOT/'data'/'corpus.json')
    for name,h in manifest['files'].items(): check('sha256 '+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h)
    check('30 cases / 15 dev / 15 test',len(cases)==30 and sum(c['split']=='dev' for c in cases)==15 and sum(c['split']=='test' for c in cases)==15)
    excluded=set(manifest['excluded_issue_families'])
    check('no heldout issue in index',not ({c.get('issue_number') for c in corpus}&excluded))
    leaks=[(c['id'],n) for c in corpus for n in excluded if re.search(r'(?:#|issues/|pull/)'+str(n)+r'\b',c['text'])]
    check('no direct heldout reference in index',not leaks)
    check('no generated placeholder evidence',not any('<Autofunction' in c['text'] for c in corpus))
    ids={c['source_id'] for c in corpus}; check('qrels have allowed sources',all(set(c['relevant_source_ids'])<=ids for c in cases))
    scenario=read_json(ROOT/'eval'/'scenarios.json'); case_map={c['id']:c for c in cases}
    check('10 multi-turn / half test',len(scenario)==10 and sum(s['split']=='test' for s in scenario)==5)
    check('scenario split matches source case',all(s['case_id'] in case_map and case_map[s['case_id']]['split']==s['split'] for s in scenario))
    frozen=read_json(ROOT/'eval'/'freeze_manifest.json')
    for name,h in frozen['code_sha256'].items(): check('frozen '+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h)
    check('fresh test selected after freeze',{c['issue_number'] for c in cases if c['split']=='test'}==set(frozen['new_test_issue_numbers']))
    nb=read_json(ROOT/'CasePilot_project.ipynb')
    for i,cell in enumerate(nb['cells']):
        if cell['cell_type']=='code': ast.parse(''.join(cell['source'])); check(f'notebook cell {i} parses',True)
    check('notebook has no error output',not any(o.get('output_type')=='error' for c in nb['cells'] for o in c.get('outputs',[])))
    execution=ROOT/'artifacts'/'notebook_execution.json'
    check('notebook execution completed offline',execution.exists() and read_json(execution)['passed'] and read_json(execution)['executed_cells']==8 and not read_json(execution)['live_enabled'])
    tests=read_json(ROOT/'artifacts'/'test_results.json')
    check('local test suite passed',tests['passed'] and tests['tests']>0 and tests['errors']==0 and tests['failures']==0)
    check('measured report exists',(ROOT/'report.md').is_file())
    wf=read_json(ROOT/'workflows'/'casepilot_main.json'); names={n['name'] for n in wf['nodes']}
    check('workflow 12 nodes / inactive',len(names)==12 and wf['active'] is False)
    check('workflow valid connections',all(c['node'] in names for out in wf['connections'].values() for group in out['main'] for c in group))
    check('all webhook paths authenticated',all(n['parameters'].get('authentication')=='headerAuth' for n in wf['nodes'] if n['type'].endswith('.webhook')))
    check('no automatic review from turn',wf['connections']['Turn Python API']['main'][0][0]['node']=='Turn Response')
    check('no embedded credential values',not any(re.search(r'Bearer\s+[A-Za-z0-9_-]{20,}',canonical(n)) for n in wf['nodes']))
    issues=read_json(ROOT/'data'/'issues_snapshot.json')
    check('Python decorators preserved',any('@st.cache_data' in (r['body'] or '') for r in issues))
    for split in ('dev','test'):
        p=ROOT/'artifacts'/'offline'/split/'evaluation_metrics.json'
        if p.exists():
            result=read_json(p); check('offline marked replay '+split,result['mode']=='replay' and result['cost']['requests']==0 and not result['provider_execution'])
            check('complete offline evaluation '+split,result['complete'] and result['selected_cases']==15 and result['scenarios']=={'n':5,'passed':5})
    write_json(ROOT/'artifacts'/'package_verification.json',{'at':utcnow(),'passed':all(c['passed'] for c in checks),'checks':checks})
    print('checks',len(checks),'passed',sum(c['passed'] for c in checks))
    return all(c['passed'] for c in checks)

if __name__=='__main__': sys.exit(0 if main() else 1)
