import {chromium, expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const webRoot=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const writes=[],errors=[];
try{
 for(const width of [1440,768,390,320])for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport:{width,height:1000}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path.startsWith('/control/')||path.startsWith('/api/')){
    if(route.request().method()!=='GET'){writes.push(route.request().url());return route.abort();}
    if(path.startsWith('/control/'))return route.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:{}});
    return route.fulfill({status:503,json:{error:'Read-only empty workspace fixture'}});
   }
   const file=path.startsWith('/assets/')?resolve(webRoot,'dist/assets',basename(path)):resolve(webRoot,'dist/index.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://fixture.local/');await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  const nav=page.getByRole('complementary',{name:'View navigation'});
  assert.deepEqual(await nav.locator('nav button').allTextContents(),['Experiments','Results','Conclusions','Usage']);
  for(const name of ['Results','Conclusions']){
   await expect(nav.getByRole('button',{name,exact:true})).toHaveCount(1);
   await expect(page.locator('.floor-observatory').getByRole('button',{name:new RegExp(name)})).toHaveCount(0);
  }
  // Both destinations must remain reachable by keyboard, including after leaving Experiments.
  for(const name of ['Results','Conclusions','Results','Experiments']){
   const button=nav.getByRole('button',{name,exact:true});
   await button.focus();await page.keyboard.press('Enter');
   await expect(button).toHaveAttribute('aria-current','page');
   await expect(page.locator('#workspace-pipeline > .window-titlebar')).toContainText(name);
   await expect(page.locator('#workspace-results, #workspace-report, .workspace-minimized-window')).toHaveCount(0);
   await expect(page.locator('.is-evidence-fullscreen')).toHaveCount(0);
   if(name==='Results')await expect(page.locator('#results-panel')).toBeVisible();
   else await expect(page.locator('#results-panel')).toHaveCount(0);
   if(name==='Experiments')await expect(page.locator('.floor-observatory')).toBeVisible();
   else await expect(page.locator('.floor-observatory')).toHaveCount(0);
   await button.scrollIntoViewIfNeeded();await expect(button).toBeInViewport();
   const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
   assert(geometry.scroll<=geometry.width+1,JSON.stringify({width,theme,name,geometry}));
  }
  await page.getByRole('button',{name:'Workspace settings',exact:true}).click();
  const settings=page.getByRole('dialog',{name:'Workspace settings',exact:true});
  await expect(settings.getByRole('button',{name:/^(Results|Conclusions)$/})).toHaveCount(0);
  await page.keyboard.press('Escape');
  if(process.env.MEMSTARA_SCREENSHOT_DIR)await page.screenshot({path:`${process.env.MEMSTARA_SCREENSHOT_DIR}/control-analysis-${theme}-${width}.png`});
  console.log(JSON.stringify({width,theme,analysisViews:'Control only',keyboardNavigation:true,noDuplicatePanels:true}));
  await page.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
}finally{await browser.close();}
