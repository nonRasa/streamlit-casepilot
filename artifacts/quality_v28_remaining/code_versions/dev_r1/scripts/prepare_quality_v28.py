"""Freeze evaluator-only fresh families before response-quality tuning."""
import json, sys, subprocess, shutil, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json
from evaluate_quality_v25_live import ledger,sha
RUN=ROOT/'artifacts/quality_v28'
DATA=ROOT/'eval/quality_v28'

def main():
    if (DATA/'manifest.json').exists():raise SystemExit('Already frozen; never overwrite this evaluation.')
    DATA.mkdir(exist_ok=True);RUN.mkdir(exist_ok=True)
    sources={x['id']:x for x in read_json(ROOT/'data/corpus_v3.sources.json')}
    specs=[
      ('D1','dev','streamed_output_duplication','bug',
       'Bug report: Streamlit 1.49.0, Python 3.12, Chrome on Windows, local app. st.write_stream sometimes displays the final word twice. My generator logs each yielded chunk once; concatenating those chunks outside Streamlit gives the expected string. I already tested with no manual rerun and a fresh browser. Code:\n```python\ndef chunks():\n    yield "north "\n    yield "star"\nst.write_stream(chunks())\n```\nI need one specific next diagnostic, not a confirmed cause.',
       {'streamlit_version':'1.49.0','python_version':'3.12','deployment':'local'},None,None,
       'Ask for one genuinely new observation such as the browser console/network trace during the duplicate display. Do not ask for code, versions, fresh browser or generator logging already supplied; do not invent a streaming cause.'),
      ('D2','dev','chat_message_pinning_design','feature_request',
       'Feature request: let a viewer pin a chosen chat message so it stays visible while they scroll through the conversation. Pinning must be opt-in; ordinary unpinned messages keep the current display order. Acceptance: enabling the pin on one message keeps that message visible during scrolling, and unpinning restores ordinary scrolling. This is a proposed UI capability, not a claim about an existing API.',
       {},None,None,'Produce a concrete maintainer design proposal preserving opt-in pinning, message order and observable unpinning acceptance. No question about the clear goal and no invented current API availability.'),
      ('D3','dev','form_input_submission_batching','usage_question',
       'Usage question: I have two sliders and an expensive calculation. I want users to adjust both inputs before a single Submit button sends their changes to the backend. How should I group those inputs? I have not selected a Streamlit version yet; do not claim a version-specific guarantee.',
       {},'docs:forms','All changes made to a form will only be sent to the Python backend when the form itself is submitted.',
       'Explain the documented form grouping and submit behavior with a direct citation and visible unknown-version limitation. Asking only for a version instead of the documented concept is less useful.'),
      ('H1','holdout','theme_sidebar_inheritance','bug',
       'Bug report: Streamlit 1.49.0, local Windows app, Chrome. The body uses my configured custom text color but the sidebar text still looks like the default. I already restarted the server and tested a fresh browser. I use no custom CSS. Full theme config:\n```toml\n[theme]\nbase="light"\ntextColor="#123456"\n```\nMinimal app:\n```python\nimport streamlit as st\nst.write("body sample")\nst.sidebar.write("sidebar sample")\n```\nPlease give one new diagnostic or carefully qualified documented guidance; the cause is not established.',
       {'streamlit_version':'1.49.0','deployment':'local'},'docs:theming',
       'The sidebar is separately\nconfigurable from the main app for almost all theming options.',
       'Do not repeat restart, fresh browser, config/code or CSS question. Use qualified theming evidence or request a concrete new observation (computed sidebar color/selected theme) without asserting a proved cause.'),
      ('H2','holdout','calendar_week_number_design','feature_request',
       'Feature request: optionally display ISO week numbers beside the calendar rows in the date picker. Keep date selection values and the current calendar layout unchanged when the option is off. Acceptance: with the option on, each visible calendar week has its ISO week number; with it off, the calendar looks and selects dates as before. Please prepare the design request; I am not reporting an existing API.',
       {},None,None,'Propose the opt-in ISO-week labels with unchanged off behavior and observable acceptance; no redundant clarification or unsupported availability claim.'),
      ('H3','holdout','session_value_serializability_validation','usage_question',
       'Usage question: during development I want Session State to reject values that cannot be pickled, for example a lambda, instead of discovering this only in another execution environment. Which documented setting enables that validation? I have not pinned a Streamlit version. I am asking about validation, not cross-session persistence.',
       {},'docs:serializable-session-state',
       'To that end, Streamlit provides a `runner.enforceSerializableSessionState` [configuration option](/develop/concepts/configuration) that, when set to `true`, only allows pickle-serializable objects in Session State.',
       'Name the documented validation option with direct evidence and unknown-version limitation; do not turn validation into a persistence/security guarantee.'),
    ]
    inputs=[];labels=[]
    for cid,split,family,kind,message,facts,sid,anchor,expected in specs:
        inputs.append({'id':cid,'split':split,'initial_message':message,'initial_facts':facts,'initial_checks':[]})
        witnesses=[]
        if sid:
            source=sources[sid];start=source['text'].index(anchor);end=start+len(anchor)
            witnesses=[{'source_id':sid,'revision':source['revision'],'product_version':source.get('product_version'),
                'quote':anchor,'source_span':[start,end],'lines':[source['text'][:start].count('\n')+1,source['text'][:end].count('\n')+1]}]
        labels.append({'id':cid,'split':split,'family':family,'expected_route':kind,'required_evidence':witnesses,
            'expected_behavior':expected,'origin':'Assistant authored synthetic scenario and source-linked reference; not human or independent',
            'previously_seen':False,'product_version':facts.get('streamlit_version')})
    protocol={'date':'2026-10-10','baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
      'variants':{'A':'v2','B':'v3_child'},'parent_context':False,'context_tokens':3000,
      'models':['gpt-4.1-mini','text-embedding-3-small'],'rewrite':False,
      'production_path':'Agent.turn with real extraction-generated retrieval query, actual HybridRetriever and model rerank; no candidate/vector injection',
      'dev_cases':['D1','D2','D3'],'holdout_cases':['H1','H2','H3'],'max_dev_correction_rounds':2,
      'max_connection_retries':4,'max_stored_draft_probes':4,
      'freeze_policy':'Holdout inputs and reference witnesses frozen before fresh tuning. No tuning/relabeling/repeated freshness claim after holdout results.',
      'family_definition':'Failure mechanism/request behavior, not API name alone. Fresh authored scenarios; nearby broad Streamlit domains may share documents with earlier corpora.',
      'acceptance':{'contract_valid_rate':1.0,'valid_citations_rate':1.0,'unsupported_claims':0,'repeated_question_or_test':0,
        'route_fit_rate':1.0,'usefulness_min_per_case':2,'context_budget_ok_rate':1.0,'independent_or_human_review_required_for_default_change':True},
      'evaluation_origin':'Assistant case review is reported separately from model verdict, deterministic guard, and independent/human review.'}
    for split in ('dev','holdout'):
        write_json(DATA/(split+'_inputs.json'),[r for r in inputs if r['split']==split])
        write_json(DATA/(split+'_labels.json'),[r for r in labels if r['split']==split])
    write_json(DATA/'protocol.json',protocol)
    write_json(DATA/'manifest.json',{'files':{p.name:sha(p) for p in sorted(DATA.glob('*.json'))},
        'sources_sha256':sha(ROOT/'data/corpus_v3.sources.json'),'corpus_hashes':{v:sha(ROOT/('data/corpus_'+v+'.json')) for v in ('v2','v3')},
        'preregistered_before_tuning':True})
    target=RUN/'baseline';target.mkdir(exist_ok=True);hashes={}
    for directory in ('src','schemas','policies'):
        for p in (ROOT/directory).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts:continue
            relative=p.relative_to(ROOT);out=target/'code'/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out);hashes[str(relative)]=sha(p)
    write_json(target/'manifest.json',{'commit':protocol['baseline_commit'],'files':hashes,'provider_requests':0})
    before=ledger()
    write_json(RUN/'authorization.json',{'campaign':'quality_v28_20261010','approval':'Human explicitly approved this exact scope up to $1.20 in this chat on 2026-10-10',
      'hard_cap_usd':1.20,'max_requests':228,'max_query_embeddings':28,'max_answer_turns':28,
      'max_development_repeat_turns':12,'max_dev_correction_rounds':2,'max_connection_retries':4,'max_stored_draft_probes':4,
      'phase_limits':{'answers':{'requests':224,'usd':1.12},'probes':{'requests':4,'usd':.08}},
      'cost_before':{k:before[k] for k in ('requests','confirmed_usd','uncertain_reserved_usd','charged_or_reserved_usd')},
      'manifest_sha256':sha(DATA/'manifest.json'),'pricing_sha256':sha(RUN/'pricing.json')})
    print('Six fresh cases/references, protocol, baseline source and approved limits frozen; no provider requests.')

if __name__=='__main__':main()
