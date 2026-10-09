"""No-network checks of the new paid harness; no API key required."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
import evaluate_quality_v22_live as campaign


def main():
    checks = []
    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})
    for total, cap, expected in [(1.24, 2.04, True), (1.96, 2.04, True),
                                  (1.9601, 2.04, False), (2.04, 2.04, False)]:
        check(f'pair_budget_{total}_{cap}', campaign.pair_fits(total, cap) == expected)
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / 'cost.sqlite3'
        with closing(sqlite3.connect(db)) as connection:
            connection.execute('create table calls (id text, at text, charged real, status text)')
            connection.executemany('insert into calls values(?,?,?,?)',
                [('a', 'now', .2, 'confirmed'), ('b', 'now', .1, 'uncertain_reserved')])
            connection.commit()
        digest = hashlib.sha256(db.read_bytes()).hexdigest()
        with patch.object(campaign, 'LEDGER', db):
            report = campaign.ledger()
        check('confirmed_and_uncertain_in_same_cap',
              abs(report['charged_or_reserved_usd'] - .3) < 1e-12 and report['requests'] == 2)
        check('ledger_read_does_not_modify', digest == hashlib.sha256(db.read_bytes()).hexdigest())
        with patch.object(campaign, 'FOLDER', Path(directory)):
            try:
                campaign.preflight()
                refused = False
            except AssertionError as exc:
                refused = 'Existing campaign' in str(exc)
        check('existing_campaign_refuses_retry', refused)
    real_hash = hashlib.sha256(campaign.LEDGER.read_bytes()).hexdigest()
    preflight = campaign.preflight()
    check('offline_preflight_zero_requests_index_ready_frozen', preflight['passed']
          and preflight['provider_requests'] == 0 and preflight['index_ready'] and preflight['frozen_unchanged'])
    check('real_ledger_bytes_unchanged', real_hash == hashlib.sha256(campaign.LEDGER.read_bytes()).hexdigest())
    result = {'status': 'waiting_for_credential', 'paid_run_started': False, 'paid_requests': 0,
              'new_cost_usd': 0, 'additional_cap_usd': .8, 'checks': checks,
              'passed': all(c['passed'] for c in checks), 'preflight': preflight}
    campaign.write(campaign.BASE / 'live_preparation_01/verification.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'preflight'}, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
