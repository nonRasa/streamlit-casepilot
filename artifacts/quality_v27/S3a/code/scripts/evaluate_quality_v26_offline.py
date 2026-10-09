"""مقایسهٔ بدون هزینه روی کپی واقعی مبنا؛ شمارش قالب، نه اثبات صحت مدل."""
import argparse,copy,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/quality_v26'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def worker(variant):
    sys.path.insert(0,str(BASE/'baseline/src' if variant=='previous' else ROOT/'src'))
    from casepilot.common import CasePilotError
    from casepilot.semantics import checked_semantic_review
    if variant=='revised':
        from casepilot.compact_review import contract,encode_fixture,decode
        from casepilot.review_contract import review_spans
    results=[];start=time.perf_counter()
    for c in read(ROOT/'artifacts/quality_v25/offline_comparison_02/offline_controls.json')['controls']:
        a,s,ev,env,r=copy.deepcopy([c[k] for k in ('answer','state','evidence','envelope','judge')])
        try:
            if variant=='revised':
                codec=contract(env,review_spans(s,ev,a['claims']));r=decode(encode_fixture(r,codec),codec)
            out=checked_semantic_review(r,a,ev,s,env)
            row={'outcome':'accept' if out['verdict']=='accept' else 'reject','covered_units':len(out['unit_reviews']), 'required_units':len(env['units'])}
        except (CasePilotError,KeyError):row={'outcome':'contract_error','covered_units':None,'required_units':len(env['units'])}
        results.append(dict(row,name=c['name'],category=c['category'],expected=c['expected']))
    write(BASE/(variant+'_offline.json'),{'results':results,'elapsed_seconds':time.perf_counter()-start,'provider_requests':0,'cost_usd':0})

def capacity():
    sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT/'runtime/quality_v26/tokenizer')]
    import tiktoken
    from casepilot.common import canonical
    from casepilot.compact_review import contract,encode_fixture,decode,packet,schema,PROMPT
    from casepilot.review_contract import review_spans
    from casepilot.semantics import semantic_schema
    from casepilot.roles import SEMANTIC_JUDGE_PROMPT
    import test_quality_v25 as v25
    from test_quality_v23 import answer
    from casepilot.model import quote_candidates,resolve_claims
    enc=tiktoken.encoding_for_model('gpt-4.1-mini')
    def count(x):return len(enc.encode(canonical(x),disallowed_special=()))
    samples=[]
    a=answer();s=v25.state();env,r=v25.judge(a,s);samples.append(('low_3',a,s,[],env,r))
    p=next(p for p in read(ROOT/'artifacts/quality_v25/live_comparison_01/ai_review_packets.json')['packets'] if p['variant']=='revised')
    raw=next(x['raw_answer'] for x in p['raw_role_outputs'] if x['kind']=='chat');ev=p['retrieved_sources']
    lookup={(e['id'],q['quote_id']):q['text'] for e in ev for q in quote_candidates(e['text'])}
    a=resolve_claims(raw,lookup);s={'id':p['id'],'revision':1,'facts':p['result']['output']['summary']['facts'],'messages':[{'role':'user','text':p['initial_report']}], 'investigation_plan':{'intent':'bug'}}
    env=copy.deepcopy(p['result']['output']['reviewed_draft']);_,r=v25.judge(a,s,ev)
    assert [u['text'] for u in env['units']]==[u['text'] for u in v25.judge(a,s,ev)[0]['units']]
    r['draft_version']=env['draft_version']
    for e,u in zip(r['unit_reviews'],env['units']):e['unit_id']=u['unit_id']
    samples.append(('actual_failed_draft_8',a,s,ev,env,r))
    a,s=v25.FeatureControls().proposal('GH16481');a['decision']='ask';a['question']='پرسش: کدام شرط پذیرش هنوز نامعلوم است؟';a['hypotheses']=['فرضیه: این برداشت هنوز تأیید نشده است.']*3
    env,r=v25.judge(a,s);samples.append(('maximum_11',a,s,[],env,r))
    metrics=[]
    for name,a,s,ev,env,r in samples:
        spans=review_spans(s,ev,a['claims']);c,public=packet(env,spans);wire=encode_fixture(r,c);decoded=decode(wire,c)
        old=dict(r,unit_reviews={e['unit_id']:{k:v for k,v in e.items() if k!='unit_id'} for e in r['unit_reviews']})
        jp={'facts':s['facts'],'decision':a['decision'],'citations':a['claims'],'spans':spans,'draft':env}
        before_payload={'system':SEMANTIC_JUDGE_PROMPT,'packet':jp,'schema':semantic_schema(env,spans)}
        after_payload={'system':PROMPT,'packet':dict(jp,compact_contract=public),'schema':schema(c)}
        record={'name':name,'units':len(env['units']),'input_before':{'utf8_bytes':len(canonical(before_payload).encode()),'local_tokens':count(before_payload)},
            'input_after':{'utf8_bytes':len(canonical(after_payload).encode()),'local_tokens':count(after_payload)},
            'output_before':{'utf8_bytes':len(canonical(old).encode()),'local_tokens':count(old)},
            'output_after':{'utf8_bytes':len(canonical(wire).encode()),'local_tokens':count(wire)},
            'byte_estimate_after_tokens':round(len(canonical(wire).encode())/3*1.3),
            'covered_units':len(decoded['unit_reviews']),'capacity_limit':1600,'actual_provider_output':False}
        record['token_reduction_fraction']=1-record['output_after']['local_tokens']/record['output_before']['local_tokens']
        metrics.append(record);write(BASE/'capacity_samples'/(name+'.json'),{'draft':env,'spans':spans,'old_synthetic_review':old,'compact_synthetic_review':wire,'decoded':decoded})
    write(BASE/'capacity.json',{'tokenizer':'tiktoken','version':tiktoken.__version__,'encoding':enc.name,'model_mapping':'encoding_for_model(gpt-4.1-mini)',
        'counts':'شمارش محلی رشتهٔ JSON؛ بدون سربار پیام یا تضمین قالب‌بندی/داوری مدل واقعی',
        'estimate_assumption':'برآورد جداگانه: سه بایت برای هر توکن و حاشیهٔ ۳۰ درصد؛ تضمین ظرفیت نیست',
        'samples':metrics,'maximum_validated_units':11,'maximum_generator_units':9,'required_unit_field_maximum':11,
        'repeat_removed':['long identifiers','rewritten assertion text','rewritten user quote','premise flag','successful criterion reasons'],
        'unknown':['raw invalid v25 judge output','v25 finish_reason','actual full model output size','provider schema overhead']})
    return metrics

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['previous','revised']);args=p.parse_args()
    if args.worker:worker(args.worker);return
    if (BASE/'offline_metrics.json').exists():raise SystemExit('توقف: ارزیابی ثبت‌شده بازنویسی نمی‌شود.')
    for v in ('previous','revised'):subprocess.run([sys.executable,'-X','utf8',__file__,'--worker',v],cwd=ROOT,check=True)
    metrics={}
    def ratio(n,d,unknown=0):return {'numerator':n,'denominator':d,'unknown':unknown}
    for v in ('previous','revised'):
        rs=read(BASE/(v+'_offline.json'))['results'];pos=[r for r in rs if r['category']=='useful'];neg=[r for r in rs if r['category'] in ('negative','citation')]
        metrics[v]={'valid_control_false_rejection':ratio(sum(r['outcome']!='accept' for r in pos),len(pos)),
            'negative_control_acceptance':ratio(sum(r['outcome']=='accept' for r in neg),len(neg)),
            'complete_processable_review':ratio(sum(r['covered_units']==r['required_units'] for r in rs if r.get('covered_units') is not None),len(rs))}
    cap=capacity();oldfit=sum(r['output_before']['local_tokens']<=1600 for r in cap);newfit=sum(r['output_after']['local_tokens']<=1600 for r in cap)
    metrics['capacity']={'previous_fit':ratio(oldfit,len(cap)),'revised_fit':ratio(newfit,len(cap)),
        'revised_full_coverage':ratio(sum(r['covered_units']==r['units'] for r in cap),len(cap))}
    gate=metrics['revised']['valid_control_false_rejection']['numerator']==0 and metrics['revised']['negative_control_acceptance']['numerator']==0 and newfit==len(cap) and newfit>oldfit and all(r['token_reduction_fraction']>=.25 for r in cap)
    write(BASE/'offline_metrics.json',{'evaluation':'کنترل توسعهٔ ساختهٔ دستیار؛ نه اجرای مدل تازه، نه بازبینی انسانی یا مستقل', 'metrics':metrics,'live_gate_passed':gate,
        'gate':'کاهش حداقل ۲۵ درصد در سه نمونه، افزایش تعداد قالب‌های کامل زیر ۱۶۰۰ توکن، صفر رد کنترل مثبت و صفر پذیرش کنترل منفی',
        'provider_requests':0,'cost_usd':0})
    print(json.dumps({'metrics':metrics,'capacity':cap,'live_gate_passed':gate},ensure_ascii=False))
if __name__=='__main__':main()
