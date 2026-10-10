"""Summarize the two development replay outputs without relabeling fixtures as models."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('v216_output_replay', 'v217_output_replay')


def summary(label):
    path = ROOT / 'artifacts/architecture_v2/offline' / (label + '_no_dense/answers.jsonl')
    record = json.loads(path.read_text(encoding='utf-8').splitlines()[0])
    output = record['output']
    return {'label': label, 'case_id': record['id'], 'mode': output['mode'],
            'generation_kind': output.get('generation_kind', 'test_fixture'),
            'decision': output['decision'], 'validation_error': output['validation_error'],
            'first_paragraph': output['response'].split('\n\n')[0],
            'technical_citations': len(output['summary']['sources']),
            'judge_kind': next((s.get('evaluation_kind') for s in output['pipeline'] if s['stage']=='judge'), None),
            'fixture_calls': output['model_calls'], 'provider_requests': output['usage']['provider_requests'],
            'proposal_status': output['proposal']['status']}


if __name__ == '__main__':
    print(json.dumps({'split': 'dev', 'comparison': [summary(label) for label in LABELS]}, ensure_ascii=False, indent=2))
