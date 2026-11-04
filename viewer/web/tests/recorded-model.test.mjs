import {test} from 'node:test';
import assert from 'node:assert/strict';
import {recordedModels, parameterText} from '../src/lib/recordedModel.ts';
test('fitted evidence overrides prose and configured seeds without mutating records', () => {
  const evaluation={ml_configuration:{effective:{primary_model:'lr',models:{lr:{parameters:{random_state:999}}}}},model_results:{lr:{evaluation:{replicates:[{seed:42,parameters:{random_state:42,C:.37},operating_point:{probability_cutoff:0}}]}}}};
  const before=structuredClone(evaluation);
  const a=recordedModels({model:'lr',evaluation});
  assert.deepEqual(a,recordedModels({model:'lr (verbose label)',evaluation}));
  assert.match(a[0].fits[0].parameters,/random_state=42/);
  assert.doesNotMatch(a[0].fits[0].parameters,/999/);
  assert.equal(a[0].fits[0].threshold,'0');
  assert.deepEqual(evaluation,before);
});
test('families and fits remain separate', () => {
  const a=recordedModels({evaluation:{model_results:{a:{evaluation:{replicates:[{parameters:{C:1}},{parameters:{C:2}}]}},b:{evaluation:{replicates:[{parameters:{max_depth:3}}]}}}}});
  assert.deepEqual(a.map(x=>x.fits.map(f=>f.parameters)),[['C=1','C=2'],['max_depth=3']]);
});
test('legacy and missing records do not invent fitted parameters', () => {
  assert.equal(recordedModels({model:'legacy',evaluation:{replicates:[{parameters:{C:2}}]}})[0].fits[0].parameters,'C=2');
  assert.deepEqual(recordedModels({model:'legacy'})[0].fits,[]);
  const a=recordedModels({evaluation:{ml_configuration:{effective:{primary_model:'lr',models:{lr:{parameters:{C:1}}}}}}})[0];
  assert.equal(a.configured,'C=1');assert.deepEqual(a.fits,[]);
  assert.equal(parameterText({z:null,a:false,b:0}),'a=false · b=0 · z=null');
});
