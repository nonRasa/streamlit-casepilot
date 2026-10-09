"""Record this assistant's post-inference judgements, never human/gold labels."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'artifacts/quality_v22/live_comparison_01'

# Overall, usefulness, repetition for delivered asks, information inventory, reason.
NOTES = {
 'GH17195': {
  'previous': [0, 0, True, 0, 'تکرار: گزارش صریحاً خالی‌شدن وضعیت و باقی‌ماندن انتخاب نمایشی را گفته و کد نمایش selection را دارد؛ پاسخ همان نتیجه را دوباره می‌خواهد. مثال پروندهٔ دیگر این پرسش یا علت را پشتیبانی نمی‌کند.'],
  'revised': [1, 1, None, 1, 'ارجاع: محیط و مسئلهٔ درست حفظ شده‌اند، اما گام بعد عمومی است. پیش‌نویس آزمایش نسخهٔ 1.57.0 می‌تواند مفید باشد، ولی استدلال حذف کلید و فرضیهٔ بی‌پیوند، کل پیش‌نویس را معتبر نمی‌کنند.']},
 'GH17011': {
  'previous': [0, 1, False, 1, 'پشتیبانی: درخواست لاگ کامل می‌تواند تازه باشد، ولی پاسخ محدودیت فرگمنت موازی را به نمونه‌ای نسبت می‌دهد که گزینهٔ اجرای موازی ندارد. نقل‌قول و فرضیه علت این نمونه را ثابت نمی‌کنند.'],
  'revised': [1, 1, None, 1, 'ارجاع: محیط فعلی حفظ شده، ولی آزمایش موفق 1.57.0 و ناموفق 1.58.0 در حافظهٔ آزمایش‌ها و متن ارجاع دیده نمی‌شوند. خطای diagnostic به گام عمومی منتهی شده است.']},
 'GH16888': {
  'previous': [1, 0, None, 0, 'ارجاع: خطای داور حفظ شده و ادعای رفع ندارد، اما هیچ شرح اختصاصی از درخواست DBSC، محدودیت مرورگر یا شرط پذیرش تحویل نمی‌دهد.'],
  'revised': [1, 1, None, 1, 'قابلیت: هدف opt-in برای جلوگیری از استفادهٔ کوکی روی دستگاه دیگر شناخته شده، اما پیشنهاد ساخت‌یافته و آزمون پذیرش از پاسخ نهایی حذف شده‌اند. پیش‌نویس به اشتباه پیاده‌سازی پیشنهادی را موجود می‌داند.']},
 'GH17127': {
  'previous': [1, 0, None, 0, 'ارجاع: پاسخ عمومی و بدون ادعای تأییدشده تحویل شده، اما اندازه‌ها، آزمون axe و گام بررسی استایل را خلاصه نمی‌کند.'],
  'revised': [0, 1, None, 1, 'پشتیبانی: پاسخ با تصمیم answer پذیرفته شده، ولی نقل‌قول فقط استفاده از glide-data-grid را می‌گوید و اندازهٔ دکمه، WCAG یا تضمین بهبود با 24 پیکسل را پشتیبانی نمی‌کند. گزارش کاربر به شاهد مستقل تبدیل شده است.']},
 'GH17006': {
  'previous': [1, 0, None, 0, 'ارجاع: خطای داور محفوظ است، ولی رفتار انتخاب چند ستون و درخواست هشدار یا خطا در بستهٔ تحویلی توضیح داده نمی‌شود.'],
  'revised': [1, 1, None, 1, 'ارجاع: ابهام انتخاب ستون و محیط حفظ شده‌اند، اما درخواست هشدار یا خطا و شرط پذیرش در ارجاع نیست. پیش‌نویس اصلاح‌شده اجرای چندباره را دوباره می‌خواهد، درحالی‌که تفاوت در اجراها از قبل گفته شده است.']},
 'GH16773': {
  'previous': [1, 0, None, 0, 'ارجاع: خطای انتخاب استناد حفظ شده، ولی تفاوت نوع ایستا، مقدار None و اثر step=1 به گام مشخص تبدیل نشده است.'],
  'revised': [1, 1, False, 1, 'پرسش: نمونهٔ با step=1 خواسته شده؛ نتیجهٔ بررسی نوع ایستا قبلاً آمده، ولی نوع زمان اجرا با این شرط صریح نیست. پرسش می‌توانست این تمایز را مشخص کند؛ درخواست نمونهٔ کامل برای افزودن یک پارامتر فایدهٔ محدودی دارد.']},
 'GH17234': {
  'previous': [0, 0, True, 0, 'تکرار: کد کامل تک‌خطی، تفاوت فایل و پوشه، مرورگرها و مرز نسخه موجود است؛ درخواست دوبارهٔ نمونهٔ کامل تمایز مشخصی ندارد. شاهد ذخیرهٔ RAM علت حذف ini در پوشه را پشتیبانی نمی‌کند.'],
  'revised': [1, 1, None, 1, 'ارجاع: نسخه و مرورگر و نوع فایل درست حفظ شده، اما مقایسهٔ Firefox و آپلود تکی در آزمایش‌ها نیامده است. درخواست لاگِ پیش‌نویس بالقوه مفید است، ولی فرضیهٔ شروع خطا از نسخهٔ Chrome 155 از گزارش نتیجه نمی‌شود.']},
 'GH16691': {
  'previous': [1, 0, None, 0, 'ارجاع: خطای داور و مرز تأیید حفظ شده‌اند؛ تفاوت نام فیلد multipart و filename و پیشنهاد نام ثابت تحویل داده نمی‌شود.'],
  'revised': [1, 1, None, 1, 'ارجاع: مسئله و محیط درست‌اند، ولی نام ثابت file و آزمون حفظ filename/path در بستهٔ نهایی نیست. پرسش پیش‌نویس درباره نسخه‌های قدیمی بدون نسخه یا شرط مشخص، بهترین گام برای این پیشنهاد محدود نیست.']},
 'GH16631': {
  'previous': [0, 0, True, 0, 'تکرار: هدر خراب دقیق و هدر مطلوب هر دو در گزارش هستند؛ پاسخ خلاف متن می‌گوید نمونهٔ دقیق هدر ارائه نشده است. استناد debug پرونده‌ای با نسخهٔ 1.52.2 پشتیبانی معنایی ندارد.'],
  'revised': [1, 1, None, 0, 'اطلاعات: عنوان مشکل درست است، ولی نسخهٔ فعلی 1.61.1 کنار تاریخچهٔ 1.60.0 به None تبدیل شده است. ارجاع هدر واقعی، جهت اصلاح و شرط پذیرش را نگه نمی‌دارد؛ پیش‌نویس نتیجهٔ اصلاحی را می‌خواهد که اجرای آن گزارش نشده است.']},
 'GH17265': {
  'previous': [1, 2, False, 2, 'پرسش: کد بازتولید واقعاً خالی است و درخواست کدِ دریافت هرثانیه تازه و مشخص است. بااین‌حال، متن تاریخیِ توصیهٔ به‌روزرسانی و انتشار patch به رفع تأییدشدهٔ خطاهای مشابه تعبیر شده؛ این بخش فقط پشتیبانی جزئی دارد.'],
  'revised': [1, 1, None, 1, 'ارجاع: با وجود امکان درخواست کد مفقود، خطای قرارداد به گام عمومی برای نگه‌دارنده منتهی شده است. پیش‌نویس کد و اجرای طولانی را یکجا می‌خواهد و فرضیهٔ قطع WebSocket را بی‌پشتیبانی اضافه می‌کند.']},
 'GH17142': {
  'previous': [0, 0, True, 0, 'قابلیت: کاربر زمان‌بندی مرکزی را به‌عنوان API پیشنهادی و با sketch داده؛ پاسخ نمونهٔ کدِ قابلیت هنوز ساخته‌نشده را می‌خواهد. run_every به‌تنهایی نبود هر راه مرکزی را ثابت نمی‌کند.'],
  'revised': [1, 1, None, 1, 'قابلیت: نیاز به به‌روزرسانی مشترک درست شناخته شده، اما اجرای یک‌بار برای همهٔ نشست‌ها و شرط مشاهدهٔ یکسان نتایج به پیشنهاد نهایی تبدیل نشده‌اند. پرسیدن برنامهٔ آینده از گزارشگر جای پیشنهاد را نمی‌گیرد.']},
 'GH17133': {
  'previous': [1, 0, None, 0, 'ارجاع: پاسخ عمومی است و زمان آخرین کش یا خروجی timestamp را به پیشنهاد نگه‌دارنده تبدیل نمی‌کند.'],
  'revised': [1, 1, None, 1, 'قابلیت: موضوع cached_function.time درست است، ولی پیش‌نویس نمونهٔ API هنوز ساخته‌نشده را می‌خواهد و امکان‌پذیری را فرض می‌گیرد. بستهٔ feature دارای رفتار مطلوب و پذیرش بود، اما در fallback نهایی حذف شده است.']},
 'GH16481': {
  'previous': [1, 0, None, 0, 'ارجاع: خطای داور محفوظ است، اما حالت pills و حفظ رفتار تب‌ها و سازگاری پیش‌فرض به پیشنهاد مشخص تبدیل نشده‌اند.'],
  'revised': [1, 1, None, 1, 'قابلیت: پیش‌نویس پیشنهاد ساخت‌یافتهٔ مفیدی با تغییر فقط ظاهر و حفظ رفتار داشت. داور نبود API پیشنهادی در نسخهٔ جاری را ایراد می‌گیرد؛ این دلیل نادرست است. بااین‌حال استناد یتیم هم وجود دارد، پس رد کل پیش‌نویس را به‌طور قطعی مثبت کاذب نمی‌شماریم. پیشنهاد مفید در fallback حذف شده است.']},
 'GH16149': {
  'previous': [1, 0, None, 0, 'ارجاع: گزارش کنتراست به خطای داور و گام عمومی منتهی شده؛ هیچ آزمون متمایزکنندهٔ قالب یا رنگ ارائه نشده است. تصویر و صفحهٔ Playground در این بازبینی اجرا نشده‌اند.'],
  'revised': [1, 1, None, 1, 'ارجاع: محیط و نسبت گزارش‌شده حفظ شده‌اند. درخواست CSS/HTML می‌تواند جزء مفید داشته باشد، ولی پیش‌نویس نهایی نبود دسترسی به آن را فرض می‌کند و استناد یتیم دارد. شاهد تازگی، وجود مسئله در گزارش را با پاسخ‌داده‌شدن درخواست CSS مخلوط کرده است.']},
 'GH16085': {
  'previous': [1, 0, None, 0, 'ارجاع: خطای ارائه‌دهنده حفظ شده و دوباره اجرا نشده است؛ درخواست SPLOM، لایه‌های انتخاب و PR موجود به پیشنهاد اختصاصی تبدیل نشده‌اند.'],
  'revised': None}
}
FEATURES = {'GH16888', 'GH17142', 'GH17133', 'GH16481', 'GH16085'}


def rate(values):
    known = [v for v in values if v is not None]
    return {'numerator': sum(known) if known else None, 'denominator': len(known),
            'unknown': len(values) - len(known), 'value': sum(known) / len(known) if known else None}


def main():
    target = FOLDER / 'ai_review.json'
    if target.exists():
        raise SystemExit('توقف: بازبینی موجود بازنویسی نمی‌شود.')
    packets = json.loads((FOLDER / 'ai_review_packets.json').read_text(encoding='utf-8'))['packets']
    rows = []
    for packet in packets:
        out = packet['result']['output']
        if not out:
            continue
        cid, variant = packet['id'], packet['variant']
        overall, usefulness, repeated, inventory, reason = NOTES[cid][variant]
        citations = out['summary']['sources']
        # All delivered citation spans were read with their source and answer.
        support = [1 if cid in ('GH17195', 'GH17265', 'GH17142') and variant == 'previous' else 0 for c in citations]
        escalated = out['decision'] == 'escalate'
        necessity = True if escalated and cid in FEATURES else False if escalated and cid == 'GH17265' else None
        rows.append({'id': cid, 'variant': variant, 'response_sha256': packet['response_sha256'],
            'overall': overall, 'next_step_usefulness': usefulness,
            'repeated_question_or_experiment': repeated, 'information_inventory_score': inventory,
            'citation_support_scores': support, 'necessary_escalation': necessity,
            'unnecessary_escalation': not necessity if necessity is not None else None,
            'feature_proposal_quality': 0 if cid in FEATURES else None,
            'inappropriate_acceptance': overall == 0 if out['validation_error'] is None else None,
            'false_rejection_of_useful_whole_draft': None,
            'version_semantic_fit': None,
            'reason': reason, 'reviewer': 'دستیار هوش مصنوعیِ مشارکت‌کننده در پیاده‌سازی'})
    review = {'independent': False, 'blind': False, 'post_inference': True, 'provider_requests': 0,
        'rubric': {'overall': 'صفر: پاسخ نامناسب، تکراری یا بی‌پشتیبانی؛ یک: جزء مفید یا ارجاع ناقص؛ دو: پاسخ مناسب و تصمیم‌ساز با اطلاعات قابل مشاهده.',
                   'citation_support_scores': 'صفر: نامرتبط یا بی‌پشتیبانی؛ یک: پشتیبانی جزئی؛ دو: پشتیبانی مستقیم. نبود استناد، مورد کاربرد ندارد.',
                   'necessity': 'فقط درخواست‌های روشن قابلیت، ارجاعِ لازم شمرده شدند؛ پروندهٔ فاقد کد GH17265 به‌وضوح قابل پرسش بود؛ باقی ارجاع‌ها مجهول‌اند.',
                   'unknown': 'نرخ مثبت کاذب رد کل پیش‌نویس و نرخ تناسب نسخهٔ مستقل، برچسب کامل ندارند؛ نمونه‌های تشخیصی دلیل و متن جدا دارند.'},
        'source_packets_sha256': hashlib.sha256((FOLDER / 'ai_review_packets.json').read_bytes()).hexdigest(),
        'annotation_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'rows': rows}
    target.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {}
    for variant in ('previous', 'revised'):
        group = [r for r in rows if r['variant'] == variant]
        originals = [p for p in packets if p['variant'] == variant]
        outputs = [p['result']['output'] for p in originals if p['result']['output']]
        citation_scores = [s for r in group for s in r['citation_support_scores']]
        escalation_rows = [r for r, p in zip(group, [p for p in originals if p['result']['output']])
                           if p['result']['output']['decision'] == 'escalate']
        asked = [r for r, p in zip(group, [p for p in originals if p['result']['output']])
                 if p['result']['output']['decision'] == 'ask']
        summary[variant] = {'attempted': len(originals), 'reviewed_deliveries': len(group),
            'missing_output': len(originals) - len(group),
            'overall_scores': {str(s): sum(r['overall'] == s for r in group) for s in (0, 1, 2)},
            'inappropriate_acceptance': rate([r['inappropriate_acceptance'] for r in group if r['inappropriate_acceptance'] is not None]),
            'repeated_question_or_experiment': rate([r['repeated_question_or_experiment'] for r in asked]),
            'necessary_escalation': rate([r['necessary_escalation'] for r in escalation_rows]),
            'unnecessary_escalation': rate([r['unnecessary_escalation'] for r in escalation_rows]),
            'citation_direct_support': rate([s == 2 for s in citation_scores]),
            'citation_partial_support': sum(s == 1 for s in citation_scores),
            'information_inventory_scores': {str(s): sum(r['information_inventory_score'] == s for r in group) for s in (0, 1, 2)},
            'feature_proposal_quality': {'scores': {str(s): sum(r['feature_proposal_quality'] == s for r in group) for s in (0, 1, 2)},
                                         'eligible_cases': len(FEATURES), 'missing_output': sum(p['id'] in FEATURES and not p['result']['output'] for p in originals)},
            'false_rejection_of_useful_whole_draft': {'numerator': None, 'denominator': 0, 'unknown': len(escalation_rows), 'value': None},
            'version_semantic_fit': {'numerator': None, 'denominator': 0, 'unknown': len(group), 'value': None},
            'retrieval_recall_at_5': {'numerator': None, 'denominator': 0, 'unknown': len(originals), 'value': None},
            'median_latency_seconds': statistics.median(p['result']['elapsed_seconds'] for p in originals)}
    ratings = {(r['id'], r['variant']): r['overall'] for r in rows}
    paired = {'better': [], 'equal': [], 'worse': [], 'missing_delivery': []}
    for cid in NOTES:
        old, new = ratings.get((cid, 'previous')), ratings.get((cid, 'revised'))
        category = 'missing_delivery' if old is None or new is None else 'better' if new > old else 'worse' if new < old else 'equal'
        paired[category].append(cid)
    metrics = {'independent': False, 'human_review': False, 'posthoc': True, 'summary': summary,
               'paired_overall': {k: {'count': len(v), 'ids': v} for k, v in paired.items()},
               'limitation': 'AI ordinal judgements over saved reports and outputs, not independently confirmed accuracy. No sampled report code, images or real Streamlit deployment was executed.'}
    (FOLDER / 'ai_review_metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (FOLDER / 'ai_review.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps({'reviewed': len(rows), 'paired': metrics['paired_overall'], 'summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
