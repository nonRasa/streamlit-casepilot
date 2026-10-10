"""Freeze fixed drafts and provisional unit references, never call a provider."""
import hashlib
import json
import secrets
import sys
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import digest
from casepilot.report_quotes import catalog, resolve
from casepilot.review_contract import draft_units, review_spans
from casepilot.semantics import UNKNOWN

DATA=ROOT/'eval/quality_v28_semantic_judge/suite_v3'
RUN=ROOT/'artifacts/quality_v28_semantic_judge'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    if path.exists():raise FileExistsError(str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def build_pair(pair_id,family,message,field,good,bad,*,feature=False,source=None,
               selected_quote=None,bad_quote=None,witness=None,defect='unsupported',bad_field=None,
               bad_unit_witness=None,version='1.48.0',source_version='1.48.0',limit=''):
    state={'id':'judge_'+pair_id,'revision':1,'facts':{'streamlit_version':version},
        'messages':[{'role':'user','text':message}], 'checks':[], 'experiments':[],
        'investigation_plan':{'intent':'feature_request' if feature else 'bug'},
        'report_quote_contract':'user-report-sections-v1'}
    base={'decision':'escalate' if feature else ('ask' if field=='question' else 'answer'),
        'question':'','next_step':'اقدام: نتیجهٔ بررسی را ثبت کنید.',
        'rationale':'محدودیت: علت مشکل در این پاسخ تأیید نشده است.',
        'hypotheses':[], 'claims':[], 'feature_proposal':None, 'diagnostic':{}}
    if feature:
        # A positive draft must not contain unrelated selected report sections.
        # Keep the common faithful design specification fixed within the pair.
        base['feature_proposal']={k:good for k in ('desired_behavior','user_need','constraints','acceptance_condition')}
        base['feature_proposal']['current_behavior']=UNKNOWN
        base['feature_proposal']['report_quotes']=[]
    evidence=[]
    if source:
        evidence=[{'id':'fixture:'+pair_id, 'source_id':'fixture:'+family,
            'text':source,'product_version':source_version,'revision':'synthetic-r1',
            'source_type':'docs','url':'https://example.invalid/semantic-fixture/'+pair_id,
            'provenance':'authored synthetic evidence; not corpus documentation'}]
        if selected_quote:base['claims']=[{'evidence_id':evidence[0]['id'],'quote':selected_quote,**({'version_limit':limit} if limit else {})}]
    inputs=[]; labels=[]
    for variant,text in [('a',good),('b',bad)]:
        answer=deepcopy(base)
        if field.startswith('feature_proposal.'):
            answer['feature_proposal'][field.split('.')[1]]=text
        else:answer[field]=text
        if feature:
            sections=catalog(state)
            needed=witness or message
            answer['feature_proposal']['report_quotes']=[s['section_id'] for s in sections if needed in s['text']]
            if not answer['feature_proposal']['report_quotes']:raise ValueError('No complete selectable witness section')
            answer=resolve(answer,sections,state)
        if variant=='b' and bad_quote is not None:
            answer['claims']=[{'evidence_id':evidence[0]['id'],'quote':bad_quote,**({'version_limit':limit} if limit else {})}] if bad_quote else []
        envelope=draft_units(answer,state['id'],1,0,include_quotes=True)
        spans=review_spans(state,evidence,answer['claims'],report_quotes=(answer.get('feature_proposal') or {}).get('report_quotes',[]))
        units=[]
        for unit in envelope['units']:
            f=unit['field']; target=f==(bad_field or field)
            expected='supported'; act='procedure'; kind='next_step'; user=[]; sources=[]
            structural=True; lineage=True; policy=True; meaning='procedural action or statement of review uncertainty'
            if f=='question':act='diagnostic';kind='question';expected='unknown'
            if f.startswith('feature_proposal.'):
                kind='request_summary';act='request'
                if unit['text']==UNKNOWN:act='unknown';expected='unknown'
                else:
                    q=witness or message
                    if f.startswith('feature_proposal.report_quotes.'):q=unit['text']
                    start=message.find(q)
                    if start<0:raise ValueError('Witness missing')
                    user=[{'message_index':0,'start':start,'end':start+len(q),'text':q}]
                    meaning='faithful requested behavior; does not establish present capability'
            if f.startswith('claims.') or (source and f==field):
                kind='technical_claim';act='technical'
                quote=answer['claims'][0]['quote'] if answer['claims'] else ''
                if quote:sources=[{'evidence_id':evidence[0]['id'],'quote':quote,'start':source.find(quote),'end':source.find(quote)+len(quote)}]
                meaning='direct support for the whole assertion, relevant to the user request'
            if variant=='b' and (target or (f.startswith('claims.') and defect in ('irrelevant','unselected'))):
                expected={'partial':'partial','contradicted':'contradicted'}.get(defect,'unknown')
                policy=False;meaning=defect
                if defect in ('unsupported','partial','unselected','version','irrelevant'):
                    act='technical';kind='technical_claim'
                if feature and defect=='unsupported_detail':act='request';kind='request_summary'
                if bad_unit_witness:user=bad_unit_witness
            units.append({'field':f,'unit_id':unit['unit_id'],'text':unit['text'],
                'expected_support':expected,'expected_act':act,'expected_kind':kind,
                'exact_user_witnesses':user,'selected_source_witnesses':sources,
                'structural_valid':structural,'quote_lineage_valid':lineage,
                'product_policy_valid':policy,'semantic_explanation':meaning,
                'relevant_source_required':act=='technical', 'expected_version_limit':limit})
        inputs.append({'id':pair_id+'_'+variant,'pair_id':pair_id,'family':family,
            'state':deepcopy(state),'answer':answer,'evidence':deepcopy(evidence)})
        labels.append({'id':pair_id+'_'+variant,'pair_id':pair_id,'family':family,
            'author':'agent-authored provisional reference; not independent human truth',
            'definitive_for_provisional_reference':True,'expected_accept':variant=='a','units':units})
    return inputs,labels


def main():
    if (DATA/'manifest.json').exists():raise FileExistsError('Frozen suite already exists')
    notice='محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است.'
    specs=[
        ('dev','D1','queue_ownership','Feature request: Add a reviewer queue view.\n\nEach reviewer should see only their own assignments.\n\nAcceptance: changing the view must leave assignment ownership unchanged.',
         'feature_proposal.constraints','درخواست: هر بازبین فقط تخصیص‌های خودش را در نمای صف ببیند.','درخواست: هر بازبین تخصیص‌های همهٔ اعضا را در نمای صف ببیند.',
         {'feature':True,'witness':'Each reviewer should see only their own assignments.','defect':'unsupported_detail'}),
        ('dev','D2','export_language','Please propose a CSV export.\n\nUse the column labels currently displayed in the report. The export should contain the displayed rows only.',
         'feature_proposal.desired_behavior','درخواست: خروجی CSV فقط ردیف‌های نمایش‌داده‌شده را با برچسب ستون‌های گزارش داشته باشد.','درخواست: خروجی CSV همهٔ ردیف‌ها را با برچسب ستون‌های گزارش داشته باشد.',
         {'feature':True,'witness':'Use the column labels currently displayed in the report. The export should contain the displayed rows only.','defect':'unsupported_detail'}),
        ('dev','D3','preview_uncertainty','I propose an audit preview. Please describe the desired behavior; I have not checked any existing API.',
         'rationale','محدودیت: وجود API برای این رفتار در این پاسخ تأیید نشده است.','محدودیت: وجود API برای این رفتار در این محصول امکان ندارد.',{}),
        ('dev','D4','chart_observation','A plot disappears during refresh. I have not recorded the console output or the timing of refresh.',
         'question','آیا می‌توانید زمان شروع refresh و زمان ناپدید شدن نمودار را ثبت کنید؟.','آیا می‌توانید تأیید کنید که refresh باعث ناپدید شدن نمودار می‌شود؟.',{}),
        ('dev','D5','download_serialization','Does st.download_button keep its data in memory and trigger a rerun?',
         'next_step','گزینهٔ st.download_button داده را در حافظه نگه می‌دارد و با کلیک بازاجرا می‌شود.','گزینهٔ st.download_button داده را در حافظه نگه می‌دارد و با کلیک بازاجرا می‌شود.',
         {'source':'st.download_button keeps its data in memory. Clicking st.download_button triggers a rerun.','selected_quote':'st.download_button keeps its data in memory. Clicking st.download_button triggers a rerun.','bad_quote':'st.download_button keeps its data in memory.','defect':'partial'}),
        ('dev','D6','cache_version','Does st.cache_data return a separate copy for each caller?',
         'next_step','گزینهٔ st.cache_data برای هر فراخواننده کپی جدا برمی‌گرداند.\n'+notice,'گزینهٔ st.cache_data برای هر فراخواننده کپی جدا برمی‌گرداند.',
         {'source':'st.cache_data returns a separate copy of the cached value to each caller.','selected_quote':'st.cache_data returns a separate copy of the cached value to each caller.','source_version':None,'defect':'version','limit':notice}),
        ('holdout','H1','reservation_retention','Propose named calendar reservations.\n\nA reservation has a name and an expiry time.\n\nOn cancellation, retain its audit record for exactly fourteen days.',
         'feature_proposal.acceptance_condition','درخواست: پس از لغو رزرو، رکورد ممیزی دقیقاً چهارده روز نگه داشته شود.','درخواست: پس از لغو رزرو، رکورد ممیزی دقیقاً چهل روز نگه داشته شود.',
         {'feature':True,'witness':'On cancellation, retain its audit record for exactly fourteen days.','defect':'unsupported_detail'}),
        ('holdout','H2','audio_format','Does st.audio accept a sampling rate argument?',
         'next_step','در تابع st.audio می‌توان sample_rate را برای دادهٔ صوتی تعیین کرد.','در تابع st.audio می‌توان sample_rate را برای دادهٔ صوتی تعیین کرد.',
         {'source':'st.audio accepts sample_rate for audio data. st.image accepts width for image data.','selected_quote':'st.audio accepts sample_rate for audio data.','bad_quote':'st.image accepts width for image data.','defect':'irrelevant'}),
        ('holdout','H3','alert_proposal','Feature proposal: add a silent preview of deployment alerts before publishing them. No current capability is claimed.',
         'feature_proposal.desired_behavior','درخواست: پیش‌نمایش بی‌صدای هشدارهای استقرار پیش از انتشار اضافه شود.','قابلیت پیش‌نمایش بی‌صدای هشدارهای استقرار هم‌اکنون وجود دارد.',
         {'feature':True,'defect':'unsupported'}),
        ('holdout','H4','state_deletion','How do I delete the key count from st.session_state?',
         'next_step','برای حذف کلید count از st.session_state از دستور del st.session_state["count"] استفاده کنید.','برای حذف کلید count از st.session_state از دستور del st.session_state["count"] استفاده کنید.',
         {'source':'Delete a key from st.session_state using del st.session_state["count"]. st.write displays its argument.','selected_quote':'Delete a key from st.session_state using del st.session_state["count"].','bad_quote':'st.write displays its argument.','defect':'unselected'}),
        ('holdout','H5','upload_cause','An upload stalls once. No trace identifies its cause; please ask for one new diagnostic observation.',
         'rationale','محدودیت: علت توقف بارگذاری هنوز تأیید نشده است.','محدودیت: شبکه قطعاً باعث توقف بارگذاری شده است.',{}),
        ('holdout','H6','form_submission','Does a form submit send all widget values together and execute its callback before the script reruns?',
         'next_step','فرم مقدار همهٔ ویجت‌ها را با هم می‌فرستد و callback را پیش از بازاجرای اسکریپت اجرا می‌کند.','فرم مقدار همهٔ ویجت‌ها را با هم می‌فرستد و callback را پیش از بازاجرای اسکریپت اجرا می‌کند.',
         {'source':'Submitting a form sends all widget values together. Its callback runs before the script reruns.','selected_quote':'Submitting a form sends all widget values together. Its callback runs before the script reruns.','bad_quote':'Submitting a form sends all widget values together.','defect':'partial'}),
    ]
    split_inputs={'dev':[],'holdout':[]};split_labels={'dev':[],'holdout':[]}
    for split,pid,family,message,field,good,bad,kwargs in specs:
        inputs,labels=build_pair(pid,family,message,field,good,bad,**kwargs)
        split_inputs[split].extend(inputs);split_labels[split].extend(labels)
    for split in split_inputs:
        write(DATA/(split+'_inputs.json'),split_inputs[split]);write(DATA/(split+'_labels.json'),split_labels[split])
    protocol={'version':'fixed-draft-judge-v1','family_disjoint':True,
        'reference_status':'provisional agent authored; independent review pending',
        'roles':['judge'],'models':{'judge':'gpt-4.1-mini'},'no_retrieval':True,'no_generation':True,'no_embeddings':True,
        'max_requests':52,'max_output_tokens':2000,'request_cap_usd':0.02,'hard_cap_usd':0.90,
        'phases':{k:{'requests':12,'usd':0.20} for k in ('baseline','correction_1','correction_2','holdout')},
        'connection_retries':{'requests':4,'usd':0.10},
        'acceptance':{'false_acceptance':0,'false_rejection':0,'selected_unit_witness_accuracy':1.0,
            'contract_validity':1.0,'overall_unit_consistency':1.0,
            'require_independent_review_for_unconditional_quality_claim':True},
        'selection':'Development only; each correction one main component, recorded hypothesis; holdout only after selection; no holdout tuning',
        'ambiguity_policy':'Exclude provisional ambiguous cases from definitive rates; never turn unknown into rejection or success',
        'retry_policy':'Only connection/timeouts, identical frozen request; no content retries outside approved corrections'}
    write(DATA/'protocol.json',protocol)
    write(DATA/'ambiguity.json',[
        {'text':'این مشاهده به تشخیص علت کمک می‌کند.','reason':'method usefulness vs implied causal guarantee requires independent review'},
        {'text':'این گزینه را برای بررسی امتحان کنید.','reason':'may assert an existing option depending on its source and surrounding text'}])
    write(DATA/'pricing.json',{'rate_basis':'Previously verified Metis tariff on 2026-10-10; frozen estimate, verify before authorized execution',
        'model':'gpt-4.1-mini','input_usd_per_million':0.44,'output_usd_per_million':1.76})
    files={p.name:sha(p) for p in DATA.glob('*.json')}
    write(DATA/'manifest.json',{'files':files,'pairs_per_split':6,'drafts_per_split':12,
        'families':{s:sorted({r['family'] for r in split_inputs[s]}) for s in split_inputs},
        'labels_are_not_independent':True,'frozen_before_judge_changes':True})
    blind=[];key=[]
    cases=split_inputs['dev']+split_inputs['holdout'];secrets.SystemRandom().shuffle(cases)
    for item in cases:
        bid='blind_'+secrets.token_hex(8)
        blind.append({'blind_id':bid,'state':item['state'],'draft':item['answer'],'evidence':item['evidence'],
            'review_form':{'units':None,'overall_accept':None,'uncertain':None,'reviewer':None}})
        key.append({'blind_id':bid,'id':item['id'],'split':'dev' if item['pair_id'].startswith('D') else 'holdout'})
    write(RUN/'review_suite_v3/human_review_blind.json',{'reference_included':False,'items':blind})
    write(RUN/'review_suite_v3/human_review_key.json',{'items':key,'manifest_sha256':sha(DATA/'manifest.json')})
    print('Frozen 12 pairs / 24 drafts; no provider calls.')


if __name__=='__main__':main()
