import test from 'node:test';
import assert from 'node:assert/strict';
import {novelty} from '../src/lib/novelty.ts';
test('only versioned full coverage scores are rankable',()=>{
 const valid={policy:'predicted_path_fraction_v1',rankable:true,coverage:1,score:.5};
 assert.equal(novelty(valid).score,.5);
 assert.equal(novelty({...valid,score:0}).score,0);
 for(const delta of [{score:NaN},{score:2},{score:-1},{score:'1'},{coverage:.5},{policy:'future'},{rankable:false}]) assert.equal(novelty({...valid,...delta}).score,null);
 for(const value of [null,[],{},'bad']) assert.equal(novelty(value).score,null);
});
test('malformed paths do not break rendering',()=>{
 const result=novelty({paths:[null,{path_id:1,rationale:[]},{path_id:'p',status:'observed'}],counts:{unknown:-1}});
 assert.equal(result.paths[2].id,'p');assert.equal(result.counts[3].count,0);
});
