"""Read-only catalogue of saved result nodes across repository artifacts."""
import sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json
from evaluate_quality_v25_live import sha

def main():
    rows=[];aggregates=[];unreadable=[]
    for path in sorted((ROOT/'artifacts').rglob('*.json')):
        if any(x in path.parts for x in ('code','code_versions','baseline','cache')):continue
        if path.name=='saved_execution_catalog.json':continue
        try:data=read_json(path)
        except (ValueError,UnicodeError):unreadable.append(str(path.relative_to(ROOT)));continue
        nodes=[('',data)] if isinstance(data,dict) else [('/'+str(i),x) for i,x in enumerate(data)] if isinstance(data,list) else []
        for pointer,node in nodes:
            if not isinstance(node,dict):continue
            if not any(k in node for k in ('output','failure','validation_error','model_calls')):
                if any(k in node for k in ('results','turns','packets','rows')):aggregates.append({'file':str(path.relative_to(ROOT)),'pointer':pointer})
                continue
            out=node.get('output') or {};out=out if isinstance(out,dict) else {}
            rows.append({'file':str(path.relative_to(ROOT)),'pointer':pointer,'sha256':sha(path),
                'id':node.get('id',node.get('case_id',out.get('case_id'))),'mode':node.get('mode',out.get('mode')),
                'stage':node.get('stage'),'failure':node.get('failure') or node.get('validation_error') or out.get('validation_error'),
                'agent_output_present':bool(out or 'model_calls' in node),
                'classification_origin':'Metadata only; this catalogue does not infer quality or count aggregates as independent executions.'})
    write_json(ROOT/'artifacts/quality_v28/saved_execution_catalog.json',{'result_nodes':rows,'aggregate_files':aggregates,
        'counts_by_artifact_family':dict(collections.Counter(Path(x['file']).parts[1] for x in rows)),
        'unreadable_json_files':unreadable,'scope':'All repository artifacts with identifiable saved result metadata; code archives/caches excluded. Focused V27 forensic inventory remains separate.',
        'provider_requests':0})
    print({'saved_result_nodes':len(rows),'aggregate_metadata_nodes':len(aggregates),'unreadable_json_files':len(unreadable),'provider_requests':0})

if __name__=='__main__':main()
