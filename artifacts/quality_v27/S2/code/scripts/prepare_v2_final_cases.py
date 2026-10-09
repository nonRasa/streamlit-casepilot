"""Prospective V2 holdout: public initial reports only, no comments/final labels.

Select three unseen reports per topic by a fixed order before generating answers.
Neither the corpus nor the existing development/test sets are modified.
"""
import re, sys
from pathlib import Path
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json, write_json, digest, utcnow, require
from collect_data import fetch, TOPICS
from prepare_data import clean

def main():
    target=ROOT/'eval/v2_final_candidates.json'
    require(not target.exists(),'evaluation_exists','انتخاب قبلی بازنویسی نمی‌شود.')
    corpus=read_json(ROOT/'data/corpus_v2.json')
    known={r['number'] for r in read_json(ROOT/'data/issues_snapshot.json')}
    known.update(c['issue_number'] for c in read_json(ROOT/'eval/cases.json'))
    indexed={r['issue_number'] for r in corpus if r.get('issue_number')}
    text='\n'.join(r['text'] for r in corpus)
    picked=[]; exclusions=[]; queries=[]
    for topic in TOPICS:
        term={'file_uploader':'"file uploader"','cache_data':'cache','multipage':'pages'}.get(topic,topic)
        query=f'repo:streamlit/streamlit is:issue {term} in:title,body created:<2025-01-01'
        url='https://api.github.com/search/issues?'+urlencode({'q':query,'per_page':100,'sort':'created','order':'desc'})
        queries.append(url); payload=fetch(url); count=0
        for row in sorted(payload['items'],key=lambda r:(r['created_at'],r['number']),reverse=True):
            n=row['number']; body=row.get('body') or ''; reason=None
            refs={int(x) for x in re.findall(r'(?:issues/|#)(\d+)\b',body)}
            if n in known or n in {x['issue_number'] for x in picked}: reason='already acquired or selected'
            elif re.search(r'(?:issues/|pull/|#)'+str(n)+r'\b',text): reason='referenced by frozen retrieval corpus'
            elif refs & (known|indexed|{x['issue_number'] for x in picked}) or any(re.search(r'(?:issues/|#)'+str(n)+r'\b',x['initial_message']) for x in picked): reason='links to acquired issue family'
            elif not 500<=len(body)<=14000: reason='outside predeclared input size'
            elif re.search(r'(?i)duplicate of|follow.up to|\bduplicate\b',row['title']+'\n'+body): reason='possible duplicate/follow-up'
            if reason: exclusions.append({'number':n,'reason':reason}); continue
            picked.append({'id':f'GH{n}','issue_number':n,'topic':topic,'url':row['html_url'],
                'created_at':row['created_at'],'initial_message':clean(row['title'])+'\n\n'+clean(body),
                'initial_facts':{},'initial_checks':[],'split':'test_fresh',
                'family_id':'v2-unseen-'+str(n),'annotation_pending':True})
            count+=1
            if count==3: break
        require(count==3,'insufficient_holdout','برای هر موضوع سه پروندهٔ تازه لازم است.')
        print('selected',topic,count,flush=True)
    write_json(target,picked)
    write_json(ROOT/'eval/v2_selection_manifest.json',{'at':utcnow(),'queries':queries,'selection_order':'created_at descending, issue_number descending',
        'per_topic':3,'cases':len(picked),'selected_ids':[r['id'] for r in picked], 'exclusions':exclusions,
        'corpus_sha256':digest(corpus),'input_sha256':digest(picked),
        'policy':'Initial report only. No comments, resolution, state or labels used. Reports already acquired/indexed or referenced by corpus excluded. Explicit issue links screened. Unknown duplicates and model pretraining remain limitations. Rubric annotated before inference.'})

if __name__=='__main__': main()
