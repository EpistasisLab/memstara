// Read-only smoke test of the served app; no fixture API and no pipeline mutation.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {writeFileSync, mkdirSync} from 'node:fs';
const require = createRequire(new URL('../viewer/web/package.json', import.meta.url));
const {chromium} = require('@playwright/test');
const root = process.env.MEMSTARA_UI_EVIDENCE || '/tmp/memstara-served-ui';
mkdirSync(root, {recursive: true});
const browser = await chromium.launch({headless: true});
const evidence = {checks: [], browserErrors: [], failedResponses: [], blockedMutations: []};
try {
  const page = await browser.newPage();
  page.on('pageerror', error => evidence.browserErrors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 500) evidence.failedResponses.push({path: new URL(response.url()).pathname, status: response.status()});
  });
  await page.route('**/*', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      evidence.blockedMutations.push({method: route.request().method(), path: new URL(route.request().url()).pathname});
      await route.abort();
    } else await route.continue();
  });
  await page.goto(process.env.MEMSTARA_TEST_URL || 'http://127.0.0.1:8070', {waitUntil: 'domcontentloaded'});
  const nav = page.locator('[aria-label="View navigation"]');
  await nav.waitFor();
  const names = await nav.getByRole('button').allTextContents();
  assert(names.length >= 4, 'Expected the application navigation to load');
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: 1000});
    for (let index = 0; index < names.length; index++) {
      await nav.getByRole('button').nth(index).click();
      await page.waitForTimeout(1500);
      const displayError = await page.getByText(/could not be displayed/).count();
      evidence.checks.push({width, view: names[index].trim(), displayError});
      assert.equal(displayError, 0, `View failed at ${width}: ${names[index]}`);
    }
  }
  assert.deepEqual(evidence.browserErrors, []);
  assert.deepEqual(evidence.failedResponses, []);
  assert.deepEqual(evidence.blockedMutations, []);
  console.log(`PASS: ${evidence.checks.length} served desktop/mobile view checks; no mutations or browser errors`);
} finally {
  writeFileSync(`${root}/checks.json`, JSON.stringify(evidence, null, 2));
  await browser.close();
}
