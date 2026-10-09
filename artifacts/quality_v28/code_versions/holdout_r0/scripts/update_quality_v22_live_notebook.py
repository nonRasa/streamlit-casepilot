"""Add saved paid results to the offline notebook, preserving its prior edition."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'artifacts/quality_v22/live_comparison_01'


def main():
    manifest = json.loads((FOLDER / 'manifest.json').read_text(encoding='utf-8'))
    if not manifest['complete'] and not manifest['stop_reason']:
        raise SystemExit('توقف: اجرای واقعی هنوز پایان نیافته است.')
    path = ROOT / 'CasePilot_project.ipynb'
    backup = FOLDER / 'prior_offline_notebook.ipynb'
    if backup.exists():
        raise SystemExit('توقف: نسخهٔ قبلی نوت‌بوک یا به‌روزرسانی موجود بازنویسی نمی‌شود.')
    shutil.copy2(path, backup)
    notebook = json.loads(path.read_text(encoding='utf-8'))
    for cell in notebook['cells']:
        source = ''.join(cell['source'])
        if cell['cell_type'] == 'code':
            cell['execution_count'] = None
            cell['outputs'] = []
            source = source.replace('artifacts/quality_v22/notebook_tests',
                                    'artifacts/quality_v22/live_comparison_01/notebook_tests')
            source = source.replace('artifacts/quality_v22/notebook_adversarial.json',
                                    'artifacts/quality_v22/live_comparison_01/notebook_adversarial.json')
            if 'RUN_LIVE = False' in source:
                source = """RUN_LIVE = False
if RUN_LIVE:
    raise RuntimeError('این نوت‌بوک درخواست پولی تازه اجرا نمی‌کند؛ خروجی‌های واقعی محفوظ خوانده می‌شوند.')
live_folder = ROOT / 'artifacts/quality_v22/live_comparison_01'
live_result = read_json(live_folder / 'manifest.json')
print('نتیجهٔ اجرای واقعی محفوظ:', {k: live_result[k] for k in ('complete', 'paired_cases', 'new_requests', 'new_charged_or_reserved_usd', 'frozen_unchanged')})
review = read_json(live_folder / 'ai_review_metrics.json')
print('بازبینی غیرمستقل دستیار؛ صحت انسانی نیست:', review['summary'])
print('مرز: بازبینی انسانی مستقل و اجرای واقعی سایت انجام نشده‌اند؛ گزارش در docs/QUALITY_V22_LIVE_FA.md است.')
temporary.cleanup()
"""
        elif source.startswith('# پروژهٔ دستیار'):
            source += '\nنتیجهٔ تکمیلی: این ویرایش خروجی‌های مقایسهٔ واقعی با سقف ۸۰ سنت را از فایل می‌خواند؛ اجرای نوت‌بوک رایگان است. بازبینی دستیار غیرمستقل است و هیچ مجوز ثبت یا اجرای خودکار به عامل نمی‌دهد.\n'
        cell['source'] = source.splitlines(keepends=True)
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
