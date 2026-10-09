"""Prospective annotations authored from initial reports BEFORE model inference."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
ANNOTATIONS={
6939:('ambiguous',['ask','escalate'],['docs:session_state','docs:widget-behavior'],'نسخه‌های ۱٫۲۴ و ۱٫۲۲، ویندوز و پایتون مشخص‌اند؛ کد واقعی مؤلفه و روش نگه‌داری انتخاب ارائه نشده. مقایسهٔ نسخه دلیل اثبات علت نیست.'),
6798:('escalate',['escalate','ask'],['docs:page-and-navigation','api:navigation'],'درخواست چند نوار کناری است؛ توابع پیشنهادی کاربر قابلیت موجود محسوب نشوند و نیاز گفته‌شده دوباره پرسیده نشود.'),
6772:('escalate',['escalate','ask'],['docs:session_state','docs:widget-behavior'],'درخواست رخداد ترک صفحه برای پاک‌سازی است؛ ماندگاری دلخواه وضعیت با رفع اشکال اشتباه نشود.'),
10089:('escalate',['escalate','ask'],['docs:session_state','docs:widget-behavior'],'درخواست تابع مقداردهی اولیه است؛ کد حلقهٔ کاربر مقدارها را بی‌قید می‌نویسد. تابع فرضی به‌عنوان موجود معرفی نشود.'),
10029:('ambiguous',['ask','escalate'],['docs:widget-behavior','docs:widgets'],'نمونهٔ کامل و نسخهٔ ۱٫۴۱٫۱ موجودند؛ وضعیت گزینهٔ انتخاب‌شده و نمایی که برچسب آن مشکل دارد روشن شود؛ کد یا نسخه دوباره خواسته نشود.'),
10020:('ambiguous',['ask','escalate'],['api:file_uploader','docs:config-toml','docs:architecture'],'محلی و ابری، مرورگر دیگر، فایل دیگر، محیط تازه و خاموش‌کردن حفاظت آزموده شده‌اند. خطای شبکه و سرور در لحظهٔ بارگذاری هنوز گزارش نشده؛ حفاظت خاموش پیشنهاد نشود.'),
9460:('escalate',['escalate','ask'],['api:file_uploader','docs:where-file-uploader-store-when-deleted'],'کد نمونهٔ داخلی برای جریان‌دهی روی دیسک است؛ بررسی نگه‌دارنده لازم است. اندازهٔ دلخواه یا پارامتر فرضی تضمین نشود.'),
9454:('escalate',['escalate','ask'],['api:file_uploader','docs:widget-behavior'],'درخواست حذف دسته‌ای فایل‌ها مشخص است؛ سؤال دربارهٔ نیاز یا حذف یکی‌یکی تکراری است. تصویر خوانده نشده.'),
9362:('ambiguous',['ask','escalate'],['docs:widgets','docs:session_state'],'کد فراخوانی چندانتخاب موجود است ولی بدنهٔ visualize ارائه نشده؛ بررسی انتقال add_col به traceهای نمودار پرسش مفید است.'),
10041:('escalate',['escalate','ask'],['docs:session_state','docs:architecture','api:cache_resource'],'درخواست شناسهٔ مرورگر پایدار است؛ نمونهٔ کوکی و حافظهٔ مشترک، احراز هویت امن یا قابلیت رسمی اثبات نمی‌کند.'),
10025:('ambiguous',['ask','escalate'],['api:cache_data','docs:caching'],'نسخه و کد status.update موجودند؛ آزمایش مقایسهٔ بدون کش یا رخداد cache hit تفکیک‌کننده است. نسخهٔ رفع ادعا نشود.'),
9789:('ambiguous',['ask','escalate'],['docs:dataframes','docs:architecture'],'خطا فقط فایرفاکس، تعداد ۹۴ ستون و نسخه‌ها مشخص‌اند؛ مقایسهٔ حذف صفحه‌بندی یا اندازهٔ جدول آزمایش تازه است.'),
9689:('ambiguous',['ask','escalate'],['docs:page-and-navigation','docs:theming'],'نشانک، تفکیک‌پذیری و نسخهٔ مرورگر معلوم‌اند؛ حذف تصویر/ویجت یا مقایسهٔ بزرگنمایی تازه است. ویدیو خوانده نشده.'),
9614:('ambiguous',['ask','escalate'],['docs:dynamic-navigation','docs:session_state','docs:architecture'],'بازخوانی صفحه و ورود و نسخه مشخص‌اند؛ کد کنترل نقش و ساخت صفحات ارائه نشده. نشست مرورگر با احراز هویت یکی فرض نشود.'),
9551:('escalate',['escalate','ask'],['api:navigation','docs:page-and-navigation'],'درخواست جمع‌شدن گروه‌های ناوبری است؛ پارامتر فرضی collapse یا تاریخ انتشار تضمین نشود.'),
}
def main():
    target=ROOT/'eval/v2_final_cases.json'; require(not target.exists(),'evaluation_exists','برچسب‌های قفل‌شده بازنویسی نمی‌شوند.')
    fresh=read_json(ROOT/'eval/v2_final_candidates.json'); known=read_json(ROOT/'eval/cases.json')
    corpus=read_json(ROOT/'data/corpus_v2.json'); sources={r['source_id'] for r in corpus}
    for r in fresh:
        category,allowed,relevant,note=ANNOTATIONS[r['issue_number']]
        require(set(relevant)<=sources,'invalid_sources','منابع معیار باید در ایندکس باشند.')
        r.update(category=category,allowed_decisions=allowed,relevant_source_ids=relevant,oracle_note=note,
            annotation_pending=False,annotation_method='Prospective AI-assisted annotation of initial report; no comments/future resolution/model outputs. Source labels are approximate investigative relevance, not a verified solution.')
    cases=[c for c in known if c['split']=='dev']+fresh
    write_json(target,cases)
    plans=read_json(ROOT/'eval/scenarios.json')
    mapping=dict(zip([s['case_id'] for s in plans if s['split']=='test'],['GH6939','GH10020','GH10025','GH9789','GH9614']))
    for s in plans:
        s['id']='V2'+s['id']; s['synthetic_followups']=True
        if s['split']=='test': s['case_id']=mapping[s['case_id']]; s['split']='test_fresh'
    write_json(ROOT/'eval/v2_final_scenarios.json',plans)
    write_json(ROOT/'eval/v2_final_freeze.json',{'at':utcnow(),'cases_sha256':digest(cases),'scenarios_sha256':digest(plans),
        'dev':15,'test_fresh':15,'scenarios':10,'annotation_source':'Visible initial report only, before any V2 full-run inference.',
        'limitations':['Not human-independent annotations. Query buckets overlap semantic topics.',
        'Initial reports are public historical reports, evaluated against current frozen corpus; not historical replay.',
        'Unknown related families, pretrained model knowledge, indirect source labels, uninspected linked media and attachments remain possible.']})
    print('prospective cases',len(cases),'scenarios',len(plans))
if __name__=='__main__': main()
