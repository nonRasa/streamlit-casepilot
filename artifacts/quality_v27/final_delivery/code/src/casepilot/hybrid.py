"""BM25 + learned dense vectors, RRF(60), MMR(.7), explicit version warnings."""
import collections, math, re
from .common import *
from .retrieval import Retriever, tokens, expand
from .embeddings import EmbeddingCache, FixtureEmbedder, cosine
from .model import MetisEmbedder
from .quality import technical_source
from .evidence import relation, annotate, eligible

def embedding_text(row):
    headers=''.join(h['text'] for h in row.get('header_spans',[]) if h['text'] not in row['text'])
    return row['title']+'\n'+row['section']+'\n'+headers+row['text']

def version_relation(row,version):
    return relation(row,version)

class HybridRetriever:
    def __init__(self,client,path=None,cache_path=None):
        import os
        index_format=os.getenv('CASEPILOT_INDEX_FORMAT','v2')
        require(index_format in ('v2','v3'),'invalid_index_format','قالب ایندکس باید v2 یا v3 باشد.')
        self.client=client; self.path=Path(path or ROOT/('data/corpus_'+index_format+'.json'))
        require(self.path.exists(),'index_missing','ایندکس نسخهٔ دوم ساخته نشده است.')
        self.lexical=Retriever(self.path); self.chunks=self.lexical.chunks
        embedder=MetisEmbedder(client) if client.mode=='live' else FixtureEmbedder()
        configs={digest(r.get('chunk_config',{})) for r in self.chunks}
        self.index_namespace=digest({'configs':sorted(configs),'format':'child-context-v3'}) if any('parent_id' in r for r in self.chunks) else None
        self.cache=EmbeddingCache(cache_path or ROOT/'runtime'/('embeddings_live.sqlite3' if client.mode=='live' else 'embeddings_fixture.sqlite3'),embedder,namespace=self.index_namespace)
        self.vectors=None; self.last_trace={}

    def load_vectors(self):
        if self.vectors is None:
            self.vectors=self.cache.get_many([embedding_text(r) for r in self.chunks],allow_create=self.client.mode!='live')
        return self.vectors

    def search(self,query,k=8,method='final',version=None,components=None,as_of=None):
        options={'dense':True,'mmr':True,'quality':True}; options.update(components or {})
        if not options['dense']:
            rows=self.lexical.search(query,k=100,method='baseline',version=version)
            rows=[annotate(r,version,as_of) for r in rows if eligible(r,as_of) and (not options['quality'] or technical_source(r))][:k]
            self.last_trace={'method':'bm25','components':options,'as_of':as_of,'temporal_policy':'exclude_future_and_unknown' if as_of else 'current_snapshot'}; return rows
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
        lexical_matches={r['id'] for r in bm}
        for i in fused:
            if version_relation(self.chunks[i],version)=='mismatch': fused[i]*=.65
            if (options['quality'] and self.chunks[i]['kind']=='docs'
                    and self.chunks[i]['id'] in lexical_matches
                    and version_relation(self.chunks[i],version)!='mismatch'): fused[i]*=1.08
        pool=sorted(fused,key=lambda i:(-fused[i],self.chunks[i]['id']))[:40]
        picked=[]; counts=collections.Counter(); max_score=max(fused.values(),default=1)
        eligible_count=len(allowed)
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
                         'quality_filter':options['quality'],'excluded_chunks':len(self.chunks)-eligible_count,
                         'official_preference':'lexical_match_and_no_known_mismatch; no quota',
                         'as_of':as_of,'temporal_policy':'exclude_future_and_unknown' if as_of else 'current_snapshot',
                         'version_warnings':[r['id'] for r in rows if r['version_relation']!='exact']}
        return rows
