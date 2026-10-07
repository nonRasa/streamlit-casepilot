"""Build an honest Persian report from existing measured artifacts only."""
import collections, csv, json, os, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.accounting import Budget

def main():
    data=read_json(ROOT/'data'/'snapshot_manifest.json')
    results={(mode,p.parent.name):read_json(p) for mode in ('offline','live') for p in sorted((ROOT/'artifacts'/mode).glob('*/evaluation_metrics.json'))}
    live_present=any(mode=='live' for mode,_ in results)
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
            for category,cat in row['by_category'].items():
                category_name={'answerable':'قابل پاسخ','ambiguous':'مبهم','escalate':'نیازمند ارجاع'}[category]
                text.append(f"تفکیک دستهٔ {category_name} برای روش {name}: تعداد {cat['n']} و شاخص مسیر {cat['decision_rubric_proxy']:.1%} است؛ این عدد داوری انسانی کیفیت پاسخ نیست.")
        missed=[r for r in records if r['method']=='final' and r['source_recall_at_5'] is not None and r['source_recall_at_5']<1]
        if missed:
            text.append('شکست بازیابی در همین اجرا: پرونده‌های زیر دست‌کم یک منبع برچسب‌خورده را در پنج نتیجه نداشتند. پس از آزمون نهایی برای بهبود عدد، بازیابی تغییر داده نشده است.')
            for r in missed[:5]:
                text.append(f"پروندهٔ `{r['id']}`: پوشش {r['source_recall_at_5']:.1%}؛ تصمیم `"+r['decision']+'`؛ منابع بازیابی‌شده:\n\n```text\n'+'\n'.join(x['source_id'] for x in r['output']['retrieved'])+'\n```')
    text.extend([
        'تفسیر: پوشش منبع، صحت پاسخ را اثبات نمی‌کند. شاخص مسیر فقط عضویت تصمیم در مجموعهٔ مجاز است و پرسش محافظه‌کارانه می‌تواند آن را بالا ببرد. خروجی‌های مدل واقعی و داوری مستقل انسانی هنوز لازم‌اند. دادهٔ آزمون توسط نویسنده برای ساخت معیار بررسی شده و آزمون کاملاً کور بیرونی نیست.',
        'تغییر مؤثر: عنوان و نشانه‌های دامنه برای هدایت بازیابی استفاده شد؛ جایگاه مستندات رسمی، تنوع منابع و ادغام رتبهٔ واژه و سه‌نویسه اضافه شد. روش پایه همان دسترسی داده و حدود اجرایی را دارد. افزایش زمان اجرای نهایی همراه با پوشش گزارش شده و پنهان نشده است.',
        '## صحت عملیاتی',
        f"آزمون: تعداد {tests.get('tests','ناموجود')} آزمون محلی اجرا شده؛ شکست‌ها {tests.get('failures','ناموجود')} و خطاها {tests.get('errors','ناموجود')} است. آزمون‌ها شامل مجوز، نقش، تغییر پرونده، ویرایش، انقضا، تراکنش، ثبت هم‌زمان، قطع ارتباط، استناد جعلی و اتصال آزمایشی درگاه‌اند."])
    for (mode,split),manifest in results.items():
        label=('توسعه' if split.startswith('dev') else 'آزمون' if split.startswith('test') else 'ترکیبی')+(' آزمایشی' if mode=='offline' else ' زنده')
        text.append(f"سناریوی {label}: تعداد {manifest['scenarios']['n']} سناریوی چندنوبتی اجرا و تعداد {manifest['scenarios']['passed']} مورد موفق شدند. نتیجه از نظرها و وضعیت واقعی پایگاه خوانده شد؛ بازبین بازیگر برنامه‌ریزی‌شدهٔ آزمایش بود.")
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
        f"هزینه: تعداد درخواست ثبت‌شدهٔ درگاه {cost['requests']} و هزینهٔ تأییدشده {cost['confirmed_usd']:.6f} دلار است. هزینهٔ embedding صفر است؛ روش فعلی آن را نیاز ندارد. هزینهٔ ذخیره‌شدهٔ نامعلوم {cost['uncertain_reserved_usd']:.6f} دلار است. این اعداد قیمت اجرای آیندهٔ مدل را پیش‌بینی نمی‌کنند.",
        ('وضعیت واقعی: فایل اجرای زنده موجود است؛ کامل‌بودن و هزینهٔ آن در بخش جدا آمده است. کیفیت پاسخ‌ها و وضعیت داوری مستقل باید از فرم انسانی بررسی شود.' if live_present else 'وضعیت واقعی: کلید هنوز دریافت نشده است. گزارش زنده و داوری انسانی پاسخ‌ها تولید نشده‌اند. پس از دریافت کلید، اجرای کوچک توسعه، تثبیت مدل، اجرای نهایی و بازبینی انسانی طبق راهنما انجام شوند.')+' بودجهٔ پنج دلار برای کل تیم، همهٔ آماده‌سازی و آزمایش و بخش امتیازی است.',
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
    write_json(ROOT/'eval'/'human_review_rubric.json',{'score_0':'wrong, unsupported or harmful','score_1':'partly supported/useful; material uncertainty','score_2':'supported and appropriate to visible input/version','pending':True,'review_required':'Independent human reviewer; do not equate routing proxy with these scores.'})
    print('وضعیت: گزارش از شواهد موجود ساخته شد؛ امتیاز انسانی ساخته نشده است.')

if __name__=='__main__': main()
