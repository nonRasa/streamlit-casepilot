"""Authorized $0.80 paired live campaign; secrets only in process memory.

Preflight never calls a provider. Results are append-only at campaign level:
an existing campaign cannot be restarted, retried, or overwritten.
"""
import argparse
from contextlib import closing
import csv
import getpass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/quality_v22'
FOLDER = BASE / 'live_comparison_01'
LEDGER = ROOT / 'runtime/team_budget.sqlite3'
ADDITIONAL_CAP = .80


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ledger():
    # Read-only preflight must not create or change the shared ledger.
    with closing(sqlite3.connect(LEDGER.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('SELECT * FROM calls ORDER BY at,id')]
    return {'requests': len(rows), 'confirmed_usd': sum(r['charged'] for r in rows if r['status'] == 'confirmed'),
            'uncertain_reserved_usd': sum(r['charged'] for r in rows if r['status'] != 'confirmed'),
            'charged_or_reserved_usd': sum(r['charged'] for r in rows), 'calls': rows}


def frozen():
    original = read(BASE / 'offline_comparison_01/plan.json')['files']
    baseline = read(BASE / 'baseline_manifest.json')['baseline_files']
    paths = [ROOT / name for name in original]
    paths += [BASE / 'baseline' / name for name in baseline]
    paths += [Path(__file__), ROOT / 'docs/QUALITY_V22_LIVE_PROTOCOL_FA.md',
              ROOT / 'data/index_v2_manifest.json', BASE / 'holdout/selection.json',
              ROOT / 'policies/execution_policy.json']
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(paths))}


def preflight():
    original = read(BASE / 'offline_comparison_01/plan.json')['files']
    assert all(sha(ROOT / name) == digest for name, digest in original.items()), 'Frozen revised files changed'
    baseline = read(BASE / 'baseline_manifest.json')['baseline_files']
    assert all(sha(BASE / 'baseline' / name) == digest for name, digest in baseline.items()), 'Frozen baseline changed'
    assert read(BASE / 'holdout/selection.json')['complete'], 'Incomplete holdout'
    cases = read(BASE / 'holdout/cases.json')
    assert len(cases) == 15 and len({c['id'] for c in cases}) == 15
    assert not FOLDER.exists(), 'Existing campaign cannot be retried or overwritten'
    assert not (ROOT / 'runtime/quality_v22/live_comparison_01').exists(), 'Existing campaign memory cannot be reused'
    before = ledger()
    assert before['charged_or_reserved_usd'] + ADDITIONAL_CAP <= 5, 'Team ceiling exceeded'
    # Load all existing corpus embeddings while forbidding every network call.
    sys.path.insert(0, str(ROOT / 'src'))
    import socket
    from unittest.mock import patch
    from casepilot.model import MetisClient
    from casepilot.hybrid import HybridRetriever
    old_env = os.environ.copy()
    try:
        os.environ.update(METIS_API_KEY='preflight-only', METIS_MODEL='gpt-4.1-mini',
                          METIS_EMBEDDING_MODEL='text-embedding-3-small',
                          CASEPILOT_INPUT_USD_PER_MILLION='1', CASEPILOT_OUTPUT_USD_PER_MILLION='1',
                          CASEPILOT_EMBEDDING_USD_PER_MILLION='1',
                          CASEPILOT_BUDGET_DB=str(LEDGER))
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('Network forbidden during preflight')):
            client = MetisClient()
            hybrid = HybridRetriever(client)
            vectors = hybrid.load_vectors()
            assert len(vectors) == len(hybrid.chunks) and client.calls == 0
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    assert ledger() == before, 'Preflight changed costs'
    return {'passed': True, 'cases': len(cases), 'paired_outputs_planned': 30, 'provider_requests': 0,
            'additional_cap_usd': ADDITIONAL_CAP, 'frozen_unchanged': True, 'index_ready': True,
            'credential_available': bool(os.getenv('METIS_API_KEY')), 'cost_before': before,
            'files': frozen()}


def pair_fits(total, cap):
    # Preserve enough room for BOTH turns at their existing four-cent limit.
    return total + 2 * .04 <= cap + 1e-12


def configuration(pricing, cap):
    chat, embed = pricing['chat'], pricing['embedding']
    return dict(METIS_BASE_URL='https://api.metisai.ir/openai/v1',
        METIS_MODEL='gpt-4.1-mini', METIS_JUDGE_MODEL='gpt-4.1-mini',
        METIS_EMBEDDING_MODEL='text-embedding-3-small',
        CASEPILOT_INPUT_USD_PER_MILLION=str(chat['inputTokenUnitIncome'] * 1e6),
        CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['outputTokenUnitIncome'] * 1e6),
        CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['inputTokenUnitIncome'] * 1e6),
        CASEPILOT_MAX_OUTPUT_TOKENS='1600', CASEPILOT_BUDGET_USD=str(cap),
        CASEPILOT_BUDGET_DB=str(LEDGER), PYTHONIOENCODING='utf-8')


def worker(variant, case_id):
    plan = read(FOLDER / 'plan.json')
    assert frozen() == plan['files'], 'Frozen files changed'
    source = BASE / 'baseline/src' if variant == 'previous' else ROOT / 'src'
    sys.path.insert(0, str(source))
    import casepilot.common as common
    common.ROOT = ROOT
    from casepilot.agent import Agent
    from casepilot.store import Store
    from casepilot.model import MetisClient
    from casepilot.hybrid import HybridRetriever
    import casepilot.pipeline as pipeline
    assert Path(pipeline.__file__).is_relative_to(source)
    assert pipeline.MAX_CALLS == 8 and pipeline.MAX_TURN_USD == .04
    path = FOLDER / 'turns' / (case_id + '_' + variant + '.json')
    intent = FOLDER / 'started' / (case_id + '_' + variant + '.json')
    assert not path.exists() and not intent.exists(), 'A turn cannot be retried'
    case = next(c for c in plan['cases'] if c['id'] == case_id)
    os.environ.update(configuration(plan['pricing'], plan['cumulative_cap_usd']))
    client = MetisClient()
    client.budget.cap = plan['cumulative_cap_usd']
    store = Store(ROOT / 'runtime/quality_v22/live_comparison_01' / (variant + '.sqlite3'))
    agent = Agent(store, client=client, hybrid=HybridRetriever(client))
    started = time.perf_counter()
    output = None
    failure = None
    write(intent, {'id': case_id, 'variant': variant, 'at': time.time(), 'no_retry': True})
    try:
        output = agent.turn(case_id, case['initial_message'], 'live-v22-' + variant,
                            case['initial_facts'], case['initial_checks'])
    except Exception as exc:
        # Never serialize exception messages, environment, headers or keys.
        failure = getattr(exc, 'code', type(exc).__name__)
    finally:
        row = {'id': case_id, 'variant': variant, 'split': 'first_live_after_replay',
               'output': output, 'failure': failure, 'elapsed_seconds': time.perf_counter() - started,
               'usage': client.usage_history, 'pipeline_sha256': sha(Path(pipeline.__file__)),
               'pipeline_path': str(Path(pipeline.__file__).resolve())}
        write(path, row)
        write(FOLDER / (variant + '_traces.json'), store.traces())
        client.key = ''


def summarize(plan, stop_reason):
    after = ledger()
    rows = [read(p) for p in sorted((FOLDER / 'turns').glob('*.json'))]
    expected = [(c['id'], v) for c in plan['cases'] for v in ('previous', 'revised')]
    attempted = {(r['id'], r['variant']) for r in rows}
    summary = {}
    for variant in ('previous', 'revised'):
        group = [r for r in rows if r['variant'] == variant]
        outputs = [r['output'] for r in group if r['output']]
        write(FOLDER / (variant + '_answers.json'), group)
        summary[variant] = {'attempted': len(group), 'delivered': len(outputs),
            'decisions': {d: sum(o['decision'] == d for o in outputs) for d in ('ask', 'answer', 'escalate')},
            'validation_errors': {str(e): sum(o['validation_error'] == e for o in outputs)
                                  for e in {o['validation_error'] for o in outputs}},
            'failed_turns': sum(bool(r['failure']) for r in group),
            'cache_hits': sum(u.get('mode') == 'cached_live' for r in group for u in r['usage']),
            'provider_requests': sum(u.get('provider_requests', 0) for r in group for u in r['usage']),
            'semantic_review': {'reviewed': 0, 'unknown': len(group), 'independent': False}}
    before = plan['cost_before']
    manifest = {'complete': len(rows) == 30 and not stop_reason, 'stop_reason': stop_reason,
        'attempted': len(rows), 'paired_cases': sum(all((c['id'], v) in attempted for v in ('previous', 'revised')) for c in plan['cases']),
        'not_started': [{'id': i, 'variant': v} for i, v in expected if (i, v) not in attempted],
        'new_requests': after['requests'] - before['requests'],
        'new_confirmed_usd': after['confirmed_usd'] - before['confirmed_usd'],
        'new_uncertain_reserved_usd': after['uncertain_reserved_usd'] - before['uncertain_reserved_usd'],
        'new_charged_or_reserved_usd': after['charged_or_reserved_usd'] - before['charged_or_reserved_usd'],
        'additional_cap_usd': ADDITIONAL_CAP, 'cost_after': after, 'summary': summary,
        'frozen_unchanged': frozen() == plan['files'], 'human_review': False, 'independent_review': False,
        'site_workflow_run': False, 'panel_balance_observed': False,
        'limitations': ['Initial reports only; no gold semantic labels. Unknown metrics are not zero errors.',
          'Same model and generator token ceiling; role prompts and internal token allocations differ by frozen implementation.',
          'Existing cache is shared; cache hits and new provider requests are reported separately.',
          'Attempted pairs include failures; useful answers and successful processing require separate review.',
          'Budget may truncate the fixed-order set; subset results do not establish quality over all fifteen cases.']}
    write(FOLDER / 'manifest.json', manifest)
    with (FOLDER / 'human_review.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['case_id', 'variant', 'response_sha256', 'utility', 'unnecessary_escalation',
                    'repeated_question_or_experiment', 'version_fit', 'citation_support', 'reason', 'reviewer'])
        for r in rows:
            if r['output']:
                w.writerow([r['id'], r['variant'], hashlib.sha256(r['output']['response'].encode()).hexdigest()] + [''] * 7)
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--live', action='store_true')
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--worker', choices=['previous', 'revised'])
    p.add_argument('--case')
    args = p.parse_args()
    if args.worker:
        worker(args.worker, args.case)
        return
    check = preflight()
    if not args.live:
        print(json.dumps({k: v for k, v in check.items() if k not in ('cost_before', 'files')}, ensure_ascii=False))
        return
    # Public metadata GET only; no paid request or result directory before key.
    url = 'https://api.metisai.ir/api/v1/meta/providers/pricing'
    with urlopen(url, timeout=20) as response:
        prices = json.load(response)
    chat = next(x for x in prices['llm'] if x['model'] == 'gpt-4.1-mini')
    embed = next(x for x in prices['embedding'] if x['model'] == 'text-embedding-3-small')
    assert all(x['currency'] == 'USD' and x['fixedCallIncome'] == 0 for x in (chat, embed))
    assert chat['inputTokenUnitIncome'] > 0 and chat['outputTokenUnitIncome'] > 0 and embed['inputTokenUnitIncome'] > 0
    key = os.getenv('METIS_API_KEY')
    if not key:
        if not sys.stdin.isatty():
            raise SystemExit('نیاز: این فرمان را در ترمینال تعاملی اجرا کنید؛ کلید را در چت ننویسید.')
        key = getpass.getpass('Metis API key (hidden): ')
    if not key or not key.strip():
        raise SystemExit('توقف: کلید وارد نشده؛ درخواست پولی اجرا نشد.')
    before = ledger()
    cap = before['charged_or_reserved_usd'] + ADDITIONAL_CAP
    assert cap <= 5
    env = os.environ.copy()
    env.update(configuration({'chat': chat, 'embedding': embed}, cap), METIS_API_KEY=key)
    key = ''
    cases = [{k: c.get(k, {} if k == 'initial_facts' else [] if k == 'initial_checks' else '')
              for k in ('id', 'initial_message', 'initial_facts', 'initial_checks')}
             for c in read(BASE / 'holdout/cases.json')]
    plan = {'mode': 'live', 'at': time.time(), 'cases': cases, 'files': frozen(), 'cost_before': before,
        'cumulative_cap_usd': cap, 'additional_cap_usd': ADDITIONAL_CAP,
        'authorization': 'سقف 80 سنت رو تایید میکنم', 'authorization_date': '2026-10-08',
        'order': [{'id': c['id'], 'variants': ['previous', 'revised'] if i % 2 == 0 else ['revised', 'previous']}
                  for i, c in enumerate(cases)],
        'pricing': {'source': url, 'chat': chat, 'embedding': embed},
        'limits': {'max_calls': 8, 'max_turn_usd': .04, 'deadline_seconds': 180, 'repairs': 1},
        'no_retry': True, 'no_post_test_tuning': True, 'semantic_labels_before_inference': False}
    FOLDER.mkdir(parents=True, exist_ok=False)
    write(FOLDER / 'plan.json', plan)
    stop = None
    try:
        for pair in plan['order']:
            assert frozen() == plan['files'], 'Frozen files changed'
            if not pair_fits(ledger()['charged_or_reserved_usd'], cap):
                stop = 'insufficient_budget_for_complete_pair'
                break
            for variant in pair['variants']:
                print('اجرا: ' + pair['id'] + ' / ' + variant, flush=True)
                proc = subprocess.run([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
                    '--worker', variant, '--case', pair['id']], cwd=ROOT, env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if proc.returncode:
                    stop = 'worker_failed_without_retry'
                    path = FOLDER / 'turns' / (pair['id'] + '_' + variant + '.json')
                    if not path.exists():
                        write(path, {'id': pair['id'], 'variant': variant, 'output': None,
                                     'failure': stop, 'usage': [], 'provider_outcome_unknown': True})
                    break
            summarize(plan, stop)
            if stop:
                break
    except KeyboardInterrupt:
        stop = 'interrupted_without_retry'
    finally:
        env.pop('METIS_API_KEY', None)
        manifest = summarize(plan, stop)
        print(json.dumps({k: manifest[k] for k in ('complete', 'stop_reason', 'paired_cases',
              'new_requests', 'new_charged_or_reserved_usd', 'frozen_unchanged')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('توقف: اجرای بهینه‌شدهٔ پایتون برای این ارزیابی مجاز نیست.')
    main()
