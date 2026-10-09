"""Offline-only prototype. Never reads credentials or creates paid embeddings."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from build_index import screened_sources
from casepilot.parent_child import chunks, CONFIG
from casepilot.common import digest, write_json
from casepilot.tokenization import count_tokens
from casepilot.hybrid import embedding_text

def build(child=300,parent=800,output=None):
    output=Path(output or ROOT/'data/corpus_v3.json')
    sources,excluded=screened_sources()
    rows=[r for source in sources for r in chunks(source,child,parent)]
    by_id={s['id']:s for s in sources}
    for r in rows:
        a,b=r['source_span']; assert by_id[r['source_id']]['text'][a:b]==r['text']
        p=r['parent']; a,b=p['source_span']; assert by_id[r['source_id']]['text'][a:b]==p['text']
        assert r['parent_id']==p['id'] and p['source_span'][0]<=r['source_span'][0]<r['source_span'][1]<=p['source_span'][1]
    write_json(output,rows)
    manifest={'format':'structural_parent_child_v3','chunk_config':dict(CONFIG,child_target_tokens=child,parent_target_tokens=parent),
        'sources':len(sources),'children':len(rows),'parents':len({r['parent_id'] for r in rows}),
        'source_snapshot_hash':digest(sources),'corpus_hash':digest(rows),
        'source_revisions':{s['id']:s.get('revision') for s in sources},
        'source_version_unknown':sum(s.get('product_version') is None for s in sources),
        'embedding_input_tokens_cl100k_base':sum(count_tokens(embedding_text(r),encoding='cl100k_base') for r in rows),
        'oversize_children':sum(r['oversized_block'] for r in rows),'excluded_issue_families':sorted(excluded),
        'provider_requests':0,'embedding_status':'not_built; new authorization required',
        'provenance':'Exact screened snapshot text; product_version copied only from existing explicit metadata.'}
    write_json(output.with_suffix('.manifest.json'),manifest)
    # Source text is necessary to verify exact citation offsets after restart.
    write_json(output.with_suffix('.sources.json'),sources)
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('source_revisions','excluded_issue_families')},ensure_ascii=True))
    return rows,manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--child-tokens',type=int,default=300)
    p.add_argument('--parent-tokens',type=int,default=800); p.add_argument('--output',type=Path)
    a=p.parse_args(); build(a.child_tokens,a.parent_tokens,a.output)
