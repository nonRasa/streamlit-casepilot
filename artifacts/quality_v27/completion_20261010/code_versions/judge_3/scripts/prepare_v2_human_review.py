"""Prepare a BLANK human form tied to exact V2 answers and judge scores."""
import argparse, csv, hashlib, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.roles import CRITERIA

def main(run,refresh_blank=False):
    folder=Path(run).resolve(); allowed=(ROOT/'artifacts/architecture_v2').resolve()
    require(folder.is_relative_to(allowed),'invalid_path','فرم فقط برای نتیجهٔ معماری دوم ساخته می‌شود.')
    source=folder/'answers.jsonl'; rows=[json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line]
    require(all(r['output'].get('architecture')=='v2' for r in rows),'invalid_architecture','پاسخ‌ها مربوط به معماری دوم نیستند.')
    form=folder/'human_review.csv'
    if form.exists():
        require(refresh_blank,'review_exists','فرم موجود بازنویسی نمی‌شود.')
        with form.open(encoding='utf-8-sig',newline='') as f: old=list(csv.DictReader(f))
        human_keys=['human_'+k+'_0_2' for k in CRITERIA]+['human_overall_0_2','reviewer','notes']
        require(len(old)==len(rows) and all(not r.get(k) for r in old for k in human_keys),'review_started','فرم دارای بازبینی انسانی حفظ می‌شود.')
        require([(r['case_id'],r['split']) for r in old]==[(r['id'],r['split']) for r in rows],'review_mismatch','منشأ فرم متفاوت است.')
    fields=['review_id','case_id','split','variant','configuration_hash','output_sha256']+['human_'+k+'_0_2' for k in CRITERIA]+['human_overall_0_2','reviewer','notes']+['model_'+k+'_0_2' for k in CRITERIA]+['model_verdict']
    manifest=read_json(folder/'manifest.json')
    with form.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for r in rows:
            judge=r['output'].get('judge') or {}; scores=judge.get('scores',{}) if not r['output']['validation_error'] else {}
            variant=r.get('variant','full')
            record={'review_id':r['split']+'/'+variant+'/'+r['id'],'case_id':r['id'],'split':r['split'],'variant':variant,
                'configuration_hash':manifest['configuration_hash'],'output_sha256':digest(r['output']),
                'model_verdict':judge.get('verdict') if not r['output']['validation_error'] else 'fallback:'+r['output']['validation_error']}
            record.update({'model_'+k+'_0_2':scores.get(k) for k in CRITERIA}); writer.writerow(record)
    write_json(folder/'human_review_manifest.json',{'at':utcnow(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'configuration_hash':manifest['configuration_hash'],'rows':len(rows),'human_review_pending':True,'reviewer_prefilled':False,
        'form_sha256':hashlib.sha256(form.read_bytes()).hexdigest(),
        'protocol':'Human reads raw report, latest facts, full final answer and source spans; independently scores before viewing model columns. Compare same criteria and report disagreements; do not substitute historical V1 AI review.'})
    print('وضعیت: فرم خالی انسانی با منشأ پاسخ‌ها آماده شد؛ امتیاز انسانی درج نشد.')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('run_folder'); p.add_argument('--refresh-blank',action='store_true'); args=p.parse_args(); main(args.run_folder,args.refresh_blank)
