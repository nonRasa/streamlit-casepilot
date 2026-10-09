"""Audit paid results, immutable runtimes, costs and review provenance offline."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import evaluate_quality_v22_live as campaign

ROOT = campaign.ROOT
FOLDER = campaign.FOLDER


def main():
    checks = []
    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})
    plan = campaign.read(FOLDER / 'plan.json')
    manifest = campaign.read(FOLDER / 'manifest.json')
    rows = [campaign.read(p) for p in (FOLDER / 'turns').glob('*.json')]
    check('finished_or_explicitly_stopped', manifest['complete'] or bool(manifest['stop_reason']))
    check('frozen_sources_inputs_and_protocol_unchanged', campaign.frozen() == plan['files'])
    baseline = campaign.read(campaign.BASE / 'baseline_manifest.json')
    check('all_historical_files_preserved', all(campaign.sha(ROOT / n) == h for n, h in baseline['historical_files'].items()))
    check('authorized_additional_cap_80_cents', plan['additional_cap_usd'] == .8
          and abs(plan['cumulative_cap_usd'] - plan['cost_before']['charged_or_reserved_usd'] - .8) < 1e-9)
    check('actual_cost_with_uncertain_reserves_within_cap',
          manifest['new_charged_or_reserved_usd'] <= .8 + 1e-9 and manifest['cost_after']['charged_or_reserved_usd'] <= 5)
    check('confirmed_plus_uncertain_equal_total_delta', abs(manifest['new_confirmed_usd']
          + manifest['new_uncertain_reserved_usd'] - manifest['new_charged_or_reserved_usd']) < 1e-9)
    expected = {(c['id'], v) for c in plan['cases'] for v in ('previous', 'revised')}
    actual = {(r['id'], r['variant']) for r in rows}
    unstarted = {(r['id'], r['variant']) for r in manifest['not_started']}
    check('all_attempted_and_unstarted_accounted_without_duplicates',
          len(rows) == len(actual) and actual.isdisjoint(unstarted) and actual | unstarted == expected)
    check('initial_only_inputs', all(set(c) == {'id', 'initial_message', 'initial_facts', 'initial_checks'} for c in plan['cases']))
    check('all_delivered_turns_within_call_and_repair_limits', all(
          not r['output'] or r['output']['model_calls'] <= 8 and r['output']['repair_count'] <= 1 for r in rows))
    check('isolated_previous_and_revised_imports', all(not r['output'] or Path(r['pipeline_path']).is_relative_to(
          campaign.BASE / 'baseline/src' if r['variant'] == 'previous' else ROOT / 'src') for r in rows))
    before_ids = {c['id'] for c in plan['cost_before']['calls']}
    new_calls = [c for c in manifest['cost_after']['calls'] if c['id'] not in before_ids]
    usages = [u for r in rows for u in r['usage'] if u.get('provider_requests') == 1]
    check('new_provider_calls_match_shared_ledger', len(new_calls) == manifest['new_requests'] == len(usages)
          and {c['id'] for c in new_calls} == {u['ledger_id'] for u in usages})
    check('turn_ledger_charges_match_campaign_delta', abs(sum(u.get('cost_usd', u.get('reserved_usd', 0))
          for u in usages) - manifest['new_charged_or_reserved_usd']) < 1e-9)
    check('no_further_spend_after_campaign', campaign.ledger() == manifest['cost_after'])
    check('delivered_turns_respect_four_cent_cap', all(not r['output'] or
          r['output']['usage']['charged_or_reserved_usd'] <= .04 + 1e-9 for r in rows))
    traces = [t for v in ('previous', 'revised') for t in campaign.read(FOLDER / (v + '_traces.json'))]
    check('no_approval_or_execution_in_paid_traces', not any(t['kind'] in
          ('approved', 'executed', 'proposal_approved', 'execution_completed') for t in traces))
    with (FOLDER / 'human_review.csv').open(encoding='utf-8-sig', newline='') as f:
        human = list(csv.DictReader(f))
    check('human_review_is_blank_and_not_fabricated', len(human) == sum(bool(r['output']) for r in rows)
          and all(not any(v for k, v in r.items() if k not in ('case_id', 'variant', 'response_sha256')) for r in human))
    review_path = FOLDER / 'ai_review.json'
    if review_path.exists():
        review = campaign.read(review_path)
        reviewed = review['rows']
        check('AI_review_explicitly_nonindependent_posthoc', not review['independent']
              and not review['blind'] and review['post_inference'] and review['provider_requests'] == 0)
        check('AI_review_covers_each_delivery_once', len(reviewed) == len({(r['id'], r['variant']) for r in reviewed})
              == sum(bool(r['output']) for r in rows)
              and {(r['id'], r['variant']) for r in reviewed} == {(r['id'], r['variant']) for r in rows if r['output']})
        by_id = {(r['id'], r['variant']): r for r in rows}
        check('AI_review_bound_to_exact_response', all(r['response_sha256'] == hashlib.sha256(
              by_id[(r['id'], r['variant'])]['output']['response'].encode()).hexdigest() for r in reviewed))
        check('AI_scores_in_declared_range', all(r['overall'] in (0, 1, 2) and bool(r['reason']) for r in reviewed))
    else:
        check('AI_review_available', False)
    result = {'passed': all(c['passed'] for c in checks), 'provider_requests': 0, 'checks': checks}
    campaign.write(FOLDER / 'verification.json', result)
    print(json.dumps({'passed': result['passed'], 'checks': len(checks),
                      'failures': [c['check'] for c in checks if not c['passed']]}))
    return result['passed']


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
