"""Render the new recovery first paragraph against three saved live outputs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.grounding import fallback, render_response


def main():
    path = ROOT / 'artifacts/architecture_v2/live/v29_dev3_no_dense/answers.jsonl'
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        saved = json.loads(line)
        output = saved['output']
        handoff = output['summary']['handoff']
        state = {'messages': [{'text': handoff['reported_problem']}], 'facts': handoff['environment'],
                 'checks': handoff['reported_checks'], 'investigation_plan': output['summary'].get('investigation_plan', {})}
        revised = render_response(fallback(output['validation_error'], state), [], state['facts'], state['checks'])
        rows.append({'case_id': saved['id'], 'split': saved['split'], 'saved_error': output['validation_error'],
                     'before_first_paragraph': output['response'].split('\n\n', 1)[0],
                     'after_first_paragraph': revised.split('\n\n', 1)[0],
                     'simulated_generation_kind': 'recovery_fallback', 'provider_requests': 0})
    result = {'source': path.relative_to(ROOT).as_posix(), 'comparison': 'saved live fallback versus offline rendering only',
              'provider_requests': 0, 'rows': rows}
    dest = ROOT / 'artifacts/architecture_v2/offline/v219/recovery_comparison.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
