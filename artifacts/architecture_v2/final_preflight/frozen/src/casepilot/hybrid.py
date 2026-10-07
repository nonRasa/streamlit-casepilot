"""BM25 + learned dense vectors, RRF(60), MMR(.7), explicit version warnings."""
import collections, math, re
from .common import *
from .retrieval import Retriever, tokens, expand
from .embeddings import EmbeddingCache, FixtureEmbedder, cosine
from .model import MetisEmbedder

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
        options={'dense':True,'mmr':True}; options.update(components or {})
        if not options['dense']:
            rows=self.lexical.search(query,k=k,method='baseline',version=version)
            self.last_trace={'method':'bm25','components':options}; return rows
        vectors=self.load_vectors()
        qvector=self.cache.get_many([query])[0]; stats=self.cache.last_stats
        # BM25 ranks without the V1 documentation quota or title routing heuristic.
        bm=self.lexical.search(expand(query),k=100,method='baseline',version=version)
        dense=sorted(range(len(vectors)),key=lambda i:(-cosine(qvector,vectors[i]),self.chunks[i]['id']))[:100]
        positions={r['id']:i for i,r in enumerate(self.chunks)}; fused={}
        for rank,row in enumerate(bm,1): fused[positions[row['id']]]=1/(60+rank)
        for rank,i in enumerate(dense,1): fused[i]=fused.get(i,0)+1/(60+rank)
        # A mismatch is a warning/penalty, never evidence that an API existed earlier.
        for i in fused:
            if version_relation(self.chunks[i],version)=='mismatch': fused[i]*=.65
        pool=sorted(fused,key=lambda i:(-fused[i],self.chunks[i]['id']))[:40]
        picked=[]; counts=collections.Counter(); max_score=max(fused.values(),default=1)
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
                         'version_warnings':[r['id'] for r in rows if r['version_relation']!='exact']}
        return rows
