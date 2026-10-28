import {openRetainedView,retainedWorkspaceUrl} from './retained-views.mjs';
import {expect} from '@playwright/test';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename,join} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await launchResponsiveBrowser();
try {for(const width of [1440,390]){
 const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path.startsWith('/control/'))return r.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:{}});
  if(path==='/api/discovery/questions')return r.fulfill({json:{questions:[],next_before:null}});
  if(path.startsWith('/api/'))return r.fulfill({status:503,json:{error:'Fixture endpoint unavailable'}});
  if(new URL(r.request().url()).port==='4177')return r.continue();
  return r.fulfill({body:await readFile(path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html')),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto(retainedWorkspaceUrl);const nav=page.locator('[aria-label="View navigation"]');
 for(const view of ['Experiments','Results','Conclusions','Usage']){
  await nav.getByRole('button',{name:view,exact:true}).click();
  await expect(page.locator('#workspace-results, #workspace-report')).toHaveCount(0);
 }
 await nav.getByRole('button',{name:'Experiments',exact:true}).click();
 await expect(page.locator('#workspace-results, #workspace-report')).toHaveCount(0);
 await expect(page.locator('.floor-observatory').getByRole('button',{name:/Results|Conclusions/})).toHaveCount(0);
 await nav.getByRole('button',{name:'Results',exact:true}).click();
 await expect(page.getByTestId('execution-outputs')).toBeVisible();
 await expect(nav.getByRole('button',{name:'Results',exact:true})).toHaveAttribute('aria-current','page');
 await openRetainedView(page);
 await expect(page.locator('#workspace-pipeline')).toBeVisible();
 await expect(page.locator('#workspace-results, #workspace-report')).toHaveCount(0);
 await expect(page.getByRole('region',{name:'Live pipeline outputs'})).toHaveCount(0);
 const options=page.getByRole('button',{name:'View options',exact:true});await options.click();
 await expect(page.locator('dialog[open]')).toHaveCount(0);
 const sizes=await page.locator('.universe-search, .universe-popover > summary, .universe-clear-questions').evaluateAll(els=>els.map(e=>e.getBoundingClientRect().height));
 assert(sizes.length===4&&sizes.every(h=>Math.abs(h-44)<1),JSON.stringify({width,sizes}));
 const tops=await page.locator('.universe-popover > summary, .universe-clear-questions').evaluateAll(els=>els.map(e=>e.getBoundingClientRect().top));
 assert(Math.max(...tops)-Math.min(...tops)<1,JSON.stringify({width,tops}));
 const popup=page.locator('.universe-popover[open] .universe-popover-body');await expect(popup).toBeVisible();
 assert(await popup.evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&e.scrollWidth<=e.clientWidth+1;}));
 await page.screenshot({path:join(tmpdir(),`universe-popover-${width}.png`)});
 await page.keyboard.press('Escape');await expect(popup).toHaveCount(0);
 await page.getByRole('button',{name:'Explore questions',exact:true}).click();await expect(page.getByRole('button',{name:'Related questions',exact:true})).toBeVisible();
 await page.locator('.universe-search input').click();await expect(page.locator('.universe-popover[open]')).toHaveCount(0);
 assert.deepEqual(errors,[]);console.log(`${width}: Analysis views in Control, no Experiments duplicates, 44px controls, nonmodal popovers, Escape/outside dismissal, no overflow`);await page.close();
}}finally{await browser.close();}
