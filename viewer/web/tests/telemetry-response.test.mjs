import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validateTelemetryResponse} from '../src/lib/telemetryResponse.ts';
const metric={calls:1,tokens:50,cost:{usd:0.01,status:'available',missing_costs:0}};
const valid={total:metric,pipelines:[{...metric,id:'p',name:'Study'}],executions:[{...metric,run_tag:'r',loops:[metric]}]};
test('usage responses require usable collections and metrics before rendering',()=>{
 assert.doesNotThrow(()=>validateTelemetryResponse(valid));
 for(const value of [null,{}, {...valid,executions:null}, {...valid,total:null}, {...valid,pipelines:[{}]}, {...valid,executions:[{...metric,run_tag:'r'}]}, {...valid,executions:[{...metric,run_tag:'r',loops:[{calls:1}]}]}]) {
  assert.throws(()=>validateTelemetryResponse(value),/incomplete/);
 }
});
test('unavailable cost status is retained rather than replaced with a measured zero',()=>{
 const value={...valid,total:{...metric,cost:{usd:0,status:'unavailable',missing_costs:1}}};
 const before=structuredClone(value);
 assert.doesNotThrow(()=>validateTelemetryResponse(value));assert.deepEqual(value,before);
});
