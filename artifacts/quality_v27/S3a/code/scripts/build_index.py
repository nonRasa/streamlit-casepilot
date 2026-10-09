"""Rebuild V2 chunks from the same screened snapshot; optional bounded embedding prep."""
import argparse, hashlib, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.chunking import chunks, CONFIG
from casepilot.embeddings import EmbeddingCache, FixtureEmbedder
from casepilot.model import MetisClient, MetisEmbedder
from casepilot.hybrid import embedding_text
from prepare_data import clean

def screened_sources():
    old=read_json(ROOT/'data/corpus.json'); allowed={r['source_id'] for r in old}
    snapshot=read_json(ROOT/'data/snapshot_manifest.json'); excluded=set(snapshot['excluded_issue_families'])
    sources=[]
    for row in read_json(ROOT/'data/issues_snapshot.json'):
        sid='issue:'+str(row['number'])
        if sid not in allowed: continue
        text=clean(row['title'])+'\n\n'+clean(row['body'])+'\n\n'+'\n\n'.join(clean(c['body']) for c in row['comments_data'])
        sources.append({'id':sid,'kind':'issue','title':row['title'],'text':text,'url':row['html_url'],
                        'revision':row['updated_at'],'product_version':None,'issue_number':row['number']})
    import re
    for doc in read_json(ROOT/'data/docs_snapshot.json'):
        if doc['id'] not in allowed: continue
        parts=re.split(r'(\n\s*\n)',doc['text'])
        for i,part in enumerate(parts):
            if any(re.search(r'(?:#|issues/|pull/)'+str(n)+r'\b',part) for n in excluded) or (doc['kind']=='release' and re.search(r'(?i)altair\s*(?:version\s*)?5',part)):
                parts[i]='\n'*part.count('\n')
        sources.append(dict(doc,text=''.join(parts)))
    return sources,excluded

def build():
    sources,excluded=screened_sources()
    import re
    rows=[c for s in sources for c in chunks(s)]
    require(not {r.get('issue_number') for r in rows}&excluded,'heldout_leak','پروندهٔ ارزیابی وارد ایندکس شده است.')
    require(not any(re.search(r'(?:#|issues/|pull/)'+str(n)+r'\b',r['text']) for r in rows for n in excluded),'heldout_leak','ارجاع پروندهٔ ارزیابی در ایندکس وجود دارد.')
    write_json(ROOT/'data/corpus_v2.json',rows)
    write_json(ROOT/'data/index_v2_manifest.json',{'architecture':'v2','chunk_config':CONFIG,'sources':len(sources),'chunks':len(rows),
        'corpus_sha256':hashlib.sha256((ROOT/'data/corpus_v2.json').read_bytes()).hexdigest(),'parent_corpus_sha256':hashlib.sha256((ROOT/'data/corpus.json').read_bytes()).hexdigest(),
        'excluded_issue_families':sorted(excluded),'isolation':'Same screened source allowlist as V1; no labels, answers or future turns embedded.',
        'oversized_atomic_blocks':sum(r['oversized_block'] for r in rows),'embedding_status':'separately prepared in private runtime cache; no false live result'})
    return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument('--live',action='store_true'); p.add_argument('--additional-cap-usd',type=float,default=.10); args=p.parse_args()
    rows=build()
    if args.live:
        require(0<args.additional_cap_usd<=.25,'invalid_budget','سقف ساخت ایندکس باید حداکثر یک‌چهارم دلار باشد.')
        client=MetisClient(); before=client.budget.report()
        client.budget.cap=min(client.budget.cap,before['charged_or_reserved_usd']+args.additional_cap_usd)
        embedder=MetisEmbedder(client); cache=EmbeddingCache(ROOT/'runtime/embeddings_live.sqlite3',embedder)
    else:
        embedder=FixtureEmbedder(); cache=EmbeddingCache(ROOT/'runtime/embeddings_fixture.sqlite3',embedder)
    vectors=cache.get_many([embedding_text(r) for r in rows])
    result={'at':utcnow(),'mode':'live' if args.live else 'replay','identity':embedder.identity,'chunks':len(rows),'dimensions':len(vectors[0]),
            'cache':cache.last_stats,'cost':client.budget.report() if args.live else {'provider_requests':0,'cost_usd':0},
            'limitation':'Offline hashing fixtures test wiring, not semantic retrieval quality. Runtime vector cache is excluded from submission.'}
    write_json(ROOT/'artifacts/architecture_v2'/('embedding_build_live.json' if args.live else 'embedding_build_offline.json'),result)
    print(canonical({k:result[k] for k in ('mode','chunks','dimensions','identity')}))

if __name__=='__main__': main()
