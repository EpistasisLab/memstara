import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
const question=id=>({question_id:id,text:`Question ${id}`,rationale:'Recorded rationale',okf_tags:[],origin_run:'fixture',origin_wave:0,writer:'hypothesis',times_used:1,best_auc:.7,status:'open',created_at:''});
const evidence=id=>({question:question(id),tasks:[],results:[{result_id:id*10,task_id:id,question_id:id,run_tag:'fixture',trial:0,auc:.7,model:'logistic_regression',hypothesis:`Hypothesis ${id}`,interpretation:'Recorded interpretation',columns_used:[],columns_missing:[],importance:{}}],record_limit:100});
try{
 for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let release;let requested=false;let offline=false;let semanticOffline=false;let semanticCalls=0;let writes=0;
  await page.route('**/control/**',r=>{
   if(r.request().method()!=='GET'){writes++;return r.abort();}
   return r.fulfill({json:new URL(r.request().url()).pathname==='/control/question-memory'?{count:2,through:2,token:'fixture',blocked:false}:{pipelines:[]}});
  });
  await page.route('**/api/discovery/questions?*',r=>offline?r.fulfill({status:502,body:'<html>Unavailable</html>'}):r.fulfill({json:{questions:[question(1),question(2)],next_before:null}}));
  await page.route('**/api/discovery/questions/*',async r=>{
   const id=Number(new URL(r.request().url()).pathname.split('/').pop());
   if(id===9){requested=true;await new Promise(resolve=>{release=resolve;});}
   await r.fulfill({json:evidence(id)});
  });
  await page.route('**/api/discovery/novelty?*',r=>r.fulfill({json:{items:[{task_id:1,result_id:10,question_id:1,run_tag:'fixture',trial:0,hypothesis:'Ranked hypothesis',auc:.7,novelty:null}],total:1,next_offset:null}}));
  await page.route('**/api/discovery/semantic?*',r=>++semanticCalls===1?r.fulfill({status:202,json:{status:'indexing'}}):semanticOffline?r.fulfill({status:503,json:{detail:'Model unavailable'}}):r.fulfill({json:{status:'ready',indexed_count:2,total_questions:2,coverage:'complete',identity:{model:'fixture',revision:'fixed'},points:[{question_id:1,x:0,y:0,z:0},{question_id:2,x:.1,y:.1,z:.1}],neighbors:[{question_id:2,similarity:.9}]}}));
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/question-universe.fixture.html');
  const options=async()=>{await page.getByRole('button',{name:'View options',exact:true}).click();};
  const close=async()=>{await page.getByRole('button',{name:'Close Universe panel',exact:true}).click();};
  const more=async()=>{await page.getByLabel('More question actions',{exact:true}).click();};
  await expect(page.getByRole('button',{name:'Novelty proxy ranking',exact:true})).toHaveCount(0);
  await expect(page.locator('.live-output-cards')).toHaveCount(0);
  await page.getByRole('button',{name:'Show outputs',exact:true}).click();
  await page.getByRole('button',{name:/Delayed question/}).click();
  await expect.poll(()=>requested).toBe(true);
  await options();await page.getByRole('button',{name:'Question list',exact:true}).click();await close();
  await page.locator('.universe-list button').filter({hasText:'Question 1'}).click();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 1');
  release();await page.waitForTimeout(300);
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 1');
  // Details trap keyboard focus, fit the viewport, and retain the selected list.
  await page.keyboard.press('Tab');
  assert(await page.locator('dialog').evaluate(el=>el.contains(document.activeElement)));
  assert(await page.locator('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth+2));
  await page.screenshot({path:`/tmp/memstara-universe-details-${width}.png`});
  await page.keyboard.press('Escape');await expect(page.locator('dialog')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'View options',exact:true})).toBeFocused();
  await expect(page.locator('.universe-list')).toBeVisible();
  await page.getByRole('button',{name:/Missing linked result/}).click();
  await expect(page.getByText(/Selected result 999 is not available/)).toBeVisible();
  await expect(page.locator('.universe-result-select select')).toHaveValue('');
  await page.locator('.universe-result-select select').selectOption('10');
  await expect(page.getByText(/Selected result 999 is not available/)).toHaveCount(0);await close();
  await options();await page.getByRole('button',{name:'Related questions & semantic layout',exact:true}).click();
  await page.getByRole('textbox',{name:'Semantic query'}).fill('cardiac disease');
  await page.getByRole('button',{name:'Search meaning',exact:true}).click();
  await expect(page.getByText('Indexed 2 of 2 active questions',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Open question 2 · cosine 0.900'}).click();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 2');
  offline=true;await expect(page.locator('.universe-alert')).toBeVisible({timeout:10000});
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 2');
  offline=false;await expect(page.locator('.universe-alert')).toHaveCount(0,{timeout:10000});await close();
  semanticOffline=true;await options();await page.getByRole('button',{name:'Related questions & semantic layout',exact:true}).click();
  await page.getByRole('button',{name:'Refresh semantic layout',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText:'Semantic view is unavailable'})).toBeVisible();await close();
  await options();await page.getByRole('button',{name:'Novelty proxy ranking',exact:true}).click();
  await page.getByRole('button',{name:'Open agent outputs',exact:true}).click();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 1');await close();
  await options();await page.getByRole('button',{name:'Question field',exact:true}).click();
  await page.getByRole('checkbox',{name:'Color by historical exploratory AUC'}).check();await close();
  await expect(page.locator('.universe-performance-key')).toContainText('Not a final holdout score');
  await more();await page.getByRole('button',{name:'Clear memory',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Clear Question Universe memory?'})).toBeVisible();
  await page.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(writes,0);
  await expect(page.locator('.universe-workspace').getByRole('button',{name:'Add pipeline',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Pipeline controls',exact:true})).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Hide outputs',exact:true}).click();
  await expect(page.locator('.live-output-cards')).toHaveCount(0);
  await page.getByRole('button',{name:'Back to question field',exact:true}).click();
  for(const theme of ['light','dark']){
   await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
   assert(await page.locator('.universe-page').evaluate(el=>el.scrollWidth<=el.clientWidth+2));
   await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('.universe-page').scrollTop=0;});
   await page.screenshot({path:`/tmp/memstara-universe-simple-${width}-${theme}.png`});
  }
  const names=await page.locator('[aria-label="View navigation"] button').allTextContents();
  assert.deepEqual(names,['Question universe','Clinician view','Final report','Floor plan','Telemetry']);
  await page.addInitScript(()=>{HTMLCanvasElement.prototype.getContext=function(){return null;};});await page.reload();
  await expect(page.getByText('Canvas is unavailable.',{exact:false})).toBeVisible();
  await options();await page.getByRole('button',{name:'Question list',exact:true}).click();await close();
  await page.locator('.universe-list button').filter({hasText:'Question 1'}).click();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 1');
  assert.deepEqual(errors,[]);assert.equal(writes,0);await page.close();
 }
 console.log('Universe desktop/mobile: compact controls, drawers/focus, delayed selection, missing results, semantic errors, ranking, clear cancellation, collapsed activity, theme/width and canvas fallback passed. No writes.');
}finally{await browser.close();}
