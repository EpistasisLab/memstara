import test from 'node:test';
import assert from 'node:assert/strict';
import {compatibleResearchSkill,resetResearchSkills,setCorpusSkillBindings} from '../src/lib/researchSkills.ts';
import {corpusSkillBindings} from './corpus-skill-bindings.fixture.mjs';
setCorpusSkillBindings(corpusSkillBindings);
for(const id of ['hiv','heart'])test(`registered ${id} offers exactly its three specialties and Random`,()=>{
 const scope=corpusSkillBindings.research[id],form={research_input_id:id};
 const expected=corpusSkillBindings.profiles[scope].hypothesis;
 assert.equal(expected.length,4);
 for(const skill of expected)assert(compatibleResearchSkill({stage:'hypothesis',id:skill},form));
 const other=corpusSkillBindings.profiles[id==='hiv'?'heart_failure':'hiv'].hypothesis.slice(0,3);
 for(const skill of [...other,'hypothesis_general'])assert(!compatibleResearchSkill({stage:'hypothesis',id:skill},form));
 assert(compatibleResearchSkill({stage:'interpreter',id:'shared-anil-shap'},form));
});
test('source switch maps expertise to the new corpus while retaining technical combinations and Random',()=>{
 const current={research_input_id:'hiv',playbook_hypothesis:'addiction-psychiatric',playbook_explanation:'shared-anil-hiv',combination_skills:{hypothesis:['addiction-psychiatric','random_features'],data:['data_training_heavy'],ml:['ml_xgboost'],interpreter:['shared-anil-shap'],report:['shared-anil-hiv']}};
 const reset=resetResearchSkills(current,{research_input_id:'heart'});
 assert.deepEqual(reset.combination_skills.hypothesis,corpusSkillBindings.profiles.heart_failure.hypothesis);
 assert.deepEqual(reset.combination_skills.report,['report_general']);
 assert.deepEqual(reset.combination_skills.ml,['ml_xgboost']);
 assert.deepEqual(reset.combination_skills.data,['data_training_heavy']);
 assert.deepEqual(reset.combination_skills.interpreter,['shared-anil-shap']);
 assert.deepEqual(current.combination_skills.hypothesis,['addiction-psychiatric','random_features']);
 assert.equal(reset.playbook_hypothesis,'heart-failure-cardiovascular');
 assert.equal(reset.skill,'');assert.deepEqual(reset.baseline_columns,[]);
 const returned=resetResearchSkills({...current,...reset,research_input_id:'heart'},{research_input_id:'hiv'});
 assert.deepEqual(returned.combination_skills.hypothesis,corpusSkillBindings.profiles.hiv.hypothesis);
});
test('selecting the same corpus preserves selected specialty and Random without mutation',()=>{
 const current={research_input_id:'hiv',playbook_hypothesis:'addiction-psychiatric',playbook_explanation:'shared-anil-hiv',combination_skills:{hypothesis:['addiction-psychiatric','random_features'],report:['shared-anil-hiv']}};
 const reset=resetResearchSkills(current,{research_input_id:'hiv'});
 assert.equal(reset.playbook_hypothesis,'addiction-psychiatric');
 assert.deepEqual(reset.combination_skills,current.combination_skills);
 reset.combination_skills.hypothesis.push('changed');
 assert.equal(current.combination_skills.hypothesis.length,2);
});
test('unknown corpus and LLM-only mode offer general skills without disease-name inference',()=>{
 for(const form of [{research_input_id:'unknown-hiv-name'},{research_input_id:'hiv',knowledge_mode:'llm_only'}]){
  assert(compatibleResearchSkill({stage:'hypothesis',id:'hypothesis_general'},form));
  assert(!compatibleResearchSkill({stage:'hypothesis',id:'addiction-psychiatric'},form));
 }
});
