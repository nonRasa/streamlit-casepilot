"""راستی‌آزمایی رایگان تحویل؛ بدون استنتاج، تأیید رهگیر یا تغییر دفتر هزینه."""
import hashlib,json,math,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import evaluate_quality_v25_live as live
from check_deliverable_secrets import scan

def main():
    base=ROOT/'artifacts/quality_v25';folder=live.FOLDER
    start=live.read(base/'baseline_manifest.json');plan=live.read(folder/'comparison_plan.json');manifest=live.read(folder/'manifest.json')
    rows=[live.read(p) for p in sorted((folder/'turns').glob('*.json'))]
    current=live.ledger();auth=live.read(folder/'authorization_plan.json');ids={u['ledger_id'] for r in rows for u in r['usage'] if u.get('mode')=='live' and 'ledger_id' in u}
    added=[r for r in current['calls'] if r['id'] in ids];before={r['id']:r for r in plan['cost_before']['calls']}
    secrets=scan(False)
    traces=[e for v in ('previous','revised') for e in live.read(folder/(v+'_traces.json'))]
    checks={
        'start_copy_matches':all(live.sha(base/'baseline'/name)==sha for name,sha in start['files'].items()),
        'historical_files_unchanged':all(live.sha(ROOT/name)==sha for name,sha in start['historical_files'].items()),
        'evaluated_source_copy_matches':all(live.sha(base/'evaluated'/name)==sha for name,sha in auth['production_files'].items()),
        'frozen_comparison_files_unchanged':live.frozen()==plan['files'],
        'all_offline_tests_passed':live.read(base/'final_offline_tests/test_results.json')['passed'],
        'meaningful_offline_gate_passed':live.read(base/'offline_comparison_02/offline_metrics.json')['live_gate_passed'],
        'stopped_after_first_pair':len(rows)==2 and manifest['stop_reason']=='provider_or_limit_failed_stop_after_current_pair' and len(manifest['not_started'])==2,
        'no_unplanned_or_repeated_turns':len(list((folder/'started').glob('*.json')))==len(rows),
        'new_calls_match_ledger':len(added)==manifest['new_requests'] and math.isclose(sum(r['charged'] for r in added),manifest['new_charged_or_reserved_usd'],abs_tol=1e-10),
        'no_new_uncertain_reserve':all(r['status']=='confirmed' for r in added),
        'previous_reservations_preserved':all(r==before[r['id']] for r in current['calls'] if r['id'] in before),
        'no_requests_after_stop':current['requests']==manifest['cost_after']['requests'],
        'same_stage_and_team_caps_respected':current['charged_or_reserved_usd']<=2.004717190<=5,
        'turn_limits_preserved':all(o['model_calls']<=8 and o['repair_count']<=1 and r['elapsed_seconds']<=180 and o['usage']['charged_or_reserved_usd']<=.04 for r in rows if (o:=r['output'])),
        'no_tracker_approval_or_execution':not any(any(word in e['kind'] for word in ('approve','execute','commit')) for e in traces),
        'no_new_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==start['git_head'],
        'no_credentials_in_delivery':not secrets,
    }
    result={'passed':all(checks.values()),'checks':checks,'provider_requests':0,'human_review':False,'independent':False,
        'live_complete':False,'paired_cases':1,'feature_live_evaluation':False,'panel_balance_observed':False,
        'secret_scan_findings':secrets,'reports':{name:live.sha(ROOT/name) for name in ('README.md','docs/QUALITY_V25_FA.md','docs/QUALITY_V25_PROTOCOL_FA.md')},
        'production_files':auth['production_files'],'cost_after':{k:current[k] for k in ('requests','confirmed_usd','uncertain_reserved_usd','charged_or_reserved_usd')}}
    target=base/'verification.json'
    if target.exists():raise SystemExit('توقف: راستی‌آزمایی موجود بازنویسی نمی‌شود.')
    live.write(target,result)
    print(json.dumps({'passed':result['passed'],'checks':checks,'secret_findings':len(secrets)},ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
