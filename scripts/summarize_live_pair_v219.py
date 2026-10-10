"""Sanitize a local paired live run into a commit-safe comparison artifact."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--main-answer', type=Path, required=True)
parser.add_argument('--branch-answer', type=Path, required=True)
parser.add_argument('--main-root', type=Path, required=True)
parser.add_argument('--branch-root', type=Path, required=True)
args = parser.parse_args()


def read(path):
    content = path.read_bytes()
    return json.loads(content), hashlib.sha256(content).hexdigest()


def summary(path, commit):
    answer, digest = read(path)
    actions = answer['proposal'].get('payload', answer['proposal'])['actions']
    return {'commit': commit, 'raw_answer_sha256': digest, 'decision': answer['decision'],
            'validation_error': answer['validation_error'], 'generation_kind': answer.get('generation_kind'),
            'first_paragraph': answer['response'].split('\n\n', 1)[0],
            'model_calls': answer['model_calls'], 'provider_requests': answer['usage']['provider_requests'],
            'estimated_charged_usd': answer['usage']['charged_or_reserved_usd'],
            'repair_count': answer['repair_count'], 'review_failures': len(answer['review_failures']),
            'source_ids': [r['source_id'] for r in answer['retrieved']],
            'proposed_status_actions': [a for a in actions if a['type'] == 'status']}


main_data = json.loads((args.main_root / 'data/corpus_v2.json').read_text(encoding='utf-8'))
branch_data = json.loads((args.branch_root / 'data/corpus_v2.json').read_text(encoding='utf-8'))
main_case = next(c for c in json.loads((args.main_root / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH9218')
branch_case = next(c for c in json.loads((args.branch_root / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH9218')
result = {'mode': 'live', 'split': 'dev', 'case_id': 'GH9218', 'variant': 'no_dense',
          'provider': 'official Metis HTTPS gateway', 'model': 'gpt-4.1-mini',
          'same_case_input': all(main_case[k] == branch_case[k] for k in ('initial_message', 'initial_facts', 'initial_checks')),
          'same_corpus_records': main_data == branch_data, 'corpus_records': len(main_data),
          'main': summary(args.main_answer, 'dacf3ecd977efa0e22f7c46d359c9fd4e4771b4c'),
          'branch': summary(args.branch_answer, 'd24013d67d613e191b4727a2d39534a52e42ac39'),
          'cost_limit_usd': .30, 'preexisting_uncertain_reserved_usd': .01237104,
          'new_uncertain_reservations': 0,
          'limitations': ['One development case cannot establish overall model improvement.',
                          'Both drafts were rejected after one repair; the visible difference is in fallback and status handling.',
                          'Prices are project estimates rather than a verified provider invoice.',
                          'No blind independent human ratings were collected.']}
dest = ROOT / 'artifacts/architecture_v2/live/v219_main_pair_no_dense/comparison.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'same_case_input': result['same_case_input'], 'same_corpus_records': result['same_corpus_records'],
                  'main': result['main']['validation_error'], 'branch': result['branch']['validation_error'],
                  'confirmed_pair_usd': result['main']['estimated_charged_usd'] + result['branch']['estimated_charged_usd']}, ensure_ascii=False))
