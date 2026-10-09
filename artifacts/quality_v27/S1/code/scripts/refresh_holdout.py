"""Retire smoke-test cases. Select a fresh disjoint holdout after code freeze."""
import hashlib, random, re, sys
from collect_data import ROOT, fetch, write, COMMIT
sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import utcnow

if __name__=='__main__':
    import json
    issues=json.loads((ROOT/'data'/'issues_snapshot.json').read_text(encoding='utf-8'))
    prior=json.loads((ROOT/'eval'/'cases.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'data'/'snapshot_manifest.json').read_text(encoding='utf-8'))
    excluded=set(manifest['excluded_issue_families']); rng=random.Random(20261007); selected=[]
    for topic in ('session_state','widget','file_uploader','cache_data','multipage'):
        pool=[x for x in issues if x['topic']==topic and x['number'] not in excluded and 300<len(x['body'] or '')<12000
              and not any(re.search(r'(?:#|issues/)'+str(n)+r'\b',(x['body'] or '')+'\n'+'\n'.join(c['body'] or '' for c in x['comments_data'])) for n in excluded)]
        rng.shuffle(pool); selected.extend(pool[:3]); assert len(pool)>=3
    write(ROOT/'eval'/'pilot_cases.json',prior)
    write(ROOT/'eval'/'freeze_manifest.json',{'at':utcnow(),'reason':'Earlier test used for smoke inspection; retired before development changes. Fresh holdout selected after freezing retrieval/model/agent/grounding code.',
        'code_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'src').rglob('*.py'))},
        'new_test_issue_numbers':[x['number'] for x in selected], 'retired_test_issue_numbers':[x['issue_number'] for x in prior if x['split']=='test']})
    for row in selected:
        if row['comments_complete']: continue
        comments=[]; page=1
        while row['comments']:
            data=fetch(row['comments_url']+f'?per_page=100&page={page}')
            comments.extend({k:c.get(k) for k in ('id','body','created_at','updated_at','html_url','author_association')} for c in data)
            if len(data)<100: break
            page+=1
        row['comments_data']=comments; row['comments_complete']=True
        print('holdout comments',row['number'],len(comments),flush=True)
    by_id={x['number']:x for x in selected}
    write(ROOT/'data'/'issues_snapshot.json',[by_id.get(x['number'],x) for x in issues])
    write(ROOT/'eval'/'fresh_holdout_raw.json',selected)
    for repo,ref,prefix,paths in [('docs',COMMIT,'streamlit-docs',['LICENSE','NOTICES']),('streamlit','1.49.0','streamlit',['LICENSE'])]:
        for path in paths:
            text=fetch(f'https://raw.githubusercontent.com/streamlit/{repo}/{ref}/{path}')
            out=ROOT/'licenses'/(prefix+'-'+path+'.txt'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(text,encoding='utf-8')
    print('fresh holdout frozen',[(x['number'],x['topic'],x['title']) for x in selected],flush=True)
