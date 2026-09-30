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

test('signed ranking keeps negative scores below zero and breaks ties deterministically',async()=>{
 const {rankedContributions}=await import('../src/lib/featureImportance.ts');
 assert.deepEqual(rankedContributions({negativeLarge:-.8,zero:0,positive:.1,negativeSmall:-.02,missing:null,bad:'4',target:9,tie:.1},'target'),[['positive',.1],['tie',.1],['zero',0],['negativeSmall',-.02],['negativeLarge',-.8]]);
 for(const key of ['ranking','permutation_ranking'])assert.deepEqual(rankedContributions({[key]:[{feature:'negative',score:-.8},{feature:'positive',score:.1}]}),[['positive',.1],['negative',-.8]]);
});
test('SHAP magnitude uses recorded mean absolute values, not absolute signed means',async()=>{
 const {rankedContributions}=await import('../src/lib/featureImportance.ts');
 assert.deepEqual(rankedContributions({cancelled:2,consistent:1,zero:0,invalid:-5,missing:null},'',true),[['cancelled',2],['consistent',1],['zero',0]]);
});
test('bar scales include zero for mixed, all-negative, all-positive and empty values',async()=>{
 const {contributionScale}=await import('../src/lib/featureImportance.ts');
 for(const values of [[-.8,0,.1],[-.8,-.2],[.1,.2],[0],[]]){
  const scale=contributionScale(values.map((v,i)=>[String(i),v]));
  assert(scale.low<=0&&scale.high>=0&&scale.range>0);
  for(const value of values){assert(Number.isFinite(scale.position(value)));assert(scale.position(value)>=0&&scale.position(value)<=100);}
 }
});
