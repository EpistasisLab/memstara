import test from 'node:test';
import assert from 'node:assert/strict';
import {startPipelines} from '../src/lib/startPipelines.ts';
const idle=id=>({id,name:`Pipeline ${id}`,running:null});
test('starts idle, resumes paused and skips running pipelines',async()=>{
  const calls=[];
  const result=await startPipelines([idle('a'),{...idle('b'),running:{run_tag:'b',execution_state:'paused'}},{...idle('c'),running:{run_tag:'c',execution_state:'running'}}],async(p,resume)=>{calls.push([p.id,resume]);},()=>false);
  assert.deepEqual(calls,[['a',false],['b',true]]);
  assert.deepEqual(result.map(r=>r.status),['started','resumed','skipped']);
});
test('a failed launch does not hide its reason or prevent the remaining launches',async()=>{
  const result=await startPipelines([idle('a'),idle('b')],async p=>{if(p.id==='a')throw Error('Invalid dataset');},()=>false);
  assert.equal(result[0].status,'failed');assert.match(result[0].detail,/Invalid dataset/);assert.equal(result[1].status,'started');
});
test('Stop all cancels remaining starts after the in-flight request completes',async()=>{
  let cancelled=false;const calls=[];
  const result=await startPipelines([idle('a'),idle('b'),idle('c')],async p=>{calls.push(p.id);cancelled=true;},()=>cancelled);
  assert.deepEqual(calls,['a']);assert.deepEqual(result.map(r=>r.status),['started','skipped','skipped']);
});
test('empty workspace makes no requests',async()=>{
  assert.deepEqual(await startPipelines([],async()=>{assert.fail('Unexpected launch');},()=>false),[]);
});
test('bulk start never re-launches a finished pipeline without an extra Loop budget',async()=>{
  const result=await startPipelines([{...idle('finished'),latest:{}},idle('new')],async p=>{assert.equal(p.id,'new');},()=>false);
  assert.equal(result[0].status,'skipped');assert.match(result[0].detail,/additional analysis/);assert.equal(result[1].status,'started');
});
