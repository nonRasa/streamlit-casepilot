"""Exclude a discovered related family before running the final holdout."""
import json
from collect_data import ROOT, fetch, write
if __name__=='__main__':
    issues=json.loads((ROOT/'data'/'issues_snapshot.json').read_text(encoding='utf-8')); by_id={x['number']:x for x in issues}
    row=by_id[6237]; comments=[]; page=1
    while row['comments']:
        payload=fetch(row['comments_url']+f'?per_page=100&page={page}')
        comments.extend({k:x.get(k) for k in ('id','body','created_at','updated_at','html_url','author_association')} for x in payload)
        if len(payload)<100: break
        page+=1
    row['comments_data']=comments; row['comments_complete']=True
    write(ROOT/'data'/'issues_snapshot.json',issues)
    freeze=json.loads((ROOT/'eval'/'freeze_manifest.json').read_text(encoding='utf-8'))
    freeze['new_test_issue_numbers']=[6237 if n==7338 else n for n in freeze['new_test_issue_numbers']]
    freeze['family_replacement']={'excluded':7338,'replacement':6237,'reason':'Initial report and comments reveal frontend/backend widget-state family related to development cases; replaced before final evaluation, not on performance.'}
    write(ROOT/'eval'/'freeze_manifest.json',freeze)
    print(row['number'],row['title'],'\n',row['body'],'\nCOMMENTS\n','\n'.join(c['body'] for c in comments))
