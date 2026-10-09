"""Freeze expanded evaluation, protocol, costs and active judge input offline."""
import json,sys,subprocess,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest,canonical
from casepilot.hybrid import embedding_text
from casepilot.embeddings import normalize
from casepilot.tokenization import count_tokens
from casepilot.parent_child import chunks
from casepilot.compact_review import packet,schema,PROMPT
from casepilot.review_contract import review_spans
from casepilot.schema_preflight import check_provider_schema
from evaluate_quality_v25_live import ledger,sha
RUN=ROOT/'artifacts/quality_v27/completion_20261010'
DATA=ROOT/'eval/quality_v27_completion'


def source_witness(sources,sid,anchor):
    s=sources[sid]; a=s['text'].index(anchor)
    return {'source_id':sid,'quote':anchor,'source_span':[a,a+len(anchor)],
            'revision':s['revision'],'product_version':s.get('product_version'),
            'source_sha256':digest(s['text']),
            'lines':[s['text'][:a].count('\n')+1,s['text'][:a+len(anchor)].count('\n')+1]}


def prepare():
    if (DATA/'manifest.json').exists():
        print('Already frozen; no input or label overwrite.'); return
    sources={s['id']:s for s in read_json(ROOT/'data/corpus_v3.sources.json')}
    inputs=sum([read_json(ROOT/('eval/quality_v27/'+s+'_inputs.json')) for s in ('dev','holdout')],[])
    labels=sum([read_json(ROOT/('eval/quality_v27/'+s+'_labels.json')) for s in ('dev','holdout')],[])
    # Broad topic families prevent near-neighbor split leakage. Existing probes
    # remain marked as previously seen; newly authored holdout is frozen now.
    families={'D01':'caching','D02':'uploads','D03':'dialog_design','D04':'session_widgets',
              'D05':'private_extension','D06':'rerun_control','H01':'url_parameters',
              'H02':'configuration','H03':'static_assets','H04':'chart_design',
              'H05':'configuration','H06':'private_hardware'}
    for i,l in zip(inputs,labels):
        i['family']=l['family']=families[i['id']]; l['previously_seen']=True
        l['required_evidence']=[source_witness(sources,w['source_id'],w['quote']) for w in l['required_evidence']]
    specs=[
      ('D07','dev','caching','How should I handle thread safety for an object shared by st.cache_resource? Streamlit 1.49.0.', '1.49.0','usage_question','api:cache_resource','must be thread-safe because they can be accessed from multiple threads','Explain the documented shared-resource requirement; do not diagnose a race without an observation.'),
      ('D08','dev','rerun_control','How can st.fragment rerun a portion of the app instead of the full script? Installed Streamlit version is unknown.',None,'usage_question','docs:fragments','introduced fragments to allow rerunning a portion of your code instead of your full script','Explain the fragment execution scope; keep installed compatibility unknown.'),
      ('D09','dev','session_widgets','Bug report: st.button returns False on the rerun after a click. I already logged both return values. Is this expected? Streamlit version unknown.',None,'bug','docs:button-behavior-and-examples','They return `True` on the script rerun resulting from their click and immediately return to `False` on the next script rerun.','Distinguish documented transient button state from a proven defect; do not repeat logging.'),
      ('D10','dev','session_widgets','How do I make Session State reject objects that cannot be pickled? Version is not recorded.',None,'usage_question','docs:serializable-session-state','only allows pickle-serializable objects in Session State','Explain the serialization option, without claiming it caused a report.'),
      ('D11','dev','session_widgets','How do widgets isolate interactions between different users? The version is unknown.',None,'usage_question','docs:widget-behavior',"The actions of one user don't affect the widgets of any other user.",'Use the exact user-isolation evidence, with unknown version applicability.'),
      ('D12','dev','uploads','How can the file uploader accept several uploaded files? Streamlit 1.49.0; I already use type=["csv"].','1.49.0','usage_question','api:file_uploader','accept_multiple_files','Describe the documented argument; do not ask for the already supplied type filter.'),
      ('H07','holdout','navigation','How do I execute the page returned by st.navigation? Streamlit 1.49.0.','1.49.0','usage_question','api:navigation','Call ``st.navigation`` in your entrypoint file to define the available','Explain entrypoint and returned-page execution using exact evidence.'),
      ('H08','holdout','navigation','How can I place common elements around multiple pages with st.Page and st.navigation? Version not supplied.',None,'usage_question','docs:page-and-navigation','your entrypoint file acts like a page router','Explain the entrypoint frame; preserve unknown compatibility.'),
      ('H09','holdout','table_editing','Which should I use to interactively edit tabular data, st.dataframe or st.data_editor? Version unknown.',None,'usage_question','docs:dataframes','If you want to interactively edit data, use [st.data_editor]','Use the documented distinction; no fabricated editing API.'),
      ('H10','holdout','pinned_layout','Bug report: I placed st.bottom inside st.sidebar and got an error. I already tested it in the main area and that worked. Version unknown.',None,'bug','docs:bottom','`st.bottom` is only available in the **main app area**.','Explain the documented scope without repeating the main-area experiment or claiming a bug fix.'),
      ('H11','holdout','configuration','How do global and project config.toml values combine? I already have both files; the project sets a different theme. Version unknown.',None,'usage_question','docs:config-toml','gives precedence to the working-directory configuration','Explain precedence, without asking whether both files exist.'),
      ('H12','holdout','app_testing','How do I name pytest test files for Streamlit app tests? No installed version recorded.',None,'usage_question','docs:get-started','Name your test scripts of the form','Use the app-testing naming example and preserve unknown version.'),
    ]
    for cid,split,family,message,version,route,sid,anchor,behavior in specs:
        inputs.append({'id':cid,'split':split,'family':family,'initial_message':message,
                       'initial_facts':{'streamlit_version':version} if version else {},'initial_checks':[]})
        labels.append({'id':cid,'split':split,'family':family,'expected_route':route,'expected_behavior':behavior,
                       'relevance':{sid:3},'judged_irrelevant_source_ids':[],
                       'required_evidence':[source_witness(sources,sid,anchor)],'previously_seen':False,
                       'human_review':None,'label_origin':'assistant-authored exact snapshot probe; not independent or human'})
    assert len(inputs)>=20 and sum(bool(l['required_evidence']) for l in labels)>=12
    fs={s:{i['family'] for i in inputs if i['split']==s} for s in ('dev','holdout')}; assert not fs['dev']&fs['holdout']
    # Select answers before any fresh live results, covering both splits,
    # feature/bug/usage/mismatch/insufficient cases. No holdout rerun tuning.
    chosen=['D01','D03','D05','H02','H03','H09']
    protocol={'date':'2026-10-10','variants':{'A':'v2','B':'v3_child','C':'v3_bounded_parent'},
        'context_budget_tokens':3000,'k':5,'initial_candidates':8,
        'fixed_components':{'models':['gpt-4.1-mini','text-embedding-3-small'],'dense':True,'mmr':True,
                            'quality':True,'rrf_k':60,'mmr_lambda':.7,'rerank':True,'rewrite':False},
        'answer_cases':chosen,'max_development_repeat_turns':6,'max_contract_attempts':3,
        'retrieval_scope':'Raw hybrid retrieval first; reranking measured separately during real answers.',
        'BC_control':'Same persisted query vector and candidate list, identical extraction/rerank inputs/cache, only parent_context differs.',
        'acceptance':{'contract_valid_rate':1.0,'unsupported_claims':0,'repeated_questions_or_tests':0,
                      'route_fit_rate':1.0,'usefulness_min_per_case':2,'judgment_coverage_min':.9,
                      'recall_regression_max':0,'witness_coverage_gain_min':.1,
                      'type_witness_regression_max':.1,'context_budget_ok_rate':1.0,
                      'independent_or_human_usefulness_required_for_default_change':True},
        'metrics':['Recall@5','pooled nDCG@5 only fully judged top-k','judgment coverage','exact witness coverage',
                   'irrelevant fraction among judged','version relation','context tokens','contract validity',
                   'unsupported/repeated findings','route fit','usefulness','cost'],
        'judgment_origin':'Assistant/model labels are not human or independent.',
        'holdout_policy':'Freeze before fresh tuning. Old H01-H06 are previously seen diagnostic cases; new H07-H12 are fresh authored holdout.',
        'unjudged_policy':'grade=null, ordinary nDCG=null when top-k not fully judged; never map missing judgments to grade 0.'}
    for split in fs:
        write_json(DATA/(split+'_inputs.json'),[i for i in inputs if i['split']==split])
        write_json(DATA/(split+'_labels.json'),[l for l in labels if l['split']==split])
    write_json(DATA/'protocol.json',protocol)
    write_json(DATA/'manifest.json',{'input_hash':digest(inputs),'label_hash':digest(labels),'protocol_hash':digest(protocol),
        'source_snapshot_hash':digest(list(sources.values())),'families':{s:sorted(fs[s]) for s in fs},
        'counts':{'total':len(inputs),'dev':12,'holdout':12,'exact_witness_cases':sum(bool(l['required_evidence']) for l in labels)},
        'sut_input_allowlist':['id','initial_message','initial_facts','initial_checks'],
        'frozen_before_new_tuning':True,'independent_annotation':False,
        'files':{p.name:sha(p) for p in DATA.glob('*.json') if p.name!='manifest.json'}})
    print('Frozen 24 probes; 20 exact-witness cases; six newly authored holdout families.')


def preflight():
    prepare(); rows=read_json(ROOT/'data/corpus_v3.json');sources=read_json(ROOT/'data/corpus_v3.sources.json')
    by={s['id']:s for s in sources}; recomputed={s['id']:chunks(s) for s in sources}
    assert digest(rows)==read_json(ROOT/'data/corpus_v3.manifest.json')['corpus_hash']
    assert digest(rows)==digest(sum([recomputed[s['id']] for s in sources],[]))
    ids=set(); oversized=[]
    for r in rows:
        assert r['id'] not in ids;ids.add(r['id']);s=by[r['source_id']]
        for part in (r,r['parent']):
            a,b=part['source_span'];assert part['text']==s['text'][a:b]
            assert part['sha256']==digest(part['text']) and part['source_sha256']==digest(s['text'])
            assert part['token_count']==count_tokens(part['text'],encoding=part['chunk_config']['encoding'])
            for h in part['header_spans']:assert h['text']==s['text'][slice(*h['source_span'])]
        assert r['parent_id']==r['parent']['id']
        assert r['parent']['source_span'][0]<=r['source_span'][0]<r['source_span'][1]<=r['parent']['source_span'][1]
        if r['oversized_block']:oversized.append({'id':r['id'],'tokens':r['token_count'],'preserved':True})
    item=read_json(ROOT/'artifacts/quality_v27/same_draft_probe/input.json')
    spans=review_spans(item['state'],item['evidence'],item['answer']['claims']);c,public=packet(item['envelope'],spans)
    jp={'facts':item['state']['facts'],'experiments':item['state']['experiments'],
        'completed_checks':item['state'].get('checks',[]),'history_complete':True,
        'decision':item['answer']['decision'],'citations':item['answer']['claims'],
        'spans':spans,'draft':item['envelope'],'compact_contract':public}
    wire=schema(c);check_provider_schema(wire)
    payload={'model':'gpt-4.1-mini','messages':[{'role':'system','content':PROMPT},{'role':'user','content':canonical(jp)}],
             'max_tokens':1600,'response_format':{'type':'json_schema','json_schema':{'name':'casepilot_judge','strict':True,'schema':wire}}}
    size=len(canonical(payload).encode());reserve=((size+500)*.44+1600*1.76)*1.2/1e6
    assert size<=45000 and reserve<=.02
    texts=list(dict.fromkeys(normalize(embedding_text(r)) for r in rows));batches=[];batch=[]
    for text in texts:
        if batch and (len(batch)>=32 or len(canonical(batch+[text]).encode())>32000):batches.append(batch);batch=[]
        batch.append(text)
    if batch:batches.append(batch)
    write_json(RUN/'judge_input.json',item);write_json(RUN/'judge_preflight.json',{'input_hash':digest(item),
        'schema':wire,'packet':jp,'prompt':PROMPT,'request_hash':digest(payload),
        'input_tokens':count_tokens(canonical(payload),encoding='o200k_base')+128,'bytes':size,'reservation_usd':reserve})
    write_json(RUN/'preflight.json',{'provider_requests':0,'v3_rows':len(rows),'unique_texts':len(texts),
        'structural_validation':'exact reconstruction / hashes / spans / tokens / stable IDs / parent linkage passed',
        'oversized_atomic_blocks':oversized,'embedding_batches':len(batches),
        'embedding_tokens':sum(count_tokens(t,encoding='cl100k_base') for t in texts),
        'embedding_estimate_usd':sum(count_tokens(t,encoding='cl100k_base') for t in texts)*.022/1e6,
        'active_code_hash':digest({str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src').rglob('*.py'))}),
        'corpus_hashes':{v:sha(ROOT/('data/corpus_'+v+'.json')) for v in ('v2','v3')},
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()})
    print('Offline structural and active-judge payload preflight passed; zero provider requests.')

if __name__=='__main__':preflight()
