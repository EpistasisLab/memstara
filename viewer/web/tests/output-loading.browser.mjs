import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const results = Array.from({length:1200}, (_, i) => ({result_id:i+1, trial:i, iteration:i+1,
  run_tag:i<600?'parent':'selected', hypothesis:`Hypothesis ${i+1}`, columns_used:['age','target'],
  columns_missing:[], importance:{}, okf_concept_ids:[], y_column:'target', auc:.8, model:'lr',
  interpretation:'', detail_deferred:true, evaluation:{interpretations:[{slot:1,worker:'i',skill:'s',
    status:'done',text:'',has_text:true,text_revision:`interpretation-${i+1}`,error:''}]}}));
const summary = {run_tag:'selected', scene_scope:'outputs', output_revision:'summary-v1',
  experiment:{id:'parent',head_run_tag:'selected',run_tags:['parent','selected'],result_combinations:1200,scheduled_combinations:1200},
  run_configuration:{trials:1,waves:1200,combination_plan:{combinations:1200,repetitions:1,total_loops:1200,execution_order:'all_pipelines_first'}},
  results, report:{status:'completed',text:'',run_tags:['parent','selected'],explanation_outputs:results.map(r=>({
    run_tag:r.run_tag,loop:r.iteration,result_id:r.result_id,text:'',has_text:true,text_revision:`explanation-${r.result_id}`,status:'completed'}))},
  board:{tasks:[],lanes:{}},scene:{places:[],agents:[],flashes:[]},agents:[],feed:[],access:{rows:[],windows:[]},
  runs:[],stale:false,health:{memstara:{up:true},core:{up:true}}};
const metric={calls:2,tokens:100,tokens_status:'complete',cost:{usd:.1,status:'complete',missing_costs:0},seconds:10,status:'completed'};
const execution={...metric,run_tag:'selected',pipeline_id:'example',run_tags:['parent','selected'],
  loops:results.map(r=>({...metric,number:r.iteration,run_tags:[r.run_tag]})),loop_summary:{},unassigned:{...metric,calls:0}};
const totals={scope:'test',updated_at:'now',total:metric,pipelines:[],executions:[execution],experiments:[execution]};
const browser=await launchResponsiveBrowser();
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],details=[]; let heavyRequests=0, usageRequests=0, conditionalRequests=0;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/control/**',route=>route.fulfill({json:{pipelines:[],skills:[]}}));
  await page.route('**/api/snapshot?**',route=>{heavyRequests++;return route.fulfill({status:503,json:{}});});
  await page.route('**/api/output-summary?**',route=>{
    if(route.request().headers()['if-none-match']==='"summary-v1"'){
      conditionalRequests++;return route.fulfill({status:304,headers:{ETag:'"summary-v1"'}});
    }
    return route.fulfill({json:summary,headers:{ETag:'"summary-v1"'}});
  });
  await page.route('**/api/output-detail?**',route=>{
    const query=new URL(route.request().url()).searchParams, loop=Number(query.get('loop'));
    details.push(loop);
    return route.fulfill({json:{run_tag:'selected',loop,results:[{...results[loop-1],detail_deferred:false,
      interpretation:`Exact Interpretation ${loop}`,evaluation:{}}],
      explanation_outputs:[{run_tag:results[loop-1].run_tag,loop,result_id:loop,status:'completed',text:`Exact Explanation ${loop}`} ]}});
  });
  await page.route('**/api/telemetry/totals',route=>{usageRequests++;return route.fulfill({json:totals});});
  await page.route('**/api/telemetry?**',route=>route.fulfill({json:{...summary,telemetry:{loop:1,loops:[]}}}));
  await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/execution-tiles.fixture.html`);
  await page.evaluate(()=>window.requestOutputRecords('selected'));
  const panel=page.getByTestId('execution-outputs');
  await expect(panel.locator('.execution-output-tile')).toHaveCount(100).catch(async error=>{
    console.error({errors,body:(await panel.textContent())?.slice(0,1500)});throw error;
  });
  await expect(panel.locator('.output-list-heading')).toContainText('1200 replicates');
  await expect(panel.getByText('1200 scheduled replicates with saved results · 1200 planned · 2 execution sessions · One experiment',{exact:true})).toBeVisible();
  assert.deepEqual(details,[]);
  await page.evaluate(()=>window.refreshOutputRecords());
  assert.equal(conditionalRequests,1); assert.equal(heavyRequests,0);
  await panel.getByLabel('Output page',{exact:true}).selectOption({value:'5'});
  await expect(panel.locator('.execution-output-tile').first()).toHaveAttribute('aria-label','Open Results: Pipeline 501 · Replicate 1');
  await panel.getByRole('button',{name:'Open Results: Pipeline 501 · Replicate 1',exact:true}).click();
  await expect(panel.locator('.output-documents')).toContainText('Exact Interpretation 501');
  await panel.getByRole('navigation',{name:'Related execution views'}).getByRole('button',{name:'Conclusions',exact:true}).click();
  await expect(panel.locator('.output-documents')).toContainText('Exact Explanation 501');
  assert.deepEqual(details,[501]);
  await panel.getByRole('button',{name:'Back to Conclusions',exact:true}).click();
  await panel.getByLabel('Output page',{exact:true}).selectOption({value:'11'});
  await expect(panel.getByRole('button',{name:'Open Conclusions: Pipeline 1200 · Replicate 1',exact:true})).toBeVisible();
  await panel.getByRole('navigation',{name:'Output views'}).getByRole('button',{name:'Usage',exact:true}).click();
  await expect(panel.locator('.execution-output-tile')).toHaveCount(100);
  await expect(panel.locator('.output-list-heading')).toContainText('1200 replicates');
  const before=usageRequests;
  await panel.getByRole('button',{name:'Open Usage: Pipeline 1 · Replicate 1',exact:true}).click();
  await expect(panel.locator('.telemetry-key-metrics')).toContainText('100');
  assert.equal(usageRequests,before,'Nested Usage detail must share the active totals request');
  assert.deepEqual(errors,[]);
  console.log('PASS: 1200 retained records, 100 mounted tiles, original detail ownership, conditional summaries and shared Usage');
} finally {await browser.close();}
