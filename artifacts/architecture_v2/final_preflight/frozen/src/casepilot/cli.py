import argparse, json, os, shutil, sys, tempfile
from .common import *
from .store import Store
from .agent import Agent
from .server import serve

def emit(value): print(json.dumps(value,ensure_ascii=False,indent=2))

def demo():
    with tempfile.TemporaryDirectory(prefix='casepilot-demo-') as tmp:
        store=Store(Path(tmp)/'tracker.sqlite3'); agent=Agent(store=store)
        out=agent.turn('demo-1','برنامه روی سرور در بارگذاری می‌ماند؛ نصب مجدد بی‌اثر بود.','turn-1',checks=['نصب مجدد بی‌اثر بود'])
        second=agent.turn('demo-1','نسخه مشخص شد؛ خطا فقط روی سرور است.','turn-2',facts={'streamlit_version':'1.49.0','deployment':'docker','reproducible':True})
        p=second['proposal']; review=store.review('demo-1',p['id'],p['hash'],'approve','بازبین آزمایشی')
        first=store.execute('demo-1',p['id'],review['approval_id']); repeated=store.execute('demo-1',p['id'],review['approval_id'])
        result={'mode':'replay','reviewer':'scripted test actor; not a live human review','first_turn':out,'second_turn':second,'execution':first,'retry':repeated,'actual_comment_count':len(store.get('demo-1')['comments'])}
        write_json(ROOT/'artifacts'/'demo.json',result); write_json(ROOT/'artifacts'/'demo_trace.json',store.traces()); emit(result)

def main():
    parser=argparse.ArgumentParser(description='دستیار محلی پیگیری پرونده'); parser.add_argument('--db',default=str(ROOT/'runtime'/'tracker.sqlite3'))
    sub=parser.add_subparsers(dest='cmd',required=True)
    sub.add_parser('demo'); sub.add_parser('doctor')
    s=sub.add_parser('serve'); s.add_argument('--host',default='127.0.0.1'); s.add_argument('--port',type=int,default=8765)
    s=sub.add_parser('turn'); s.add_argument('--case',required=True); s.add_argument('--message',required=True); s.add_argument('--request-id',required=True); s.add_argument('--facts',default='{}'); s.add_argument('--checks',default='[]'); s.add_argument('--mode',choices=['replay','live'],default=os.getenv('CASEPILOT_MODE','replay')); s.add_argument('--method',choices=['baseline','final'],default='final')
    s=sub.add_parser('show'); s.add_argument('--case',required=True)
    s=sub.add_parser('review'); s.add_argument('--case',required=True); s.add_argument('--proposal',required=True); s.add_argument('--hash',required=True); s.add_argument('--decision',choices=['approve','reject','edit'],required=True); s.add_argument('--reviewer',required=True); s.add_argument('--actions-file')
    s=sub.add_parser('execute'); s.add_argument('--case',required=True); s.add_argument('--proposal',required=True); s.add_argument('--approval',required=True)
    s=sub.add_parser('reset'); s.add_argument('--confirm-local-reset',action='store_true')
    args=parser.parse_args()
    try:
        if args.cmd=='demo': demo(); return
        if args.cmd=='doctor':
            emit({'python':sys.version.split()[0],'snapshot_exists':(ROOT/'data'/'corpus.json').exists(),'live_key_present':bool(os.getenv('METIS_API_KEY')),'model_configured':bool(os.getenv('METIS_MODEL')),'mode':os.getenv('CASEPILOT_MODE','replay'),'network_required_offline':False}); return
        if args.cmd=='serve':
            from .server import create_server
            server=create_server(args.host,args.port,Agent(store=Store(args.db),mode=os.getenv('CASEPILOT_MODE','replay')))
            print(f'نشانی رابط: http://{args.host}:{args.port}')
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: server.server_close()
            return
        if args.cmd=='reset':
            require(args.confirm_local_reset,'confirmation_required','برای بازنشانی رهگیر، گزینهٔ صریح بازنشانی لازم است.')
            db=Path(args.db).resolve(); allowed=(ROOT/'runtime').resolve()
            require(db.is_relative_to(allowed),'reset_path','بازنشانی فقط در پوشهٔ محلی runtime مجاز است.')
            require(db.name!='team_budget.sqlite3','budget_protected','دفتر هزینه با بازنشانی رهگیر حذف نمی‌شود.')
            for suffix in ('','-wal','-shm'):
                p=Path(str(db)+suffix)
                if p.exists(): p.unlink()
            emit({'reset':True,'budget_untouched':True}); return
        store=Store(args.db)
        if args.cmd=='turn': emit(Agent(store=store,mode=args.mode).turn(args.case,args.message,args.request_id,json.loads(args.facts),json.loads(args.checks),args.method))
        elif args.cmd=='show': emit(store.get(args.case))
        elif args.cmd=='review': emit(store.review(args.case,args.proposal,args.hash,args.decision,args.reviewer,read_json(args.actions_file) if args.actions_file else None))
        elif args.cmd=='execute': emit(store.execute(args.case,args.proposal,args.approval))
    except (CasePilotError,ValueError) as exc:
        emit({'error':getattr(exc,'code','invalid_input'),'message':str(exc)}); raise SystemExit(2)

if __name__=='__main__': main()
