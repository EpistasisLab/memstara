import {test} from 'node:test';
import assert from 'node:assert/strict';
import {executionTiles, tileComplete, tileStatus, testAuroc} from '../src/lib/executionTiles.ts';

const snapshot = (order='all_pipelines_first') => ({run_tag:'selected',run_configuration:{trials:1,combination_plan:{combinations:16,repetitions:2,total_loops:32,execution_order:order}},results:[],report:{explanation_outputs:[]},board:{tasks:[]}});
for (const order of ['all_pipelines_first','pipeline_replicates_first']) test(`32 independent tiles, frozen ordering and exact output ownership: ${order}`,()=>{
  const s=snapshot(order);
  const loop=order==='all_pipelines_first'?17:2;
  const text='  # Original\n\n| Confidence | AUROC |\n|---|---|\n| untouched | 0.81234 |\n';
  const result={result_id:10,trial:loop-1,interpretation:text,auc:.81234};
  const explanation={loop,result_id:10,text,status:'completed'};
  s.results=[{...result,run_tag:'other',result_id:99},result];
  s.report.explanation_outputs=[explanation];
  const usage={run_tag:'selected',loops:[{number:loop,tokens:123,status:'completed'}]};
  const tiles=executionTiles(s,usage);
  assert.equal(tiles.length,32);
  assert.equal(new Set(tiles.map(t=>`${t.pipeline_number}:${t.replicate_number}`)).size,32);
  assert.deepEqual(tiles.slice(0,4).map(t=>[t.pipeline_number,t.replicate_number]),[[1,1],[1,2],[2,1],[2,2]]);
  const selected=tiles[1];
  assert.equal(selected.loop,loop);
  assert.equal(selected.results[0],result);
  assert.equal(selected.explanations[0],explanation);
  assert.equal(selected.results[0].interpretation,text);
  assert.equal(selected.usage.tokens,123);
  assert.equal(tileStatus(selected,'results'),'Ready');
  assert.equal(tileStatus(selected,'report'),'Ready');
  assert.equal(tiles[0].results.length,0);
  assert.equal(tileStatus(tiles[0],'report'),'Awaiting output');
  assert.equal(executionTiles(s,{...usage,run_tag:'other'})[1].usage,undefined);
});
test('multiple analyses and interpreter branches stay in one tile, failures never reuse a neighbouring result',()=>{
  const s=snapshot();
  s.results=[{trial:0,result_id:1,evaluation:{interpretations:[{slot:1,text:'SHAP original',status:'done'},{slot:2,text:'',status:'failed'}]}},{trial:0,result_id:2,interpretation:'Another analysis'}];
  s.board.tasks=[{trial:1,status:'failed'}];
  const tiles=executionTiles(s);
  assert.equal(tiles.length,32);
  assert.equal(tiles[0].results.length,2);
  assert.equal(tileStatus(tiles[0],'results'),'Partial output');
  const failed=tiles.find(t=>t.loop===2);
  assert.equal(tileStatus(failed,'results'),'Needs attention');
  assert.equal(failed.results.length,0);
  assert.equal(testAuroc({auc:null,evaluation:{auc:.99}}),'Not reported');
  assert.equal(testAuroc({auc:0}),'0.000');
});
test('legacy non-combination and continuous runs use recorded loop positions without inventing future runs',()=>{
  const s={run_tag:'legacy',run_configuration:{waves:3,trials:2},results:[{trial:3,result_id:1}],board:{tasks:[]}};
  assert.deepEqual(executionTiles(s).map(t=>t.replicate_number),[1,2,3]);
  assert.equal(executionTiles(s)[1].results[0].result_id,1);
  s.run_configuration.continuous=true;
  assert.deepEqual(executionTiles(s).map(t=>t.loop),[2]);
});

test('only completed records appear, including all analyses and branches',()=>{
 const s=snapshot();
 s.results=[{trial:0,result_id:1,interpretation:'complete'},
  {trial:1,result_id:2,evaluation:{interpretations:[{text:'draft',status:'in_progress'}]}},
  {trial:2,result_id:3,evaluation:{interpretations:[{text:'done',status:'done'},{text:'',status:'failed'}]}},
  {trial:3,result_id:4,interpretation:'one analysis done'},{trial:3,result_id:5,interpretation:''},
  {trial:4,result_id:6,evaluation:{interpretations:[{text:'   ',status:'done'}]}}];
 s.report.explanation_outputs=[{loop:1,text:'complete explanation',status:'completed'},
  {loop:2,text:'partial',status:'running'},{loop:3,text:'failed',status:'failed'},
  {loop:4,text:'one complete',status:'completed'},{loop:4,text:'',status:'pending'}];
 const usage={run_tag:'selected',loops:[{number:1,status:'completed',tokens_status:'partial'},
  {number:2,status:'running'},{number:3,status:'failed'},{number:4,status:'cancelled'},{number:5,status:'unknown'}]};
 const tiles=executionTiles(s,usage);
 for(const view of ['results','report','agents'])
  assert.deepEqual(tiles.filter(t=>tileComplete(t,view)).map(t=>t.loop),[1]);
 s.results[1].evaluation.interpretations[0].status='done';
 const updated=executionTiles(s,usage);
 assert.deepEqual(updated.filter(t=>tileComplete(t,'results')).map(t=>t.loop),[1,2]);
 assert.deepEqual(updated.filter(t=>tileComplete(t,'report')).map(t=>t.loop),[1]);
 assert.equal(updated[0].results[0].interpretation,'complete');
});
