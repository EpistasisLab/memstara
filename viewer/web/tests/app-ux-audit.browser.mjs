// Read-only UI audit. Every mutation is blocked; no pipeline is started or changed.
import {chromium} from '@playwright/test';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const directory=process.env.UX_AUDIT_DIR||'/tmp/memstara-ux-baseline';mkdirSync(directory,{recursive:true});
const results=[],errors=[];const tabs=[];
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(15000);
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/control/**',async r=>{if(r.request().method()!=='GET')throw Error('Unexpected mutation '+r.request().url());const u=new URL(r.request().url());try{const response=await r.fetch({url:'http://127.0.0.1:8070'+u.pathname+u.search,timeout:15000});await r.fulfill({response});}catch{await r.fulfill({status:503,json:{error:'Read unavailable'}});}});
 await page.route('**/api/**',async r=>{const u=new URL(r.request().url());try{const response=await r.fetch({url:'http://127.0.0.1:8070'+u.pathname+u.search,timeout:15000});await r.fulfill({response});}catch{await r.fulfill({status:503,json:{error:'Read unavailable'}});}});
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:8070');
 await page.locator('[aria-label="View navigation"] button').first().waitFor();
 await page.addScriptTag({path:'/tmp/memstara-ux-audit/node_modules/axe-core/axe.min.js'});
 for(const theme of (process.env.UX_FULL?['light','dark']:['light']))for(const width of [1440,320]){
  await page.setViewportSize({width,height:1000});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  for(const view of ['Experiments','Results','Conclusions','Usage']){
   await page.locator('[aria-label="View navigation"]').getByRole('button',{name:view,exact:true}).click();
   await page.waitForTimeout(600);
   const geometry=await page.evaluate(()=>({width:innerWidth,pageWidth:document.documentElement.scrollWidth,
    hiddenInputs:[...document.querySelectorAll('input,select,textarea,button')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&!e.closest('[aria-hidden=true],[inert]')&&r.right>innerWidth+3&&!e.closest('table,.react-flow,.floor-canvas,[role=tooltip]');}).slice(0,12).map(e=>({tag:e.tagName,label:e.getAttribute('aria-label')||e.textContent?.slice(0,40),class:e.className}))}));
   const violations=await page.evaluate(async()=>{const r=await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,count:v.nodes.length,targets:v.nodes.slice(0,8).map(n=>n.target)}));});
   results.push({theme,width,view,geometry,violations});writeFileSync(directory+'/audit.json',JSON.stringify({results,tabs,errors},null,2));console.log(JSON.stringify({theme,width,view,overflow:geometry.pageWidth>width+2,rules:violations.map(v=>v.id+':'+v.count)}));
   if(view==='Telemetry') {
    await page.waitForTimeout(7000);
    for(const tab of ['Totals','Agents','Activity','Logs','Access','Tasks','Results']){
     await page.locator('[aria-label="Usage tabs"]').getByRole('button',{name:tab,exact:true}).click();
     await page.waitForTimeout(250);
     const state=await page.locator('.telemetry-tab-body').evaluate(e=>({height:e.clientHeight,contentWidth:e.clientWidth,scrollWidth:e.scrollWidth,loading:/^Loading|^Waiting to retry|^Preparing/.test(e.textContent.trim()),fallback:!!e.closest('.view-recovery')}));
     tabs.push({theme,width,tab,...state});
    }
    await page.locator('[aria-label="Usage tabs"]').getByRole('button',{name:'Agents',exact:true}).click();
   }
   if(view==='Telemetry'||(width===320&&view==='Experiments'))await page.screenshot({path:directory+'/'+theme+'-'+width+'-'+view.replaceAll(' ','-')+'.png'});
  }
 }
 writeFileSync(directory+'/audit.json',JSON.stringify({results,tabs,errors},null,2));
 await page.unrouteAll({behavior:'ignoreErrors'});
 if(errors.length || results.some(r=>r.violations.length || r.geometry.pageWidth>r.width+2))throw Error('UI audit found issues; inspect audit.json');
}finally{await browser.close();}
