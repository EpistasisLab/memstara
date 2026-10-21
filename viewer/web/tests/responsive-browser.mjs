import {chromium,firefox,webkit} from '@playwright/test';
import {mkdtemp,writeFile,rm,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

// Chromium tab zoom is browser zoom, not CSS zoom, pinch scale or viewport resizing.
export async function launchResponsiveBrowser(){
 const engine=process.env.MEMSTARA_BROWSER||'chromium';
 const zoom=Number(process.env.MEMSTARA_BROWSER_ZOOM||1);
 if(zoom===1)return {chromium,firefox,webkit}[engine].launch({headless:true});
 if(engine!=='chromium')throw Error('Native zoom harness currently supports Chromium only');
 const dir=await mkdtemp(join(tmpdir(),'memstara-responsive-'));
 const extension=join(dir,'extension');await mkdir(extension);
 await writeFile(join(extension,'manifest.json'),JSON.stringify({manifest_version:3,name:'Responsive zoom test',version:'1.0',permissions:['tabs'],background:{service_worker:'worker.js'}}));
 await writeFile(join(extension,'worker.js'),'chrome.runtime.onInstalled.addListener(()=>{});');
 const context=await chromium.launchPersistentContext(join(dir,'profile'),{headless:true,channel:'chromium',args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
 const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker');
 return {
  async newPage(options={}){
   const page=await context.newPage();if(options.viewport)await page.setViewportSize(options.viewport);
   const goto=page.goto.bind(page);
   page.goto=async(...args)=>{
    const result=await goto(...args);
    const url=page.url();
    await worker.evaluate(async({url,zoom})=>{
     const tabs=await chrome.tabs.query({});const tab=tabs.find(t=>t.url===url);
     if(!tab)throw Error('Fixture tab not found');
     await chrome.tabs.setZoomSettings(tab.id,{mode:'automatic',scope:'per-tab'});
     await chrome.tabs.setZoom(tab.id,zoom);
     const actual=await chrome.tabs.getZoom(tab.id);if(Math.abs(actual-zoom)>.01)throw Error(`Zoom mismatch: ${actual}`);
    },{url,zoom});
    await page.waitForFunction(z=>Math.abs(devicePixelRatio-z)<.02,zoom);
    return result;
   };
   return page;
  },async close(){await context.close();await rm(dir,{recursive:true,force:true});}
 };
}
