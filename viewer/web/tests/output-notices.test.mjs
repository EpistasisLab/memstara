import {test} from 'node:test';
import assert from 'node:assert/strict';
import {outputNoticeKeys} from '../src/lib/outputNotices.ts';

const snapshot={run_tag:'a',results:[],report:{explanation_outputs:[{loop:1,result_id:1,status:'completed',text:'Saved output'}]}};
test('only completed view-specific records produce notifications',()=>{
  assert.equal(outputNoticeKeys(snapshot,undefined,'report').length,1);
  assert.deepEqual(outputNoticeKeys(snapshot,undefined,'agents'),[]);
  for(const output of [{status:'running',text:'Partial'},{status:'completed',text:'  '}]) {
    assert.deepEqual(outputNoticeKeys({...snapshot,report:{explanation_outputs:[{loop:1,...output}]}},undefined,'report'),[]);
  }
});
test('receipts are stable across polling but isolated by run, view and revision',()=>{
  const keys=outputNoticeKeys(snapshot,undefined,'report');
  assert.deepEqual(outputNoticeKeys(structuredClone(snapshot),undefined,'report'),keys);
  assert.notDeepEqual(outputNoticeKeys({...snapshot,run_tag:'b'},undefined,'report'),keys);
  const changed=structuredClone(snapshot);changed.report.explanation_outputs[0].text='Revised output';
  assert.notDeepEqual(outputNoticeKeys(changed,undefined,'report'),keys);
  assert(!keys[0].includes('Saved output'));
});
test('usage belongs to its execution and must be completed',()=>{
  const usage={run_tag:'a',loops:[{number:1,status:'completed',calls:2,tokens:50,cost:{usd:.1},seconds:4},{number:2,status:'running'}]};
  const keys=outputNoticeKeys(snapshot,usage,'agents');assert.equal(keys.length,1);
  assert.deepEqual(outputNoticeKeys(snapshot,{...usage,run_tag:'b'},'agents'),[]);
  assert.deepEqual(outputNoticeKeys(snapshot,usage,'agents',2),[]);
  assert.notDeepEqual(outputNoticeKeys(snapshot,{...usage,loops:[{...usage.loops[0],tokens:100}]},'agents'),keys);
});
