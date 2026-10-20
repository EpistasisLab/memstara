import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let saved=0,starts=0;
 let settings={read_only:false,models:[{id:'model-id',model:'Fixture model',provider:'openai',roles:['non_explanation_agents','explanation_agent'],enabled:false,rates:{},source:'',valid_until:''}]};
 const item={id:'p',number:1,name:'Pricing fixture',configuration:{waves:1,trials:1,y_column:'Y'},running:null,latest:null,progress:{}};
 await page.route('**/control/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/control/pricing'){
   if(r.request().method()==='POST'){settings={...settings,...r.request().postDataJSON()};saved++;}
   return r.fulfill({json:settings});
  }
  if(r.request().method()!=='GET'){starts++;throw Error('Unexpected execution or mutation');}
  if(path==='/control/pipelines')return r.fulfill({json:{pipelines:[item]}});
  if(path==='/control/health')return r.fulfill({json:{ok:true,llm:{provider:'openai',model:'Fixture model'}}});
  if(path==='/control/playbooks')return r.fulfill({json:{catalog:[],playbooks:[],stages:[],references:[]}});
  return r.fulfill({json:{inputs:[],skills:[],runs:[]}});
 });
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Isolated fixture'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.getByRole('button',{name:'View floor plan',exact:true}).click();
 await page.getByRole('button',{name:'Settings and more for Pricing fixture',exact:true}).first().click();
 const dialog=page.getByRole('dialog',{name:'Pipeline settings and actions'});
 await dialog.getByText('Cost estimate settings · optional',{exact:true}).click();
 await dialog.getByLabel('Use manually verified rates').check();
 await dialog.getByLabel('Input · USD per 1 million tokens',{exact:true}).fill('2');
 await dialog.getByLabel('Output · USD per 1 million tokens',{exact:true}).fill('8');
 await dialog.getByLabel('Cache read (optional) · USD per 1 million tokens',{exact:true}).fill('1');
 await dialog.getByLabel('Verified rate source (HTTPS URL)').fill('https://example.test/pricing');
 await dialog.getByLabel('Expires at start of this date (UTC)').fill('2099-01-01');
 for(const width of [390,1440]){await page.setViewportSize({width,height:1000});assert.equal(await dialog.evaluate(el=>el.scrollWidth>el.clientWidth+2),false);}
 await dialog.getByRole('button',{name:'Save manual rates',exact:true}).click();
 await dialog.getByText(/Manual rates saved for subsequent requests/).waitFor();
 assert.equal(saved,1);assert.deepEqual(settings.models[0].rates,{input:2,output:8,cache_read:1});
 assert.equal(starts,0);assert.deepEqual(errors,[]);
 console.log('Manual rates edited without JSON; USD units and provenance; mobile layout; no model calls. HTTP mocked.');
}finally{await browser.close();}
