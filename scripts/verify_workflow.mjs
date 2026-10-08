// Validate the exported n8n Code contracts without contacting n8n or a model.
import fs from 'node:fs';
const workflowPath=process.argv[2]||'workflows/casepilot_main.json';
const outputPath=process.argv[3]||'artifacts/quality_v22/workflow_verification.json';
const workflow=JSON.parse(fs.readFileSync(workflowPath,'utf8'));
const audit=workflow.nodes.find(n=>n.name==='Turn Pipeline Contract');
const check=new Function('$json',audit.parameters.jsCode);
const checks=[];
function test(name,fn){try{fn();checks.push({check:name,passed:true});}catch(error){checks.push({check:name,passed:false});}}
function requireValue(ok){if(!ok)throw new Error('assertion');}
const safe={statusCode:200,body:{method:'final',architecture:'v2',quality_revision:'v2.2-quality',mode:'live',pipeline:[],model_calls:5,repair_count:0,validation_error:null,
  reviewed_draft:{draft_version:'current'},review_failures:[],
  proposal:{id:'proposal',hash:'digest'},judge:{verdict:'accept',draft_version:'current'},summary:{sources:[],handoff:{maintainer_action:'review context'}},decision:'ask'}};
test('accepted model draft passes',()=>requireValue(check(structuredClone(safe))[0].json.body.proposal.id==='proposal'));
test('safe escalation passes',()=>{const x=structuredClone(safe);x.body.validation_error='judge_rejected';x.body.decision='escalate';x.body.judge=null;requireValue(check(x).length===1);});
for(const [name,mutate] of [
  ['missing judge',x=>x.body.judge=null],['too many calls',x=>x.body.model_calls=9],
  ['second repair',x=>x.body.repair_count=2],['legacy final',x=>x.body.architecture='v1'],
  ['unsafe fallback',x=>x.body.validation_error='judge_rejected'],['missing scoped proposal',x=>x.body.proposal=null]
  ,['old quality contract',x=>x.body.quality_revision='v2.1-quality'],['stale review',x=>x.body.judge.draft_version='old']
])test('reject '+name,()=>{const x=structuredClone(safe);mutate(x);let rejected=false;try{check(x);}catch{rejected=true;}requireValue(rejected);});
test('contract error requires trace',()=>{const x=structuredClone(safe);Object.assign(x.body,{validation_error:'judge_contract_error',decision:'escalate'});let rejected=false;try{check(x);}catch{rejected=true;}requireValue(rejected);x.body.review_failures=[{kind:'judge_contract'}];requireValue(check(x).length===1);});
test('generic escalation without handoff rejected',()=>{const x=structuredClone(safe);x.body.decision='escalate';x.body.summary.handoff=null;let rejected=false;try{check(x);}catch{rejected=true;}requireValue(rejected);});
test('HTTP error preserved',()=>requireValue(check({statusCode:503,body:{error:'budget_exhausted'}})[0].json.statusCode===503));
for(const node of workflow.nodes.filter(n=>n.type.endsWith('.code'))){new Function('$json',node.parameters.jsCode);}
test('graph keeps human review separate',()=>requireValue(workflow.connections['Turn Pipeline Contract'].main[0][0].node==='Turn Response'));
const result={at:new Date().toISOString(),passed:checks.every(c=>c.passed),checks,limitation:'Code/graph verification only; actual import and execution on the user n8n instance remain pending.'};
fs.mkdirSync(outputPath.slice(0,outputPath.lastIndexOf('/')),{recursive:true});
fs.writeFileSync(outputPath,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({checks:checks.length,passed:result.passed}));
if(!result.passed)process.exitCode=1;
