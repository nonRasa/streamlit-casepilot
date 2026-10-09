"""One authorized minimal generation probe; credentials stay in process memory."""
import getpass
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, urlopen

import evaluate_quality_v23_additional as campaign


def compact(value):
    return {k: v for k, v in value.items() if k != 'calls'}


def main():
    folder = campaign.BASE / 'live_comparison_05'
    assert not folder.exists(), 'Existing diagnostic cannot be overwritten'
    auth = campaign.read(campaign.FOLDER / 'authorization_plan.json')
    assert all(campaign.sha(campaign.ROOT / n) == h for n, h in auth['production_files'].items())
    before = campaign.ledger()
    cap = min(auth['cumulative_cap_usd'], 5)
    assert before['charged_or_reserved_usd'] + .003 <= cap
    campaign.write(folder / 'plan.json', {
        'authorization': 'درخواست کاربر برای بررسی و رفع اتصال؛ فقط یک درخواست کوچک تولید',
        'cost_before': compact(before), 'cumulative_cap_usd': cap,
        'probe_cap_usd': .003, 'max_generation_calls': 1, 'timeout_seconds': 45,
        'base_url': 'https://api.metisai.ir/openai/v1',
        'model': 'gpt-4.1-mini', 'max_tokens': 64, 'response_format': None,
        'purpose': 'تفکیک شکست تولید ساده از قالب ساخت‌یافته؛ بدون ارزیابی کیفیت',
        'production_files': auth['production_files'],
    })
    key = getpass.getpass('Credential: ')
    assert key, 'Credential missing'
    os.environ['METIS_API_KEY'] = key
    result = {'generation_success': False, 'generation_http_status': None}
    client = None
    started = time.monotonic()
    try:
        request = Request('https://api.metisai.ir/openai/v1/models',
                          headers={'Authorization': 'Bearer ' + key})
        try:
            with urlopen(request, timeout=10) as response:
                data = json.load(response)
                result['models_http_status'] = response.status
                ids = [row.get('id') for row in data.get('data', [])]
                result['requested_model_listed'] = 'gpt-4.1-mini' in ids
        except HTTPError as exc:
            result['models_http_status'] = exc.code
            return
        except Exception as exc:
            result['models_transport_error'] = type(exc).__name__
            return
        with urlopen('https://api.metisai.ir/api/v1/meta/providers/pricing', timeout=15) as response:
            prices = json.load(response)
        pricing = {'chat': next(x for x in prices['llm'] if x['model'] == 'gpt-4.1-mini'),
                   'embedding': next(x for x in prices['embedding'] if x['model'] == 'text-embedding-3-small')}
        assert all(x['currency'] == 'USD' and x['fixedCallIncome'] == 0 and x['perSecondIncome'] == 0
                   for x in pricing.values())
        campaign.write(folder / 'pricing.json', pricing)
        os.environ.update(campaign.configuration(pricing, cap))
        sys.path.insert(0, str(campaign.ROOT / 'src'))
        import casepilot.model as model
        original_opener = model.build_opener

        class Observed:
            def __init__(self, opener):
                self.opener = opener

            def open(self, *args, **kwargs):
                try:
                    response = self.opener.open(*args, **kwargs)
                    result['generation_http_status'] = response.status
                    return response
                except HTTPError as exc:
                    result['generation_http_status'] = exc.code
                    body = exc.read(4000).decode('utf-8', errors='replace')
                    try:
                        parsed = json.loads(body)
                        error = parsed.get('error', parsed)
                        result['provider_error_code'] = error.get('code') if isinstance(error, dict) else None
                    except (ValueError, AttributeError):
                        pass
                    raise
                except Exception as exc:
                    result['generation_transport_error'] = type(exc).__name__
                    raise

        model.build_opener = lambda *args, **kwargs: Observed(original_opener(*args, **kwargs))
        client = model.MetisClient()
        client.turn_scope = {'calls_before': 0, 'max_calls': 1, 'cap_usd': .003,
                             'cost_before': before['charged_or_reserved_usd'],
                             'deadline': time.monotonic() + 45}
        payload = {'model': 'gpt-4.1-mini', 'messages': [
            {'role': 'user', 'content': 'Connectivity check 05. Return exactly this JSON: {"probe":true}'}],
            'max_tokens': 64}
        answer = client._request(payload, kind='minimal_connection_probe')
        result['generation_success'] = answer == {'probe': True}
    except Exception as exc:
        result['error_code'] = getattr(exc, 'code', type(exc).__name__)
    finally:
        after = campaign.ledger()
        result.update(elapsed_seconds=time.monotonic() - started,
                      usage=client.usage_history if client else [], cost_after=compact(after),
                      added_confirmed_usd=after['confirmed_usd'] - before['confirmed_usd'],
                      added_uncertain_reserved_usd=after['uncertain_reserved_usd'] - before['uncertain_reserved_usd'],
                      remaining_stage_usd=cap - after['charged_or_reserved_usd'],
                      panel_balance_observed=False,
                      production_unchanged=all(campaign.sha(campaign.ROOT / n) == h for n, h in auth['production_files'].items()))
        campaign.write(folder / 'diagnostic.json', result)
        if client:
            client.key = ''
        os.environ.pop('METIS_API_KEY', None)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
