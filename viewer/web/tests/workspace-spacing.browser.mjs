import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';

// All navigation destinations, without starting pipelines or requiring a DB.
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 const page=await browser.newPage();
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/control/**',route=>route.fulfill({json:{pipelines:[]}}));
 await page.route('**/api/**',route=>route.fulfill({status:503,json:{error:'No records in layout fixture'}}));
 for(const width of [320,390,759,760,900,1440]) {
  await page.setViewportSize({width,height:900});
  await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
  const nav=page.locator('[aria-label="View navigation"] nav');
  await nav.waitFor();
  const buttons=nav.getByRole('button');
  assert.equal(await buttons.count(),5);
  assert.equal(await buttons.first().innerText(),'Floor plan');
  assert.equal(await buttons.first().getAttribute('aria-current'),'page');
  await page.getByRole('group',{name:'Pipeline workspace header',exact:true}).waitFor();
  if(width<760) {
   const box=await nav.boundingBox();assert(box.height<=64,`Navigation must remain one row at ${width}px`);
   const top=await page.locator('#workspace-pipeline').boundingBox();
   const control=await page.locator('#workspace-control').boundingBox();
   assert(top.y>=control.y+control.height+8);
  }
  for(let index=0;index<5;index++) {
   // The final tab must be reachable even when it starts outside the viewport.
   await buttons.nth(index).click();
   assert.equal(await buttons.nth(index).getAttribute('aria-current'),'page');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Page overflow at ${width}px`);
  }
  await nav.getByRole('button',{name:'Question universe',exact:true}).click();
  await page.locator('.universe-page').waitFor();
  assert.equal(await page.locator('#workspace-pipeline .panel-header').count(),0,'One workspace title, not nested title bars');
  const gutter=await page.locator('.universe-page').evaluate(e=>getComputedStyle(e).paddingLeft);
  assert.equal(gutter,width<760?'12px':'16px');
  const minimized=page.locator('.workspace-minimized-window');
  if(width<760&&await minimized.count()===2) {
   const first=await minimized.nth(0).boundingBox(),second=await minimized.nth(1).boundingBox();
   assert.equal(first.y,second.y,'Minimized panels share a row');
  }
  console.log(`Spacing and navigation: ${width}px passed`);
 }
 assert.deepEqual(errors,[]);
} finally {await browser.close();}
