"""Transactional tracker. The model never receives a write-capable DB handle."""
from __future__ import annotations
import json, secrets, sqlite3
from contextlib import contextmanager
from .common import *

DDL='''
CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, case_id TEXT, kind TEXT, payload TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, case_id TEXT NOT NULL, revision INTEGER NOT NULL,
 hash TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, proposal_id TEXT UNIQUE NOT NULL, case_id TEXT NOT NULL,
 hash TEXT NOT NULL, revision INTEGER NOT NULL, reviewer TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS executions(proposal_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY, case_id TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS turns(case_id TEXT NOT NULL, request_id TEXT NOT NULL, input_hash TEXT NOT NULL,
 output TEXT NOT NULL, PRIMARY KEY(case_id,request_id));
CREATE TABLE IF NOT EXISTS turn_inputs(case_id TEXT NOT NULL, request_id TEXT NOT NULL, input_hash TEXT NOT NULL,
 revision INTEGER NOT NULL, PRIMARY KEY(case_id,request_id));
'''

class Store:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db: db.executescript(DDL)

    def connect(self):
        db=sqlite3.connect(self.path,timeout=20,factory=ClosingConnection); db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA journal_mode=WAL')
        return db

    @contextmanager
    def tx(self):
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE'); yield db; db.commit()
        except BaseException:
            db.rollback(); raise
        finally: db.close()

    def _event(self,db,cid,kind,payload):
        # Redact decoded string values, never serialized JSON: regex replacement
        # after serialization can consume the n in a \n escape before an email.
        def clean(value):
            if isinstance(value,str): return redact(value)
            if isinstance(value,list): return [clean(x) for x in value]
            if isinstance(value,dict): return {k:clean(v) for k,v in value.items()}
            return value
        db.execute('INSERT INTO events(case_id,kind,payload,at) VALUES(?,?,?,?)',
                   (cid,kind,canonical(clean(payload)),utcnow()))

    def event(self,cid,kind,payload):
        with self.tx() as db: self._event(db,cid,kind,payload)

    def _load(self,db,cid):
        row=db.execute('SELECT state FROM cases WHERE id=?',(cid,)).fetchone()
        require(row is not None,'not_found','پرونده یافت نشد.')
        return json.loads(row['state'])

    def get(self,cid):
        identifier(cid)
        with self.connect() as db:
            state=self._load(db,cid)
            state['comments']=[dict(x) for x in db.execute('SELECT id,body FROM comments WHERE case_id=? ORDER BY rowid',(cid,))]
            state['proposals']=[dict(x) for x in db.execute('SELECT id,revision,hash,status,payload FROM proposals WHERE case_id=? ORDER BY rowid',(cid,))]
            for p in state['proposals']: p['payload']=json.loads(p['payload'])
            return state

    def update(self,cid,message,facts=None,checks=None,expected_revision=None,request_id=None,input_hash=None):
        identifier(cid); message=bounded_text(message); facts=facts_input(facts or {}); checks=checks or []
        require(isinstance(checks,list) and len(checks)<=30,'invalid_checks','بررسی‌ها نامعتبرند.')
        checks=[bounded_text(x,'check',1000) for x in checks]
        with self.tx() as db:
            if request_id:
                prior=db.execute('SELECT * FROM turn_inputs WHERE case_id=? AND request_id=?',(cid,request_id)).fetchone()
                if prior:
                    require(prior['input_hash']==input_hash,'request_conflict','شناسهٔ درخواست برای ورودی دیگری است.')
                    state=self._load(db,cid)
                    require(state['revision']==prior['revision'],'request_superseded','پس از این درخواست اطلاعات تازه رسیده است؛ شناسهٔ جدید لازم است.')
                    return state
            row=db.execute('SELECT state FROM cases WHERE id=?',(cid,)).fetchone()
            state=json.loads(row['state']) if row else {'id':cid,'revision':0,'facts':{},'fact_history':[], 'checks':[], 'messages':[], 'status':'open','labels':[], 'source_ids':[], 'pending_proposal':None,'action_results':[]}
            if expected_revision is not None: require(state['revision']==expected_revision,'conflict','وضعیت پرونده تغییر کرده است.')
            for key,value in facts.items():
                if key in state['facts'] and state['facts'][key]!=value:
                    state['fact_history'].append({'key':key,'old':state['facts'][key],'new':value,'at':utcnow()})
                state['facts'][key]=value
            state['checks']=list(dict.fromkeys(state['checks']+checks))
            state['messages'].append({'role':'user','text':message,'at':utcnow()})
            require(len(state['messages'])<=100,'turn_limit','سقف نوبت‌های پرونده رسیده است؛ پرونده را برای بررسی انسانی ارجاع دهید.')
            state['revision']+=1; state['pending_proposal']=None
            db.execute("UPDATE proposals SET status='stale' WHERE case_id=? AND status IN ('pending','approved')",(cid,))
            db.execute('INSERT INTO cases VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,state=excluded.state',
                       (cid,state['revision'],canonical(state)))
            self._event(db,cid,'user_update',{'revision':state['revision'],'message':message,'facts':facts,'checks':checks})
            if request_id: db.execute('INSERT INTO turn_inputs VALUES(?,?,?,?)',(cid,request_id,input_hash,state['revision']))
            return state

    def propose(self,cid,revision,payload):
        validate_actions(payload)
        with self.tx() as db:
            state=self._load(db,cid); require(state['revision']==revision,'conflict','دادهٔ جدید رسیده است؛ پیشنهاد دوباره ساخته شود.')
            pid=secrets.token_hex(12); h=digest({'case_id':cid,'revision':revision,'payload':payload})
            db.execute("UPDATE proposals SET status='stale' WHERE case_id=? AND status IN ('pending','approved')",(cid,))
            db.execute('INSERT INTO proposals VALUES(?,?,?,?,?,?)',(pid,cid,revision,h,canonical(payload),'pending'))
            state['pending_proposal']=pid; state['source_ids']=payload.get('source_ids',[])
            db.execute('UPDATE cases SET state=? WHERE id=?',(canonical(state),cid))
            self._event(db,cid,'proposal_created',{'proposal_id':pid,'hash':h,'revision':revision,'payload':payload})
            return {'id':pid,'case_id':cid,'revision':revision,'hash':h,'payload':payload,'status':'pending'}

    def review(self,cid,pid,expected_hash,decision,reviewer,edited_actions=None,ttl=900):
        import time
        identifier(cid); reviewer=bounded_text(reviewer,'reviewer',100)
        require(decision in ('approve','reject','edit'),'invalid_review','تصمیم بازبین نامعتبر است.')
        if decision=='edit': validate_actions({'actions':edited_actions})
        with self.tx() as db:
            state=self._load(db,cid)
            row=db.execute('SELECT * FROM proposals WHERE id=? AND case_id=?',(pid,cid)).fetchone()
            require(row is not None,'not_found','پیشنهاد متعلق به این پرونده نیست.')
            require(row['hash']==expected_hash,'proposal_changed','متن پیشنهادی با متن دیده‌شده یکسان نیست.')
            require(row['revision']==state['revision'] and state['pending_proposal']==pid,'stale_approval','پیشنهاد منقضی شده است.')
            require(row['status']=='pending','already_reviewed','پیشنهاد قبلاً بررسی شده است.')
            if decision=='edit':
                payload=json.loads(row['payload']); payload['actions']=edited_actions
                new_id=secrets.token_hex(12); h=digest({'case_id':cid,'revision':state['revision'],'payload':payload})
                db.execute("UPDATE proposals SET status='edited' WHERE id=?",(pid,))
                db.execute('INSERT INTO proposals VALUES(?,?,?,?,?,?)',(new_id,cid,state['revision'],h,canonical(payload),'pending'))
                state['pending_proposal']=new_id
                db.execute('UPDATE cases SET state=? WHERE id=?',(canonical(state),cid))
                result={'id':new_id,'case_id':cid,'hash':h,'payload':payload,'status':'pending','requires_new_approval':True}
            elif decision=='reject':
                db.execute("UPDATE proposals SET status='rejected' WHERE id=?",(pid,))
                state['pending_proposal']=None
                db.execute('UPDATE cases SET state=? WHERE id=?',(canonical(state),cid)); result={'status':'rejected','changed':False}
            else:
                aid=secrets.token_urlsafe(24)
                db.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?,?)',(aid,pid,cid,row['hash'],state['revision'],reviewer,time.time()+ttl))
                db.execute("UPDATE proposals SET status='approved' WHERE id=?",(pid,))
                result={'status':'approved','approval_id':aid,'proposal_id':pid,'expires_in_seconds':ttl}
            self._event(db,cid,'human_review',{'proposal_id':pid,'decision':decision,'reviewer':reviewer,'result':{k:v for k,v in result.items() if k!='approval_id'}})
            return result

    def execute(self,cid,pid,approval_id,fail=None):
        import time
        identifier(cid)
        # Retry checks committed result before requiring an unexpired approval.
        with self.tx() as db:
            approval=db.execute('SELECT * FROM approvals WHERE id=? AND proposal_id=? AND case_id=?',(approval_id,pid,cid)).fetchone()
            require(approval is not None,'approval_required','تأیید معتبر این پرونده لازم است.')
            existing=db.execute('SELECT result FROM executions WHERE proposal_id=? AND case_id=?',(pid,cid)).fetchone()
            if existing: return dict(json.loads(existing['result']),replayed=True)
            row=db.execute('SELECT * FROM proposals WHERE id=? AND case_id=?',(pid,cid)).fetchone(); state=self._load(db,cid)
            require(row is not None,'approval_required','پیشنهاد یافت نشد.')
            require(approval['hash']==row['hash'] and approval['revision']==state['revision'] and state['pending_proposal']==pid,'stale_approval','اطلاعات یا پیشنهاد تغییر کرده است.')
            require(row['status']=='approved','approval_required','پیشنهاد تأیید نشده است.')
            require(approval['expires']>=time.time(),'approval_expired','تأیید منقضی شده است.')
            payload=json.loads(row['payload']); validate_actions(payload)
            if fail=='before_commit': raise CasePilotError('tool_unavailable','خرابی آزمایشی ابزار پیش از ثبت.')
            effects=[]
            for index,action in enumerate(payload['actions']):
                kind=action['type']
                if kind=='comment':
                    comment_id=f'{pid}-{index}'; db.execute('INSERT INTO comments VALUES(?,?,?)',(comment_id,cid,action['body']))
                    effects.append({'type':kind,'comment_id':comment_id})
                elif kind=='status':
                    require(action['value']!='closed' or state['facts'].get('resolved') is True,'resolution_unconfirmed','بسته‌شدن نیازمند تأیید رفع از کاربر است.')
                    state['status']=action['value']; effects.append(action)
                elif kind=='labels': state['labels']=action['values']; effects.append(action)
            state['revision']+=1; state['pending_proposal']=None
            result={'proposal_id':pid,'case_id':cid,'effects':effects,'revision':state['revision'],'replayed':False,'resolution_confirmed':state['facts'].get('resolved') is True}
            state['action_results'].append(result)
            db.execute('UPDATE cases SET revision=?,state=? WHERE id=?',(state['revision'],canonical(state),cid))
            db.execute("UPDATE proposals SET status='executed' WHERE id=?",(pid,))
            db.execute('INSERT INTO executions VALUES(?,?,?)',(pid,cid,canonical(result)))
            self._event(db,cid,'action_committed',result)
        if fail=='after_commit': raise CasePilotError('connection_lost','خرابی آزمایشی پس از ثبت؛ نتیجه را با همان شناسه بازیابی کنید.')
        return result

    def turn_result(self,cid,rid,input_hash):
        with self.connect() as db:
            row=db.execute('SELECT * FROM turns WHERE case_id=? AND request_id=?',(cid,rid)).fetchone()
            if row:
                require(row['input_hash']==input_hash,'request_conflict','شناسهٔ درخواست با ورودی دیگری استفاده شده است.')
                return json.loads(row['output'])

    def save_turn(self,cid,rid,h,output):
        with self.tx() as db: db.execute('INSERT INTO turns VALUES(?,?,?,?)',(cid,rid,h,canonical(output)))

    def traces(self):
        with self.connect() as db: return [dict(r,payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM events ORDER BY id')]

def validate_actions(payload):
    actions=payload.get('actions')
    require(isinstance(actions,list) and 1<=len(actions)<=3,'invalid_action','تعداد اقدام‌ها نامعتبر است.')
    kinds=[]
    for action in actions:
        require(isinstance(action,dict),'invalid_action','ساختار اقدام نامعتبر است.'); kind=action.get('type'); kinds.append(kind)
        if kind=='comment':
            require(set(action)=={'type','body'},'invalid_action','فیلد اضافی اقدام پذیرفته نیست.'); bounded_text(action['body'],'comment',12000)
        elif kind=='status': require(set(action)=={'type','value'} and action['value'] in ('open','waiting_user','escalated','closed'),'invalid_action','وضعیت نامعتبر است.')
        elif kind=='labels': require(set(action)=={'type','values'} and isinstance(action['values'],list) and len(action['values'])<=8 and all(isinstance(x,str) and 0<len(x)<=40 for x in action['values']),'invalid_action','برچسب نامعتبر است.')
        else: raise CasePilotError('invalid_action','ابزار نوشتن مجاز نیست.')
    require(len(set(kinds))==len(kinds),'invalid_action','نوع اقدام تکراری است.')
