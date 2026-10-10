"""Small local HTTP adapter; human reviewer and operator have separate credentials."""
from __future__ import annotations
import hmac, json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from .common import *
from .agent import Agent

def create_server(host='127.0.0.1',port=8765,agent=None,user_token=None,review_token=None):
    user_token=user_token or os.getenv('CASEPILOT_API_TOKEN',''); review_token=review_token or os.getenv('CASEPILOT_REVIEW_TOKEN','')
    require(len(user_token)>=24 and len(review_token)>=24 and user_token!=review_token,'missing_server_tokens','دو توکن جداگانه با حداقل ۲۴ نویسه برای اپراتور و بازبین تنظیم کنید.')
    agent=agent or Agent(mode=os.getenv('CASEPILOT_MODE','replay'))
    class Handler(BaseHTTPRequestHandler):
        server_version='CasePilot/1.0'
        def log_message(self,*args): pass  # Never log Authorization, user input, or URL query strings.
        def send_json(self,status,payload):
            raw=json.dumps(payload,ensure_ascii=False).encode()
            self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
        def auth(self,review=False):
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            expected=review_token if review else user_token
            require(hmac.compare_digest(token,expected),'unauthorized','مجوز این مسیر معتبر نیست.')
        def do_GET(self):
            try:
                parts=urlsplit(self.path)
                if parts.path=='/':
                    raw=(Path(__file__).parent/'web'/'index.html').read_bytes()
                    self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(raw)))
                    self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
                    self.end_headers(); self.wfile.write(raw); return
                if parts.path=='/health': self.send_json(200,{'status':'ok','mode':agent.client.mode}); return
                self.auth()
                if parts.path=='/api/case':
                    cid=parse_qs(parts.query).get('case_id',[''])[0]; self.send_json(200,agent.store.get(cid)); return
                self.send_json(404,{'error':'not_found'})
            except CasePilotError as exc: self.send_json(401 if exc.code=='unauthorized' else 400,{'error':exc.code,'message':str(exc)})
        def do_POST(self):
            try:
                path=urlsplit(self.path).path
                require(path in ('/api/turn','/api/review','/api/execute'),'not_found','مسیر یافت نشد.')
                self.auth(review=path in ('/api/review','/api/execute'))
                length=int(self.headers.get('Content-Length','0'))
                require(0<length<=60000,'payload_limit','اندازهٔ ورودی معتبر نیست.')
                require('application/json' in self.headers.get('Content-Type',''),'invalid_content_type','ورودی باید JSON باشد.')
                body=json.loads(self.rfile.read(length)); require(isinstance(body,dict),'invalid_input','ورودی شیء نیست.')
                fields={
                    '/api/turn':({'case_id','message','request_id'},{'facts','checks','method'}),
                    '/api/review':({'case_id','proposal_id','proposal_hash','decision','reviewer'},{'edited_actions'}),
                    '/api/execute':({'case_id','proposal_id','approval_id'},set())}
                required,optional=fields[path]
                require(required<=set(body)<=required|optional,'invalid_input','فیلد ورودی ناشناخته یا ناقص است.')
                if path=='/api/turn': result=agent.turn(**body)
                elif path=='/api/review':
                    result=agent.store.review(body['case_id'],body['proposal_id'],body['proposal_hash'],body['decision'],body['reviewer'],body.get('edited_actions'))
                else: result=agent.store.execute(body['case_id'],body['proposal_id'],body['approval_id'])
                self.send_json(200,result)
            except CasePilotError as exc:
                status=401 if exc.code=='unauthorized' else 404 if exc.code=='not_found' else 409 if exc.code in ('conflict','stale_approval','proposal_changed','request_conflict','request_superseded') else 503 if exc.code in ('provider_error','budget_exhausted') else 400
                self.send_json(status,{'error':exc.code,'message':str(exc)})
            except (ValueError,TypeError,KeyError): self.send_json(400,{'error':'invalid_input','message':'ورودی قابل پردازش نیست.'})
            except Exception: self.send_json(500,{'error':'internal_error','message':'خطای داخلی؛ نتیجهٔ ثبت‌شده را پیش از تکرار بررسی کنید.'})
    return ThreadingHTTPServer((host,port),Handler)

def serve(host='127.0.0.1',port=8765):
    server=create_server(host,port)
    print(f'نشانی رابط: http://{host}:{port}\nوضعیت: توکن‌ها فقط از محیط خوانده شدند؛ کلید مدل در مرورگر وارد نشود.')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
