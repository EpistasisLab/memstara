import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const artifacts = fileURLToPath(new URL('../../../.private-tmp/developer-performance/', import.meta.url));
await mkdir(artifacts, {recursive: true, mode: 0o700});
const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const metric = {calls: 2, input_tokens: 12000, output_tokens: 300, total_tokens: 12300,
  tokens_status: 'complete', active_seconds: 120, active_status: 'recorded', agent_span_seconds: 180};
const points = Array.from({length: 32}, (_, i) => ({...metric, input_tokens: 12000 + i * 500, total_tokens: 12300 + i * 500,
  order: i + 1, loop: i + 1, pipeline_number: Math.floor(i / 2) + 1, replicate_number: i % 2 + 1,
  started_at: 1700000000 + i * 300, ended_at: 1700000200 + i * 300,
  elapsed_seconds: 200 + i * 2, elapsed_status: 'recorded', attribution: 'recorded',
  run_tag: i < 16 ? 'old' : 'retry', run_tags: i < 16 ? ['old'] : ['retry'], attempts: 1,
  agents: {ml: {...metric, input_tokens: 7000, total_tokens: 7300}}}));
const payload = {run_tag: 'retry', name: 'Synthetic study', run_tags: ['old', 'retry'], updated_at: '2026-11-06T10:00:00Z',
  points, excluded_replicates: 1, unassigned_calls: 2, unknown_order_count: 0};
try {
  const page = await browser.newPage();
  const errors = [], writes = [];
  let fetches = 0, failed = false;
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => {if (r.method() !== 'GET') writes.push(r.url());});
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/developer/trends/catalog') return route.fulfill({json: {experiments: [{name: 'Synthetic study', run_tag: 'retry'}]}});
    if (url.pathname === '/api/developer/trends') {fetches++; return failed
      ? route.fulfill({status: 503, json: {detail: 'Synthetic outage'}})
      : route.fulfill({json: payload});}
    return route.fulfill({status: 500, json: {detail: 'Unexpected API call'}});
  });
  await page.goto((process.env.MEMSTARA_TEST_URL || 'http://127.0.0.1:4188') + '/developer.html?view=performance');
  await page.getByRole('heading', {name: 'Execution performance', exact: true}).waitFor();
  assert.equal(fetches, 0, 'No measurement load until explicit selection');
  await page.getByLabel('Experiment / continuation chain').selectOption('retry');
  await page.locator('.trend-summary').waitFor();
  assert.match(await page.locator('.trend-summary').innerText(), /32/);
  assert.equal(await page.locator('.recharts-line').count(), 5);
  await page.getByText('Recorded values and source executions', {exact: true}).click();
  assert.equal(await page.locator('tbody tr').count(), 32);
  assert.match(await page.locator('tbody').innerText(), /old/);
  assert.match(await page.locator('tbody').innerText(), /retry/);
  await page.getByLabel('Agent', {exact: true}).selectOption('ml');
  assert.match(await page.locator('tbody tr').first().innerText(), /7,000/);
  const dot = page.locator('.recharts-line-dots circle').first();
  await dot.hover();
  await page.locator('.trend-tooltip').first().waitFor({state: 'visible'});
  assert.match(await page.locator('.trend-tooltip').first().innerText(), /Pipeline 1/);
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({width, height: 1000});
    // ResizeObserver updates chart SVG dimensions on the next frame.
    await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth + 2, undefined, {timeout: 5000});
    await page.screenshot({path: `${artifacts}/performance-${width}.png`, fullPage: true});
  }
  failed = true;
  await page.getByRole('button', {name: 'Refresh measurements', exact: true}).click();
  await page.getByRole('alert').filter({hasText: 'Synthetic outage'}).waitFor();
  assert.equal(await page.locator('tbody tr').count(), 32, 'Failure must retain previous snapshot');
  assert.deepEqual(writes, []);
  assert.deepEqual(errors, []);
  console.log('Developer performance: charts, filters, lineage, tooltip, responsive layouts and stale recovery passed.');
} finally {await browser.close();}
