import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
const browser=await launchResponsiveBrowser();
const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
const messages=Array.from({length:80},(_,i)=>({id:String(i),run_id:'fixture',stage:'ml',name:'Model '+i,label:'Long label '+ 'Identifier'.repeat(30),kind:'answer',kind_label:'Answer',at:'2026-10-21T12:00:00Z',loop:i+1,text:`# Output ${i}\n\n`+'Recorded explanation '.repeat(400),truncated:false}));
try{for(const [width,height] of [[390,500],[768,700],[1440,900]]){
 const page=await browser.newPage({viewport:{width,height}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',r=>r.fulfill({json:{run_tag:'history-fixture',loop:null,messages,limited:false}}));
 await page.goto(root+'/tests/responsive-history.fixture.html');
 const list=page.getByRole('navigation',{name:'Recorded agent outputs'});
 await expect(list.getByRole('button')).toHaveCount(80);
 const last=list.getByRole('button').last();await last.focus();await page.keyboard.press('Enter');
 await expect(page.locator('.agent-reader-body h1')).toHaveText('Output 0');
 await page.getByRole('button',{name:'Go to latest output'}).click();
 await expect(page.locator('.agent-reader-body h1')).toHaveText('Output 79');
 await page.getByRole('textbox',{name:'Search agent outputs'}).fill('unmatched fixture');
 await page.getByRole('button',{name:'Clear filters'}).click();await expect(list.getByRole('button')).toHaveCount(80);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'history horizontal overflow');
 // A reader can navigate the bounded list and continue reading the document with the keyboard.
 await list.getByRole('button').first().focus();await expect(list.getByRole('button').first()).toBeInViewport();
 await page.goto(root+'/tests/responsive-history.fixture.html?log=1');
 const log=page.locator('main .overflow-auto');
 await expect.poll(()=>log.evaluate(e=>e.scrollHeight-e.scrollTop-e.clientHeight)).toBeLessThan(25);
 await log.hover();await page.mouse.wheel(0,-800);await expect(page.getByRole('button',{name:'Follow the end ↓'})).toBeVisible();
 await log.focus();const keyboardBefore=await log.evaluate(e=>e.scrollTop);
 await page.keyboard.press('PageUp');
 await expect.poll(()=>log.evaluate(e=>e.scrollTop)).toBeLessThan(keyboardBefore);
 // Wait for the native PageUp animation before testing append/resize.
 await log.evaluate(el=>new Promise(resolve=>{
   let previous=el.scrollTop,stable=0;
   const frame=()=>{const next=el.scrollTop;stable=next===previous?stable+1:0;previous=next;
     if(stable>=10)resolve();else requestAnimationFrame(frame);};frame();
 }));
 // Stabilize at the start before checking new records and resize behavior.
 await log.evaluate(e=>e.scrollTop=0);
 await expect.poll(()=>log.evaluate(e=>e.scrollTop)).toBe(0);
 await page.setViewportSize({width:width===390?768:390,height:500});
 await expect(page.getByRole('button',{name:'Follow the end ↓'})).toBeVisible();
 await expect.poll(()=>log.evaluate(e=>e.scrollTop)).toBe(0);
 const before=await log.evaluate(e=>e.scrollTop);await page.getByRole('button',{name:'Append record'}).click();
 await expect.poll(()=>log.evaluate(e=>e.scrollTop)).toBe(before);
 await page.getByRole('button',{name:'Follow the end ↓'}).click();
 await expect.poll(()=>log.evaluate(e=>e.scrollHeight-e.scrollTop-e.clientHeight)).toBeLessThan(25);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'log overflow');
 assert.deepEqual(errors,[]);console.log(JSON.stringify({width,height,historyNavigation:true,filters:true,logFollow:true}));await page.close();
}}finally{await browser.close();}
