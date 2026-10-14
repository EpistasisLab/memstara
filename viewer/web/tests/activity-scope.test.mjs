import assert from 'node:assert/strict';
import test from 'node:test';
import { matchesActivityStage } from '../src/lib/activityScope.ts';

test('numbered runtime calls match their floor-plan stage',()=>{
  for(const [actual,scope] of [['ml#1','ml'],['interpretation#2','interpreter'],['explanation#1','report']]){
    for(const kind of ['tool','text']) assert.equal(matchesActivityStage(actual,scope,kind),true);
  }
  assert.equal(matchesActivityStage('ml#1','hypothesis','text'),false);
  assert.equal(matchesActivityStage('explanation#1','interpreter','tool'),false);
});
test('hypothesis floor tile includes questions; question detail keeps text precise',()=>{
  assert.equal(matchesActivityStage('question#1','hypothesis','text'),true);
  assert.equal(matchesActivityStage('curator','hypothesis','text'),true);
  assert.equal(matchesActivityStage('hypothesis','question','tool'),true);
  assert.equal(matchesActivityStage('hypothesis','question','text'),false);
  assert.equal(matchesActivityStage('ml','question','tool'),false);
  assert.equal(matchesActivityStage('ml',undefined,'text'),true);
});
