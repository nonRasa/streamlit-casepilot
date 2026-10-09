"""تشخیص محدود اتصال با حفظ سقف و رزروهای مرحلهٔ قبلی."""
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import urlopen

import evaluate_quality_v23_additional as campaign

ROOT = campaign.ROOT
FOLDER = campaign.BASE / 'live_comparison_03'


def compact(value):
    return {k: v for k, v in value.items() if k != 'calls'}


def main():
    assert not FOLDER.exists(), 'Existing retry cannot be overwritten'
    auth = campaign.read(campaign.FOLDER / 'authorization_plan.json')
    assert all(campaign.sha(ROOT / name) == digest for name, digest in auth['production_files'].items())
    assert campaign.read(campaign.BASE / 'prelive_tests_03/test_results.json')['passed']
    before = campaign.ledger()
    cap = auth['cumulative_cap_usd']
    assert before['charged_or_reserved_usd'] + .003 <= cap <= 5
    assert os.environ.get('METIS_API_KEY'), 'Credential missing'
    plan = {
        'authorization': 'درخواست کاربر برای تلاش مجدد؛ همان بودجهٔ سی سنتی و بدون افزایش سقف',
        'stage_cost_before': compact(auth['cost_before']), 'attempt_cost_before': compact(before),
        'additional_cap_usd': .30, 'cumulative_cap_usd': cap,
        'probe': {'max_calls': 1, 'cap_usd': .003, 'timeout_seconds': 45},
        'comparison': {'case_ids': ['GH17011', 'GH17127', 'GH16481'], 'max_usd': .24,
                       'limits': {'max_calls': 8, 'max_turn_usd': .04, 'seconds': 180, 'repairs': 1}},
        'stop_conditions': ['شکست تشخیص: توقف بدون مقایسه', 'کمبود ظرفیت کامل زوج: توقف',
                            'خطای ارائه‌دهنده: توقف پس از زوج جاری', 'بدون تکرار برای بهبود امتیاز'],
        'split': 'development_seen', 'production_files': auth['production_files'],
        'baseline_commit': '1c77a4f574180e8d9d0eb9e2c748233aeb80fba6',
        'review': 'بازبینی دستیار غیرکور و غیرمستقل؛ بدون بازبینی انسانی یا آزمون نهایی',
        'review_rubric_sha256': campaign.sha(campaign.FOLDER / 'review_rubric.json'),
        'probe_script_sha256': campaign.sha(Path(__file__)),
    }
    campaign.write(FOLDER / 'retry_plan.json', plan)
    # Preserve original stage origin; never assign a new thirty cents to this retry.
    new_auth = dict(auth, cost_before=compact(auth['cost_before']), attempt_cost_before=compact(before))
    campaign.write(FOLDER / 'authorization_plan.json', new_auth)
    campaign.write(FOLDER / 'review_rubric.json', campaign.read(campaign.FOLDER / 'review_rubric.json'))
    result = {'success': False, 'http_status': None, 'transport_error_type': None}
    started = time.perf_counter()
    client = None
    try:
        with urlopen('https://api.metisai.ir/api/v1/meta/providers/pricing', timeout=20) as response:
            prices = json.load(response)
        pricing = {
            'chat': next(x for x in prices['llm'] if x['model'] == 'gpt-4.1-mini'),
            'embedding': next(x for x in prices['embedding'] if x['model'] == 'text-embedding-3-small'),
        }
        assert all(x['currency'] == 'USD' and x['fixedCallIncome'] == 0 and x['perSecondIncome'] == 0
                   for x in pricing.values())
        campaign.write(FOLDER / 'pricing.json', pricing)
        os.environ.update(campaign.configuration(pricing, cap))
        sys.path.insert(0, str(ROOT / 'src'))
        import casepilot.model as model
        original_opener = model.build_opener

        class Observed:
            def __init__(self, opener):
                self.opener = opener

            def open(self, *args, **kwargs):
                try:
                    response = self.opener.open(*args, **kwargs)
                    result['http_status'] = response.status
                    return response
                except HTTPError as exc:
                    result['http_status'] = exc.code
                    body = exc.read(4000).decode('utf-8', errors='replace')
                    body = body.replace(os.environ['METIS_API_KEY'], '[REDACTED]')
                    result['provider_error_body'] = re.sub(r'tpsg-[A-Za-z0-9_-]+', '[REDACTED]', body)
                    result['transport_error_type'] = type(exc).__name__
                    raise
                except Exception as exc:
                    result['transport_error_type'] = type(exc).__name__
                    result['transport_reason_type'] = type(getattr(exc, 'reason', None)).__name__
                    raise

        model.build_opener = lambda *args, **kwargs: Observed(original_opener(*args, **kwargs))
        client = model.MetisClient()
        client.turn_scope = {'calls_before': 0, 'max_calls': 1, 'cap_usd': .003,
                             'cost_before': before['charged_or_reserved_usd'],
                             'deadline': time.monotonic() + 45}
        answer = client.structured('stage30_retry_probe', 'Return JSON with probe=true. Connectivity check only.',
                                   {'stage': 'quality-v23-live-comparison-03'},
                                   {'type': 'object', 'properties': {'probe': {'type': 'boolean'}},
                                    'required': ['probe'], 'additionalProperties': False}, 80)
        result['success'] = answer == {'probe': True}
        result['response'] = answer
    except Exception as exc:
        result['error_code'] = getattr(exc, 'code', type(exc).__name__)
    finally:
        after = campaign.ledger()
        result.update(elapsed_seconds=time.perf_counter() - started,
                      usage=client.usage_history if client else [], cost_after=compact(after),
                      attempt_confirmed_usd=after['confirmed_usd']-before['confirmed_usd'],
                      attempt_uncertain_reserved_usd=after['uncertain_reserved_usd']-before['uncertain_reserved_usd'],
                      stage_added_usd=after['charged_or_reserved_usd']-auth['cost_before']['charged_or_reserved_usd'],
                      remaining_stage_usd=cap-after['charged_or_reserved_usd'],
                      production_unchanged=all(campaign.sha(ROOT / n)==h for n,h in auth['production_files'].items()),
                      panel_balance_observed=False)
        campaign.write(FOLDER / 'diagnostic.json', result)
        if client:
            client.key = ''
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('توقف: اجرای بهینه‌شده مجاز نیست.')
    main()
