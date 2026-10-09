"""Ten scripted local multi-turn scenarios; approvals are fixtures, never humans."""
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.model import ReplayClient
from casepilot.common import CasePilotError,write_json

class EmptyRetriever:
    last_trace={'method':'empty_operational_fixture'}
    def search(self,*args,**kwargs): return []

def run():
    dev=json.loads((ROOT/'eval/quality_cases.json').read_text(encoding='utf-8'))[:5]
    fresh=json.loads((ROOT/'artifacts/quality_v22/holdout/cases.json').read_text(encoding='utf-8'))[:5]
    cases=dev+fresh; results=[]
    names=['unauthorized','wrong_case','changed_case','edited_proposal','expired_approval','after_commit_loss','before_commit_failure','restart_pending','duplicate_turn','resume_interrupted']
    def expect_error(fn,code):
        try: fn()
        except CasePilotError as exc: assert exc.code==code; return code
        raise AssertionError('Expected containment error')
    with tempfile.TemporaryDirectory() as temp:
        for i,(case,name) in enumerate(zip(cases,names)):
            store=Store(Path(temp)/(str(i)+'.sqlite3')); client=ReplayClient(); agent=Agent(store,client=client,hybrid=EmptyRetriever())
            cid=case['id']; error=None
            try:
                first=agent.turn(cid,case['initial_message'],'first'); assert not store.get(cid)['comments']
                agent.turn(cid,'اصلاح آزمایشی: نسخهٔ دقیق محیط اکنون مشخص است.','correction',facts={'streamlit_version':'1.51.1.dev20251130'})
                state=Store(store.path).get(cid); assert state['facts']['streamlit_version']=='1.51.1.dev20251130'
                p=next(p for p in state['proposals'] if p['id']==state['pending_proposal'])
                def approve(ttl=900): return store.review(cid,p['id'],p['hash'],'approve','بازبین ساختگی سناریو',ttl=ttl)['approval_id']
                if name=='unauthorized': expect_error(lambda:store.execute(cid,p['id'],'forged'),'approval_required')
                elif name=='wrong_case':
                    aid=approve(); store.update('Other','پروندهٔ دیگر'); expect_error(lambda:store.execute('Other',p['id'],aid),'approval_required')
                elif name=='changed_case':
                    aid=approve(); store.update(cid,'اصلاح بعدی کاربر'); expect_error(lambda:store.execute(cid,p['id'],aid),'stale_approval')
                elif name=='edited_proposal':
                    replacement=store.review(cid,p['id'],p['hash'],'edit','بازبین ساختگی سناریو',[{'type':'comment','body':'پاسخ اصلاح‌شدهٔ آزمایشی'}])
                    expect_error(lambda:store.execute(cid,replacement['id'],'forged'),'approval_required')
                    assert replacement['requires_new_approval']
                elif name=='expired_approval':
                    aid=approve(-1); expect_error(lambda:store.execute(cid,p['id'],aid),'approval_expired')
                elif name=='after_commit_loss':
                    aid=approve(); expect_error(lambda:store.execute(cid,p['id'],aid,fail='after_commit'),'connection_lost')
                    result=Store(store.path).execute(cid,p['id'],aid); assert result['replayed']; assert len(store.get(cid)['comments'])==1
                elif name=='before_commit_failure':
                    aid=approve(); expect_error(lambda:store.execute(cid,p['id'],aid,fail='before_commit'),'tool_unavailable')
                    assert not store.get(cid)['comments']; Store(store.path).execute(cid,p['id'],aid); assert len(store.get(cid)['comments'])==1
                elif name=='restart_pending':
                    store=Store(store.path); assert store.get(cid)['pending_proposal']==p['id']; aid=approve(); store.execute(cid,p['id'],aid); assert len(store.get(cid)['comments'])==1
                elif name=='duplicate_turn':
                    calls=client.calls
                    repeated=agent.turn(cid,'اصلاح آزمایشی: نسخهٔ دقیق محیط اکنون مشخص است.','correction',facts={'streamlit_version':'1.51.1.dev20251130'})
                    assert repeated['request_replayed'] and client.calls==calls; assert len(store.get(cid)['messages'])==2
                elif name=='resume_interrupted':
                    with patch.object(store,'save_turn',side_effect=RuntimeError('simulated stop')):
                        try: agent.turn(cid,'پیگیری ساختگی پس از توقف.','resume')
                        except RuntimeError: pass
                    resumed=Agent(Store(store.path),client=client,hybrid=EmptyRetriever()).resume(cid,'resume')
                    assert resumed['case_id']==cid; assert len(store.get(cid)['messages'])==3
                final=store.get(cid)
                if name not in ('after_commit_loss','before_commit_failure','restart_pending'): assert not final['comments']
                passed=True
            except Exception as exc: passed=False; error=getattr(exc,'code',type(exc).__name__); final=store.get(cid)
            results.append({'scenario':name,'case_id':cid,'split':'development_seen' if i<5 else 'unseen_replay_only','passed':passed,'error':error,
                'message_count':len(final['messages']),'comment_count':len(final['comments']),'facts':final['facts'],'state_revision':final['revision'],
                'provider_requests':0,'approval_kind':'scripted_fixture','human_review':False})
    dest=ROOT/'artifacts/quality_v22/operations.json'
    if dest.exists(): raise SystemExit('نتایج سناریوها بازنویسی نمی‌شوند.')
    write_json(dest,{'mode':'scripted_local_replay','scenarios':results,'passed':sum(r['passed'] for r in results),'attempted':len(results),
        'never_started':0,'unseen_scenarios':5,'paid_requests':0,'site_execution':False,'human_review':False})
    print(json.dumps({'passed':sum(r['passed'] for r in results),'attempted':len(results)}))
    return all(r['passed'] for r in results)
if __name__=='__main__': sys.exit(0 if run() else 1)
