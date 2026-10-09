"""Build an honest Persian report from existing measured artifacts only."""
import collections, csv, hashlib, json, os, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.accounting import Budget
from quality_result_files import result_paths

def main():
    data=read_json(ROOT/'data'/'snapshot_manifest.json')
    results={(mode,p.parent.name):read_json(p) for mode in ('offline','live') for p in sorted((ROOT/'artifacts'/mode).glob('*/evaluation_metrics.json'))}
    live_present=any(mode=='live' for mode,_ in results)
    full_path=ROOT/'artifacts'/'live'/'full_evaluation.json'
    full=read_json(full_path) if full_path.exists() else None
    full_complete=bool(full and full.get('complete'))
    smoke_path=ROOT/'artifacts'/'live'/'smoke'/'result.json'
    smoke=read_json(smoke_path) if smoke_path.exists() else None
    citation_path=ROOT/'artifacts'/'live'/'citation_fix_v3'/'result.json'
    citation_fix=read_json(citation_path) if citation_path.exists() else None
    tests=read_json(ROOT/'artifacts'/'test_results.json') if (ROOT/'artifacts'/'test_results.json').exists() else {}
    bonus=read_json(ROOT/'artifacts'/'adversarial_results.json')['summary'] if (ROOT/'artifacts'/'adversarial_results.json').exists() else {}
    ledger_path=Path(os.getenv('CASEPILOT_BUDGET_DB',str(ROOT/'runtime'/'team_budget.sqlite3')))
    cost=Budget(ledger_path).report() if ledger_path.exists() else {'budget_usd':5,'requests':0,'input_tokens':0,'output_tokens':0,'embedding_requests':0,'embedding_cost_usd':0,'confirmed_usd':0,'uncertain_reserved_usd':0,'charged_or_reserved_usd':0,'calls':[]}
    write_json(ROOT/'artifacts'/'api_usage.json',cost)
    with (ROOT/'artifacts'/'cost_ledger.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['id','at','model','reserved','charged','status','input_tokens','output_tokens','kind']); writer.writeheader(); writer.writerows(cost['calls'])
    text=['# گزارش پروژهٔ دستیار پیگیری پرونده',
          'وضعیت: این گزارش از فایل‌های اجرای موجود ساخته شده است. سیاست قطعی آزمایشی و نتایج اجرای زنده، در صورت وجود، با نام جدا گزارش می‌شوند. ارزیابی محلی، اجرای سایت را تأیید نمی‌کند.',
          '## مسئله و رفتار نهایی',
          'هدف: گزارش ناقص با شواهد مستند به پاسخ، پرسش یا ارجاع تبدیل شود؛ همان پرونده در نوبت‌های بعد با اصلاح واقعیت و تأیید انسانی ادامه پیدا کند. پاسخ پیشنهادی و خلاصهٔ نگه‌دارنده تولید می‌شوند. نظر و وضعیت و برچسب فقط روی رهگیر محلی، پس از تأیید مخصوص همان پیشنهاد، قابل تغییرند.',
          '## داده و ارزیابی',
          f"داده: تعداد {data['issue_count']} گزارش واقعی، تعداد {data['comments_retained']} نظر پس از پاک‌سازی، تعداد {data['docs_count']} منبع رسمی و تعداد {data['chunks']} قطعهٔ مجاز آماده‌اند. گفت‌وگوی کامل برای {data['comments_fetched_for_issues']} گزارش دریافت شده است؛ گفت‌وگوی {data['comments_not_fetched_for_issues']} گزارش کامل دریافت نشده و این وضعیت صریح ثبت است.",
          'تقسیم: مجموعهٔ نهایی شامل ۱۵ پروندهٔ توسعه و ۱۵ آزمون تازه است. آزمون مقدماتی بازنشسته شد؛ پس از اصلاح بازیابی روی توسعه، کد قفل و آزمون تازه انتخاب شد. تمام پرونده‌های ارزیابی و خانواده‌ها و نظرهایشان از بازیابی خارج‌اند. بندهای پاسخ‌دهندهٔ مستندات نیز حذف شده‌اند. این طراحی روی snapshot کنونی است و بازسازی تاریخی نیست.',
          '## مقایسهٔ اندازه‌گیری‌شده']
    v2_runs=sorted((ROOT/'artifacts/architecture_v2/live').glob('*/manifest.json'),key=lambda p:p.stat().st_mtime)
    v2_path=v2_runs[-1] if v2_runs else None
    v2=read_json(v2_path) if v2_path else None
    v2_index=read_json(ROOT/'data/index_v2_manifest.json') if (ROOT/'data/index_v2_manifest.json').exists() else None
    intro=['## معماری دوم؛ مسیر جاری',
           'پیاده‌سازی: چانک ساختاری و هم‌پوشانی، کش امبدینگ مبتنی بر متن و مدل، بازیابی واژگانی و برداری، ادغام رتبه، تنوع، بازرتبه‌بندی محدود و داوری جدا با یک اصلاح و داوری دوباره اضافه شده‌اند. تأیید انسانی و اجرای مجاز از مدل‌ها جدا هستند. شرح و نمودار در `ARCHITECTURE_V2_FA.md` آمده است.',
           'کنترل: سقف هر نوبت هشت فراخوانی، چهار سنت و ۱۸۰ ثانیه است. خطای استناد، رد داور، کمبود بودجه یا پایان مهلت به پاسخ محافظه‌کارانه می‌رسد. داور مدل جای داور انسانی نیست. امبدینگ و داوری آفلاین فقط بدل آزمایشی‌اند.']
    if v2_index: intro.append(f"ایندکس دوم: تعداد {v2_index['chunks']} چانک از {v2_index['sources']} منبع غربال‌شده، با هش مستقل و حذف همان خانواده‌های ارزیابی آماده شده است.")
    if v2: intro.append(f"آزمایش واقعی دوم: تعداد {v2['cases']} پروندهٔ توسعه با وضعیت تکمیل {v2['complete']}، تعداد درخواست تازه {v2['new_requests']} و هزینهٔ افزودهٔ ثبت‌شده یا رزروشده {v2['new_charged_or_reserved_usd']:.8f} دلار اجرا شد. این نمونه جای ارزیابی نهایی کیفیت نیست. علت توقف: `{v2['stopped_reason'] or 'بدون توقف'}`.")
    if v2_runs:
        intro.append('تاریخچهٔ توسعهٔ دوم: دو اجرای مقدماتی به ارجاع محافظه‌کارانه رسیدند. قرارداد نخست، توضیح مثبت داور را هم اشکال حساب می‌کرد؛ اکنون هر معیار امتیاز و دلیل دارد و فقط امتیاز پایین‌تر از دو اشکال محسوب می‌شود. کنترل قطعی همچنان مقدم است. نتیجه‌ها و کد هر اجرا حفظ شده‌اند؛ تنظیم فقط بر توسعه انجام شد.')
        latest_rows=[json.loads(line) for line in (v2_path.parent/'answers.jsonl').read_text(encoding='utf-8').splitlines() if line]
        intro.append(f"نتیجهٔ نمونهٔ توسعه: تعداد {sum(r['output']['validation_error'] is None for r in latest_rows)} پاسخ از داوری گذشتند و تعداد {sum(r['output']['repair_count'] for r in latest_rows)} اصلاح انجام شد. عبور از داور مدل به معنی تأیید مستقل انسانی نیست.")
        intro.append('محدودیت مشاهده‌شده: در پاسخ جاری `GH11528`، درخواست تأیید خروجی تابع و کلاس بخشی از نمونه‌کد موجود را تکرار می‌کند؛ داور مدل آن را کامل تشخیص نداده است. پذیرش مدل به معنی صحت معنایی نیست. جزئیات در `V2_DEVELOPMENT_NOTES_FA.md` ثبت شده‌اند و فرم انسانی اجرای دوم هنوز خالی است.')
    build=ROOT/'artifacts/architecture_v2/embedding_build_live.json'
    if build.exists():
        embedded=read_json(build); intro.append(f"امبدینگ واقعی: تعداد {embedded['chunks']} چانک با مدل `{embedded['identity']['model']}` و بردار {embedded['dimensions']} بعدی آماده و در کش خصوصی محلی ذخیره شدند. خلاصهٔ هزینه و دسته‌ها همراه نتیجه است؛ کش و کلید داخل بسته نیستند.")
    final_folder=ROOT/'artifacts/architecture_v2/final_evaluation'
    if (final_folder/'ai_review_manifest.json').exists():
        final=read_json(final_folder/'manifest.json'); ai2=read_json(final_folder/'ai_review_manifest.json')
        comparison=read_json(final_folder/'judge_ai_comparison.json')
        intro += [f"ارزیابی کامل دوم: تعداد {final['comparison_outputs']} پاسخ برای دو روش روی پانزده توسعه و پانزده آزمون تازه، با کد قفل‌شده ثبت شدند. تعداد {ai2['scenario_rows']} نوبت در ده سناریو اجرا شدند؛ تعداد موفق {final['scenarios']['passed']} و پیکربندی ثابت {final['configuration_unchanged']} است. یک خطای درگاه در مقایسه و یکی در سناریوی دهم حفظ شدند؛ سناریوی دهم پیش از ثبت متوقف شد.",
            f"بازبینی جاری: همهٔ {ai2['rows']} پاسخ نهایی توسط این دستیار با نمره و دلیل مختص همان پاسخ بررسی شدند؛ هزینهٔ تازهٔ بازبینی متیس صفر است. از {comparison['comparable_outputs']} خروجی پذیرفتهٔ داور، {comparison['accepted_with_ai_overall_below_2']} مورد کیفیت کلی کمتر از دو گرفتند. این داوری مستقل انسانی یا نرخ خطای کالیبره‌شده نیست. فرم انسانی خالی است.",
            'نتیجهٔ کیفیت: پوشش منبع پایین، سؤال‌های تکراری و انتقال ادعا از منابع نامرتبط باقی‌اند؛ برتری معنایی مسیر کامل بر پایه در این نمونه دیده نشد. عدد مسیر تصمیم، درصد صحت نیست. جدول تفکیکی و محدودیت‌ها در [ارزیابی کامل دوم](docs/V2_FINAL_EVALUATION_FA.md) و موارد مشخص در [یافته‌های بازبینی](docs/V2_FINAL_FINDINGS_FA.md) آمده‌اند. هیچ تنظیم یا خروجی آزمون بر اساس بازبینی تغییر نکرده است.',
            f"هزینهٔ مرحلهٔ کامل دوم: تعداد {final['new_requests']} درخواست تازه، مصرف تأییدشده {final['new_confirmed_usd']:.8f} دلار و مصرف همراه رزرو {final['new_charged_or_reserved_usd']:.8f} دلار، زیر سقف موقت نود سنت اضافه. جزئیات مصرف کل تیم در بخش هزینه است."]
    quality_folder=ROOT/'artifacts/quality_revision/final_evaluation'
    if (quality_folder/'ai_review_manifest.json').exists():
        qm=read_json(result_paths(quality_folder)[0]); qr=read_json(quality_folder/'ai_review_manifest.json')
        pair=qr['paired_fresh']; current=['## نسخهٔ اصلاح کیفیت؛ مسیر جاری',
            'اصلاح: جست‌وجوی متمرکز، فیلتر شاهد اداری، حفظ گزارش و اصلاحات، فهرست آزمایش‌های انجام‌شده، تفکیک درخواست قابلیت از خطا و برنامهٔ تشخیص اضافه شده‌اند. داور رابطهٔ ادعا و شاهد و تازه‌بودن پرسش را ممیزی می‌کند؛ قرارداد نامعتبر به ارجاع امن می‌رسد. همان داده و کش امبدینگ حفظ شدند.',
            f"ارزیابی جاری: تعداد {qm['attempted_comparisons']} مقایسهٔ پردازش‌شده روی پنج پروندهٔ توسعهٔ هدفمند و پانزده آزمون تازه؛ ده سناریو با {qm['scenarios']['passed']} موفق. نسخهٔ پیشین در فرایند جدا از کد قفل‌شدهٔ خودش اجرا شد؛ پاسخ‌های توسعهٔ قدیمی بازاستفاده شدند. کد پس از مشاهدهٔ آزمون تازه تغییر نکرد.",
            f"مقایسهٔ زوجی تازه: تعداد بهتر {sum(x['difference']>0 for x in pair)}، برابر {sum(x['difference']==0 for x in pair)} و بدتر {sum(x['difference']<0 for x in pair)} در قضاوت جامع این دستیار. این نمره‌ها درصد صحت یا داوری مستقل نیستند."]
        for variant,label in [('previous','قبلی'),('revised','اصلاح‌شده')]:
            scores=qr['summary']['test_fresh'][variant]['overall_counts']
            current.append(f"کیفیت آزمون تازهٔ نسخهٔ {label}: امتیاز صفر {scores.get('0',0)}، یک {scores.get('1',0)} و دو {scores.get('2',0)}. صفر نامناسب یا بی‌پشتوانه، یک ناقص یا ارجاع عمومی و دو مناسبِ ورودی قابل مشاهده است؛ میانگین مکانیکی معیارها نیست.")
        current += [f"بازبینی جاری: همهٔ {qr['rows']} خروجی واقعی با هش، دلیل و شش معیار توسط این دستیار بررسی شدند؛ درخواست متیس برای این بازبینی صفر بود. فرم انسانی خالی است. نمونه کوچک و غیرتصادفی است؛ تصاویر و کد گزارش‌ها اجرا نشده‌اند. جزئیات در [ارزیابی اصلاح کیفیت](docs/QUALITY_REVISION_FA.md) و [یافته‌های کیفیت](docs/QUALITY_FINDINGS_FA.md) آمده‌اند.",
            f"هزینهٔ نهایی این نسخه: مصرف همراه رزرو {qm['new_charged_or_reserved_usd']:.8f} دلار؛ همهٔ توسعه و ارزیابی این نوبت زیر سقف ۰٫۶۵ دلار اضافه روی همان دفتر تیم قرار دارند. هزینهٔ کل تیم در بخش هزینهٔ همین گزارش از دفتر فعلی خوانده می‌شود.",
            'باقی‌مانده: ضعف‌های معنایی ثبت‌شده، داوری مستقل انسانی، آزمون سایت کاربر و مشارکت واقعی اعضا. ارجاع امن به معنی حل مشکل نیست. تنظیم دوباره روی همین آزمون تازه انجام نشده و بهبود بعدی به نسخه و آزمون تازه نیاز دارد.',
            'تاریخچه: بخش بعد دربارهٔ معماری دوم پیش از اصلاح کیفیت است؛ اعداد و ضعف‌های آن زمان به خروجی جدید نسبت داده نمی‌شوند.']
        intro[0]='## تاریخچهٔ معماری دوم پیش از اصلاح کیفیت'
        intro=[s.replace('بازبینی جاری:','بازبینی تاریخی:').replace('در پاسخ جاری `GH11528`','در پاسخ تاریخی `GH11528`') for s in intro]
        intro=current+intro
    else:
        intro.append('باقی‌مانده: اصلاح کیفیت با نسخه و ارزیابی تازه، مقایسهٔ داور مدل با انسان، بازبینی مستقل، اجرای سایت کاربر و ثبت سهم واقعی اعضا. سقف عملیاتی پیش‌فرض نیم دلار تغییر نکرده و اکنون درخواست پولی تازه را متوقف می‌کند؛ پاسخ‌های موجود رایگان قابل مرورند.')
    intro+=[
            '## تاریخچهٔ ارزیابی معماری اول',
            'تاریخچه: نتیجه‌های سی پرونده، ده سناریو و فرم هوش مصنوعی در بخش‌های بعد مربوط به کد قفل‌شدهٔ معماری اول‌اند. آن کد با هش اصلی حفظ شده است؛ اعداد آن به معماری دوم نسبت داده نمی‌شوند.']
    text[2:2]=intro
    for (mode,split),manifest in results.items():
        label=('توسعه' if split.startswith('dev') else 'آزمون تازه' if split.startswith('test') else 'ترکیبی')+(' آزمایشی' if mode=='offline' else ' زنده')
        if '_sample_' in split: label+=' نمونهٔ کوچک'
        records_path=ROOT/'artifacts'/mode/split/'answers.jsonl'
        records=[json.loads(line) for line in records_path.read_text(encoding='utf-8').splitlines() if line] if records_path.exists() else []
        text.append(f"وضعیت اجرای {label}: تعداد پروندهٔ انتخاب‌شده {manifest['selected_cases']}؛ تکمیل اجرا {manifest['complete']}؛ دلیل توقف {manifest['stopped_reason'] or 'بدون توقف'}. نتایج ناقص با اجرای کامل قابل مقایسه نیستند.")
        for method in ('baseline','final'):
            row=manifest['metrics'][method]; name='پایه' if method=='baseline' else 'نهایی'
            recall=row.get('source_recall_at_5'); value=f'{recall:.1%}' if recall is not None else 'ناموجود'
            proxy=f"{row['decision_rubric_proxy']:.1%}" if row['decision_rubric_proxy'] is not None else 'ناموجود'
            latency=f"{row['median_latency_seconds']:.3f}" if row['median_latency_seconds'] is not None else 'ناموجود'
            text.append(f"نتیجهٔ {label} برای روش {name}: پوشش منبع در پنج قطعه {value} روی {row.get('recall_labelled_n',row['n'])} پروندهٔ برچسب‌خورده؛ شاخص مسیر تصمیم {proxy}؛ میانهٔ زمان هر نوبت {latency} ثانیه. تعداد پرونده‌ها {row['n']} است.")
            group=[r for r in records if r['method']==method]; counts=collections.Counter(r['decision'] for r in group)
            text.append(f"توزیع تصمیم {name}: پاسخ {counts['answer']}؛ پرسش {counts['ask']}؛ ارجاع {counts['escalate']}. تعداد فراخوانی سیاست یا مدل در نوبت‌های موفق {sum(r['model_calls'] for r in group)}؛ تعداد درخواست واقعی در همین نوبت‌ها {sum(r['usage'].get('provider_requests',0) for r in group)}. هزینهٔ خطاها و سناریوها در دفتر کل تیم هم لحاظ می‌شود.")
            text.append(f"اعتبارسنجی روش {name}: تعداد پاسخ‌های ردشده از کنترل ساختار یا شاهد {row['validation_failures']} است. پاسخ ردشده با ارجاع محافظه‌کارانه جایگزین می‌شود و از نتایج حذف نمی‌شود.")
            for category,cat in row['by_category'].items():
                category_name={'answerable':'قابل پاسخ','ambiguous':'مبهم','escalate':'نیازمند ارجاع'}[category]
                text.append(f"تفکیک دستهٔ {category_name} برای روش {name}: تعداد {cat['n']} و شاخص مسیر {cat['decision_rubric_proxy']:.1%} است؛ این عدد داوری انسانی کیفیت پاسخ نیست.")
        missed=[r for r in records if r['method']=='final' and r['source_recall_at_5'] is not None and r['source_recall_at_5']<1]
        rejected=[r for r in records if r['validation_error']]
        if rejected:
            text.append('خروجی‌های ردشده: موارد زیر در نتایج باقی مانده و با ارجاع محافظه‌کارانه جایگزین شده‌اند؛ برای بهبود عدد حذف یا دوباره تولید نشده‌اند.')
            for r in rejected:
                text.append(f"پروندهٔ `{r['id']}` با روش `"+r['method']+'`: کد `'+r['validation_error']+'`.')
        if missed:
            text.append('شکست بازیابی در همین اجرا: پرونده‌های زیر دست‌کم یک منبع برچسب‌خورده را در پنج نتیجه نداشتند. پس از آزمون نهایی برای بهبود عدد، بازیابی تغییر داده نشده است.')
            for r in missed[:5]:
                text.append(f"پروندهٔ `{r['id']}`: پوشش {r['source_recall_at_5']:.1%}؛ تصمیم `"+r['decision']+'`؛ منابع بازیابی‌شده:\n\n```text\n'+'\n'.join(x['source_id'] for x in r['output']['retrieved'])+'\n```')
    if smoke:
        text.extend([
            '## آزمایش کوچک اتصال واقعی',
            f"وضعیت: فقط یک پروندهٔ توسعه با مدل `{smoke['model']}` و سقف خروجی {smoke['max_output_tokens']} توکن اجرا شد. سقف محلی این مرحله {smoke['pilot_cap_usd']:.2f} دلار بود. نتیجهٔ این اجرا `{smoke['status']}` است و ارزیابی کامل زنده محسوب نمی‌شود.",
            f"مصرف: تعداد توکن ورودی {smoke['cost']['input_tokens']} و خروجی {smoke['cost']['output_tokens']} بود. هزینهٔ محاسبه‌شده از مصرف گزارش‌شده و تعرفهٔ رسمی {smoke['cost']['confirmed_usd']:.8f} دلار است. این عدد از موجودی پنل خوانده نشده است.",
            'کنترل: در نخستین پاسخ، نقل‌قول عین متن منبع نبود و اعتبارسنج آن را رد کرد. خروجی به ارجاع محافظه‌کارانه تبدیل شد؛ هیچ اقدام عمومی ثبت و هیچ تلاش خودکار دوباره انجام نشد. پاسخ خام نهان‌شده داخل بستهٔ تحویل قرار نمی‌گیرد.',
            ('ادامه: اصلاح استناد و ارزیابی کامل بعدی در بخش‌های جدا ثبت شده‌اند؛ داوری مستقل انسانی باقی است.' if full_complete else 'اصلاح بعدی: نتیجهٔ اصلاح استناد در بخش بعد ثبت شده است. اجرای کامل زنده و داوری مستقل انسانی هنوز انجام نشده‌اند.' if citation_fix else 'باقی‌مانده: اصلاح دستور و ارزیابی پاسخ‌های واقعی تنها بر مجموعهٔ توسعه انجام شود. اجرای کامل زنده و داوری مستقل انسانی هنوز انجام نشده‌اند.')] if smoke['status']=='validation_failed' else [
            '## آزمایش کوچک اتصال واقعی',
            f"وضعیت: نتیجهٔ آزمایش `{smoke['status']}` است. جزئیات، مصرف و محدودیت‌ها در فایل آزمایش ثبت‌اند؛ این آزمایش جای ارزیابی کامل و داوری مستقل انسانی را نمی‌گیرد."])
    if citation_fix:
        text.extend([
            '## اصلاح و آزمون استناد واقعی',
            'علت: مدل در نخستین نقل‌قول، نشانی پیوند داخل متن مستند را حذف کرد. اکنون مدل فقط شناسهٔ قطعهٔ شاهد را انتخاب می‌کند؛ برنامه متن اصلی همان منبع را درج می‌کند. قالب انتخاب با پاسخ ساخت‌یافته درخواست می‌شود و تطبیق سخت‌گیرانهٔ متن همچنان برقرار است. شناسهٔ جعلی یا شاهد متعلق به منبع دیگر پذیرفته نمی‌شود.',
            f"نتیجه: وضعیت بررسی نهایی `{citation_fix['status']}`؛ تعداد درخواست تازه در همین بررسی {citation_fix['new_provider_requests']} و هزینهٔ آن {citation_fix['new_cost_usd']:.8f} دلار است. این بررسی فقط روی پروندهٔ توسعهٔ `GH9218` انجام شد.",
            'تاریخچه: تلاش نخست اصلاح از کنترل ساختار پاسخ عبور نکرد و متوقف شد؛ سپس قالب اجباری افزوده شد. یک اجرای محلی با شناسهٔ تکراری، نتیجهٔ قبلی را بدون درخواست شبکه بازگرداند؛ اجرای نهایی با شناسهٔ تازه انجام شد. همهٔ هزینه‌ها در دفتر مشترک باقی مانده‌اند.',
            'محدودیت: موفقیت تطبیق نقل‌قول به‌معنای صحت معنایی تمام توصیه‌ها نیست. پیشنهاد مدل دربارهٔ ذخیره‌سازی روی دیسک و استنباط علت، به بازبینی انسانی نیاز دارد. هیچ تأیید یا اقدام عمومی در این آزمون انجام نشد. بازیابی و دادهٔ آزمون تغییر نکردند؛ نتایج آفلاین قبلی، کیفیت دستور زندهٔ جدید را نمی‌سنجند.',
        ])
    text.extend([
        'تفسیر: پوشش منبع، صحت پاسخ را اثبات نمی‌کند. شاخص مسیر فقط عضویت تصمیم در مجموعهٔ مجاز است و پرسش محافظه‌کارانه می‌تواند آن را بالا ببرد. کیفیت معنایی پاسخ و فایدهٔ سؤال نیازمند داوری مستقل انسانی‌اند. دادهٔ آزمون توسط نویسنده برای ساخت معیار بررسی شده و آزمون کاملاً کور بیرونی نیست.',
        'تغییر مؤثر: عنوان و نشانه‌های دامنه برای هدایت بازیابی استفاده شد؛ جایگاه مستندات رسمی، تنوع منابع و ادغام رتبهٔ واژه و سه‌نویسه اضافه شد. روش پایه همان دسترسی داده و حدود اجرایی را دارد. افزایش زمان اجرای نهایی همراه با پوشش گزارش شده و پنهان نشده است.',
        '## صحت عملیاتی',
        f"آزمون: تعداد {tests.get('tests','ناموجود')} آزمون محلی اجرا شده؛ شکست‌ها {tests.get('failures','ناموجود')} و خطاها {tests.get('errors','ناموجود')} است. آزمون‌ها شامل مجوز، نقش، تغییر پرونده، ویرایش، انقضا، تراکنش، ثبت هم‌زمان، قطع ارتباط، استناد جعلی و اتصال آزمایشی درگاه‌اند."])
    for (mode,split),manifest in results.items():
        label=('توسعه' if split.startswith('dev') else 'آزمون' if split.startswith('test') else 'ترکیبی')+(' آزمایشی' if mode=='offline' else ' زنده')
        text.append(f"سناریوی {label}: تعداد {manifest['scenarios']['n']} سناریوی چندنوبتی اجرا و تعداد {manifest['scenarios']['passed']} مورد موفق شدند. نتیجه از نظرها و وضعیت واقعی پایگاه خوانده شد؛ بازبین بازیگر برنامه‌ریزی‌شدهٔ آزمایش بود.")
    if full:
        text.extend([
            '## اجرای کامل مدل واقعی',
            f"تکمیل: وضعیت تکمیل کل ارزیابی {full['complete']} است. تعداد درخواست تازه در اجرای نهایی {full['new_provider_requests']} و هزینهٔ تأییدشدهٔ همین اجرا {full['new_confirmed_usd']:.8f} دلار است. سقف تجمعی محلی {full['cumulative_cap_usd']:.2f} دلار بود.",
            f"ثبات: تغییرنکردن کد و دادهٔ قفل‌شده {full['configuration_unchanged']} است؛ تعداد بخش‌های ثبت‌شده {len(full['runs'])} و تعداد هش‌های پیکربندی متمایز {len({r['configuration_hash'] for r in full['runs']})} است. هیچ تنظیم بر اساس خروجی آزمون انجام نشد. پاسخ‌ها، ردپاها، سناریوها و هش‌ها در پوشه‌های اجرای زنده ثبت شده‌اند.",
            'اختلال اتصال: پیش از اجرای نهایی، یک درخواست به پایان مهلت اتصال رسید و هیچ پرونده‌ای ارزیابی نشد. تلاش ناموفق جدا حفظ شد؛ پس از دریافت پاسخ اتصال بدون کلید، اجرا به‌صورت کنترل‌شده از سر گرفته شد. هزینهٔ نامعلوم آن آزاد یا صفر فرض نشده و در دفتر مشترک باقی است.',
            'مرز نتیجه: سناریوهای چندنوبتی شامل پاسخ‌های تکمیلی طراحی‌شده‌اند و بازبین برنامه‌ریزی‌شده دارند. این اجرا کیفیت معنایی همهٔ توصیه‌ها، داوری انسانی یا کارکرد سایت را تأیید نمی‌کند.',
        ])
    ai_manifest_path=ROOT/'eval'/'ai_review_manifest.json'
    if ai_manifest_path.exists():
        ai=read_json(ai_manifest_path)
        ai_form=ROOT/ai['form']['path']
        if hashlib.sha256(ai_form.read_bytes()).hexdigest()!=ai['form']['sha256']:
            raise ValueError('AI review form changed; refresh its provenance before reporting.')
        text.extend([
            '## بازبینی معنایی با هوش مصنوعی',
            f"تکمیل: تعداد {ai['reviewed_rows']} پاسخ ذخیره‌شده برای {ai['reviewed_cases']} پرونده، در شش معیار صفر تا دو، با توضیح مختص هر پاسخ در فایل `ai_review.csv` ارزیابی شده‌اند. نام بازبین «بازبین هوش مصنوعی — Codex» است. این دستیار در پیاده‌سازی هم مشارکت داشته و داوری مستقل یا کور نیست؛ داوری مستقل انسانی هنوز باقی است.",
            'روش: متن کامل گزارش اولیه، پاسخ کاربر، استدلال و فرضیه‌های خلاصه نگه‌دارنده، نقل‌قول‌ها و نسخه منابع بررسی شدند. شاخص مسیر تصمیم جای امتیاز معنایی قرار نگرفت. سه ارجاع ناشی از استناد نامعتبر به‌صورت ایمن ولی حل‌نشده امتیاز گرفتند. خروجی سناریوهای چندنوبتی خارج از دامنه این بازبینی است.',
        ])
        for group in ai['summary']:
            split_name='توسعه' if group['split']=='dev' else 'آزمون'
            method_name='پایه' if group['method']=='baseline' else 'نهایی'
            counts=group['overall_counts']
            text.append(f"نتیجهٔ {split_name} برای روش {method_name}: از {group['n']} پاسخ، امتیاز کلی صفر برای {counts['0']} پاسخ، یک برای {counts['1']} پاسخ و دو برای {counts['2']} پاسخ ثبت شد. این‌ها قضاوت ترتیبی یک بازبین هوش مصنوعی‌اند؛ درصد صحت یا نتیجه آماری تعمیم‌پذیر نیستند.")
        text.extend([
            'یافته‌ها: پرسیدن دوباره اطلاعات موجود، نسبت دادن علت به گزارش مشابه، اشتباه گرفتن تنظیم مقدار دکمه با تغییر وضعیت صفحه و تعمیم راهکار میان نسخه‌ها دیده شد. برای نمونه در `GH12607` حذف دستی فایل قبلاً آزموده شده بود؛ در `GH16732` کلید ثابت و آزمایش‌های کنترل قبلاً گزارش شده بودند. تطبیق عینی نقل‌قول، این خطاهای معنایی را به‌تنهایی نمی‌گیرد.',
            'نسخه: در `GH6182` پیشنهاد `hash_funcs` با نسخه ۱٫۱۸٫۱ اعلام‌شده سازگار نیست؛ بررسی [کد رسمی همان برچسب](https://raw.githubusercontent.com/streamlit/streamlit/1.18.1/lib/streamlit/runtime/caching/cache_data_api.py) نبود این پارامتر در امضای دکوراتور را تأیید کرد. این منبع فقط برای داوری نسخه خوانده شد و وارد بازیابی عامل نشد.',
            'مصرف: این بازبینی هیچ درخواست تازه‌ای به متیس نفرستاد و هزینه افزوده متیس صفر است. کد مدل، بازیابی، داده و پاسخ‌های آزمون تغییر نکردند. فرم انسانی اصلی حفظ شده و نسخه خالی آن در `human_review_template.csv` نیز موجود است. ثبت نام یک انسان و امتیازهای مستقل او همچنان باید توسط همان بازبین انجام شود.',
        ])
    text.extend([
        '## شکست‌ها و اصلاحات',
        'شکست اول: اتصال‌های پایگاه پس از خروج از زمینه بسته نمی‌شدند و در ویندوز پاک‌سازی پایگاه موقت خطا می‌داد. اتصال بسته‌شونده اضافه و دمو و آزمون تکرار شدند.',
        'شکست دوم: توضیحات جانبی و مولد خودکار صفحات به‌جای شاهد فنی وارد پاسخ می‌شدند. بخش اطلاعات جانبی و مؤلفه‌های تولیدکننده از متن شاهد حذف و متن راهنمای توابع نسخه‌دار افزوده شد.',
        'شکست سوم: جایگاه زیاد گزارش‌های مشابه، مستندات مفید را عقب می‌راند. اصلاح بازیابی روی توسعه انجام و آزمون قبلی بازنشسته شد؛ آزمون تازه پس از قفل انتخاب شد.',
        'شکست چهارم: پاک‌سازی اشاره به حساب، تزئینگر پایتون را هم تغییر می‌داد. داده از پاسخ خام ذخیره‌شده بازسازی و پاک‌سازی به متن بیرون بلوک کد محدود شد.',
        'شکست پنجم: پاک‌سازی رایانامه پس از تبدیل ردپا به قالب JSON، در برخی متن‌های چندخطی قالب را خراب می‌کرد. پاک‌سازی روی مقدارهای متنی پیش از تبدیل انجام و آزمون رگرسیون اضافه شد. نوت‌بوک توسعه پس از اصلاح بدون خطا اجرا شد؛ تغییر بازیابی یا دستور مدل بر اساس آزمون نهایی انجام نشد.',
        'شکست ششم: توکن سرویس نقشه در نمونه‌کد یک گزارش عمومی از پاک‌سازی جا مانده و ارسال مخزن مسدود شد. پوشاندن این الگو، آزمون رگرسیون و کنترل محتوای بسته اضافه شدند. داده و خروجی‌ها بازسازی شدند؛ هیچ تنظیم بازیابی یا دستور مدل بر اساس نتیجهٔ آزمون تغییر نکرد.',
        'محدودیت باقی‌مانده: بازیابی واژگانی معنا را کامل نمی‌فهمد، مسیر نسخه یک حل‌کنندهٔ کامل نیست، استناد تطبیق معنایی را تضمین نمی‌کند، و داوری مسیر محافظه‌کارانه جای سنجش فایدهٔ سؤال را نمی‌گیرد. نمونه‌های شکست در خروجی پرونده‌ها قابل بررسی‌اند.',
        '## هزینه و اجرای واقعی',
        f"هزینه: تعداد درخواست ثبت‌شدهٔ درگاه {cost['requests']} و هزینهٔ محاسبه‌شده از مصرف تأییدشدهٔ توکن {cost['confirmed_usd']:.8f} دلار است. تعداد درخواست امبدینگ {cost['embedding_requests']} و هزینهٔ ثبت‌شده یا رزروشدهٔ امبدینگ {cost['embedding_cost_usd']:.8f} دلار است. هزینهٔ ذخیره‌شدهٔ نامعلوم {cost['uncertain_reserved_usd']:.6f} دلار است. جمع مصرف و رزرو {cost['charged_or_reserved_usd']:.8f} دلار است. این اعداد از دفتر مشترک و تعرفه‌اند؛ موجودی پنل نیستند.",
        ('وضعیت واقعی: فایل اجرای زنده موجود است؛ کامل‌بودن و هزینهٔ آن در بخش جدا آمده است. کیفیت پاسخ‌ها و وضعیت داوری مستقل باید از فرم انسانی بررسی شود.' if live_present else 'وضعیت واقعی: کلید دریافت و آزمایش کوچک انجام شده است؛ ارزیابی کامل زنده و داوری مستقل انسانی هنوز انجام نشده‌اند.' if smoke else 'وضعیت واقعی: کلید هنوز دریافت نشده است. گزارش زنده و داوری انسانی پاسخ‌ها تولید نشده‌اند. پس از دریافت کلید، اجرای کوچک توسعه، تثبیت مدل، اجرای نهایی و بازبینی انسانی طبق راهنما انجام شوند.')+' بودجهٔ پنج دلار برای کل تیم، همهٔ آماده‌سازی و آزمایش و بخش امتیازی است.',
        '## مسیر امتیازی',
        f"مطالعه: تعداد {bonus.get('unique_attack_cases',0)} ورودی ساخته‌شده در چهار خانواده با حذف کنترل مقایسه شدند. نسخهٔ محافظت‌شده {bonus.get('guarded_contained',0)} مورد را مهار کرد؛ نمونه‌های سالم موفق {bonus.get('positive_controls_passed',0)} مورد بودند. این مطالعه صحت مرز کد را می‌سنجد و مقاومت مدل واقعی را اثبات نمی‌کند. دامنهٔ امتیاز نیازمند هماهنگی منتور است.",
        '## مشارکت و بازتولید',
        'مشارکت: پیاده‌سازی و آماده‌سازی این نسخه با کمک دستیار کدنویسی انجام شده است. نام اعضا و سهم واقعی داده، آزمایش، بازبینی و ارائه هنوز از طرف گروه اعلام نشده؛ این قسمت باید با مشارکت واقعی تکمیل شود و سهم ساختگی درج نشده است.',
        'بازتولید: کد، نوت‌بوک، دادهٔ ثابت، فهرست هش‌ها، قرارداد ابزار، سناریو، آزمون، گردش‌کار و راهنمای اجرا در بسته هستند. اجرای محلی بدون شبکه و بدون کلید ممکن است. برای اجرای سایت، نشانی سرور و چهار اعتبارنامه توسط کاربر تنظیم می‌شوند.',
    ])
    (ROOT/'report.md').write_text('\n\n'.join(text)+'\n',encoding='utf-8')
    review=ROOT/'eval'/'human_review.csv'
    if not review.exists():
        with review.open('w',encoding='utf-8-sig',newline='') as f:
            fields=['case_id','split','method','evidence_relevance_0_2','claim_support_0_2','version_fit_0_2','next_step_usefulness_0_2','avoids_repeated_check_0_2','overall_0_2','reviewer','notes']
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            for c in read_json(ROOT/'eval'/'cases.json'):
                for method in ('baseline','final'): w.writerow({'case_id':c['id'],'split':c['split'],'method':method})
    rubric=ROOT/'eval'/'human_review_rubric.json'
    if not rubric.exists():
        write_json(rubric,{'score_0':'wrong, unsupported or harmful','score_1':'partly supported/useful; material uncertainty','score_2':'supported and appropriate to visible input/version','pending':True,'review_required':'Independent human reviewer; do not equate routing proxy with these scores.'})
    print('وضعیت: گزارش از شواهد موجود ساخته شد؛ امتیاز انسانی ساخته نشده است.')

if __name__=='__main__': main()
