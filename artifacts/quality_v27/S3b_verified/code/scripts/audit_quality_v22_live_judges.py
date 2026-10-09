"""Explain saved revised judge decisions offline, without rerunning any model."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.common import CasePilotError
from casepilot.model import quote_candidates, resolve_claims
from casepilot.review_contract import draft_units, checked_review


def main():
    folder = ROOT / 'artifacts/quality_v22/live_comparison_01'
    target = folder / 'judge_diagnostics.json'
    if target.exists():
        raise SystemExit('توقف: ممیزی قبلی بازنویسی نمی‌شود.')
    packets = json.loads((folder / 'ai_review_packets.json').read_text(encoding='utf-8'))['packets']
    diagnoses = []
    for packet in packets:
        if packet['variant'] != 'revised' or not packet['result']['output']:
            continue
        out = packet['result']['output']
        sources = packet['retrieved_sources']
        lookup = {(r['id'], q['quote_id']): q['text'] for r in sources for q in quote_candidates(r['text'])}
        state = {'id': packet['id'], 'revision': 1, 'facts': out['summary']['facts'],
                 'messages': [{'text': packet['initial_report']}]}
        answer = None
        generation = -1
        for stage in packet['raw_role_outputs']:
            if stage['kind'] in ('chat', 'repair'):
                generation += 1
                try:
                    answer = resolve_claims(stage['raw_answer'], lookup)
                except CasePilotError:
                    answer = None
            if stage['kind'] == 'judge' and answer:
                envelope = draft_units(answer, packet['id'], 1, generation)
                row = {'id': packet['id'], 'generation': generation,
                       'raw_verdict': stage['raw_answer'].get('verdict'),
                       'draft_version': envelope['draft_version'], 'provider_requests': 0}
                try:
                    checked = checked_review(stage['raw_answer'], answer, sources, state, envelope)
                    row.update(contract_valid=True, checked_verdict=checked['verdict'],
                               findings_without_runtime_forced_checks=checked['findings'])
                except CasePilotError as exc:
                    row.update(contract_valid=False, code=exc.code, diagnostic=str(exc))
                diagnoses.append(row)
    result = {'provider_requests': 0, 'no_model_regeneration': True,
              'limitation': 'Reconstructs single-turn draft and contract checks from saved raw roles; runtime forced content checks are not replayed.',
              'rows': diagnoses}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'judge_calls_audited': len(diagnoses), 'contract_failures': sum(not r['contract_valid'] for r in diagnoses)}))


if __name__ == '__main__':
    main()
