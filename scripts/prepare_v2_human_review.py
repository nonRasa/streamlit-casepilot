"""Prepare a BLANK human form tied to exact V2 answers and judge scores."""
import argparse, csv, hashlib, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.roles import CRITERIA

def main(run):
    folder=Path(run).resolve(); allowed=(ROOT/'artifacts/architecture_v2').resolve()
    require(folder.is_relative_to(allowed),'invalid_path','فرم فقط برای نتیجهٔ معماری دوم ساخته می‌شود.')
    source=folder/'answers.jsonl'; rows=[json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line]
    require(all(r['output'].get('architecture')=='v2' for r in rows),'invalid_architecture','پاسخ‌ها مربوط به معماری دوم نیستند.')
    form=folder/'human_review.csv'; require(not form.exists(),'review_exists','فرم موجود بازنویسی نمی‌شود.')
    fields=['case_id','split','configuration_hash']+['human_'+k+'_0_2' for k in CRITERIA]+['human_overall_0_2','reviewer','notes']+['model_'+k+'_0_2' for k in CRITERIA]+['model_verdict']
    manifest=read_json(folder/'manifest.json')
    with form.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for r in rows:
            judge=r['output'].get('judge') or {}; scores=judge.get('scores',{})
            record={'case_id':r['id'],'split':r['split'],'configuration_hash':manifest['configuration_hash'],'model_verdict':judge.get('verdict')}
            record.update({'model_'+k+'_0_2':scores.get(k) for k in CRITERIA}); writer.writerow(record)
    write_json(folder/'human_review_manifest.json',{'at':utcnow(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'configuration_hash':manifest['configuration_hash'],'rows':len(rows),'human_review_pending':True,'reviewer_prefilled':False,
        'protocol':'Human reads raw report, latest facts, full final answer and source spans; independently scores before viewing model columns. Compare same criteria and report disagreements; do not substitute historical V1 AI review.'})
    print('وضعیت: فرم خالی انسانی با منشأ پاسخ‌ها آماده شد؛ امتیاز انسانی درج نشد.')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('run_folder'); main(p.parse_args().run_folder)
