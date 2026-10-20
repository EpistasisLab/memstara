import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));let writes=0;
 await page.route('**/api/**',r=>{
  if(r.request().method()!=='GET'){writes++;return r.abort();}
  const u=new URL(r.request().url());
  if(u.pathname==='/api/motoro/execution')return r.fulfill({json:{calls:u.searchParams.get('loop')==='2'?[]:[{run_id:'r1',stage:'ml',loop:1,seq:0,availability:'available',record:{status:'completed'}}],note:'Runtime fields are read from Motoro.'}});
  if(u.pathname==='/api/motoro/run')return r.fulfill({json:{first_step_started_at:'2026-10-20T12:00:00Z',record:{started_at:width===390?null:'2026-10-20T12:00:00Z',completed_at:'2026-10-20T12:02:05Z',input:'Original task',output:'Original answer',config_snapshot:{model:'model'},state_snapshot:null}}});
  if(u.searchParams.get('detail')==='true')return r.fulfill({json:{steps:[{input_data:'Original step input',llm_call:{model:'model',prompt_tokens:123,cost_estimate:.12},tool_call:{tool:'train_and_score',arguments:{model:'lr'},result:'Saved result'}}],next_offset:null}});
  return r.fulfill({json:{steps:[{id:'s1',sequence:1,phase:'act',started_at:'2026-10-20T12:00:00Z'}],next_offset:null}});
 });
 await page.goto('http://127.0.0.1:4177/tests/motoro-records.fixture.html');
 await page.getByRole('combobox',{name:'Motoro agent invocation'}).selectOption('r1');
 await expect(page.getByText('2m 5s',{exact:true})).toBeVisible();
 await page.getByText('Run input, output, state and configuration',{exact:true}).click();
 await page.locator('summary').filter({hasText:/^output$/}).click();
 await expect(page.getByText('"Original answer"',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:/Step 1 · act/}).click();
 await page.locator('summary').filter({hasText:/^tool call$/}).click();
 await expect(page.getByText(/train_and_score/)).toBeVisible();
 assert(await page.locator('section').evaluate(e=>e.scrollWidth<=e.clientWidth+2));
 await page.getByRole('button',{name:'Choose loop 2',exact:true}).click();
 await expect(page.getByText('No invocations in this scope.')).toBeVisible();
 await expect(page.getByText('"Original answer"',{exact:true})).toHaveCount(0);
 assert.equal(writes,0);assert.deepEqual(errors,[]);await page.close();
}console.log('Motoro records: original run/step payloads, model/tool fields, scope reset and mobile layout passed.');}finally{await browser.close();}
