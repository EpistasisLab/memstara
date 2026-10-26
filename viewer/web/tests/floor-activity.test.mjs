import {test} from 'node:test';
import assert from 'node:assert/strict';
import {floorActivityRows, floorCallRole, floorCallStatus, floorExecutionState, floorStageProcessing} from '../src/lib/floorActivity.ts';
const trace={calls:[{stage:'question6-1',status:'completed',skill:{stage:'hypothesis',id:'psychiatric'}},{stage:'hypothesis6',status:'completed',skill:{stage:'hypothesis',id:'psychiatric'}},{stage:'data#1',status:'started',skill:{stage:'data',id:'exact-features'}}],planned:{agents:[{stage:'ml',id:'governance'}]}};
test('pause request stops live animation before the worker finishes',()=>{
 for(const run of [{pause_requested:true,execution_state:'running'},{execution_state:'stopping'}]){
  const state=floorExecutionState(run);
  assert.equal(state.live,false);
  assert.equal(state.stopping,true);
  assert.equal(floorCallStatus({stage:'ml#1',status:'started'},{...state,currentStage:'ml'}),'Pause requested · finishing call');
 }
 const state=floorExecutionState({pause_requested:true,execution_state:'paused'});
 assert.equal(floorCallStatus({stage:'ml#1',status:'started'},state),'Paused · call open');
 assert.equal(floorExecutionState(null).live,false);
 assert.equal(floorExecutionState({execution_state:'running'}).live,true);
 assert.equal(floorExecutionState({execution_state:'running',waiting_for_questions:true}).live,false);
 assert.equal(floorExecutionState({execution_state:'running',connection_health:{state:'verifying'}}).live,false);
});
test('log and floor use actual current-loop workers and distinguish planned skills',()=>{
 const rows=floorActivityRows({trace,live:true,currentStage:'data'});
 assert.equal(rows[0].call.stage,'hypothesis6');
 assert.equal(rows[0].status,'Completed');
 assert.equal(rows[1].skill.id,'exact-features');
 assert.equal(rows[1].status,'Running');
 assert.equal(rows[2].skill.id,'governance');
 assert.equal(rows[2].call,undefined);
 assert.equal(rows[2].status,'Waiting · no call recorded');
 for(const row of rows)assert.equal(row.status,floorCallStatus(row.call,{live:true,currentStage:'data'}));
});
test('stale, paused and historical records never claim active execution',()=>{
 assert.equal(floorActivityRows({trace,live:false})[1].status,'Last recorded: call open');
 assert.equal(floorActivityRows({trace,live:true,error:'offline'})[1].status,'Last recorded: call open');
 assert.equal(floorActivityRows({trace,paused:true})[1].status,'Paused · call open');
 assert.equal(floorCallRole({stage:'interpret#1'}),'interpreter');
 assert.equal(floorCallRole({stage:'question6-1'}),'hypothesis');
 assert.equal(floorCallStatus({status:'failed'},{}),'failed');
});
test('overlapping invocations do not imply overlapping training and interpretation',()=>{
 const calls=[{stage:'ml#1',status:'started'},{stage:'interpret#1',status:'started'}];
 const rows=floorActivityRows({trace:{calls},live:true,currentStage:'interpreter'});
 assert.equal(rows[2].status,'Call still open');
 assert.equal(rows[3].status,'Running');
 assert.equal(calls[0].status,'started');
 assert.equal(floorCallStatus(calls[0],{live:true}),'Call still open');
 assert.equal(floorCallStatus(calls[1],{live:true,currentStage:'ml'}),'Call still open');
 assert.equal(floorCallStatus({...calls[0],status:'failed'},{live:true,currentStage:'interpreter'}),'failed');
 assert.equal(floorCallStatus({...calls[0],status:'completed'},{live:true,currentStage:'interpreter'}),'Completed');
});

test('unverified and lost connections cannot animate as running',()=>{
 for(const state of ['lost','verifying','disconnected','unknown']){
  const status=floorExecutionState({execution_state:'running',connection_health:{state}});
  assert.equal(status.live,false);
  assert.equal(floorCallStatus({stage:'ml',status:'started'},{...status,currentStage:'ml'}),'Last recorded: call open');
 }
 assert.equal(floorExecutionState({execution_state:'running',connection_health:{state:'healthy'}}).live,true);
});


test('current stage remains visible between calls without changing call completion',()=>{
 const state={live:true,currentStage:'hypothesis'};
 const call={stage:'question22-1',status:'completed'};
 assert.equal(floorStageProcessing('hypothesis',call,state),true);
 assert.equal(floorCallStatus(call,state),'Completed');
 assert.equal(floorStageProcessing('data',undefined,state),false);
 assert.equal(floorStageProcessing('hypothesis',undefined,state),true);
 assert.equal(floorStageProcessing('hypothesis',{...call,status:'started'},state),false);
 assert.equal(floorStageProcessing('hypothesis',{...call,status:'failed'},state),false);
 for(const guard of [{live:false},{paused:true},{stopping:true},{stale:true}])
  assert.equal(floorStageProcessing('hypothesis',call,{...state,...guard}),false);
});
