import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,headless:true});
try {
 const page=await browser.newPage(); page.setDefaultTimeout(15000); const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Unavailable during layout test'}}));
 await page.route('**/control/**',r=>r.fulfill({status:503,json:{error:'Unavailable during layout test'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.locator('.unified-topbar').waitFor();
 for(const theme of ['light','dark']) for(const width of [1440,1024,768,390,320]) {
  await page.setViewportSize({width,height:900});
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  const size=await page.locator('.unified-topbar').evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth,height:el.getBoundingClientRect().height}));
  assert(size.scroll<=size.width+2,JSON.stringify({theme,width,size}));assert(size.height<85);
  await page.getByRole('button',{name:'Workspace settings',exact:true}).click();
  const settings=page.getByRole('dialog',{name:'Workspace settings',exact:true});
  await settings.getByRole('button',{name:/System status|Status · attention/}).click();
  await page.getByRole('dialog',{name:'System status',exact:true}).waitFor();
  await page.keyboard.press('Escape');
  assert(await settings.isVisible());
  await settings.getByRole('button',{name:'Reset window layout',exact:true}).click();
  await page.keyboard.press('Escape');assert(await page.getByRole('button',{name:'Workspace settings',exact:true}).evaluate(e=>e===document.activeElement));
  await page.getByRole('button',{name:'Exploration overview',exact:true}).click();
  const overview=page.getByRole('dialog',{name:'Exploration overview',exact:true});
  const fits=await overview.evaluate(e=>e.scrollWidth<=e.clientWidth+2&&e.getBoundingClientRect().bottom<=innerHeight);
  assert(fits);await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Saved analyses',exact:true}).click();
  await page.getByRole('dialog',{name:'Saved analyses',exact:true}).waitFor();await page.keyboard.press('Escape');
  console.log(JSON.stringify({theme,width,...size,dialogs:'passed'}));
  if(width===1440||width===390)await page.screenshot({path:`/tmp/topbar-${theme}-${width}.png`});
 }
 assert.deepEqual(errors,[]);
}finally{await browser.close();}
