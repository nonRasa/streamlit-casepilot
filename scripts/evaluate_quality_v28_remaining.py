"""Budget-fenced live product evaluation for the frozen V28 follow-up suite."""
import argparse
import copy
import hashlib
import json
import math
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,require,canonical,utcnow,digest
from casepilot.accounting import Budget
from casepilot.model import MetisClient
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.hybrid import HybridRetriever,embedding_text
from casepilot.context_pack import pack_evidence
from casepilot.tokenization import count_tokens
from casepilot.schema_preflight import check_provider_schema
from casepilot.roles import QUALITY_EXTRACTION,RERANK
from casepilot.case_type import selection_schema
from complete_quality_v27 import CampaignBudget,active_hash
from evaluate_quality_v27_live import credentials
from evaluate_quality_v25_live import sha
from prepare_quality_v28_remaining import RUN,DATA

MAX_PROVIDER_REQUESTS=208
HARD_CAP_USD=1.10
MAX_ATTEMPTS=26
MAX_REQUESTS_PER_TURN=8
TURN_COST_CAP_USD=0.04
MAX_TURN_SECONDS=600
MODEL='gpt-4.1-mini'
EMBEDDING_MODEL='text-embedding-3-small'
PHASE_LIMITS={
    'development':{'requests':144,'usd':0.78},
    'holdout':{'requests':32,'usd':0.16},
    'connection_retry':{'requests':32,'usd':0.16},
}


def active_hash():
    """Bind the selected run to product code and this exact evaluation harness."""
    paths=[p for base in ('src','schemas','policies','tests') if (ROOT/base).exists()
           for p in (ROOT/base).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths.append(ROOT/'scripts'/'evaluate_quality_v28_remaining.py')
    return digest({str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)})


def verify():
    auth=read_json(RUN/'authorization.json')
    require(auth.get('human_approval')=='approved' and auth.get('hard_cap_usd')==HARD_CAP_USD and
        auth.get('max_requests')==MAX_PROVIDER_REQUESTS and auth.get('max_product_attempts')==MAX_ATTEMPTS and
        auth.get('phase_limits')==PHASE_LIMITS and auth.get('models')=={
            'text_roles':MODEL,'query_embedding':EMBEDDING_MODEL},
        'invalid_budget','مجوز بودجه یا دامنهٔ کارزار معتبر نیست.')
    manifest=read_json(DATA/'manifest.json')
    require(sha(DATA/'manifest.json')==auth['manifest_sha256'] and
        sha(DATA/'protocol.json')==auth['protocol_sha256'] and
        sha(DATA/'pricing.json')==auth['pricing_sha256'],
        'frozen_suite_changed','مجموعه یا تعرفه پس از انجماد تغییر کرده است.')
    for name,expected in manifest['files'].items():
        require(sha(DATA/name)==expected,'frozen_suite_changed','فایل ارزیابی منجمد تغییر کرده است.')
    for name,expected in manifest['corpus_hashes'].items():
        require(sha(ROOT/'data'/name)==expected,'corpus_changed','snapshot ایندکس تغییر کرده است.')
    return auth


class FollowupBudget(CampaignBudget):
    pass


def new_client(phase):
    auth=verify()
    prices=read_json(DATA/'pricing.json')['models']
    rates={row['model']:row for row in prices}
    chat=rates[MODEL];embed=rates[EMBEDDING_MODEL]
    require(chat['input_usd_per_million']==0.44 and chat['output_usd_per_million']==1.76 and
        embed['input_usd_per_million']==0.022,'pricing_changed','تعرفه خارج از طرح تأییدشده است.')
    os.environ.update(METIS_MODEL=MODEL,METIS_JUDGE_MODEL=MODEL,METIS_EMBEDDING_MODEL=EMBEDDING_MODEL,
        METIS_BASE_URL='https://api.metisai.ir/openai/v1',
        CASEPILOT_INPUT_USD_PER_MILLION=str(chat['input_usd_per_million']),
        CASEPILOT_OUTPUT_USD_PER_MILLION=str(chat['output_usd_per_million']),
        CASEPILOT_EMBEDDING_USD_PER_MILLION=str(embed['input_usd_per_million']),
        CASEPILOT_MAX_OUTPUT_TOKENS='1600',
        CASEPILOT_BUDGET_USD=str(min(5,auth['cost_before']['charged_or_reserved_usd']+HARD_CAP_USD)),
        CASEPILOT_BUDGET_DB=str(ROOT/'runtime'/'team_budget.sqlite3'),
        CASEPILOT_CHAT_ENCODING='o200k_base',CASEPILOT_CONTEXT_TOKENS='24000',CASEPILOT_INDEX_FORMAT='v2')
    credentials()  # Secret is read locally; never serialized or printed.
    cl=MetisClient();cl.budget=FollowupBudget(cl.budget.path,auth,phase)
    private=ROOT/'runtime'/'quality_v28_remaining'
    cl.cache=private/'cache';cl.cache.mkdir(parents=True,exist_ok=True)
    cl.diagnostics=private/'diagnostics';cl.audit=[]
    original=cl._perform_request
    def observed(payload,kind='chat',endpoint='/chat/completions',input_rate=None,output_rate=None):
        if kind=='embedding':
            require(endpoint=='/embeddings' and isinstance(payload.get('input'),list) and len(payload['input'])==1,
                'index_rebuild_not_authorized','فقط embedding تک‌پرسش مجاز است؛ ساخت بردارهای corpus بسته است.')
        request={'kind':kind,'endpoint':endpoint,'payload':payload,'payload_hash':digest(payload),
            'input_tokens':count_tokens(canonical(payload),encoding='o200k_base')}
        cl.audit.append(request)
        try:
            request['raw_reply']=original(payload,kind,endpoint,input_rate,output_rate)
            return request['raw_reply']
        except Exception as exc:
            request['failure']=getattr(exc,'code',type(exc).__name__)
            raise
        finally:
            request['usage']=dict(cl.last_usage)
    cl._perform_request=observed
    return cl


def corpus_only_client():
    """No-request client for proving local vectors exist before authorization."""
    class Local:
        mode='live'
        base='https://api.metisai.ir/openai/v1'
        def _request(self,*args,**kwargs):
            raise AssertionError('Offline preflight must never contact a model endpoint.')
    return Local()


def preflight():
    manifest=read_json(DATA/'manifest.json')
    for name,expected in manifest['files'].items():
        assert sha(DATA/name)==expected
    pricing=read_json(DATA/'pricing.json')['models']
    rates={row['model']:row for row in pricing}
    os.environ.update(METIS_EMBEDDING_MODEL=EMBEDDING_MODEL,
        CASEPILOT_EMBEDDING_USD_PER_MILLION=str(rates[EMBEDDING_MODEL]['input_usd_per_million']),
        CASEPILOT_INDEX_FORMAT='v2')
    cache_info={}
    for version in ('v2','v3'):
        h=HybridRetriever(corpus_only_client(),ROOT/('data/corpus_'+version+'.json'))
        vectors=h.cache.get_many([embedding_text(row) for row in h.chunks],allow_create=False)
        assert len(vectors)==len(h.chunks) and all(len(v)==1536 and all(math.isfinite(x) for x in v) for v in vectors)
        cache_info[version]={'rows':len(vectors),'dimensions':1536,'cache_only':True,
            'index_namespace':h.index_namespace,'identity':h.cache.embedder.identity}
    check_provider_schema(QUALITY_EXTRACTION);check_provider_schema(RERANK)
    for case in read_json(DATA/'dev_inputs.json')+read_json(DATA/'holdout_inputs.json'):
        state={'id':case['id'],'revision':1,'facts':case['initial_facts'],
            'messages':[{'role':'user','text':case['initial_message']}]}
        check_provider_schema(selection_schema(state,{},[]))
    result={'active_hash':active_hash(),'cached_vectors':cache_info,'provider_requests':0,
        'corpus_embedding_requests':0,'suite_manifest_sha256':sha(DATA/'manifest.json'),
        'offline_tests':None}
    test=subprocess.run([sys.executable,'-X','utf8','-m','unittest','discover','-s','tests'],
        cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    result['offline_tests']={'passed':test.returncode==0,'exit_code':test.returncode,
        'output_tail':(test.stdout+'\n'+test.stderr)[-6000:]}
    require(test.returncode==0,'offline_preflight_failed','آزمون آفلاین برای این hash کد نگذشت؛ ارزیابی واقعی متوقف شد.')
    write_json(RUN/'preflight.json',result)
    print('Preflight passed: cached v2/v3 vectors and offline tests verified; 0 provider requests.')


def snapshot(label):
    target=RUN/'code_versions'/label
    if target.exists():
        saved=read_json(target/'manifest.json')
        require(saved['active_hash']==active_hash(),'snapshot_code_changed','برای کد جدید نام snapshot تازه لازم است.')
        for relative,expected in saved['files'].items():
            require(sha(ROOT/relative)==expected,'snapshot_integrity_error','فایل کد با snapshot منجمد فرق دارد.')
        return saved['active_hash']
    saved_files={}
    for folder in ('src','schemas','policies','scripts','tests'):
        for file in (ROOT/folder).rglob('*'):
            if not file.is_file() or '__pycache__' in file.parts:continue
            relative=file.relative_to(ROOT);target_file=target/relative
            target_file.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target_file)
            saved_files[str(relative)]=sha(file)
    value=active_hash()
    write_json(target/'manifest.json',{'active_hash':value,'files':saved_files,
        'provider_requests':0,'input_manifest_sha256':sha(DATA/'manifest.json')})
    return value


class NoCorpusEmbeddingHybrid(HybridRetriever):
    def search(self,*args,**kwargs):
        rows=super().search(*args,**kwargs)
        self.observed_candidates=copy.deepcopy(rows)
        return rows

    def load_vectors(self):
        if self.vectors is None:
            self.vectors=self.cache.get_many([embedding_text(row) for row in self.chunks],allow_create=False)
        return self.vectors


def run_one(cl,case,variant,index,stem,code,split,round_number,retry_of=None):
    usage_start=len(cl.usage_history);audit_start=len(cl.audit);output=None;failure=None;started=time.perf_counter()
    store=Store(ROOT/('runtime/quality_v28_remaining/'+stem+'.sqlite3'))
    hybrid=NoCorpusEmbeddingHybrid(cl,ROOT/('data/corpus_'+index+'.json'))
    agent=Agent(store,client=cl,hybrid=hybrid,components={'parent_context':False,'context_tokens':3000,'rewrite':False})
    import casepilot.pipeline as product_pipeline
    original_pack=product_pipeline.pack_evidence
    selected_context=[];packing_trace={}
    def capture_pack(*args,**kwargs):
        nonlocal selected_context,packing_trace
        selected_context,packing_trace=original_pack(*args,**kwargs)
        selected_context=copy.deepcopy(selected_context)
        return selected_context,packing_trace
    previous_scope=getattr(cl,'turn_scope',None)
    turn_scope={'calls_before':cl.calls,'max_calls':MAX_REQUESTS_PER_TURN,
        'deadline':time.monotonic()+MAX_TURN_SECONDS,'cap_usd':TURN_COST_CAP_USD,
        'cost_before':cl.budget.report()['charged_or_reserved_usd']}
    cl.turn_scope=turn_scope
    try:
        with patch('casepilot.store.utcnow',return_value='2026-10-10T00:00:00+00:00'), \
                patch('casepilot.pipeline.pack_evidence',side_effect=capture_pack):
            output=agent.turn('V28R_'+case['id'],case['initial_message'],'product-eval',
                case['initial_facts'],case['initial_checks'])
    except Exception as exc:
        failure=getattr(exc,'code',type(exc).__name__)
    finally:
        cl.turn_scope=previous_scope
    turn_usage=cl.usage_history[usage_start:]
    turn_cost=cl.budget.report()['charged_or_reserved_usd']-turn_scope['cost_before']
    provider_requests=sum(int(row.get('provider_requests',0)) for row in turn_usage)
    if provider_requests>MAX_REQUESTS_PER_TURN or turn_cost>TURN_COST_CAP_USD+1e-9:
        failure='turn_budget_invariant_violation'
    record={'case_id':case['id'],'split':split,'round':round_number,'variant':variant,'index':index,
        'code_hash':code,'input_hash':digest(case),'output':output,'failure':failure,
        'actual_query':getattr(hybrid,'observed_query',None),'retrieval_kwargs':getattr(hybrid,'observed_kwargs',None),
        'retrieval_trace':hybrid.last_trace,'initial_candidates':getattr(hybrid,'observed_candidates',[]),
        'packed_context':selected_context,'packing':packing_trace,
        'state':store.get('V28R_'+case['id']) if output else None,
        'requests':cl.audit[audit_start:],'usage':turn_usage,
        'turn_accounting':{'provider_requests':provider_requests,
            'charged_or_reserved_usd':turn_cost,'request_cap':MAX_REQUESTS_PER_TURN,
            'cost_cap_usd':TURN_COST_CAP_USD,'within_cap':failure!='turn_budget_invariant_violation'},
        'elapsed_seconds':time.perf_counter()-started,'retry_of':retry_of,
        'human_review':None,'independent_review':None}
    write_json(RUN/'turns'/(stem+'.json'),record)
    write_json(RUN/'traces'/(stem+'.json'),store.traces())
    print(stem+': '+str(failure or (output or {}).get('validation_error') or 'reviewed'),flush=True)


def run_split(split,round_number,hypothesis=None):
    require(round_number in (0,1,2),'invalid_round','دو دور اصلاح توسعه مجاز است.')
    if split=='holdout':
        selection=read_json(RUN/'selection.json')
        require(selection['active_hash']==active_hash() and round_number==0,
            'holdout_code_unfrozen','کد holdout با نسخهٔ منتخب توسعه یکسان نیست.')
    elif round_number:
        require(bool(hypothesis),'missing_hypothesis','دور اصلاح به فرضیهٔ ثبت‌شده نیاز دارد.')
        prior=read_json(RUN/'code_versions'/('dev_r'+str(round_number-1))/'manifest.json')
        require(prior['active_hash']!=active_hash(),'blind_content_retry','بدون تغییر مؤثر کد تکرار محتوایی مجاز نیست.')
        write_json(RUN/('round_'+str(round_number)+'_hypothesis.json'),
            {'hypothesis':hypothesis,'previous_hash':prior['active_hash'],'active_hash':active_hash()})
    tests=read_json(RUN/'preflight.json')
    require(tests.get('offline_tests',{}).get('passed') and tests['active_hash']==active_hash(),'offline_preflight_required',
        'آزمون آفلاین برای همین hash کد لازم است.')
    run_label=split+'_r'+str(round_number);code=snapshot(run_label)
    cases=read_json(DATA/(split+'_inputs.json'));cl=new_client('holdout' if split=='holdout' else 'development')
    for case in cases:
        for variant,index in (('A','v2'),('B','v3')):
            stem=run_label+'_'+case['id']+'_'+variant;path=RUN/'turns'/(stem+'.json')
            if path.exists():
                saved=read_json(path)
                require(saved['code_hash']==code and saved['input_hash']==digest(case),
                    'existing_attempt_mismatch','اجرای قبلی را با همان ورودی/hash ادامه دهید.')
                continue
            marker=RUN/'started'/(stem+'.json')
            require(not marker.exists(),'interrupted_turn','علامت نوبت ناتمام باقی است؛ retry محتوا مجاز نیست.')
            attempts=list((RUN/'turns').glob('*.json')) if (RUN/'turns').exists() else []
            require(len(attempts)<MAX_ATTEMPTS,'campaign_turn_limit','سقف تلاش‌های محصول تمام شده است.')
            write_json(marker,{'code_hash':code,'input_hash':digest(case),'status':'started'})
            run_one(cl,case,variant,index,stem,code,split,round_number)
    accounting()


def retry(stem):
    original=read_json(RUN/'turns'/(stem+'.json'))
    error=original['failure'] or (original['output'] or {}).get('validation_error')
    require(error in ('provider_connection_error','provider_timeout'),'non_connection_retry',
        'تکرار فقط برای خطای اتصال/timeout مجاز است.')
    attempts=read_json(RUN/'connection_retries.json') if (RUN/'connection_retries.json').exists() else []
    require(len(attempts)<4 and stem not in [row['original'] for row in attempts],
        'connection_retry_limit','هر نوبت حداکثر یک retry؛ چهار retry کل مجاز است.')
    require(original['code_hash']==active_hash(),'retry_code_changed','کد تغییر کرده؛ فقط دور توسعهٔ منجمدشده قابل اجراست.')
    cases=read_json(DATA/(original['split']+'_inputs.json'))
    case=next(row for row in cases if row['id']==original['case_id'])
    retry_stem=stem+'_connection_retry';attempts.append({'original':stem,'retry':retry_stem})
    write_json(RUN/'connection_retries.json',attempts)
    write_json(RUN/'started'/(retry_stem+'.json'),{'code_hash':active_hash(),
        'input_hash':digest(case),'status':'connection_retry'})
    phase='connection_retry';cl=new_client(phase)
    run_one(cl,case,original['variant'],original['index'],retry_stem,active_hash(),
        original['split'],original['round'],stem)
    accounting()


def select(round_number,reason):
    require(round_number in (0,1,2) and bool(reason),'invalid_selection','نسخه باید با دلیل انتخاب شود.')
    selected=RUN/'selection.json'
    require(not selected.exists(),'selection_frozen','انتخاب توسعه قبلاً منجمد شده است.')
    snapshot_path=RUN/'code_versions'/('dev_r'+str(round_number))/'manifest.json'
    saved=read_json(snapshot_path)
    require(saved['active_hash']==active_hash(),'selection_code_changed','کد با snapshot توسعه متفاوت است.')
    tests=read_json(RUN/'preflight.json')
    require(tests.get('offline_tests',{}).get('passed') and tests['active_hash']==active_hash(),'offline_preflight_required',
        'آزمون آفلاین برای کد منتخب لازم است.')
    paths=[path for path in (RUN/'turns').glob('dev_r'+str(round_number)+'_*.json')
        if not path.name.endswith('_connection_retry.json')]
    require(len(paths)==6,'incomplete_development','هر سه پرونده با دو index باید کامل باشند.')
    write_json(selected,{'development_round':round_number,'active_hash':active_hash(),
        'reason':reason,'dev_artifacts':{path.name:sha(path) for path in paths},
        'holdout_manifest_sha256':sha(DATA/'manifest.json'),'default_changed':False})
    print('کد توسعه انتخاب و پیش از holdout منجمد شد؛ پیش‌فرض تغییر نکرد.')


def accounting():
    auth=verify();budget=FollowupBudget(ROOT/'runtime/team_budget.sqlite3',auth,'development')
    with budget.db() as db:
        rows=db.execute('SELECT c.charged,c.status,m.phase,c.kind FROM calls c JOIN completion_calls m ON c.id=m.id WHERE m.campaign=?',(auth['campaign'],)).fetchall()
    confirmed=sum(row[0] for row in rows if row[1]=='confirmed')
    unknown=sum(row[0] for row in rows if row[1]!='confirmed')
    spent=confirmed+unknown
    report={'requests':len(rows),'query_embedding_requests':sum(row[3]=='embedding' for row in rows),
        'corpus_embedding_requests':0,'confirmed_usd':confirmed,'unknown_reserved_usd':unknown,
        'charged_or_reserved_usd':spent,'hard_cap_usd':HARD_CAP_USD,
        'historical_before':auth['cost_before'],
        'by_phase':{phase:{'requests':sum(row[2]==phase for row in rows),
            'confirmed_usd':sum(row[0] for row in rows if row[2]==phase and row[1]=='confirmed'),
            'unknown_reserved_usd':sum(row[0] for row in rows if row[2]==phase and row[1]!='confirmed')}
            for phase in ('development','holdout','connection_retry')}}
    require(len(rows)<=MAX_PROVIDER_REQUESTS and spent<=HARD_CAP_USD,
        'campaign_limit_violation','دفتر واقعی از سقف درخواست/هزینه فراتر رفته است.')
    write_json(RUN/'accounting.json',report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['preflight','dev','holdout','retry','select','accounting'])
    parser.add_argument('--round',type=int,default=0);parser.add_argument('--hypothesis')
    parser.add_argument('--stem');parser.add_argument('--reason')
    args=parser.parse_args()
    if args.phase=='preflight':preflight()
    elif args.phase=='dev':run_split('dev',args.round,args.hypothesis)
    elif args.phase=='holdout':run_split('holdout',0)
    elif args.phase=='retry':retry(args.stem)
    elif args.phase=='select':select(args.round,args.reason)
    else:accounting()
