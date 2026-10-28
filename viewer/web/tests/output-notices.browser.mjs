import assert from 'node:assert/strict';
import {expect} from '@playwright/test';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const metric={calls:2,tokens:1234,tokens_status:'complete',cost:{usd:.1,status:'complete',missing_costs:0},seconds:42,status:'completed'};
const snapshot={run_tag:'selected',run_configuration:{trials:1,waves:2},stale:false,health:{memstara:{up:true},core:{up:true}},results:[],board:{tasks:[]},
  report:{status:'running',text:'',explanation_outputs:[{loop:1,result_id:1,status:'completed',text:'# Saved explanation'},{loop:2,result_id:2,status:'running',text:'Partial text'}]},
  agents:[],scene:{places:[],agents:[],flashes:[]},feed:[],access:{rows:[],windows:[]},runs:[]};
const totals={updated_at:'2026-10-28T01:00:00Z',executions:[{run_tag:'selected',model:'Fixture',provider:'test',loops:[{...metric,number:1},{...metric,number:2,status:'running'}],loop_summary:{},unassigned:{...metric,calls:0}}],pipelines:[],total:metric};
const browser=await launchResponsiveBrowser();
try {for(const width of [390,1440]) {
  const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const writes=[];page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url());});
  await page.route('**/api/telemetry/totals',route=>route.fulfill({json:totals}));
  await page.route('**/control/**',route=>route.fulfill({json:{pipelines:[],skills:[]}}));
  const goto=()=>page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/execution-tiles.fixture.html`);
  const deliver=(data=snapshot,error=null,requested=data.run_tag)=>page.evaluate(({data,error,requested})=>window.deliverOutputs(data,error,requested),{data,error,requested});
  await goto();await deliver();
  const nav=page.getByRole('complementary',{name:'View navigation'});
  const conclusions=nav.getByRole('button',{name:'Conclusions',exact:true});
  const usage=nav.getByRole('button',{name:'Usage',exact:true});
  const badge=button=>button.locator('.results-new-badge');
  const panel=page.getByTestId('execution-outputs');
  await expect(badge(conclusions)).toBeVisible();await expect(badge(usage)).toBeVisible();
  assert.equal(await badge(usage).locator('i').evaluate(el=>getComputedStyle(el).animationName),'none');
  await conclusions.click();await expect(panel.locator('.execution-output-tile')).toHaveCount(1);
  await expect(badge(conclusions)).toBeVisible(); // Merely opening the list does not read the output.
  await panel.locator('.execution-output-tile').click();
  await expect(panel).toContainText('Saved explanation');await expect(badge(conclusions)).toHaveCount(0);
  await expect(badge(usage)).toBeVisible();
  await deliver();await expect(badge(conclusions)).toHaveCount(0); // Polls do not re-announce the same revision.
  await usage.click();await expect(badge(usage)).toBeVisible();
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  await panel.locator('.execution-output-tile').click();await expect(badge(usage)).toBeVisible();
  await page.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
  await expect(badge(usage)).toHaveCount(0);
  await goto();await deliver();await expect(badge(conclusions)).toHaveCount(0);await expect(badge(usage)).toHaveCount(0);
  // A newly completed replicate announces only its view and is not swallowed by an old receipt.
  const completed=structuredClone(snapshot);completed.report.explanation_outputs[1]={loop:2,result_id:2,status:'completed',text:'Second explanation'};
  await deliver(completed);await expect(badge(conclusions)).toBeVisible();await expect(badge(usage)).toHaveCount(0);
  await conclusions.click();await expect(panel.locator('.execution-output-tile')).toHaveCount(2);
  await deliver(completed,'Connection interrupted');
  await panel.locator('.execution-output-tile[data-loop="2"]').click();await expect(badge(conclusions)).toBeVisible();
  await deliver(completed);await expect(badge(conclusions)).toHaveCount(0);
  // A late revision is new; a response for another execution must never announce it.
  completed.report.explanation_outputs[1].text='Updated second explanation';
  await usage.click();await deliver(completed,null,'another-run');await expect(badge(conclusions)).toHaveCount(0);
  await deliver(completed);await expect(badge(conclusions)).toBeVisible();
  const other={...completed,run_tag:'other'};await deliver(other);await expect(badge(conclusions)).toBeVisible();await expect(badge(usage)).toHaveCount(0);
  const overflow=await nav.evaluate(el=>el.scrollWidth>el.clientWidth+2);
  if(width===1440)assert.equal(overflow,false);
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  console.log(`PASS ${width}px: independent output receipts, completed-only badges, visibility, persistence, revisions, run isolation, reduced motion; no writes or LLM calls`);
  await page.close();
}}finally{await browser.close();}
