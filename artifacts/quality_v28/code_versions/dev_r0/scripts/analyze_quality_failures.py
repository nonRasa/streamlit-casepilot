"""Diagnostic counts from delivered outputs and trace findings, not quality labels."""
import collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from quality_result_files import result_paths

def main():
    folder=ROOT/'artifacts/quality_revision/final_evaluation'
    rows=read_json(folder/'answers.json'); result={}
    for variant in ('previous','revised'):
        outs=[r['output'] for r in rows if r['variant']==variant and r['split']=='test_fresh' and r['output']]
        result[variant]={'delivered':len(outs),'safe_fallbacks':sum(bool(o['validation_error']) for o in outs),
            'accepted':sum(not o['validation_error'] for o in outs),
            'citations':sum(len(o['summary']['sources']) for o in outs),
            'administrative_citations':sum(s['section'].lower() in ('checklist','additional context','related issues') for o in outs for s in o['summary']['sources']),
            'decisions':dict(collections.Counter(o['decision'] for o in outs))}
    findings=[]
    allouts=[r['output'] for r in rows if r['variant']=='revised' and r['output']]
    allouts += [o for s in read_json(result_paths(folder)[1]) for o in s['turns']]
    for out in allouts:
        for stage in out['pipeline']:
            if stage['stage']=='judge':
                findings += [{'case_id':out['case_id'],'attempt':stage.get('attempt'),'criterion':f['criterion'],'reason':f['reason']} for f in stage.get('findings',[])]
    result['revised_judge_findings']={'n':len(findings),'by_criterion':dict(collections.Counter(f['criterion'] for f in findings)),'records':findings}
    result['limitations']='Counts include retained fallback outputs. Fewer bad citations can result from withholding answers, not better diagnosis. Judge findings are model/code diagnostics, not independent semantic labels.'
    write_json(folder/'failure_analysis.json',result)
    print(canonical({k:v for k,v in result.items() if k!='revised_judge_findings'}))

if __name__=='__main__':main()
