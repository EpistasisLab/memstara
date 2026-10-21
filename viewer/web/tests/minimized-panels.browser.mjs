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
 await page.getByRole('navigation').getByRole('button',{name:'Floor plan',exact:true}).first().click();
 for(const name of ['Results','Final report']){
 const launch=page.getByRole('button',{name:`Open ${name} full screen`,exact:true});
 await launch.focus();await page.keyboard.press('Enter');
 const dock=page.locator(name==='Results'?'#workspace-results':'#workspace-report');
 await dock.waitFor();await dock.getByRole('button',{name:/^Collapse /}).click();
 await dock.waitFor({state:'hidden'});
 assert.equal(await page.locator('.workspace-minimized-window').count(),0);
 const bounds=await launch.boundingBox();assert(bounds.y>=0&&bounds.y+bounds.height<=1000&&bounds.x+bounds.width<=width);
 }
 await page.locator('#workspace-pipeline').getByRole('button',{name:/Maximize .* window/}).click();
 await page.getByRole('button',{name:'Open Final report full screen',exact:true}).click();
 await page.locator('#workspace-report .window-content').waitFor();
 assert.deepEqual(errors,[]);console.log(JSON.stringify({width,theme,visibleHeaders:true,keyboardRestore:true,maximizedRestore:true}));await page.close();
 }
}finally{await browser.close();}
