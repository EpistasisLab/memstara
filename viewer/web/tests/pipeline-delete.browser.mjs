import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) for(const theme of ['light','dark']) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let items=Array.from({length:3},(_,i)=>({id:`p${i}`,number:i===2?100:i+1,name:i===0?'Research Alpha':i===1?'Running research':'A long pipeline name for responsive deletion confirmation',configuration:{waves:10,hypothesis_agents:1,interpret_agents:1},running:i===1?{run_tag:'running',configuration:{waves:10},execution_state:'running'}:null,latest:null,progress:i===2?{counts:{failed:1}}:{}}));
  let attempts=0,fail=true,release;
  let endAttempts=0,failEnd=true;
  await page.route('**/control/**',async route=>{
   if(new URL(route.request().url()).pathname==='/control/runs/running/end'){
    assert.equal(route.request().method(),'POST');endAttempts++;
    return failEnd?route.fulfill({status:503,json:{error:'Fixture end rejected'}}):route.fulfill({json:{stopping:'running'}});
   }
   if(new URL(route.request().url()).pathname!=='/control/pipelines')return route.fulfill({json:{}});
   if(route.request().method()==='GET')return route.fulfill({json:{pipelines:items}});
   const body=route.request().postDataJSON();assert.equal(body.action,'remove');attempts++;
   if(fail)return route.fulfill({status:409,json:{error:'Fixture deletion rejected'}});
   await new Promise(resolve=>{release=resolve;});
   items=items.filter(p=>p.id!==body.id);await route.fulfill({json:{id:body.id}});
  });
  await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Isolated UI fixture'}}));
  await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  async function showList(){const b=page.getByRole('button',{name:'Show pipeline list',exact:true});if(await b.isVisible())await b.click();}
  await showList();await page.locator('.pipeline-card-delete').first().waitFor();assert.equal(await page.locator('.pipeline-card-delete').count(),3);
  assert.equal(await page.locator('.pipeline-card-status-actions .pipeline-card-delete').count(),3);
  assert(await page.locator('.pipeline-card-status-actions').first().evaluate(e=>{
   const badge=e.querySelector('.pipeline-state-badge').getBoundingClientRect();
   const button=e.querySelector('button').getBoundingClientRect();
   return button.left>=badge.right && Math.abs((badge.top+badge.bottom)/2-(button.top+button.bottom)/2)<2;
  }));
  assert(await page.locator('.pipeline-card-header').evaluateAll(headers=>headers.every(e=>{
   const identity=e.querySelector('.pipeline-card-identity').getBoundingClientRect();
   const actions=e.querySelector('.pipeline-card-status-actions').getBoundingClientRect();
   return Math.abs((identity.top+identity.bottom)/2-(actions.top+actions.bottom)/2)<2 && identity.right<=actions.left && e.scrollWidth<=e.clientWidth+1;
  })));
  await page.screenshot({path:`/tmp/pipeline-tile-${width}-${theme}.png`});
  const heading=page.getByRole('button',{name:'Select pipeline 2: Running research',exact:true});
  await heading.click();await showList();assert.equal(await heading.getAttribute('aria-pressed'),'true');
  const firstHeading=page.getByRole('button',{name:'Select pipeline 1: Research Alpha',exact:true});
  await firstHeading.focus();await page.keyboard.press('Enter');await showList();
  assert.equal(await firstHeading.getAttribute('aria-pressed'),'true');
  await heading.click();await showList();
  await page.getByRole('button',{name:'Delete Research Alpha',exact:true}).click();
  let dialog=page.getByRole('dialog',{name:'Delete pipeline?',exact:true});
  await dialog.waitFor();assert.equal(await heading.getAttribute('aria-pressed'),'true');assert.match(await dialog.innerText(),/Research Alpha/);assert.match(await dialog.innerText(),/Saved analysis results remain/);
  assert.equal(await dialog.getByRole('button',{name:'Cancel',exact:true}).evaluate(e=>e===document.activeElement),true);
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(attempts,0);
  await page.getByRole('button',{name:'Delete Running research',exact:true}).click();
  assert.equal(await dialog.getByRole('button',{name:'Delete pipeline',exact:true}).isDisabled(),true);
  await dialog.getByRole('button',{name:'End execution…',exact:true}).click();
  await dialog.getByRole('button',{name:'Keep execution',exact:true}).click();
  assert.equal(endAttempts,0);
  await dialog.getByRole('button',{name:'End execution…',exact:true}).click();
  await dialog.getByRole('button',{name:'Confirm end execution',exact:true}).click();
  await dialog.getByText(/Fixture end rejected/).waitFor();
  assert.equal(attempts,0);assert.equal(endAttempts,1);
  failEnd=false;
  await dialog.getByRole('button',{name:'Confirm end execution',exact:true}).click();
  await dialog.getByText(/Waiting for the server to confirm/).waitFor();
  assert.equal(await dialog.getByRole('button',{name:'Delete pipeline',exact:true}).isDisabled(),true);
  assert.equal(attempts,0);assert.equal(endAttempts,2);
  items[1].running=null;
  await dialog.getByText(/Execution ended. You can now delete/).waitFor();
  assert.equal(await dialog.getByRole('button',{name:'Delete pipeline',exact:true}).isEnabled(),true);
  await dialog.getByRole('button',{name:'Cancel',exact:true}).focus();
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});assert.equal(attempts,0);
  await page.getByRole('button',{name:'Delete Research Alpha',exact:true}).click();
  await dialog.getByRole('button',{name:'Delete pipeline',exact:true}).click();
  await dialog.getByRole('alert').waitFor();assert.equal(await page.locator('.pipeline-card-delete').count(),3);assert.equal(attempts,1);
  fail=false;await dialog.getByRole('button',{name:'Delete pipeline',exact:true}).click();
  await dialog.getByRole('button',{name:'Deleting…',exact:true}).waitFor();
  await page.keyboard.press('Escape');assert.equal(await dialog.isVisible(),true);
  assert.equal(await dialog.getByRole('button',{name:'Cancel',exact:true}).isDisabled(),true);
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  await page.screenshot({path:`/tmp/pipeline-delete-${width}-${theme}.png`});
  while(!release)await new Promise(r=>setTimeout(r,20));release();
  await dialog.waitFor({state:'hidden'});assert.equal(await page.locator('.pipeline-card-delete').count(),2);
  await page.reload();
  // Wait for loading/layout (including the compact ResizeObserver) before opening the list.
  await page.getByRole('button',{name:'Select pipeline 2: Running research',exact:true,includeHidden:true}).waitFor({state:'attached'});
  await page.locator('.pipeline-browser').evaluate(element=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(element.clientWidth)))));
  await showList();await page.locator('.pipeline-card-delete').first().waitFor();assert.equal(await page.locator('.pipeline-card-delete').count(),2);
  assert.equal(attempts,2);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({width,theme,cancel:'pass',activeGuard:'pass',failure:'pass',pendingEscape:'pass',deleteAndReload:'pass'}));await page.close();
 }
}finally{await browser.close();}
