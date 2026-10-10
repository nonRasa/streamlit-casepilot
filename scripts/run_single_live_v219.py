"""One development-only live case with a shared cost ledger and fresh cache.

The same harness can load a complete checkout of main or the improvement branch.
"""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--incremental-cap-usd', type=float, default=.04)
parser.add_argument('--experiment-v221', action='store_true')
parser.add_argument('--split-query', action='store_true')
args = parser.parse_args()
if not 0 < args.incremental_cap_usd <= .04:
    parser.error('--incremental-cap-usd must be in (0, 0.04]')
root = args.source_root.resolve()
output = args.output.resolve()
sys.path.insert(0, str(root / 'src'))

from casepilot.agent import Agent
from casepilot.common import CasePilotError
from casepilot.hybrid import HybridRetriever
from casepilot.model import make_client
from casepilot.store import Store

output.mkdir(parents=True, exist_ok=False)
case = next(c for c in json.loads((root / 'eval/cases.json').read_text(encoding='utf-8')) if c['id'] == 'GH9218' and c['split'] == 'dev')
client = make_client('live')
client.focus_quotes = args.experiment_v221
client.evidence_first = args.experiment_v221
client.cache = output / 'fresh_cache'
client.cache.mkdir()
client.diagnostics = output / 'diagnostics'
before = client.budget.report()
client.budget.cap = min(client.budget.cap, before['charged_or_reserved_usd'] + args.incremental_cap_usd, .30)
hybrid = HybridRetriever(client)
frozen = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in
          ('src/casepilot/model.py', 'src/casepilot/pipeline.py', 'src/casepilot/quality.py',
           'src/casepilot/hybrid.py', 'data/corpus_v2.json', 'eval/cases.json')}
result = {'label': args.label, 'case_id': case['id'], 'split': 'dev', 'variant': 'no_dense',
          'focused_quotes': args.experiment_v221, 'evidence_first': args.experiment_v221,
          'split_query': args.split_query,
          'source_root': str(root), 'frozen_hashes': frozen, 'budget_before': before['charged_or_reserved_usd'],
          'existing_uncertain_reserved_usd': before['uncertain_reserved_usd'], 'incremental_cap_usd': args.incremental_cap_usd,
          'fresh_cache': True, 'constructor_bypass': False}
(output / 'progress.json').write_text(json.dumps({'stage': 'before_turn', 'label': args.label}) + '\n', encoding='utf-8')
with tempfile.TemporaryDirectory(prefix='casepilot-live-pair-') as tmp:
    agent = Agent(Store(Path(tmp) / 'tracker.sqlite3'), client=client, hybrid=hybrid,
                  components={'dense': False, 'split_query': args.split_query})
    try:
        answer = agent.turn(case['id'], case['initial_message'], 'paired-live-' + args.label,
                            case['initial_facts'], case['initial_checks'])
        (output / 'answer.json').write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding='utf-8')
        result.update(decision=answer['decision'], validation_error=answer['validation_error'],
                      generation_kind=answer.get('generation_kind'), model_calls=answer['model_calls'],
                      first_paragraph=answer['response'].split('\n\n', 1)[0],
                      status_actions=[a for a in answer['proposal'].get('payload', answer['proposal']).get('actions', [])
                                      if a['type'] == 'status'])
    except CasePilotError as exc:
        result.update(error_code=exc.code)
    except BaseException as exc:
        # Record the class only: provider exceptions may embed request details.
        result.update(error_code='interrupted' if isinstance(exc, KeyboardInterrupt) else 'unexpected_exception',
                      error_type=type(exc).__name__)
after = client.budget.report()
result.update(new_requests=after['requests'] - before['requests'],
              new_confirmed_usd=after['confirmed_usd'] - before['confirmed_usd'],
              new_charged_or_reserved_usd=after['charged_or_reserved_usd'] - before['charged_or_reserved_usd'],
              new_uncertain_reserved_usd=after['uncertain_reserved_usd'] - before['uncertain_reserved_usd'],
              budget_after=after['charged_or_reserved_usd'])
(output / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in ('source_root', 'frozen_hashes')}, ensure_ascii=False))
