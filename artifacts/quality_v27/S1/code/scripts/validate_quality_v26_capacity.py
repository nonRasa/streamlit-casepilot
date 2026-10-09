"""بازبینی مستقل قالب JSON و عبور کامل قرارداد پس از توقف؛ بدون مدل."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/quality_v26'
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT/'runtime/quality_v26/tokenizer')]
import jsonschema,tiktoken
import test_quality_v25 as v25
from test_quality_v23 import answer
from casepilot.common import canonical,read_json,write_json
from casepilot.model import quote_candidates,resolve_claims
from casepilot.review_contract import review_spans
from casepilot.semantics import checked_semantic_review
from casepilot.compact_review import contract,encode_fixture,decode,schema

def main():
    target=BASE/'validated_capacity.json'
    if target.exists():raise SystemExit('توقف: شواهد بازنویسی نمی‌شوند.')
    enc=tiktoken.encoding_for_model('gpt-4.1-mini');samples=[]
    a=answer();s=v25.state();env,r=v25.judge(a,s);samples.append(('low_3',a,s,[],env,r))
    p=next(p for p in read_json(ROOT/'artifacts/quality_v25/live_comparison_01/ai_review_packets.json')['packets'] if p['variant']=='revised')
    ev=p['retrieved_sources'];a=resolve_claims(next(x['raw_answer'] for x in p['raw_role_outputs'] if x['kind']=='chat'),{(e['id'],q['quote_id']):q['text'] for e in ev for q in quote_candidates(e['text'])})
    s={'id':p['id'],'revision':1,'facts':p['result']['output']['summary']['facts'],'messages':[{'role':'user','text':p['initial_report']}],'investigation_plan':{'intent':'bug'}}
    env,r=v25.judge(a,s,ev);samples.append(('actual_failed_draft_8',a,s,ev,env,r))
    a,s=v25.FeatureControls().proposal('GH16481');a['decision']='ask';a['question']='پرسش: کدام شرط پذیرش هنوز نامعلوم است؟';a['hypotheses']=['فرضیه: این برداشت هنوز تأیید نشده است.']*3
    env,r=v25.judge(a,s)
    for u,e in zip(env['units'],r['unit_reviews']):
        if u['field'].startswith('hypotheses.'):
            e.update(kind='hypothesis',premise=True);e['meaning'].update(act='technical',assertion_text=u['text'])
    samples.append(('maximum_11',a,s,[],env,r));records=[]
    for name,a,s,ev,env,r in samples:
        for u,e in zip(env['units'],r['unit_reviews']):
            if u['field'].startswith('hypotheses.'):
                e.update(kind='hypothesis',premise=True);e['meaning'].update(act='technical',assertion_text=u['text'])
        c=contract(env,review_spans(s,ev,a['claims']));wire=encode_fixture(r,c);definition=schema(c)
        errors=list(jsonschema.Draft202012Validator(definition).iter_errors(wire));assert not errors,[(list(e.path),e.message) for e in errors]
        reviewed=checked_semantic_review(decode(wire,c),a,ev,s,env)
        old=dict(r,unit_reviews={e['unit_id']:{k:v for k,v in e.items() if k!='unit_id'} for e in r['unit_reviews']})
        old_fixture=read_json(BASE/'capacity_samples'/(name+'.json'))['compact_synthetic_review']
        old_errors=list(jsonschema.Draft202012Validator(definition).iter_errors(old_fixture))
        row={'name':name,'units':len(env['units']),'json_schema_valid':True,'full_contract_valid':True,'covered_units':len(reviewed['unit_reviews']),
            'semantic_verdict':reviewed['verdict'],'old_wire_tokens':len(enc.encode(canonical(old),disallowed_special=())),
            'compact_wire_tokens':len(enc.encode(canonical(wire),disallowed_special=())),
            'original_capacity_fixture_schema_errors':[{'path':list(e.path),'validator':e.validator} for e in old_errors]}
        records.append(row);write_json(BASE/'validated_capacity_samples'/(name+'.json'),{'answer':a,'state':s,'evidence':ev,'envelope':env,'fixture_review':r,'compact_review':wire,'schema':definition,'checked':reviewed})
    write_json(target,{'mode':'کنترل آفلاین پس از توقف؛ دادهٔ توسعه و نه مدل واقعی','schema_validator':'jsonschema Draft202012Validator',
        'tokenizer':tiktoken.__version__,'encoding':enc.name,'records':records,'provider_requests':0,
        'original_gate_limitation':'نمونهٔ هشت‌واحدی و بیشینه در دروازهٔ اولیه نوع فرضیه را نادرست داشتند؛ فقط بازکردن فشرده سنجیده شد، نه کل قرارداد. اکنون نوع درست و مسیر کامل سنجیده شده‌اند.',
        'semantic_note':'فرضیهٔ بیشینه عمداً بی‌شاهد است و رد محتوایی می‌شود؛ معتبر بودن قرارداد به معنای پذیرش محتوایی نیست.',
        'paid_rerun':False})
    print(json.dumps(records,ensure_ascii=False))
if __name__=='__main__':main()
