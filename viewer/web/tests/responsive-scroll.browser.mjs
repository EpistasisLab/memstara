import {expect} from '@playwright/test';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
import assert from 'node:assert/strict';
const browser=await launchResponsiveBrowser();
const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
try{
 for(const [width,height] of [[360,700],[390,500],[768,700],[1024,500],[1280,900],[1440,700],[1920,900]]){
  const page=await browser.newPage({viewport:{width,height}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/control/**',r=>r.fulfill({json:{inputs:[],models:[],skills:[]}}));
  await page.goto(root+'/tests/responsive-scroll.fixture.html');
  const dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});
  await dialog.getByRole('button',{name:/Agent skills/}).click();
  await dialog.locator('.comb-skill-picker > summary').click();
  await expect(dialog.locator('.comb-skill-card')).toHaveCount(16);
  for(let i=0;i<8;i++)await dialog.locator('.comb-skill-card input').nth(i).check();
  await dialog.locator('.comb-skill-card details > summary').first().click();
  const scrolls=await dialog.evaluate(d=>[d,...d.querySelectorAll('*')].filter(e=>/auto|scroll/.test(getComputedStyle(e).overflowY)&&e.scrollHeight>e.clientHeight+2).map(e=>e.className));
  assert.equal(scrolls.length,1,JSON.stringify({width,height,scrolls}));
  assert(await dialog.evaluate(d=>d.scrollWidth<=d.clientWidth+2),'dialog horizontal overflow');
  const scroller=await page.evaluate(()=>innerHeight<=550)?dialog:dialog.locator('.comb-step-content');
  await scroller.evaluate(e=>e.scrollTop=0);
  const box=await scroller.boundingBox();await page.mouse.move(box.x+box.width*.75,box.y+Math.min(box.height*.65,150));
  await page.mouse.wheel(0,350);
  await expect.poll(()=>scroller.evaluate(e=>e.scrollTop)).toBeGreaterThan(0);
  // Wheel over an expanded instruction must move the same outer region.
  const pre=dialog.locator('.comb-skill-card pre').first();await pre.scrollIntoViewIfNeeded();
  const before=await scroller.evaluate(e=>e.scrollTop);const pb=await pre.boundingBox();
  const sb=await scroller.boundingBox();await page.mouse.move(sb.x+sb.width*.8,Math.max(sb.y+25,Math.min(sb.y+sb.height-25,pb.y+50)));
  await page.mouse.wheel(0,250);await expect.poll(()=>scroller.evaluate(e=>e.scrollTop)).toBeGreaterThan(before);
  const next=dialog.locator('.comb-footer button').last();await next.focus();
  await expect(next).toBeInViewport();await page.keyboard.press('Shift+Tab');
  await page.setViewportSize({width:width===360?768:360,height:500});
  await expect(dialog.locator('.comb-skill-card input:checked')).toHaveCount(8);
  assert(await dialog.evaluate(d=>d.scrollWidth<=d.clientWidth+2),'resize overflow');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,height,oneScroll:true,wheel:true,focus:true,resize:true}));
  await page.close();
 }
 for(const mode of ['single','editor'])for(const [width,height] of [[390,500],[1440,900]]){
  const page=await browser.newPage({viewport:{width,height}});
  await page.route('**/control/**',r=>r.fulfill({json:{inputs:[],models:[],skills:[]}}));
  await page.goto(root+`/tests/responsive-scroll.fixture.html?${mode}=1`);
  if(mode==='single'){
   await page.getByRole('dialog').locator('button[hidden]').filter({hasText:'Selected Pipelines'}).evaluate(e=>e.click());
   await page.getByRole('checkbox',{name:/Use .* for this pipeline/}).check();
   await page.getByRole('button',{name:'Next',exact:true}).click();
   await page.getByText('Read skill instructions',{exact:true}).click();
  }else{
   await page.locator('[aria-label="Review selected skill"] summary').click();
  }
  const dialog=page.getByRole('dialog');await expect(dialog.locator('pre').first()).toBeVisible();
  assert(await dialog.evaluate(d=>d.scrollWidth<=d.clientWidth+2));
  const owners=await dialog.evaluate(d=>[d,...d.querySelectorAll('*')].filter(e=>/auto|scroll/.test(getComputedStyle(e).overflowY)&&e.scrollHeight>e.clientHeight+2).map(e=>e.className));
  assert.equal(owners.length,1,JSON.stringify({mode,width,height,owners}));
  await dialog.locator('button').last().focus();await expect(dialog.locator('button').last()).toBeInViewport();
  console.log(JSON.stringify({mode,width,height,oneScroll:true}));await page.close();
 }
}finally{await browser.close();}
