import test from 'node:test';
import assert from 'node:assert/strict';
import {newPipelineConfiguration,newPipelineRequest} from '../src/lib/newPipelineConfiguration.ts';
for (const stage_models of [
 {qwen:{model:'qwen-old'},sonnet:{model:'sonnet-old'}},
 {non_explanation_agents:{model:'qwen-old'},explanation_agent:{model:'sonnet-old'}},
]) test(`new creation removes inherited role models (${Object.keys(stage_models)[0]})`,()=>{
 const selected={provider:'openai',model:'qwen-old',stage_models,waves:10,combination_skills:{hypothesis:[{id:'random'}]},research_input_id:'my-data'};
 const draft=newPipelineConfiguration(selected);
 assert.equal(Object.hasOwn(draft,'stage_models'),false);
 const payload=JSON.parse(JSON.stringify(newPipelineRequest(selected)));
 for(const key of ['provider','model','stage_models'])assert.equal(Object.hasOwn(payload,key),false);
 assert(!JSON.stringify(payload).includes('qwen-old'));
 assert(!JSON.stringify(payload).includes('sonnet-old'));
 assert.equal(draft.model,''); assert.equal(draft.provider,'');
 assert.equal(draft.research_input_id,'my-data');
 assert.deepEqual(draft.combination_skills,selected.combination_skills);
 draft.combination_skills.hypothesis[0].id='edited';
 assert.equal(selected.combination_skills.hypothesis[0].id,'random');
 assert.equal(selected.model,'qwen-old');
 assert.deepEqual(selected.stage_models,stage_models);
});
