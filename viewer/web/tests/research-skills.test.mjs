import test from 'node:test';
import assert from 'node:assert/strict';
import {compatibleResearchSkill,resetResearchSkills} from '../src/lib/researchSkills.ts';
for (const id of ['hiv-study','heart-failure-study']) test(`registered ${id} uses compatible generic choices`,()=>{
 const form={research_input_id:id};
 for(const [stage,skill] of [['hypothesis','hypothesis_general'],['hypothesis','random_features'],['report','report_general'],['interpreter','shared-anil-shap']]) assert(compatibleResearchSkill({stage,id:skill},form));
 for(const [stage,skill] of [['hypothesis','addiction-psychiatric'],['report','shared-anil-hiv'],['report','shared-anil-addiction']]) assert(!compatibleResearchSkill({stage,id:skill},form));
});
test('switching study or source mode clears previous combinations and evidence filters',()=>{
 const reset=resetResearchSkills();
 assert.deepEqual(reset.combination_skills,{});
 assert.deepEqual(reset.baseline_columns,[]);
 assert.equal(reset.skill,'');
 assert.equal(reset.playbook_hypothesis,'hypothesis_general');
 assert.equal(reset.playbook_explanation,'report_general');
});
