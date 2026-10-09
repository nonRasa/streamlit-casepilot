"""Bind manually authored grades to actual final output hashes; no API or scoring rules."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.roles import CRITERIA

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation'
    notes=read_json(ROOT/'eval/quality_ai_review_notes.json')
    packets=read_json(folder/'ai_review_packets.json');rows=[]
    require(set(notes)=={p['review_id'] for p in packets},'incomplete_review','یادداشت اختصاصی همهٔ خروجی‌ها لازم است.')
    for p in packets:
        n=notes[p['review_id']]
        require(n['output_sha256']==p['output_sha256'] and len(n['grades'])==7,'review_source_mismatch','خروجی بازبینی‌شده تغییر کرده است.')
        rows.append({'review_id':p['review_id'],'output_sha256':p['output_sha256'],
            'scores':dict(zip(CRITERIA,n['grades'][:6])),'overall':n['grades'][6],'notes':n['notes'],
            **({'reused_review_provenance':n['reused_review_provenance']} if n.get('reused_review_provenance') else {})})
    write_json(folder/'ai_review.json',rows);print('Authored AI grades saved:',len(rows))

if __name__=='__main__':main()
