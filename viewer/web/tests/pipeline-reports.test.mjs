import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pipelineReports,pipelineReportMarkdown} from '../src/lib/pipelineReports.ts';
import {executionLog} from '../src/lib/telemetry.ts';
for(const order of ['all_pipelines_first','pipeline_replicates_first'])test(`reports preserve source and pipeline scope: ${order}`,()=>{
 const plan={combinations:2,repetitions:2,total_loops:4,execution_order:order};
 const outputs=[1,2,3,4].map(loop=>({loop,result_id:loop,text:`Original narrative ${loop}`,status:'completed'}));
 const findings=outputs.map(o=>({trial:o.loop-1,result_id:o.loop,hypothesis:`Question ${o.loop}`,run_tag:'run'}));
 findings.unshift({trial:0,result_id:99,hypothesis:'Another execution',run_tag:'other'});
 const reports=pipelineReports(outputs,findings,'run',plan);
 assert.equal(reports.length,2);
 assert.equal(reports[0].title,'Pipeline 1 · Question 1');
 const positions=order==='all_pipelines_first'?[1,3]:[1,2];
 assert.deepEqual(reports[0].outputs.map(o=>o.loop),positions);
 assert.equal(reports[0].expected,2);
 const markdown=pipelineReportMarkdown(reports[0],'run');
 for(const n of positions)assert(markdown.includes(`Original narrative ${n}`));
 assert(!markdown.includes('Another execution'));
 assert.equal(markdown,positions.map(n=>`Original narrative ${n}`).join('\n\n'));
 assert.equal(executionLog('Loop 3: planning started',plan),order==='all_pipelines_first'?'Pipeline 1 · Replicate 2: planning started':'Pipeline 2 · Replicate 1: planning started');
});
test('partial reports disclose coverage, unknown logs do not invent identity',()=>{
 const [report]=pipelineReports([{loop:1,result_id:null,text:'Only saved text',status:'failed'}],[],'run',{combinations:1,repetitions:3,total_loops:3});
 assert.equal(pipelineReportMarkdown(report), 'Only saved text');
 assert.equal(report.expected,3);
 assert.equal(executionLog('Loop 3'), 'Scheduled run 3');
 assert.equal(executionLog('loop-3.json'), 'loop-3.json');
});

test('download preserves exact single narrative including fences, labels and whitespace',()=>{
 const text='  ```markdown\n| Confidence | Robustness |\n|---|---|\n| shared-shap | 0.5 |\n```\n';
 assert.equal(pipelineReportMarkdown({outputs:[{text}]}),text);
});
