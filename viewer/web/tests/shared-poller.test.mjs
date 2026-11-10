import test from 'node:test';
import assert from 'node:assert/strict';
import {sharedPoller} from '../src/lib/sharedPoller.ts';

test('multiple consumers share one request; errors retain previous measured totals', async () => {
  let count = 0, finish, fail;
  const poller = sharedPoller(() => {count++; return new Promise((resolve,reject) => {finish = resolve;fail=reject;});}, 60000);
  const stop1 = poller.subscribe(() => {}), stop2 = poller.subscribe(() => {});
  assert.equal(count, 1);
  poller.refresh(); assert.equal(count, 1);
  stop1();
  finish({tokens: 125, cost: 2.5});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(poller.getSnapshot().data, {tokens: 125, cost: 2.5});
  poller.refresh();
  fail(new Error('Usage temporarily unavailable'));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(poller.getSnapshot().data, {tokens: 125, cost: 2.5});
  assert.equal(poller.getSnapshot().error, 'Usage temporarily unavailable');
  stop2();
});
