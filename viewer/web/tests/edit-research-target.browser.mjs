import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage();
 const config={name:'Existing study',dataset_path:'/inputs/data.csv',knowledge_path:'/inputs/okf',knowledge_mode:'okf',data_mode:'dataset',excluded_columns:[],missing_policy:'reject',target:{column:'old_label',description:'Existing objective',positive_label:'1',negative_label:'0',prediction_time:'Baseline',horizon:''}};
 const original={id:'original',configuration:config,input_checks_passed:true};
 let records=[original],submitted;
 await page.route('**/control/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/control/health')return route.fulfill({json:{input_defaults:{dataset_available:false,knowledge_available:false,target_column:'stale_env_label'}}});
  if(path==='/control/research-inputs')return route.fulfill({json:{inputs:records}});
  if(path==='/control/research-inputs/register'){
   submitted=route.request().postDataJSON();
   const saved={id:'revised',configuration:submitted,input_checks_passed:true,dataset:{rows:10,column_count:5,columns:['new_label'],missing_cells:0},knowledge:{documents:1,domains:[]},issues:[],execution_note:'Fixture'};
   records=[original,saved];return route.fulfill({json:saved});
  }
  throw Error('Unexpected request '+path);
 });
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/research-inputs.fixture.html?selector');
 await page.getByRole('combobox',{name:'Research inputs',exact:true}).selectOption('original');
 await page.getByRole('button',{name:'Edit data & target',exact:true}).click();
 assert.equal(await page.getByLabel('Target column',{exact:true}).inputValue(),'old_label');
 assert.equal(await page.getByLabel('Dataset CSV path').inputValue(),'/inputs/data.csv');
 await page.getByLabel('Target column',{exact:true}).fill('new_label');
 await page.getByRole('button',{name:'Check & use this data'}).click();
 await page.waitForFunction(()=>JSON.parse(document.querySelector('output').textContent).research_input_id==='revised');
 const selected=JSON.parse(await page.getByLabel('Selected research configuration').textContent());
 assert.equal(selected.y_column,'new_label');
 assert.equal(original.configuration.target.column,'old_label');
 assert.equal(submitted.dataset_path,config.dataset_path);
 await page.getByRole('combobox',{name:'Research inputs',exact:true}).selectOption('');
 assert.equal(JSON.parse(await page.getByLabel('Selected research configuration').textContent()).y_column,'');
 console.log('Existing target prefilled, saved as a new version, automatically selected; old target and source preserved.');
}finally{await browser.close();}
