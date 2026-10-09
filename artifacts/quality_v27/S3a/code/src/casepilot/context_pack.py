"""Token-budgeted evidence packets; explicit omissions and exact source spans."""
from .common import canonical
from .tokenization import count_tokens

FIELDS=('id','source_id','kind','title','section','text','revision','product_version',
        'version_relation','temporal_status','source_authority','url','lines','source_span',
        'source_sha256','header_spans','parent_id','selected_child_ids')

def public_row(row):
    return {k:row.get(k) for k in FIELDS if k in row}

def pack_evidence(rows,max_tokens=3000,k=5,expand_parent=False,encoding='o200k_base',max_expansion_ratio=3):
    selected=[]; trace=[]; seen=set(); parents={}
    def cost(items): return count_tokens(canonical([public_row(r) for r in items]),encoding=encoding)
    for row in rows:
        key=(row['source_id'],row.get('revision'),tuple(row.get('source_span',row.get('lines',[]))),row['sha256'])
        if key in seen: trace.append({'id':row['id'],'status':'omitted','reason':'duplicate_span'}); continue
        pid=row.get('parent_id'); parent=row.get('parent'); chosen=dict(row); reason='child_only'
        if expand_parent and pid in parents:
            existing=selected[parents[pid]]
            # Include this child's provenance without charging duplicate parent text.
            revised=dict(existing,selected_child_ids=existing['selected_child_ids']+[row['id']])
            trial=list(selected); trial[parents[pid]]=revised
            if cost(trial)<=max_tokens:
                selected=trial; trace.append({'id':row['id'],'status':'merged','parent_id':pid}); seen.add(key); continue
            trace.append({'id':row['id'],'status':'omitted','reason':'context_budget_metadata'}); continue
        if len(selected)>=k:
            trace.append({'id':row['id'],'status':'omitted','reason':'item_limit'}); continue
        if expand_parent and parent:
            ratio=parent['token_count']/max(1,row['token_count'])
            # Expansion is local to the same structural section and bounded in size.
            if ratio<=max_expansion_ratio and parent['source_span']!=row['source_span']:
                expanded=dict(parent,selected_child_ids=[row['id']],parent_id=pid,
                              **{x:row[x] for x in ('version_relation','temporal_status','source_authority') if x in row})
                if cost(selected+[expanded])<=max_tokens: chosen=expanded; reason='bounded_parent'
                else: reason='parent_budget_exceeded_use_child'
            elif ratio>max_expansion_ratio: reason='parent_relevance_window_exceeded_use_child'
        if cost(selected+[chosen])>max_tokens:
            trace.append({'id':row['id'],'status':'omitted','reason':'context_budget','tokens':cost([chosen])}); continue
        if reason=='bounded_parent': parents[pid]=len(selected)
        selected.append(chosen); seen.add(key)
        trace.append({'id':row['id'],'status':'included','reason':reason,'context_id':chosen['id']})
    return selected,{'encoding':encoding,'budget_tokens':max_tokens,'used_tokens':cost(selected),
                     'expand_parent':expand_parent,'items':trace}
