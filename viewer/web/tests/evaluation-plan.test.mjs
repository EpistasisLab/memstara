import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluationPlanError} from '../src/lib/evaluationPlan.ts';
const valid={engine:'xgboost',seed:42,test_size:.25,folds:0,replicates:1,search_trials:1};
test('accepts supported settings and automatic training CV during search',()=>{
  for(const engine of ['xgboost','random_forest','logistic_regression']) {
    assert.equal(evaluationPlanError({...valid,engine,search_trials:10,replicates:10}),null);
  }
  assert.equal(evaluationPlanError({...valid,seed:0,test_size:.1,folds:2}),null);
  assert.equal(evaluationPlanError({...valid,seed:2147483647,test_size:.5,folds:10}),null);
});
test('blocks empty, out-of-range and fractional integer settings before creation',()=>{
  for(const patch of [{seed:NaN},{seed:-1},{seed:1.5},{seed:2147483648},{seed:2147483647,replicates:2},{test_size:NaN},{test_size:.09},{test_size:.51},{folds:1},{folds:11},{folds:2.5},{replicates:0},{replicates:11},{replicates:1.5},{search_trials:0},{search_trials:11},{search_trials:2.5},{engine:'unsupported'}]) {
    assert.ok(evaluationPlanError({...valid,...patch}),JSON.stringify(patch));
  }
});
