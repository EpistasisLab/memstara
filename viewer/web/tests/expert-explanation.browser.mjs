import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const result={result_id:1,task_id:12,trial:0,hypothesis:'Synthetic marker question',columns_used:['marker'],columns_missing:[],y_column:'target',auc:.6,importance:{marker:.1},created_at:'2026-10-06',evaluation:{}};
  const evidence={status:'completed',aggregation:'verbatim saved reports; no new LLM call',reports:[
   {status:'completed',expert:'addiction',loop:1,database_ids:['addiction-fixture'],interpretation_methods:['shap'],task_ids:[12],citations:['[addiction-fixture:a]']},
   {status:'completed',expert:'hiv',loop:2,database_ids:['hiv-fixture'],interpretation_methods:['lime'],task_ids:[13],citations:['[hiv-fixture:h]']}]};
  const snapshot={run_tag:'fixture',runs:[{run_tag:'fixture',tasks:1,done:1}],stale:false,generated_at:'2026-10-06',
   health:{memstara:{up:true,error:''},core:{up:true,error:''}},scene:{places:[],agents:[],flashes:[]},board:{lanes:{},tasks:[]},agents:[],access:{rows:[],windows:[]},feed:[],results:[result],
   report:{status:'completed',text:'# Expert report\n\nSynthetic evidence.',specialist_explanation:evidence},
   run_configuration:{hypotheses:1,interpreters:1,books:{},evaluation:{},trials:1,waves:2}};
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/control/pipelines')return route.fulfill({json:{pipelines:[{id:'p',name:'Fixture',number:1,configuration:{waves:2},latest:{run_tag:'fixture'},running:null,progress:{}}]}});
   if(path.startsWith('/control/'))return route.fulfill({json:{}});
   if(path==='/api/runs')return route.fulfill({json:{runs:snapshot.runs}});
   if(path==='/api/snapshot')return route.fulfill({json:snapshot});
   if(path.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Unrelated fixture endpoint'}});
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://fixture.local/');
  const expand=page.getByRole('button',{name:'Expand Results',exact:true});if(await expand.count())await expand.click();
  const tab=page.getByRole('tab',{name:'Results',exact:true});if(await tab.count())await tab.click();
  await page.getByRole('button',{name:'This execution',exact:true}).click();
  await page.getByText('Open the report for this execution',{exact:true}).click();
  const panel=page.getByTestId('final-report').getByRole('region',{name:'Explanation provenance'});await panel.waitFor();
  await panel.getByText('Addiction Expert · Loop 1 · completed',{exact:true}).click();
  await panel.getByText('HIV Expert · Loop 2 · completed',{exact:true}).click();
  const text=await panel.innerText();
  for(const value of ['addiction-fixture','hiv-fixture','SHAP','LIME','LR and XGBoost','12','13','[addiction-fixture:a]','[hiv-fixture:h]'])assert(text.includes(value),value);
  assert(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth+2));
  assert.deepEqual(errors,[]);
  snapshot.report.status='failed';snapshot.report.error='Knowledge database unavailable';
  snapshot.report.specialist_explanation={status:'failed',expert:'hiv',loop:3};
  await page.reload();
  await page.getByRole('button',{name:'This execution',exact:true}).click();
  await page.getByText('Open the report for this execution',{exact:true}).click();
  await page.getByTestId('final-report').getByText('Knowledge database unavailable',{exact:true}).waitFor();
  assert((await page.getByTestId('final-report').getByRole('region',{name:'Explanation provenance'}).innerText()).includes('failed'));
  assert.deepEqual(errors,[]);await page.close();
 }
}finally{await browser.close();}
