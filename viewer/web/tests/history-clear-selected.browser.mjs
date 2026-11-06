import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE});
let state={state:'idle',revision:'initial'},cleared=false;
const posts=[],errors=[];
try {
 const context=await browser.newContext();
 await context.route(/\/(api|control)\//,async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  if(path==='/control/history-reset'){
   if(req.method()==='POST'){
    const body=req.postDataJSON();posts.push(body);
    assert.equal(body.scope,'selected');assert.equal(body.pipeline_id,'a');
    assert.equal(body.confirmation,'CLEAR SELECTED HISTORY');
    cleared=true;state={state:'completed',revision:body.request_id,request_id:body.request_id,
     scope:'selected',pipeline_id:'a',pipeline_name:'Experiment A',execution_count:3};
   }
   return route.fulfill({json:state});
  }
  if(path==='/control/pipelines')return route.fulfill({json:{pipelines:[
   {id:'a',number:1,name:'Experiment A',configuration:{},running:cleared?null:{run_tag:'a-retry'},latest:cleared?null:{run_tag:'a-retry'},progress:{}},
   {id:'b',number:2,name:'Experiment B',configuration:{},running:{run_tag:'b-run'},latest:{run_tag:'b-run'},progress:{}}
  ]}});
  if(path==='/api/workspace-cost')return route.fulfill({json:{usd:cleared?7:12,status:'complete',missing_costs:0,pending_runs:0,missing_archives:0,
   run_tags:cleared?['b-run']:['a-retry','b-run'],executions:[...(!cleared?[{run_tag:'a-retry',usd:5,status:'complete'}]:[]),{run_tag:'b-run',usd:7,status:'complete'}],shared_agent_runs:0}});
  assert.equal(req.method(),'GET','No stop, start or unrelated write is allowed');
  return route.fulfill({status:503,json:{detail:'Unused fixture endpoint'}});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto((process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4189')+'/tests/history-clear.fixture.html');
 const cost=page.getByRole('button',{name:'Estimated total. Show pipeline cost breakdown',exact:true});
 await expect(cost).toContainText('$12.0000');
 await page.getByRole('button',{name:'Clear',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Clear experiment history'});
 await dialog.getByRole('radio',{name:/Selected experiment/}).check();
 await dialog.getByRole('combobox',{name:'Experiment to clear'}).selectOption('a');
 await expect(dialog).toContainText('This experiment is running');
 await expect(dialog).toContainText('other experiments will continue');
 const submit=dialog.getByRole('button',{name:'Clear without backup',exact:true});
 await dialog.getByRole('radio',{name:/Clear without backup/}).check();
 await dialog.getByRole('textbox').fill('CLEAR ALL HISTORY');
 await expect(submit).toBeDisabled();
 await dialog.getByRole('textbox').fill('CLEAR SELECTED HISTORY');
 await expect(submit).toBeEnabled();
 // A changed target always requires a new explicit confirmation.
 await dialog.getByRole('combobox').selectOption('b');
 await expect(dialog.getByRole('textbox')).toHaveValue('');
 await expect(submit).toBeDisabled();
 await dialog.getByRole('combobox').selectOption('a');
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:800});
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+1));
 }
 await dialog.getByRole('textbox').fill('CLEAR SELECTED HISTORY');
 await submit.click();
 await expect(cost).toContainText('$7.0000');
 await expect(dialog).toContainText('History for Experiment A has been cleared');
 await expect(dialog).toContainText('Other experiments are retained');
 await expect(dialog).not.toContainText('Estimated total is $0');
 assert.equal(posts.length,1);assert.equal(posts[0].mode,'no_backup');
 assert.deepEqual(errors,[]);
 console.log('Selected scope, explicit target, running warning, confirmation reset, preserved other costs and responsive UI passed. Mocked endpoints only.');
} finally {await browser.close();}
