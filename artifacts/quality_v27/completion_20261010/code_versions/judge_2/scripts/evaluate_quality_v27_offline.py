"""Frozen, offline stage comparisons. Hash vectors are fixtures, not learned AI.

Workers receive only allowlisted input fields. Labels are loaded by the parent
scorer after outputs have been written, never by retrieval or generation.
"""
import argparse, csv, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/'artifacts/quality_v27'
VARIANTS=('S0','S1','S2','tokens_only','S3a','S3b_verified','S4')

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def worker(variant,split):
    stage='S2' if variant=='tokens_only' else variant
    sys.path.insert(0,str(BASE/stage/'code/src'))
    import casepilot.common as common
    common.ROOT=ROOT
    from casepilot.model import ReplayClient
    from casepilot.hybrid import HybridRetriever
    from casepilot.agent import Agent
    from casepilot.store import Store
    from casepilot import pipeline
    corpus=ROOT/'data/corpus_v2.json'
    if variant in ('S3a','S3b_verified','S4'): corpus=ROOT/'data/corpus_v3.json'
    if variant=='tokens_only':
        # Change ONLY counting on the old block algorithm and same numeric limits.
        import tiktoken
        import casepilot.chunking as chunking
        enc=tiktoken.get_encoding('o200k_base')
        chunking.token_estimate=lambda text:len(enc.encode(text,disallowed_special=()))
        chunking.CONFIG=dict(chunking.CONFIG,name='legacy_structure_real_tokens',token_estimator='o200k_base')
        sources=read(ROOT/'data/corpus_v3.sources.json')
        corpus=ROOT/'runtime/quality_v27/token_only_corpus.json'
        write(corpus,[r for source in sources for r in chunking.chunks(source)])
    client=ReplayClient(); hybrid=HybridRetriever(client,path=corpus,cache_path=ROOT/'runtime/quality_v27/offline_vectors.sqlite3')
    inputs=read(ROOT/'eval/quality_v27'/(split+'_inputs.json')); results=[]
    with tempfile.TemporaryDirectory() as tmp:
        agent=Agent(Store(Path(tmp)/'tracker.sqlite3'),client=client,hybrid=hybrid)
        for case in inputs:
            # Explicit allowlist: no labels, expected behavior, split or family.
            inp={k:case[k] for k in ('id','initial_message','initial_facts','initial_checks')}
            result=agent.turn(inp['id'],inp['initial_message'],variant+'-'+inp['id'],inp['initial_facts'],inp['initial_checks'])
            stages=result['pipeline']; candidate_ids=next((s.get('candidates',[]) for s in stages if s['stage']=='retrieve'),[])
            selected_ids=[r['id'] for r in result['retrieved']]
            by_id={r['id']:r for r in hybrid.chunks}
            by_id.update({r['parent']['id']:r['parent'] for r in hybrid.chunks if 'parent' in r})
            from casepilot.evidence import annotate
            candidates=[annotate(by_id[i],inp['initial_facts'].get('streamlit_version')) for i in candidate_ids]
            selected=[annotate(by_id[i],inp['initial_facts'].get('streamlit_version')) for i in selected_ids]
            results.append({'id':inp['id'],'variant':variant,'input_hash':common.digest(inp),
                'result':result,'candidate_rows':candidates,'context_rows':selected})
    write(BASE/'offline'/variant/(split+'.json'),{'evaluation_kind':'offline_hash_fixture',
         'corpus_sha256':__import__('hashlib').sha256(corpus.read_bytes()).hexdigest(),'rows':results,'provider_requests':0})

def score(output_dir=None):
    output_dir=Path(output_dir or BASE/'offline')
    if (output_dir/'metrics.json').exists(): raise SystemExit('Score report exists; choose a new output directory.')
    sys.path.insert(0,str(ROOT/'src'))
    from casepilot.evaluation import retrieval_metrics,answer_metrics
    from casepilot.context_pack import public_row
    from casepilot.tokenization import count_tokens
    from casepilot.common import canonical
    all_rows=[]; summaries=[]; human=[]
    for variant in VARIANTS:
        for split in ('dev','holdout'):
            labels={r['id']:r for r in read(ROOT/'eval/quality_v27'/(split+'_labels.json'))}
            result=read(BASE/'offline'/variant/(split+'.json'))
            group=[]
            for row in result['rows']:
                label=labels[row['id']]
                packing=next((s for s in row['result']['pipeline'] if s['stage']=='context_pack'),{})
                tokens=packing.get('used_tokens',count_tokens(canonical([public_row(r) for r in row['context_rows']])))
                metrics={'id':row['id'],'variant':variant,'split':split,
                    'retrieval':retrieval_metrics(row['candidate_rows'],label),
                    'context':retrieval_metrics(row['context_rows'],label,context_tokens=tokens),
                    'answer':answer_metrics(row['result'],label)}
                # Replay judge is intentionally a control-flow stub, not the full wire judge.
                metrics['answer']['contract_valid']=None
                all_rows.append(metrics);group.append(metrics)
                human.append({'blind_id':'review-'+str(len(human)+1),'case':row['id'],'variant_private':variant,
                    'input_hash':row['input_hash'],'response':row['result']['response'],'sources':row['context_rows'],
                    'expected_behavior_evaluator_only':label['expected_behavior'],'human_usefulness':None,'human_unsupported_claims':None,'human_repetition':None})
            def avg(category,key):
                values=[r[category][key] for r in group if r[category][key] is not None]
                return sum(values)/len(values) if values else None
            summaries.append({'variant':variant,'split':split,'n':len(group),
                'recall_at_5':avg('retrieval','recall_at_k'),'ndcg_at_5':avg('retrieval','ndcg_at_k'),
                'judged_irrelevant_fraction':avg('retrieval','judged_irrelevant_fraction'),
                'unjudged_fraction':avg('retrieval','unjudged_fraction'),
                'evidence_coverage':avg('context','required_evidence_coverage'),
                'context_tokens_mean':avg('context','context_tokens'),
                'context_budget_violations':sum(not r['context']['context_budget_ok'] for r in group),
                'route_fit':avg('answer','route_fit'),'fixture_internal_errors':sum(r['answer']['internal_error'] for r in group)})
    write(output_dir/'metrics.json',{'evaluation_kind':'offline_hash_fixture','rows':all_rows,'summaries':summaries,
        'provider_requests':0,'human_review_completed':False,'live_quality_confirmed':False,
        'comparisons':[['S0','S1','judge contract only'],['S1','S2','evidence selection only'],
            ['S2','tokens_only','old block algorithm, same numeric target; only counter changes'],
            ['tokens_only','S3a','structural child algorithm and new 300/800 sizes'],
            ['S3a','S3b_verified','same child corpus, parent context only'],['S3b_verified','S4','response routing only']],
        'limitations':['Hash vectors are not learned embeddings; rerank/generation/judge are transparent fixtures.',
            'Legacy context limit is 10000 UTF-8 bytes; new context is 3000 actual tokens. S3a/S3b share exactly the same corpus and budget.',
            'Sparse authored source judgments: unjudged sources are reported separately; nDCG treats unjudged as zero and is not exhaustive relevance truth.',
            'Probes were authored after implementation; holdout is family-disjoint but not independent. No model quality improvement claim.']})
    write(output_dir/'review_key_private.json',human)
    write(output_dir/'human_packets.json',[{k:v for k,v in h.items() if k!='variant_private'} for h in human])
    with (output_dir/'human_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['blind_id','usefulness_0_to_3','unsupported_claims','repeated_question_or_test','route_fit','reviewer','reason'])
        for h in human:w.writerow([h['blind_id'],'','','','','',''])
    print(json.dumps(summaries,ensure_ascii=True))

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',nargs=2);p.add_argument('--score-only',action='store_true');p.add_argument('--score-output',type=Path);args=p.parse_args()
    if args.worker: worker(*args.worker);return
    if not args.score_only:
        for variant in VARIANTS:
            for split in ('dev','holdout'):
                target=BASE/'offline'/variant/(split+'.json')
                if target.exists(): raise SystemExit('Output already exists; immutable comparison cannot be silently rerun.')
                subprocess.run([sys.executable,'-X','utf8',__file__,'--worker',variant,split],check=True,cwd=ROOT)
                print('Offline complete: '+variant+' / '+split,flush=True)
    score(args.score_output)

if __name__=='__main__':main()
