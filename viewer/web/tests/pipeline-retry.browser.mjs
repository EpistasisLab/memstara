import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{for(const width of [390,1440]){
 const page=await browser.newPage({viewport:{width,height:1000}});
 const items=['Paused','Checkpoint','Failed','Unknown','Completed'].map((name,i)=>({id:name,number:i+1,name,configuration:{waves:10},progress:{},running:i===0?{run_tag:'paused',execution_state:'paused'}:null,latest:{run_tag:name,recoverable:i===1},failure:i===2||i===3?{code:'agent_execution_failed',loop:i===2?3:null}:null}));
 const requests=[];
 await page.route('**/api/**',r=>r.fulfill({json:{}}));
 await page.route('**/control/**',r=>{
  const path=new URL(r.request().url()).pathname;
  if(r.request().method()==='POST'){requests.push({path,body:r.request().postDataJSON()});return r.fulfill({status:409,json:{error:'Saved evidence requires review'}});}
  return r.fulfill({json:path==='/control/pipelines'?{pipelines:items}:{}});
 });
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 const show=page.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
 for(const name of ['Resume Paused','Resume from checkpoint Checkpoint','Additional analysis Completed'])await expect(page.getByRole('button',{name,exact:true})).toBeVisible();
 await expect(page.getByText('Retry unavailable: the failed replicate is not identified.')).toBeVisible();
 const retry=page.getByRole('button',{name:'Retry remaining replicates Failed',exact:true});await retry.click();
 const dialog=page.getByRole('dialog',{name:'Retry remaining replicates',exact:true});
 await expect(dialog).toContainText('not checkpoint resume');assert.equal(requests.length,0);
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(requests.length,0);
 await retry.click();await dialog.getByRole('button',{name:'Retry from Replicate 3',exact:true}).click();
 await expect(dialog.getByRole('alert')).toContainText('Saved evidence requires review');
 assert.deepEqual(requests,[{path:'/control/runs',body:{pipeline_id:'Failed',execution_mode:'retry',expected_run_tag:'Failed'}}]);
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('button',{name:'Resume Paused',exact:true}).click();await expect.poll(()=>requests.length).toBe(2);assert.equal(requests[1].path,'/control/runs/paused/resume');
 await page.close();
}}finally{await browser.close();}
