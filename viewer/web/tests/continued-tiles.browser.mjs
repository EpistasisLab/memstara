import {expect, chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const plan={combinations:64,repetitions:1,total_loops:64,execution_order:'all_pipelines_first'};
const metric={calls:2,tokens:100,tokens_status:'complete',cost:{usd:.1,status:'complete',missing_costs:0},seconds:10,status:'completed'};
const results=Array.from({length:64},(_,i)=>({trial:i,iteration:i+1,result_id:i+1,run_tag:i<28?'original':i<49?'continued':'selected',
 hypothesis:`Hypothesis ${i+1}`,columns_used:['age','target'],y_column:'target',auc:.7,interpretation:`Interpretation ${i+1}`}));
const snapshot={run_tag:'selected',experiment:{id:'original',name:'test-hiv-1',head_run_tag:'selected',run_tags:['original','continued','selected'],scheduled_combinations:64,result_combinations:64},run_configuration:{trials:1,waves:64,combination_plan:plan,y_column:'target'},
 stale:false,health:{memstara:{up:true},core:{up:true}},results,board:{tasks:[],lanes:{}},
 report:{status:'completed',run_tags:['original','continued','selected'],explanation_outputs:results.map(r=>({
  run_tag:r.run_tag,loop:r.iteration,result_id:r.result_id,text:`Explanation ${r.result_id}`,status:'completed'}))},
 agents:[],scene:{places:[],agents:[],flashes:[]},feed:[],access:{rows:[],windows:[]},runs:[]};
const cumulative={...metric,run_tag:'selected',run_tags:['original','continued','selected'],pipeline_id:'example',
 loops:results.map(r=>({...metric,number:r.iteration,run_tags:[r.run_tag]})),loop_summary:{},unassigned:{...metric,calls:0}};
const totals={scope:'test',updated_at:'2026-11-05T00:00:00Z',total:metric,pipelines:[],
 executions:[{...cumulative,loops:cumulative.loops.slice(49)}],experiments:[cumulative]};
const browser=process.env.MEMSTARA_BROWSER_EXECUTABLE
 ? await chromium.launch({headless:true,executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE})
 : await launchResponsiveBrowser();
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];const requests=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/telemetry/totals',route=>route.fulfill({json:totals}));
 await page.route('**/api/telemetry/conversation?**',route=>{
  const url=new URL(route.request().url());
  return route.fulfill({json:{run_tag:url.searchParams.get('run_tag'),loop:Number(url.searchParams.get('loop')),messages:[]}});
 });
 await page.route('**/api/telemetry?**',route=>{
  const url=new URL(route.request().url());requests.push(url);
  const tag=url.searchParams.get('run_tag'),loop=Number(url.searchParams.get('loop'));
  return route.fulfill({json:{...snapshot,run_tag:tag,results:[],report:null,
   telemetry:{loop,loops:[],legacy_attribution:false,unassigned_calls:0},
   loop_log:{lines:['Original execution log'],note:'',truncated:false}}});
 });
 await page.route('**/control/**',route=>route.fulfill({json:{pipelines:[],skills:[]}}));
 await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/execution-tiles.fixture.html`);
 await page.evaluate(()=>window.setOutputOwnerName('test-hiv-1'));
 await page.evaluate(s=>window.deliverOutputs(s),snapshot);
 await page.evaluate(results=>window.deliverLiveOutputs({tags:'selected',updatedAt:new Date().toISOString(),results,
  continuationGroups:{selected:['original','continued','selected']}}),results);
 await expect(page.locator('.topbar-result-count')).toHaveText('64 results loaded');
 const panel=page.getByTestId('execution-outputs');
 for(const view of ['Results','Conclusions','Usage']){
  await panel.getByRole('navigation',{name:'Output views'}).getByRole('button',{name:view,exact:true}).click();
  await expect(panel.locator('.execution-output-tile')).toHaveCount(64);
  await expect(panel.getByRole('heading',{name:'test-hiv-1',exact:true})).toBeVisible();
  await expect(panel.getByText('64 scheduled replicates with saved results · 64 planned · 3 execution sessions · One experiment',{exact:true})).toBeVisible();
  const old=panel.getByRole('button',{name:`Open ${view}: Pipeline 1 · Replicate 1`,exact:true});
  await old.click();
  if(view==='Results')await expect(panel.locator('.output-documents')).toContainText('Interpretation 1');
  if(view==='Conclusions')await expect(panel.locator('.output-documents')).toContainText('Explanation 1');
  if(view==='Usage'){
   await expect(panel.locator('.telemetry-key-metrics')).toContainText('100');
   await panel.getByLabel('Detailed records').selectOption('Logs');
   await panel.getByRole('button',{name:'Console log',exact:true}).click();
   await expect(panel).toContainText('Original execution log');
   assert(requests.some(url=>url.searchParams.get('run_tag')==='original'&&url.searchParams.get('loop')==='1'));
  }
  await panel.getByRole('button',{name:`Back to ${view}`,exact:true}).click();
 }
 assert.deepEqual(errors,[]);
 console.log('PASS: all 64 pipelines appear in Results, Conclusions and Usage across three attempts; historical detail uses original execution');
 await page.close();
}finally{await browser.close();}
