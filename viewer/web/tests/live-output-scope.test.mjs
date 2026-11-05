import {test} from 'node:test';
import assert from 'node:assert/strict';
import {liveOutputScope} from '../src/lib/liveOutputScope.ts';

test('summary counts the same 28 previous and 7 continued results as tiles',()=>{
 const scope=liveOutputScope(['retry'],'retry',{retry:['original','retry']});
 const results=Array.from({length:35},(_,i)=>({run_tag:i<28?'original':'retry'}));
 results.push({run_tag:'unrelated'});
 assert.equal(results.filter(r=>scope.has(r.run_tag)).length,35);
});
test('a fresh execution cannot inherit ancestors from stale live output metadata',()=>{
 assert.deepEqual([...liveOutputScope(['fresh'],'retry',{retry:['original','retry']})],['fresh']);
 assert.deepEqual([...liveOutputScope(['fresh'],'fresh',{})],['fresh']);
});
test('workspace scope includes multiple current chains once',()=>{
 assert.deepEqual([...liveOutputScope(['b','a','a'],'a,b',{a:['base','a'],b:['b']})].sort(),['a','b','base']);
});
