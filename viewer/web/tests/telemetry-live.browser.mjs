// Read-only live regression; every execution mutation is blocked.
import {chromium,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
const b=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const records=[],errors=[];
try{
 const p=await b.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(60000);p.on('pageerror',e=>errors.push(e.message));
 for(const pattern of ['**/api/**','**/control/**'])await p.route(pattern,async r=>{
  if(r.request().method()!=='GET')throw Error('Mutation blocked');
  const u=new URL(r.request().url());if(u.port==='8070')return r.continue();const response=await r.fetch({url:'http://127.0.0.1:8070'+u.pathname+u.search,timeout:15000});await r.fulfill({response});
 });
 p.on('response',async r=>{if(r.url().includes('/api/telemetry?')&&r.status()===200){try{const d=await r.json();records.push({view:d.telemetry?.view,loop:d.telemetry?.loop,core:d.health?.core.up,stale:d.stale});}catch{}}});
 await p.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await p.locator('[aria-label="View navigation"]').getByRole('button',{name:'Usage',exact:true}).click();
 await p.locator('.telemetry-workspace').getByRole('combobox',{name:'Pipeline to inspect',exact:true}).selectOption({label:'test-3'});
 console.log('Waiting for test-3 agents');await expect(p.locator('.telemetry-tab-body table tbody tr')).toHaveCount(50,{timeout:60000});
 await p.locator('.telemetry-tab-body').getByRole('button',{name:'Next page',exact:true}).click();
 await expect(p.locator('.telemetry-tab-body')).toContainText('Page 2 of');
 await p.locator('.telemetry-tab-body th').first().getByRole('button').focus();await p.keyboard.press('Enter');
 await expect(p.locator('.telemetry-tab-body')).toContainText('Page 1 of');
 console.log('Pagination and keyboard sorting passed');for(const tab of ['Totals','Agents','Activity','Logs','Access','Tasks','Results']){
  await p.locator('[aria-label="Usage tabs"]').getByRole('button',{name:tab,exact:true}).click();
  await expect(p.locator('.telemetry-tab-body')).not.toContainText('Preparing all loops history');
  await expect(p.locator('.telemetry-workspace')).not.toContainText('Telemetry timed out');
  if(tab==='Logs'){try{await p.locator('.agent-reader-document').waitFor();}catch(e){console.log(JSON.stringify({alerts:await p.locator('.telemetry-workspace [role=alert]').allTextContents(),statuses:await p.locator('.telemetry-workspace [role=status]').allTextContents(),reader:await p.locator('.agent-reader').count(),recorded:records.slice(-5)}));throw e;}}console.log('Loaded '+tab);
 }
 await p.locator('[aria-label="Usage tabs"]').getByRole('button',{name:'Agents',exact:true}).click();
 await p.locator('.telemetry-workspace').getByRole('combobox',{name:'Replicate to inspect',exact:true}).selectOption('1');
 await expect.poll(()=>records.some(r=>r.view==='Agents'&&r.loop===1&&r.core),{timeout:30000}).toBeTruthy();
 await p.locator('.telemetry-workspace').getByRole('combobox',{name:'Replicate to inspect',exact:true}).selectOption('all');
 await expect(p.locator('.telemetry-tab-body')).toContainText('Rows 1–50');
 await p.setViewportSize({width:390,height:844});
 await expect(p.locator('.telemetry-workspace').getByRole('combobox',{name:'Replicate to inspect',exact:true})).toBeVisible();
 if(errors.length)throw Error(errors.join('\n'));
 writeFileSync('/tmp/memstara-telemetry-browser.json',JSON.stringify({records,errors},null,2));
 console.log('Passed: test-3 All replicates, seven tabs, pagination, keyboard sorting, Loop 1 → All replicates, mobile controls; no browser errors.');
 await p.unrouteAll({behavior:'ignoreErrors'});
}finally{await b.close();}
