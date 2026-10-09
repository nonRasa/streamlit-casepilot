"""Acquire 15 never-acquired initial reports after freezing revised code.

Fixed 2023-2025 window and descending creation order; 3 per predeclared topic.
No comments, labels, state, final resolution or generated outputs retained.
"""
import re,sys,hashlib
from pathlib import Path
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from collect_data import fetch,TOPICS
from prepare_data import clean
from evaluate_quality import frozen_files

def main():
    target=ROOT/'eval/quality_candidates.json'
    require(not target.exists(),'evaluation_exists','انتخاب تازه بازنویسی نمی‌شود.')
    before=frozen_files(False)
    known={r['number'] for r in read_json(ROOT/'data/issues_snapshot.json')}
    known|={r['issue_number'] for r in read_json(ROOT/'eval/v2_final_cases.json')}
    # Exclude every issue returned in earlier acquisition, even when not selected.
    for path in (ROOT/'data/raw').glob('*.json'):
        data=read_json(path)
        if '/search/issues?' in data.get('url',''):
            known|={x['number'] for x in data['payload'].get('items',[]) if 'number' in x}
    corpus=read_json(ROOT/'data/corpus_v2.json'); corpus_text='\n'.join(x['text'] for x in corpus)
    picked=[]; exclusions=[]; queries=[]
    for topic in TOPICS:
        term={'session_state':'"session state"','widget':'input','file_uploader':'upload','cache_data':'cache','multipage':'navigation'}[topic]
        q=f'repo:streamlit/streamlit is:issue {term} in:title,body created:2023-01-01..2025-12-31'
        url='https://api.github.com/search/issues?'+urlencode({'q':q,'per_page':100,'sort':'created','order':'desc'})
        queries.append(url); payload=fetch(url); count=0
        for row in sorted(payload['items'],key=lambda r:(r['created_at'],r['number']),reverse=True):
            n=row['number']; body=row.get('body') or ''; refs={int(x) for x in re.findall(r'(?:issues/|#)(\d+)\b',body)}; reason=None
            selected={x['issue_number'] for x in picked}
            if n in known|selected: reason='previously acquired or already selected'
            elif re.search(r'(?:issues/|pull/|#)'+str(n)+r'\b',corpus_text): reason='referenced by frozen corpus'
            elif refs & (known|selected): reason='explicit known family link'
            elif any(re.search(r'(?:issues/|#)'+str(n)+r'\b',x['initial_message']) for x in picked): reason='reverse selected family link'
            elif not 500<=len(body)<=12000: reason='outside fixed text size'
            elif re.search(r'(?i)duplicate|follow.up to',row['title']+'\n'+body): reason='possible duplicate/follow-up'
            if reason: exclusions.append({'number':n,'reason':reason}); continue
            picked.append({'id':f'GH{n}','issue_number':n,'topic':topic,'url':row['html_url'],'created_at':row['created_at'],
                'initial_message':clean(row['title'])+'\n\n'+clean(body),'initial_facts':{},'initial_checks':[],
                'split':'test_fresh','family_id':'quality-unseen-'+str(n)})
            count+=1
            if count==3: break
        if count!=3:
            write_json(ROOT/'artifacts/quality_revision/selection_incomplete.json',{'at':utcnow(),'queries':queries,'exclusions':exclusions,'counts_selected':len(picked),'topic_failed':topic,'no_inference_performed':True})
            require(False,'insufficient_holdout','سه پروندهٔ تازه برای هر موضوع پیدا نشد.')
        print('selected',topic,count,flush=True)
    require(frozen_files(False)==before,'configuration_changed','کد حین انتخاب تغییر کرد.')
    write_json(target,picked)
    write_json(ROOT/'eval/quality_selection_manifest.json',{'at':utcnow(),'files_before_acquisition':before,'selected_ids':[x['id'] for x in picked],
        'selector_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'known_issue_count':len(known),'queries':queries,
        'known_issue_numbers':sorted(known),'exclusions':exclusions,'selected_input_sha256':digest(picked),
        'protocol':'Initial 2025 exact session_state query returned 18 previously acquired reports and was abandoned before inference. Revised fixed 2023-2025 window with broader topic terms, descending creation/number, first 3 eligible per topic, before inference. All prior raw-acquired issue IDs excluded. Initial reports only. Explicit family references screened; unknown families/pretraining remain limitations.'})

if __name__=='__main__': main()
