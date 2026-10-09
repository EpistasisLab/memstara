import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8070');
 await page.getByRole('button',{name:/Telemetry/}).first().click();
 await page.getByRole('button',{name:'Experiments',exact:true}).click();
 const region=page.getByRole('region',{name:'Experiment registry'});
 await region.getByRole('combobox').selectOption('standalone:board_20261007T164851_129217');
 await region.getByText('$1.41192',{exact:true}).waitFor();
 await region.getByRole('button',{name:'Inspect',exact:true}).click();
 try{await region.getByRole('button',{name:'Download complete evidence JSON'}).waitFor();}catch(e){console.log('REGION', (await region.innerText()).slice(0,1500), 'ERRORS',errors);throw e;}
 const event=page.waitForEvent('download');await region.getByRole('button',{name:'Download complete evidence JSON'}).click();
 assert.match((await event).suggestedFilename(),/evidence.json$/);
 for(const width of [1280,390]){await page.setViewportSize({width,height:900});assert.equal(await region.evaluate(e=>e.scrollWidth>e.clientWidth+2),false);}
 assert.deepEqual(errors,[]);console.log('Registry UI: database listing, costs, evidence, download, responsive panel passed.');
}finally{await browser.close();}
