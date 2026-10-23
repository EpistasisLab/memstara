import {launchResponsiveBrowser} from './responsive-browser.mjs';
import assert from 'node:assert/strict';
const b=await launchResponsiveBrowser();
try{
 const p=await b.newPage();p.setDefaultTimeout(15000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
 const items=Array.from({length:30},(_,i)=>({id:'layout-'+i,number:i+1,name:'Research '+(i+1)+' — substance use and clinical outcomes',configuration:{skill:'test',waves:10,hypothesis_agents:1,interpreter_agents:1},running:null,
 latest:i%2?{run_tag:'fixture-'+i,exit_code:0,configuration:{waves:10},infrastructure_status:{status:'interrupted',message:'Recorded connection interruption. Previous results are retained for review.'}}:null,
 progress:{stage:'report',exploration:{outcome:'completed',completed:10,blocked:0}}}));
 await p.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:items}:{}}));
 await p.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Layout fixture'}}));
 await p.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');await p.locator('[aria-label="View navigation"]').getByRole('button',{name:'Experiments',exact:true}).click();
 for(const width of [1440,1024,768,390,320]){
  await p.setViewportSize({width,height:800});
  await p.getByRole('button',{name:'Workspace settings',exact:true}).click();await p.getByRole('dialog',{name:'Workspace settings',exact:true}).getByRole('button',{name:'Reset window layout',exact:true}).click();await p.keyboard.press('Escape');
  await p.locator('.floor-canvas').waitFor();
  const show=p.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();const previous=p.getByRole('button',{name:'Previous',exact:true});if(await previous.isVisible()&&await previous.isEnabled())await previous.click();
  const inspect=p.getByRole('button',{name:'Inspect '+items[1].name,exact:true});await inspect.click();
  const reopenAfterSelect=p.getByRole('button',{name:'Show pipeline list',exact:true});if(await reopenAfterSelect.isVisible())await reopenAfterSelect.click();
  const actions=p.getByRole('group',{name:'Actions for '+items[1].name,exact:true});
  await actions.scrollIntoViewIfNeeded();
  const controls=await actions.boundingBox();const floor=await p.locator('#workspace-pipeline').boundingBox();
  assert(await actions.evaluate(e=>!!e.closest('.pipeline-browser-row')));
  assert.equal(await p.locator('[aria-label="Selected pipeline controls"]').count(),0);
  assert(await actions.getByRole('button',{name:'Additional analysis '+items[1].name,exact:true}).isVisible());
  const canvas=await p.locator('.floor-canvas').boundingBox();assert(canvas.height>=260);assert(canvas.y+canvas.height<=floor.y+floor.height+1,JSON.stringify({width,canvas,floor,controls}));
  if(width===1440){console.log(await p.locator('.pipeline-browser').evaluate(e=>[...e.querySelectorAll('#pipeline-browser-content,.pipeline-browser-list,.pipeline-selected-controls,.pipeline-browser-footer,.pipeline-browser-heading,.pipeline-browser-search-tools')].map(n=>({class:n.className,height:n.clientHeight,scroll:n.scrollHeight}))));await p.screenshot({path:'/tmp/pipeline-list-debug.png'});const list=p.locator('.pipeline-browser-list');assert(await list.evaluate(e=>e.clientHeight>=180));await list.evaluate(e=>e.scrollTop=e.scrollHeight);await actions.scrollIntoViewIfNeeded();assert(await actions.getByRole('button',{name:'Additional analysis '+items[1].name,exact:true}).isVisible());}
  const reopen=p.getByRole('button',{name:'Show pipeline list',exact:true});if(await reopen.isVisible())await reopen.click();
  await p.getByRole('button',{name:'Next',exact:true}).click();await p.getByRole('button',{name:'Inspect '+items[29].name,exact:true}).click();
  console.log(JSON.stringify({width,canvasHeight:canvas.height,controlsHeight:controls.height,longHistory:'passed'}));
  await p.screenshot({path:'/tmp/pipeline-list-'+width+'.png'});
 }
 assert.deepEqual(errors,[]);
}finally{await b.close();}
