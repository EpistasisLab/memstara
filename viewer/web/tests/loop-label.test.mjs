import test from 'node:test';
import assert from 'node:assert/strict';
import { loopLabel } from '../src/lib/loopLabel.ts';

test('saved one-based iteration is authoritative', () => {
  assert.equal(loopLabel({ iteration: 9, trial: 0 }, 3), 'Loop 9');
});
test('zero-based analysis indices map to their configured loop, not index + 1', () => {
  assert.equal(loopLabel({ trial: 0 }, 1), 'Loop 1');
  assert.equal(loopLabel({ trial: 8 }, 1), 'Loop 9');
  assert.equal(loopLabel({ trial: 0 }, 3), 'Loop 1');
  assert.equal(loopLabel({ trial: 2 }, 3), 'Loop 1');
  assert.equal(loopLabel({ trial: 3 }, 3), 'Loop 2');
  assert.equal(loopLabel({ trial: 8 }, 3), 'Loop 3');
});
test('unknown or invalid metadata never invents a loop number', () => {
  for (const count of [undefined, null, 0, -1, 1.5, Infinity]) assert.equal(loopLabel({ trial: 8 }, count), 'Loop —');
  for (const index of [undefined, null, -1, 1.5, Infinity]) assert.equal(loopLabel({ trial: index }, 1), 'Loop —');
  assert.equal(loopLabel({ iteration: 0 }), 'Loop —');
});

test('pipeline counter shows position against the saved execution ceiling', async () => {
  const { executionLoopLabel } = await import('../src/lib/loopLabel.ts');
  assert.equal(executionLoopLabel(3, 10, true), 'Loop 3 / 10');
  assert.equal(executionLoopLabel(10, 10, true), 'Loop 10 / 10');
  assert.equal(executionLoopLabel(undefined, 10, false), 'Loop 0 / 10');
  assert.equal(executionLoopLabel(undefined, 10, true), 'Loop — / 10');
  assert.equal(executionLoopLabel(3, undefined, true), 'Loop 3 / —');
  assert.equal(executionLoopLabel(3, 10, true, true), 'Loop 3 · Continuous');
});
