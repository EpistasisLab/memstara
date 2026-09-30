import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try {
 for(const width of [1440,390])for(const theme of ['light','dark']) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let cleared=false,blocked=false,mode='normal';const posts=[];
  const question={question_id:1,text:'Synthetic memory question',okf_tags:['tag'],rationale:'Fixture',origin_run:'fixture-run',origin_wave:0,writer:'fixture',times_used:0,best_auc:null,status:'open',created_at:'2026-09-30T12:00:00Z'};
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url()),path=url.pathname;
   if(path==='/control/question-memory')return route.fulfill({json:{count:cleared?0:1,through:cleared?0:1,token:'a'.repeat(64),blocked}});
   if(path==='/control/question-memory/clear'){
    const body=route.request().postDataJSON();posts.push(body);assert.equal(body.confirm,'CLEAR QUESTION MEMORY');
    if(mode==='conflict')return route.fulfill({status:409,json:{error:'Question memory changed. Review the updated count and confirm again.'}});
    cleared=true;
    if(mode==='lost'){mode='normal';return route.fulfill({status:503,json:{error:'Clear could not be confirmed. Retry this confirmation to check its outcome.'}});}
    return route.fulfill({json:{cleared:1,cleared_through:1}});
   }
   if(path==='/api/discovery/questions')return route.fulfill({json:{questions:cleared?[]:[question],next_before:null,cleared_through:cleared?1:0}});
   if(path.startsWith('/control/')){assert.equal(route.request().method(),'GET');return route.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:{}});}
   if(path.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Fixture'}});
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  const navigate=async()=>{await page.goto('http://localhost/');await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await page.getByRole('button',{name:/Question universe/}).first().click();};
  await navigate();
  await page.getByRole('button',{name:'Clear memory',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Clear Question Universe memory?'});
  await dialog.getByText('1 questions will be cleared.').waitFor();
  assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth+1),false);
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(posts.length,0);
  blocked=true;await page.getByRole('button',{name:'Clear memory',exact:true}).click();
  await dialog.getByText('End all running or paused executions before clearing memory.').waitFor();
  assert(await dialog.getByRole('button',{name:'Clear memory',exact:true}).isDisabled());
  await page.keyboard.press('Escape');assert.equal(posts.length,0);
  blocked=false;mode='conflict';await page.getByRole('button',{name:'Clear memory',exact:true}).click();
  await dialog.getByText('1 questions will be cleared.').waitFor();await dialog.getByRole('button',{name:'Clear memory',exact:true}).click();
  await dialog.getByRole('alert').waitFor();assert.equal(cleared,false);assert(await dialog.getByRole('button',{name:'Clear memory',exact:true}).isDisabled());
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  mode='lost';await page.getByRole('button',{name:'Clear memory',exact:true}).click();
  await dialog.getByText('1 questions will be cleared.').waitFor();await dialog.getByRole('button',{name:'Clear memory',exact:true}).click();
  await dialog.getByRole('alert').waitFor();await dialog.getByRole('button',{name:'Clear memory',exact:true}).click();
  await page.getByText('1 questions cleared from active memory. Saved analyses and reports are retained.').waitFor();
  assert.equal(posts.at(-1).request_id,posts.at(-2).request_id,'Uncertain requests must reuse their idempotency key');
  await navigate();await page.getByRole('button',{name:'Clear memory',exact:true}).click();
  await dialog.getByText('0 questions will be cleared.').waitFor();assert(await dialog.getByRole('button',{name:'Clear memory',exact:true}).isDisabled());
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  assert.equal(await page.getByText('Synthetic memory question',{exact:true}).count(),0);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,theme,cancel:'pass',blocked:'pass',conflict:'pass',retry:'pass',reload:'pass'}));await page.close();
 }
}finally{await browser.close();}
