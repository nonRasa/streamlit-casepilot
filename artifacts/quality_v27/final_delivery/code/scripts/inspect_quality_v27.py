"""Local structural grid, contract capacity and live accounting analysis."""
import copy, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from casepilot.common import read_json,write_json,canonical,digest
from casepilot.parent_child import chunks
from casepilot.tokenization import count_tokens
from casepilot.compact_review import contract,encode_fixture,decode,schema
from casepilot.review_contract import review_spans
from casepilot.semantics import checked_semantic_review
from casepilot.schema_preflight import check_provider_schema
from casepilot.hybrid import embedding_text
from test_quality_v23 import answer
import test_quality_v25 as controls
BASE=ROOT/'artifacts/quality_v27'

def inspect():
    sources=read_json(ROOT/'data/corpus_v3.sources.json');grid=[]
    for child,parent in ((200,600),(300,800),(400,1000)):
        rows=[r for s in sources for r in chunks(s,child,parent)]
        sizes=sorted(r['token_count'] for r in rows)
        grid.append({'child_target_tokens':child,'parent_target_tokens':parent,'children':len(rows),
                     'parents':len({r['parent_id'] for r in rows}),'median_tokens':sizes[len(sizes)//2],
                     'p95_tokens':sizes[int(.95*(len(sizes)-1))],'max_tokens':max(sizes),
                     'oversize_children':sum(r['oversized_block'] for r in rows),
                     'embedding_input_tokens':sum(count_tokens(embedding_text(r),encoding='cl100k_base') for r in rows)})
    write_json(BASE/'structure_grid.json',{'snapshot_hash':digest(sources),'encoding':'o200k_base',
        'embedding_encoding':'cl100k_base','grid':grid,'provider_requests':0,'optimal_size_claimed':False,
        'note':'Structural measurements only, no learned-vector or answer-quality comparison across sizes. Short reports stay whole.'})
    a=answer();s=controls.state(); samples=[('small',a,s)]
    a,s=controls.FeatureControls().proposal('GH16481');a.update(decision='ask',question='پرسش: کدام شرط پذیرش هنوز نامعلوم است؟',hypotheses=['فرضیه: این علت تأیید نشده است.']*3)
    samples.append(('maximum_units',a,s));capacity=[]
    for name,a,s in samples:
        env,r=controls.judge(a,s)
        for u,e in zip(env['units'],r['unit_reviews']):
            if u['field'].startswith('hypotheses.'):
                e.update(kind='hypothesis',premise=True);e['meaning'].update(act='technical',assertion_text=u['text'])
        c=contract(env,review_spans(s,[],a['claims']));w=encode_fixture(r,c);check_provider_schema(schema(c))
        result=checked_semantic_review(decode(w,c),a,[],s,env)
        worst=copy.deepcopy(w)
        long_reason=('دلیل: نیازمند بررسی دقیق است. '*5)[:80]
        worst['r']=[long_reason]*6;worst['n']['r']=long_reason
        for e in worst['u'].values():e['r']=long_reason
        worst_result=checked_semantic_review(decode(worst,c),a,[],s,env)
        item={'sample':name,'units':len(env['units']),'contract_valid':True,'semantic_verdict':result['verdict'],
              'typical_fixture_tokens':count_tokens(canonical(w)),'all_reasons_80_chars_tokens':count_tokens(canonical(worst)),
              'configured_judge_output_tokens':1600,'provider_requests':0,
              'maximum_reason_fixture_full_processing':len(worst_result['unit_reviews'])==len(env['units'])}
        capacity.append(item)
        write_json(BASE/'contract_examples'/(name+'.json'),{'draft':env,'schema':schema(c),'wire':w,'checked':result})
    write_json(BASE/'capacity.json',{'samples':capacity,'limitation':'Local serialized fixture sizes do not guarantee model completion or semantic correctness; maximum source/dependency references may need more space.'})
    live=BASE/'contract_live_01'
    if (live/'result.json').exists():
        diagnostic=read_json(ROOT/'runtime/quality_v27/contract_live_01/S1/diagnostics/d44df0956dd753c79b98d655.json')
        write_json(live/'failure_analysis.json',{'observed':'HTTP 400; provider explicitly rejects uniqueItems at novelty message references',
            'diagnostic':diagnostic,'after_failure':'Current source removes unsupported keyword; uniqueness still checked by decoder. No paid retry.',
            'evaluated_stage':'S1','current_code_live_verified':False,'historical_reservation_released':False})
    print(json.dumps({'structure_grid':grid,'capacity':capacity},ensure_ascii=True))

if __name__=='__main__':inspect()
