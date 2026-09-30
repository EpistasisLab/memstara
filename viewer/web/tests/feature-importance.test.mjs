import test from 'node:test';
import assert from 'node:assert/strict';
import {featureImportance} from '../src/lib/featureImportance.ts';
test('flat contributions keep finite signed values and real zeros without coercion',()=>{
 assert.deepEqual(featureImportance({a:-.2,b:0,c:null,d:'0.5',e:NaN,f:Infinity}).values,{a:-.2,b:0});
});
test('both historical permutation formats preserve method, note and signed scores',()=>{
 for(const key of ['ranking','permutation_ranking']){
 const parsed=featureImportance({method:'holdout_permutation_auc',note:'Not native importance',[key]:[{feature:'x',score:-.2},null,{feature:'bad',score:'0.1'}]});
 assert.deepEqual(parsed.values,{x:-.2});assert.equal(parsed.method,'holdout_permutation_auc');assert.equal(parsed.note,'Not native importance');
 }
});
test('unrecognized records are disclosed and missing records remain missing',()=>{
 assert.equal(featureImportance({note:'unplottable'}).unsupported,true);
 for(const value of [null,undefined,[],{}])assert.deepEqual(featureImportance(value).values,{});
});
