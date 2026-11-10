import test from 'node:test';
import assert from 'node:assert/strict';
import {tileSkillStages, tileSkillConfiguration, tileStages} from '../src/lib/tileSkills.ts';

const skills=Object.fromEntries(tileStages.map((stage,i)=>[stage.id,Array.from({length:i===2?1:2},(_,j)=>({id:`${stage.id}-${j}`,hash:`hash-${j}`,title:`${stage.label} ${j}`}))]));
const config={books:{},combination_plan:{skills,combinations:16,total_loops:32,repetitions:2}};
const selection=(value,loop,results=[])=>tileSkillStages(value,loop,results).map(stage=>stage.selected?.id);
test('frozen Cartesian order matches all roles, random starts and both replicate orders',()=>{
  assert.deepEqual(selection(config,1),['hypothesis-0','data-0','ml-0','interpreter-0','report-0']);
  assert.deepEqual(selection(config,2),['hypothesis-0','data-0','ml-0','interpreter-0','report-1']);
  assert.deepEqual(selection(config,9),['hypothesis-1','data-0','ml-0','interpreter-0','report-0']);
  assert.deepEqual(selection(config,17),selection(config,1));
  const rotated={...config,combination_plan:{...config.combination_plan,start_index:8,execution_order:'pipeline_replicates_first'}};
  assert.deepEqual(selection(rotated,1),selection(config,9));
  assert.deepEqual(selection(rotated,2),selection(config,9));
  assert.deepEqual(selection(rotated,3),selection(config,10));
  assert.deepEqual(selection(config,33),Array(5).fill(undefined));
});
test('retained runs never borrow the head schedule or current skill versions',()=>{
  const older={...config,combination_plan:{...config.combination_plan,skills:{...skills,hypothesis:[{id:'old',hash:'old-version'},{id:'other',hash:'other-version'}]}}};
  const snapshot={run_tag:'head',run_configuration:config,skill_configurations:{parent:older}};
  assert.equal(tileSkillConfiguration(snapshot,'parent'),older);
  assert.equal(tileSkillConfiguration(snapshot,'head'),config);
  assert.equal(tileSkillConfiguration(snapshot,'missing'),undefined);
  assert.equal(tileSkillStages(older,1,[])[0].selected.hash,'old-version');
});
test('result evidence wins, conflicting and missing selections do not become guessed dots',()=>{
  const rows=[{evaluation:{skills:{hypothesis:['actual']}}}];
  const stage=tileSkillStages(config,1,rows)[0];
  assert.equal(stage.selected.id,'actual');
  assert.equal(stage.selected.hash,undefined);
  assert.match(stage.issue,/different skill/);
  const ambiguous=tileSkillStages(config,1,[...rows,{evaluation:{skills:{hypothesis:['other']}}}])[0];
  assert.equal(ambiguous.selected,undefined);
  assert.match(ambiguous.issue,/Multiple/);
  assert.equal(tileSkillStages(undefined,1,[])[0].selected,undefined);
  assert.equal(tileSkillStages({books:{hypothesis:['only']}},1,[])[0].selected.id,'only');
  assert.equal(tileSkillStages({books:{hypothesis:['one','two']}},1,[])[0].selected,undefined);
});
