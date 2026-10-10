"""Fixed-draft judge campaign. Preflight is offline; live phases require fresh approval."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'artifacts/quality_v28_semantic_judge'
DATA=ROOT/'eval/quality_v28_semantic_judge/suite_v3'
# Baseline must use the saved implementation in a fresh process, not a mixture.
BASELINE='--baseline' in sys.argv
sys.path[:0]=[str(RUN/'baseline/src' if BASELINE else ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import canonical,digest,require,CasePilotError
from casepilot.compact_review import packet,descriptive_schema,descriptive_decode,DESCRIPTIVE_PROMPT
from casepilot.review_contract import draft_units,review_spans
from casepilot.semantics import checked_semantic_review
from casepilot.case_type import response_policy
from casepilot.schema_preflight import check_provider_schema
from casepilot.tokenization import count_tokens

MODEL='gpt-4.1-mini'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,obj):
    require(not path.exists(),'artifact_exists','اثر قبلی بازنویسی نمی‌شود.')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verify_suite():
    manifest=read(DATA/'manifest.json')
    for name,h in manifest['files'].items():require(sha(DATA/name)==h,'suite_changed','مجموعهٔ منجمد تغییر کرده است.')
    return manifest


def implementation_hash():
    source=RUN/'baseline/src' if BASELINE else ROOT/'src'
    return digest({str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*.py'))})


def build_request(case,presentation='baseline',instructions='baseline'):
    answer=deepcopy(case['answer']);state=deepcopy(case['state']);evidence=deepcopy(case['evidence'])
    envelope=draft_units(answer,state['id'],state['revision'],0,include_quotes=True)
    spans=review_spans(state,evidence,answer['claims'],report_quotes=(answer.get('feature_proposal') or {}).get('report_quotes',[]))
    bound,public=packet(envelope,spans)
    prompt=DESCRIPTIVE_PROMPT
    if presentation!='baseline':
        from casepilot.judge_presentation import inline_evidence
        public=inline_evidence(public,bound)
    if instructions!='baseline':
        from casepilot.judge_presentation import PROVENANCE_PROMPT
        prompt+=PROVENANCE_PROMPT
    jp={'facts':state['facts'],'experiments':state['experiments'],'completed_checks':state['checks'],
        'response_policy':response_policy(state,evidence),'history_complete':True,
        'decision':answer['decision'],'citations':answer['claims'],'spans':spans,'draft':envelope,'compact_contract':public}
    schema=descriptive_schema(bound);check_provider_schema(schema)
    payload={'model':MODEL,'messages':[{'role':'system','content':prompt},{'role':'user','content':canonical(jp)}],
        'max_tokens':2000,'response_format':{'type':'json_schema','json_schema':{'name':'casepilot_judge','strict':True,'schema':schema}}}
    encoded=canonical(payload).encode('utf-8')
    require(len(encoded)<=45000,'context_limit','بستهٔ داوری از سقف محصول بیشتر است.')
    tokens=count_tokens(canonical(payload),encoding='o200k_base')+128
    reservation=((len(encoded)+500)*.44+2000*1.76)*1.2/1e6
    return {'payload':payload,'packet':jp,'bound':bound,'envelope':envelope,
        'input_tokens':tokens,'bytes':len(encoded),'reservation_usd':reservation}


def assess(raw,built,case):
    try:
        decoded=descriptive_decode(raw,built['bound'])
    except CasePilotError as exc:
        return {'contract_valid':False,'contract_error':exc.code,'semantic_result':None,'guard':None}
    try:
        guard=checked_semantic_review(decoded,case['answer'],case['evidence'],case['state'],built['envelope'])
    except CasePilotError as exc:
        return {'contract_valid':True,'guard_contract_error':exc.code,'semantic_result':decoded,'guard':None}
    return {'contract_valid':True,'semantic_result':decoded,'guard':guard,
        'raw_accept_with_invalid_units':raw.get('verdict')=='accept' and
            len(guard.get('valid_unit_ids',[]))!=len(built['envelope']['units'])}


def preflight():
    verify_suite();reports=[]
    for split in ('dev','holdout'):
        for case in read(DATA/(split+'_inputs.json')):
            variants=[('baseline','baseline')] if BASELINE else [('baseline','baseline'),('inline-evidence-v1','baseline'),('inline-evidence-v1','provenance-v1')]
            for pres,instr in variants:
                built=build_request(case,pres,instr)
                reports.append({'id':case['id'],'presentation':pres,'instructions':instr,
                    'input_tokens':built['input_tokens'],'bytes':built['bytes'],'reservation_usd':built['reservation_usd']})
    result={'implementation_hash':implementation_hash(),'baseline':BASELINE,
        'suite_manifest_sha256':sha(DATA/'manifest.json'),'provider_requests':0,'api_cost_usd':0,
        'requests':reports,'max_input_tokens':max(r['input_tokens'] for r in reports),
        'max_reservation_usd':max(r['reservation_usd'] for r in reports)}
    target=RUN/'preflights'/(implementation_hash()+'.json')
    if target.exists():require(read(target)==result,'preflight_changed','پیش‌بررسی با همان شناسه تغییر کرده است.')
    else:write(target,result)
    print('Offline preflight:',len(reports),'packets; max input tokens',result['max_input_tokens'],'max reservation',result['max_reservation_usd'])
    return result


def authorization():
    require((RUN/'authorization.json').exists(),'budget_not_approved','این مرحله مجوز بودجهٔ تازه ندارد.')
    auth=read(RUN/'authorization.json');protocol=read(DATA/'protocol.json')
    amendment=read(RUN/'suite_repair.json') if (RUN/'suite_repair.json').exists() else auth
    require(auth.get('human_approval')=='approved' and amendment.get('manifest_sha256')==sha(DATA/'manifest.json') and
        amendment.get('protocol_sha256')==sha(DATA/'protocol.json') and auth.get('model')==MODEL and
        auth.get('hard_cap_usd')==protocol['hard_cap_usd'] and auth.get('max_requests')==protocol['max_requests'],
        'invalid_budget','مجوز با دامنهٔ این مرحله منطبق نیست.')
    require(auth['phase_limits']=={**protocol['phases'],'connection_retry':protocol['connection_retries']},
            'invalid_budget','سقف فازها تغییر کرده است.')
    verify_suite()
    return auth


def live(phase,presentation,instructions,hypothesis):
    auth=authorization();protocol=read(DATA/'protocol.json')
    if phase=='baseline':require(BASELINE and presentation==instructions=='baseline','baseline_changed','مبنای منجمد لازم است.')
    elif phase=='correction_1':require(BASELINE and presentation==instructions=='baseline',
        'wrong_implementation','این دور به اصلاح fixture و سنجش دوبارهٔ مبنا اختصاص دارد.')
    else:require(not BASELINE,'wrong_implementation','فاز اصلاح داور نباید کد مبنا را بار کند.')
    if phase.startswith('correction'):
        require(bool(hypothesis.strip()),'missing_hypothesis','فرضیهٔ اصلاح لازم است.')
        previous='baseline' if phase=='correction_1' else 'correction_1'
        require((RUN/'phases'/previous/'manifest.json').exists(),'phase_order','مرحلهٔ قبلی باید کامل ثبت شود.')
    if phase=='holdout':
        require((RUN/'selection.json').exists(),'unselected','نسخه باید پیش از holdout انتخاب شود.')
        selected=read(RUN/'selection.json')
        require(selected['implementation_hash']==implementation_hash() and selected['presentation']==presentation and selected['instructions']==instructions,
            'selection_mismatch','کد یا گزینه‌ها با نسخهٔ منتخب یکسان نیستند.')
    preflight_path=RUN/'preflights'/(implementation_hash()+'.json')
    require(preflight_path.exists() and read(preflight_path)['implementation_hash']==implementation_hash(),
        'preflight_required','preflight این نسخه لازم است.')
    from casepilot.model import MetisClient
    from complete_quality_v27 import CampaignBudget
    from evaluate_quality_v27_live import credentials
    class JudgeBudget(CampaignBudget):
        def reserve(self,amount,model,kind='judge'):
            require(kind=='judge' and model==MODEL and amount<=protocol['request_cap_usd'],
                'unauthorized_call','فقط داوری با سقف هر درخواست مجاز است.')
            return super().reserve(amount,model,kind)
    os.environ.update(METIS_MODEL=MODEL,METIS_JUDGE_MODEL=MODEL,METIS_BASE_URL='https://api.metisai.ir/openai/v1',
        CASEPILOT_INPUT_USD_PER_MILLION='.44',CASEPILOT_OUTPUT_USD_PER_MILLION='1.76',
        CASEPILOT_MAX_OUTPUT_TOKENS='2000',CASEPILOT_BUDGET_DB=str(ROOT/'runtime/team_budget.sqlite3'),
        CASEPILOT_BUDGET_USD=str(min(5,auth['cost_before']['charged_or_reserved_usd']+auth['hard_cap_usd'])))
    credentials();client=MetisClient();client.budget=JudgeBudget(client.budget.path,auth,phase)
    client.cache=ROOT/'runtime/quality_v28_semantic_judge/cache';client.cache.mkdir(parents=True,exist_ok=True)
    client.diagnostics=ROOT/'runtime/quality_v28_semantic_judge/diagnostics'
    split='holdout' if phase=='holdout' else 'dev';cases=read(DATA/(split+'_inputs.json'))
    phase_dir=RUN/'phases'/phase
    require(not (phase_dir/'manifest.json').exists(),'phase_complete','فاز تکمیل‌شده تکرار نمی‌شود.')
    snapshot=phase_dir/'src'
    if not snapshot.exists():
        shutil.copytree(RUN/'baseline/src' if BASELINE else ROOT/'src',snapshot,ignore=shutil.ignore_patterns('__pycache__'))
    results=[]
    for case in cases:
        path=phase_dir/(case['id']+'.json')
        if path.exists():
            saved=read(path)
            require(saved['implementation_hash']==implementation_hash() and saved['presentation']==presentation and saved['instructions']==instructions,
                'resume_mismatch','اثر قبلی متعلق به تنظیمات دیگری است.')
            results.append(path.name);continue
        built=build_request(case,presentation,instructions)
        started=time.monotonic();raw=None;failure=None;checked=None
        before=client.budget.report()['charged_or_reserved_usd']
        try:
            raw=client._request(built['payload'],kind='judge',input_rate=.44,output_rate=1.76)
            checked=assess(raw,built,case)
        except CasePilotError as exc:failure=exc.code
        record={'id':case['id'],'phase':phase,'input_sha256':digest(case),
            'implementation_hash':implementation_hash(),'presentation':presentation,'instructions':instructions,
            'suite_manifest_sha256':sha(DATA/'manifest.json'),'payload':built['payload'],
            'payload_sha256':digest(built['payload']),'raw_model_reply':raw,'failure':failure,
            'assessment':checked,'usage':deepcopy(client.last_usage),'elapsed_seconds':time.monotonic()-started,
            'charged_or_reserved_usd':client.budget.report()['charged_or_reserved_usd']-before}
        write(path,record);results.append(path.name)
        if failure in ('budget_exhausted','campaign_request_limit','unauthorized_call'):break
    write(phase_dir/'manifest.json',{'implementation_hash':implementation_hash(),
        'presentation':presentation,'instructions':instructions,'hypothesis':hypothesis,
        'results':{name:sha(phase_dir/name) for name in results},'complete':len(results)==len(cases)})
    print('Stored phase',phase,'results',len(results),'without generation or embeddings.')


def select(phase,reason):
    require(phase in ('correction_1','correction_2'),'invalid_selection','نسخهٔ توسعه لازم است.')
    require(not (RUN/'phases/holdout').exists(),'holdout_opened','پس از بازکردن holdout انتخاب جدید مجاز نیست.')
    manifest=read(RUN/'phases'/phase/'manifest.json')
    checkpoint=read(RUN/'offline_guard_checkpoint.json') if (RUN/'offline_guard_checkpoint.json').exists() else None
    same=manifest['implementation_hash']==implementation_hash()
    guarded=bool(checkpoint and checkpoint.get('implementation_hash')==implementation_hash() and
        checkpoint.get('development_phase')==phase and checkpoint.get('tests_passed') and
        checkpoint.get('guard_replay_sha256')==sha(RUN/'guard_replays'/(''+phase+'.json')))
    require(manifest['complete'] and (same or guarded),'selection_mismatch','نسخهٔ جاری باید همان نسخهٔ توسعه یا سخت‌گیری آفلاین ثبت‌شده باشد.')
    require(bool(reason.strip()),'missing_selection_reason','علت انتخاب لازم است.')
    write(RUN/'selection.json',{**manifest,'implementation_hash':implementation_hash(),
        'development_implementation_hash':manifest['implementation_hash'],'offline_guard_checkpoint':checkpoint,
        'phase':phase,'reason':reason,'reference_status':'provisional unless independent review completed'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['preflight','run','select'])
    p.add_argument('--baseline',action='store_true');p.add_argument('--phase',default='baseline',choices=['baseline','correction_1','correction_2','holdout'])
    p.add_argument('--presentation',choices=['baseline','inline-evidence-v1'],default='baseline')
    p.add_argument('--instructions',choices=['baseline','provenance-v1'],default='baseline')
    p.add_argument('--hypothesis',default='');p.add_argument('--reason',default='')
    a=p.parse_args()
    if a.command=='preflight':preflight()
    elif a.command=='select':select(a.phase,a.reason)
    else:live(a.phase,a.presentation,a.instructions,a.hypothesis)
