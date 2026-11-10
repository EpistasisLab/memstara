import test from 'node:test';
import assert from 'node:assert/strict';
import {scopedSavedCounts,workspaceOutputHeads} from '../src/lib/savedOutputCounts.ts';

test('saved counts remain independent of live caps and require exact continuation scope',()=>{
  const scope=new Set(['old','current']);
  const counts={results:1457,questions:801,run_tags:['current','old']};
  assert.equal(scopedSavedCounts(counts,scope)?.results,1457);
  for(const value of [undefined,null,{}, {...counts,results:-1},{...counts,results:NaN},
    {...counts,results:'1457'},{...counts,run_tags:['current']},{...counts,run_tags:['current','old','other']}]) {
    assert.equal(scopedSavedCounts(value,scope),null);
  }
  assert.equal(scopedSavedCounts({...counts,results:0,questions:0},scope)?.results,0);
});
test('active execution wins over an outdated latest tag and duplicate heads do not double count',()=>{
  assert.deepEqual(workspaceOutputHeads([{running:{run_tag:'new'},latest:{run_tag:'old'}},
    {latest:{run_tag:'new'}},{latest:{run_tag:'saved'}},{}]),['new','saved']);
});
