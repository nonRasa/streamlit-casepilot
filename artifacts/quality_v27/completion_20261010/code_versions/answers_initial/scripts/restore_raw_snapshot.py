"""Reconstruct acquired issue records from URL-keyed raw cache; never refetch."""
import json, re
from urllib.parse import parse_qs, urlsplit
from collect_data import ROOT, TOPICS, issue_record, write

if __name__=='__main__':
    entries=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'data'/'raw').glob('*.json')]
    issues={}
    for topic in TOPICS:
        for entry in entries:
            query=parse_qs(urlsplit(entry['url']).query).get('q',[''])[0]
            if '/search/issues?' not in entry['url'] or f' {topic} in:' not in query: continue
            for row in entry['payload']['items']:
                if 'pull_request' not in row and row.get('body'): issues.setdefault(row['number'],issue_record(row,topic))
    comments={}
    for entry in entries:
        match=re.search(r'/issues/(\d+)/comments\?',entry['url'])
        if match:
            number=int(match.group(1)); page=int(parse_qs(urlsplit(entry['url']).query).get('page',['1'])[0])
            comments.setdefault(number,{})[page]=entry['payload']
    for number,row in issues.items():
        pages=comments.get(number,{})
        if pages:
            row['comments_data']=[{k:c.get(k) for k in ('id','body','created_at','updated_at','html_url','author_association')} for page in sorted(pages) for c in pages[page]]
            row['comments_complete']=1 in pages and len(pages[max(pages)])<100 and set(pages)==set(range(1,max(pages)+1))
        elif row['comments']==0: row['comments_complete']=True
    write(ROOT/'data'/'issues_snapshot.json',list(issues.values()))
    print('restored',len(issues),'complete comment threads',sum(x['comments_complete'] for x in issues.values()))
