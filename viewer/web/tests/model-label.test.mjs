import test from 'node:test';
import assert from 'node:assert/strict';
import {hypothesisSummaryRows, hypothesisSummaryCsv} from '../src/lib/hypothesisSummary.ts';

test('all agent label variants use identical measured parameters and threshold', () => {
  const evaluation = {model:'logistic_regression',evaluation:{replicates:[{
    seed:123,parameters:{random_state:123,C:0.37,solver:'liblinear',penalty:'l2'},
    operating_point:{probability_cutoff:0.35}
  }]}};
  const rows = hypothesisSummaryRows(['Verbose agent label', 'logistic_regression', 'Wrong model'].map(model=>({model,evaluation})));
  assert.equal(new Set(rows.map(row=>row.model)).size,1);
  assert.equal(rows[0].model,'logistic_regression (penalty="l2"; solver="liblinear"; C=0.37; random_state=123; threshold=0.35)');
  assert(!hypothesisSummaryCsv(rows).includes('Wrong model'));
});

test('parameters belong to their evaluation split; missing metadata is explicit', () => {
  const rows=hypothesisSummaryRows([{model:'Unsupported claim',evaluation:{model:'xgboost',evaluation:{replicates:[
    {parameters:{random_state:7,max_depth:0}},{parameters:{random_state:8,max_depth:3}}
  ]}}}]);
  assert.match(rows[0].model,/max_depth=0; random_state=7/);
  assert.match(rows[1].model,/max_depth=3; random_state=8/);
  assert.equal(hypothesisSummaryRows([{model:'Agent only'}])[0].model,'Model not recorded (parameters not recorded)');
});
