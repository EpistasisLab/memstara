// All API reads mocked; no credentials, writes or paid model calls.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const profiles={qwen:{provider:'openai',model:'qwen-default'},sonnet:{provider:'azure_foundry',model:'claude-sonnet-default'}};
  const frozen={qwen:{provider:'openai',model:'qwen-frozen'},sonnet:{provider:'azure_foundry',model:'claude-sonnet-frozen'}};
  const config={stage_models:profiles,provider:'openai',model:'wrong-shared-label'};
  const items=[{id:'active',name:'Active fixture',number:1,configuration:config,running:{run_tag:'fixture',configuration:{stage_models:frozen}},latest:null,progress:{}},
    {id:'idle',name:'Idle fixture',number:2,configuration:config,running:null,latest:null,progress:{}}];
  let invalid=false;
  await page.route('**/control/**',r=>{
   assert.equal(r.request().method(),'GET');const path=new URL(r.request().url()).pathname;
   if(path==='/control/health')return r.fulfill({json:{llm:{model:'shared-deployment',provider:'openai'},stage_models:invalid?{}:profiles,stage_model_error:invalid?'Deployment stage model profiles are missing or invalid':null}});
   if(path==='/control/pipelines')return r.fulfill({json:{pipelines:items}});
   return r.fulfill({json:{catalog:[],stages:[],playbooks:[],references:[]}});
  });
  await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Mock unavailable'}}));
  await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4176');
  await page.getByRole('button',{name:'Workspace settings',exact:true}).click();
  await page.getByRole('button',{name:'Model connection',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Model connection',exact:true});
  await dialog.getByText('claude-sonnet-frozen · azure_foundry',{exact:true}).waitFor();
  assert.equal(await dialog.getByText('qwen-frozen · openai',{exact:true}).count(),5);
  assert.equal(await dialog.getByText('claude-sonnet-default · azure_foundry',{exact:true}).count(),2);
  assert(!(await dialog.innerText()).includes('wrong-shared-label'));
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  assert(await dialog.evaluate(e=>e.getBoundingClientRect().right<=innerWidth));
  invalid=true;await dialog.getByRole('button',{name:'Refresh status',exact:true}).click();
  await dialog.getByRole('alert').waitFor();
  assert((await dialog.getByRole('alert').innerText()).includes('missing or invalid'));
  await page.close();
 }
 console.log('Desktop/mobile stage assignments, frozen active profiles, saved defaults and configuration errors passed.');
} finally {await browser.close();}
