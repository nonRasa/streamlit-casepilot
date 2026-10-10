"""Same semantic scenarios, explicit synthetic reviewer outputs for each contract.

This audits deterministic acceptance behavior, not live-model understanding.
"""
import copy,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/quality_v23'
def worker(variant):
    sys.path.insert(0,str(BASE/'baseline/src' if variant=='previous' else ROOT/'src'))
    from casepilot.common import CasePilotError
    from casepilot.review_contract import draft_units
    from casepilot.roles import CRITERIA
    if variant=='previous':from casepilot.review_contract import checked_review as check
    else:from casepilot.review_contract import checked_review_v23 as check,review_spans
    state={'id':'control','revision':1,'facts':{},'messages':[{'role':'user','text':'The UI fails. The example calls helper(), but its body is absent.'}]}
    evidence=[{'id':'doc1','text':'The helper returns a table containing the requested rows.', 'product_version':None}]
    names=['positive_supported','positive_focused','negative_unsupported','negative_report_escape','negative_premise','negative_forged','negative_wrong_namespace','negative_stale','negative_partial']
    outputs=[]
    for name in names:
        technical=name not in ('positive_focused','negative_report_escape','negative_premise')
        a={'decision':'ask','question':'پرسش: بدنهٔ تابع کمکی چیست؟','next_step':'اقدام: فقط بدنهٔ تابع کمکی را بفرستید.',
            'rationale':'توضیح: تابع جدولِ ردیف‌های خواسته‌شده را برمی‌گرداند.' if technical else 'اقدام: برای ادامه، بدنهٔ تابع کمکی لازم است.',
            'claims':[{'evidence_id':'doc1','quote':evidence[0]['text']}] if technical else [],'hypotheses':[]}
        if name=='negative_report_escape':a['rationale']='گزارش: استفاده از کتابخانه رفع مشکل را تضمین می‌کند.'
        if name=='negative_premise':a['question']='پرسش: چون علت مشکل کتابخانه است، آیا آن را عوض می‌کنید؟'
        env=draft_units(a,state['id'],1,0)
        r={'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: کنترل ساخته‌شده است؛ داوری مدل نیست.'} for k in CRITERIA},'draft_version':env['draft_version'],'unit_reviews':[]}
        if variant=='revised':spans=review_spans(state,evidence,a['claims'])
        for u in env['units']:
            claim=technical and u['field']=='rationale';reported=name=='negative_report_escape' and u['field']=='rationale'
            kind='technical_claim' if claim else ('reported_fact' if reported else ('question' if u['field']=='question' else 'next_step'))
            support='unknown' if name=='negative_unsupported' and claim else ('partial' if name=='negative_partial' and claim else ('supported' if claim or reported else 'unknown'))
            e={'unit_id':u['unit_id'],'kind':kind,'support':support,'reason':'توضیح: رابطهٔ معنایی کنترل از پیش مشخص است.','version_dependent':False,'version_limit':''}
            if variant=='previous':e['links']=[{'evidence_id':'doc1','quote':evidence[0]['text']}] if claim and support!='unknown' else []
            else:e.update(source_ids=[spans['sources'][0]['span_id']] if claim and support!='unknown' else [],message_ids=[spans['messages'][0]['span_id']] if reported else [],premise=name=='negative_premise' and u['field']=='question',standalone=True)
            r['unit_reviews'].append(e)
        if variant=='previous':r['novelty']={'useful':True,'new':True,'reason':'پرسش: بدنهٔ تابع واقعاً غایب است.','already_supplied_quote':'The UI fails.' if name=='positive_focused' else ''}
        else:r['novelty']={'useful':True,'status':'new','reason':'پرسش: بدنهٔ تابع واقعاً غایب است.','relation':'context_only' if name=='positive_focused' else 'unknown','message_ids':[spans['messages'][0]['span_id']] if name=='positive_focused' else []}
        if name=='negative_stale':r['draft_version']='expired'
        if name=='negative_forged':
            if variant=='previous':r['unit_reviews'][-1]['links'][0]['quote']='A fabricated quotation that does not occur in the source.'
            else:r['unit_reviews'][-1]['source_ids']=['src_fabricated']
        if name=='negative_wrong_namespace':
            if variant=='previous':r['unit_reviews'][-1]['links'][0]['evidence_id']='usr_user_message'
            else:r['unit_reviews'][-1]['source_ids']=[spans['messages'][0]['span_id']]
        try:result=check(r,a,evidence,state,env)
        except CasePilotError as exc:result={'verdict':'contract_failure','code':exc.code}
        outputs.append({'name':name,'answer':a,'reviewer_fixture':r,'checked_result':result,'expectation':'accept' if name.startswith('positive') else 'reject'})
    print(json.dumps(outputs,ensure_ascii=False))
def main():
    if len(sys.argv)>1:worker(sys.argv[1]);return
    outputs={}
    for variant in ('previous','revised'):
        run=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__)),variant],capture_output=True,text=True,encoding='utf-8',check=True)
        outputs[variant]=json.loads(run.stdout)
    metrics={}
    for variant,rows in outputs.items():
        positives=[r for r in rows if r['name'].startswith('positive')];semantic_neg=[r for r in rows if r['name'] in ('negative_unsupported','negative_report_escape','negative_premise','negative_partial')]
        contracts=[r for r in rows if r['name'] in ('negative_forged','negative_wrong_namespace','negative_stale')]
        metrics[variant]={'false_rejection_useful_control':{'numerator':sum(r['checked_result']['verdict']!='accept' for r in positives),'denominator':len(positives),'unknown':0},
            'unsupported_acceptance_control':{'numerator':sum(r['checked_result']['verdict']=='accept' for r in semantic_neg),'denominator':len(semantic_neg),'unknown':0},
            'invalid_contract_blocked':{'numerator':sum(r['checked_result']['verdict']=='contract_failure' for r in contracts),'denominator':len(contracts),'unknown':0}}
    out={'evaluation_kind':'synthetic_contract_controls','provider_requests':0,'model_inference':False,'human':False,'independent':False,'metrics':metrics,'rows':outputs,
        'limitation':'معنای پاسخ‌های داور را دستیار از پیش نوشته است؛ این اعداد درک مدل یا نرخ خطای کاربرد واقعی نیستند.'}
    p=BASE/'development_01/behavioral_controls.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False))
if __name__=='__main__':main()
