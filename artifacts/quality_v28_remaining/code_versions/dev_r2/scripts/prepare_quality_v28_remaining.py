"""Freeze fresh, family-disjoint V28-follow-up evaluation inputs and labels."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json, write_json, digest

DATA=ROOT/'eval'/'quality_v28_remaining'
RUN=ROOT/'artifacts'/'quality_v28_remaining'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if (DATA/'manifest.json').exists():
        raise SystemExit('Frozen follow-up suite exists; do not overwrite it.')
    DATA.mkdir(parents=True,exist_ok=True)
    pricing=read_json(DATA/'pricing.json')
    assert pricing['source_url']=='https://api.metisai.ir/api/v1/meta/providers/pricing'
    source_rows={row['id']:row for row in read_json(ROOT/'data'/'corpus_v3.sources.json')}
    source=source_rows['docs:2025']
    anchor='To avoid blocking your script, you can pass a callable to [`st.download_button`](/develop/api-reference/widgets/st.download_button) for on-demand download generation'
    start=source['text'].index(anchor); end=start+len(anchor)
    witness={'source_id':source['id'],'revision':source.get('revision'),
        'product_version':source.get('product_version'),'quote':anchor,'source_span':[start,end],
        'lines':[source['text'][:start].count('\n')+1,source['text'][:end].count('\n')+1]}

    specs=[
      ('D1','dev','report_favorite_design','feature_request',
       'Feature request: In the build-report list, let a reader optionally mark a report as a favorite and filter to favorites. Turning the option off must preserve the current list and ordering. Acceptance: when enabled, a marked report appears in the favorites filter; clearing the mark removes it from that filter without deleting the report. This describes desired behavior, not an existing API.',{},
       'Describe the request and an observable maintainer design decision. Preserve opt-in behavior and ordinary list order. Do not ask whether an API exists or claim that the current product lacks this capability.'),
      ('D2','dev','download_generation_callable_usage','usage_question',
       'Usage question: A large CSV takes several seconds to prepare in my Streamlit app. I have not pinned a Streamlit version. What documented pattern generates download data on demand for `st.download_button`? Explain the documented scope and show the source-version limitation; do not promise that it fixes every delay.',{},
       'Use the direct documented recommendation if retrieved and selected. Connect every technical statement to its own selected excerpt and keep the source version unknown. Do not turn the recommendation into a guaranteed performance fix.',[witness]),
      ('D3','dev','audio_capture_duration_diagnostic','bug',
       'Bug report: Streamlit 1.52.0, Python 3.12, Firefox on Windows. A 45-second recording made with `st.audio_input` plays back as about 8 seconds. I measured the input recording at 45 seconds before passing it to the app, repeated in a new session, and saw no failed browser request. Please give one new discriminating check for whether the returned audio data or the rendered player is shortened; do not state a cause.',
       {'streamlit_version':'1.52.0','python_version':'3.12','browser':'Firefox','os':'Windows'},
       'Do not repeat the recording, session, or network checks. Offer one specific measurement of the returned bytes/duration or player metadata and leave cause unknown.'),
      ('H1','holdout','build_report_favorites_feature','feature_request',
       'Feature request: Let reviewers save named views of the build-report queue. A saved view can hold selected status filters and a sort order. It is private to the reviewer, can be renamed or deleted, and must not change the underlying reports. Acceptance: reopening a saved view restores its filters and order; deleting the view leaves every report unchanged. This is a new design request, not a statement about current capabilities.',{},
       'Give a concrete proposal with privacy, non-destructive behavior, and a visible acceptance condition. Use an exact report excerpt only if it is relevant to a particular requested detail; no source can establish that this new capability already exists.'),
      ('H2','holdout','toast_visibility_after_rerun','bug',
       'Bug report: Streamlit 1.51.0, local Linux app, Firefox. A short `st.toast` notice disappears before it can be read when a page reruns after a button click. I reduced this to one page and recorded the screen; the console shows no error. Please suggest one new observation that separates the notice lifetime from the rerun timing. Do not infer a cause or ask me to repeat the reduced case.',
       {'streamlit_version':'1.51.0','os':'Linux','browser':'Firefox','deployment':'local'},
       'Ask for one genuinely new timing observation or propose a discriminating trace that is not already in the report. No source-dependent cause is currently established.')
    ]
    inputs={'dev':[],'holdout':[]}; labels={'dev':[],'holdout':[]}
    for spec in specs:
        cid,split,family,route,message,facts,expected,*witnesses=spec
        inputs[split].append({'id':cid,'initial_message':message,'initial_facts':facts,'initial_checks':[]})
        labels[split].append({'id':cid,'split':split,'family':family,'expected_route':route,
            'required_evidence':witnesses[0] if witnesses else [],'expected_behavior':expected,
            'origin':'Assistant-authored offline control; not a human or independent quality verdict',
            'previously_seen':False,'product_version':facts.get('streamlit_version')})
    dev_families={row['family'] for row in labels['dev']}
    holdout_families={row['family'] for row in labels['holdout']}
    assert dev_families.isdisjoint(holdout_families)
    write_json(DATA/'dev_inputs.json',inputs['dev'])
    write_json(DATA/'dev_labels.json',labels['dev'])
    write_json(DATA/'holdout_inputs.json',inputs['holdout'])
    write_json(DATA/'holdout_labels.json',labels['holdout'])
    protocol={'date':'2026-10-10','base_commit':subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'suite':'CasePilot V28 remaining defects; new synthetic families, held-out behavior labels excluded from product inputs',
        'variants':{'A':'v2','B':'v3'},'parent_context':False,'context_tokens':3000,
        'models':{'text_roles':'gpt-4.1-mini','query_embedding':'text-embedding-3-small'},
        'pricing_snapshot':'pricing.json','hard_cost_cap_usd':1.10,
        'estimated_cost_range_usd':[0.55,0.70],
        'estimated_text_tokens':{'input_max_approx':800000,'output_max_approx':100000},
        'production_path':'Agent.turn, live extraction, actual HybridRetriever over existing cached v2/v3 vectors, normal generation/repair and active semantic judge; no frozen candidates or vector injection',
        'development_cases':['D1','D2','D3'],'holdout_cases':['H1','H2'],
        'max_development_correction_rounds':2,'turns_per_round':6,
        'holdout_runs':4,'max_connection_retries':4,'max_calls_per_turn':8,
        'turn_cost_cap_usd':0.04,'max_provider_requests':208,'max_product_attempts':26,
        'phase_limits':{'development':{'requests':144,'usd':0.78},
            'holdout':{'requests':32,'usd':0.16},
            'connection_retry':{'requests':32,'usd':0.16}},
        'embedding_rebuild':False,'direct_stored_draft_probes':0,
        'criteria':{
            'report_quote':'Every rendered/persisted quote is code-copied from a current user-message snapshot with matching message_id, UTF-8 text hash, Unicode-codepoint [start,end), case revision and message role; empty is allowed when no relevant excerpt exists. A human reviewer also checks relevance to the specific feature detail.',
            'technical_coverage':'Every code-triggered technical candidate has a full contiguous assertion range, technical label and a source selected into that answer. No candidate may pass as procedure or with p=none. Deterministic code enforces candidate coverage, selected-source linkage, provenance-derived version checks and a same-unit visible limitation. The model must separately judge whole-claim support and relevance; blind human review remains necessary because semantic truth is not mechanically proven.',
            'preserved_safe_behavior':'Clear proposals remain requests, safe diagnostics remain fresh and single-target, and unsupported causes stay unknown.',
            'quality_success':'All four final holdout product runs pass contract, quote-lineage, per-unit source/support/version checks and human-blind content review; zero unsupported technical claims, repeated questions/tests, false product-presence/absence claims, or incomplete report quotes. Any failure means no overall quality-success claim.',
            'retrieval_metrics':'Report Recall@8 only against frozen exact source witnesses; report candidate and packed-context witness coverage, unknown/mismatched source-version counts, and context-token budget. nDCG@8 and irrelevant-candidate fraction stay null until blind pooled relevance grades are complete; unjudged candidates are never treated as irrelevant.',
            'answer_metrics':'Report structural/contract failures separately from content rejection; count product acceptance, per-unit technical candidate coverage, selected-output-source linkage, exact report-quote snapshots and display, route, model cost, provider requests, and human-blind usefulness/freshness review.',
            'report_separation':'Report retrieval metrics and answer/contract metrics separately; fixture, live product, and independent human review are separate evidence classes.'},
        'freeze_policy':'Run all development rounds before select. A correction round requires a recorded defect hypothesis and effective source change. Freeze selected code and its hash before the four holdout runs. Never tune, relabel, or repeat a quality claim on holdout outputs.',
        'limits':'The lexical candidate audit is a high-recall trigger, not a proof of entailment. Human/independent semantic review remains necessary; this small synthetic suite cannot establish general model quality.'}
    write_json(DATA/'protocol.json',protocol)
    files={name:sha(DATA/name) for name in ('dev_inputs.json','dev_labels.json','holdout_inputs.json',
        'holdout_labels.json','protocol.json','pricing.json')}
    manifest={'suite':'quality_v28_remaining','created_at':'2026-10-10',
        'base_commit':protocol['base_commit'],'files':files,
        'corpus_hashes':{name:sha(ROOT/'data'/name) for name in ('corpus_v2.json','corpus_v3.json','corpus_v3.sources.json')},
        'families':{'dev':sorted(dev_families),'holdout':sorted(holdout_families)},
        'source_witnesses':{'D2':witness}}
    write_json(DATA/'manifest.json',manifest)
    print('Frozen 3 development and 2 family-disjoint holdout cases; no provider calls.')


if __name__=='__main__':
    main()
