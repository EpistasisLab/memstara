import test from 'node:test';
import assert from 'node:assert/strict';
import {compatibleResearchSkill,resetResearchSkills,setCorpusSkillBindings} from '../src/lib/researchSkills.ts';
import {corpusSkillBindings} from './corpus-skill-bindings.fixture.mjs';
setCorpusSkillBindings(corpusSkillBindings);
for(const id of ['hiv','heart'])test(`registered ${id} hides Random even when an older catalog offers it`,()=>{
 const scope=corpusSkillBindings.research[id],form={research_input_id:id};
 const expected=corpusSkillBindings.profiles[scope].hypothesis.filter(id=>id!=='random_features');
 assert(!compatibleResearchSkill({stage:'hypothesis',id:'random_features'},form));
 assert.equal(expected.length,3);
 for(const skill of expected)assert(compatibleResearchSkill({stage:'hypothesis',id:skill},form));
 const other=corpusSkillBindings.profiles[id==='hiv'?'heart_failure':'hiv'].hypothesis.slice(0,3);
 for(const skill of [...other,'hypothesis_general'])assert(!compatibleResearchSkill({stage:'hypothesis',id:skill},form));
 assert(compatibleResearchSkill({stage:'interpreter',id:'shared-shap'},form));
});
test('source switch maps hypotheses while preserving the explicitly selected Explanation skill',()=>{
 const current={research_input_id:'hiv',playbook_hypothesis:'addiction-psychiatric',playbook_explanation:'shared-hiv',combination_skills:{hypothesis:['addiction-psychiatric','random_features'],data:['data_training_heavy'],ml:['ml_xgboost'],interpreter:['shared-shap'],report:['shared-hiv']}};
 const reset=resetResearchSkills(current,{research_input_id:'heart'});
 assert.deepEqual(reset.combination_skills.hypothesis,corpusSkillBindings.profiles.heart_failure.hypothesis.slice(0,1));
 assert.deepEqual(reset.combination_skills.report,['shared-hiv']);
 assert.equal(reset.playbook_explanation,'shared-hiv');
 assert.deepEqual(reset.combination_skills.ml,['ml_xgboost']);
 assert.deepEqual(reset.combination_skills.data,['data_training_heavy']);
 assert.deepEqual(reset.combination_skills.interpreter,['shared-shap']);
 assert.deepEqual(current.combination_skills.hypothesis,['addiction-psychiatric','random_features']);
 assert.equal(reset.playbook_hypothesis,'heart-failure-cardiovascular');
 assert.equal(reset.skill,'');assert.deepEqual(reset.baseline_columns,[]);
 const returned=resetResearchSkills({...current,...reset,research_input_id:'heart'},{research_input_id:'hiv'});
 assert.deepEqual(returned.combination_skills.hypothesis,corpusSkillBindings.profiles.hiv.hypothesis.slice(0,1));
});
test('selecting the same corpus preserves the specialty and removes Random without mutating saved records',()=>{
 const current={research_input_id:'hiv',playbook_hypothesis:'addiction-psychiatric',playbook_explanation:'shared-hiv',combination_skills:{hypothesis:['addiction-psychiatric','random_features'],report:['shared-hiv']}};
 const reset=resetResearchSkills(current,{research_input_id:'hiv'});
 assert.equal(reset.playbook_hypothesis,'addiction-psychiatric');
 assert.deepEqual(reset.combination_skills,{hypothesis:['addiction-psychiatric'],report:['shared-hiv']});
 reset.combination_skills.hypothesis.push('changed');
 assert.equal(current.combination_skills.hypothesis.length,2);
});
test('unknown corpus and LLM-only mode offer general skills without disease-name inference',()=>{
 for(const form of [{research_input_id:'unknown-hiv-name'},{research_input_id:'hiv',knowledge_mode:'llm_only'}]){
  assert(compatibleResearchSkill({stage:'hypothesis',id:'hypothesis_general'},form));
  assert(!compatibleResearchSkill({stage:'hypothesis',id:'addiction-psychiatric'},form));
 }
});
