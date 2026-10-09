"""Export existing live artifacts for offline, explicitly non-independent review."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'artifacts/quality_v23/live_comparison_02'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    manifest = read(FOLDER / 'manifest.json')
    if not manifest['complete'] and not manifest['stop_reason']:
        raise SystemExit('توقف: اجرای مقایسه هنوز پایان نیافته است.')
    target = FOLDER / 'ai_review_packets.json'
    if target.exists():
        raise SystemExit('توقف: بستهٔ بازبینی موجود بازنویسی نمی‌شود.')
    cases = {c['id']: c for c in read(FOLDER / 'comparison_plan.json')['cases']}
    corpus = {c['id']: c for c in read(ROOT / 'data/corpus_v2.json')}
    cached = {}
    for path in (ROOT / 'artifacts/live_cache').glob('*.json'):
        value = read(path)
        usage = value.get('usage', {})
        if usage.get('kind') != 'embedding' and usage.get('ledger_id'):
            cached[usage['ledger_id']] = value
    packets = []
    for path in sorted((FOLDER / 'turns').glob('*.json')):
        row = read(path)
        output = row['output'] or {}
        stages = []
        for usage in row['usage']:
            original = usage.get('original_usage', usage)
            value = cached.get(original.get('ledger_id'))
            if value:
                stages.append({'kind': usage['kind'], 'cached': usage.get('mode') == 'cached_live',
                               'ledger_id': original['ledger_id'], 'raw_answer': value['raw_answer']})
        packets.append({'id': row['id'], 'variant': row['variant'], 'initial_report': cases[row['id']]['initial_message'],
                        'result': row, 'raw_role_outputs': stages,
                        'retrieved_sources': [corpus[r['id']] for r in output.get('retrieved', [])],
                        'response_sha256': hashlib.sha256(output.get('response', '').encode()).hexdigest()})
    target.write_text(json.dumps({'reviewer_type': 'AI assistant involved in implementation',
        'independent': False, 'blind': False, 'gold_labels_predeclared': False, 'review_rubric_before_inference': True,
        'no_new_provider_requests': True, 'packets': packets}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'packets': len(packets), 'provider_requests': 0}))


if __name__ == '__main__':
    main()
