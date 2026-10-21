import {expect} from '@playwright/test';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
import assert from 'node:assert/strict';
const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
const browser=await launchResponsiveBrowser();
const metric={calls:5,tokens:12345,cost:{usd:.5,status:'complete',missing_costs:0},seconds:125,status:'completed',duration_basis:'Synthetic timing basis '.repeat(15)};
const loops=Array.from({length:50},(_,i)=>({...metric,number:i+1}));
const summary={sample_count:0,completed_count:50,excluded_completed:50,other_loops:0,seconds:null,usd:null,tokens:null,basis:'Synthetic fixture'};
const totals={scope:'Synthetic records',updated_at:'2026-10-21T12:00:00Z',total:metric,pipelines:[],loop_summary:summary,executions:[{...metric,run_tag:'responsive-fixture',pipeline_id:'fixture',loops,loop_summary:summary,unassigned:metric}]};
try{for(const [width,height] of [[360,500],[390,700],[768,500],[1024,700],[1440,900],[1920,900]]){
 const page=await browser.newPage({viewport:{width,height}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',r=>{
  const u=new URL(r.request().url());
  if(u.pathname==='/api/telemetry/totals')return r.fulfill({json:totals});
  if(u.pathname==='/api/cost-details')return r.fulfill({json:{run_tag:'responsive-fixture',loop:u.searchParams.has('loop')?Number(u.searchParams.get('loop')):null,status:'partial',usd:.5,recorded_calls:1,unpriced_calls:1,expected_calls:1,groups:[],records:[],coverage_note:'Long partial usage notice '.repeat(80)}});
  return r.fulfill({json:{}});
 });
 await page.goto(root+'/tests/responsive-reading.fixture.html');
 await page.getByText('Usage & cost details',{exact:true}).click();
 await page.getByText('Estimated cost · Motoro LLM requests',{exact:true}).click();
 await page.getByText('Execution LLM request subtotal:',{exact:false}).waitFor();
 await page.locator('summary').filter({hasText:/^Compare loops/}).click();
 const pane=page.locator('.telemetry-workspace');
 const owners=await pane.evaluate(d=>[d,...d.querySelectorAll('*')].filter(e=>/auto|scroll/.test(getComputedStyle(e).overflowY)&&e.scrollHeight>e.clientHeight+2).map(e=>e.className));
 assert.equal(owners.length,1,JSON.stringify({width,height,owners}));
 const overflow=await pane.evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth,items:[...e.querySelectorAll('*')].filter(n=>n.getBoundingClientRect().right>e.getBoundingClientRect().right+2).slice(0,12).map(n=>({tag:n.tagName,cls:n.className,text:n.textContent?.slice(0,80)}))}));
 assert(overflow.scroll<=overflow.width+2,JSON.stringify(overflow));
 await pane.evaluate(e=>e.scrollTop=0);const box=await pane.boundingBox();await page.mouse.move(box.x+box.width*.6,box.y+box.height*.7);await page.mouse.wheel(0,400);
 await expect.poll(()=>pane.evaluate(e=>e.scrollTop)).toBeGreaterThan(0);
 await page.getByRole('combobox',{name:'Loop to inspect'}).focus();await expect(page.getByRole('combobox',{name:'Loop to inspect'})).toBeInViewport();
 await page.getByRole('combobox',{name:'Loop to inspect'}).selectOption('2');
 await page.setViewportSize({width:390,height:500});await expect(page.getByRole('combobox',{name:'Loop to inspect'})).toHaveValue('2');
 await page.setViewportSize({width,height});
 await page.goto(root+'/tests/responsive-reading.fixture.html?report=1');
 await page.getByRole('region',{name:'Report table — scroll horizontally to see all columns'}).waitFor();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'report page overflow');
 await page.getByRole('button',{name:'Next page',exact:true}).focus();await page.keyboard.press('Enter');await page.getByText('Page 2 of',{exact:false}).waitFor();
 assert.deepEqual(errors,[]);console.log(JSON.stringify({width,height,telemetrySingleScroll:true,longReport:true,pagination:true,selectionRetained:true}));await page.close();
}}finally{await browser.close();}
