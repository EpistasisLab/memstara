import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try{for(const width of [1440,900,390]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],api=[];
 page.setDefaultTimeout(10000);page.setDefaultNavigationTimeout(15000);
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.startsWith('/api/')||path.startsWith('/control/')){api.push(path);return route.abort();}
  const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/developer.html');
  return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://localhost/developer.html?view=agents');
 await page.getByRole('heading',{name:/How an idea becomes/}).waitFor();
 assert.equal(await page.locator('.learn-chapter').count(),8);
 assert.equal(await page.locator('.learn-flow-card').count(),24);
 assert.equal(await page.locator('.learn-chapter details').count(),0,'Core explanation must never be collapsed');
 assert.equal(await page.locator('.agent-map').count(),0,'Technical map is optional and not mounted by default');
 for(const c of await page.locator('.learn-chapter').all()){
  assert.equal(await c.locator('.learn-flow-card').count(),3);
  assert.equal(await c.locator('.learn-example li').count(),3);
  assert.ok((await c.locator('.learn-storage').innerText()).length>30);
 }
 await page.locator('#learn-question').scrollIntoViewIfNeeded();
 await page.waitForFunction(()=>document.querySelector('#learn-question').classList.contains('is-animating'));
 assert.match(await page.locator('#learn-question').innerText(),/Server-built question/);
 assert.match(await page.locator('#learn-hypothesis').innerText(),/Required hypothesis/);
 assert.ok(await page.locator('.learn-chapter.is-animating').count()<8,'Off-screen chapters do not animate');
 await page.getByRole('button',{name:'Pause explanation animations'}).click();
 assert.equal(await page.locator('.learn-chapter.is-animating').count(),0);
 await page.locator('#learn-question').scrollIntoViewIfNeeded();
 assert.equal(await page.locator('#learn-question .learn-connector i').first().evaluate(e=>getComputedStyle(e).animationName),'none');
 await page.getByRole('button',{name:'Resume explanation animations'}).click();
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.waitForFunction(()=>document.querySelectorAll('.learn-chapter.is-animating').length===0);
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.locator('#learn-question').scrollIntoViewIfNeeded();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 const grid=await page.locator('#learn-question .learn-flow').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);
 assert.equal(grid,width===390?1:5);
 await page.screenshot({path:`/private/tmp/memstara-narrative-${width}.png`});
 await page.getByRole('button',{name:'Open optional technical explorer'}).click();
 await page.getByRole('heading',{name:'From knowledge to evidence.'}).waitFor();
 await page.getByRole('button',{name:'Hide technical explorer'}).click();
 assert.equal(await page.locator('.agent-map').count(),0);
 assert.deepEqual(api,[]);assert.deepEqual(errors,[]);
 console.log(JSON.stringify({width,chapters:8,expandedCards:24,offscreenMotion:'pass',pause:'pass',reducedMotion:'pass',apiCalls:0,errors}));await page.close();
}}finally{await browser.close();}
