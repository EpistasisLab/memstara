import test from 'node:test';
import assert from 'node:assert/strict';
import {chartPoints, pointLabel} from '../src/developer/performanceData.ts';

test('charts retain resume order and preserve unavailable versus measured zero', () => {
  const a = {loop: 9, order: 1, started_at: 10, pipeline_number: 5, replicate_number: 1,
    active_seconds: 120, elapsed_seconds: 600, input_tokens: 100, output_tokens: 0, total_tokens: 100,
    agents: {ml: {active_seconds: 60, agent_span_seconds: 90, input_tokens: 0, output_tokens: 0, total_tokens: 0}}};
  const b = {...a, loop: 1, order: 2, started_at: 20, agents: {}};
  assert.equal(pointLabel(a), 'Pipeline 5 · Replicate 1');
  const all = chartPoints([a, b, {...a, started_at: null}], 'all');
  assert.deepEqual(all.map(p => p.loop), [9, 1]);
  assert.equal(all[0].elapsed_minutes, 10);
  assert.equal(all[0].output, 0);
  const ml = chartPoints([a, b], 'ml');
  assert.equal(ml[0].elapsed_minutes, 1.5);
  assert.equal(ml[0].total, 0);
  assert.equal(ml[1].total, null);
  assert.equal(ml[1].active_minutes, null);
});
