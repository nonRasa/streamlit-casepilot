"""Offline snapshot preparation. All evaluation families excluded before chunking."""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json, write_json, redact, digest, utcnow

DEV={17119,17093,16388,14710,16732,17250,12607,9218,12150,14639,14593,11528,14793,13002,12432}
FAMILIES=[{17119,17093,16388,7338},{14710,16732},{12607,9218},{14593,11528}]
# Manual prospective annotations from initial report, NOT final GitHub labels.
# Acceptable decisions allow more than one defensible next step.
ANNOTATIONS={
17119:('ambiguous',['ask','escalate'],['widget-behavior','session_state'],'بررسی زمان حذف و نمایش مجدد کلید؛ ادعای رفع در نسخه‌ای خاص مجاز نیست.'),
16914:('ambiguous',['ask','escalate'],['architecture','session-state'],'تفکیک قطع اتصال از تبدیل داده؛ نسخه، محیط و خروجی بازتولید مستقل بررسی شود.'),
17112:('ambiguous',['ask','escalate'],['fragments','session-state'],'تفکیک اجرای کامل و جزئی و توالی فراخوانی در نمونهٔ تو در تو؛ علت قطعی از عنوان نتیجه نشود.'),
16388:('ambiguous',['ask','escalate'],['session_state','widget-behavior'],'تفاوت حذف کلید و وضعیت سمت مرورگر در اجرای بعدی بررسی شود.'),
16269:('ambiguous',['ask','escalate'],['widget-behavior'],'کنترل اثر تغییر متن نمایشی با ثابت نگه‌داشتن مقدار و کلید؛ نیازمند شاهد نسخهٔ مرتبط.'),
14710:('ambiguous',['ask','escalate'],['state-and-triggers','architecture'],'تفکیک مقدار اولیه از رخداد و زمان بازگشت فرانت‌اند؛ پیشنهاد اجرای کد ناشناس ممنوع.'),
17093:('ambiguous',['ask','escalate'],['widget-behavior','session_state'],'بررسی مقدار پیش‌فرض نوشته‌شده در اجرای پیشین و نخستین نمایش ویجت.'),
17290:('escalate',['escalate','ask'],['dataframes','theming'],'درخواست بهبود دسترس‌پذیری ابزار؛ قابلیت یا تاریخ انتشار تضمین نشود.'),
16977:('ambiguous',['ask','escalate'],['architecture','bottom'],'مقایسهٔ ورودی گفت‌وگو با ورودی متن در همان ظرف؛ قصد رابط و رفتار نخستین اجرا روشن شود.'),
17250:('escalate',['escalate','ask'],['get-started','query_params'],'رفتار آزمون با مرورگر واقعی مقایسه شود؛ همگام‌سازی پارامترها فرض نشود.'),
16732:('ambiguous',['ask','escalate'],['state-and-triggers','widget-behavior'],'بازنصب مؤلفه و callback و احتمال ازدست‌رفتن رخداد بررسی شود؛ کلید ثابت به‌تنهایی دلیل کافی نیست.'),
17249:('ambiguous',['ask','escalate'],['get-started','widgets'],'پایداری ویجت در بازاجرای همان صفحه بین محیط آزمون و مرورگر مقایسه شود.'),
12607:('answerable',['answer','ask'],['where-file-uploader-store-when-deleted','file_uploader'],'چرخهٔ عمر فایل و مصرف حافظه بررسی شود؛ حذف مرجع معادل آزادشدن قطعی حافظه نیست.'),
10049:('ambiguous',['ask','escalate'],['config-toml','architecture'],'هدر واقعی درخواست و پاسخ و تنظیمات پروکسی بررسی شود؛ خاموش‌کردن حفاظت پیش‌فرض پیشنهاد نشود.'),
12189:('ambiguous',['ask','escalate'],['file_uploader','widget-behavior'],'طول فهرست نوع فایل و نسخه در بازتولید رابط مقایسه شود؛ تصاویر خوانده‌نشده شاهد متنی نیستند.'),
9218:('answerable',['answer','ask'],['where-file-uploader-store-when-deleted','file_uploader'],'حجم فایل و حافظهٔ محیط بررسی شود؛ راهنمای حافظه شاهد است نه تضمین یک نسبت مصرف ثابت.'),
12150:('ambiguous',['ask','escalate'],['navigation','file_uploader'],'بازتولید روی محیط تازه و مقایسهٔ اجرای تک‌صفحه با ناوبری؛ نصب مجدد انجام‌شده تکرار نشود.'),
8534:('ambiguous',['ask','escalate'],['file_uploader','architecture'],'تعداد فایل و خطای شبکه از فرض محدودیت بازگشت جدا شود؛ سقف داخلی ۹۸۰ ادعا نشود.'),
14639:('ambiguous',['ask','escalate'],['caching','cache-data'],'جداسازی هویت تابع و منبع کد و کلید حافظه در دو صفحه؛ نتایج متفاوت آزمایش شوند.'),
11157:('ambiguous',['ask','escalate'],['caching','cache-data'],'متغیر آزاد و پارامتر صریح در دو تابع بررسی شوند؛ علت یا نسخهٔ رفع بدون شاهد قطعی نشود.'),
14593:('ambiguous',['ask','escalate'],['cache-data','cache-resource'],'قابلیت سریال‌سازی مقدار بازگشتی و وابستگی به اجرای مجدد کلاس بررسی شود.'),
6620:('answerable',['answer','ask'],['cache-data','caching'],'نام و قابلیت عمومی خطا با مستندات نسخه تطبیق داده شود؛ همهٔ خطاها یکسان تلقی نشوند.'),
11528:('ambiguous',['ask','escalate'],['cache-data','cache-resource'],'نمونهٔ کوچک سریال‌سازی و تفاوت نسخه‌ها بررسی شود؛ جایگزینی کش منابع بدون بررسی اشتراک و ایمنی تضمین نشود.'),
10615:('answerable',['answer','ask'],['caching','cache-resource'],'قابلیت هش آرگومان اتصال و ایمنی اشتراک منبع جدا بررسی شوند؛ اتصال خصوصی یا توکن اجرا نشود.'),
14793:('answerable',['answer','ask'],['widget-behavior','widget-updating-session-state'],'هویت ویجت و کلید صریح با مقدار پیش‌فرض متغیر بررسی شود.'),
14031:('escalate',['escalate','ask'],['caching','overview'],'پیش‌محاسبهٔ داده از ذخیرهٔ صفحهٔ تعاملی جدا شود؛ قابلیت پیش‌بارگذاری تضمین نشود.'),
13002:('escalate',['escalate','ask'],['page-and-navigation','dynamic-navigation'],'مخفی‌کردن رابط معادل مجوز دسترسی نیست؛ منطق ناوبری و احراز هویت بررسی شود.'),
11922:('escalate',['escalate','ask'],['set_page_config','page-and-navigation'],'امکان منوی تعاملی جدید تضمین نشود؛ نیاز و گزینهٔ رابط فعلی روشن شود.'),
12432:('ambiguous',['ask','answer'],['static-file-serving'],'نشانی درخواست فایل و وضعیت شبکه و فاصلهٔ نام فایل بررسی شود؛ نگاشت مسیر به‌تنهایی اثبات رفع نیست.'),
11920:('escalate',['escalate','ask'],['context','theming'],'مقدار تم در اجرای اول و پس از بازاجرا بررسی شود؛ گزارش قابلیت ناقص دلیل رفع نیست.'),
}

FRESH_ANNOTATIONS={
7336:('ambiguous',['ask','escalate'],['cache-resource','architecture'],'تفکیک اتصال مشترک پایگاه داده از رفتار بازاجرا؛ نمونهٔ اولیه شبه‌کد است و علت قطعی ندارد.'),
10701:('escalate',['ask','escalate'],['dataframes','session_state'],'درخواست حفظ انتخاب و مرتب‌سازی و پیمایش؛ ذخیرهٔ داده با حفظ وضعیت رابط یکسان نیست.'),
8608:('ambiguous',['ask','escalate'],['state-and-triggers','session_state'],'تفکیک مؤلفهٔ نسل اول از نسل دوم و callback غیررسمی؛ راهنمای جدید برای نسخهٔ قدیمی تضمین نیست.'),
16474:('ambiguous',['ask','escalate'],['widget-behavior'],'دامنهٔ تاریخ و خروجی بازتولید بررسی شوند؛ جزئیات بازهٔ عددی گزارش بدون منبع مستقل واقعیت مستند محسوب نشود.'),
16375:('escalate',['ask','escalate'],['button-behavior-and-examples','widget-behavior'],'درخواست گروه دکمه با رفتار رخداد؛ حالت جدید انتخاب یا تاریخ انتشار تضمین نشود.'),
16495:('escalate',['ask','escalate'],['widget-behavior','theming'],'درخواست نمای کارت برای انتخاب؛ پارامتر پیشنهادی گزارش به‌عنوان قابلیت موجود عرضه نشود.'),
2311:('ambiguous',['ask','escalate'],['file_uploader','where-file-uploader-store-when-deleted'],'عمر شیء فایل و بازاجرای ویجت در نسخهٔ قدیمی بررسی شود؛ شاهد نسخهٔ جدید دلیل رفع نسخهٔ قدیمی نیست.'),
3122:('answerable',['answer','ask'],['file_uploader','architecture'],'تفاوت فراخوانی در ظرف فعلی و فراخوانی صریح نوار کناری بررسی شود؛ نام قدیمی رابط بدون تطبیق نسخه پیشنهاد نشود.'),
8151:('escalate',['ask','escalate'],['file_uploader'],'درخواست بازخورد بصری ناحیهٔ بارگذاری؛ تصویر بررسی‌نشده شاهد نتیجهٔ فنی نیست.'),
6182:('ambiguous',['ask','escalate'],['caching','cache-data'],'نوع آرایه و مقدار کلید در اجرای تکراری مقایسه شود؛ نسخهٔ رفع از نظرها به ورودی نشت نکند.'),
6215:('escalate',['ask','escalate'],[],'درخواست پشتیبانی نسخهٔ جدید کتابخانهٔ نمودار؛ منبع مستقیم پاسخ از نسخه‌های انتشار کنار گذاشته شده است؛ این پرونده در مخرج پوشش منبع نیست.'),
6109:('ambiguous',['ask','escalate'],['cache-data','caching'],'متد نمونه و آرگومان خودکار و تغییر نسخه بررسی شوند؛ سریال‌سازی به‌تنهایی توضیح خطای آرگومان نیست.'),
6525:('answerable',['answer','ask'],['button-behavior-and-examples','session_state'],'ترتیب اجرای تابع بازخوانی و تغییر صفحه با نمونهٔ کوچک بررسی شود؛ یک کلیک تضمین رفع همهٔ شرایط نیست.'),
6237:('ambiguous',['ask','escalate'],['set_page_config','page-and-navigation'],'وراثت چیدمان میان صفحات و وجود فراخوانی صریح تنظیمات بررسی شود؛ رفتار مطلوب با رفتار مستند مخلوط نشود.'),
8815:('escalate',['ask','escalate','answer'],['page-and-navigation','overview'],'تفاوت ساختار پوشهٔ صفحات و ناوبری جدید و محل اعلان نشان بررسی شود؛ رفع قطعی در نسخهٔ نامشخص ادعا نشود.'),
}

def clean(text):
    text=redact(text or '').replace('\r\n','\n').replace('\r','\n')
    text=re.sub(r'<img\b[^>]*>','[IMAGE OMITTED: not inspected]',text,flags=re.I)
    text=re.sub(r'!\[[^\]]*\]\([^)]*\)','[IMAGE OMITTED: not inspected]',text)
    text=re.sub(r'(?im)^.*(?:api.views-badge.org|hits.seeyoufarm.com).*$','',text)
    text=re.sub(r'(?im)^.*(?:_streamlit_xsrf|ajs_anonymous_id|document\.cookie\s*=|cookie=jwt).*$','[COOKIE VALUE REDACTED]',text)
    # Preserve decorators and code. Redact GitHub mentions only outside fenced blocks.
    fenced=False; cleaned=[]
    for line in text.splitlines():
        if line.lstrip().startswith('```'): fenced=not fenced
        if not fenced and not line.startswith('    '):
            line=re.sub(r'(?<!\w)@[A-Za-z0-9_-]+(?![\w.(])','[USER]',line)
        cleaned.append(line)
    text='\n'.join(cleaned)
    return re.sub(r'\n{4,}','\n\n\n',text).strip()

def chunks(source):
    lines=source['text'].splitlines(); groups=[]; start=1; section=source['title']; pending=[]
    def emit(end):
        if pending:
            text='\n'.join(pending).strip()
            if len(text)>60: groups.append((start,end,section,text))
    for no,line in enumerate(lines,1):
        # YAML frontmatter and generated API placeholders are not technical evidence.
        if no==1 and line.strip()=='---':
            front_end=next((j for j in range(2,len(lines)+1) if lines[j-1].strip()=='---'),0)
        if lines and lines[0].strip()=='---' and no<=front_end:
            start=no+1; continue
        if re.fullmatch(r'\s*</?[A-Za-z][^>]*>\s*',line):
            line=''  # Drop MDX component placeholders, preserve original line positions.
        if line.startswith('#') and len('\n'.join(pending))>150:
            emit(no-1); pending=[]; start=no
        if line.startswith('#'): section=line.lstrip('# ').strip()
        if pending and len('\n'.join(pending))+len(line)>2000:
            emit(no-1); pending=[]; start=no
        pending.append(line)
    emit(len(lines))
    out=[]
    for index,(a,b,heading,text) in enumerate(groups):
        out.append({'id':source['id']+f':{index:03d}','source_id':source['id'],'kind':source['kind'],
                    'title':source['title'],'section':heading,'text':text,'lines':[a,b],
                    'url':source['url']+f'#L{a}-L{b}' if '/blob/' in source['url'] and not source['id'].startswith('api:') else source['url'],
                    'revision':source['revision'],'product_version':source.get('product_version'),
                    'issue_number':source.get('issue_number'),'sha256':hashlib.sha256(text.encode()).hexdigest()})
    return out

def main():
    issues=read_json(ROOT/'data'/'issues_snapshot.json'); docs=read_json(ROOT/'data'/'docs_snapshot.json')
    original_ids=read_json(ROOT/'data'/'eval_selection.json'); by_id={x['number']:x for x in issues}
    freeze_path=ROOT/'eval'/'freeze_manifest.json'
    ids=sorted(DEV)+read_json(freeze_path)['new_test_issue_numbers'] if freeze_path.exists() else original_ids
    annotations=dict(ANNOTATIONS,**{})
    annotations.update(FRESH_ANNOTATIONS)
    assert set(ids)<=set(annotations) and len(ids)==30 and len(DEV)==15
    cases=[]
    for n in ids:
        row=by_id[n]; cat,decisions,sources,note=annotations[n]
        family=next(('family-'+str(min(g)) for g in FAMILIES if n in g),'issue-'+str(n))
        body=clean(row['body']); title=clean(row['title'])
        cases.append({'id':f'GH{n}','issue_number':n,'url':row['html_url'],'split':'dev' if n in DEV else 'test',
                      'family_id':family,'category':cat,'topic':row['topic'],
                      'initial_message':title+'\n\n'+body,'initial_facts':{},'initial_checks':[],
                      'allowed_decisions':decisions,'relevant_source_ids':[{'file_uploader':'api:file_uploader','navigation':'api:navigation','cache-data':'api:cache_data','cache-resource':'api:cache_resource','set_page_config':'api:set_page_config'}.get(x,'docs:'+x) for x in sources],
                      'oracle_note':note,'annotation_method':'manual prospective rubric; not final state/labels',
                      'evaluation_time_policy':'current frozen snapshot; not a historical replay',
                      'missing_information':['exact failing environment','independent minimal reproduction result'],
                      'forbidden_conclusions':['unverified fixed version','closed means resolved','similar issue proves same cause']})
    # Entire related families are kept on one side of the split.
    families={}
    for c in cases:
        assert c['family_id'] not in families or families[c['family_id']]==c['split']
        families[c['family_id']]=c['split']
    write_json(ROOT/'eval'/'cases.json',cases)
    excluded=set(ids)|set(original_ids)  # Retired smoke cases stay excluded from retrieval.
    # Follow explicit duplicate / follow-up edges including external issue numbers.
    edges=[]
    for row in issues:
        text=(row['body'] or '')+'\n'+'\n'.join(c['body'] or '' for c in row['comments_data'])
        refs=[int(x) for x in re.findall(r'(?i)(?:duplicate\s+of|follow.up\s+to)\s*(?:https://github.com/streamlit/streamlit/issues/|#)(\d+)',text)]
        edges.extend((row['number'],n) for n in refs)
    for family in FAMILIES: edges.extend((min(family),n) for n in family)
    changed=True
    while changed:
        changed=False
        for a,b in edges:
            if (a in excluded)!=(b in excluded): excluded.update((a,b)); changed=True
    sources=[]; exclusions=[]; comment_count=0
    for row in issues:
        row['body']=clean(row['body']); row['title']=clean(row['title'])
        comments=[]
        for c in row['comments_data']:
            body=clean(c['body'])
            if 'Your feedback helps us prioritize' in body or 'Your vote helps us identify' in body: continue
            comments.append(dict(c,body=body))
        row['comments_data']=comments; comment_count+=len(comments)
        text=row['title']+'\n\n'+row['body']+'\n\n'+'\n\n'.join(c['body'] for c in comments)
        linked=any(re.search(r'(?:#|issues/)'+str(n)+r'\b',text) for n in excluded)
        if row['number'] in excluded or linked:
            exclusions.append({'number':row['number'],'reason':'heldout family or links to heldout case'}); continue
        sources.append({'id':'issue:'+str(row['number']),'kind':'issue','title':row['title'],'text':text,
                        'url':row['html_url'],'revision':row['updated_at'],'product_version':None,'issue_number':row['number']})
    docs_excluded=[]; redacted_sections=[]
    for doc in docs:
        text=doc['text']; parts=re.split(r'(\n\s*\n)',text); removed=0
        for index,part in enumerate(parts):
            has_ref=any(re.search(r'(?:#|issues/|pull/)'+str(n)+r'\b',part) for n in excluded)
            semantic_answer=doc['kind']=='release' and bool(re.search(r'(?i)altair\s*(?:version\s*)?5',part))
            if has_ref or semantic_answer:
                parts[index]='\n'*part.count('\n'); removed+=1
        if removed:
            text=''.join(parts); redacted_sections.append({'source_id':doc['id'],'paragraphs_removed':removed,'reason':'heldout issue reference or direct Altair-5 answer','line_numbers_preserved':True})
        sources.append(dict(doc,text=text))
    corpus=[c for source in sources for c in chunks(source)]
    write_json(ROOT/'data'/'corpus.json',corpus)
    write_json(ROOT/'data'/'issues_snapshot.json',issues)
    manifest={'created_at':utcnow(),'docs_commit':'695e6ce2fb1b23afc6df66b40420ab0013ad72fd',
              'issue_count':len(issues),'comments_retained':comment_count,'comments_fetched_for_issues':sum(x['comments_complete'] for x in issues),
              'comments_not_fetched_for_issues':sum(not x['comments_complete'] for x in issues),
              'docs_count':len(docs),'indexed_sources':len(sources),'chunks':len(corpus),
              'eval_count':len(cases),'split':{'dev':15,'test':15},'excluded_issue_families':sorted(excluded),
              'excluded_sources':exclusions,'excluded_docs':docs_excluded,
              'redacted_doc_sections':redacted_sections,
              'policy':'Current snapshot evaluation; all heldout cases/comments/final labels outside retrieval. Explicit duplicate edges + manual families + links screened. Unknown duplicates and prior model knowledge remain limitations.',
              'cleaning':'Normalize line endings; omit uninspected images/bot votes, redact email, handles, cookie lines, key-shaped strings; preserve code and traceback.',
              'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['data/corpus.json','data/issues_snapshot.json','data/docs_snapshot.json','eval/cases.json']}}
    write_json(ROOT/'data'/'snapshot_manifest.json',manifest)
    print(json.dumps({k:manifest[k] for k in ('issue_count','comments_retained','docs_count','indexed_sources','chunks','excluded_docs')},indent=2))

if __name__=='__main__': main()
