"""Verify data isolation, hashes, notebook cells, workflow graph and artifact honesty."""
import ast, csv, hashlib, json, re, sys
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
    for name,h in frozen['code_sha256'].items():
        historical=ROOT/'artifacts/architecture_v1/frozen'/name
        check('historical V1 frozen '+name,hashlib.sha256((historical if historical.exists() else ROOT/name).read_bytes()).hexdigest()==h)
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
    check('workflow 13 nodes / inactive',len(names)==13 and wf['active'] is False)
    check('workflow valid connections',all(c['node'] in names for out in wf['connections'].values() for group in out['main'] for c in group))
    check('all webhook paths authenticated',all(n['parameters'].get('authentication')=='headerAuth' for n in wf['nodes'] if n['type'].endswith('.webhook')))
    check('no automatic human approval from turn',wf['connections']['Turn Python API']['main'][0][0]['node']=='Turn Pipeline Contract' and wf['connections']['Turn Pipeline Contract']['main'][0][0]['node']=='Turn Response')
    v2=read_json(ROOT/'data/corpus_v2.json'); v2manifest=read_json(ROOT/'data/index_v2_manifest.json')
    check('V2 corpus hash',hashlib.sha256((ROOT/'data/corpus_v2.json').read_bytes()).hexdigest()==v2manifest['corpus_sha256'])
    check('V2 source allowlist',set(r['source_id'] for r in v2)<=set(r['source_id'] for r in corpus))
    check('V2 heldout families excluded',not {r.get('issue_number') for r in v2}&excluded)
    check('V2 heldout references excluded',not any(re.search(r'(?:#|issues/|pull/)'+str(n)+r'\b',r['text']) for r in v2 for n in excluded))
    check('V2 rubric and bounds',read_json(ROOT/'policies/judge_rubric.json')['can_approve_or_execute'] is False and read_json(ROOT/'policies/execution_policy.json')['max_model_calls_per_turn']==8)
    check('V2 saved-output audit passed',read_json(ROOT/'artifacts/architecture_v2/verification.json')['passed'])
    check('V2 workflow contracts passed',read_json(ROOT/'artifacts/architecture_v2/workflow_verification.json')['passed'])
    final_folder=ROOT/'artifacts/architecture_v2/final_evaluation'
    if (final_folder/'manifest.json').exists():
        final=read_json(final_folder/'manifest.json'); audit=read_json(final_folder/'verification.json')
        ai=read_json(final_folder/'ai_review_manifest.json'); review=read_json(final_folder/'ai_review.json')
        packets=read_json(final_folder/'ai_review_packets.json'); scenario2=read_json(final_folder/'multi_turn_results.json')
        check('V2 final complete and audit passed',final['complete'] and audit['passed'] and final['configuration_unchanged'])
        check('V2 final frozen files still match',all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in final['configuration']['files'].items()))
        check('V2 final source answers unchanged',hashlib.sha256((final_folder/'answers.jsonl').read_bytes()).hexdigest()==ai['source_answers_sha256']==audit['answers_sha256'])
        check('V2 final source scenarios unchanged',hashlib.sha256((final_folder/'multi_turn_results.json').read_bytes()).hexdigest()==ai['source_scenarios_sha256']==audit['scenario_answers_sha256'])
        check('V2 final honest scenario count',len(scenario2)==10 and final['scenarios']['passed']==sum(s['passed'] for s in scenario2))
        check('V2 final authored AI review complete',ai['completed'] and ai['rows']==len(review)==len(packets)==83 and ai['comparison_rows']==60 and ai['scenario_rows']==23)
        check('V2 final AI review hash',hashlib.sha256((final_folder/'ai_review.json').read_bytes()).hexdigest()==ai['review_sha256'])
        check('V2 final AI CSV hash',hashlib.sha256((final_folder/'ai_review.csv').read_bytes()).hexdigest()==ai['review_csv_sha256'])
        check('V2 final review packet hash',hashlib.sha256((final_folder/'ai_review_packets.json').read_bytes()).hexdigest()==ai['packets_sha256'])
        check('V2 final review provenance',{r['review_id']:r['output_sha256'] for r in review}=={p['review_id']:p['output_sha256'] for p in packets})
        check('V2 final AI not claimed human',ai['independent_human_review'] is False and ai['additional_metis_requests']==0)
        with (final_folder/'human_review.csv').open(encoding='utf-8-sig',newline='') as f: human=list(csv.DictReader(f))
        hm=read_json(final_folder/'human_review_manifest.json')
        check('V2 final human form hash',hashlib.sha256((final_folder/'human_review.csv').read_bytes()).hexdigest()==hm['form_sha256'] and hm['human_review_pending'])
        check('V2 final human form blank distinct rows',len(human)==60 and len({r['review_id'] for r in human})==60 and all(not value for r in human for k,value in r.items() if k.startswith('human_') or k in ('reviewer','notes')))
        check('V2 final budget respected',final['new_charged_or_reserved_usd']<=.90 and final['cost_cumulative']['charged_or_reserved_usd']<=5)
        check('V2 final report and findings included',(ROOT/'docs/V2_FINAL_EVALUATION_FA.md').is_file() and (ROOT/'docs/V2_FINAL_FINDINGS_FA.md').is_file())
    check('materialized quote schema matches validator',read_json(ROOT/'schemas/answer.schema.json')['properties']['claims']['items']['required']==['evidence_id','quote'])
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
