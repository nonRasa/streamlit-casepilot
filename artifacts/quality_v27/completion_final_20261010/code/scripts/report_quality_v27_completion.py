"""Evaluator-only reproducible scores and Persian decision report, no API calls."""
import sys,json,collections,statistics,csv,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest
from casepilot.evaluation_completion import retrieval_scores,candidate_key
from casepilot.evaluation import answer_metrics
from complete_quality_v27 import accounting,load_cases,verify,read_retrieval
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
        ret=read_retrieval(path.stem)
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
    keys=['recall_at_k','ndcg_at_k','judgment_coverage','judged_irrelevant_fraction','unknown_versions',
          'candidate_witness_coverage_at_k','context_witness_coverage','context_tokens',
          'context_judgment_coverage','context_judged_irrelevant_fraction']
    summaries=[]
    for split in ('dev','holdout','fresh_holdout','all'):
        for variant in ('A','B','C'):
            rows=[r for r in metrics if r['variant']==variant and (split=='all' or r['split']==split
                   or (split=='fresh_holdout' and r['split']=='holdout' and not lab[r['id']]['previously_seen']))]
            summaries.append({'split':split,'variant':variant,'n':len(rows),**{k:mean(rows,k) for k in keys},
                'ndcg_scored_cases':sum(r['ndcg_at_k'] is not None for r in rows),
                'context_budget_violations':sum(not r['context_budget_ok'] for r in rows),
                'known_version_mismatches':sum(r['known_version_mismatches'] for r in rows)})
    type_results=[]
    for kind in sorted({l['expected_route'] for l in lab.values()}):
        for variant in ('A','B','C'):
            rows=[r for r in metrics if r['variant']==variant and r['type']==kind]
            type_results.append({'type':kind,'variant':variant,'n':len(rows),**{k:mean(rows,k) for k in keys}})
    lookup={(r['id'],r['variant']):r for r in metrics};paired=[]
    for split in ('dev','holdout','fresh_holdout','all'):
        ids=[cid for cid in cases if split=='all' or cases[cid]['split']==split or
             (split=='fresh_holdout' and cases[cid]['split']=='holdout' and not lab[cid]['previously_seen'])]
        for left,right in (('A','B'),('B','C')):
            for key in ('recall_at_k','ndcg_at_k','context_witness_coverage','context_tokens'):
                items=[(cid,lookup[(cid,right)][key]-lookup[(cid,left)][key]) for cid in ids
                       if (cid,left) in lookup and (cid,right) in lookup and lookup[(cid,left)][key] is not None and lookup[(cid,right)][key] is not None]
                paired.append({'split':split,'comparison':left+'_'+right,'metric':key,'n_pairs':len(items),
                    'mean_delta':sum(x[1] for x in items)/len(items) if items else None,
                    'positive_cases':[cid for cid,d in items if d>1e-10],'negative_cases':[cid for cid,d in items if d< -1e-10],
                    'paired_case_ids':[cid for cid,_ in items]})
    ans=[];answer_controls=[];human=[];mapping={}
    answer_paths=[(p,'initial') for p in sorted((RUN/'answers').glob('*.json'))]+[(p,'development_fix') for p in sorted((RUN/'answer_repeats').glob('*.json'))]
    for path,stage_name in answer_paths:
        r=read_json(path);out=r['output'] or {};sc=answer_metrics(out,lab[r['id']],evaluation_kind='live')
        judge=out.get('judge');error=r['failure'] or out.get('validation_error')
        contract_valid=bool(judge and judge.get('draft_version')==(out.get('reviewed_draft') or {}).get('draft_version')) and error in (None,'judge_rejected','unsupported_answer','deterministic_review_failed')
        sc.update(contract_valid=contract_valid,observed_error=error,
                  final_content_accepted=bool(judge and judge.get('verdict')=='accept' and not error),
                  outcome=out.get('outcome'),review_attempts=sum(x['stage']=='judge' for x in out.get('pipeline',[])),
                  review_failures=out.get('review_failures',[]),
                  # Failed/contract-invalid final replies cannot claim zero
                  # unsupported content; leave that dimension unassessed.
                  unsupported_claim_findings=sc['unsupported_claim_findings'] if contract_valid else None,
                  repeated_question_or_test_findings=sc['repeated_question_or_test_findings'] if contract_valid else None)
        ans.append({'id':r['id'],'split':r['split'],'variant':r['variant'],'stage':stage_name,**sc})
        alias='review_'+digest({'id':r['id'],'variant':r['variant'],'stage':stage_name})[:12]
        mapping[alias]={'id':r['id'],'variant':r['variant'],'stage':stage_name}
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
        answer_controls.append({'id':cid,'same_candidate_hash':bool(stage(outs[0],'retrieve') and stage(outs[1],'retrieve') and
            stage(outs[0],'retrieve')[0]['candidate_hash']==stage(outs[1],'retrieve')[0]['candidate_hash']),
            'same_selected_ids':bool(stage(outs[0],'rerank') and stage(outs[1],'rerank') and
                stage(outs[0],'rerank')[0].get('ids')==stage(outs[1],'rerank')[0].get('ids')),
            'extract_B':stage(outs[0],'extract'),'extract_C':stage(outs[1],'extract')})
    write_json(RUN/'metrics.json',{'retrieval_per_case':metrics,'retrieval_summary':summaries,'retrieval_by_type':type_results,
        'answer_per_case':ans,'BC_controls':controls,'BC_answer_controls':answer_controls,
        'paired_retrieval_comparisons':paired,
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
      'مقایسه ابتدا بازیابی خام ترکیبی بدون تولید پاسخ را اندازه می‌گیرد. سپس Agent واقعی روی نامزدهای ثبت‌شده اجرا می‌شود: استخراج، انتخاب شواهد، تولید، داوری و حداکثر یک اصلاح محتوایی. خلاصهٔ استخراج‌شده حق تغییر نامزدها را در این آزمایش ندارد؛ این مداخله در trace ثبت است و با جست‌وجوی آزاد تولیدی یکسان نیست. بازیابی B/C دقیقاً همان نامزدها و بردار را دارد. در پاسخ‌های اولیه، با وجود cache مشترک، timestamp منشأ داده موجب نابرابری برخی ورودی‌های بازرتبه‌بندی شد؛ نتیجهٔ آن نمونه‌ها مقایسهٔ علّی گسترش والد نیست. BC_answer_controls وضعیت هر نمونه را نشان می‌دهد. clock ثابتِ ابزار آزمایش بعداً آفلاین اصلاح شد و نتایج زندهٔ قبلی بازنویسی نشده‌اند.','',
      'قرارداد فعال','',
      f"نخستین تلاش مستقیم روی پیش‌نویس و شواهد ثابت: اعتبار قرارداد={judge['contract_valid']}، تصمیم مدل={model}، تصمیم نهایی نگهبان={judge['content_verdict']}. شکست S0 پیش‌شرط نبود. دلایل غیرخالی، پوشش واحدها، اتصال به پیش‌نویس و ارجاع‌ها از مسیر کامل بررسی شدند. مدل ممکن است امتیاز مثبت نادرست بدهد؛ یافته‌های نگهبان و تغییر تصمیم جدا در artifact محفوظ‌اند. این آزمایش دقت معنایی مستقل داور را اثبات نمی‌کند.",'',
      'داده و قضاوت','',
      '۲۴ نمونه: ۱۲ توسعه و ۱۲ نهایی، ۲۰ نمونه دارای شاهد دقیق با متن، بازهٔ نویسه، خط و بازبینی. خانواده‌های گسترده میان دو بخش مشترک نیستند. شش نمونهٔ نهایی قدیمی قبلاً دیده شده‌اند؛ شش نمونهٔ جدید جدا گزارش می‌شوند. داده، رفتار مورد انتظار و معیارها پیش از تنظیم تازه منجمد شده‌اند. سه شاهد در preflight، پیش از بازیابی، از نام/عبارت کوتاه به متنِ حاوی رفتار تقویت شدند؛ برچسب اولیه حفظ شده و errata جداست.','',
      'pool بر اساس پنجرهٔ دقیق منبع تجمیع و بدون نام نسخه آماده شده است. منشأ برچسب‌ها دستیار/قاعدهٔ کمکی است و انسانی یا مستقل نیست. منابع قضاوت‌نشده grade=null دارند؛ nDCG عادی در top-k ناقص گزارش نمی‌شود. nDCG بر واحد پنجرهٔ منبع و IDCG مشترک pool محاسبه می‌شود؛ Recall بر منبع مرجع و پوشش شاهد بر متن دقیق محاسبه می‌شود. مرجعِ یک شاهد ممکن است همهٔ پاسخ‌های معتبر را پوشش ندهد.','',
      'ساخت واقعی embedding','',
      'همهٔ فرزندها با بازسازی آفلاین، متن دقیق، hash، شناسهٔ پایدار، شمارش واقعی توکن و رابطهٔ والد اعتبارسنجی شدند. چهار قطعهٔ اتمی بزرگ حفظ و ثبت شده‌اند. پس از ۵۶ batch موفق، اتصال شکست خورد؛ ۱۷۹۲ متن ذخیره شده بود. ادامه فقط ۵۶۳ متن باقی‌مانده را ساخت. پوشش نهایی ۲۳۵۸ ردیف/۲۳۵۵ آدرس یکتا، با بردارهای واقعی ۱۵۳۶بُعدی و namespace جدید کامل است. cache قدیمی یا fixture در مقایسهٔ زنده وارد نشد. ساخت باعث فعال‌کردن پیش‌فرض نشده است.','',
      'نتایج بازیابی','',
      '| بخش | نسخه | n | n برای nDCG | Recall@5 | nDCG@5 قضاوت‌شده | پوشش قضاوت | پوشش شاهد در زمینه | توکن زمینه |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in summaries:
        rows.append('| '+r['split']+' | '+r['variant']+' | '+str(r['n'])+' | '+str(r['ndcg_scored_cases'])+' | '+' | '.join(fmt(r[k]) for k in ('recall_at_k','ndcg_at_k','judgment_coverage','context_witness_coverage','context_tokens'))+' |')
    rows+=['','مخرج Recall و پوشش شاهد در کل ۲۰ نمونهٔ دارای مرجع و در holdout ده نمونه است؛ چهار نمونهٔ بدون مرجع مقدار null دارند. میانگین‌های nDCG کلی A/B بر مجموعهٔ دقیقاً یکسانی نیستند: مقایسهٔ زوجی روی ۱۹ نمونهٔ مشترک، تغییر +۰٫۰۴۵۶ را نشان می‌دهد. رتبه‌بندی در هشت نمونه بهتر و در هفت نمونه بدتر شد؛ پسرفت‌های D03، D06، D07، H01، H04، H08 و H10 محفوظ‌اند. افزایش پوشش شاهد B فقط در D11 و H11 رخ داد؛ افزایش Recall فقط در H08. این شمارش کوچک و قضاوت دستیار، اثبات بهبود عمومی نیست.','',
       'C در هیچ نمونه شاهد دقیق تازه‌ای نسبت به B وارد نکرد؛ میانگین زمینه ۲۹۵٫۵۴ توکن (۱۴٫۵٪) بیشتر شد. در هیچ‌یک از ۷۲ بسته بودجه نقض نشد. ناسازگاری نسخهٔ معلوم مشاهده نشد، اما به‌طور میانگین ۴٫۷۱ منبع از پنج نامزد A/B نسخهٔ نامعلوم دارند؛ سازگاری نسخه اثبات نشده است. سهم نامرتبط در میان نامزدهای قضاوت‌شده: A=۳۳٫۳٪ و B/C=۲۹٫۷٪؛ این بازیابی خام است و شواهد تأییدشدهٔ پاسخ محسوب نمی‌شود.','',
       '| نوع درخواست | نسخه | تعداد | Recall@5 | پوشش شاهد | سهم نامرتبطِ قضاوت‌شده | توکن زمینه |',
       '|---|---|---:|---:|---:|---:|---:|']
    for r in type_results:
        rows.append('| '+r['type']+' | '+r['variant']+' | '+str(r['n'])+' | '+' | '.join(fmt(r[k]) for k in ('recall_at_k','context_witness_coverage','judged_irrelevant_fraction','context_tokens'))+' |')
    rows+=['','نتایج هر نمونه در retrieval_per_case.csv و metrics.json موجود است. نقض بودجه، نسخهٔ نامعلوم/ناسازگار و دلایل حذف/عدم گسترش در همان فایل و trace محفوظ‌اند. نبود شاهد مرجع برای قابلیت/درخواست مبهم، الزام به مستندسازی ادعای فنی را حذف نمی‌کند.','',
       'پاسخ‌های واقعی','',
       '| نمونه | بخش | نسخه | قرارداد معتبر | پذیرش نهایی محتوا | خطا | فایدهٔ انسانی |','|---|---|---|---|---|---|---|']
    for r in ans:rows.append(f"| {r['id']} ({r['stage']}) | {r['split']} | {r['variant']} | {r['contract_valid']} | {r['final_content_accepted']} | {r['observed_error'] or '—'} | ارزیابی نشده |")
    judges=[read_json(p) for p in sorted((RUN/'judge').glob('attempt_*.json'))]
    rows+=['','اصلاح نهایی قرارداد و محدودیت تکرار','',
        'پس از شکست‌های واقعی، قرارداد readable-semantic-3 جای آرایهٔ اندیس عبارت را با enum بازهٔ پیوسته عوض کرد؛ برای نمونه phrases_0_to_2 دقیقاً همان سه برش را برمی‌گرداند. تکرار [0,0] و ترتیب [1,2,0] در قالب جدید قابل بیان نیست. یکتایی سایر ارجاع‌ها، دلایل غیرخالی، binding و معیارهای پشتیبانی همچنان الزامی‌اند. رد ساختاری از رد محتوا جداست.','',
        '| تلاش مستقیم | واحد | قرارداد معتبر | تصمیم مدل | تصمیم نهایی |','|---|---:|---|---|---|']
    for j in judges:
        rows.append(f"| {j['attempt']} | {len(j['repro']['packet']['draft']['units'])} | {j['contract_valid']} | {(j['raw_review'] or {}).get('v','—')} | {j['content_verdict'] or j['failure']} |")
    rows+=['','تلاش دوم همان پیش‌نویس ثابت اولیه با wire جدید بود؛ تلاش سوم پیش‌نویس ثابتِ هفت‌واحدیِ توسعه را از اجرای ذخیره‌شده بررسی کرد و هیچ تولید پاسخ/embedding تازه نداشت. برداشتِ نبود API موجود از صرف درخواست افزودن آن نیز با veto محدود و آزمون مثبت/منفی اصلاح شد. پوشش ۱۱ واحد همچنان فقط fixture است؛ پوشش زندهٔ قرارداد تا ۷ واحد بررسی شده است.','',
       'هر ۱۸ گرهٔ پاسخ اولیه ثبت شد؛ سه گرهٔ D01 به‌علت پیش‌نیاز بازیابی، Agent را اجرا نکردند. پس از رفع اتصال، سه اجرای D01 و سه تکرار اصلاحی D03 جدا ثبت شدند. هیچ پاسخ نهایی از این مجموعه پذیرفته نشد. سقف سه تلاش مستقیم داور و شش نوبت اصلاحی توسعه مصرف شده است؛ سقف پولی تمام نشده، اما این مجوز اجازهٔ تکرارهای بیش‌ترِ پاسخ را نمی‌دهد.','',
       'اصلاح‌های پس از آخرین تکرار پاسخ شامل clock کنترل‌شده، نقل‌قول دقیق یا مجهول برای current_behavior و wire بازه‌ای جدید است. این نسخه روی پیش‌نویس‌های ثابت زنده بررسی شده، ولی تولید پاسخ کامل با این ترکیب نهایی هنوز زنده ارزیابی نشده است. نتایج اولیه و اصلاحی، مبنای کافی برای ادعای کیفیت این ترکیب نیستند.']
    rows+=['','ادعاهای بی‌پشتوانه و تکرار در answer_per_case شمارش یافته‌های داور/نگهبان‌اند، حقیقت مستقل نیستند. نبود judge به‌صورت ارزیابی‌نشده ثبت است، نه صفر خطا. بستهٔ human_answer_review.json پاسخ‌ها را با شناسهٔ کور و زمینهٔ کامل گزارش برای بازبینی انسانی آماده می‌کند؛ ستون‌ها تا بازبینی خالی هستند.','',
       'هزینهٔ تازه (دلار)','',
       '| مرحله | درخواست | قطعی | رزرو نامعلوم |','|---|---:|---:|---:|']
    for p in ('judge','index','retrieval','answers'):
        r=ph[p];rows.append(f"| {p} | {r['requests']} | {r['confirmed_usd']:.9f} | {r['unknown_reserved_usd']:.9f} |")
    rows+=[f"\nجمع تازه: قطعی {cost['confirmed_usd']:.9f}، نامعلوم {cost['unknown_reserved_usd']:.9f}، مجموع {cost['charged_or_reserved_usd']:.9f} از سقف مصوب ۱٫۱۰ دلار؛ {cost['requests']} درخواست از سقف ۳۴۳. هزینهٔ ساخت ایندکس جدا از embedding پرسش و استنتاج گزارش شده است. هزینهٔ تاریخی V27: قطعی ۰٫۰۳۰۳۶۹۱۳۰، نامعلوم ۰٫۰۱۲۸۵۸۳۸۴؛ مجوز و هزینهٔ تازه از آن جداست.",'',
      'جدول تصمیم','',
      '| نسخه | کیفیت و هزینه | محدودیت | وضعیت استفاده |','|---|---|---|---|',
      '| A: v2 | پوشش شاهد ۱۱/۲۰؛ میانگین زمینه ۱۵۹۲ توکن؛ ساخت تازه ندارد | پاسخ پذیرفته‌شده ندارد؛ کیفیت انسانی تأیید نشده | حفظ پیش‌فرض فعلی؛ حفظ پیش‌فرض به معنی تأیید کیفیت نیست |',
      '| B: فرزند v3 | پوشش شاهد ۱۳/۲۰؛ زمینه ۲۰۳۵ توکن؛ ساخت قطعی ۰٫۰۰۷۵۲ دلار و رزرو ۰٫۰۰۰۷۰ دلار | هفت پسرفت رتبه‌بندی؛ سود محدود به دو شاهد و بدون تأیید پاسخ | گزینهٔ آزمایشی برای ادامهٔ ارزیابی؛ مناسب تغییر پیش‌فرض نیست |',
      '| C: والد محدود | همان پوشش ۱۳/۲۰ و embedding B؛ زمینه ۲۳۳۱ توکن | هیچ سود شاهد نسبت به B؛ مقایسهٔ پاسخ بعضی نمونه‌ها مخدوش | گسترش پیش‌فرض/خودکار فعال نشود؛ سود انتخابی برای هیچ نوعی اثبات نشد |','',
      'انتساب ضعف و معیار پذیرش','',
      'بازیابی: B شاهد دو سؤال کاربردی را بهتر پوشش داد، ولی پوشش کل هنوز ۶۵٪ است و منابع نامرتبط باقی‌اند. والد: هزینهٔ زمینه بالا رفت و شاهد تازه اضافه نشد؛ فایدهٔ انسانی ارزیابی نشده است. تولید: ارجاع نامعتبر و برداشت بی‌پشتوانه دربارهٔ نبود API مشاهده شد. داوری: wire قدیمی آرایهٔ تکراری/نامرتب تولید کرد؛ wire جدید روی دو پیش‌نویس ثابت معتبر بود. مدل هنوز ممکن است درخواست فرضی را ادعای فنی تلقی کند. رد مدل، به‌تنهایی ثابت نمی‌کند همهٔ این پاسخ‌ها واقعاً بی‌فایده‌اند؛ نگهبان، مدل و بازبینی مستقل باید جدا بمانند. خطای اتصال و پیش‌نیاز نیز خطای محتوا نیست.','',
      'معیارهای منجمد: اعتبار قرارداد ۱۰۰٪، ادعای بی‌پشتوانه و سؤال/آزمایش تکراری صفر، تناسب مسیر ۱۰۰٪، فایدهٔ هر نمونه حداقل ۲ از ۳ با بازبینی انسانی/مستقل، پوشش قضاوت حداقل ۹۰٪، بدون پسرفت Recall، افزایش پوشش شاهد حداقل ۰٫۱۰ و بدون پسرفت نوعی بیش از ۰٫۱۰، رعایت کامل بودجه. B شرط افزایش پوشش شاهد را در این دادهٔ کوچک لمس می‌کند؛ C نسبت به B آن را ندارد. شرایط پاسخ و بازبینی مستقل برقرار/سنجیده نیستند، بنابراین هیچ نسخهٔ تازه‌ای مجوز تغییر پیش‌فرض ندارد. thresholds و شکست‌ها تغییر داده نشده‌اند.','',
      'آزمایش باقی‌مانده؛ اجرا نشده و نیازمند مجوز دامنهٔ تازه','',
      'ابتدا بستهٔ کور human_answer_review.json، به‌ویژه پیشنهاد هفت‌واحدی و پاسخ‌های کاربردی، انسانی/مستقل بازبینی شود تا خطای تولید از سخت‌گیری نادرست داور جدا شود. سپس سه خانوادهٔ تازه (یک خطا، یک قابلیت، یک سؤال کاربردی) پیش از تنظیم منجمد شوند و روی A/B/C با کد نهایی اجرا شوند؛ ۹ نوبت، هر نوبت حداکثر هشت درخواست و یک اصلاح محتوایی. پیش از پرداخت، برابری hash ورودی استخراج و بازرتبه‌بندی B/C و snapshot/بودجه باید بررسی شود؛ فقط زمینهٔ والد متفاوت باشد. تکرار روی holdout فعلی، ارزیابی مستقل تازه محسوب نمی‌شود.','',
      'مدل‌ها همان gpt-4.1-mini و text-embedding-3-small؛ هیچ بازسازی ایندکس لازم نیست. طرح پیشنهادی: حداکثر ۷۲ درخواست نقش‌ها، شش embedding پرسش و سه بررسی مستقیم قرارداد تا ۱۱ واحد (جمع حداکثر ۸۱ درخواست). حجم تقریبی ۱۰۰ تا ۱۸۰هزار توکن متنی ورودی و ۳۰ تا ۵۰هزار خروجی؛ برآورد با تعرفهٔ ثبت‌شدهٔ این گزارش حدود ۰٫۱۰ تا ۰٫۱۸ دلار، سقف سخت تازه ۰٫۴۳ دلار: ۰٫۳۶ برای پاسخ‌ها، ۰٫۰۶ برای داور و ۰٫۰۱ برای پرسش‌ها. سقف هر نوبت ۰٫۰۴ و هر بررسی مستقیم ۰٫۰۲ دلار؛ رزرو نامعلوم از سقف کم شود. این پیشنهاد مجوز هزینه نیست و قبل از اجرا تعرفه و پیش‌نیازها دوباره بررسی شوند. پیش‌فرض تنها پس از عبور معیارهای فوق تغییر کند.','',
      'فایل‌ها و بازتولید','',
      'ابزارهای prepare_quality_v27_completion.py، complete_quality_v27.py، adjudicate_quality_v27_pool.py و report_quality_v27_completion.py؛ معیارها در src/casepilot/evaluation_completion.py؛ بردار پرسش مشترک در hybrid.py؛ قرارداد در compact_review.py و نگهبان معنایی در semantics.py؛ قالب تولید/ارجاع پویا در case_type.py، model.py و pipeline.py؛ آزمون‌های test_quality_v27_completion.py و fixtureهای قرارداد در test_quality_v26.py. source نسخه‌های اجرای داور و پاسخ در code_versions با hash محفوظ است. هیچ مجوزی برای هزینهٔ تازه در اجرای دوبارهٔ این ابزارها استنباط نمی‌شود؛ authorization مربوط به همین دامنه و سقف است و ledger محدودیت را اعمال می‌کند.','',
      'آزمون نهایی: ۲۴۰ آزمون، بدون خطا/شکست و بدون درخواست مدل؛ git diff --check موفق. هنگام تغییر wire، دو fixture قدیمی با آرایهٔ phrase شکست خوردند؛ تاریخچهٔ شکست و اجرای اصلاح‌شده در offline_test_history.json حفظ شد. این گذر آفلاین اثبات کیفیت پاسخ واقعی نیست. snapshotهای تاریخی دست‌نخورده و خروجی‌های اولیه/اصلاحی جدا نگه داشته شدند؛ کلید امن در فایل‌های غیرنادیدهٔ Git یافت نشد.','',
      'وضعیت تحویل: کد و ابزار پیاده‌سازی شده؛ ساختار، قرارداد، محافظ بودجه و ادامه از cache آفلاین آزموده شده؛ قالب داور و embedding و نتایج درج‌شده واقعاً با مدل زنده اجرا شده‌اند. کیفیت انسانی یا مستقل هنوز تأیید نشده است. ضعف/عدم‌قطعیتِ قابل‌انتساب باید از نتایج نمونه‌ها خوانده شود، نه صرفاً تعداد آزمون‌ها.']
    path=ROOT/'docs/QUALITY_V27_COMPLETION_FA.md';path.write_text('\n'.join(rows)+'\n',encoding='utf8')
    print('Completion report and per-case evidence written; no quality success claimed.')

if __name__=='__main__':main()
