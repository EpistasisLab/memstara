import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 for(const width of [390,1280]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let calls=0;
  await page.route('**/control/research-inputs**',async route=>{
   if(route.request().method()==='GET')return route.fulfill({json:{inputs:[]}});
   calls++;const configuration=route.request().postDataJSON();
   return route.fulfill({json:{configuration,dataset:{rows:10,column_count:6,columns:['target'],missing_cells:2},knowledge:{documents:1,domains:['example']},issues:[{code:'missing_values',message:'Selected columns contain missing values.'}],input_checks_passed:false,execution_ready:false,execution_note:'Input registration only.'}});
  });
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/research-inputs.fixture.html');
  await page.getByLabel('Research name',{exact:true}).fill('Example');
  await page.getByLabel('Dataset CSV path').fill('/local/example.csv');
  await page.getByLabel('OKF bundle folder (contains index.md)').fill('/local/okf');
  await page.getByRole('button',{name:'Inspect inputs'}).click();
  await page.getByText('Resolve input issues before execution',{exact:true}).waitFor();
  assert.equal(calls,1);
  await page.getByLabel('Prediction objective and target meaning').fill('Updated objective');
  assert.equal(await page.getByText('Resolve input issues before execution',{exact:true}).count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.deepEqual(errors,[]);
  await page.close();
 }
 const page=await browser.newPage({viewport:{width:390,height:900}});
 await page.route('**/control/research-inputs',r=>r.fulfill({json:{inputs:[
  {id:'a'.repeat(32),input_checks_passed:true,configuration:{name:'Synthetic study',target:{column:'new_target',description:'New objective',prediction_time:'Baseline'}}},
  {id:'b'.repeat(32),input_checks_passed:false,configuration:{name:'Incomplete study',target:{}}}
 ]}}));
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/research-inputs.fixture.html?selector');
 await page.getByLabel('Research inputs',{exact:true}).selectOption('a'.repeat(32));
 const selected=JSON.parse(await page.getByLabel('Selected research configuration').innerText());
 assert.equal(selected.y_column,'new_target');assert.equal(selected.skill,'');assert.deepEqual(selected.baseline_columns,[]);
 assert.equal(selected.playbook_hypothesis,'hypothesis_research');
 assert.equal(await page.locator(`option[value="${'b'.repeat(32)}"]`).evaluate(option=>option.disabled),true);
 await page.close();
 for(const width of [390,1280]){
  const workspace=await browser.newPage({viewport:{width,height:900}});
  await workspace.route('**/control/**',r=>{
   if(r.request().method()!=='GET')throw Error('Unexpected execution/write');
   const path=new URL(r.request().url()).pathname;
   return r.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:path==='/control/research-inputs'?{inputs:[]}:{skills:[],catalog:[],runs:[],playbooks:[],stages:[]}});
  });
  await workspace.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Offline UI fixture'}}));
  await workspace.goto(process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179');
  await workspace.getByRole('button',{name:'Prepare research inputs',exact:true}).click();
  await workspace.getByRole('heading',{name:'Research input preparation',exact:true}).waitFor();
  await workspace.close();
 }
 for(const suffix of ['', '?selector']){
  const malformed=await browser.newPage(),errors=[];let invalid=true;
  malformed.on('pageerror',e=>errors.push(e.message));
  await malformed.route('**/control/research-inputs',r=>r.fulfill({json:invalid?{}:{inputs:[]}}));
  await malformed.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/research-inputs.fixture.html'+suffix);
  await malformed.getByRole('alert').waitFor();
  assert.deepEqual(errors,[]);
  invalid=false;
  if(suffix){
   await malformed.getByRole('button',{name:'Retry',exact:true}).click();
   await malformed.getByRole('alert').waitFor({state:'hidden'});
  }else{
   await malformed.reload();
   await malformed.getByRole('button',{name:'Inspect inputs',exact:true}).waitFor();
  }
  assert.deepEqual(errors,[]);await malformed.close();
 }
 console.log('Research inspection, selection, stale-setting reset, malformed-list recovery, disabled invalid records and desktop/mobile workspace entry passed. All execution writes blocked.');
}finally{await browser.close();}
