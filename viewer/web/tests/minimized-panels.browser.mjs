import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const webRoot=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{
 for(const width of [1440,390])for(const theme of ['light','dark']){
 const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async r=>{const path=new URL(r.request().url()).pathname;
 if(path.startsWith('/control/'))return r.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:{}});
 if(path.startsWith('/api/'))return r.fulfill({status:503,json:{error:'Read-only UI fixture'}});
 const file=path.startsWith('/assets/')?resolve(webRoot,'dist/assets',basename(path)):resolve(webRoot,'dist/index.html');
 return r.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://fixture.local/');await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
 for(const name of ['Activity feed','Results','Final report']){
 await page.getByRole('tab',{name,exact:true}).click();await page.getByRole('button',{name:`Collapse ${name==='Final report'?'Final Report':name}`,exact:true}).click();
 const restore=page.getByRole('button',{name:`Expand ${name==='Final report'?'Final Report':name}`,exact:true});await restore.waitFor();
 const bounds=await restore.boundingBox();assert(bounds.y>=0&&bounds.y+bounds.height<=1000&&bounds.x+bounds.width<=width);
 }
 assert.equal(await page.locator('.workspace-minimized-window').count(),3);
 assert.equal(await page.locator('.workspace-evidence-bar').count(),0);
 const restore=page.getByRole('button',{name:'Expand Results',exact:true});await restore.focus();await page.keyboard.press('Enter');
 await page.locator('#workspace-results .window-content').waitFor();assert.equal(await page.getByRole('button',{name:'Expand Results',exact:true}).count(),0);
 assert(await page.getByRole('button',{name:'Expand Activity feed',exact:true}).isVisible());
 await page.getByRole('button',{name:'Collapse Results',exact:true}).click();
 await page.locator('#workspace-pipeline').getByRole('button',{name:/Maximize .* window/}).click();
 assert(await page.getByRole('button',{name:'Expand Activity feed',exact:true}).isVisible());
 await page.getByRole('button',{name:'Expand Activity feed',exact:true}).click();await page.locator('#workspace-feed .window-content').waitFor();
 assert.deepEqual(errors,[]);console.log(JSON.stringify({width,theme,visibleHeaders:true,keyboardRestore:true,maximizedRestore:true}));await page.close();
 }
}finally{await browser.close();}
