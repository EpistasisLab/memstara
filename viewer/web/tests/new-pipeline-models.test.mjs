import test from 'node:test';
import assert from 'node:assert/strict';
import {newPipelineConfiguration,newPipelineRequest} from '../src/lib/newPipelineConfiguration.ts';
test('new drafts replace retired extraction choice without changing saved designs',()=>{
 const saved={playbook_data:'data_exact_features'};
 assert.equal(newPipelineConfiguration(saved).playbook_data,'data_training_heavy');
 assert.equal(saved.playbook_data,'data_exact_features');
 assert.equal(newPipelineConfiguration({playbook_data:'data_balanced_stratified'}).playbook_data,'data_balanced_stratified');
});
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

test('new drafts use explicit model skills while preserving historical configuration',()=>{
 for(const [previous,next] of [['ml_governance','ml_logistic_regression'],['ml_pilot_lr_focus','ml_logistic_regression'],['ml_pilot_xgb_focus','ml_xgboost']]){
  const saved={playbook_ml:previous};
  assert.equal(newPipelineConfiguration(saved).playbook_ml,next);
  assert.equal(saved.playbook_ml,previous);
 }
});

test('new drafts avoid hidden Interpretation choices without editing saved ones',()=>{
 const saved={playbook_interpreter:'interpreter_factual_observations'};
 assert.equal(newPipelineConfiguration(saved).playbook_interpreter,'shared-shap');
 assert.equal(saved.playbook_interpreter,'interpreter_factual_observations');
 assert.equal(newPipelineConfiguration({playbook_interpreter:'shared-lime'}).playbook_interpreter,'shared-lime');
});

test('new drafts replace disabled Explanation choices without editing saved ones',()=>{
 const saved={playbook_explanation:'shared-ml-results'};
 assert.equal(newPipelineConfiguration(saved).playbook_explanation,'shared-addiction');
 assert.equal(saved.playbook_explanation,'shared-ml-results');
 assert.equal(newPipelineConfiguration({playbook_explanation:'shared-hiv'}).playbook_explanation,'shared-hiv');
});

test('new drafts avoid disabled hypothesis choices and preserve saved selections',()=>{
 const saved={playbook_hypothesis:'hypothesis_research'};
 assert.equal(newPipelineConfiguration(saved).playbook_hypothesis,'hypothesis_general');
 assert.equal(saved.playbook_hypothesis,'hypothesis_research');
 assert.equal(newPipelineConfiguration({playbook_hypothesis:'random_features'}).playbook_hypothesis,'hypothesis_general');
});


test('new study drafts replace incompatible hypothesis skills and preserve supplied Explanation skills',()=>{
 const saved={research_input_id:'heart-failure',playbook_hypothesis:'addiction-psychiatric',playbook_explanation:'shared-hiv'};
 const draft=newPipelineConfiguration(saved);
 assert.equal(draft.playbook_hypothesis,'hypothesis_general');
 assert.equal(draft.playbook_explanation,'shared-hiv');
 assert.equal(saved.playbook_hypothesis,'addiction-psychiatric');
 assert.equal(saved.playbook_explanation,'shared-hiv');
});


test('new drafts reset inherited connections but an explicit selection is saved without credentials',()=>{
 const saved={model_connection_id:'old-connection',provider:'openai',model:'old-model',stage_models:{}};
 const draft=newPipelineConfiguration(saved);
 assert.equal(draft.model_connection_id,'');
 draft.model_connection_id='checked-connection';
 const request=newPipelineRequest(draft);
 assert.equal(request.model_connection_id,'checked-connection');
 assert(!Object.hasOwn(request,'stage_models'));
 assert(!Object.hasOwn(request,'provider'));
 assert.equal(saved.model_connection_id,'old-connection');
});
