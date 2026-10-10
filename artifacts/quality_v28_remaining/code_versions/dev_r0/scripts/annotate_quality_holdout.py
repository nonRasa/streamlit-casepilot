"""Prospective initial-report labels; never passed into model prompts."""
import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import read_json,write_json,require,utcnow

NOTES={
'GH13466':('feature','Deferred download exception reporting back to script thread. Goal already explicit. Request for existing try/catch or session state logging repeats known limitation. Qualify implementation and propose an observable main-thread error-reporting acceptance condition.'),
'GH13341':('bug','Tabs reset when widgets ABOVE are added/removed; below control and label-only change already tested. Full MRE and versions provided. Seek a genuinely different controlled condition; do not request supplied MRE/version or call related older issues proof of cause.'),
'GH13111':('bug','Intermittent Cloud startup healthcheck EOF; restarts sometimes help. Full startup code/log not supplied. Ask one targeted startup diagnostic. Environment may describe local development; do not conclude OOM from app ingredients.'),
'GH13487':('bug','date_input max_value today accepted at runtime but annotation reportedly rejects it; short MRE already provided. Exact checker diagnostic/version missing. Do not claim min_value affected or released fix without evidence.'),
'GH13307':('bug','None column in data_editor becomes list despite explicit TextColumn already tried. Versions and MRE provided. A genuinely new data-seeding or version control may help; referenced PR is a hypothesis, not established cause.'),
'GH13242':('feature','Arrow PyCapsule protocols and low-copy interoperability requested explicitly; converter examples provided. A maintainer-ready protocol compatibility/measurement condition is useful; do not guarantee zero-copy or invent current support.'),
'GH13068':('feature','Compact upload-button feature requested; proposed API is not current confirmed API. Goal explicit; propose observable file-picker/content acceptance condition, not a question asking goal back.'),
'GH12905':('bug','Small PDF uploads intermittently disconnect Android WebSocket. Full MRE, logs, environment and no-proxy configuration given. Ask a genuinely new desktop/mobile comparison or targeted event diagnostic, not supplied size/proxy/MRE/version. Avoid unproved OOM or disabling XSRF.'),
'GH12477':('feature','Camera/gallery capture from chat_input and file_uploader requested. Goal explicit. Propose device-capture behavior plus fallback acceptance condition; do not invent existing capture parameter.'),
'GH13165':('bug','CachedForwardMsg MISS when returning to app, exact hash provided but no versions/MRE. One targeted missing diagnostic is reasonable. Error name alone does not prove cache_data function use or root cause.'),
'GH13065':('feature','Streamlit-specific Ruff rules requested with state/cache examples. Goal explicit; propose concrete lint-rule behavior and false-positive acceptance condition, not assumed existing plugin.'),
'GH12800':('bug','Cloud dpkg overwrite conflict between libodbc2 Debian and Microsoft libodbc1 fully logged; trivial packages.txt/app supplied. Platform packaging escalation with exact conflicting package/path is useful. No force overwrite, irrelevant browser/Python question or repeated minimal example.'),
'GH13332':('feature','Keyboard access to dataframe header menu requested explicitly. Describe observable keyboard focus/menu access and usability review, not request feature goal back or invent API.'),
'GH13189':('bug','Collapsed sidebar artifact with full MRE and exact nightly 1.51.1.dev20251130 supplied. A new stable/nightly or zoom control can help; do not silently treat nightly as stable or repeat MRE request. Attached image not inspected.'),
'GH13096':('feature','Responsive topbar background requested, wide/narrow behavior and top-navigation interaction explicit. Propose observable responsive behavior and usability review; no unsupported CSS API or released-fix claim.')}

def main():
    target=ROOT/'eval/quality_cases.json'; require(not target.exists(),'exists','برچسب آزمون بازنویسی نمی‌شود.')
    candidates=read_json(ROOT/'eval/quality_candidates.json')
    wanted={'GH9218','GH11528','GH12607','GH14593','GH14710'}
    dev=[dict(x,split='dev') for x in read_json(ROOT/'eval/v2_final_cases.json') if x['id'] in wanted]
    require(len(dev)==5 and {x['id'] for x in candidates}==set(NOTES),'invalid_cases','پرونده‌ها ناسازگارند.')
    fresh=[]
    for row in candidates:
        kind,note=NOTES[row['id']]
        fresh.append(dict(row,category=kind,allowed_decisions=['ask','escalate'],oracle_note=note,
                          annotation_provenance='AI-authored initial-text-only before final inference; no gold labels in prompts'))
    plans=copy.deepcopy(read_json(ROOT/'eval/v2_final_scenarios.json'))
    new_ids=['GH11528','GH14710','GH9218','GH12607','GH14593','GH13341','GH12905','GH13165','GH13189','GH13111']
    for i,(plan,cid) in enumerate(zip(plans,new_ids),1):
        plan.update(id=f'QS{i:02d}',case_id=cid,synthetic_followups=True,
                    limitation='Operational synthetic corrections may contradict real initial report intentionally; not actual reporter follow-ups or human approvals.')
    write_json(target,dev+fresh); write_json(ROOT/'eval/quality_scenarios.json',plans)
    write_json(ROOT/'artifacts/quality_revision/prospective_annotations.json',{'at':utcnow(),'cases':15,'before_final_inference':True,'notes':NOTES})
    print('Prospective annotations and synthetic scenarios prepared:',len(dev+fresh),len(plans))

if __name__=='__main__': main()
