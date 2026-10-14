import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';

// No model/backend calls: simulate a lost start response and authoritative polls.
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage();
 let items=[];
 await page.route('**/control/**',route=>route.fulfill({json:{pipelines:items}}));
 await page.route('**/api/**',route=>route.fulfill({status:503,json:{error:'Isolated fixture'}}));
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/start-reconciliation.fixture.html');
 await page.waitForFunction(()=>!!window.pipelineStore);
 const pipeline=(id,tag=null,running=false)=>({id,number:1,name:id,configuration:{},progress:{},running:running?{run_tag:tag}:null,latest:tag?{run_tag:tag}:null});
 items=[pipeline('target','previous'),pipeline('other')];
 await page.evaluate(async()=>{
  await window.pipelineStore.getState().poll();
  const fetchOriginal=window.fetch;
  window.starts=0;
  window.fetch=(url,options)=>{
   if(url==='/control/runs'&&options?.method==='POST'){
    window.starts++;
    return Promise.reject(new DOMException('Simulated delayed response','TimeoutError'));
   }
   return fetchOriginal(url,options);
  };
  await window.pipelineStore.getState().play('target');
 });
 await page.waitForFunction(()=>window.pipelineStore.getState().pendingStart?.pipelineId==='target');
 items=[pipeline('target','previous'),pipeline('other','unrelated-new',true)];
 await page.waitForTimeout(100);
 await page.evaluate(()=>window.pipelineStore.getState().poll());
 assert.equal(await page.evaluate(()=>!!window.pipelineStore.getState().pendingStart),true);
 assert.match(await page.evaluate(()=>window.pipelineStore.getState().error),/start response was delayed/);
 await page.evaluate(async()=>{await window.pipelineStore.getState().play('target');await window.pipelineStore.getState().playAll();});
 assert.equal(await page.evaluate(()=>window.starts),1,'An unconfirmed start must not be submitted again');
 // Even a run that completed before the first successful poll confirms acceptance.
 items=[pipeline('target','accepted-new'),pipeline('other','unrelated-new',true)];
 await page.evaluate(()=>window.pipelineStore.getState().poll());
 assert.equal(await page.evaluate(()=>window.pipelineStore.getState().pendingStart),null);
 assert.equal(await page.evaluate(()=>window.pipelineStore.getState().error),null);
 await page.evaluate(()=>window.pipelineStore.setState({error:'Settings not saved: fixture conflict'}));
 await page.evaluate(()=>window.pipelineStore.getState().poll());
 assert.equal(await page.evaluate(()=>window.pipelineStore.getState().error),'Settings not saved: fixture conflict');
 // Confirmation must not dismiss another action's diagnosis.
 await page.evaluate(()=>window.pipelineStore.setState({pendingStart:{pipelineId:'target',previousTag:'accepted-new'},error:'Settings not saved: fixture conflict'}));
 items=[pipeline('target','running-new',true)];
 await page.evaluate(()=>window.pipelineStore.getState().poll());
 assert.equal(await page.evaluate(()=>window.pipelineStore.getState().pendingStart),null);
 assert.equal(await page.evaluate(()=>window.pipelineStore.getState().error),'Settings not saved: fixture conflict');
 console.log('Delayed starts reconciled only with matching new runs; duplicate starts blocked; unrelated errors retained. All requests mocked.');
} finally {await browser.close();}
