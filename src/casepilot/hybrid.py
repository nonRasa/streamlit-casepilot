"""BM25 + learned dense vectors, RRF(60), MMR(.7), explicit version warnings."""
import collections, math, re
from .common import *
from .retrieval import Retriever, tokens, expand
from .embeddings import EmbeddingCache, FixtureEmbedder, cosine
from .model import MetisEmbedder
from .quality import technical_source
from .evidence import relation, annotate, eligible

def embedding_text(row): return row['title']+'\n'+row['section']+'\n'+row['text']

def version_relation(row,version):
    return relation(row,version)

def split_lexical_queries(query):
    """Separate exact API/error names from the report's symptom language."""
    lines=query.splitlines(); title=lines[0] if lines else query
    names=' '.join(line for line in lines[1:] if line.startswith(('APIs:','Errors:')))
    symptoms=' '.join(line for line in lines[1:] if not line.startswith(('APIs:','Errors:')))
    return (title+' '+names).strip()[:1200],(title+' '+symptoms).strip()[:1600]

def split_lexical_search(lexical,query,k=100):
    """RRF of two lexical views; no model, labels, or embedding calls."""
    views=split_lexical_queries(query); scores={}; rows={}
    for view in dict.fromkeys(views):
        for rank,row in enumerate(lexical.search(view,k=k,method='baseline'),1):
            scores[row['id']]=scores.get(row['id'],0)+1/(60+rank)
            rows[row['id']]=row
    return [dict(rows[key],retrieval_score=round(scores[key],8)) for key in
            sorted(scores,key=lambda key:(-scores[key],key))[:k]]


def direct_official_matches(rows,query,limit=2):
    """Reserve directly named official passages without using evaluation labels."""
    title=query.splitlines()[0].casefold()
    title_words=' '.join(re.findall(r'[a-z0-9]+',title))
    # Code examples often mention incidental APIs. Only names in the report's
    # problem title qualify for a reserved documentation slot.
    apis={name.casefold() for name in re.findall(r'\bst\.([A-Za-z_]\w*)',query)
          if re.search(r'(?<![a-z0-9_])'+re.escape(name.casefold())+r'(?![a-z0-9_])',title)}
    matches=[]
    for position,row in enumerate(rows):
        if row.get('kind')!='docs': continue
        heading=(row.get('title','')+' '+row.get('section','')).casefold()
        source=row.get('source_id','').casefold()
        api_hit=any(re.search(r'(?<![a-z0-9_])'+re.escape(api)+r'(?![a-z0-9_])',heading) or source=='api:'+api for api in apis)
        slug=source.split(':',1)[-1]
        slug_words=' '.join(re.findall(r'[a-z0-9]+',slug))
        named=bool(len(slug_words)>=8 and re.search(r'(?<![a-z0-9])'+re.escape(slug_words)+r'(?![a-z0-9])',title_words))
        if not api_hit and not named: continue
        matches.append((not api_hit,position,row))
    matches.sort(key=lambda item:item[:2])
    picked=[]; seen=set()
    for _,_,row in matches:
        if row['source_id'] in seen: continue
        picked.append(row); seen.add(row['source_id'])
        if len(picked)>=limit: break
    return picked

class HybridRetriever:
    def __init__(self,client,path=None,cache_path=None):
        self.client=client; self.path=Path(path or ROOT/'data/corpus_v2.json')
        require(self.path.exists(),'index_missing','ایندکس نسخهٔ دوم ساخته نشده است.')
        self.lexical=Retriever(self.path); self.chunks=self.lexical.chunks
        self.cache_path=cache_path or ROOT/'runtime'/('embeddings_live.sqlite3' if client.mode=='live' else 'embeddings_fixture.sqlite3')
        self.cache=None
        self.vectors=None; self.last_trace={}

    def load_vectors(self):
        if self.vectors is None:
            if self.cache is None:
                embedder=MetisEmbedder(self.client) if self.client.mode=='live' else FixtureEmbedder()
                self.cache=EmbeddingCache(self.cache_path,embedder)
            self.vectors=self.cache.get_many([embedding_text(r) for r in self.chunks],allow_create=self.client.mode!='live')
        return self.vectors

    def search(self,query,k=8,method='final',version=None,components=None,as_of=None):
        options={'dense':True,'mmr':True,'quality':True}; options.update(components or {})
        if not options['dense']:
            rows=(split_lexical_search(self.lexical,query) if options.get('split_query') else
                  self.lexical.search(query,k=100,method='baseline',version=version))
            rows=[r for r in rows if eligible(r,as_of) and (not options['quality'] or technical_source(r))]
            if options['quality']:
                reserved=direct_official_matches(rows,query,min(2,k))
                chosen={r['id'] for r in reserved}
                counts=collections.Counter(r['source_id'] for r in reserved)
                for row in rows:
                    if len(reserved)>=k: break
                    if row['id'] in chosen or counts[row['source_id']]>=2: continue
                    reserved.append(row); chosen.add(row['id']); counts[row['source_id']]+=1
                rows=reserved
            rows=[annotate(r,version,as_of) for r in rows[:k]]
            self.last_trace={'method':'bm25-split-rrf' if options.get('split_query') else 'bm25','components':options,'as_of':as_of,'temporal_policy':'exclude_future_and_unknown' if as_of else 'current_snapshot'}; return rows
        vectors=self.load_vectors()
        qvector=self.cache.get_many([query])[0]; stats=self.cache.last_stats
        # BM25 ranks without the V1 documentation quota or title routing heuristic.
        bm=self.lexical.search(expand(query),k=100,method='baseline',version=version)
        allowed={i for i,r in enumerate(self.chunks) if eligible(r,as_of) and (not options['quality'] or technical_source(r))}
        dense=sorted(allowed,key=lambda i:(-cosine(qvector,vectors[i]),self.chunks[i]['id']))[:100]
        positions={r['id']:i for i,r in enumerate(self.chunks)}; fused={}
        for rank,row in enumerate((r for r in bm if positions[r['id']] in allowed),1): fused[positions[row['id']]]=1/(60+rank)
        for rank,i in enumerate(dense,1): fused[i]=fused.get(i,0)+1/(60+rank)
        # A mismatch is a warning/penalty, never evidence that an API existed earlier.
        for i in fused:
            if version_relation(self.chunks[i],version)=='mismatch': fused[i]*=.65
            if options['quality'] and self.chunks[i]['kind']=='docs': fused[i]*=1.18
        pool=sorted(fused,key=lambda i:(-fused[i],self.chunks[i]['id']))[:40]
        picked=[]; counts=collections.Counter(); max_score=max(fused.values(),default=1)
        # Official documentation is prioritized, not treated as automatically
        # relevant: the model reranker may omit it, and judge must prove support.
        if options['quality']:
            official=[i for i in pool if self.chunks[i]['kind']=='docs']
            for i in official:
                if len(picked)>=min(3,k) or counts[self.chunks[i]['source_id']]: continue
                picked.append(i); counts[self.chunks[i]['source_id']]+=1; pool.remove(i)
        while pool and len(picked)<k:
            allowed=[i for i in pool if counts[self.chunks[i]['source_id']]<2]
            if not allowed: break
            def score(i):
                similarity=max((cosine(vectors[i],vectors[j]) for j in picked),default=0)
                return .7*fused[i]/max_score-.3*similarity if options['mmr'] else fused[i]
            best=min(allowed,key=lambda i:(-score(i),self.chunks[i]['id']))
            picked.append(best); counts[self.chunks[best]['source_id']]+=1; pool.remove(best)
        rows=[dict(annotate(self.chunks[i],version,as_of),retrieval_score=round(fused[i],8),rank=r) for r,i in enumerate(picked,1)]
        self.last_trace={'method':'bm25+dense+rrf+mmr','rrf_k':60,'mmr_lambda':.7,'components':options,
                         'embedding':stats,'candidates':[r['id'] for r in rows],
                         'quality_filter':options['quality'],'excluded_chunks':len(self.chunks)-len(allowed),
                         'as_of':as_of,'temporal_policy':'exclude_future_and_unknown' if as_of else 'current_snapshot',
                         'version_warnings':[r['id'] for r in rows if r['version_relation']!='exact']}
        return rows

