"""Publish executable contract schemas and development controls, never test answers."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.roles import QUALITY_JUDGE,QUALITY_EXTRACTION,QUALITY_JUDGE_PROMPT,QUALITY_EXTRACT_PROMPT
from casepilot.model import QUALITY_SELECTION
from casepilot.review_contract import draft_units
from casepilot.common import write_json

def main():
    for name,schema in [('judge',QUALITY_JUDGE),('extraction',QUALITY_EXTRACTION),('selection',QUALITY_SELECTION)]:
        write_json(ROOT/'schemas'/(name+'_quality_v22.schema.json'),schema)
    dest=ROOT/'artifacts/quality_v22/development'; dest.mkdir(parents=True,exist_ok=True)
    (dest/'judge_prompt.txt').write_text(QUALITY_JUDGE_PROMPT,encoding='utf-8')
    (dest/'extraction_prompt.txt').write_text(QUALITY_EXTRACT_PROMPT,encoding='utf-8')
    corpus=json.loads((ROOT/'data/corpus_v2.json').read_text(encoding='utf-8'))
    source=next(r for r in corpus if r['id']=='docs:dataframes:v2:bc5b9833dfed8dd0')
    quote='You can use `st.data_editor` to collect tabular input from a user. When starting from an empty dataframe, default column types are text. Use column configuration to specify the data types you want to collect from users.'
    assert quote in source['text']
    limitation='سازگاری این توضیح با نسخهٔ گزارش‌شده نامعلوم است.'
    answer={'decision':'ask','claims':[{'evidence_id':source['id'],'quote':quote}],
        'question':'پرسش: در آزمایشی که فقط مقدار اولیهٔ ستون از `None` به رشتهٔ خالی تغییر کند، مقدار بازگشتی سلول همچنان فهرست است؟',
        'next_step':'آزمایش: فقط مقدار اولیهٔ ستون را تغییر دهید و نوع مقدار بازگشتی را گزارش کنید؛ نتیجه هنوز معلوم نیست.',
        'rationale':'توضیح: مستندات برای جدول خالی نوع پیش‌فرض ستون را متن توصیف می‌کنند؛ '+limitation,'hypotheses':[]}
    envelope=draft_units(answer,'development-GH13307',1,0)
    result={'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: کنترل مثبت قرارداد؛ برچسب صحت انسانی نیست.'} for k in ('relevance','claim_support','version_fit','next_step_usefulness','avoids_repeated_check','injection_resistance')},
        'draft_version':envelope['draft_version'],'unit_reviews':[],
        'novelty':{'useful':True,'new':True,'reason':'آزمایش: مقدار اولیه تغییر کرده است؛ پیکربندی متن قبلاً امتحان شده بود.','already_supplied_quote':''}}
    for unit in envelope['units']:
        claim=unit['field']=='rationale'
        result['unit_reviews'].append({'unit_id':unit['unit_id'],'kind':'technical_claim' if claim else 'question' if unit['field']=='question' else 'next_step',
            'support':'supported' if claim else 'unknown','links':[{'evidence_id':source['id'],'quote':quote}] if claim else [],
            'reason':'توضیح: منبع نوع پیش‌فرض را توصیف می‌کند.' if claim else 'آزمایش: مشاهدهٔ تازه درخواست شده است.',
            'version_dependent':claim,'version_limit':limitation if claim else ''})
    controls=[{'name':'valid_persian_unit','expected':'accept','result':result}]
    for name,change in [('stale_draft',lambda r:r.update(draft_version='previous')),('unknown_unit',lambda r:r['unit_reviews'][0].update(unit_id='unknown')),
        ('source_quote_as_unit',lambda r:r['unit_reviews'][0].update(unit_id=quote)),('fabricated_source_span',lambda r:r['unit_reviews'][-1]['links'][0].update(quote='A fabricated source quotation with no supporting original.'))]:
        bad=copy.deepcopy(result);change(bad);controls.append({'name':name,'expected':'judge_contract_error','result':bad})
    bad=copy.deepcopy(result); bad['unit_reviews'][-1]['support']='partial'; controls.append({'name':'partial_support','expected':'repair','result':bad})
    write_json(dest/'judge_controls.json',{'scope':'development_seen_GH13307; handcrafted contract controls, not a new model answer','answer':answer,'draft':envelope,'evidence':[source],'controls':controls})
    traces=json.loads((ROOT/'artifacts/quality_revision/final_evaluation/revised_traces.json').read_text(encoding='utf-8'))
    write_json(dest/'GH13307_historical_failure.json',[r for r in traces if r.get('case_id')=='GH13307' and r.get('payload',{}).get('stage')=='judge'])
if __name__=='__main__': main()
