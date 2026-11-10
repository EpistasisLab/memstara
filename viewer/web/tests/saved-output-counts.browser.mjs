import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const browser=await launchResponsiveBrowser();
try {
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let fail=false,total=1457,offset=0;
  await page.route('**/api/discovery/live?**',route=>route.fulfill(fail?{status:503,json:{}}:{json:{
    generated_at:new Date().toISOString(),record_limit:200,events:[],reports:{},questions:[],
    results:Array.from({length:200},(_,i)=>({result_id:i+offset,run_tag:'old'})),
    continuation_groups:{head:['old','head']},saved_counts:{results:total,questions:801,run_tags:['old','head']},
  }}));
  await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/saved-output-counts.fixture.html`);
  const header=page.locator('.topbar-result-count');
  const summary=page.getByRole('button').filter({has:page.getByText('Saved results',{exact:true})});
  await page.evaluate(()=>window.pollCounts());
  await expect(header).toHaveText('1,457 saved results');
  await expect(summary.locator('strong')).toHaveText('1,457');
  await expect(summary).toContainText('801 saved questions');
  // A long-running tab accumulates over 600 arrivals; total still comes from DB.
  for(offset of [200,400,600])await page.evaluate(()=>window.pollCounts());
  await expect(header).toHaveText('1,457 saved results');
  total=1500;
  await page.evaluate(()=>window.pollCounts());
  await expect(summary.locator('strong')).toHaveText('1,500');
  fail=true;
  await page.evaluate(()=>window.pollCounts());
  await expect(header).toHaveCount(0);
  await expect(summary.locator('strong')).toHaveText('—');
  await expect(summary).toContainText('Count updates delayed');
  // Missing counts (older API) and mismatched scope cannot reuse a cached total.
  await page.evaluate(()=>window.setCountLive({error:null,savedCounts:null}));
  await expect(header).toHaveText('Result count unavailable');
  await expect(summary.locator('strong')).toHaveText('—');
  await page.evaluate(()=>window.setCountLive({savedCounts:{results:999,questions:9,run_tags:['other']}}));
  await expect(header).toHaveText('Result count unavailable');
  await page.evaluate(()=>window.setCountLive({savedCounts:{results:0,questions:0,run_tags:['old','head']}}));
  await expect(header).toHaveText('0 saved results');
  await page.evaluate(()=>window.setCountPipelines({items:[{id:'other',name:'Other',latest:{run_tag:'other'},running:null,progress:{}}]}));
  await expect(header).toHaveCount(0);
  await expect(summary.locator('strong')).toHaveText('—');
  assert.deepEqual(errors,[]);
  console.log('PASS: exact totals beyond 200/600, shared header/overview, refreshed counts, outages, missing metadata, zero and scope switching');
} finally {await browser.close();}
