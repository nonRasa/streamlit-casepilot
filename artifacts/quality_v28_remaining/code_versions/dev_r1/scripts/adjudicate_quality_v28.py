"""Evidence-linked assistant inspection, explicitly not independent/human gold."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json
from prepare_quality_v28 import RUN

SPECS=[
 ('development_fix_D01_A',[3,4,7],
  'فرضیهٔ ناسازگاری داخلی از شرط pickleable بودن نتیجه نمی‌شود. سؤال درخواست traceback تازه دارد، اما دوباره نمونهٔ کد می‌خواهد؛ کل تابع کاربر ارائه نشده، پس تکراری بودن تمام درخواست کد قطعی نیست.',
  'I tested pickle outside Streamlit and it works.',
  'ممکن است خطای pickle ناشی از محدودیت یا ناسازگاری داخلی',
  'Cached objects are stored in "pickled" form, which means that the return\nvalue of a cached function must be pickleable.'),
 ('initial_H03_A',[3,4,7],
  'تنظیم فعال‌سازی و آزمایش مرورگر قبلاً گزارش شده‌اند. درخواست کل config می‌تواند اطلاعات تازه بدهد، اما فرض وجود گزینهٔ تنظیم مسیر static اثبات نشده است. داور بعضی قدم‌های تشخیصی را ادعای نسخه‌دار دانسته؛ علت 404 قابل انتساب نیست.',
  'My config already contains [server] enableStaticServing=true',
  'تنظیمات مربوط به مسیر فایل static',
  'Media stored in the folder `./static/` relative to the running app file is served at path\n`app/static/[filename]`'),
 ('initial_D03_A',[3,4,5],
  'درخواست قابلیت روشن است؛ پرسش درباره وجود API و تأمین پیاده‌سازی نامتناسب است. شرط پذیرش شرطی ادعای وجود قابلیت نیست. نگهبان regex قدیمی عبارت باعث تغییر عرض شود را بی‌جهت ادعا می‌گرفت؛ این ایراد مستقل از ایرادهای دیگر پاسخ است.',
  'Acceptance: dragging changes width only when the option is enabled.',
  'کشیدن لبه دیالوگ فقط زمانی باعث تغییر عرض شود',None),
 ('development_fix_D03_A',[3,4],
  'ادعای نبود گزینه از درخواست افزودن آن نتیجه نمی‌شود. رد این انتساب درست است، ولی داور متن هدف و شرح خواسته را هم با پیش‌فرض فنی علامت زده؛ رأی خام و تفسیر واحدها باید جدا خوانده شوند.',
  'Feature request: add an option to resize a dialog by dragging its edge.',
  'در حال حاضر هیچ گزینه‌ای برای تغییر اندازه یک کادر گفتگو با کشیدن لبه آن وجود ندارد',None),
 ('initial_H02_C',[3,4,7],
  'متن خطای issue شاهد رفتار مشاهده‌شدهٔ گزارش‌دهنده است؛ نسخهٔ محصول شاهد نامعلوم است و محدودیت قطعی 1.18.0 را ثابت نمی‌کند. پرسش درباره خواستن توضیح، پاسخ کاربردی مفیدی نیست. والد حضور دارد ولی انطباق تاریخی را اضافه نکرده است.',
  'Our deployed Streamlit version is 1.18.0.',
  'در نسخه 1.18.0 استریم‌لیت فقط مجاز',
  'StreamlitAPIException: set_page_config() can only be called once per app page, and must be called as the first Streamlit command in your script.'),
 ('initial_H09_A',[3,4],
  'راهنمای انتخاب ابزار در زمینه موجود است. پاسخ می‌توانست راهنمای مفهوم را با محدودیت نسخه بدهد؛ سؤال نسخه به‌تنهایی هدف را برآورده نمی‌کند. فیلد ویژگی در سؤال کاربردی ساخته شده و معنای reported_fact ندارد. پشتیبانی علت نسخه‌دار و orphan با هم بررسی شده‌اند.',
  'Which should I use to interactively edit tabular data',
  'کدام نسخه استریم‌لیت را استفاده می‌کنید',
  'If you want to interactively edit data, use [st.data_editor]'),
 ('initial_H09_B',[3,4],
  'همان شاهد کاربردی در فرزند v3 هم حاضر است؛ رشد کیفیت بازیابی به‌تنهایی خطای تولید/داوری را رفع نکرد. نسخهٔ نامعلوم باید محدودیت مرئی داشته باشد، نه اینکه جای راهنمای کاربردی را بگیرد.',
  'Version unknown.',
  'آیا نسخه خاصی از استریم‌لیت مدنظر شماست',
  'If you want to interactively edit data, use [st.data_editor]'),
]

def locate(bundle,scope,needle):
    if scope=='user':texts=[('/full_user_report',bundle['full_user_report'])]
    elif scope=='draft':texts=[('/reviewed_draft/units/'+str(i)+'/text',x['text']) for i,x in enumerate(bundle['reviewed_draft']['units'])]
    else:texts=[('/actual_context/'+str(i)+'/text',x['text']) for i,x in enumerate(bundle['actual_context'])]
    pointer,text=next((p,t) for p,t in texts if needle in t)
    start=text.index(needle)
    return {'scope':scope,'json_pointer':pointer,'start':start,'end':start+len(needle),'quote':needle}

def main():
    target=RUN/'forensics';rows=[]
    for name,categories,explanation,user,draft,source in SPECS:
        bundle=read_json(target/(name+'.json'))
        evidence=[locate(bundle,'user',user),locate(bundle,'draft',draft)]
        if source:evidence.append(locate(bundle,'source',source))
        raw=[r['raw_reply'] for r in bundle['raw_role_replies'] if r['role']=='judge' and r['raw_reply']]
        rows.append({'run':name,'review_origin':'assistant inspection; neither human nor independent',
            'categories':categories,'assessment_fa':explanation,'evidence':evidence,
            'context_loss_observed':False,'context_reconstruction_verified':bundle['context_reconstruction_verified'],
            'raw_judge_verdicts':[r.get('v',r.get('verdict')) for r in raw],
            'checked_verdicts':[r['verdict'] for r in bundle['checked_reviews']],
            'guard_findings':[{k:x.get(k) for k in ('attempt','draft_version','findings')} for x in bundle['checked_reviews']],
            'bundle':name+'.json','uncertainty':'Cannot independently establish true product cause or overall response quality.'})
    write_json(target/'assistant_adjudications.json',{'categories':{
        '1':'necessary witness not retrieved','2':'retrieved witness absent from context','3':'generator misuse',
        '4':'judge false positive/negative or erroneous unit interpretation','5':'deterministic guard misinterpretation',
        '6':'contract/gateway/infrastructure','7':'insufficient evidence for causal attribution'},
        'reviews':rows,'provider_requests':0,'independent_or_human_review':False,
        'actionable_roots':[
            {'id':'R1','problem':'Generator instructions and response route permit redundant/bundled requests and invented availability/mechanisms.',
             'fix':'One active generator prompt, empty nonfeature fields, fresh single-target action and request/claim distinction.'},
            {'id':'R2','problem':'Selected quotes absent from review units; source version ambiguity not attached to visible quote.',
             'fix':'Source-bound quotation units and server-derived visible applicability notices.'},
            {'id':'R3','problem':'Speech act/premise/version selections confused by wire encoding; conditional requested behavior overmatched by old guard.',
             'fix':'Descriptive semantic field names derived from one mapping; conditional-request positive/negative guard tests.'}]})
    print('Seven source-linked assistant inspections written; no independent/human claim.')

if __name__=='__main__':main()
