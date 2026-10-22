import {chromium, expect} from '@playwright/test';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const pipelines=[1,2,3].map(n=>({id:`cost-${n}`,number:n,name:`Research pipeline ${n}`,configuration:{},running:null,latest:{run_tag:`cost-run-${n}`},progress:{}}));
const amounts=[1.49954,1.507792,1.712369];
let mode='complete',reads=0,empty=false,changedScope=false;
const errors=[],writes=[];
try {
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
 await page.route(/\/(api|control)\//,async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname;
  if(request.method()!=='GET'){writes.push(path);return route.abort();}
  if(path==='/control/pipelines')return route.fulfill({json:{pipelines:empty?[]:pipelines.map(p=>changedScope?{...p,latest:{run_tag:p.latest.run_tag+'-new'}}:p)}});
  if(path==='/api/workspace-cost'){
   reads++;
   if(mode==='error')return route.fulfill({status:503,json:{detail:'Fixture unavailable'}});
   const tags=url.searchParams.get('run_tags').split(',');
   const partial=mode==='partial'||mode==='unknown';
   const executions=tags.map((run_tag,index)=>({run_tag,usd:mode==='unknown'?0:amounts[index],status:partial?'partial':'complete',missing_costs:partial?1:0,pending_runs:0,missing_archives:0}));
   return route.fulfill({json:{usd:executions.reduce((sum,e)=>sum+e.usd,0),status:partial?'partial':'complete',missing_costs:partial?3:0,pending_runs:0,missing_archives:0,run_tags:tags,executions,shared_agent_runs:0}});
  }
  if(path==='/api/discovery/live')return route.fulfill({json:{events:[],questions:[],results:[],reports:{},record_limit:200,generated_at:new Date().toISOString()}});
  return route.fulfill({status:503,json:{detail:'Not needed for cost fixture'}});
 });
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 const trigger=page.getByRole('button',{name:'Estimated total. Show pipeline cost breakdown',exact:true});
 await expect(trigger).toContainText('$4.7197');
 await expect(page.getByRole('dialog',{name:'Workspace summary',exact:true})).not.toBeVisible();
 const refresh=async()=>{
  const before=reads;
  await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
  await expect.poll(()=>reads).toBeGreaterThan(before);
 };
 for(const theme of ['light','dark'])for(const width of [1440,1024,768,390,320]){
  await page.setViewportSize({width,height:900});
  await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
  await expect(trigger).toBeInViewport();
  const header=await page.locator('.unified-topbar').evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth}));
  assert(header.scroll<=header.width+2,JSON.stringify({theme,width,header}));
  const areas=await page.locator('.memstara-identity-row > *').evaluateAll(items=>items.filter(e=>e.getClientRects().length).map(e=>{const b=e.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom};}));
  for(let i=0;i<areas.length;i++)for(let j=i+1;j<areas.length;j++)assert(areas[i].right<=areas[j].left+1||areas[j].right<=areas[i].left+1||areas[i].bottom<=areas[j].top+1||areas[j].bottom<=areas[i].top+1,`Header controls overlap at ${width}`);
  await trigger.click();
  const panel=page.getByRole('dialog',{name:'Pipeline costs',exact:true});
  await expect(panel).toBeVisible();
  await expect(panel.locator('tbody tr')).toHaveCount(3);
  await expect(panel.locator('tfoot')).toContainText('$4.7197');
  const geometry=await panel.evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,viewport:innerWidth}));
  assert(geometry.scroll<=geometry.width+1&&geometry.left>=0&&geometry.right<=geometry.viewport,JSON.stringify({width,geometry}));
  if([1440,390].includes(width))await page.screenshot({path:`/tmp/workspace-cost-${theme}-${width}.png`});
  await page.keyboard.press('Escape');
  await expect(panel).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await page.getByRole('button',{name:'Workspace summary',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Workspace summary',exact:true}).locator('.summary-cost strong')).toHaveText('$4.7197');
  await page.keyboard.press('Escape');
 }
 // Closing the summaries does not stop refreshes; missing prices are never free.
 mode='partial';await refresh();await expect(trigger).toContainText('Partial estimate');await expect(trigger).toContainText('$4.7197');
 mode='unknown';await refresh();await expect(trigger).toContainText('Not available');await expect(trigger).not.toContainText('$0.0000');
 mode='complete';await refresh();await expect(trigger).toContainText('$4.7197');
 mode='error';await refresh();await expect(trigger).toContainText('Update delayed');await expect(trigger).toContainText('$4.7197');
 // A changed execution set must not inherit the preceding set's subtotal.
 changedScope=true;
 await expect(trigger).toContainText('Not available',{timeout:20000});
 await expect(trigger).not.toContainText('$4.7197');
 mode='complete';await refresh();await expect(trigger).toContainText('$4.7197');
 // Long names and large amounts remain readable in the compact breakdown.
 pipelines[0].name='Long pipeline name '.repeat(18);amounts[0]=1234567.125;
 await page.reload();await expect(trigger).toContainText('$1234570.3452');
 await trigger.click();
 const panel=page.getByRole('dialog',{name:'Pipeline costs',exact:true});
 await expect(panel.locator('tbody tr').first()).toContainText(pipelines[0].name.trim());
 const overflow=await panel.evaluate(e=>e.scrollWidth>e.clientWidth+1);assert(!overflow);
 await panel.getByRole('button',{name:'View in Telemetry',exact:true}).click();
 await expect(panel).not.toBeVisible();await expect(page.locator('.telemetry-workspace')).toBeVisible();
 empty=true;await page.reload();await expect(trigger).toContainText('No executions');await expect(trigger).not.toContainText('$0.0000');
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 console.log('Persistent cost, shared summary/breakdown values, ten responsive/theme cases, Escape/focus, partial/unknown/stale costs, execution-scope changes, large costs, long names, Telemetry navigation and empty workspace passed. No writes or model calls.');
}finally{await browser.close();}
