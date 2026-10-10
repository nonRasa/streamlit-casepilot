"""Structure-aware chunks with contiguous source spans and block-level overlap.

Fences/tables are atomic. Oversized blocks remain intact and are explicitly marked;
the context packer can exclude them rather than silently truncate code.
Token counts are conservative UTF-8 byte estimates, not provider tokenization.
"""
import hashlib, re
from .common import digest

CONFIG={'name':'section_blocks_v2','target_tokens':1600,'overlap_tokens':256,'token_estimator':'utf8_bytes_upper_bound'}

def token_estimate(text): return len(text.encode('utf-8'))

def chunks(source, target=1600, overlap=256):
    lines=source['text'].replace('\r\n','\n').splitlines()
    blocks=[]; section=source['title']; i=0
    if lines and lines[0].strip()=='---':
        end=next((j for j in range(1,len(lines)) if lines[j].strip()=='---'),None)
        if end is not None: i=end+1
    while i<len(lines):
        if not lines[i].strip(): i+=1; continue
        start=i; line=lines[i]; heading=re.match(r'^#{1,6}\s+(.+)',line)
        if heading: section=heading.group(1).strip(); i+=1
        elif re.match(r'^\s*(`{3,}|~{3,})',line):
            marker=re.match(r'^\s*(`{3,}|~{3,})',line).group(1); i+=1
            while i<len(lines):
                closed=bool(re.match(r'^\s*'+re.escape(marker[0])+'{'+str(len(marker))+r',}\s*$',lines[i])); i+=1
                if closed: break
        else:
            i+=1
            while i<len(lines) and lines[i].strip() and not re.match(r'^\s*(?:#{1,6}\s|`{3,}|~{3,})',lines[i]): i+=1
        blocks.append((start,i,section))
    groups=[]; current=[]
    for block in blocks:
        a,b,heading=block
        if current and (heading!=current[-1][2] or token_estimate('\n'.join(lines[current[0][0]:b]))>target):
            groups.append(current)
            carry=[]
            if heading==current[-1][2]:
                for old in reversed(current):
                    if token_estimate('\n'.join(lines[old[0]:current[-1][1]]))>overlap: break
                    carry.insert(0,old)
            current=carry
        current.append(block)
    if current: groups.append(current)
    result=[]
    for group in groups:
        a,b=group[0][0],group[-1][1]; text='\n'.join(lines[a:b]); estimate=token_estimate(text)
        if len(text.strip())<20: continue
        conf=dict(CONFIG,target_tokens=target,overlap_tokens=overlap)
        meta={k:source.get(k) for k in ('kind','title','url','revision','product_version','issue_number')}
        meta.update(id=source['id']+':v2:'+digest({'span':[a+1,b],'text':text,'config':conf})[:16],source_id=source['id'],
                    section=group[-1][2],text=text,lines=[a+1,b],sha256=hashlib.sha256(text.encode()).hexdigest(),
                    chunk_config=conf,estimated_tokens=estimate,oversized_block=estimate>target)
        result.append(meta)
    return result
