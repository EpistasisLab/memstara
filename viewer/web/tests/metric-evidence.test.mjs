import test from 'node:test';
import assert from 'node:assert/strict';
import {precisionExplanation, validationEvidence, splitEvidence} from '../src/lib/metricEvidence.ts';
import {reportLoopText} from '../src/lib/reportLoopText.ts';

test('undefined precision is distinct from zero and missing evidence', () => {
  assert.match(precisionExplanation({precision:null,true_positive:0,false_positive:0}), /0 \/ 0/);
  assert.equal(precisionExplanation({precision:0,true_positive:0,false_positive:2}), null);
  assert.match(precisionExplanation({precision:null}), /does not infer/);
});
test('high AUC does not establish independent validation', () => {
  assert.equal(validationEvidence({auc:0.99}).label, 'Validation not recorded');
  assert.equal(validationEvidence({evaluation:{hypothesis_policy:{validation_status:'exploratory_not_independently_validated'}}}).label, 'Not validated');
  assert.match(validationEvidence({evaluation:{evaluation:{validation_reserve:{status:'reserved_not_evaluated'}}}}).reason, /has not been evaluated/);
});
test('actual splits override requested replicate counts', () => {
  const result={evaluation:{evaluation:{plan:{replicates:10},replicates:[{seed:42,auc:.6,split_id:'a'}]}}};
  assert.equal(splitEvidence(result).unique, 1);
  assert.match(splitEvidence(result).summary, /One distinct/);
  result.evaluation.evaluation.replicates.push({seed:43,auc:.7,split_id:'b'});
  assert.equal(splitEvidence(result).unique, 2);
  assert.match(splitEvidence({evaluation:{evaluation:{plan:{replicates:10}}}}).summary, /unavailable/);
  assert.match(splitEvidence({evaluation:{evaluation:{replicates:[{seed:42}]}}}).summary, /cannot be verified/);
});
test('legacy report references retain analysis identity and respect multiple analyses per loop', () => {
  assert.equal(reportLoopText('Trial zero, trial 3; iteration 4', 2), 'Loop 1 (analysis ID 0), Loop 2 (analysis ID 3); Loop 4');
  assert.equal(reportLoopText('Trial 3'), 'Analysis ID 3 (Loop not recorded)');
  for (const text of ['Clinical trial 3', 'hyperparameter trial 3', 'retry attempt 3', '`trial 3`', '[trial 3](https://example.org/trial3)', '```md\ntrial 3\n```']) {
    assert.equal(reportLoopText(text, 1), text);
  }
});
