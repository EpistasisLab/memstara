import {test} from 'node:test';
import assert from 'node:assert/strict';
import {clinicalPipelineStatus, clinicalEventText, scopedClinicalEvents} from '../src/lib/clinicalLog.ts';

test('clinical status distinguishes completion, failure, pause and an unconfirmed end',()=>{
 const p={progress:{},running:null,latest:{exit_code:0}};
 assert.match(clinicalPipelineStatus(p),/Completion has not been confirmed/);
 assert.match(clinicalPipelineStatus({...p,progress:{exploration:{outcome:'completed'}}}),/Execution completed/);
 assert.match(clinicalPipelineStatus({...p,latest:{exit_code:1}}),/stopped with an error/);
 assert.match(clinicalPipelineStatus({...p,running:{execution_state:'paused'}}),/^Paused/);
 assert.match(clinicalPipelineStatus({...p,running:{pause_requested:true}}),/^Pausing/);
 assert.match(clinicalPipelineStatus({...p,running:{},progress:{stage:'ml'}}),/Training and evaluating/);
 assert.match(clinicalPipelineStatus({...p,running:{},progress:{counts:{failed:1}}}),/needs attention/);
});

test('failed and unfinished outputs cannot be described as saved successes',()=>{
 assert.match(clinicalEventText({stage:'report',status:'failed'}),/needs attention/);
 assert.match(clinicalEventText({stage:'report',status:'in_progress'}),/not been confirmed/);
 assert.equal(clinicalEventText({stage:'ml',status:'recorded'}),'A model evaluation was recorded.');
});

test('log isolates selected executions including a new running tag and retains received order',()=>{
 const events=[{id:'new',run_tag:'active',receivedAt:30},{id:'foreign',run_tag:'other',receivedAt:10},{id:'old',run_tag:'previous',receivedAt:5},{id:'first',run_tag:'active',receivedAt:20}];
 assert.deepEqual(scopedClinicalEvents(events,[{running:{run_tag:'active'},latest:{run_tag:'previous'}}]).map(e=>e.id),['first','new']);
 assert.deepEqual(scopedClinicalEvents(events,[]),[]);
});

test('persisted failure explains needs-attention and clears for a fresh execution',()=>{
 const failure={code:'model_message_format',message:'The model rejected the system-message format.'};
 const p={progress:{stage:'report',exploration:{outcome:'blocked'}},latest:{exit_code:1},failure};
 assert.equal(clinicalPipelineStatus(p),failure.message);
 assert.match(clinicalPipelineStatus({...p,failure:null,running:{},progress:{stage:'question'}}),/Developing a research question/);
});
