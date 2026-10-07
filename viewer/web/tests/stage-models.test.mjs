import test from 'node:test';
import assert from 'node:assert/strict';
import {stageModelRows} from '../src/lib/stageModels.ts';
test('all roles use their assigned profile rather than a shared label',()=>{
 const rows=stageModelRows({model:'wrong',provider:'wrong',stage_models:{qwen:{model:'qwen-test',provider:'openai'},sonnet:{model:'claude-sonnet-test',provider:'azure_foundry'}}});
 assert.equal(rows.length,6);
 assert(rows.slice(0,5).every(r=>r.model==='qwen-test'));
 assert.equal(rows[5].model,'claude-sonnet-test');
 assert.equal(rows[5].provider,'azure_foundry');
});
test('legacy and missing profiles remain explicit',()=>{
 assert(stageModelRows({model:'legacy',provider:'openai'}).every(r=>r.model==='legacy'));
 assert(stageModelRows().every(r=>r.model==='Not recorded'));
 assert.equal(stageModelRows({stage_models:{qwen:{model:'qwen-test',provider:'openai'}}})[5].model,'Not recorded');
});
