"""Create a blank independent-human form for actual paired outputs."""
import csv,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.roles import CRITERIA

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation'; target=folder/'human_review.csv'
    require(not target.exists(),'form_exists','فرم انسانی موجود بازنویسی نمی‌شود.')
    assignments=read_json(folder/'ai_review_assignment.json')
    fields=['review_id','source_key','output_sha256']+['human_'+c+'_0_2' for c in CRITERIA]+['human_overall_0_2','reviewer','notes']
    with target.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in assignments: w.writerow(r)
    write_json(folder/'human_review_manifest.json',{'at':utcnow(),'rows':len(assignments),'human_review_pending':True,
        'form_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'source_assignment_sha256':hashlib.sha256((folder/'ai_review_assignment.json').read_bytes()).hexdigest(),
        'protocol':'Blank human columns. Read corresponding packet and original output; author independent scores and reasons. AI grades must not be relabeled human.'})
    print('Blank human rows:',len(assignments))

if __name__=='__main__':main()
