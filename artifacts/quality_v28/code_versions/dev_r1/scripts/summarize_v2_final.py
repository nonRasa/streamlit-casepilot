"""Summarize frozen measurements and separately authored AI reviews, no network."""
import collections,csv,hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.roles import CRITERIA

def main():
    folder=ROOT/'artifacts/architecture_v2/final_evaluation'; m=read_json(folder/'manifest.json')
    review=read_json(folder/'ai_review.json'); packets=read_json(folder/'ai_review_packets.json')
    require(len(review)==len(packets) and {r['review_id'] for r in review}=={r['review_id'] for r in packets},'incomplete_review','بازبینی همهٔ پاسخ‌ها لازم است.')
    by_id={p['review_id']:p for p in packets}
    for r in review:
        require(r['output_sha256']==by_id[r['review_id']]['output_sha256'],'review_mismatch','بازبینی مربوط به پاسخ دیگری است.')
        require(set(r['scores'])==set(CRITERIA) and all(type(x) is int and x in (0,1,2) for x in r['scores'].values()) and r['overall'] in (0,1,2) and len(r['notes'])>30,'invalid_review','امتیاز یا دلیل بازبینی کامل نیست.')
    fields=['review_id','kind','case_id']+['ai_'+c+'_0_2' for c in CRITERIA]+['ai_overall_0_2','reviewer','notes','output_sha256']
    with (folder/'ai_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in review:
            p=by_id[r['review_id']]
            w.writerow(dict(review_id=r['review_id'],kind=p['kind'],case_id=p['case_id'],
                **{'ai_'+c+'_0_2':r['scores'][c] for c in CRITERIA},ai_overall_0_2=r['overall'],reviewer='بازبین هوش مصنوعی — Codex',notes=r['notes'],output_sha256=r['output_sha256']))
    summary={}
    for split in ('dev','test_fresh'):
        summary[split]={}
        for variant in ('baseline','full'):
            group=[r for r in review if r['review_id'].startswith(split+'/'+variant+'/')]
            summary[split][variant]={'n':len(group),'overall_counts':dict(collections.Counter(r['overall'] for r in group)),
                'criterion_counts':{c:dict(collections.Counter(r['scores'][c] for r in group)) for c in CRITERIA}}
    scenario_reviews=[r for r in review if by_id[r['review_id']]['kind']=='scenario']
    outputs={r['split']+'/'+r['variant']+'/'+r['id']:r['output'] for r in [json.loads(s) for s in (folder/'answers.jsonl').read_text(encoding='utf-8').splitlines() if s]}
    for s in read_json(folder/'multi_turn_results.json'):
        for i,out in enumerate(s['turns']): outputs[s['id']+'/'+str(i+1)]=out
    comparable=[]
    for r in review:
        out=outputs[r['review_id']]; judge=out.get('judge') or {}
        # Rejected-draft scores do NOT describe the safe fallback delivered instead.
        if not out['validation_error'] and judge.get('verdict')=='accept':
            compared=[c for c in CRITERIA if c!='injection_resistance' and (c!='relevance' or by_id[r['review_id']]['sources'])]
            comparable.append({'review_id':r['review_id'],'kind':by_id[r['review_id']]['kind'],'ai_overall':r['overall'],
                'compared_criteria':compared,'disagreements':[c for c in compared if r['scores'][c]!=judge['scores'][c]],
                'model_scores':judge['scores'],'ai_scores':r['scores']})
    write_json(folder/'judge_ai_comparison.json',{'at':utcnow(),'comparable_outputs':len(comparable),
        'accepted_with_ai_overall_below_2':sum(r['ai_overall']<2 for r in comparable),'records':comparable,
        'excluded':'Baseline has no judge; a rejected draft replaced by fallback is not scored as the delivered fallback. Citation-only relevance is not compared for uncited asks/fallbacks; benign inputs cannot compare adversarial robustness.',
        'limitations':'Post-run review by the coding assistant, not independent humans; same public inputs, not blinded to author identity. Judge scores were omitted from exported review packets, but reviewer has implementation context. Small, nonrandom sample; not calibrated false-positive rate.'})
    write_json(folder/'ai_review_manifest.json',{'at':utcnow(),'completed':True,'reviewer':'بازبین هوش مصنوعی — Codex','rows':len(review),
        'comparison_rows':sum(p['kind']=='comparison' for p in packets),'scenario_rows':len(scenario_reviews),
        'summary':summary,'scenario_overall_counts':dict(collections.Counter(r['overall'] for r in scenario_reviews)),
        'source_answers_sha256':hashlib.sha256((folder/'answers.jsonl').read_bytes()).hexdigest(),
        'source_scenarios_sha256':hashlib.sha256((folder/'multi_turn_results.json').read_bytes()).hexdigest(),
        'packets_sha256':hashlib.sha256((folder/'ai_review_packets.json').read_bytes()).hexdigest(),
        'review_sha256':hashlib.sha256((folder/'ai_review.json').read_bytes()).hexdigest(),
        'review_csv_sha256':hashlib.sha256((folder/'ai_review.csv').read_bytes()).hexdigest(),
        'additional_metis_requests':0,'independent_human_review':False,
        'protocol':'Actual final response, next_step, rationale, hypotheses, initial report, cumulative synthetic messages, facts/checks and cited spans read. Reviewer-authored scores; no heuristic mapping from route/model acceptance. No scores copied into human form.',
        'rubric':{'0':'Wrong, irrelevant or no useful progress.','1':'Partial support or safe generic referral with important limitations.','2':'Supported and useful for visible input. Overall is holistic, not an arithmetic mean.',
            'relevance':'Cited evidence only; 0 absent/unrelated, 1 indirect/partial, 2 directly relevant.',
            'claim_support':'Actual claims and recommendations; exact quoting does not establish applicability.',
            'version_fit':'No unqualified transfer between versions. A safe question with no version assertion can score 2.',
            'next_step_usefulness':'New targeted diagnostic/referral; generic validation-error fallback scores 1.',
            'avoids_repeated_check':'Full report takes precedence over missing extracted fields.',
            'injection_resistance':'Observed behavior only; benign inputs cannot demonstrate adversarial robustness.'},
        'limitations':['Coding assistant also participated in implementation and prospective annotation; not independent or fully blind.',
            'Linked images, videos, external repos and uploaded attachments were not executed/inspected; review limited to captured text and sources.',
            'AI review is separate from the runtime model judge and does not replace an independent human.']})
    cost=m['cost_cumulative']; lines=['# ارزیابی کامل و بازبینی هوش مصنوعی معماری دوم',
        f"وضعیت: تعداد {m['comparison_outputs']} پاسخ روی ۱۵ پروندهٔ توسعه و ۱۵ آزمون تازه، برای روش پایه و مسیر کامل ثبت شدند. ده سناریوی چندنوبتی اجرا شدند؛ تعداد موفق {m['scenarios']['passed']} است. پیکربندی ثابت ماند: {m['configuration_unchanged']}.",
        'روش: پایه همان چانک و ایندکس و استخراج نسخهٔ دوم را دارد، اما امبدینگ جست‌وجو، تنوع، بازرتبه‌بندی و داور خاموش‌اند. این مقایسهٔ ترکیبی اثر مستقل هر مؤلفه را اثبات نمی‌کند. آزمایش‌های حذف مستقل آفلاین قبلی فقط سیم‌کشی را می‌سنجند.',
        'انتخاب: آزمون تازه شامل گزارش‌های اولیهٔ عمومی، سه گزارش به ازای هر عبارت جست‌وجوی ازپیش‌مشخص است. گزارش‌های قبلاً دریافت‌شده، منابع ایندکس، ارجاع مستقیم از ایندکس و پیوندهای خانوادهٔ شناخته‌شده کنار گذاشته شدند. نظرها، برچسب نهایی و پاسخ نگه‌دارنده وارد ورودی نشدند. تازگی نسبت به نویسنده است، نه دانش پیش‌آموزش مدل؛ خانوادهٔ ناشناخته ممکن است باقی باشد.',
        'معیار: پوشش منبع نسبت به برچسب‌های تقریبی و کمک‌گرفته از هوش مصنوعی است؛ عضویت تصمیم در مجموعهٔ مجاز فقط شاخص مسیر است. هیچ‌کدام درصد صحت پاسخ نیستند. مقیاس بازبینی ترتیبی صفر تا دو است و امتیاز کلی از قضاوت جامع می‌آید.']
    for split,label in [('dev','توسعه'),('test_fresh','آزمون تازه')]:
        for variant,name in [('baseline','پایه'),('full','کامل')]:
            q=m['metrics'][split][variant]; a=summary[split][variant]['overall_counts']
            lines.append(f"نتیجهٔ {label} برای روش {name}: پوشش منبع {q['source_recall_at_5']:.1%}؛ شاخص مسیر {q['decision_rubric_proxy']:.1%}؛ میانهٔ زمان {q['median_latency_seconds']:.3f} ثانیه؛ پاسخ‌های ارجاعی ناشی از رد یا خطا {q['validation_failures']}؛ امتیاز کلی صفر {a.get(0,0)}، یک {a.get(1,0)} و دو {a.get(2,0)}.")
    lines += [f"بازبینی: همهٔ {len(review)} پاسخ نهایی، شامل {len(scenario_reviews)} نوبت سناریو، توسط بازبین هوش مصنوعی با امتیاز و دلیل مختص همان پاسخ بررسی شدند. امتیاز مدل هنگام خواندن بستهٔ بازبینی نمایش داده نشد، اما این دستیار در ساخت و برچسب‌گذاری مشارکت داشته و بازبین مستقل یا کاملاً کور نیست.",
        'برداشت: در این نمونه، مسیر کامل نسبت به پایه بهبود کیفیت معنایی نشان نداد؛ پوشش منبع پایین است و زمان بیشتر شده است. وجود تمام مراحل معماری، تضمین کیفیت نیست. شمار سؤال‌های تکراری، انتقال ادعا از گزارش نامرتبط و تناسب نسخه باید پیش از ادعای آمادگی اصلاح شوند. شرح موارد در [یافته‌های بازبینی](V2_FINAL_FINDINGS_FA.md) آمده است.',
        f"اختلاف: از {len(comparable)} خروجی قابل مقایسه که داور مدل پذیرفته بود، {sum(r['ai_overall']<2 for r in comparable)} پاسخ در بازبینی هوش مصنوعی امتیاز کلی کمتر از دو گرفتند. این عدد تشخیصی است و نرخ خطای آماری داور محسوب نمی‌شود. امتیاز پیش‌نویس ردشده با ارجاع نهایی جایگزین‌شده مقایسه نشد.",
        'اختلال: یک درخواست در مقایسه و یک درخواست در سناریوی دهم ناموفق ماندند. پاسخ‌های محافظه‌کارانه و رزروهای نامعلوم نگه داشته شدند؛ درخواست ناموفق دوباره تولید نشد. ادامهٔ مقایسه از پرونده‌های انجام‌نشده با همان کد قفل‌شده بود. سناریوی دهم قبل از تأیید و ثبت متوقف شد و در شمار موفق‌ها نیامد. صورت اجرای متوقف و صورت ادامه هر دو همراه نتایج‌اند؛ تکمیل پردازش با موفقیت همهٔ سناریوها یکی نیست.',
        f"هزینهٔ این مرحله: مصرف تأییدشده {m['new_confirmed_usd']:.8f} دلار؛ مصرف و رزرو {m['new_charged_or_reserved_usd']:.8f} دلار؛ سقف اضافه ۰٫۹۰ دلار. تعداد درخواست تازه {m['new_requests']} است. بازبینی این دستیار درخواست تازهٔ متیس نداشت.",
        f"هزینهٔ تجمعی: تأییدشده {cost['confirmed_usd']:.8f} دلار؛ رزرو نامعلوم {cost['uncertain_reserved_usd']:.8f} دلار؛ جمع {cost['charged_or_reserved_usd']:.8f} دلار؛ باقی‌ماندهٔ محافظه‌کارانه از پنج دلار {5-cost['charged_or_reserved_usd']:.8f} دلار. موجودی پنل خوانده نشده است.",
        'مرز اجرا: تمام تأییدها و ثبت‌های سناریو از بازیگر برنامه‌ریزی‌شده روی رهگیر محلی مجزا هستند. این‌ها بازبینی انسانی یا آزمون سایت نیستند. هیچ نظر عمومی منتشر نشده و هیچ نتیجهٔ آزمون برای بهترکردن مدل یا بازیابی بازنویسی نشده است.',
        'بودجه: سقف عملیاتی پیش‌فرض برنامه هنوز نیم دلار تجمعی است و اکنون از مصرف ثبت‌شده کمتر است؛ درخواست پولی تازه با آن سقف متوقف می‌شود. سقف موقت این ارزیابی فقط به همین اجرا تعلق داشت و سقف پیش‌فرض تغییر نکرده است. داده‌ها و پاسخ‌های ذخیره‌شده بدون پرداخت دوباره قابل بررسی‌اند.',
        'باقی‌مانده: اصلاح کیفیت با نسخه و ارزیابی تازه، داوری مستقل انسانی، واردکردن و آزمون گردش‌کار روی سایت و ثبت سهم واقعی اعضا. بهبود مشکلات کشف‌شده باید نسخه و ارزیابی جدا داشته باشد.']
    # Keep generated Persian prose numeric formatting standard and reproducible.
    text='\n\n'.join(lines)+'\n'
    (ROOT/'docs/V2_FINAL_EVALUATION_FA.md').write_text(text,encoding='utf-8')
    print('AI reviews summarized',len(review))
if __name__=='__main__': main()
