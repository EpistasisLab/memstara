import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const browser=await launchResponsiveBrowser();
const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
const receiptKey='memstara-results-read-v1';
const result=(id,auc=.65)=>({result_id:id,task_id:id,trial:id-1,perspective:`Question ${id}`,hypothesis:`Hypothesis ${id}`,columns_used:['age'],columns_missing:[],importance:{age:.1},okf_concept_ids:[],y_column:'outcome',auc,model:'lr',interpretation:'Recorded interpretation',created_at:`2026-10-22T12:${String(id).padStart(2,'0')}:00Z`});
const snapshot=(rows,tag='alpha-run')=>({run_tag:tag,run_configuration:{trials:1,pipeline_name:tag==='alpha-run'?'Alpha research':'Beta research'},generated_at:'2026-10-22T13:00:00Z',stale:false,health:{core:{up:true},memstara:{up:true}},runs:[],scene:{places:[],agents:[],flashes:[]},board:{lanes:{},tasks:[]},feed:[],agents:[],access:{rows:[],windows:[]},results:rows,report:null});
const errors=[],writes=[];
try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});page.setDefaultTimeout(10000);
  page.on('pageerror',e=>errors.push(e.message));
  await page.route(/\/(api|control)\//,r=>{
    if(r.request().method()!=='GET'){writes.push(r.request().url());return r.abort();}
    return r.fulfill({status:503,json:{error:'Fixture: no server records'}});
  });
  const goto=async()=>{await page.goto(root+'/tests/results-notices.fixture.html');await page.waitForFunction(()=>typeof window.deliverResults==='function');};
  const deliver=(rows,tag='alpha-run',requested=tag,error=null)=>page.evaluate(({value,requested,error})=>window.deliverResults(value,requested,error),{value:snapshot(rows,tag),requested,error});
  const nav=page.getByRole('complementary',{name:'View navigation'});
  const launch=nav.getByRole('button',{name:'Results',exact:true});
  const badge=launch.locator('.results-new-badge');
  const dock=page.locator('#results-panel');
  const selected=dock.getByRole('article',{name:'Selected analysis evidence'});
  const seen=()=>page.evaluate(key=>JSON.parse(localStorage.getItem(key)||'{}'),receiptKey);
  const close=()=>nav.getByRole('button',{name:'Floor plan',exact:true}).click();
  await goto();
  await deliver([]);await expect(badge).toHaveCount(0);
  await deliver([result(1,null)]);await expect(badge).toHaveCount(0);
  await deliver([result(1,0)]);await expect(badge).toBeVisible();
  await expect(launch).toHaveAccessibleDescription(/1 new result is ready/);
  const original=await badge.elementHandle();
  await deliver([result(1,0)]);
  assert(await original.evaluate(e=>e.isConnected),'Repeated polling must not restart the arrival animation');
  await expect(badge.locator('i')).toHaveCSS('animation-iteration-count','2');
  for(const theme of ['light','dark'])for(const width of [1440,768,390,320]){
    await page.setViewportSize({width,height:900});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
    await launch.scrollIntoViewIfNeeded();await expect(launch).toBeInViewport();
    const bounds=await launch.evaluate(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,viewport:innerWidth,width:e.clientWidth,scroll:e.scrollWidth}));
    assert(bounds.left>=0&&bounds.right<=bounds.viewport&&bounds.scroll<=bounds.width+1,`${theme} ${width}: ${JSON.stringify(bounds)}`);
    if(process.env.MEMSTARA_SCREENSHOT_DIR&&[1440,390].includes(width))await page.screenshot({path:`${process.env.MEMSTARA_SCREENSHOT_DIR}/results-notice-${theme}-${width}.png`});
  }
  await page.emulateMedia({reducedMotion:'reduce'});await expect(badge.locator('i')).toHaveCSS('animation-name','none');
  await page.emulateMedia({reducedMotion:'no-preference'});await page.setViewportSize({width:1440,height:900});
  await launch.click();await expect(selected).toContainText('Hypothesis 1');await expect(badge).toHaveCount(0);
  assert.equal((await seen())['alpha-run:1'],true);
  // Keep the selected evidence stable while a later loop completes.
  await deliver([result(1,0),result(2)]);
  await expect(dock.getByRole('button',{name:'View latest results'})).toBeVisible();
  await expect(selected).toContainText('Hypothesis 1');assert.equal((await seen())['alpha-run:2'],undefined);
  await dock.getByRole('button',{name:'View latest results'}).click();await expect(selected).toContainText('Hypothesis 2');
  await expect(badge).toHaveCount(0);await close();
  // Opening chooses the latest timestamp, independent of API ordering or ID order.
  await deliver([result(3),result(2),result(1,0)]);await expect(badge).toBeVisible();await launch.click();
  await expect(selected).toContainText('Hypothesis 3');await close();
  await goto();await deliver([result(3),result(2),result(1,0)]);await expect(badge).toHaveCount(0);
  // The same result number in another execution is still unread. Mismatched snapshots do not alert.
  await deliver([result(4)],'alpha-run','beta-run');await expect(badge).toHaveCount(0);
  await deliver([result(1)],'beta-run');await expect(badge).toBeVisible();await launch.click();
  await expect(selected).toContainText('Beta research');await close();
  // A failed load must not consume an unread notice. Recovery while visible can acknowledge it.
  await deliver([result(4)],'alpha-run','alpha-run','Connection interrupted');await launch.click();
  await expect(dock).toContainText('Showing the last available results');assert.equal((await seen())['alpha-run:4'],undefined);
  await deliver([result(4)]);await expect(badge).toHaveCount(0);await close();
  // Opening without results, then receiving them, acknowledges only once content is visible.
  await deliver([]);await launch.click();await expect(dock).toContainText('No finished results yet.');
  await deliver([result(5)]);await expect(selected).toContainText('Hypothesis 5');await expect(badge).toHaveCount(0);await close();
  // A background tab must retain the receipt until the user returns.
  await deliver([result(6)]);
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  await launch.click();await expect(selected).toContainText('Hypothesis 6');assert.equal((await seen())['alpha-run:6'],undefined);
  await page.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
  await expect(badge).toHaveCount(0);await close();
  // Reading one execution cannot silently acknowledge another one.
  await deliver([result(7)]);await expect(badge).toBeVisible();
  await deliver([result(1)],'beta-run');await expect(badge).toHaveCount(0);
  await deliver([result(7)]);await expect(badge).toBeVisible();
  // Out-of-order arrival of a lower ID must not be lost to a high-watermark receipt.
  await launch.click();await expect(badge).toHaveCount(0);await close();
  await deliver([result(7),{...result(2),result_id:20}]);await expect(badge).toBeVisible();
  await launch.click();await expect(selected).toContainText('Hypothesis 7');await expect(badge).toHaveCount(0);await close();
  await deliver([result(7),{...result(2),result_id:20},{...result(2),result_id:19}]);await expect(badge).toBeVisible();
  // Corrupt or unavailable browser storage must not break the workspace.
  await page.evaluate(key=>localStorage.setItem(key,'invalid json'),receiptKey);await goto();await deliver([result(1)]);await expect(badge).toBeVisible();
  await page.evaluate(()=>{Storage.prototype.setItem=function(){throw new DOMException('Blocked','SecurityError');};});
  await launch.click();await expect(selected).toContainText('Hypothesis 1');await expect(badge).toHaveCount(0);await close();
  await deliver([result(1)]);await expect(badge).toHaveCount(0);
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  console.log('Results arrivals, visible receipts, persistence, pipeline isolation, repeat polling, errors, reduced motion and responsive themes passed. No backend writes or model calls.');
}finally{await browser.close();}
