import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE});
let state={state:'idle',revision:'initial'},cleared=false,posts=[],backupFailure=false;
const errors=[];
try{
 const context=await browser.newContext();
 await context.route(/\/(api|control)\//,async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  if(path==='/control/history-reset'){
   if(request.method()==='POST'){
    const body=request.postDataJSON();posts.push(body);
    if(backupFailure){state={state:'failed',revision:'initial',message:'Backup failed. No history was deleted.',failed_phase:'backing_up'};return route.fulfill({status:202,json:state});}
    const id=body.request_id;
    cleared=true;state={state:'completed',revision:id,request_id:id,mode:body.mode,
     ...(body.mode==='backup'?{backup:{id,location:`outputs/history-backups/${id}`,download:`/control/history-reset/backups/${id}/download`}}:{})};
   }
   return route.fulfill({json:state});
  }
  if(path==='/control/pipelines')return route.fulfill({json:{pipelines:[{id:'configured',number:1,name:'Preserved pipeline',configuration:{},running:null,latest:cleared?null:{run_tag:'old-run'},progress:{}}]}});
  if(path==='/api/workspace-cost')return route.fulfill({json:{usd:12,status:'complete',missing_costs:0,pending_runs:0,missing_archives:0,run_tags:['old-run'],executions:[{run_tag:'old-run',usd:12,status:'complete'}],shared_agent_runs:0}});
  if(request.method()!=='GET')throw new Error('Unexpected write '+path);
  return route.fulfill({status:503,json:{detail:'Unused fixture endpoint'}});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 const other=await context.newPage();other.on('pageerror',e=>errors.push(e.message));
 const url=(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4189')+'/tests/history-clear.fixture.html';
 await page.goto(url);await other.goto(url);
 const cost=page.getByRole('button',{name:'Estimated total. Show pipeline cost breakdown',exact:true});
 await expect(cost).toContainText('$12.0000');
 await page.evaluate(()=>{
  localStorage.setItem('memstara-draft-v1','{"model":"preserve"}');
  localStorage.setItem('memstara-theme-v2','dark');
  localStorage.setItem('memstara-output-read-v1','old');
  window.seedCachedHistory();
 });
 await other.evaluate(()=>window.seedCachedHistory());
 await expect(other.getByTestId('cached-results')).toContainText('1');
 await page.getByRole('button',{name:'Clear',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Clear experiment history'});
 await expect(dialog).toBeVisible();
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:800});
  const box=await dialog.evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,viewport:innerWidth}));
  assert(box.scroll<=box.width+1&&box.left>=0&&box.right<=box.viewport);
 }
 const backup=dialog.getByRole('button',{name:'Back up and clear',exact:true});
 await expect(backup).toBeDisabled();assert.equal(posts.length,0);
 await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();assert.equal(posts.length,0);
 await page.getByRole('button',{name:'Clear',exact:true}).click();
 await dialog.getByRole('textbox').fill('CLEAR ALL HISTORY');
 backupFailure=true;await backup.click();
 await expect(dialog.getByRole('alert')).toContainText('No history was deleted');
 await expect(cost).toContainText('$12.0000');
 await expect(page.getByTestId('cached-results')).toContainText('1');
 backupFailure=false;await backup.click();
 await expect(cost).toContainText('$0.0000');
 await expect(page.getByTestId('cached-results')).toContainText('0');
 await expect(page.getByTestId('cached-snapshot')).toContainText('no');
 await expect(other.getByTestId('cached-results')).toContainText('0');
 await expect(other.getByRole('button',{name:'Estimated total. Show pipeline cost breakdown'})).toContainText('$0.0000');
 const success=page.getByRole('dialog',{name:'Clear experiment history'});
 await expect(success.getByRole('link',{name:'Download verified backup'})).toBeVisible();
 assert.equal(await page.evaluate(()=>localStorage.getItem('memstara-draft-v1')),'{"model":"preserve"}');
 assert.equal(await page.evaluate(()=>localStorage.getItem('memstara-theme-v2')),'dark');
 assert.equal(await page.evaluate(()=>localStorage.getItem('memstara-output-read-v1')),null);
 await success.getByRole('button',{name:'Done',exact:true}).click();
 // A later clear still opens the choices, rather than trapping the user on the receipt.
 await page.getByRole('button',{name:'Clear',exact:true}).click();
 await expect(dialog.getByRole('radio',{name:/Clear without backup/})).toBeVisible();
 await dialog.getByRole('radio',{name:/Clear without backup/}).check();
 await dialog.getByRole('textbox').fill('CLEAR ALL HISTORY');
 await dialog.getByRole('button',{name:'Clear without backup',exact:true}).click();
 await expect.poll(()=>posts.length).toBe(3);
 assert.deepEqual(posts.map(p=>p.mode),['backup','backup','no_backup']);
 assert(posts.every(p=>p.confirmation==='CLEAR ALL HISTORY'));
 assert.deepEqual(errors,[]);
 console.log('Both clear choices, typed confirmation, cancel, failed backup preservation, zero costs, all-tab memory clearing, retained settings, backup link and responsive dialog passed. Mocked endpoints only.');
}finally{await browser.close();}
