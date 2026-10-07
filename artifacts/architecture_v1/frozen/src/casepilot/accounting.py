"""Shared durable USD ledger; reservations survive timeout/process failure."""
import sqlite3, secrets
from .common import *

class Budget:
    def __init__(self,path,cap=5.0):
        require(0<cap<=5,'invalid_budget','بودجهٔ تیم نمی‌تواند بیش از پنج دلار باشد.')
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.cap=cap
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,at TEXT,model TEXT,reserved REAL,charged REAL,status TEXT,input_tokens INTEGER,output_tokens INTEGER,kind TEXT)')
    def db(self): return sqlite3.connect(self.path,timeout=30,factory=ClosingConnection)
    def reserve(self,amount,model,kind='chat'):
        require(amount>0,'invalid_price','برآورد هزینه باید مثبت باشد.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            total=db.execute('SELECT COALESCE(SUM(charged),0) FROM calls').fetchone()[0]
            require(total+amount<=self.cap,'budget_exhausted','بودجهٔ تیم برای فراخوانی بعدی کافی نیست.')
            cid=secrets.token_hex(12)
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?)',(cid,utcnow(),model,amount,amount,'reserved',None,None,kind))
            return cid
    def settle(self,cid,input_tokens,output_tokens,input_rate,output_rate):
        cost=(input_tokens*input_rate+output_tokens*output_rate)/1e6
        with self.db() as db:
            db.execute('UPDATE calls SET charged=?,status=?,input_tokens=?,output_tokens=? WHERE id=?',
                       (cost,'confirmed',input_tokens,output_tokens,cid))
        return cost
    def uncertain(self,cid):
        with self.db() as db: db.execute("UPDATE calls SET status='uncertain_reserved' WHERE id=?",(cid,))
    def report(self):
        with self.db() as db:
            db.row_factory=sqlite3.Row; rows=[dict(x) for x in db.execute('SELECT * FROM calls ORDER BY at')]
        return {'budget_usd':self.cap,'charged_or_reserved_usd':sum(x['charged'] for x in rows),
                'confirmed_usd':sum(x['charged'] for x in rows if x['status']=='confirmed'),
                'uncertain_reserved_usd':sum(x['charged'] for x in rows if x['status']!='confirmed'),
                'requests':len(rows),'embedding_requests':0,'embedding_cost_usd':0,
                'input_tokens':sum(x['input_tokens'] or 0 for x in rows),'output_tokens':sum(x['output_tokens'] or 0 for x in rows),'calls':rows}
