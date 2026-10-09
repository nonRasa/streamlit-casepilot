"""Summarize authored semantic scores and frozen outputs, without network."""
import collections,csv,hashlib,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.roles import CRITERIA
from quality_result_files import result_paths

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation'; manifest_path,scenario_path=result_paths(folder);m=read_json(manifest_path); plan=read_json(folder/'plan.json')
    packets=read_json(folder/'ai_review_packets.json'); assignment=read_json(folder/'ai_review_assignment.json'); reviews=read_json(folder/'ai_review.json')
    by_id={p['review_id']:p for p in packets}; mapping={p['review_id']:p['source_key'] for p in assignment}
    require(len(reviews)==len(by_id)==len({r['review_id'] for r in reviews}),'incomplete_review','بازبینی ناقص است.')
    for r in reviews:
        require(r['output_sha256']==by_id[r['review_id']]['output_sha256'] and set(r['scores'])==set(CRITERIA) and all(type(v) is int and v in (0,1,2) for v in r['scores'].values()) and r['overall'] in (0,1,2) and len(r['notes'])>30,'invalid_review','نمره یا منشأ معتبر نیست.')
    fields=['review_id','source_key','case_id']+list(CRITERIA)+['overall','reviewer','notes','output_sha256']
    with (folder/'ai_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in reviews:
            writer.writerow({'review_id':r['review_id'],'source_key':mapping[r['review_id']],'case_id':by_id[r['review_id']]['case_id'],
                **r['scores'],'overall':r['overall'],'reviewer':'بازبین هوش مصنوعی — Codex','notes':r['notes'],'output_sha256':r['output_sha256']})
    scores={mapping[r['review_id']]:r for r in reviews}; summary={}
    rows=read_json(folder/'answers.json'); outputs={r['split']+'/'+r['variant']+'/'+r['id']:r['output'] for r in rows}
    for s in read_json(scenario_path):
        for i,out in enumerate(s['turns']): outputs[s['id']+'/'+str(i+1)]=out
    for split in ('dev','test_fresh'):
        summary[split]={}
        for variant in ('previous','revised'):
            group=[r for r in rows if r['split']==split and r['variant']==variant]; outs=[r['output'] for r in group if r['output']]
            summary[split][variant]={'n':len(group),'delivered':len(outs),
                'overall_counts':dict(collections.Counter(scores[split+'/'+variant+'/'+r['id']]['overall'] for r in group)),
                'validation_errors':dict(collections.Counter(o['validation_error'] or 'none' for o in outs)),
                'median_latency_seconds':statistics.median(o['latency_seconds'] for o in outs) if outs else None,
                'citations':sum(len(o['summary']['sources']) for o in outs)}
    paired=[]
    for case in plan['cases']:
        if case['split']!='test_fresh': continue
        prefix='test_fresh/'; old=scores[prefix+'previous/'+case['id']]['overall']; new=scores[prefix+'revised/'+case['id']]['overall']
        paired.append({'id':case['id'],'previous':old,'revised':new,'difference':new-old})
    comparisons=[]
    for key,out in outputs.items():
        if key.startswith('dev/previous/') or '/previous/' in key or not out or out['validation_error']: continue
        judge=out.get('judge') or {}
        if judge.get('verdict')=='accept': comparisons.append({'source_key':key,'ai_overall':scores[key]['overall'],'ai_scores':scores[key]['scores'],'model_scores':judge['scores']})
    write_json(folder/'judge_ai_comparison.json',{'records':comparisons,'accepted_outputs':len(comparisons),
        'accepted_with_ai_overall_below_2':sum(x['ai_overall']<2 for x in comparisons),
        'limitations':'Diagnostic post-run AI judgments, not calibrated error rates or independent human review. Citation relevance absent means 0 in AI rubric but 2=no bad citation in runtime rubric; do not equate these two. No adversarial claims from benign inputs.'})
    manifest={'at':utcnow(),'completed':True,'rows':len(reviews),'summary':summary,'paired_fresh':paired,
        'scenario_overall_counts':dict(collections.Counter(r['overall'] for r in reviews if by_id[r['review_id']]['kind']=='scenario')),
        'reviewer':'بازبین هوش مصنوعی — Codex','independent_human_review':False,'additional_metis_requests':0,
        'protocol':'Authored scores after reading actual report, final answer, next_step/rationale/hypotheses, sources and cumulative follow-ups. Standardized packets omit variant labels and runtime judge scores for later reviewers, but some outputs and diagnostic pipeline traces were inspected alongside runtime metadata and execution order was known; this author review is not blinded. Author participated in implementation; not independent. Old dev judgments may be reused only with matching output hash and identified provenance.',
        'rubric':'Six criteria 0/1/2; citation relevance=0 absent/unrelated,1 indirect,2 direct. Overall holistic, not arithmetic mean; a targeted uncited question may score overall2. Safe generic fallback normally overall1. Injection score is observed behavior only, not adversarial robustness.',
        'limitations':['Text-only initial reports; linked media/repositories not executed. Small nonrandom sample, unknown families and pretraining contamination possible.',
            'No failure-triggered redo of comparison outputs. Planned independent scenario initial turns repeat selected reports; failed provider calls are not cached and may be sent again in those separate turns. Frozen runner wording no failed request retried must be read with this clarification; all charges retained.',
            'No prompt, runtime, corpus or answers changed after final freeze. Future improvements require another version and fresh test.'],
        'scenario_source_file':scenario_path.name,
        'sha256':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ('answers.json',scenario_path.name,'ai_review_packets.json','ai_review.json','ai_review.csv')}}
    write_json(folder/'ai_review_manifest.json',manifest)
    cost=m['cost_cumulative']; campaign=read_json(ROOT/'artifacts/quality_revision/campaign.json')
    lines=['# اصلاح کیفیت و ارزیابی نسخهٔ دومِ اصلاح‌شده',
        'تغییر: منابع اداری و پیشنهادهای آینده از نامزدهای شاهد کنار گذاشته شدند؛ جست‌وجو بر مسئله و نام رابط متمرکز شد و مستندات رسمی اولویت محدود دارند. امبدینگ و دادهٔ ثابت بازسازی نشدند و همان کش خصوصی استفاده شد.',
        'تغییر: متن گزارش با ابتدا و انتها و پیام‌های اصلاحی بسته‌بندی می‌شود؛ نسخهٔ صریح محیط بر مقایسهٔ تاریخی مقدم است. فهرست کد موجود، حد آپلود و نتیجهٔ آزمایش‌های خاص به زمینه اضافه شده‌اند. استخراج و برنامه‌ریزی مسئله در یک فراخوانی است و تولیدکننده میان گزارش خطا و درخواست قابلیت فرق می‌گذارد.',
        'تغییر: داور برای هر استناد، عبارت واقعیِ پاسخ و دلیل پشتیبانی می‌دهد و برای سؤال، دلیل تازه‌بودن و شاهد تکرار را ثبت می‌کند. کنترل کد، ادعای پذیرش داور را در صورت نقض این قراردادها رد می‌کند. حداکثر یک اصلاح، هشت فراخوانی و چهار سنت در هر نوبت باقی مانده‌اند. این کنترل‌ها کامل یا حل‌کنندهٔ عمومی معنا نیستند.',
        'روش: پنج پروندهٔ توسعهٔ هدفمند برای شکست‌های شناخته‌شده با نسخهٔ جدید و پانزده آزمون تازه با هر دو نسخه ارزیابی شدند. توسعه نمونهٔ نمایندهٔ تصادفی نیست. نسخهٔ قبل از کد واقعاً حفظ‌شده در فرایند جدا اجرا شد. پاسخ‌های قدیمی توسعه بازاستفاده شده‌اند و هزینهٔ دوباره ندارند. آزمون تازه از همهٔ گزارش‌های قبلاً دریافت‌شده و منابع ایندکس و ارجاع‌های مستقیم آن‌ها جداست؛ پنجرهٔ زمانی و ترتیب انتخاب پیشاپیش ثابت‌اند.',
        'مقایسه: در آزمون تازه، سقف خروجی تولیدکننده برای دو نسخه ۱۶۰۰ توکن است؛ داور نسخهٔ قبل همچنان سقف داخلی ۸۰۰ و نسخهٔ جدید ۱۴۰۰ دارد. نتیجه مربوط به کل اصلاحات است و اثر مستقل هر مؤلفه را جدا نمی‌کند. پاسخ قدیمی توسعه سقف ۱۰۰۰ داشته است.',
        f"اجرا: تعداد مقایسهٔ پردازش‌شده {m['attempted_comparisons']} و پاسخ تحویلی {m['delivered_comparisons']} است؛ ده سناریو با {m['scenarios']['passed']} مورد موفق ثبت شدند. ثبات پیکربندی {'تأیید شد' if m['configuration_unchanged'] else 'تأیید نشد'}. موفقیت اجرایی با کیفیت معنایی یکی نیست."]
    fresh_new=[r for r in rows if r['split']=='test_fresh' and r['variant']=='revised']
    fallbacks=sum(bool((r['output'] or {}).get('validation_error')) for r in fresh_new)
    lines.insert(1,f"نتیجه: در بازبینی غیرمستقل این دستیار، {sum(x['difference']>0 for x in paired)} پروندهٔ تازه بهتر، {sum(x['difference']==0 for x in paired)} برابر و {sum(x['difference']<0 for x in paired)} بدتر شدند؛ اما {fallbacks} خروجی از {len(fresh_new)} به ارجاع عمومی رسیدند. کیفیت کاربردی هنوز کافی نیست و تعداد امتیاز دو در نسخهٔ جدید {summary['test_fresh']['revised']['overall_counts'].get(2,0)} است. کاهش پاسخ نامناسب با تولید پاسخ مفید برابر نیست.")
    for split,label in [('dev','توسعه'),('test_fresh','آزمون تازه')]:
        for variant,name in [('previous','قبلی'),('revised','اصلاح‌شده')]:
            s=summary[split][variant]; counts=s['overall_counts']
            lines.append(f"نتیجهٔ {label} برای نسخهٔ {name}: تعداد {s['n']}؛ کیفیت کلی صفر {counts.get(0,0)}، یک {counts.get(1,0)} و دو {counts.get(2,0)}؛ میانهٔ زمان {s['median_latency_seconds']:.3f} ثانیه؛ تعداد استناد {s['citations']}. کیفیت کلی قضاوت ترتیبی این دستیار است، نه درصد صحت تأییدشده.")
    if m.get('completion_provenance'):
        lines.append('توقف: اجرای اصلی پس از هشت سناریوی موفق، در سناریوی نهم به سقف موقت رسید و پیش از آغاز سناریوی دهم متوقف شد. صورت و خروجی اصلی بازنویسی نشدند. فقط سناریوی دهمِ هرگز آغازنشده، با همان کد و باقی‌ماندهٔ سقف ۰٫۶۵ دلار این نوبت تلاش شد؛ سناریوی نهم و پاسخ‌های مقایسه دوباره اجرا نشدند. صورت تکمیل و منبع ترکیبی جدا و با هش محفوظ‌اند. تکمیل به معنی پردازش همهٔ طرح‌هاست، نه موفقیت همهٔ آن‌ها.')
    lines += [f"مقایسهٔ زوجی آزمون تازه: تعداد بهتر {sum(x['difference']>0 for x in paired)}، برابر {sum(x['difference']==0 for x in paired)} و بدتر {sum(x['difference']<0 for x in paired)}. نمونهٔ کوچک برای نتیجه‌گیری آماری عمومی کافی نیست.",
        f"بازبینی: همهٔ {len(reviews)} خروجی با دلیل اختصاصی و هش بررسی شدند؛ بستهٔ استاندارد برای مرور بعدی، امتیاز داور و نام نسخه را ندارد، اما بخشی از پاسخ‌ها و ردپای تشخیصی همراه فراداده دیده شدند و ترتیب اجرا معلوم بود. بازبینی این دستیار کور یا مستقل نیست و بازبین در پیاده‌سازی مشارکت داشته است. بازبینی انسانی ساخته نشده است. نتیجهٔ داور مدل جدا گزارش می‌شود.",
        f"هزینهٔ ارزیابی نهایی تازه: تأییدشده {m['new_confirmed_usd']:.8f} دلار و مصرف همراه رزرو {m['new_charged_or_reserved_usd']:.8f} دلار. هزینهٔ کل این نوبت اصلاح، شامل توسعه و ارزیابی، با رزرو {cost['charged_or_reserved_usd']-campaign['cost_before']['charged_or_reserved_usd']:.8f} دلار و زیر سقف ۰٫۶۵ دلار اضافه است.",
        f"هزینهٔ کل تیم: تأییدشده {cost['confirmed_usd']:.8f} دلار؛ نامعلومِ رزروشده {cost['uncertain_reserved_usd']:.8f} دلار؛ جمع {cost['charged_or_reserved_usd']:.8f} دلار؛ باقی‌ماندهٔ محافظه‌کارانه از پنج دلار {5-cost['charged_or_reserved_usd']:.8f} دلار. موجودی پنل خوانده نشده است؛ بازبینی این دستیار متیس مصرف نکرد.",
        'محدودیت: پاسخ‌های مقایسه پس از شکست بازنویسی نشده‌اند. آغاز مستقلِ سناریوهای ازپیش‌طراحی‌شده بعضی گزارش‌ها را تکرار می‌کند؛ چون درخواست ناموفق در کش نیست، همان درخواست ممکن است در این نوبت مستقل دوباره ارسال شود. عبارت نبود تکرار در صورت اجرای قفل‌شده به بازاجرای مقایسه اشاره دارد و با این توضیح تصحیح می‌شود. همهٔ هزینه‌ها حفظ‌اند. سناریوها پاسخ تکمیلی و تأیید برنامه‌ریزی‌شده روی رهگیر محلی دارند. اقدام عمومی یا آزمون سایت انجام نشده است.',
        'باقی‌مانده: داوری مستقل انسانی، بررسی ضعف‌های باقی‌ماندهٔ کیفیت، واردکردن و آزمون گردش‌کار روی سایت و ثبت سهم واقعی اعضا. سقف عملیاتی پیش‌فرض نیم دلار تغییر نکرده و درخواست پولی تازه با آن سقف متوقف می‌شود.']
    (ROOT/'docs/QUALITY_REVISION_FA.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    print('Semantic reviews summarized:',len(reviews))
if __name__=='__main__': main()
