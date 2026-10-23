import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{
 const page=await browser.newPage();page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const items=[['Partial',3,1,0,false],['Empty',0,4,0,false],['Failed',2,0,1,false],['Failed checkpoint',0,0,1,true]].map(([name,completed,skipped,exit_code,recoverable],i)=>({
  id:'skip-'+i,number:i+1,name,configuration:{waves:4},running:null,
  latest:{run_tag:'fixture-'+i,exit_code,recoverable,configuration:{waves:4}},
  progress:{stage:'report',iteration:4,exploration:{attempted:4,completed,skipped,blocked:exit_code,outcome:exit_code?'blocked':completed?'completed':'skipped'}}
 }));
 await page.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:items}:{}}));
 await page.route('**/api/**',r=>r.fulfill({json:{runs:[],results:[],questions:[],events:[],reports:{}}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 const list=page.locator('.pipeline-browser-list');
 await list.getByText('Finished with skips',{exact:true}).waitFor();
 await list.getByText('No findings',{exact:true}).waitFor();
 await list.getByText('Needs attention',{exact:true}).first().waitFor();assert.equal(await list.getByText('Needs attention',{exact:true}).count(),2);
 const failedCheckpoint=list.locator('.pipeline-browser-row').filter({hasText:'Failed checkpoint'});
 await failedCheckpoint.getByText('Needs attention',{exact:true}).waitFor();
 assert.equal(await list.getByText('Completed',{exact:true}).count(),0);
 assert.deepEqual(errors,[]);
}finally{await browser.close();}
