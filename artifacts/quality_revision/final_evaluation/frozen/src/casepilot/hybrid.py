"""BM25 + learned dense vectors, RRF(60), MMR(.7), explicit version warnings."""
import collections, math, re
from .common import *
from .retrieval import Retriever, tokens, expand
from .embeddings import EmbeddingCache, FixtureEmbedder, cosine
from .model import MetisEmbedder
from .quality import technical_source

def embedding_text(row): return row['title']+'\n'+row['section']+'\n'+row['text']

def version_relation(row,version):
    if not version or not row.get('product_version'): return 'unknown'
    return 'exact' if row['product_version']==version else 'mismatch'

class HybridRetriever:
    def __init__(self,client,path=None,cache_path=None):
        self.client=client; self.path=Path(path or ROOT/'data/corpus_v2.json')
        require(self.path.exists(),'index_missing','ایندکس نسخهٔ دوم ساخته نشده است.')
        self.lexical=Retriever(self.path); self.chunks=self.lexical.chunks
        embedder=MetisEmbedder(client) if client.mode=='live' else FixtureEmbedder()
        self.cache=EmbeddingCache(cache_path or ROOT/'runtime'/('embeddings_live.sqlite3' if client.mode=='live' else 'embeddings_fixture.sqlite3'),embedder)
        self.vectors=None; self.last_trace={}

    def load_vectors(self):
        if self.vectors is None:
            self.vectors=self.cache.get_many([embedding_text(r) for r in self.chunks],allow_create=self.client.mode!='live')
        return self.vectors

    def search(self,query,k=8,method='final',version=None,components=None):
        options={'dense':True,'mmr':True,'quality':True}; options.update(components or {})
        if not options['dense']:
            rows=self.lexical.search(query,k=k,method='baseline',version=version)
            self.last_trace={'method':'bm25','components':options}; return rows
        vectors=self.load_vectors()
        qvector=self.cache.get_many([query])[0]; stats=self.cache.last_stats
        # BM25 ranks without the V1 documentation quota or title routing heuristic.
        bm=self.lexical.search(expand(query),k=100,method='baseline',version=version)
        eligible={i for i,r in enumerate(self.chunks) if not options['quality'] or technical_source(r)}
        dense=sorted(eligible,key=lambda i:(-cosine(qvector,vectors[i]),self.chunks[i]['id']))[:100]
        positions={r['id']:i for i,r in enumerate(self.chunks)}; fused={}
        for rank,row in enumerate((r for r in bm if positions[r['id']] in eligible),1): fused[positions[row['id']]]=1/(60+rank)
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
        rows=[dict(self.chunks[i],retrieval_score=round(fused[i],8),rank=r,version_relation=version_relation(self.chunks[i],version)) for r,i in enumerate(picked,1)]
        self.last_trace={'method':'bm25+dense+rrf+mmr','rrf_k':60,'mmr_lambda':.7,'components':options,
                         'embedding':stats,'candidates':[r['id'] for r in rows],
                         'quality_filter':options['quality'],'excluded_nontechnical_chunks':len(self.chunks)-len(eligible),
                         'version_warnings':[r['id'] for r in rows if r['version_relation']!='exact']}
        return rows
