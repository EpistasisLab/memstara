import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try {
 for(const width of [1440,390])for(const structured of [false,true]) {
  const page=await browser.newPage({viewport:{width,height:1000}});page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const raw={negativeLarge:-.8,missing:null,zero:0,positive:.1,negativeSmall:-.02,target:9};
  const importance=structured?{method:'holdout_permutation_auc',permutation_ranking:Object.entries(raw).map(([feature,score])=>({feature,score}))}:raw;
  const question={question_id:1,text:'Synthetic question',okf_tags:[],rationale:'Fixture',origin_run:'fixture',origin_wave:0,writer:'fixture',times_used:1,status:'done'};
  const result={result_id:1,task_id:1,question_id:1,trial:0,iteration:1,run_tag:'fixture',pipeline_name:'Fixture',hypothesis:'Synthetic hypothesis',columns_used:Object.keys(raw),columns_missing:[],y_column:'target',auc:.6,importance,created_at:'2026-09-30',evaluation:{explanation:{method:'holdout_permutation_auc',shap:{units:'log-odds',mean_absolute:{cancelled:2,consistent:1,missing:null,zero:0,invalid:-5},mean_signed:{cancelled:0,consistent:1,zero:0}}}}};
  const run={run_tag:'fixture',configuration:{waves:1}};
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/control/pipelines')return route.fulfill({json:{pipelines:[{id:'p',name:'Fixture',number:1,configuration:{waves:1},latest:run,running:null,progress:{}}]}});
   if(path.startsWith('/control/'))return route.fulfill({json:{}});
   if(path==='/api/discovery/live')return route.fulfill({json:{questions:[question],results:[result],events:[],reports:{},generated_at:new Date().toISOString(),record_limit:200}});
   if(path==='/api/pipeline-results')return route.fulfill({json:{results:[result],failures:[]}});
   if(path==='/api/discovery/questions')return route.fulfill({json:{questions:[question],next_before:null}});
   if(path==='/api/discovery/questions/1')return route.fulfill({json:{question,tasks:[],results:[result],record_limit:100}});
   if(path.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Unrelated fixture endpoint'}});
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html');return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://localhost/');
  await page.getByRole('button',{name:/Question universe/}).first().click();await page.getByRole('button',{name:'Question list',exact:true}).click();await page.locator('.universe-list button').first().click();await page.locator('.universe-stages').getByRole('button',{name:'ML',exact:true}).click();
  await page.locator('.universe-bar').first().waitFor();
  assert.deepEqual(await page.locator('.universe-bar > span').allTextContents(),['positive','zero','negativeSmall','negativeLarge']);
  const assertBars=async selector=>{
   const bars=await page.locator(selector+' .signed-contribution-track').evaluateAll(nodes=>nodes.map(n=>{const b=n.querySelector('[data-contribution-value]');const z=n.querySelector('[data-zero-baseline]');return {v:Number(b.dataset.contributionValue),left:parseFloat(b.style.left),width:parseFloat(b.style.width),zero:parseFloat(z.style.left)};}));
   assert.equal(bars.length,4);for(const b of bars){if(b.v<0)assert(Math.abs(b.left+b.width-b.zero)<.01);if(b.v>0)assert(Math.abs(b.left-b.zero)<.01);if(b.v===0)assert.equal(b.width,0);}
  };
  await assertBars('.universe-evidence');
  await page.getByRole('button',{name:/Clinician view/}).first().click();await page.getByText('Explore the supporting evidence',{exact:true}).click();await page.locator('.clinical-contribution').first().waitFor();
  assert.deepEqual(await page.locator('.clinical-contribution > div:first-child > span').allTextContents(),['positive','zero','negativeSmall','negativeLarge']);await assertBars('.clinical-contributions');
  const expand=page.getByRole('button',{name:'Expand Results',exact:true});if(await expand.count())await expand.click();
  const tab=page.getByRole('tab',{name:'Results',exact:true});if(await tab.count())await tab.click();
  await page.getByRole('button',{name:'Latest executions across pipelines',exact:true}).click();
  await page.locator('.result-feature-row').first().waitFor();
  assert.deepEqual(await page.locator('.result-feature-row').evaluateAll(es=>es.map(e=>e.dataset.feature)),['positive','zero','negativeSmall','negativeLarge']);
  await page.getByRole('button',{name:'SHAP magnitude',exact:true}).click();
  assert.deepEqual(await page.locator('.result-feature-row').evaluateAll(es=>es.map(e=>e.dataset.feature)),['cancelled','consistent','zero']);
  assert.equal(await page.getByText(/could not be displayed/).count(),0);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({width,structured,universe:'pass',clinician:'pass',results:'pass',shap:'pass',zeroAxis:'pass'}));await page.close();
 }
}finally{await browser.close();}
