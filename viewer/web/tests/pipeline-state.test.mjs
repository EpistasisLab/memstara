import test from 'node:test';
import assert from 'node:assert/strict';
import {pipelineState} from '../src/lib/pipelineState.ts';

const pipeline=(latest, running=null, progress={})=>({latest,running,progress});

test('terminal failure takes precedence over a resumable checkpoint',()=>{
 assert.equal(pipelineState(pipeline({exit_code:1,recoverable:true})), 'Needs attention');
 assert.equal(pipelineState(pipeline({exit_code:1,recoverable:false})), 'Needs attention');
 assert.equal(pipelineState(pipeline({exit_code:0,recoverable:true})), 'Interrupted');
});

test('active controls and completed/skipped runs retain their own states',()=>{
 assert.equal(pipelineState(pipeline({exit_code:1}, {execution_state:'paused'})), 'Paused');
 assert.equal(pipelineState(pipeline(null, {waiting_for_questions:true})), 'Waiting');
 assert.equal(pipelineState(pipeline({exit_code:1}, {execution_state:'running'})), 'Running');
 assert.equal(pipelineState(pipeline({exit_code:1}, null), true), 'Starting');
 assert.equal(pipelineState(pipeline({exit_code:0}, null, {exploration:{completed:2,skipped:1}})), 'Finished with skips');
 assert.equal(pipelineState(pipeline(null)), 'Ready');
});


test('predictor preparation is visible only for a live run',()=>{
 const progress={preparation:{status:'running',message:'Preparing predictor search'}};
 assert.equal(pipelineState(pipeline(null, {execution_state:'running'}, progress)), 'Preparing predictor search');
 assert.equal(pipelineState(pipeline({exit_code:1}, null, progress)), 'Needs attention');
 assert.equal(pipelineState(pipeline(null, {execution_state:'paused'}, progress)), 'Paused');
});
