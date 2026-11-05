import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pipelineState} from '../src/lib/pipelineState.ts';
test('global report assembly failure is distinguished from failed analyses',()=>{
 const p={running:null,latest:{exit_code:1},progress:{},failure:{code:'final_report_assembly_failed',stage:'report_assembly',loop:null}};
 assert.equal(pipelineState(p),'Analyses completed · Report needs attention');
 assert.equal(pipelineState({...p,latest:{exit_code:1,report_recovered:true},failure:null}),'Completed');
 assert.equal(pipelineState({...p,failure:{code:'stage_task_failed',stage:'ml',loop:50}}),'Needs attention');
});
