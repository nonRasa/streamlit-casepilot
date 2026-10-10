"""Offline accounting, integrity checks and blind unit review; never calls a provider."""
import hashlib
import json
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'artifacts/quality_v28_semantic_judge'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    if path.exists():
        if read(path) == value:
            return
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    auth = read(RUN / 'authorization.json')
    with sqlite3.connect(ROOT / 'runtime/team_budget.sqlite3') as db:
        rows = db.execute('SELECT m.phase,c.status,c.charged,c.reserved,c.kind,c.model,c.input_tokens,c.output_tokens '
                          'FROM calls c JOIN completion_calls m ON c.id=m.id WHERE m.campaign=?',
                          (auth['campaign'],)).fetchall()
    phases = {}
    for phase, status, charged, reserved, kind, model, input_tokens, output_tokens in rows:
        assert kind == 'judge' and model == auth['model']
        assert reserved <= .02 + 1e-12
        p = phases.setdefault(phase, {'provider_requests': 0, 'confirmed_usd': 0,
                                     'uncertain_reserved_usd': 0, 'input_tokens': 0, 'output_tokens': 0})
        p['provider_requests'] += 1
        p['confirmed_usd' if status == 'confirmed' else 'uncertain_reserved_usd'] += charged
        p['input_tokens'] += input_tokens or 0
        p['output_tokens'] += output_tokens or 0
    for phase, p in phases.items():
        p['charged_or_reserved_usd'] = p['confirmed_usd'] + p['uncertain_reserved_usd']
        assert p['provider_requests'] <= auth['phase_limits'][phase]['requests']
        assert p['charged_or_reserved_usd'] <= auth['phase_limits'][phase]['usd']
    total = sum(p['charged_or_reserved_usd'] for p in phases.values())
    assert len(rows) <= auth['max_requests'] and total <= auth['hard_cap_usd']
    assessment_count = 0
    for phase in ('baseline', 'correction_1', 'correction_2', 'holdout'):
        manifest = read(RUN / 'phases' / phase / 'manifest.json')
        assert manifest['complete'] and len(manifest['results']) == 12
        for name, expected in manifest['results'].items():
            path = RUN / 'phases' / phase / name
            assert sha(path) == expected and not read(path)['failure']
        assessment_count += len(manifest['results'])
    accounting = {'campaign': auth['campaign'], 'provider_requests': len(rows), 'draft_assessments': assessment_count,
                  'cached_assessments': assessment_count - len(rows), 'phases': phases, 'confirmed_usd': sum(p['confirmed_usd'] for p in phases.values()),
                  'uncertain_reserved_usd': sum(p['uncertain_reserved_usd'] for p in phases.values()),
                  'charged_or_reserved_usd': total, 'hard_cap_usd': auth['hard_cap_usd'],
                  'connection_retries': 0, 'embedding_requests': 0, 'generation_requests': 0,
                  'prior_campaign_cost_excluded': auth['cost_before'], 'budget_limits_passed': True}
    write(RUN / 'accounting.json', accounting)

    historical = read(ROOT / 'artifacts/quality_v28_offline_rescore/historical_inputs_before.json')
    changed = [name for name, expected in historical.items() if not (ROOT / name).exists() or sha(ROOT / name) != expected]
    baseline = read(RUN / 'baseline/manifest.json')
    snapshot_changed = [name for name, expected in baseline['files'].items()
                        if sha(RUN / 'baseline' / name) != expected]
    selected = read(RUN / 'selection.json')['implementation_hash']
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from evaluate_quality_v28_semantic_judge import implementation_hash
    assert not changed and not snapshot_changed and selected == implementation_hash()
    write(RUN / 'integrity.json', {'historical_files_checked': len(historical), 'historical_changes': changed,
          'baseline_files_checked': len(baseline['files']), 'baseline_changes': snapshot_changed,
          'selected_implementation_hash': selected, 'current_implementation_hash': implementation_hash(),
          'holdout_implementation_hash': read(RUN / 'phases/holdout/manifest.json')['implementation_hash'],
          'provider_requests': 0})

    original = read(RUN / 'review_suite_v3/human_review_blind.json')
    items = []
    from casepilot.review_contract import draft_units
    for item in original['items']:
        units = draft_units(item['draft'], item['state']['id'], item['state']['revision'], 1, include_quotes=True)['units']
        items.append({**item, 'review_form': {'units': [{**unit,
            'speech_act': None, 'literal_membership': None, 'source_relevance': None,
            'semantic_entailment': None, 'version_applicability': None,
            'exact_selected_witnesses': None, 'product_policy_valid': None,
            'uncertainty_or_reason': None} for unit in units],
            'overall_verdict': None, 'ambiguous': None, 'reviewer': None}})
    random.Random(20261010).shuffle(items)
    write(RUN / 'human_review_units_blind.json', {'reference_included': False, 'model_results_included': False,
          'independent_review_complete': False, 'source_status': 'Authored frozen fixture text, not independently verified corpus documentation',
          'instructions': 'Review literal membership, relevance, entailment, version and product policy separately. Null means unreviewed, not accepted.',
          'items': items})
    print(json.dumps({'accounting': accounting, 'historical_files_unchanged': len(historical),
                      'baseline_files_unchanged': len(baseline['files']), 'review_cases': len(items)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
