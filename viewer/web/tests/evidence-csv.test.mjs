import test from 'node:test';
import assert from 'node:assert/strict';
import {evidenceToCsv} from '../src/lib/evidenceCsv.ts';

const detail={
  run_tag:'run-1',experiment_id:'study',combination_id:'C01',pipeline_id:'p1',status:'completed',
  configuration:{seed_schedule:{seeds:[[731]],policy:'independent_pipelines'},books:{hypothesis:['h1'],ml:['ml_logistic_regression']}},
  prompts:{hypothesis:{playbook:'h1',body_sha256:'abc'}},report:'Saved report',outcome:{status:'completed'},
  agents:[{agent_run_id:'a1',stage:'hypothesis',metadata:{skill:'h1'},evidence:{answer:'=unsafe'}}],
  results:[{result_id:9,task_id:4,trial:0,hypothesis:'HIV outcome',model:'logistic_regression',evaluation:{
    skills:{hypothesis:'h1',ml:'ml_logistic_regression'},auc:.82,evaluation:{replicate_seeds:[731],replicates:[{seed:731,auc:.82,average_precision:.74,operating_point:{probability_cutoff:.5,true_negative:12,false_positive:3,false_negative:2,true_positive:7,sensitivity:.777,specificity:.8,precision:.7},performance:{test:{metrics:{auroc:.82,f1:.736}}}}]}}}],
  costs:[{id:'c1',receipt:{usd:.01}}],artifacts:[{path:'/outputs/result.json',sha256:'123',bytes:40,kind:'.json'}],
};

test('complete evidence CSV contains every evidence record and stable analysis columns',()=>{
  const csv=evidenceToCsv(detail);
  assert(csv.startsWith('\uFEFF'));
  for(const type of ['execution','agent','result','cost','artifact'])assert.match(csv,new RegExp(`"${type}"`));
  for(const value of ['"seed_number"','"true_negative"','"false_positive"','"false_negative"','"true_positive"','"skills_json"','"record.configuration"','"record.evaluation"'])assert(csv.includes(value));
  for(const value of ['"731"','"12"','"3"','"2"','"7"','"0.82"'])assert(csv.includes(value));
  assert.match(csv,/"record\.evidence"/);
  assert.match(csv,/=unsafe/,'nested agent evidence is retained in its JSON cell');
  assert.match(csv,/"record\.configuration"/,'the authoritative configuration JSON is retained');
});

test('empty child collections still produce a complete execution row',()=>{
  const csv=evidenceToCsv({run_tag:'empty',configuration:{},prompts:{},agents:[],results:[],costs:[],artifacts:[]});
  assert.match(csv,/"execution"/);
  assert.match(csv,/"empty"/);
});
