// Render saved selection provenance and measured columns; every API response is synthetic.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const features=['age','bmi','marker','history'];
  const result={result_id:1,task_id:1,trial:0,iteration:1,run_tag:'fixture',pipeline_name:'Fixture',
   hypothesis:'Synthetic random control',columns_used:[...features,'target'],columns_missing:[],y_column:'target',
   auc:.6,importance:{age:.1},created_at:'2026-10-06',evaluation:{feature_selection:{mode:'random',minimum:4,
    maximum:20,actual_count:4,features,seed:12345,pool_size:30,pool_sha256:'fixture',loop:1,combination:2}}};
  const run={run_tag:'fixture',configuration:{waves:1}};
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/control/pipelines')return route.fulfill({json:{pipelines:[{id:'p',name:'Fixture',number:1,
    configuration:{waves:1},latest:run,running:null,progress:{}}]}});
   if(path.startsWith('/control/'))return route.fulfill({json:{}});
   if(path==='/api/pipeline-results')return route.fulfill({json:{results:[result],failures:[]}});
   if(path.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Unrelated fixture endpoint'}});
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://fixture.local/');
  const expand=page.getByRole('button',{name:'Expand Results',exact:true});if(await expand.count())await expand.click();
  const tab=page.getByRole('tab',{name:'Results',exact:true});if(await tab.count())await tab.click();
  await page.getByRole('button',{name:'Latest executions across pipelines',exact:true}).click();
  const evidence=page.getByRole('article',{name:'Selected analysis evidence'});
  await evidence.getByText(/Hypothesis selection: random/).waitFor();
  const text=await evidence.innerText();
  for(const value of ['4 predictors used','4 original predictors','allowed 4–20','eligible pool 30',
                      'random seed 12345','Loop 1','combination 2'])assert(text.includes(value),value);
  for(const name of features)assert(await evidence.getByText(name,{exact:true}).count());
  assert.deepEqual(errors,[]);
  console.log(`Saved selection and evaluated predictor display passed at ${width}px; all APIs mocked.`);
  await page.close();
 }
} finally {await browser.close();}
