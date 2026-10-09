"""Reuse the frozen comparison runner with isolated results and runtime state.

No production code is patched. The prior runner is loaded with only the output
label, current-attempt accounting, and authorization wording adjusted. Its hash
and this adapter's hash are included in the pre-inference freeze.
"""
from pathlib import Path

original = Path(__file__).with_name('evaluate_quality_v23_additional.py')
source = original.read_text(encoding='utf-8')
assert source.count("live_comparison_02") == 3
source = source.replace('live_comparison_02', 'live_comparison_06')
replacements = {
    "paths += [Path(__file__),ROOT/'docs/QUALITY_V23_ADDITIONAL_PROTOCOL_FA.md',FOLDER/'authorization_plan.json']":
        "paths += [Path(__file__),ROOT/'scripts/evaluate_quality_v23_additional.py',ROOT/'docs/QUALITY_V23_ADDITIONAL_PROTOCOL_FA.md',FOLDER/'authorization_plan.json']",
    "before = read(FOLDER/'authorization_plan.json')['cost_before']": "before = ledger()",
    "'remaining_stage_usd':ADDITIONAL_CAP-(after['charged_or_reserved_usd']-before['charged_or_reserved_usd'])":
        "'remaining_stage_usd':plan['cumulative_cap_usd']-after['charged_or_reserved_usd']",
    "'authorization': 'مجوز تازهٔ کاربر: ۳۰ سنت برای اجرای مقایسهٔ پیشرفت', 'authorization_date': '2026-10-08'":
        "'authorization': 'درخواست کاربر برای بررسی دوبارهٔ آزمون‌ها؛ در باقی‌ماندهٔ همان بودجهٔ سی سنتی، بدون افزایش سقف', 'authorization_date': '2026-10-09'",
}
for old, new in replacements.items():
    assert source.count(old) == 1, 'Unexpected comparison runner layout'
    source = source.replace(old, new)
exec(compile(source, str(original), 'exec'), globals())
