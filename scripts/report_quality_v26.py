"""گزارش و تطبیق فقط از شواهد محفوظ؛ بدون فراخوانی مدل یا تغییر رهگیر."""
import hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/quality_v26';FOLDER=BASE/'live_comparison_01'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ratio(n,d,unknown=0,na=0):return {'numerator':n,'denominator':d,'unknown':unknown,'not_applicable':na}
def main():
    row=read(FOLDER/'turns/GH17011_revised.json');out=row['output'];packet=read(FOLDER/'ai_review_packets.json')['packets'][0]
    manifest=read(FOLDER/'manifest.json');plan=read(FOLDER/'comparison_plan.json');baseline=read(BASE/'baseline_manifest.json');analysis=read(FOLDER/'failure_analysis.json')
    state=packet['state'];a=packet['answer_before_fallback'];raw=next(x['raw_answer'] for x in packet['raw_role_outputs'] if x['kind']=='judge')
    unit_count=len(out['reviewed_draft']['units']);unknown={'previous':ratio(None,1,1)}
    metrics={'mode':'اجرای مدل واقعی؛ زوج متوقف و ناقص','paired_comparison_valid':False,
        'previous':{'attempted':0,'processable_judge':ratio(None,1,1),'complete_units':ratio(None,0,1),'utility':ratio(None,1,1)},
        'revised':{'attempted':1,'valid_json':ratio(1,1),'processable_judge':ratio(0,1),'complete_unit_keys':ratio(len(raw['u']),unit_count),
            'validated_full_coverage':ratio(0,1),'semantically_reviewed_units':ratio(0,unit_count,unit_count),
            'truncated_output':ratio(0,1),'judge_contract_failure':ratio(1,1),
            'preserved_current_version':ratio(int(state['facts'].get('streamlit_version')=='1.64.0'),1),
            'preserved_reported_comparisons':ratio(sum(e['status'] in ('succeeded','failed') for e in state['experiments']),2),
            'preserved_raw_report':ratio(int(state['messages'][0]['text']==plan['case']['initial_message']),1),
            'irrelevant_feature_fields':ratio(sum(bool(v) for k,v in a['feature_proposal'].items() if k!='report_quotes'),5),
            'real_feature_preservation':ratio(None,0,na=1),'valid_control_false_rejection':ratio(None,0,na=1),
            'negative_control_acceptance':ratio(None,0,na=1),'utility_score_2':ratio(0,1),
            'utility_score':0,'utility_reviewer':'دستیار مشارکت‌کننده؛ غیرمستقل، پس از نتیجه',
            'provider_requests':5,'model_calls':5,'cache_hits':0,'repair_count':0,'elapsed_seconds':row['elapsed_seconds'],
            'confirmed_usd':manifest['new_confirmed_usd'],'uncertain_reserved_usd':manifest['new_uncertain_reserved_usd']},
        'limitations':['زوج مبنا/اصلاح تکمیل نشده؛ مقایسهٔ علّی زنده نداریم','پس از اصلاح مستقل آفلاین درخواست واقعی دیگری اجرا نشده',
            'خروجی متوقف‌شده در سقف نیست؛ پاسخ قرارداد را رعایت نکرده','فایدهٔ صفر به ارجاع عمومی مربوط است، نه اثبات ضرورت ارجاع پرونده'],
        'human_review':False,'independent_review':False,'provider_requests_for_review':0}
    write(FOLDER/'evaluation_metrics.json',metrics)
    write(FOLDER/'ai_review.json',{'reviewer':'دستیار مشارکت‌کننده در پیاده‌سازی','independent':False,'blind':False,'human':False,
        'response_sha256':hashlib.sha256(out['response'].encode()).hexdigest(),'utility':0,
        'reason':'پاسخ نهایی ارجاع عمومی ناشی از خطای داخلی قرارداد است؛ اقدام تشخیصی تصمیم‌ساز تحویل نشده و ضرورت ارجاع واقعی پرونده اثبات نشده است.',
        'version_fit':'نسخهٔ جاری حفظ شده؛ داوری محتوایی تکمیل نشده است.','repetition':'داوری محتوایی تکمیل نشده؛ نامعلوم.',
        'source_support':'متن قالب مدل قابل خواندن است، اما پشتیبانی محتوایی اعتبارسنجی نشده؛ نامعلوم.',
        'feature':'فیلدهای قابلیت در خطا خالی‌اند؛ قابلیت واقعی اجرا نشده است.','provider_requests':0})
    calls=manifest['cost_after']['calls'];total=0;prefix=None
    for i,r in enumerate(calls):
        if abs(total-1.704717190)<1e-9:prefix=calls[:i];break
        total+=r['charged']
    assert prefix is not None
    start_confirmed=sum(r['charged'] for r in prefix if r['status']=='confirmed');start_unknown=sum(r['charged'] for r in prefix if r['status']!='confirmed')
    after=manifest['cost_after'];account={'round':{'confirmed_usd':manifest['new_confirmed_usd'],'uncertain_reserved_usd':manifest['new_uncertain_reserved_usd'],
        'charged_or_reserved_usd':manifest['new_charged_or_reserved_usd'],'requests':manifest['new_requests']},
        'stage':{'original_start_usd':1.704717190,'cumulative_cap_usd':2.004717190,'confirmed_usd':after['confirmed_usd']-start_confirmed,
            'uncertain_reserved_usd':after['uncertain_reserved_usd']-start_unknown,'charged_or_reserved_usd':after['charged_or_reserved_usd']-1.704717190,
            'remaining_usd':2.004717190-after['charged_or_reserved_usd'],'original_prefix_requests':len(prefix)},
        'team':{k:after[k] for k in ('confirmed_usd','uncertain_reserved_usd','charged_or_reserved_usd','requests')},
        'team_cap_usd':5,'new_allocation_usd':0,'panel_balance_observed':False,'old_unknown_reservations_released':False}
    write(BASE/'accounting.json',account)
    changed={n:{'evaluated_sha256':h,'current_sha256':sha(ROOT/n)} for n,h in plan['files'].items() if sha(ROOT/n)!=h}
    write(BASE/'post_live_offline_fix.json',{'announced_before_change':True,'purpose':'هماهنگ‌کردن منع دلیل خالی/سفید در قالب و پردازش‌کننده؛ معیار پذیرش آسان نشده',
        'changed_frozen_files':changed,'evaluated_snapshot':'artifacts/quality_v26/evaluated_snapshot','paid_rerun':False,
        'saved_invalid_response_still_rejected':True,'tests':read(BASE/'final_delivery_tests/test_results.json'),
        'live_result_applies_to_current_source':False,'remaining_unknown':'رفتار مدل واقعی با قید سخت‌تر دلیل، ارزیابی نشده است.'})
    current={r['id']:r for r in calls};old=manifest['cost_before']['calls']
    checks={'actual_start_snapshot_matches':all(sha(BASE/'baseline'/n)==h for n,h in baseline['files'].items()),
        'historical_artifacts_unchanged':all(sha(ROOT/n)==h for n,h in baseline['historical_files'].items()),
        'evaluated_snapshot_matches_plan':all(sha(BASE/'evaluated_snapshot'/n)==h for n,h in plan['files'].items()),
        'post_live_changes_declared_and_limited':set(changed)=={'src/casepilot/compact_review.py','tests/test_quality_v26.py'},
        'git_head_unchanged':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==baseline['git_head'],
        'old_ledger_rows_unchanged':all(current[r['id']]==r for r in old),'new_reservations_accounted_once':manifest['new_requests']==5,
        'stage_cap_respected':after['charged_or_reserved_usd']<=2.004717190,'turn_cap_respected':manifest['new_charged_or_reserved_usd']<=.04,
        'no_approval_execute_or_comment':all(n==0 for n in analysis['effects'].values()),
        'calls_time_repair_limits_respected':out['model_calls']<=8 and out['latency_seconds']<=180 and out['repair_count']<=1,
        'all_tests_passed':read(BASE/'final_delivery_tests/test_results.json')['passed'],
        'final_capacity_schema_and_full_contract':all(r['json_schema_valid'] and r['full_contract_valid'] and r['covered_units']==r['units'] for r in read(BASE/'validated_capacity.json')['records']),
        'live_stop_and_no_retry':manifest['attempted']==1 and manifest['stop_reason']=='judge_contract_error' and not (FOLDER/'turns/GH17011_previous.json').exists()}
    sensitive=[]
    paths=list(BASE.rglob('*'))+[ROOT/'docs/QUALITY_V26_FA.md',ROOT/'docs/QUALITY_V26_PROTOCOL_FA.md',ROOT/'README.md']
    for p in paths:
        if not p.is_file() or p.suffix not in ('.json','.md','.txt','.py','.csv'):continue
        if re.search(r'tpsg-[A-Za-z0-9_-]{30,}',p.read_text(encoding='utf-8',errors='replace')):sensitive.append(p.relative_to(ROOT).as_posix())
    checks['no_metis_credential_in_delivery']=not sensitive
    write(BASE/'verification.json',{'checks':checks,'all_passed':all(checks.values()),'sensitive_file_count':len(sensitive),
        'code_current_differs_from_evaluated':True,'reason':'اصلاح مستقل آفلاین اعلام‌شده؛ نتیجهٔ واقعی برای آن ادعا نمی‌شود.'})
    print(json.dumps({'verification':checks,'accounting':account,'metrics':metrics['revised']},ensure_ascii=False))
if __name__=='__main__':main()
