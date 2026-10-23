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
 await page.getByRole('button',{name:'Experiments',exact:true}).click();
 assert.equal(await page.getByRole('button',{name:'Settings and more for Pricing fixture',exact:true}).count(),0);
 assert.equal(await page.getByRole('button',{name:'Save manual rates',exact:true}).count(),0);
 assert.equal(saved,0);
 assert.equal(starts,0);assert.deepEqual(errors,[]);
 console.log('Minimal pipeline settings, no local rate editor, responsive layout, no writes or model calls. HTTP mocked.');
}finally{await browser.close();}
