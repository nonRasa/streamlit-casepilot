"""Content/model/config-addressed embedding cache; offline fixture is NOT semantic AI."""
import collections, hashlib, math, sqlite3
from .common import *

def normalize(text): return ' '.join(text.split())

def unit(vector):
    require(isinstance(vector,list) and 1<=len(vector)<=8192 and
            all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in vector),
            'invalid_embedding','بردار امبدینگ معتبر نیست.')
    norm=math.sqrt(sum(v*v for v in vector)); require(norm>0,'invalid_embedding','بردار صفر پذیرفته نیست.')
    return [v/norm for v in vector]

def cosine(a,b):
    require(len(a)==len(b),'embedding_dimension','ابعاد بردارها یکسان نیست.')
    return sum(x*y for x,y in zip(a,b))

class FixtureEmbedder:
    """Hashing features for deterministic integration tests, never a learned model."""
    identity={'provider':'offline-test-fixture','model':'hash-features-v2','dimensions':128,'normalization':'whitespace-v1'}
    def __init__(self): self.last_usage={'mode':'replay','provider_requests':0,'cost_usd':0}
    def embed(self,texts):
        from .retrieval import tokens,expand
        result=[]
        for text in texts:
            vector=[0.0]*128
            for word,count in collections.Counter(tokens(expand(normalize(text)))).items():
                n=int.from_bytes(hashlib.sha256(word.encode()).digest()[:8],'big')
                vector[n%128]+=(1 if n&128 else -1)*math.log1p(count)
            if not any(vector): vector[0]=1
            result.append(unit(vector))
        return result

class EmbeddingCache:
    def __init__(self,path,embedder,namespace=None):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.embedder=embedder; self.namespace=namespace
        with self.db() as db: db.execute('CREATE TABLE IF NOT EXISTS vectors(key TEXT PRIMARY KEY, vector TEXT)')
        self.last_stats={}
    def db(self): return sqlite3.connect(self.path,timeout=30,factory=ClosingConnection)
    def key(self,text):
        identity=dict(self.embedder.identity)
        if self.namespace: identity['index_namespace']=self.namespace
        return digest({'identity':identity,'content':normalize(text)})
    def get_many(self,texts,allow_create=True,batch_size=32):
        keys=[self.key(t) for t in texts]; found={}; missing={}
        with self.db() as db:
            for key,text in zip(keys,texts):
                if key in found or key in missing: continue
                row=db.execute('SELECT vector FROM vectors WHERE key=?',(key,)).fetchone()
                if row: found[key]=unit(json.loads(row[0]))
                else: missing[key]=normalize(text)
        require(allow_create or not missing,'embedding_index_not_ready','ابتدا ایندکس امبدینگ را با سقف هزینهٔ مستقل بسازید؛ ساخت کامل هنگام پاسخ‌گویی انجام نمی‌شود.')
        usages=[]; items=list(missing.items())
        batches=[]; batch=[]
        for item in items:
            if batch and (len(batch)>=batch_size or len(canonical([v for _,v in batch+[item]]).encode())>32000):
                batches.append(batch); batch=[]
            batch.append(item)
        if batch: batches.append(batch)
        for batch in batches:
            vectors=self.embedder.embed([t for _,t in batch])
            require(len(vectors)==len(batch),'invalid_embedding','تعداد بردارهای برگشتی معتبر نیست.')
            normalized=[unit(v) for v in vectors]
            require(len({len(v) for v in normalized+list(found.values())})==1,'embedding_dimension','مدل ابعاد ناسازگار برگرداند.')
            with self.db() as db:
                for (key,_),vector in zip(batch,normalized):
                    db.execute('INSERT OR IGNORE INTO vectors VALUES(?,?)',(key,canonical(vector))); found[key]=vector
            usages.append(dict(self.embedder.last_usage))
        self.last_stats={'texts':len(texts),'unique_missing':len(missing),'cache_hits':len(keys)-len(missing),'batches':len(usages),'usage':usages,'identity':self.embedder.identity}
        return [found[k] for k in keys]
