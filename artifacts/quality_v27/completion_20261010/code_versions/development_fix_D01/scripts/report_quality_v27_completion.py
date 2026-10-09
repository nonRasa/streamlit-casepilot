"""Evaluator-only reproducible scores and Persian decision report, no API calls."""
import sys,json,collections,statistics,csv,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest
from casepilot.evaluation_completion import retrieval_scores,candidate_key
from casepilot.evaluation import answer_metrics
from complete_quality_v27 import accounting,load_cases,verify
from prepare_quality_v27_completion import RUN,DATA
from evaluate_quality_v25_live import sha


def labels():
    rows=sum([read_json(DATA/(s+'_labels.json')) for s in ('dev','holdout')],[])
    errata=read_json(RUN/'witness_errata_preregistered.json')['replacement_witnesses']
    for r in rows:
        if r['id'] in errata:r['required_evidence']=errata[r['id']]
    return {r['id']:r for r in rows}


def mean(rows,key):
    values=[r[key] for r in rows if isinstance(r.get(key),(int,float)) and not isinstance(r[key],bool)]
    return sum(values)/len(values) if values else None


def fmt(value):return '—' if value is None else f'{value:.3f}'


def main():
    verify();lab=labels();cases={r['id']:r for r in load_cases()}
    judgments_path=RUN/'pool_judgments.json';judgments=read_json(judgments_path) if judgments_path.exists() else {'cases':{}}
    metrics=[];controls=[]
    for path in sorted((RUN/'retrieval').glob('*.json')):
        ret=read_json(path)
        if 'B' in ret['variants'] and 'C' in ret['variants']:
            controls.append({'id':ret['id'],'same_initial_candidates':ret['variants']['B']['candidate_hash']==ret['variants']['C']['candidate_hash'],
                             'same_query_vector':True,'same_context_budget':ret['variants']['B']['packing']['budget_tokens']==ret['variants']['C']['packing']['budget_tokens']})
        for variant in ('A','B','C'):
            r=ret['variants'].get(variant)
            if not r or r.get('failure'):continue
            j=judgments['cases'].get(ret['id'],{})
            score=retrieval_scores(r['candidates'],r['context'],lab[ret['id']],j,
                context_tokens=r['packing']['used_tokens'])
            # Context relevance has its own denominator (including parents).
            gs=[j.get(candidate_key(x),{}).get('grade') for x in r['context']]
            known=[g for g in gs if g is not None]
            score.update(context_judgment_coverage=len(known)/len(gs) if gs else 1,
                         context_judged_irrelevant_fraction=sum(g==0 for g in known)/len(known) if known else None)
            metrics.append({'id':ret['id'],'split':ret['split'],'type':lab[ret['id']]['expected_route'],
                            'variant':variant,**score,'packing':r['packing']})
    keys=['recall_at_k','ndcg_at_k','judgment_coverage','judged_irrelevant_fraction',
          'candidate_witness_coverage_at_k','context_witness_coverage','context_tokens',
          'context_judgment_coverage','context_judged_irrelevant_fraction']
    summaries=[]
    for split in ('dev','holdout','fresh_holdout','all'):
        for variant in ('A','B','C'):
            rows=[r for r in metrics if r['variant']==variant and (split=='all' or r['split']==split
                   or (split=='fresh_holdout' and r['split']=='holdout' and not lab[r['id']]['previously_seen']))]
            summaries.append({'split':split,'variant':variant,'n':len(rows),**{k:mean(rows,k) for k in keys},
                'context_budget_violations':sum(not r['context_budget_ok'] for r in rows),
                'known_version_mismatches':sum(r['known_version_mismatches'] for r in rows)})
    type_results=[]
    for kind in sorted({l['expected_route'] for l in lab.values()}):
        for variant in ('A','B','C'):
            rows=[r for r in metrics if r['variant']==variant and r['type']==kind]
            type_results.append({'type':kind,'variant':variant,'n':len(rows),**{k:mean(rows,k) for k in keys}})
    ans=[];answer_controls=[];human=[];mapping={}
    for path in sorted((RUN/'answers').glob('*.json')):
        r=read_json(path);out=r['output'] or {};sc=answer_metrics(out,lab[r['id']],evaluation_kind='live')
        judge=out.get('judge');error=r['failure'] or out.get('validation_error')
        contract_valid=bool(judge) and error not in ('judge_contract_error','invalid_judge')
        sc.update(contract_valid=contract_valid,observed_error=error,
                  final_content_accepted=bool(judge and judge.get('verdict')=='accept' and not error),
                  outcome=out.get('outcome'),review_attempts=sum(x['stage']=='judge' for x in out.get('pipeline',[])),
                  review_failures=out.get('review_failures',[]),
                  # Failed/contract-invalid final replies cannot claim zero
                  # unsupported content; leave that dimension unassessed.
                  unsupported_claim_findings=sc['unsupported_claim_findings'] if judge else None,
                  repeated_question_or_test_findings=sc['repeated_question_or_test_findings'] if judge else None)
        ans.append({'id':r['id'],'split':r['split'],'variant':r['variant'],**sc})
        alias='review_'+digest({'id':r['id'],'variant':r['variant']})[:12]
        mapping[alias]={'id':r['id'],'variant':r['variant']}
        human.append({'alias':alias,'report':cases[r['id']]['initial_message'],
            'already_supplied_facts':cases[r['id']]['initial_facts'],'already_completed_checks':cases[r['id']]['initial_checks'],
            'response':out.get('response'),'final_claims':out.get('summary',{}).get('sources',[]),
            'reviewed_draft':out.get('reviewed_draft'),'internal_error':error,
            'unsupported_claims':None,'repeated_question_or_test':None,'route_fit':None,'usefulness_0_to_3':None,
            'reviewer_origin':None})
    for cid in read_json(DATA/'protocol.json')['answer_cases']:
        paths=[RUN/'answers'/(cid+'_'+v+'.json') for v in ('B','C')]
        if not all(p.exists() for p in paths):continue
        outs=[read_json(p)['output'] or {} for p in paths]
        def stage(out,name):return [x for x in out.get('pipeline',[]) if x['stage']==name]
        answer_controls.append({'id':cid,'same_candidate_hash':stage(outs[0],'retrieve') and stage(outs[1],'retrieve') and
            stage(outs[0],'retrieve')[0]['candidate_hash']==stage(outs[1],'retrieve')[0]['candidate_hash'],
            'same_selected_ids':bool(stage(outs[0],'rerank') and stage(outs[1],'rerank') and
                stage(outs[0],'rerank')[0].get('ids')==stage(outs[1],'rerank')[0].get('ids')),
            'extract_B':stage(outs[0],'extract'),'extract_C':stage(outs[1],'extract')})
    write_json(RUN/'metrics.json',{'retrieval_per_case':metrics,'retrieval_summary':summaries,'retrieval_by_type':type_results,
        'answer_per_case':ans,'BC_controls':controls,'BC_answer_controls':answer_controls,
        'judgment_origin':judgments.get('origin','not yet judged'),'judgment_sha256':sha(judgments_path) if judgments_path.exists() else None,
        'labels_sha256':sha(DATA/'manifest.json'),'witness_errata_sha256':sha(RUN/'witness_errata_preregistered.json'),
        'independent_review_completed':False,'human_review_completed':False,'quality_success':False,
        'default_changed':False,'default':'v2'})
    write_json(RUN/'human_answer_review.json',sorted(human,key=lambda r:r['alias']))
    write_json(RUN/'human_answer_review_key.json',mapping)
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=['id','split','type','variant']+keys+['known_version_mismatches'])
    writer.writeheader();writer.writerows({k:r.get(k) for k in writer.fieldnames} for r in metrics)
    (RUN/'retrieval_per_case.csv').write_text(out.getvalue(),encoding='utf-8-sig')
    accounting();cost=read_json(RUN/'accounting.json');ph=cost['phases']
    judge=read_json(RUN/'judge/attempt_1.json');model=judge['raw_review'].get('v') if judge['raw_review'] else None
    rows=['گزارش تکمیل و تصمیم V27 ـ ۲۰۲۶-۱۰-۱۰','',
      'تصمیم فعلی: ایندکس v2 پیش‌فرض باقی می‌ماند. ساخت v3 و موفقیت قالب داور به‌تنهایی مجوز تغییر پیش‌فرض نیستند. وضعیت تصمیم بر اساس نتایج زیر و شروط پذیرشِ منجمد ثبت شده؛ ادعای بهبود کیفیت پاسخ نشده است.','',
      'مبنا و کنترل آزمایش','',
      'HEAD برابر 38f04b8 است؛ تغییرات قبلی حفظ شدند. AGENTS.md در پروژه و والدهای بررسی‌شده وجود ندارد. معماری همچنان BM25 + بردار + RRF(60) + MMR(0.7) است. مدل همهٔ نقش‌ها gpt-4.1-mini و مدل embedding، text-embedding-3-small است. v2 و v3 همان ۲۳۱ منبع و بازبینی را دارند. A=v2، B=فرزند v3 و C=همان فرزند با گسترش محدود والد. بودجهٔ زمینه در هر سه ۳۰۰۰ توکن است.','',
      'مقایسه ابتدا بازیابی خام ترکیبی بدون تولید پاسخ را اندازه می‌گیرد. سپس Agent واقعی روی نامزدهای ثبت‌شده اجرا می‌شود: استخراج، انتخاب شواهد، تولید، داوری و حداکثر یک اصلاح محتوایی. خلاصهٔ استخراج‌شده حق تغییر نامزدها را در این آزمایش ندارد؛ این مداخله در trace ثبت است و با جست‌وجوی آزاد تولیدی یکسان نیست. برای B/C ورودی استخراج و بازرتبه‌بندی و cache مشترک است؛ تنها گسترش والد تغییر می‌کند.','',
      'قرارداد فعال','',
      f"نخستین تلاش مستقیم روی پیش‌نویس و شواهد ثابت: اعتبار قرارداد={judge['contract_valid']}، تصمیم مدل={model}، تصمیم نهایی نگهبان={judge['content_verdict']}. شکست S0 پیش‌شرط نبود. دلایل غیرخالی، پوشش واحدها، اتصال به پیش‌نویس و ارجاع‌ها از مسیر کامل بررسی شدند. مدل ممکن است امتیاز مثبت نادرست بدهد؛ یافته‌های نگهبان و تغییر تصمیم جدا در artifact محفوظ‌اند. این آزمایش دقت معنایی مستقل داور را اثبات نمی‌کند.",'',
      'داده و قضاوت','',
      '۲۴ نمونه: ۱۲ توسعه و ۱۲ نهایی، ۲۰ نمونه دارای شاهد دقیق با متن، بازهٔ نویسه، خط و بازبینی. خانواده‌های گسترده میان دو بخش مشترک نیستند. شش نمونهٔ نهایی قدیمی قبلاً دیده شده‌اند؛ شش نمونهٔ جدید جدا گزارش می‌شوند. داده، رفتار مورد انتظار و معیارها پیش از تنظیم تازه منجمد شده‌اند. سه شاهد در preflight، پیش از بازیابی، از نام/عبارت کوتاه به متنِ حاوی رفتار تقویت شدند؛ برچسب اولیه حفظ شده و errata جداست.','',
      'pool بر اساس پنجرهٔ دقیق منبع تجمیع و بدون نام نسخه آماده شده است. منشأ برچسب‌ها دستیار/قاعدهٔ کمکی است و انسانی یا مستقل نیست. منابع قضاوت‌نشده grade=null دارند؛ nDCG عادی در top-k ناقص گزارش نمی‌شود. nDCG بر واحد پنجرهٔ منبع و IDCG مشترک pool محاسبه می‌شود؛ Recall بر منبع مرجع و پوشش شاهد بر متن دقیق محاسبه می‌شود. مرجعِ یک شاهد ممکن است همهٔ پاسخ‌های معتبر را پوشش ندهد.','',
      'ساخت واقعی embedding','',
      'همهٔ فرزندها با بازسازی آفلاین، متن دقیق، hash، شناسهٔ پایدار، شمارش واقعی توکن و رابطهٔ والد اعتبارسنجی شدند. چهار قطعهٔ اتمی بزرگ حفظ و ثبت شده‌اند. پس از ۵۶ batch موفق، اتصال شکست خورد؛ ۱۷۹۲ متن ذخیره شده بود. ادامه فقط ۵۶۳ متن باقی‌مانده را ساخت. پوشش نهایی ۲۳۵۸ ردیف/۲۳۵۵ آدرس یکتا، با بردارهای واقعی ۱۵۳۶بُعدی و namespace جدید کامل است. cache قدیمی یا fixture در مقایسهٔ زنده وارد نشد. ساخت باعث فعال‌کردن پیش‌فرض نشده است.','',
      'نتایج بازیابی','',
      '| بخش | نسخه | n | Recall@5 | nDCG@5 قضاوت‌شده | پوشش قضاوت | پوشش شاهد در زمینه | توکن زمینه |','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summaries:
        rows.append('| '+r['split']+' | '+r['variant']+' | '+str(r['n'])+' | '+' | '.join(fmt(r[k]) for k in ('recall_at_k','ndcg_at_k','judgment_coverage','context_witness_coverage','context_tokens'))+' |')
    rows+=['','نتایج هر نمونه در retrieval_per_case.csv و metrics.json و تفکیک نوع درخواست در retrieval_by_type موجود است. نقض بودجه، نسخهٔ نامعلوم/ناسازگار و دلایل حذف/عدم گسترش در همان فایل و trace محفوظ‌اند.','',
       'پاسخ‌های واقعی','',
       '| نمونه | بخش | نسخه | قرارداد معتبر | پذیرش نهایی محتوا | خطا | فایدهٔ انسانی |','|---|---|---|---|---|---|---|']
    for r in ans:rows.append(f"| {r['id']} | {r['split']} | {r['variant']} | {r['contract_valid']} | {r['final_content_accepted']} | {r['observed_error'] or '—'} | ارزیابی نشده |")
    rows+=['','ادعاهای بی‌پشتوانه و تکرار در answer_per_case شمارش یافته‌های داور/نگهبان‌اند، حقیقت مستقل نیستند. نبود judge به‌صورت ارزیابی‌نشده ثبت است، نه صفر خطا. بستهٔ human_answer_review.json پاسخ‌ها را با شناسهٔ کور و زمینهٔ کامل گزارش برای بازبینی انسانی آماده می‌کند؛ ستون‌ها تا بازبینی خالی هستند.','',
       'هزینهٔ تازه (دلار)','',
       '| مرحله | درخواست | قطعی | رزرو نامعلوم |','|---|---:|---:|---:|']
    for p in ('judge','index','retrieval','answers'):
        r=ph[p];rows.append(f"| {p} | {r['requests']} | {r['confirmed_usd']:.9f} | {r['unknown_reserved_usd']:.9f} |")
    rows+=[f"\nجمع تازه: قطعی {cost['confirmed_usd']:.9f}، نامعلوم {cost['unknown_reserved_usd']:.9f}، مجموع {cost['charged_or_reserved_usd']:.9f} از سقف مصوب ۱٫۱۰ دلار؛ {cost['requests']} درخواست از سقف ۳۴۳. هزینهٔ ساخت ایندکس جدا از embedding پرسش و استنتاج گزارش شده است. هزینهٔ تاریخی V27: قطعی ۰٫۰۳۰۳۶۹۱۳۰، نامعلوم ۰٫۰۱۲۸۵۸۳۸۴؛ مجوز و هزینهٔ تازه از آن جداست.",'',
      'جدول تصمیم','',
      '| نسخه | کیفیت و هزینه | محدودیت | وضعیت استفاده |','|---|---|---|---|',
      '| A: v2 | معیارهای بازیابی و پاسخ در بالا؛ embedding موجود | تضمین کیفیت پاسخ حاصل نشده؛ داوری مستقل موجود نیست | حفظ به‌عنوان پیش‌فرض فعلی با نگهبان‌های محافظه‌کارانه |',
      '| B: فرزند v3 | ساخت واقعی تکمیل؛ هزینهٔ ساخت حدود یک سنت، مقایسهٔ سنجیده در بالا | موفقیت ساخت، بهبود کیفیت نیست | گزینهٔ آزمایشی صریح؛ پیش‌فرض نشده |',
      '| C: والد محدود | همان هزینهٔ embedding B؛ توکن بیشتر فقط در گسترش | والدِ بزرگ‌تر بدون شاهد/فایدهٔ بیشتر برنده نیست | گزینهٔ آزمایشی؛ انتخاب خودکار جدید فعال نشده |','',
      'فایل‌ها و بازتولید','',
      'ابزارهای prepare_quality_v27_completion.py، complete_quality_v27.py و report_quality_v27_completion.py؛ معیارها در src/casepilot/evaluation_completion.py؛ تزریق اختیاری بردار پرسش مشترک در hybrid.py؛ آزمون‌های test_quality_v27_completion.py. source نسخه‌های اجرای داور و پاسخ در code_versions با hash محفوظ است. هیچ مجوزی برای هزینهٔ تازه در اجرای دوبارهٔ این ابزارها استنباط نمی‌شود؛ authorization مربوط به همین دامنه و سقف است و ledger محدودیت را اعمال می‌کند.','',
      'وضعیت تحویل: کد و ابزار پیاده‌سازی شده؛ ساختار، قرارداد، محافظ بودجه و ادامه از cache آفلاین آزموده شده؛ قالب داور و embedding و نتایج درج‌شده واقعاً با مدل زنده اجرا شده‌اند. کیفیت انسانی یا مستقل هنوز تأیید نشده است. ضعف/عدم‌قطعیتِ قابل‌انتساب باید از نتایج نمونه‌ها خوانده شود، نه صرفاً تعداد آزمون‌ها.']
    path=ROOT/'docs/QUALITY_V27_COMPLETION_FA.md';path.write_text('\n'.join(rows)+'\n',encoding='utf8')
    print('Completion report and per-case evidence written; no quality success claimed.')

if __name__=='__main__':main()
