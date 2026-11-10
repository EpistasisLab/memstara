import test from 'node:test';
import assert from 'node:assert/strict';
import {outputTileFilterIndex, filterOutputTiles, UNRECORDED_SKILL} from '../src/lib/outputTileFilters.ts';

test('filter identity uses saved source choices and result evidence, including retained executions',()=>{
  const snapshot={run_tag:'head',run_configuration:{books:{hypothesis:['new']}},skill_configurations:{old:{books:{hypothesis:['old']}}}};
  const tile=(loop,tag,results=[])=>({loop,record_run_tag:tag,results,explanations:[]});
  const tiles=[tile(1,'old'),tile(2,'head',[{run_tag:'old',auc:.8,evaluation:{skills:{hypothesis:['actual']}}},{run_tag:'old',auc:.6}]),tile(3,'unavailable')];
  const original=structuredClone(tiles);
  const {metadata}=outputTileFilterIndex(snapshot,tiles);
  assert.deepEqual(metadata.get(1).skills,['old']);
  assert.deepEqual(metadata.get(2).skills,['actual','old']);
  assert.equal(metadata.get(2).auroc,.7);
  assert.deepEqual(filterOutputTiles(tiles,metadata,{skill:UNRECORDED_SKILL,sort:'schedule'}).map(t=>t.loop),[3]);
  assert.deepEqual(filterOutputTiles(tiles,metadata,{skill:'old',sort:'auroc_desc'}).map(t=>t.loop),[2,1]);
  assert.deepEqual(tiles,original);
});

test('numeric ranking keeps zero, stable ties and missing scores last in both directions',()=>{
  const tiles=[1,2,3,4,5].map(loop=>({loop}));
  const metadata=new Map([.7,null,0,.7,.9].map((auroc,i)=>[i+1,{auroc,skills:['h']}]));
  const order=sort=>filterOutputTiles(tiles,metadata,{skill:'',sort}).map(t=>t.loop);
  assert.deepEqual(order('auroc_desc'),[5,1,4,3,2]);
  assert.deepEqual(order('auroc_asc'),[3,1,4,5,2]);
  assert.deepEqual(order('schedule'),[1,2,3,4,5]);
});
