"""Deterministic lexical baseline and hybrid lexical/character retrieval. No API."""
from __future__ import annotations
import collections, math, re
from .common import *

EXPANSIONS={
 'نشست':'session session_state websocket', 'حافظه':'memory cache session_state',
 'ویجت':'widget key identity', 'بارگذاری':'loading deployment', 'سرور':'server deployment websocket',
 'آپلود':'upload file_uploader', 'فایل':'file upload', 'کش':'cache caching cache_data',
 'صفحه':'page navigation multipage', 'دکمه':'button callback', 'نسخه':'version release',
 'قطع':'disconnect websocket', 'انتخاب':'selectbox selection', 'بازنشانی':'reset state',
 'session_state':'session state widget lifecycle', 'file_uploader':'upload file memory server',
 'cache_data':'cache caching pickle serialize hash', 'multipage':'page navigation widget',
 'websocket':'session reconnect', 'oom':'memory killed', 'qualname':'cache function hash',
}
STOP={'the','and','a','to','of','in','is','it','on','with','for','that','this','i','st','streamlit','have','my','from','be','as','not','are','was','an','or','but','can','if','when','s','t','at','by','no','me','you','your','we','x','true','false','checklist','response','issue','expected','current','behavior'}

def tokens(text):
    text=text.casefold()
    return [x for x in re.findall(r'[\w]+(?:[._][\w]+)*',text) if x not in STOP and len(x)>1]

def expand(text):
    additions=[value for key,value in EXPANSIONS.items() if key in text.casefold()]
    return text+' '+' '.join(additions)

def grams(text):
    text=' '.join(tokens(text))[:3000]
    return collections.Counter(text[i:i+3] for i in range(len(text)-2))

# Domain routing is based only on the visible report title, never case IDs or labels.
ROUTES=[
 (r'file.?upload|upload.*(?:ram|memory|file)', {'api:file_uploader','docs:where-file-uploader-store-when-deleted'}),
 (r'cache[_ .-]?data|cache[_ .-]?resource|serializ|duckdb|qualname', {'docs:caching','api:cache_data','api:cache_resource'}),
 (r'session[_ -]?state|widget|selectbox|pill', {'docs:widget-behavior','docs:session_state','docs:widget-updating-session-state'}),
 (r'multipage|navigation|sidebar', {'docs:page-and-navigation','docs:widgets','api:navigation','docs:dynamic-navigation'}),
 (r'component|trigger.?value|setstatevalue', {'docs:state-and-triggers','docs:architecture'}),
 (r'apptest|app.?test', {'docs:get-started','docs:widgets'}),
 (r'query.*param', {'docs:query_params','docs:widget-behavior'}),
 (r'static|image.*html|img src', {'docs:static-file-serving'}),
 (r'fragment|dialog', {'docs:fragments'}),
 (r'theme|dataframe.*control', {'docs:theming','docs:context','docs:dataframes'}),
]

class Retriever:
    def __init__(self,path=None):
        self.chunks=read_json(path or ROOT/'data'/'corpus.json')
        self.by_id={x['id']:x for x in self.chunks}
        self.tf=[collections.Counter(tokens(x['title']+' '+x['section']+' '+x['text'])) for x in self.chunks]
        self.lengths=[sum(t.values()) for t in self.tf]; self.avg=sum(self.lengths)/max(1,len(self.tf))
        df=collections.Counter(term for row in self.tf for term in row)
        n=len(self.chunks); self.idf={t:math.log(1+(n-c+.5)/(c+.5)) for t,c in df.items()}
        self.cg=[grams(x['title']+' '+x['section']+' '+x['text']) for x in self.chunks]
        self.norm=[math.sqrt(sum(v*v for v in g.values())) or 1 for g in self.cg]

    def search(self,query,k=5,method='final',version=None):
        require(method in ('baseline','final'),'invalid_method','روش بازیابی معتبر نیست.')
        query=bounded_text(query,'query',60000)
        q=tokens(expand(query) if method=='final' else query); q=list(dict.fromkeys(q))[:300]
        scores=[]
        for idx,row in enumerate(self.tf):
            score=0
            for term in q:
                f=row.get(term,0)
                if f: score+=self.idf.get(term,0)*f*2.2/(f+1.2*(.25+.75*self.lengths[idx]/self.avg))
            scores.append(score)
        bm=sorted(range(len(scores)),key=lambda i:(-scores[i],self.chunks[i]['id']))
        if method=='baseline': chosen=[i for i in bm if scores[i]>0][:k]
        else:
            qg=grams(expand(query)); qnorm=math.sqrt(sum(v*v for v in qg.values())) or 1
            cos=[sum(v*g.get(t,0) for t,v in qg.items())/(qnorm*self.norm[i]) for i,g in enumerate(self.cg)]
            cr=sorted(range(len(cos)),key=lambda i:(-cos[i],self.chunks[i]['id']))
            rank={i:1/(60+r) for r,i in enumerate(bm[:100],1) if scores[i]>0}
            for r,i in enumerate(cr[:100],1):
                if cos[i]>.025: rank[i]=rank.get(i,0)+1/(60+r)
            for i in rank:
                if self.chunks[i]['kind']=='docs': rank[i]*=1.12
                pv=self.chunks[i].get('product_version')
                if version and pv and pv!=version: rank[i]*=.8
            title=query.splitlines()[0].casefold()
            routed=set().union(*(sources for pattern,sources in ROUTES if re.search(pattern,title)))
            for i in rank:
                if self.chunks[i]['source_id'] in routed: rank[i]*=1.6
            ranked=sorted(rank,key=lambda i:(-rank[i],self.chunks[i]['id']))
            chosen=[]; per_source=collections.Counter()
            # Reserve three slots for official documentation, then admit related reports/releases.
            official=[i for i in ranked if self.chunks[i]['kind']=='docs']
            order=official+ranked
            doc_slots=0
            for pos,i in enumerate(order):
                source=self.chunks[i]['source_id']
                if per_source[source]>=1: continue
                is_doc=self.chunks[i]['kind']=='docs'
                if pos<len(official) and doc_slots>=3: continue
                chosen.append(i); per_source[source]+=1
                if is_doc: doc_slots+=1
                if len(chosen)>=k: break
        return [dict(self.chunks[i],retrieval_score=round(scores[i],5), rank=j+1) for j,i in enumerate(chosen)]
