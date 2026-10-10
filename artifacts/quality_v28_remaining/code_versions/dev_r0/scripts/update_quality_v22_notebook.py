"""Update the reviewable notebook without executing or rewriting old results."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    path=ROOT/'CasePilot_project.ipynb'; notebook=json.loads(path.read_text(encoding='utf-8'))
    for cell in notebook['cells']:
        source=''.join(cell['source'])
        if cell['cell_type']=='code':
            cell['execution_count']=None; cell['outputs']=[]
            if "'scripts/run_tests.py'" in source:
                source="subprocess.run([sys.executable, 'scripts/run_tests.py', '--output-dir', 'artifacts/quality_v22/notebook_tests'], cwd=ROOT, check=True)\nfolder = ROOT / 'artifacts/quality_v22/offline_comparison_01'\nif (folder / 'metrics.json').exists():\n    print('نتیجهٔ بازپخش؛ معیار کیفیت مدل نیست:', read_json(folder / 'metrics.json')['summary'])\nelse:\n    print('وضعیت: مقایسهٔ محفوظ هنوز موجود نیست؛ آزمون نهایی از نوت‌بوک اجرا نمی‌شود.')\n"
            if "'scripts/adversarial.py'" in source:
                source="subprocess.run([sys.executable, 'scripts/adversarial.py', '--output', 'artifacts/quality_v22/notebook_adversarial.json'], cwd=ROOT, check=True)\nprint('نتیجهٔ کنترل‌های قطعی:', read_json(ROOT / 'artifacts/quality_v22/notebook_tests/test_results.json'))\n"
            if 'RUN_LIVE = False' in source:
                source="RUN_LIVE = False\nif RUN_LIVE:\n    raise RuntimeError('این نوت‌بوک اجازهٔ هزینهٔ تازه نمی‌دهد؛ سقف صریح و بررسی دفتر هزینه لازم است.')\nprint('وضعیت: ارزیابی پولی، بازبینی انسانی و آزمون واقعی سایت در این دور انجام نشده‌اند.')\nprint('راهنما: طرح و گزارش نسخهٔ جدید در docs/QUALITY_V22_PROTOCOL_FA.md و docs/QUALITY_V22_FA.md است.')\ntemporary.cleanup()\n"
        elif 'مرحلهٔ تولید، داوری' in source:
            source='## مرحلهٔ تولید، داوری و گفت‌وگو\n\nتوضیح: نسخهٔ `v2.2-quality` برای هر فیلد کامل پاسخ، شناسهٔ وابسته به پرونده، نسخهٔ وضعیت و نسل پیش‌نویس می‌سازد. داور فقط شناسه را به شاهد و یکی از چهار حالت پشتیبانی وصل می‌کند. نسخهٔ قدیمی، شناسهٔ ناشناخته و نقل‌قول جعلی در کد رد می‌شوند. خرابی قرارداد از ضعف محتوایی جدا ثبت می‌شود. سؤال و آزمایش با معیار فایده و تازگی بررسی می‌شوند. داور مدل بازبین انسانی نیست.\n'
        cell['source']=source.splitlines(keepends=True)
    note={'id':'quality-v22-memory-note','cell_type':'markdown','metadata':{},'source':['## مرحلهٔ حافظهٔ ساخت‌یافته و نسخه\n','\n','توضیح: نمونهٔ بعدی فقط کنترل کد است. نسخهٔ شبانه کامل می‌ماند، پیشنهاد آزمایش به انجام واقعی تبدیل نمی‌شود و حافظه پس از بازکردن دوبارهٔ پایگاه باقی می‌ماند. عنوان خالی محیط مقدار معلوم نیست.\n']}
    code="from casepilot.agent import extract_facts\nfrom casepilot.memory import diagnostic_findings\nassert extract_facts('Streamlit version: 1.51.1.dev20251130')['streamlit_version'] == '1.51.1.dev20251130'\nassert not extract_facts('Streamlit version:\\nPython version:')\nwith tempfile.TemporaryDirectory() as temp:\n    memory_path = Path(temp) / 'memory.sqlite3'\n    memory_store = Store(memory_path)\n    quote = 'I disabled rerun; memory remained.'\n    event = dict(action='disable rerun', conditions=[], status='failed', result=quote, quote=quote, supersedes='')\n    memory_store.update('memory-demo', quote, experiment_events=[event])\n    state = Store(memory_path).get('memory-demo')\n    proposal = dict(decision='ask', diagnostic=dict(action='بدون بازاجرا', conditions=[], repeat_of='', changed_condition='', repeat_reason='', missing_fact=''))\n    assert diagnostic_findings(proposal, state)\n    assert not state['comments']\n    print('وضعیت: تکرارِ آزمایش انجام‌شده با بیان متفاوت رد شد؛ اثر رهگیر ثبت نشد.')\n"
    if not any(c.get('id')=='quality-v22-memory-code' for c in notebook['cells']):
        notebook['cells'][4:4]=[note,{'id':'quality-v22-memory-code','cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':code.splitlines(keepends=True)}]
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
if __name__=='__main__': main()
