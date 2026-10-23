import test from 'node:test';
import assert from 'node:assert/strict';
import {loopLabel,executionLoopLabel} from '../src/lib/loopLabel.ts';
import {scheduleIdentity,identityLabel,scheduleSummary} from '../src/lib/replicateIdentity.ts';
test('48 pipelines with 10 replicates map positions to separate identities',()=>{
 const plan={combinations:48,total_loops:480};
 assert.equal(loopLabel({iteration:49},1,plan),'Pipeline 1 · Replicate 2');
 assert.equal(executionLoopLabel(480,480,true,false,plan),'Pipeline 48 / 48 · Replicate 10 / 10');
 assert.equal(executionLoopLabel(undefined,480,false,false,plan),'48 pipelines · 480 total replicates');
});
test('random start and partial legacy limits retain actual per-pipeline counts',()=>{
 const plan={combinations:4,total_loops:6,start_index:3};
 assert.equal(identityLabel(scheduleIdentity(1,plan),true),'Pipeline 4 / 4 · Replicate 1 / 2');
 assert.equal(identityLabel(scheduleIdentity(4,plan),true),'Pipeline 3 / 4 · Replicate 1 / 1');
 assert.equal(identityLabel(scheduleIdentity(5,plan),true),'Pipeline 4 / 4 · Replicate 2 / 2');
 assert.deepEqual(scheduleIdentity(7,plan),{});
});
test('recorded identity wins; legacy analysis grouping remains supported',()=>{
 assert.equal(loopLabel({iteration:80,pipeline_number:2,replicate_number:3}),'Pipeline 2 · Replicate 3');
 assert.equal(loopLabel({trial:8},3),'Pipeline 1 · Replicate 3');
 assert.equal(loopLabel({iteration:9,trial:0},3),'Pipeline 1 · Replicate 9');
 for(const trial of [undefined,null,-1,1.5,Infinity])assert.equal(loopLabel({trial},1),'Pipeline — · Replicate —');
 assert.equal(loopLabel({trial:8}),'Pipeline — · Replicate —');
});

test('schedule summary distinguishes complete products from partial historical schedules',()=>{
 assert.equal(scheduleSummary({combinations:48,total_loops:480}),'48 total pipelines × 10 replicates per pipeline = 480 total replicates');
 assert.equal(scheduleSummary({combinations:64,total_loops:10}),'64 total pipelines · 10 total replicates · Partial schedule');
 assert.equal(scheduleSummary({combinations:4,total_loops:6}),'4 total pipelines · 6 total replicates · Partial schedule');
 assert.equal(scheduleSummary({combinations:0,total_loops:0}),'Schedule totals unavailable');
});
