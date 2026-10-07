"""Generate portable schemas, n8n JSON, notebook and request examples. No credentials."""
import argparse, json, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import write_json
from casepilot.model import SCHEMA

def node(name,kind,parameters,x,y,version=2,credentials=None):
    row={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'casepilot/'+name)),'name':name,'type':'n8n-nodes-base.'+kind,'typeVersion':version,'position':[x,y],'parameters':parameters}
    if credentials: row['credentials']={'httpHeaderAuth':{'id':'','name':credentials}}
    if kind=='webhook': row['webhookId']=str(uuid.uuid5(uuid.NAMESPACE_URL,'casepilot-webhook/'+name))
    return row

def workflow(base_url):
    nodes=[]; connections={}
    for index,(route,review,required,optional) in enumerate([
        ('turn',False,['case_id','message','request_id'],['facts','checks','method']),
        ('review',True,['case_id','proposal_id','proposal_hash','decision','reviewer'],['edited_actions']),
        ('execute',True,['case_id','proposal_id','approval_id'],[]) ]):
        y=index*320; prefix=route.title()
        incoming='CasePilot Reviewer Webhook' if review else 'CasePilot Operator Webhook'
        backend='CasePilot Reviewer API' if review else 'CasePilot Operator API'
        names=[prefix+' Webhook',prefix+' Validate',prefix+' Python API',prefix+' Response']
        js="const b=$json.body; const required="+json.dumps(required)+"; const optional="+json.dumps(optional)+";\nif(!b || typeof b!=='object' || Array.isArray(b) || required.some(k=>!(k in b)) || Object.keys(b).some(k=>!required.includes(k)&&!optional.includes(k))) throw new Error('Invalid request fields');\nif(typeof b.case_id!=='string'||! /^[A-Za-z0-9_-]{1,80}$/.test(b.case_id)) throw new Error('Invalid case ID');\nreturn [{json:{body:b}}];"
        nodes.extend([
            node(names[0],'webhook',{'httpMethod':'POST','path':'casepilot-'+route,'authentication':'headerAuth','responseMode':'responseNode','options':{}},0,y,credentials=incoming),
            node(names[1],'code',{'mode':'runOnceForAllItems','jsCode':js},240,y),
            node(names[2],'httpRequest',{'method':'POST','url':base_url.rstrip('/')+'/api/'+route,
                 'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth',
                 'sendBody':True,'specifyBody':'json','jsonBody':'={{ JSON.stringify($json.body) }}',
                 'options':{'timeout':90000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'json'}}}},500,y,4.2,backend),
            node(names[3],'respondToWebhook',{'respondWith':'json','responseBody':'={{ $json.body }}','options':{'responseCode':'={{ $json.statusCode }}'}},760,y,1.4)
        ])
        for a,b in zip(names,names[1:]): connections[a]={'main':[[{'node':b,'type':'main','index':0}]]}
    return {'name':'CasePilot — Turn, Human Review, Execute','nodes':nodes,'connections':connections,'active':False,
            'settings':{'executionOrder':'v1','saveDataSuccessExecution':'none','saveDataErrorExecution':'none','saveManualExecutions':False,'executionTimeout':180},
            'pinData':{},'tags':[], 'meta':{'templateCredsSetupCompleted':False}}

def notebook():
    cells=[]
    def md(text): cells.append({'id':f'cell-{len(cells):02d}','cell_type':'markdown','metadata':{},'source':text.splitlines(keepends=True)})
    def code(text): cells.append({'id':f'cell-{len(cells):02d}','cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':text.splitlines(keepends=True)})
    md('# پروژهٔ دستیار پیگیری پرونده\n\nراهنما: این نوت‌بوک مسیر داده، بازیابی، پاسخ مستند، تأیید انسانی، آزمون و ارزیابی را مانند تمرین‌ها اجرا می‌کند. حالت پیش‌فرض `replay` است و هیچ کلید یا هزینه‌ای ندارد. خروجی آزمایشی، نتیجهٔ مدل واقعی محسوب نمی‌شود.')
    code("from pathlib import Path\nimport sys, json, subprocess, tempfile\nROOT = Path.cwd()\nif not (ROOT / 'src' / 'casepilot').exists():\n    raise RuntimeError('نوت‌بوک را از ریشهٔ پروژه باز کنید.')\nsys.path.insert(0, str(ROOT / 'src'))\nfrom casepilot.common import read_json\nfrom casepilot.store import Store\nfrom casepilot.retrieval import Retriever\nfrom casepilot.agent import Agent\nfrom casepilot.model import ReplayClient\nprint('وضعیت: محیط آماده است.')")
    md('## مرحلهٔ داده و مرز ارزیابی\n\nتوضیح: گزارش‌های واقعی از دادهٔ ثابت خوانده می‌شوند. پرونده‌های ارزیابی، نظرها و خانواده‌های تکراری‌شان پیش از قطعه‌بندی از بازیابی کنار گذاشته شده‌اند. ارزیابی روی snapshot کنونی است و ادعای بازسازی تاریخی ندارد.')
    code("manifest = read_json(ROOT / 'data' / 'snapshot_manifest.json')\nprint(json.dumps({k: manifest[k] for k in ('issue_count','comments_retained','docs_count','chunks','split','excluded_docs')}, ensure_ascii=False, indent=2))\ncases = read_json(ROOT / 'eval' / 'cases.json')\nprint('تعداد پرونده‌های توسعه:', sum(c['split']=='dev' for c in cases))")
    md('## مرحلهٔ بازیابی و استناد\n\nتوضیح: روش پایه جست‌وجوی واژگانی است. روش نهایی ادغام رتبهٔ واژه و سه‌نویسه، گسترش واژگان و تنوع منبع را اضافه می‌کند. کنترل خودکار، وجود نقل‌قول در منبع را می‌سنجد؛ تشخیص کامل صحت معنایی همچنان نیازمند بازبینی است.')
    code("retriever = Retriever()\nquery = 'session_state widget value resets after navigation'\nfor method in ('baseline','final'):\n    rows = retriever.search(query, method=method)\n    print('روش:', method)\n    print([(r['source_id'], r['section']) for r in rows])")
    md('## مرحلهٔ پاسخ و گفت‌وگوی وابسته\n\nتوضیح: اطلاعات تازه جای واقعیت قبلی را می‌گیرد و در سابقه ثبت می‌شود. هیچ نظر عمومی در این مرحله ثبت نمی‌شود.')
    code("temporary = tempfile.TemporaryDirectory(prefix='casepilot-notebook-')\nstore = Store(Path(temporary.name) / 'tracker.sqlite3')\nagent = Agent(store, retriever, ReplayClient())\nfirst = agent.turn('notebook-case', 'مقدار session_state پس از جابه‌جایی صفحه تغییر می‌کند.', 'nb-turn-1')\nprint(first['response'])\nsecond = agent.turn('notebook-case', 'پاسخ: نسخه مشخص شد و نمونهٔ کوچک هم رفتار را دارد.', 'nb-turn-2', facts={'streamlit_version':'1.49.0','reproducible':True})\nprint(second['response'])\nassert len(store.get('notebook-case')['comments']) == 0")
    md('## مرحلهٔ تأیید انسانی و اقدام\n\nراهنما: متن پیشنهاد را بخوانید. مقدار `REVIEW_DECISION` را خودتان انتخاب کنید. مقدار پیش‌فرض `reject` است. تأیید همین متن و همین پرونده معتبر است و ویرایش نیازمند تأیید تازه است.')
    code("REVIEW_DECISION = 'reject'\np = second['proposal']\nreview = store.review('notebook-case', p['id'], p['hash'], REVIEW_DECISION, 'بازبین نوت‌بوک')\nif REVIEW_DECISION == 'approve':\n    result = store.execute('notebook-case', p['id'], review['approval_id'])\n    repeated = store.execute('notebook-case', p['id'], review['approval_id'])\n    assert repeated['replayed']\n    print(json.dumps(result, ensure_ascii=False, indent=2))\nelse:\n    assert len(store.get('notebook-case')['comments']) == 0\n    print('وضعیت: پیشنهاد رد شد و تغییری ثبت نشد.')")
    md('## مرحلهٔ آزمون و ارزیابی توسعه\n\nتوضیح: اجرای زیر رایگان است. سنجهٔ تصمیم در بازپخش فقط یک شاخص مسیر است؛ کیفیت مدل واقعی، درستی علت و مفیدبودن پاسخ را ثابت نمی‌کند. آزمون نهایی باید پس از قفل تنظیمات اجرا شود.')
    code("subprocess.run([sys.executable, 'scripts/run_tests.py'], cwd=ROOT, check=True)\nsubprocess.run([sys.executable, 'scripts/evaluate.py', '--split', 'dev'], cwd=ROOT, check=True)")
    md('## مرحلهٔ ارزیابی خصمانه\n\nتوضیح: ورودی‌های تزریقی و مجوزهای جعلی در چند خانواده آزموده می‌شوند. بازپخش مقاومت مدل واقعی در برابر تزریق را اثبات نمی‌کند؛ نتیجهٔ مکانیزم مجوز و استناد جدا گزارش می‌شود.')
    code("subprocess.run([sys.executable, 'scripts/adversarial.py'], cwd=ROOT, check=True)")
    md('## مرحلهٔ اتصال واقعی پس از دریافت کلید\n\nراهنما: کلید و نام مدل و تعرفه را فقط در محیط تنظیم کنید. ابتدا نمونهٔ کوچک توسعه اجرا شود. مقدار زیر پیش‌فرض خاموش است. راهنمای دقیق در فایل `docs/LIVE_RUN_FA.md` آمده است.')
    code("RUN_LIVE = False\nif RUN_LIVE:\n    subprocess.run([sys.executable, 'scripts/evaluate.py', '--mode', 'live', '--split', 'dev', '--limit', '2', '--no-scenarios'], cwd=ROOT, check=True)\nelse:\n    print('وضعیت: اجرای واقعی انجام نشده؛ کلید هنوز دریافت نشده است.')\ntemporary.cleanup()")
    return {'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.11'}},'nbformat':4,'nbformat_minor':5}

def main(base):
    write_json(ROOT/'schemas'/'answer.schema.json',SCHEMA)
    write_json(ROOT/'policies'/'tool_manifest.json',{'tools':[
        {'name':'read_case','implementation':'Store.get','input':{'case_id':'string'},'output':'case state, pending proposal, comments','errors':['invalid_id','not_found'],'write':False},
        {'name':'search_evidence','implementation':'Retriever.search','input':{'query':'string','k':'integer <= 5','method':'baseline | final'},'output':'versioned source chunks','errors':['invalid_input','invalid_method'],'write':False},
        {'name':'prepare_proposal','implementation':'Store.propose','input':{'case_id':'string','revision':'integer','payload':'validated actions and summary'},'output':'proposal id, hash, revision','errors':['invalid_action','conflict'],'write':'internal draft only'},
        {'name':'review_proposal','implementation':'Store.review','input':{'decision':'approve | reject | edit','proposal_hash':'string','reviewer':'authenticated actor'},'output':'approval or replacement draft','errors':['stale_approval','proposal_changed','already_reviewed'],'write':'internal approval only'},
        {'name':'execute_approved','implementation':'Store.execute','input':{'case_id':'string','proposal_id':'string','approval_id':'string'},'output':'stored effects and idempotent result','errors':['approval_required','approval_expired','stale_approval','resolution_unconfirmed'],'write':'local tracker only'}]})
    write_json(ROOT/'policies'/'execution_policy.json',{'max_steps_per_turn':5,'max_model_calls_per_turn':1,'max_user_turns_per_case':100,'max_retrieved_chunks':5,'max_context_characters':10000,'max_message_characters':20000,'max_actions':3,'approval_ttl_seconds':900,'team_budget_usd':5,'auto_execute':False,'allowed_gateway_host':'api.metisai.ir','writes':'local SQLite only'})
    write_json(ROOT/'workflows'/'casepilot_main.json',workflow(base))
    write_json(ROOT/'CasePilot_project.ipynb',notebook())
    write_json(ROOT/'examples'/'turn.json',{'case_id':'demo-1','request_id':'example-turn-1','message':'مقدار session_state پس از تغییر صفحه از بین می‌رود.','facts':{},'checks':[]})
    write_json(ROOT/'examples'/'review.json',{'case_id':'demo-1','proposal_id':'COPY_FROM_TURN_RESULT','proposal_hash':'COPY_FROM_TURN_RESULT','decision':'reject','reviewer':'نگه‌دارنده'})
    write_json(ROOT/'examples'/'execute.json',{'case_id':'demo-1','proposal_id':'COPY_FROM_TURN_RESULT','approval_id':'COPY_FROM_REVIEW_RESULT'})
    write_json(ROOT/'artifacts'/'live_run_manifest.json',{'status':'not_run','provider_requests':0,'reason':'API key has not been provided; no fabricated model results.','n8n_status':'JSON generated; user imports and verifies on their own instance.'})
    print('وضعیت: نوت‌بوک، قراردادها و گردش‌کار ساخته شدند.')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--backend-url',default='https://YOUR-CASEPILOT-BACKEND.example'); main(p.parse_args().backend_url)
