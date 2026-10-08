from __future__ import annotations
import hashlib, json, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class CasePilotError(Exception):
    def __init__(self, code, message):
        super().__init__(message); self.code=code

class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()

def utcnow(): return datetime.now(timezone.utc).isoformat()
def canonical(obj): return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(obj): return hashlib.sha256(canonical(obj).encode()).hexdigest()
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write_json(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

MAPBOX_TOKEN_RE = re.compile(r'\b(?:pk|sk|tk)\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b')

def redact(text):
    text=MAPBOX_TOKEN_RE.sub('[REDACTED_MAPBOX_TOKEN]',str(text))
    text=re.sub(r'(?i)(bearer\s+)[\w.\-]+',r'\1[REDACTED]',str(text))
    text=re.sub(r'\b(?:sk|ghp|github_pat)[-_][A-Za-z0-9_-]{10,}\b','[REDACTED]',text)
    text=re.sub(r'\btpsg-[A-Za-z0-9_-]{12,}\b','[REDACTED_METIS_KEY]',text)
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[EMAIL]',text)
    return text

def require(condition, code, message):
    if not condition: raise CasePilotError(code,message)

def identifier(value):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value), 'invalid_id','شناسهٔ پرونده یا درخواست نامعتبر است.')
    return value

def bounded_text(value,name='text',limit=20000):
    require(isinstance(value,str) and 0<len(value.strip())<=limit,'invalid_input',f'مقدار {name} معتبر نیست.')
    return redact(value.strip())

FACT_KEYS={'streamlit_version','python_version','os','browser','deployment','reproducible','resolved','symptom_scope'}
def facts_input(facts):
    require(isinstance(facts,dict) and set(facts)<=FACT_KEYS,'invalid_facts','فیلد واقعیت مجاز نیست.')
    for key,value in facts.items():
        require(value is None or isinstance(value,(str,bool)), 'invalid_facts','نوع واقعیت معتبر نیست.')
        if isinstance(value,str): require(len(value)<=500,'invalid_facts','مقدار واقعیت طولانی است.')
    return {k:(redact(v) if v.strip() and v.strip().casefold() not in ('_no response_','n/a','unknown','نامعلوم','نامشخص') else None) if isinstance(v,str) else v for k,v in facts.items()}
