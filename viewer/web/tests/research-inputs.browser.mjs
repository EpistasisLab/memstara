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
   calls++;if(route.request().url().endsWith('/upload'))return route.fulfill({json:{dataset_path:'/local/example.csv',columns:['target','age'],rows:10,missing_cells:2,columns_with_missing:{age:2},nonfinite_columns:[],message:'Missing values found.'}});const configuration=route.request().postDataJSON();
   return route.fulfill({json:{configuration,dataset:{rows:10,column_count:6,columns:['target'],missing_cells:2},knowledge:{documents:1,domains:['example']},issues:[{code:'missing_values',message:'Selected columns contain missing values.'}],input_checks_passed:false,execution_ready:false,execution_note:'Input registration only.'}});
  });
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/research-inputs.fixture.html');
  await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'example.csv',mimeType:'text/csv',buffer:Buffer.from('target,age\n0,30\n1,\n')});
  await page.getByText('Missing values found',{exact:true}).waitFor();
  assert.equal(calls,1);
  assert.equal(await page.getByLabel('Target column',{exact:true}).count(),0);
  await page.getByRole('radio',{name:'Fill missing values for me',exact:true}).check();
  await page.getByLabel('Target column',{exact:true}).selectOption('target');
  await page.getByRole('radio',{name:'My research folder',exact:true}).check();
  await page.getByLabel('Research document folder path').fill('/local/okf');
  await page.getByRole('button',{name:'Check & use this data'}).click();
  await page.getByRole('dialog',{name:'Review your data settings'}).getByText('Selected columns contain missing values.',{exact:true}).waitFor();
  assert.equal(calls,2);
  await page.getByRole('button',{name:'Back to settings'}).click();
  await page.getByRole('radio',{name:'LLM only',exact:true}).check();
  assert.equal(await page.getByText('Resolve input issues before execution',{exact:true}).count(),0);
  assert.equal(await page.getByText('Missing values found',{exact:true}).count(),1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.deepEqual(errors,[]);
  await page.close();
 }
 const page=await browser.newPage({viewport:{width:390,height:900}});
 await page.route('**/control/health',r=>r.fulfill({json:{input_defaults:{dataset_available:true,knowledge_available:true,target_column:'deployment_target'}}}));
 await page.route('**/control/research-inputs',r=>r.fulfill({json:{inputs:[
  {id:'a'.repeat(32),input_checks_passed:true,configuration:{name:'Synthetic study',dataset_path:'/fixtures/study.csv',knowledge_path:'/fixtures/study-okf',target:{column:'new_target',description:'New objective',prediction_time:'Baseline'}}},
  {id:'b'.repeat(32),input_checks_passed:false,configuration:{name:'Incomplete study',target:{}}}
 ]}}));
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/research-inputs.fixture.html?selector');
 await page.getByRole('button',{name:'Use Synthetic study',exact:true}).click();
 const selected=JSON.parse(await page.getByLabel('Selected research configuration').innerText());
 assert.equal(selected.y_column,'new_target');assert.equal(selected.skill,'');assert.deepEqual(selected.baseline_columns,[]);
 assert.equal(selected.playbook_hypothesis,'hypothesis_general');
 assert.equal(selected.playbook_data,'data_training_heavy');
 assert.equal(selected.playbook_explanation,'shared-addiction');
 assert.deepEqual(selected.combination_skills,{});
 await page.getByText('Change dataset',{exact:false}).click();
 assert.equal(await page.getByRole('button',{name:'Review Incomplete study',exact:true}).count(),1);
 assert.equal(await page.getByRole('button',{name:'Use Incomplete study',exact:true}).count(),0);
 await page.getByRole('article',{name:'Synthetic study',exact:true}).getByText('Study details',{exact:true}).click();
 await page.getByText('/fixtures/study.csv',{exact:true}).waitFor();
 await page.getByText('/fixtures/study-okf',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Upload new CSV',exact:true}).click();
 await page.getByLabel('Upload CSV',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('Target column',{exact:true}).count(),0);
 assert.equal(await page.getByText('Saved research versions',{exact:true}).count(),0);
 await page.getByRole('button',{name:'Cancel editing',exact:true}).click();
 assert.equal(JSON.parse(await page.getByLabel('Selected research configuration').innerText()).research_input_id,'a'.repeat(32));
 assert.equal(await page.getByLabel('Deployment target column',{exact:true}).count(),0);
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
  await workspace.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();await workspace.getByRole('button',{name:/Add experiment/i}).click();
  assert.equal(await workspace.getByRole('dialog',{name:'Build pipelines',exact:true}).count(),0);
  assert.equal(await workspace.getByRole('button',{name:'Prepare research inputs',exact:true}).count(),0);
  await workspace.getByRole('dialog',{name:'All Combinations',exact:true}).waitFor();
  await workspace.getByRole('button',{name:'Upload new CSV',exact:true}).click();
  await workspace.getByRole('heading',{name:'Set up your CSV',exact:true}).waitFor();
  await workspace.close();
 }
 for(const suffix of ['?selector']){
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
   await malformed.getByRole('button',{name:'Check inputs',exact:true}).waitFor();
  }
  assert.deepEqual(errors,[]);await malformed.close();
 }
 console.log('Research inspection, selection, stale-setting reset, malformed-list recovery, disabled invalid records and desktop/mobile workspace entry passed. All execution writes blocked.');
}finally{await browser.close();}
