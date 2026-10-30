import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';

// Isolated response fixtures; no control action reaches a live backend.
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 const page=await browser.newPage({viewport:{width:1280,height:900}});
 page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const run={run_tag:'original',execution_state:'running',configuration:{waves:3}};
 const item={id:'recovery-fixture',number:1,name:'Recovery fixture',configuration:{waves:3},
  running:run,latest:run,progress:{stage:'ml',iteration:2}};
 const posts=[];
 page.on('pageerror', error => console.error('Browser error:', error.message));
 page.on('console', message => {if(message.type()==='error')console.error('Browser console:',message.text());});
 await page.route('**/control/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(route.request().method()==='POST') {
   posts.push(path);
   assert.equal(path,'/control/runs/original/resume');
   item.running={...run,execution_state:'running'};
   return route.fulfill({json:{recovered:true,run_tag:'original'}});
  }
  return route.fulfill({json:path==='/control/pipelines'?{pipelines:[item]}:{}});
 });
 await page.route('**/api/**',route=>route.fulfill({json:{runs:[],results:[],questions:[],events:[],reports:{}}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 const card=page.locator('.pipeline-browser-row').filter({hasText:'Recovery fixture'});
 const badge=card.locator('.pipeline-state-badge');
 await badge.getByText('Running',{exact:true}).waitFor();
 item.running={...run,pause_requested:true,execution_state:'stopping'};
 await badge.getByText('Stopping',{exact:true}).waitFor();
 item.running={...run,pause_requested:true,execution_state:'paused'};
 await badge.getByText('Paused',{exact:true}).waitFor();
 await card.getByRole('button',{name:'Resume Recovery fixture',exact:true}).click();
 await badge.getByText('Running',{exact:true}).waitFor();
 assert.deepEqual(posts,['/control/runs/original/resume']);
 item.running=null;item.latest={...run,exit_code:1,recoverable:true};
 await badge.getByText('Needs attention',{exact:true}).waitFor();
 await card.getByRole('button',{name:'Resume from checkpoint Recovery fixture',exact:true}).waitFor();
 assert.equal(await badge.getByText('Completed',{exact:true}).count(),0);
 item.latest={...run,exit_code:1,recoverable:false,recovery_blocked:'Uncertain external effects'};
 await card.getByRole('button',{name:'Resume from checkpoint Recovery fixture',exact:true}).waitFor({state:'hidden'});
 assert.equal(posts.length,1,'Polling must never automatically resume uncertain work');
 item.latest={...run,exit_code:0,recoverable:false};
 await badge.getByText('Completed',{exact:true}).waitFor();
 assert.deepEqual(errors,[]);
 console.log('Running / Pausing / Paused / Resume / blocked checkpoint / Completed: passed');
} finally {await browser.close();}
