"""Public read-only acquisition. Cached raw responses make collection resumable."""
from __future__ import annotations
import argparse, hashlib, json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '695e6ce2fb1b23afc6df66b40420ab0013ad72fd'
TOPICS = ['session_state', 'widget', 'file_uploader', 'cache_data', 'multipage']

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def fetch(url):
    cache = ROOT/'data'/'raw'/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))['payload']
    headers = {'User-Agent':'CasePilot-educational-snapshot', 'Accept':'application/vnd.github+json'}
    if os.getenv('GITHUB_TOKEN') and url.startswith('https://api.github.com/'):
        headers['Authorization'] = 'Bearer '+os.environ['GITHUB_TOKEN']
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=40) as response:
                content=response.read().decode('utf-8')
                payload=json.loads(content) if 'application/json' in response.headers.get('Content-Type','') else content
                write(cache, {'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(), 'payload':payload})
                return payload
        except HTTPError as exc:
            if exc.code in (403,429):
                raise RuntimeError('GitHub rate limit; cached responses retained. Resume later.') from None
            if exc.code not in (500,502,503,504) or attempt==2: raise
        except OSError:
            if attempt==2: raise
        time.sleep(2**attempt)

def issue_record(i, topic):
    fields=['number','html_url','title','body','created_at','updated_at','closed_at','state','state_reason','comments','comments_url']
    row={k:i.get(k) for k in fields}
    row.update(topic=topic, labels=[x['name'] for x in i.get('labels',[])], comments_data=[], comments_complete=False)
    return row

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--comments',type=int,default=42); args=parser.parse_args()
    issues={}
    for topic in TOPICS:
        query=f'repo:streamlit/streamlit is:issue {topic} in:title,body created:<2026-10-07'
        url='https://api.github.com/search/issues?'+urlencode({'q':query,'per_page':60,'sort':'created','order':'desc'})
        for i in fetch(url)['items']:
            if 'pull_request' not in i and i.get('body'): issues.setdefault(i['number'],issue_record(i,topic))
        print('collected',topic,len(issues),flush=True)
    # Select six per topic, balancing open/closed, avoiding obvious duplicates/empty reports.
    selected=[]
    for topic in TOPICS:
        candidates=[x for x in issues.values() if x['topic']==topic and len(x['body'])>150]
        closed=[x for x in candidates if x['state']=='closed']; opened=[x for x in candidates if x['state']=='open']
        pool=[]
        for index in range(max(len(closed),len(opened))):
            for rows in (closed,opened):
                if index<len(rows): pool.append(rows[index])
        selected.extend(pool[:6])
    assert len(selected)==30, 'Need thirty real issues; broaden search explicitly.'
    eval_numbers=[x['number'] for x in selected]
    others=[x for x in issues.values() if x['number'] not in eval_numbers]
    requested=selected+others[:max(0,args.comments-30)]
    for index, row in enumerate(requested):
        page=1; comments=[]
        while True:
            payload=fetch(row['comments_url']+f'?per_page=100&page={page}')
            comments.extend({k:x.get(k) for k in ('id','body','created_at','updated_at','html_url','author_association')} for x in payload)
            if len(payload)<100: break
            page+=1
        row['comments_data']=comments; row['comments_complete']=True
        print('comments',index+1,row['number'],len(comments),flush=True)
    write(ROOT/'data'/'issues_snapshot.json',list(issues.values()))
    write(ROOT/'data'/'eval_selection.json',eval_numbers)
    tree=fetch(f'https://api.github.com/repos/streamlit/docs/git/trees/{COMMIT}?recursive=1')
    paths=[x['path'] for x in tree['tree'] if x['type']=='blob']
    write(ROOT/'data'/'docs_paths.json',paths)
    print('snapshot',len(issues),'issues',len(paths),'doc paths',flush=True)

if __name__=='__main__': main()
