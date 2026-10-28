import {preparedInputs} from './current-research.fixture.mjs';
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';

// Partial saved configurations must not strand users at the ML step.
// All backend calls are mocked and creation is captured by the fixture.
const browser=await chromium.launch({headless:true});
try {
 for(const evaluation of [{},{seed:0,test_size:.3},null]) {
  const page=await browser.newPage();
  await page.route('**/control/**',r=>r.fulfill({json:{...preparedInputs,models:[],skills:[]}}));
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/responsive-scroll.fixture.html?evaluation='+encodeURIComponent(JSON.stringify(evaluation)));
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('button',{name:'Use CI dataset',exact:true}).click();
  await dialog.getByRole('button',{name:/Agent skills/}).click();
  await dialog.getByRole('button',{name:'Next: Data',exact:true}).click();
  await dialog.getByRole('button',{name:'Next: Machine learning',exact:true}).click();
  await expect(dialog.locator('.comb-skill-card input:checked')).toHaveCount(1);
  const next=dialog.getByRole('button',{name:'Next: Interpretation',exact:true});
  console.log(JSON.stringify({evaluation,disabled:await next.isDisabled(),guidance:await dialog.locator('#comb-next-help').innerText()}));
  await expect(next).toBeEnabled();
  await next.click();
  await expect(dialog.getByRole('heading',{name:'Interpretation skills',exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Next: Explanation',exact:true}).click();
  await dialog.getByRole('button',{name:'Review plan',exact:true}).click();
  await dialog.getByLabel('Name',{exact:true}).fill('Missing evaluation regression');
  await dialog.getByRole('checkbox',{name:/I reviewed/}).check();
  await dialog.getByRole('button',{name:'Create combination design'}).click();
  const saved=JSON.parse(await page.locator('body').getAttribute('data-created'));
  assert.equal(saved.configuration.evaluation.seed,42);
  assert.equal(saved.configuration.evaluation.test_size,.25);
  await page.close();
 }
} finally {await browser.close();}
