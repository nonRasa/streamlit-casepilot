"""Assistant case inspection of delivered outputs, not a second model/human."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json
from prepare_quality_v28 import RUN,DATA

FINAL={
 'H1_A':('محتوایی',0,False,[3,4,7],
  'شاهد مستقل‌بودن تنظیم sidebar در v2 آمده است. پیشنهاد آزمایش بخش sidebar تازه است، اما دو سؤال و تعمیم اعمال‌نشدن تم عمومی باقی است. داور rationale را unknown می‌نامد؛ هیچ علت قطعی اثبات نشده.',
  'آیا با اضافه کردن این تنظیم، رنگ نوار کناری تغییر می‌کند؟'),
 'H1_B':('محتوایی',0,False,[1,3,4,7],
  'فرزند شامل شاهد دقیق مرجع نیست؛ متن راه‌اندازی مجدد را انتخاب می‌کند، با اینکه کاربر قبلاً restart کرده است. نسخهٔ دیگر یا سایر رنگ‌ها آزمایش واحد روشنی نیست؛ انتساب علت ناکافی است.',
  'نسخه استریم‌لیت دیگری یا با پیکربندی سایر تنظیمات تم'),
 'H2_A':('محتوایی',1,False,[3,4],
  'رفتار پیشنهادی و شرط پذیرش عمدتاً وفادارند؛ report_quotes به متن دقیق متصل نیست و داور ارجاع پیام بعضی شروط را unknown می‌گذارد. ارجاع عمومی تحویلی شرح پیشنهاد قابل‌پذیرش نیست.',
  'با فعال کردن این گزینه، هر هفته قابل مشاهده در تقویم شماره هفته ISO خود را نشان می‌دهد'),
 'H2_B':('محتوایی',1,False,[3,4],
  'خواستهٔ روشن به پرسش درباره پشتیبانی و امکان فنی منحرف می‌شود. انتساب دقیق گزارش و ارزیابی واحدهای ترجمه‌شده همچنان نادرست است؛ نبود سند API پیشنهادی علت رد خودِ پیشنهاد نیست.',
  'وضعیت فعلی و امکان فنی پشتیبانی نمایش شماره هفته ISO'),
 'H3_A':('پذیرش محصول؛ ممیزی معنایی نامعتبر',2,True,[3,4,5],
  'راهنمای مفهوم و تنظیم مشخص مفید و در کل زمینه مستند است. ولی داور next_step/rationale را procedure با assertion=none علامت می‌زند، همه وابستگی‌های متقابل را standalone می‌نامد، و limitation را روی جملهٔ اول نقل‌قول می‌گذارد. selected quote شامل مسیر config و گزارهٔ صدور خطا نیست؛ آن‌ها در متن دیگری از زمینه هستند. نگهبان این ممیزی ناقص را قبول کرده است. پشتیبانی هستهٔ پاسخ از کل زمینه با پوشش ادعا در ارجاع منتخب یکسان نیست.',
  'این گزینه باعث می‌شود که تنها اشیاء قابل pickle شدن'),
 'H3_B':('محتوایی',0,False,[3,4],
  'هستهٔ راهنمای کاربردی در شواهد و پیش‌نویس هست. داور گزارهٔ مستند را observation کاربر معرفی می‌کند؛ نقص محدودیت در prose اولیه هم باقی بوده است. رد محصول به معنی نبود راهنمای صحیح در corpus نیست.',
  'مقادیر غیرقابل پیکل باعث خطا می‌شوند'),
}

def pointer_quote(record,needle):
    units=(record['output'] or {}).get('reviewed_draft',{}).get('units',[])
    i,u=next((i,u) for i,u in enumerate(units) if needle in u['text'])
    start=u['text'].index(needle)
    return {'json_pointer':'/output/reviewed_draft/units/'+str(i)+'/text','start':start,'end':start+len(needle),'quote':needle}

def main():
    metrics=read_json(RUN/'metrics.json');rows=[]
    for stem,m in metrics['per_turn'].items():
        record=read_json(RUN/'turns'/(stem+'.json'));final=m['product_gate_accepted']
        # Abstaining from technical content does not prove route usefulness.
        scores={'unsupported_claims':0,'repeated_question_or_test':0,'route_fit':False,'usefulness_0_to_3':0}
        if m['category']=='technical_unassessed':scores={k:None for k in scores}
        if final:scores.update(unsupported_claims=None,route_fit=True,usefulness_0_to_3=2)
        m['final_content_metrics']=scores
        m['final_content_explanation']='Assistant inspection of delivered fallback; no useful requested answer. No independent/human judgement.' if not final else 'Useful concept guidance; semantic/citation audit gaps prevent certifying quality.'
    for key,(status,usefulness,fit,categories,note,needle) in FINAL.items():
        stem='holdout_r0_'+key
        if key.startswith('H1'):stem+='_connection_retry'
        record=read_json(RUN/'turns'/(stem+'.json'));m=metrics['per_turn'][stem]
        m['final_content_metrics'].update(usefulness_0_to_3=usefulness,route_fit=fit)
        m['final_content_explanation']=note
        rows.append({'case_variant':key,'effective_turn':stem,'product_status':status,
            'assistant_usefulness_0_to_3':usefulness,'assistant_route_fit':fit,'categories':categories,
            'assessment_fa':note,'draft_evidence':pointer_quote(record,needle),
            'meets_frozen_quality_acceptance':False,'human_review':None,'independent_review':None,
            'origin':'Assistant inspecting its own implementation; neither human nor independent.'})
    write_json(RUN/'metrics.json',metrics)
    write_json(RUN/'assistant_final_reviews.json',{'rows':rows,'quality_success_demonstrated':False,
        'usefulness_rubric':'0=no useful delivered answer;1=generic handoff/partial proposal;2=specific useful qualified guidance;3=complete independently checked response',
        'default_decision':'keep_v2','live_product_gate_accepted':1,'live_product_gate_rejected':5,
        'effective_final_technical_unassessed':0,'original_connection_failures_retained':3,
        'provider_requests':0,'post_holdout_runtime_tuning':False})
    print('Six effective final reviews written; one gate acceptance is not certified quality.')

if __name__=='__main__':main()
