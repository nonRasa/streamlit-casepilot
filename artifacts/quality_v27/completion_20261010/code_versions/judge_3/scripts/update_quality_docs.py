"""Promote measured quality-revision results while retaining historical reports."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json
from quality_result_files import result_paths

def replace(path,prefix,text):
    p=ROOT/path; parts=p.read_text(encoding='utf8').split('\n\n')
    if text in parts:return
    alternate={'راهنما: برای رابط واقعی،':'راهنما: فایل `START_LIVE.ps1`','پرسش: چه کارهایی بیرون این بسته':'پرسش: چه کارهایی باقی‌اند؟'}.get(prefix,prefix)
    index=next(i for i,s in enumerate(parts) if s.startswith(prefix) or s.startswith(alternate));parts[index]=text
    p.write_text('\n\n'.join(parts),encoding='utf8')

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation';m=read_json(result_paths(folder)[0]);ai=read_json(folder/'ai_review_manifest.json')
    pair=ai['paired_fresh'];cost=m['cost_cumulative'];counts=ai['summary']['test_fresh']['revised']['overall_counts']
    rows=read_json(folder/'answers.json');fallbacks=sum(bool((r['output'] or {}).get('validation_error')) for r in rows if r['split']=='test_fresh' and r['variant']=='revised')
    evaluation=(f"ارزیابی: نسخهٔ اصلاح‌شده روی پنج پروندهٔ توسعهٔ هدفمند و پانزده آزمون تازه، با {m['attempted_comparisons']} مقایسهٔ پردازش‌شده و {m['scenarios']['n']} سناریوی عملیاتی سنجیده شد؛ تعداد سناریوی موفق {m['scenarios']['passed']} است. "
        f"مقایسهٔ زوجی تازه در بازبینی این دستیار، {sum(x['difference']>0 for x in pair)} بهتر، {sum(x['difference']==0 for x in pair)} برابر و {sum(x['difference']<0 for x in pair)} بدتر دارد. "
        f"نسخهٔ جدید امتیاز کلی صفر {counts.get('0',0)}، یک {counts.get('1',0)} و دو {counts.get('2',0)} دارد. "
        f'تعداد {fallbacks} پاسخ از پانزده به ارجاع عمومی رسیدند؛ فایده هنوز کافی نیست. ارجاع امن، حل مسئله محسوب نمی‌شود. گزارش [اصلاح کیفیت](docs/QUALITY_REVISION_FA.md) و [یافته‌ها](docs/QUALITY_FINDINGS_FA.md) مرجع جاری‌اند؛ گزارش‌های معماری‌های قبلی تاریخی حفظ شده‌اند. داوری مستقل انسانی و آزمون سایت باقی‌اند.')
    review=(f"بازبینی: همهٔ {ai['rows']} خروجی این مقایسه و سناریوها با دلیل اختصاصی و هش در [فرم هوش مصنوعی](artifacts/quality_revision/final_evaluation/ai_review.csv) ثبت شدند. "
        'بازبین در پیاده‌سازی مشارکت دارد و بازبینی کور یا مستقل نیست؛ بخشی از پاسخ‌ها و ردپای تشخیصی همراه فراداده دیده شدند. فرم [انسانی](artifacts/quality_revision/final_evaluation/human_review.csv) خالی است. بازبینی این دستیار درخواست تازهٔ متیس ندارد. راهنما در [بازبینی پاسخ‌ها](docs/AI_REVIEW_FA.md) است.')
    replace('README.md','ارزیابی:',evaluation);replace('README.md','بازبینی:',review)
    replace('README.md','ارزیابی جاری:',
        'ارزیابی جاری: فایل `quality_cases.json` پنج پروندهٔ توسعه و پانزده آزمون تازه دارد. همهٔ گزارش‌های قبلاً دریافت‌شده، ایندکس و ارجاع‌های مستقیم خانواده‌ها پیش از انتخاب کنار گذاشته شدند. برچسب‌ها فقط از متن اولیه و پیش از پاسخ نوشته شدند و به عامل داده نمی‌شوند. صورت انتخاب، کد و ورودی قفل‌شده در پوشهٔ نتیجه‌اند. نسخهٔ پیشین از کد محفوظ خودش در فرایند جدا اجرا شد؛ پاسخ‌های توسعهٔ قبلی بازاستفاده شدند. پیگیری‌ها و تأییدهای ده سناریو ساختگی عملیاتی‌اند، نه گفت‌وگو یا بازبینی انسانی واقعی. آزمون‌های پیشین اکنون توسعه یا تاریخچه‌اند؛ برای ارزیابی تازه دوباره همان آزمون را تنظیم نکنید.')
    replace('README.md','راهنما: برای رابط واقعی،',
        f"راهنما: فایل `START_LIVE.ps1` کلید را پنهان می‌گیرد و تعرفه را بررسی می‌کند؛ ایندکس واقعی روی این دستگاه آماده است. دفتر تیم اکنون {cost['charged_or_reserved_usd']:.8f} دلار مصرف همراه رزرو دارد. سقف عملیاتی پیش‌فرض نیم دلار درخواست تازه را متوقف می‌کند؛ سقف تیم پنج دلار و باقی‌ماندهٔ محافظه‌کارانه {5-cost['charged_or_reserved_usd']:.8f} دلار است. موجودی پنل خوانده نشده است. سقف موقت ارزیابی به رابط منتقل نمی‌شود. دفتر مشترک حفظ شود؛ مرور خروجی‌های ذخیره‌شده رایگان است. راهنما در `docs/LIVE_RUN_FA.md` است.")
    replace('docs/REQUIREMENTS_FA.md','بخش ارزیابی:',evaluation.replace('ارزیابی:','بخش ارزیابی:',1).replace('docs/',''))
    replace('docs/REQUIREMENTS_FA.md','بخش داوری انسانی:',
        f"بخش داوری انسانی: همهٔ {ai['rows']} خروجی نسخهٔ اصلاح کیفیت، نمره و دلیل هوش مصنوعی و هش دارند. مقایسه با داور مدل جداست. دستیار در ساخت مشارکت دارد و بازبینی کور یا مستقل نیست. فرم انسانی همین نسخه خالی است؛ داوری مستقل و مقایسه با انسان هنوز لازم‌اند. نتیجه‌های هشتادوسه خروجی نسخهٔ دوم پیشین تاریخی حفظ شده‌اند.")
    replace('docs/ARCHITECTURE_V2_FA.md','مرحلهٔ ارزیابی:',evaluation.replace('ارزیابی:','مرحلهٔ ارزیابی:',1).replace('docs/',''))
    architecture=ROOT/'docs/ARCHITECTURE_V2_FA.md';text=architecture.read_text(encoding='utf8')
    if 'مرحلهٔ اصلاح کیفیت:' not in text:
        architecture.write_text(text+'\nمرحلهٔ اصلاح کیفیت: برنامهٔ تشخیص در همان استخراج، حفظ گزارش و اصلاحات، فیلتر منابع اداری، جست‌وجوی فنی کوتاه، سؤال تازه و ممیزی ادعا و شاهد اضافه شده‌اند. شرح قراردادها و محدودیت‌ها در [پیاده‌سازی اصلاح کیفیت](QUALITY_IMPLEMENTATION_FA.md) است. کنترل قطعی و پذیرش مدل صحت کامل معنا را تضمین نمی‌کنند.\n',encoding='utf8')
    replace('docs/AI_REVIEW_FA.md','وضعیت جاری:',review.replace('بازبینی:','وضعیت جاری:',1).replace('artifacts/','../artifacts/').replace('docs/AI_REVIEW_FA.md','QUALITY_REVISION_FA.md'))
    replace('docs/AI_REVIEW_FA.md','تفکیک:',
        'تفکیک: بخش‌های بعد دربارهٔ معماری اول‌اند. بازبینی هشتادوسه خروجی معماری دوم پیش از اصلاح در پوشهٔ تاریخی خودش باقی است. امتیاز صفر نامناسب یا بی‌پشتوانه، یک ناقص یا ارجاع عمومی و دو مناسبِ اطلاعات قابل مشاهده است. امتیاز کلی قضاوت جامع است؛ پرسش مشخصِ بی‌استناد می‌تواند دو بگیرد، ولی ارجاع عمومی معمولاً یک است. معیار ارتباط شاهد در نبود شاهد صفر است و با تعریف داور زمان اجرا یکسان نیست. ورودی سالم مقاومت خصمانه را اثبات نمی‌کند.')
    replace('docs/LIVE_RUN_FA.md','وضعیت:',evaluation.replace('ارزیابی:','وضعیت:',1).replace('docs/',''))
    replace('docs/LIVE_RUN_FA.md','مصرف:',
        f"مصرف: هزینهٔ کل تیم همراه رزرو {cost['charged_or_reserved_usd']:.8f} دلار است؛ تأییدشده {cost['confirmed_usd']:.8f} و نامعلومِ رزروشده {cost['uncertain_reserved_usd']:.8f} دلار. ارزیابی نهایی اصلاح کیفیت {m['new_charged_or_reserved_usd']:.8f} دلار افزوده و کل توسعه و ارزیابی این نوبت زیر سقف ۰٫۶۵ دلار اضافه بوده است. موجودی پنل خوانده نشده است. سقف پیش‌فرض نیم دلار درخواست تازه را متوقف می‌کند؛ سقف موقت به رابط منتقل نشده است.")
    replace('docs/LIVE_RUN_FA.md','مرحلهٔ بازبینی:',
        'مرحلهٔ بازبینی: فرم انسانی نسخهٔ اصلاح کیفیت در پوشهٔ نتیجه خالی است. گزارش اولیه، پیام‌های تکمیلی، پاسخ، قدم بعد، فرضیه و منابع را مستقل بخوانید و شش معیار و امتیاز کلی را با دلیل خودتان پر کنید. نام بازبین واقعی نوشته شود. فرم هوش مصنوعی را به نام انسان کپی نکنید. ابزار نمونهٔ زیر مربوط به صورت‌های تاریخی معماری دوم است؛ فرم تازه موجود را بازنویسی نکنید.')
    replace('docs/DEFENSE_FA.md','مرحلهٔ پنجم:',
        'مرحلهٔ پنجم: گزارش `QUALITY_REVISION_FA.md`، یافته‌های کیفیت و فرم بازبینی همین نسخه را بخوانید. مقایسهٔ زوجی و تعداد ارجاع‌های عمومی را جدا از موفقیت اجرایی توضیح دهید. برای ارائه از پاسخ ذخیره‌شده استفاده کنید؛ نتیجه‌های پیشین با برچسب تاریخی حفظ شده‌اند.')
    replace('docs/DEFENSE_FA.md','پرسش: چه کارهایی بیرون این بسته',
        'پرسش: چه کارهایی باقی‌اند؟ پاسخ: ضعف‌های معنایی ثبت‌شده، بازبینی مستقل انسان، آزمون سایت با اعتبارنامهٔ واقعی و ثبت سهم واقعی اعضا. اصلاحات و مقایسهٔ نسخهٔ اصلاح‌شده انجام شده‌اند، اما کیفیت کامل یا حل همهٔ گزارش‌ها ادعا نمی‌شود.')
    print('Measured quality documentation updated')

if __name__=='__main__':main()
