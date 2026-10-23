import {openRetainedView,retainedWorkspaceUrl} from './retained-views.mjs';
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('503 (Service Unavailable)'))errors.push(m.text());});
  let retired=false,lateAssets=0,variant=0;
  const question={question_id:1,text:'Synthetic question',okf_tags:['tag'],rationale:'Fixture',origin_run:'fixture',origin_wave:0,writer:'fixture',times_used:1,status:'done'};
  const importance=[{method:'holdout_permutation_auc',note:'Permutation scores, not native model importance.',permutation_ranking:[{feature:'input',score:-.12}]},{method:'holdout_permutation_auc',ranking:[{feature:'input',score:.23}]},{input:0},{note:'Historical unsupported record',unknown:['value']}];
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/api/discovery/questions')return route.fulfill({json:{questions:[question],next_before:null}});
   if(path==='/api/discovery/questions/1')return route.fulfill({json:{question,tasks:[],results:[{result_id:1,question_id:1,task_id:1,run_tag:'fixture',columns_used:['input'],columns_missing:[],auc:.6,hypothesis:'Synthetic hypothesis',importance:importance[variant],evaluation:{auc_std:null}}],record_limit:100}});
   if(path.startsWith('/control/'))return route.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:{}});
   if(path.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Unrelated fixture endpoint unavailable'}});
   if(retired&&path.startsWith('/assets/')){lateAssets++;return route.fulfill({status:404,body:'Retired build asset'});}
   if(new URL(route.request().url()).port==='4177')return route.continue();
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto(retainedWorkspaceUrl);
  await page.waitForFunction(()=>typeof window.openRetainedView==='function');
  // Simulate deployment after the application loaded but before first opening this view.
  retired=true;
  await openRetainedView(page);
  await page.getByRole('button',{name:'View options',exact:true}).click();
  await page.getByRole('button',{name:'List',exact:true}).click();
  await page.keyboard.press('Escape');
  await page.locator('.universe-list button').first().click();
  const stages=page.locator('.universe-stages');
  await stages.getByRole('button',{name:'ML',exact:true}).click();
  await page.getByText('Recorded method: holdout_permutation_auc').waitFor();
  assert.equal(await page.locator('.universe-bar code').innerText(),'-0.120');
  assert.equal(await page.locator('.model-spread').count(),0);
  for(variant=1;variant<importance.length;variant++) {
   const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/discovery/questions/1');await response;
   await page.waitForTimeout(100);
   if(variant===1)assert.equal(await page.locator('.universe-bar code').innerText(),'0.230');
   if(variant===2)assert.equal(await page.locator('.universe-bar code').innerText(),'0.00');
   if(variant===3)await page.getByText('The recorded contribution format cannot be plotted.',{exact:false}).waitFor();
  }
  await stages.getByRole('button',{name:'Data',exact:true}).click();
  await page.locator('.atlas-inputs button').first().click();
  await stages.getByRole('button',{name:'Interpretation',exact:true}).click();
  assert.equal(lateAssets,0,'Opening a view after deployment must not fetch retired modules');
  assert.equal(await page.getByText(/could not be displayed/).count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({width,deployment:'pass',historicalFormats:'pass',liveUpdates:'pass',nullSpread:'pass'}));await page.close();
 }
}finally{await browser.close();}
