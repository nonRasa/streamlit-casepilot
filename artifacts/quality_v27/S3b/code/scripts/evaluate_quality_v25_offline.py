"""مقایسهٔ کنترل‌های توسعه روی کدهای واقعی مبنا و اصلاح؛ بدون مدل و هزینه."""
import argparse,copy,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CAMPAIGN=ROOT/'artifacts/quality_v25';BASE=CAMPAIGN

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build():
    sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
    from test_quality_v25 import state,judge,technical,FeatureControls
    from test_quality_v23 import answer
    from casepilot.review_contract import review_spans
    controls=[]
    def add(name,a,s,ev,r,env,expected,category,retention=False):
        controls.append({'name':name,'answer':copy.deepcopy(a),'state':s,'evidence':ev,'judge':r,'envelope':env,
            'expected':expected,'category':category,'retention':retention,'label_source':'ساختهٔ دستیار، غیرمستقل، توسعه'})
    a=answer();s=state();env,r=judge(a,s);add('safe_question',a,s,[],r,env,'accept','useful')
    for name,text,claim in [('direct_document','The button target width is 24px.','توضیح: عرض هدف دکمه ۲۴ px است.'),
        ('dialog_example','@st.dialog("My dialog")\ndef show_dialog():\n    st.write("dialog content")','توضیح: بازاجرا باعث از دست رفتن واکنش دیالوگ می‌شود.'),
        ('import_example','```python\nimport streamlit as st','توضیح: بازاجرا باعث از دست رفتن واکنش دیالوگ می‌شود.'),
        ('library_mention','`st.dataframe` uses glide-data-grid under the hood.','توضیح: اندازهٔ دکمه‌ها ۲۴ px و دسترس‌پذیری کافی است.')]:
        a=answer();a['rationale']=claim;ev=[{'id':'doc','text':text,'product_version':'1.64.0'}];a['claims']=[{'evidence_id':'doc','quote':text}]
        env,r=technical(a,s,ev);add(name,a,s,ev,r,env,'accept' if name=='direct_document' else 'reject','useful' if name=='direct_document' else 'citation')
    for cid in ('GH16481','GH17133'):
        a,s=FeatureControls().proposal(cid);env,r=judge(a,s)
        add('feature_'+cid,a,s,[],r,env,'accept','useful')
    a,s=FeatureControls().proposal('GH16481');env,r=judge(a,s)
    next(e for e,u in zip(r['unit_reviews'],env['units']) if u['field']=='feature_proposal.constraints')['support']='partial'
    add('retain_feature_unknown_constraint',a,s,[],r,env,'reject','retention',True)
    a=answer();s=state();env,r=judge(a,s);r['unit_reviews'][0].update(premise=True)
    r['unit_reviews'][0]['meaning'].update(act='technical',assertion_text=a['question'])
    add('unsupported_premise',a,s,[],r,env,'reject','negative')
    for kind in ('stale','wrong_namespace','forged_quote'):
        env,r=judge(a,s)
        if kind=='stale':r['draft_version']='old'
        if kind=='wrong_namespace':r['unit_reviews'][0]['source_ids']=[review_spans(s,[])['messages'][0]['span_id']]
        if kind=='forged_quote':r['unit_reviews'][0].update(kind='reported_fact',support='supported');r['unit_reviews'][0]['meaning']['user_quote']='never in report'
        add(kind,a,s,[],r,env,'contract_error' if kind!='forged_quote' else 'reject','negative')
    env,r=judge(a,s);r['novelty'].update(status='repeated',relation='answers_requested_detail',message_ids=[review_spans(s,[])['messages'][0]['span_id']])
    add('repeated_question',a,s,[],r,env,'reject','negative')
    write(BASE/'offline_controls.json',{'mode':'synthetic_control_with_seen_report_context','independent':False,'human':False,'controls':controls})

def worker(variant):
    source=CAMPAIGN/'baseline/src' if variant=='previous' else ROOT/'src';sys.path.insert(0,str(source))
    from casepilot.review_contract import checked_review_v23,recompose,draft_units,review_spans
    from casepilot.common import CasePilotError
    if variant=='revised':from casepilot.semantics import checked_semantic_review,recompose_semantic
    results=[];start=time.perf_counter()
    for c in json.loads((BASE/'offline_controls.json').read_text(encoding='utf-8'))['controls']:
        raw=copy.deepcopy(c['judge']);a=c['answer'];s=c['state'];ev=c['evidence'];env=c['envelope']
        if variant=='previous':
            for e in raw['unit_reviews']:e.pop('meaning')
        try:
            out=(checked_review_v23 if variant=='previous' else checked_semantic_review)(raw,a,ev,s,env)
            result={'outcome':'accept' if out['verdict']=='accept' else 'reject','review':out,'retained_final':None}
            if c['retention']:
                combined=(recompose(a,out,env,s) if variant=='previous' else recompose_semantic(a,out,env,s))
                result['retained_final']=combined
                if combined:
                    # داوری دوم بدل صریح با شناسهٔ تازه است، نه خروجی مدل واقعی.
                    env2=draft_units(combined,s['id'],s['revision'],1);r2=copy.deepcopy(raw);r2['draft_version']=env2['draft_version'];r2['unit_reviews']=[]
                    spans=review_spans(s,[],[])
                    for u in env2['units']:
                        unknown=u['text'].startswith('نامعلوم:');feature=u['field'].startswith('feature_proposal.')
                        e={'unit_id':u['unit_id'],'kind':'request_summary' if feature else 'next_step','support':'supported' if feature and not unknown else 'unknown',
                           'source_ids':[],'message_ids':[spans['messages'][0]['span_id']] if feature and not unknown else [],'premise':False,'standalone':True,
                           'reason':'توضیح: بدل ترکیب تازه است.','version_dependent':False,'version_limit':''}
                        if variant=='revised':e['meaning']={'act':'unknown' if unknown else ('request' if feature else 'procedure'),'assertion_text':'',
                            'user_quote':spans['messages'][0]['text'][:150] if feature and not unknown else '', 'depends_on':[]}
                        r2['unit_reviews'].append(e)
                    second=(checked_review_v23 if variant=='previous' else checked_semantic_review)(r2,combined,[],s,env2)
                    result['retention_rechecked']=second['verdict']=='accept'
        except CasePilotError as exc:result={'outcome':'contract_error','error':exc.code,'retained_final':None}
        results.append(dict(result,name=c['name'],expected=c['expected'],category=c['category']))
    write(BASE/(variant+'_offline.json'),{'variant':variant,'results':results,'calls':0,'provider_requests':0,'cost_usd':0,'elapsed_seconds':time.perf_counter()-start})

def main():
    global BASE
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['previous','revised']);p.add_argument('--label',default='');args=p.parse_args()
    if args.label:
        if not args.label.replace('_','').isalnum():raise SystemExit('توقف: نام پوشهٔ ارزیابی معتبر نیست.')
        BASE=CAMPAIGN/args.label
    if args.worker:worker(args.worker);return
    if (BASE/'offline_controls.json').exists():raise SystemExit('توقف: کنترل‌های ثبت‌شده بازنویسی نمی‌شوند.')
    build()
    for variant in ('previous','revised'):subprocess.run([sys.executable,'-X','utf8',__file__,'--worker',variant,'--label',args.label],cwd=ROOT,check=True)
    rows={v:json.loads((BASE/(v+'_offline.json')).read_text(encoding='utf-8')) for v in ('previous','revised')}
    metrics={}
    def count(n,d,unit,unknown=0,na=0):return {'numerator':n,'denominator':d,'unit':unit,'unknown':unknown,'not_applicable':na}
    for v,group in rows.items():
        rs=group['results'];positive=[r for r in rs if r['category']=='useful'];negative=[r for r in rs if r['category'] in ('negative','citation')];citation=[r for r in rs if r['category']=='citation']
        metrics[v]={'false_rejection_valid_control':count(sum(r['outcome']!='accept' for r in positive),len(positive),'control'),
            'unsafe_acceptance':count(sum(r['outcome']=='accept' for r in negative),len(negative),'negative_control'),
            'irrelevant_citation_accepted':count(sum(r['outcome']=='accept' for r in citation),len(citation),'source_claim_link'),
            'retention_after_recheck':count(sum(r.get('retention_rechecked',False) for r in rs),sum(r['category']=='retention' for r in rs),'recomposed_feature'),
            'calls':count(0,len(rs),'provider_request_per_control'),'cost_usd':count(0,len(rs),'USD_per_control'),'elapsed_seconds':group['elapsed_seconds']}
    gate=metrics['revised']['retention_after_recheck']['numerator']>metrics['previous']['retention_after_recheck']['numerator'] and metrics['revised']['unsafe_acceptance']['numerator']<=metrics['previous']['unsafe_acceptance']['numerator'] and metrics['revised']['false_rejection_valid_control']['numerator']<=metrics['previous']['false_rejection_valid_control']['numerator']
    write(BASE/'offline_metrics.json',{'evaluation':'کنترل و بدل توسعهٔ ساختهٔ دستیار؛ مدل تازه یا حقیقت مستقل نیست','metrics':metrics,'live_gate_passed':gate})
    print(json.dumps({'metrics':metrics,'live_gate_passed':gate},ensure_ascii=False))

if __name__=='__main__':main()
