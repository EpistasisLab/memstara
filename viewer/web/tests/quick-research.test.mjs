import test from 'node:test';
import assert from 'node:assert/strict';
import {quickResearchConfiguration} from '../src/lib/guidedStudy.ts';
import {setCorpusSkillBindings} from '../src/lib/researchSkills.ts';
const base={provider:'old',model:'old',stage_models:{old:{}},baseline_columns:['old'],ml_overrides:{old:{}},combination_skills:{ml:['old']},waves:64,trials:9,continuous:true,evaluation:{engine:'xgboost',seed:42,test_size:.25,folds:0,replicates:10,search_trials:9}};
const study={id:'example',configuration:{target:{column:'outcome',description:'Example objective'}}};
const catalog=[['guided','hypothesis'],['data_training_heavy','data'],['ml_logistic_regression','ml'],['shared-anil-shap','interpreter'],['explain','report']].map(([id,stage])=>({id,stage}));
function bindings(){setCorpusSkillBindings({default:'general',profiles:{custom:{label:'Example',hypothesis:['guided','random_features'],report:['explain']}},research:{example:'custom'}});}
test('guided setup selects the actual corpus profile and bounds work to one model and Loop',()=>{
 bindings();const result=quickResearchConfiguration(base,study,catalog);
 assert.equal(result.playbook_hypothesis,'guided');assert.equal(result.playbook_explanation,'explain');
 assert.equal(result.y_column,'outcome');assert.equal(result.research_input_id,'example');
 for(const key of ['waves','trials','combination_max_loops','combination_repetitions'])assert.equal(result[key],1);
 assert.equal(result.evaluation.engine,'logistic_regression');assert.equal(result.evaluation.replicates,1);
 assert.equal(result.evaluation.search_trials,1);assert.equal(result.continuous,false);
 assert.deepEqual(result.combination_skills.ml,['ml_logistic_regression']);
 assert.deepEqual(result.baseline_columns,[]);assert.deepEqual(result.ml_overrides,{});
 assert.equal(result.stage_models,undefined);assert.equal(result.provider,'');assert.equal(result.model,'');
 assert.equal(base.waves,64);
});
test('missing compatible skills block the guided preset instead of silently substituting',()=>{
 bindings();assert.throws(()=>quickResearchConfiguration(base,study,catalog.filter(s=>s.id!=='guided')),/hypothesis skill is unavailable/);
});
test('proposal-only studies retain their modes and objective',()=>{
 setCorpusSkillBindings();const s={id:'proposal',configuration:{knowledge_mode:'llm_only',data_mode:'proposal',target:{column:'',description:'Mechanism research'}}};
 const c=catalog.filter(s=>!['guided','explain'].includes(s.id)).concat([{id:'hypothesis_general',stage:'hypothesis'},{id:'report_general',stage:'report'}]);
 const result=quickResearchConfiguration(base,s,c);assert.equal(result.data_mode,'proposal');assert.equal(result.knowledge_mode,'llm_only');assert.equal(result.research_objective,'Mechanism research');
});
