"""Select initial reports once; never request comments, state, or labels as inputs."""
import hashlib, json, re, sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import write_json,utcnow,digest
from prepare_data import clean

DEST=ROOT/'artifacts/quality_v22/holdout'
TOPICS={'session_state':'"session state"','widget':'input','file_uploader':'upload','cache_data':'cache','multipage':'navigation'}
def refs(text): return {int(n) for n in re.findall(r'(?:issues/|pull/|#)(\d+)\b',text)}
def collect_numbers(value):
    result=set()
    if isinstance(value,list):
        for v in value: result.update(collect_numbers(v))
    if isinstance(value,dict):
        for k,v in value.items():
            if k in ('issue_number','number') and type(v) is int: result.add(v)
            elif k in ('id','case_id') and isinstance(v,str) and re.fullmatch(r'GH\d+',v): result.add(int(v[2:]))
            if isinstance(v,(list,dict)): result.update(collect_numbers(v))
    return result

def main():
    if DEST.exists(): raise SystemExit('انتخاب موجود بازنویسی نمی‌شود.')
    known=set(); old_text=[]
    for folder in ('eval','data/raw'):
        for p in (ROOT/folder).glob('*.json'):
            try: d=json.loads(p.read_text(encoding='utf-8')); known.update(collect_numbers(d))
            except (ValueError,UnicodeError): pass
    known.update(r['number'] for r in json.loads((ROOT/'data/issues_snapshot.json').read_text(encoding='utf-8')))
    corpus=json.loads((ROOT/'data/corpus_v2.json').read_text(encoding='utf-8'))
    corpus_text='\n'.join(r['text'] for r in corpus)
    known.update(refs(corpus_text))
    for p in (ROOT/'artifacts').rglob('*answers.json'):
        if 'quality_v22' in p.parts: continue
        old_text.append(p.read_text(encoding='utf-8'))
    previous_output_text='\n'.join(old_text)
    known.update(refs(previous_output_text))
    for p in (ROOT/'eval').glob('*cases.json'):
        try:
            d=json.loads(p.read_text(encoding='utf-8'))
            if isinstance(d,list): old_text += [r.get('initial_message','') for r in d if isinstance(r,dict)]
        except ValueError: pass
    cache=ROOT/'runtime/quality_v22/acquisition'; cache.mkdir(parents=True,exist_ok=True)
    picked=[]; excluded=[]; queries=[]
    def terms(text): return set(re.findall(r'[a-z_]{3,}',re.sub(r'https?://\S+','',text.casefold())))
    for topic,term in TOPICS.items():
        q=f'repo:streamlit/streamlit is:issue {term} in:title,body created:2024-01-01..2026-10-08'
        url='https://api.github.com/search/issues?'+urlencode({'q':q,'per_page':100,'sort':'created','order':'desc'})
        queries.append(url); raw=cache/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if raw.exists(): payload=json.loads(raw.read_text(encoding='utf-8'))
        else:
            # Public GET, no credentials and no automatic retries.
            with urlopen(Request(url,headers={'User-Agent':'CasePilot-quality-v22','Accept':'application/vnd.github+json'}),timeout=30) as response:
                payload=json.load(response)
            raw.write_text(json.dumps(payload),encoding='utf-8')
        count=0
        for r in sorted(payload.get('items',[]),key=lambda r:(r['created_at'],r['number']),reverse=True):
            n=r['number']; body=r.get('body') or ''; text=r['title']+'\n\n'+body; why=None
            if n in known or n in {c['issue_number'] for c in picked}: why='known_or_selected'
            elif refs(text)&known: why='direct_known_family'
            elif refs(text)&{c['issue_number'] for c in picked}: why='direct_selected_family'
            elif any(n in refs(c['initial_message']) for c in picked): why='reverse_selected_family'
            elif not 500<=len(body)<=12000: why='text_size'
            elif re.search(r'(?i)duplicate|follow.up to',text): why='possible_duplicate'
            elif any(len(terms(text)&terms(t))/max(1,len(terms(text)|terms(t)))>.62 for t in old_text+[c['initial_message'] for c in picked]): why='similar_family'
            if why: excluded.append({'number':n,'reason':why}); continue
            picked.append({'id':f'GH{n}','issue_number':n,'topic':topic,'url':r['html_url'],'created_at':r['created_at'],
                'initial_message':clean(r['title'])+'\n\n'+clean(body),'initial_facts':{},'initial_checks':[],
                'family_id':'v22-unseen-'+str(n),'split':'unseen_replay_only'})
            count+=1
            if count==3: break
        if count!=3: break
    write_json(DEST/'cases.json',picked)
    write_json(DEST/'selection.json',{'at':utcnow(),'complete':len(picked)==15,'selected_ids':[c['id'] for c in picked],
        'known_count':len(known),'known_numbers':sorted(known),'excluded':excluded,'queries':queries,
        'inputs_sha256':digest(picked),'corpus_sha256':hashlib.sha256((ROOT/'data/corpus_v2.json').read_bytes()).hexdigest(),
        'selection_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'protocol_sha256':hashlib.sha256((ROOT/'docs/QUALITY_V22_PROTOCOL_FA.md').read_bytes()).hexdigest(),
        'comments_acquired':False,'final_labels_used':False,'paid_requests':0,
        'limitation':'Explicit links, duplicate markers and conservative token Jaccard screen; latent semantic families and pretraining cannot be ruled out.'})
    print(json.dumps({'selected':len(picked),'complete':len(picked)==15,'excluded':len(excluded)}))
if __name__=='__main__': main()
