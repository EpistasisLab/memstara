import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 const page=await browser.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const items=[1,2,3].map(n=>({id:'layout-'+n,number:n,name:'Research pipeline '+n,configuration:{skill:'test',hypothesis_agents:1,interpreter_agents:1,playbook_hypothesis:'default',playbook_ml:'default',playbook_interpreter:'default',playbook_explanation:'default'},running:null,latest:null,progress:{}}));
 await page.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:items}:{}}));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Layout fixture: results unavailable'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.getByRole('button',{name:'View floor plan',exact:true}).click();
 await page.locator('.floor-canvas .react-flow').waitFor();
 const resources=page.getByRole('button',{name:'Shared resources',exact:true});
 await resources.click();await page.locator('.react-flow__node[data-id="resources-zone"]').waitFor();
 await resources.click();await page.locator('.react-flow__node[data-id="resources-zone"]').waitFor({state:'hidden'});
 for(const theme of ['light','dark'])for(const width of [1920,1440,1024,768,390,320]){
  await page.setViewportSize({width,height:900});
  await page.getByRole('button',{name:'Workspace settings',exact:true}).click();
  await page.getByRole('dialog',{name:'Workspace settings',exact:true}).getByRole('button',{name:'Reset window layout',exact:true}).click();
  await page.keyboard.press('Escape');await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await page.waitForTimeout(500);
  const g=await page.locator('.floor-canvas').evaluate(e=>({h:e.getBoundingClientRect().height,bottom:e.getBoundingClientRect().bottom,w:e.clientWidth,display:getComputedStyle(e.parentElement).display}));
  assert(g.h>=260,JSON.stringify({theme,width,g}));assert(g.w>100);assert(g.display!=='none');
  const floor=await page.locator('#workspace-pipeline').boundingBox();assert(g.bottom<=floor.y+floor.height+1,JSON.stringify({width,g,floor,reason:'Canvas clipped by window'}));
  const visible=await page.locator('.floating-window:not([hidden])').evaluateAll(es=>es.filter(e=>e.id!=='workspace-control').map(e=>({id:e.id,x:e.offsetLeft,y:e.offsetTop,w:e.offsetWidth,h:e.offsetHeight})));
  for(let i=0;i<visible.length;i++)for(let j=i+1;j<visible.length;j++){const a=visible[i],b=visible[j];assert(a.x+a.w<=b.x+1||b.x+b.w<=a.x+1||a.y+a.h<=b.y+1||b.y+b.h<=a.y+1,'Overlapping windows');}
  for(const name of ['Results','Final report']){if(await page.getByRole('tab',{name,exact:true}).count())await page.getByRole('tab',{name,exact:true}).click();await page.waitForTimeout(60);}
  await page.locator('#workspace-pipeline').scrollIntoViewIfNeeded();
  const show=page.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
  await page.getByRole('button',{name:'Inspect Research pipeline 2',exact:true}).click();await page.waitForTimeout(600);
  const before=await page.locator('.react-flow__viewport').getAttribute('style');
  const restore=page.getByRole('button',{name:'Expand Results',exact:true});if(await restore.count())await restore.click();
  const splitter=page.getByRole('button',{name:'Resize pipeline and analysis space',exact:true});await splitter.focus();await page.keyboard.press('ArrowDown');await page.waitForTimeout(400);
  const after=await page.locator('.react-flow__viewport').getAttribute('style');assert.equal(after,before,'Resize changed diagram viewport');
  const max=page.locator('#workspace-pipeline').getByRole('button',{name:/Maximize .* window/});await max.click();assert.equal(await page.locator('.floating-window:not([hidden])').count(),2);
  await page.locator('#workspace-pipeline').getByRole('button',{name:/Restore .* window/}).click();
  console.log(JSON.stringify({theme,width,canvas:g,windows:visible.length,resize:'preserved'}));
  if(width===1440||width===390){await page.locator('.docked-workspace').evaluate(e=>e.scrollTop=0);await page.screenshot({path:`/tmp/floor-layout-${theme}-${width}.png`});}
 }
 assert.deepEqual(errors,[]);
}finally{await browser.close();}
