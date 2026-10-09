"""Source-preserving structural child search and bounded parent context.

Offsets refer to original Unicode text, including original newlines. Tables carry
an exact header span separately; code continuations never invent source lines.
"""
import bisect, re
from .common import digest, require
from .tokenization import count_tokens

CONFIG={'name':'structural_parent_child_v3','child_target_tokens':300,
        'parent_target_tokens':800,'encoding':'o200k_base','offset_unit':'unicode_character',
        'embedding_namespace':'casepilot-structural-v3'}

def structural_blocks(text,title):
    lines=text.splitlines(keepends=True); offsets=[0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    blocks=[]; stack=[]; i=0
    # Front matter is metadata, not an invented product version.
    if lines and lines[0].strip()=='---':
        stop=next((j for j in range(1,len(lines)) if lines[j].strip()=='---'),None)
        if stop is not None: i=stop+1
    while i<len(lines):
        if not lines[i].strip(): i+=1; continue
        start=i; heading=re.match(r'^(#{1,6})\s+(.+)',lines[i]); header=None
        fence=re.match(r'^\s*(`{3,}|~{3,})',lines[i])
        if heading:
            level=len(heading[1]); stack=[x for x in stack if x[0]<level]; stack.append((level,heading[2].strip()))
            kind='heading'; i+=1
        elif fence:
            kind='code'; marker=fence[1]; i+=1
            while i<len(lines):
                closed=re.match(r'^\s*'+re.escape(marker[0])+'{'+str(len(marker))+r',}\s*$',lines[i])
                i+=1
                if closed: break
        elif i+1<len(lines) and '|' in lines[i] and re.match(r'^\s*\|?[ :\-]+\|[| :\-]*$',lines[i+1].strip()):
            kind='table'; header=[offsets[i],offsets[i+2]]; i+=2
            while i<len(lines) and '|' in lines[i] and lines[i].strip(): i+=1
        else:
            kind='paragraph'; i+=1
            while i<len(lines) and lines[i].strip() and not re.match(r'^\s*(?:#{1,6}\s|`{3,}|~{3,})',lines[i]): i+=1
        blocks.append({'span':[offsets[start],offsets[i]],'section_path':[title]+[x[1] for x in stack],
                       'block_kind':kind,'header_span':header})
    return blocks,offsets

def split_block(block,text,target,encoding):
    start,end=block['span']
    if count_tokens(text[start:end],encoding=encoding)<=target: return [block]
    # Prefer function/class boundaries for code. Preserve decorators with their definition.
    if block['block_kind']=='code':
        cuts=[start]+[start+m.start() for m in re.finditer(r'(?m)^(?=(?:@|(?:async )?def |class ))',text[start:end])]+[end]
    else: cuts=[start,end]
    cuts=sorted(set(cuts)); result=[]
    for a,b in zip(cuts,cuts[1:]):
        if count_tokens(text[a:b],encoding=encoding)<=target:
            result.append(dict(block,span=[a,b])); continue
        # Rows/lines first; a long prose line uses sentence boundaries, then words.
        boundaries=[a]+[a+m.end() for m in re.finditer(r'\n',text[a:b])]+[b]
        if block['block_kind']=='paragraph':
            boundaries += [a+m.end() for m in re.finditer(r'(?<=[.!?؟؛])\s+|\s+',text[a:b])]
        boundaries=sorted(set(boundaries)); current=a
        for left,right in zip(boundaries,boundaries[1:]):
            if count_tokens(text[current:right],encoding=encoding)>target and left>current:
                result.append(dict(block,span=[current,left],continuation=current>start)); current=left
        if current<b: result.append(dict(block,span=[current,b],continuation=current>start))
    return result

def group_blocks(blocks,text,target,encoding):
    groups=[]; group=[]
    for block in blocks:
        if group and (block['section_path']!=group[-1]['section_path'] or
                      count_tokens(text[group[0]['span'][0]:block['span'][1]],encoding=encoding)>target):
            groups.append(group); group=[]
        group.append(block)
    if group: groups.append(group)
    return groups

def chunks(source,child_tokens=300,parent_tokens=800,encoding='o200k_base'):
    require(0<child_tokens<=parent_tokens,'invalid_chunk_config','بودجهٔ فرزند باید مثبت و حداکثر والد باشد.')
    text=source['text']; blocks,offsets=structural_blocks(text,source['title'])
    if source.get('kind')=='issue' and text.strip() and count_tokens(text,encoding=encoding)<=child_tokens:
        blocks=[{'span':[0,len(text)],'section_path':[source['title']],'block_kind':'short_report','header_span':None}]
    conf=dict(CONFIG,child_target_tokens=child_tokens,parent_target_tokens=parent_tokens,encoding=encoding)
    metadata={k:source.get(k) for k in ('kind','title','url','revision','product_version','issue_number',
                                      'available_at','published_at','created_at','updated_at','fetched_at')}
    source_hash=digest(text)
    def row(group,level):
        a,b=group[0]['span'][0],group[-1]['span'][1]; content=text[a:b]
        identifier=source['id']+':v3:'+level+':'+digest({'source_hash':source_hash,'revision':source.get('revision'),
                       'span':[a,b],'config':conf})[:20]
        headers=list(dict.fromkeys(tuple(x['header_span']) for x in group if x.get('header_span')))
        return dict(metadata,id=identifier,source_id=source['id'],text=content,source_span=[a,b],
                    source_sha256=source_hash,sha256=digest(content),lines=[bisect.bisect_right(offsets,a),bisect.bisect_left(offsets,b)],
                    section=' > '.join(group[-1]['section_path']),section_path=group[-1]['section_path'],
                    chunk_config=conf,token_count=count_tokens(content,encoding=encoding),
                    block_kinds=sorted({x['block_kind'] for x in group}),
                    context_needed=any(x.get('continuation') or x['block_kind'] in ('code','table') for x in group),
                    header_spans=[{'source_span':list(h),'text':text[h[0]:h[1]]} for h in headers],
                    oversized_block=count_tokens(content,encoding=encoding)>(parent_tokens if level=='parent' else child_tokens))
    parent_blocks=[part for b in blocks for part in split_block(b,text,parent_tokens,encoding)]
    parents=group_blocks(parent_blocks,text,parent_tokens,encoding); output=[]
    for group in parents:
        parent=row(group,'parent')
        parts=[part for b in group for part in split_block(b,text,child_tokens,encoding)]
        for child_group in group_blocks(parts,text,child_tokens,encoding):
            child=row(child_group,'child'); child.update(parent_id=parent['id'],parent=parent)
            output.append(child)
    return output
