"""Freeze family-disjoint inputs and evaluator-only labels before scoring.

These are authored diagnostic probes over the existing snapshot, not a random
sample and not an independent human-annotated benchmark. No labels enter SUT.
"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json,write_json,digest

def prepare():
    base=ROOT/'eval/quality_v27'
    if (base/'manifest.json').exists(): raise SystemExit('Evaluation already frozen.')
    sources={r['id']:r for r in read_json(ROOT/'data/corpus_v3.sources.json')}
    # id, split, family, report, product version, expected route, evidence, exact anchor, behavior
    specifications=[
      ('D01','dev','cache_serialization','Bug report: st.cache_data raises a pickle error. Python 3.11. My class is already included: class Payload: pass. I tested pickle outside Streamlit and it works. What fresh diagnostic would isolate this?', '1.49.0','bug','api:cache_data','value of a cached function must be pickleable.', 'Distinguish a serialization requirement from the cause of this report; do not request the supplied class or repeat the outside-pickle test.'),
      ('D02','dev','upload_limit','How do I configure the maximum file upload size in Streamlit 1.49.0? I already set server.maxUploadSize=400.','1.49.0','usage_question','api:file_uploader','server.maxUploadSize','Explain the documented setting without asking for its already supplied value.'),
      ('D03','dev','dialog_resize_proposal','Feature request: add an option to resize a dialog by dragging its edge. Keep the default fixed size unchanged. Acceptance: dragging changes width only when the option is enabled.',None,'feature_request',None,None,'Summarize the requested opt-in behavior, unchanged default and visible acceptance; do not invent an existing resize API or ask for an implementation.'),
      ('D04','dev','session_disconnect','Bug report: state disappears after a browser disconnect. The Streamlit version is unknown. What evidence would distinguish a new session from a rerun?',None,'bug','docs:session-state','Session State exists for as long as the tab is open','Treat the source version as unknown; do not prove a cause from topic similarity; ask one discriminating missing detail.'),
      ('D05','dev','proprietary_extension','A proprietary extension named MoonBridge emits EZX991 with an undocumented binary. Please help.',None,'unknown',None,None,'Identify a precise missing observation; disclose absent relevant evidence and do not fabricate product behavior.'),
      ('D06','dev','forms_batching','How can I batch multiple widget inputs using st.form and submit them together? I have not supplied a product version.',None,'usage_question','docs:forms','Forms make it easy to batch user input into a single rerun.','Use the relevant form behavior with explicit unknown version; do not claim historical compatibility.'),
      ('H01','holdout','url_parameters','How do I read repeated URL query parameters through st.query_params? The installed version has not been recorded.',None,'usage_question','docs:query_params','keys may be repeated in an app\'s URL.','Explain the relevant repeated-key mechanism without pretending the installed version is known.'),
      ('H02','holdout','page_configuration_version','How can I change page_title twice in one script run? Our deployed Streamlit version is 1.18.0.','1.18.0','usage_question','api:set_page_config','This command can be called multiple times in a script run','The 1.49.0 API snapshot cannot establish 1.18.0 behavior; expose the mismatch rather than recommend an unsupported API behavior.'),
      ('H03','holdout','static_media','Bug report: a static image URL fails. My config already contains [server] enableStaticServing=true and I tested the exact URL in a fresh browser; it still returns 404.',None,'bug','docs:static-file-serving','enableStaticServing = true','Use the serving documentation; ask for an unprovided path or a new discriminating check, not the already supplied setting/browser experiment.'),
      ('H04','holdout','chart_export_proposal','Feature request: offer a keyboard-triggered export of the currently selected chart region. Preserve the existing mouse interaction. Acceptance: a keyboard action exports only the selected region.',None,'feature_request',None,None,'Provide a request-only proposal, preserved interaction and observable acceptance. No claim that an export shortcut already exists.'),
      ('H05','holdout','theme_scope_combined','Bug report: the theme text color changed unexpectedly. Feature request: add an independent sidebar contrast control. I need to separate the regression from this proposed option.',None,'mixed','docs:theming','Streamlit themes are defined using configuration options','Preserve both requests, keep the proposed control distinct from documented theme settings, and clarify only a detail affecting the next decision.'),
      ('H06','holdout','hardware_driver','The undocumented vendor driver ZephyrQ raises ZX77 on a private device. Please help determine what information to collect.',None,'unknown',None,None,'State that no relevant supplied source establishes this private driver error; request one discriminating observation.'),
    ]
    inputs=[]; labels=[]
    for cid,split,family,report,version,route,sid,anchor,behavior in specifications:
        facts={'streamlit_version':version} if version else {}
        inputs.append({'id':cid,'split':split,'family':family,'initial_message':report,'initial_facts':facts,'initial_checks':[]})
        witnesses=[]
        if sid:
            source=sources[sid]
            if anchor not in source['text']: raise ValueError('Missing exact witness: '+cid)
            a=source['text'].index(anchor)
            witnesses=[{'source_id':sid,'quote':anchor,'source_span':[a,a+len(anchor)],'revision':source['revision'],'product_version':source.get('product_version')}]
        distractors=[s for s in ('docs:theming','docs:forms','docs:static-file-serving','api:file_uploader','docs:query_params') if s!=sid]
        labels.append({'id':cid,'split':split,'family':family,'expected_route':route,'expected_behavior':behavior,
                       'relevance':{sid:3} if sid else {},'judged_irrelevant_source_ids':distractors,
                       'required_evidence':witnesses,'evidence_required_for_proposal':False if route=='feature_request' else bool(sid),
                       'human_review':None,'label_origin':'author-authored snapshot probe, not independent annotation'})
    families={split:{x['family'] for x in inputs if x['split']==split} for split in ('dev','holdout')}
    assert not families['dev'] & families['holdout']
    for split in families:
        write_json(base/(split+'_inputs.json'),[x for x in inputs if x['split']==split])
        write_json(base/(split+'_labels.json'),[x for x in labels if x['split']==split])
    write_json(base/'manifest.json',{'input_hash':digest(inputs),'label_hash':digest(labels),
        'families':{k:sorted(v) for k,v in families.items()},'source_snapshot_hash':digest(list(sources.values())),
        'frozen_before_scoring':True,'authored_after_implementation':True,
        'limitation':'Protocol and baseline controls preceded implementation; new family-disjoint probes were authored after implementation, before scoring. They cannot establish unbiased improvement.',
        'sut_input_allowlist':['id','initial_message','initial_facts','initial_checks'],
        'acceptance':{'contract_valid_rate':1.0,'unsupported_claims':0,'repeated_questions_or_tests':0,'route_fit_rate':1.0,'human_usefulness_min_per_case':2,'human_usefulness_scale':[0,1,2,3]}})
    print('Frozen 6 development and 6 holdout probes, no shared families.')

if __name__=='__main__':prepare()
