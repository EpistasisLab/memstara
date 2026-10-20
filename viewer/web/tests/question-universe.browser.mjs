import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
const question=id=>({question_id:id,text:`Question ${id}`,rationale:'Recorded rationale',okf_tags:[],origin_run:'fixture',origin_wave:0,writer:'hypothesis',times_used:1,best_auc:.7,status:'open',created_at:''});
const evidence=id=>({question:question(id),tasks:[],results:[{result_id:id*10,task_id:id,question_id:id,run_tag:'fixture',trial:0,auc:.7,model:'logistic_regression',hypothesis:`Hypothesis ${id}`,interpretation:'Recorded interpretation',columns_used:[],columns_missing:[],importance:{}}],record_limit:100});
try{
 for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let release;let requested=false;let offline=false;let semanticOffline=false;let semanticCalls=0;
  await page.route('**/api/discovery/questions?*',r=>offline?r.fulfill({status:502,body:'<html>Unavailable</html>'}):r.fulfill({json:{questions:[question(1),question(2)],next_before:null}}));
  await page.route('**/api/discovery/questions/*',async r=>{
   const id=Number(new URL(r.request().url()).pathname.split('/').pop());
   if(id===9){requested=true;await new Promise(resolve=>{release=resolve;});}
   await r.fulfill({json:evidence(id)});
  });
  await page.route('**/api/discovery/semantic?*',r=>++semanticCalls===1?r.fulfill({status:202,json:{status:'indexing'}}):semanticOffline?r.fulfill({status:503,json:{detail:'Model unavailable'}}):r.fulfill({json:{status:'ready',indexed_count:2,total_questions:2,coverage:'complete',identity:{model:'fixture',revision:'fixed'},points:[{question_id:1,x:0,y:0,z:0},{question_id:2,x:.1,y:.1,z:.1}],neighbors:[{question_id:2,similarity:.9}]}}));
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/question-universe.fixture.html');
  await page.getByRole('button',{name:/Delayed question/}).click();
  await expect.poll(()=>requested).toBe(true);
  await page.getByRole('button',{name:'Question list',exact:true}).click();
  await page.locator('.universe-list button').filter({hasText:'Question 1'}).click();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 1');
  release();await page.waitForTimeout(300);
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 1');
  await page.getByRole('button',{name:/Missing linked result/}).click();
  await expect(page.getByText(/Selected result 999 is not available/)).toBeVisible();
  await expect(page.locator('.universe-result-select select')).toHaveValue('');
  await page.locator('.universe-result-select select').selectOption('10');
  await expect(page.getByText(/Selected result 999 is not available/)).toHaveCount(0);
  await page.getByRole('button',{name:'Semantic layout and search',exact:true}).click();
  await page.getByRole('textbox',{name:'Semantic query'}).fill('cardiac disease');
  await page.getByRole('button',{name:'Search meaning',exact:true}).click();
  await expect(page.getByText('Indexed 2 of 2 active questions',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Open question 2 · cosine 0.900'}).click();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 2');
  offline=true;
  await expect(page.locator('.universe-alert')).toBeVisible({timeout:10000});
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 2');
  offline=false;
  await expect(page.locator('.universe-alert')).toHaveCount(0,{timeout:10000});
  semanticOffline=true;
  await page.getByRole('button',{name:'Refresh semantic layout',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText:'Semantic view is unavailable'})).toBeVisible();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 2');
  await page.screenshot({path:`/tmp/memstara-universe-${width}.png`});
  await expect(page.getByRole('button',{name:'Advanced views',exact:true})).toHaveCount(0);
  for(const name of ['Question universe','Floor plan','Clinician view','Final report','Telemetry','Run log','Board','Task life','Access map']) {
   await expect(page.getByRole('button',{name,exact:true})).toBeVisible();
  }
  const controls=page.locator('.research-controls');
  await expect(controls).not.toHaveAttribute('open','');
  await controls.locator('summary').click();
  await expect(controls).toHaveAttribute('open','');
  await controls.locator('summary').click();
  await expect(controls).not.toHaveAttribute('open','');
  await page.addInitScript(()=>{HTMLCanvasElement.prototype.getContext=function(){return null;};});
  await page.reload();
  await expect(page.getByText('Canvas is unavailable.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Question list',exact:true}).click();
  await page.locator('.universe-list button').filter({hasText:'Question 1'}).click();
  await expect(page.locator('.universe-evidence h2')).toHaveText('Question 1');
  assert.deepEqual(errors,[]);
  await page.close();
 }
 console.log('Question Universe: delayed navigation cannot replace selection; missing result never falls back silently; desktop/mobile passed.');
}finally{await browser.close();}
