import {chromium,webkit,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
const name=process.env.MEMSTARA_BROWSER||'chromium';
const engine={chromium,webkit}[name];
if(!engine)throw Error('Touch emulation is supported by this harness in Chromium and WebKit');
{
 const browser=await engine.launch();try{
 const context=await browser.newContext({viewport:{width:390,height:700},hasTouch:true,isMobile:true});const page=await context.newPage();
 await page.route('**/control/**',r=>r.fulfill({json:{inputs:[],models:[],skills:[]}}));
 await page.goto(root+'/tests/responsive-scroll.fixture.html');
 await page.getByRole('button',{name:/Agent skills/}).tap();await page.locator('.comb-skill-card input').first().waitFor({state:'visible'});
 await page.locator('.comb-skill-card input').first().tap();await expect(page.locator('.comb-skill-card input').first()).toBeChecked();
 await page.locator('.comb-skill-card details > summary').first().tap();
 const scroll=page.locator('.comb-step-content');
 if(name==='chromium'){
  const cdp=await context.newCDPSession(page);await scroll.evaluate(e=>e.scrollTop=0);const r=await scroll.boundingBox();
  const x=r.x+r.width*.8,y=r.y+r.height*.8,before=await scroll.evaluate(e=>e.scrollTop);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
  for(let i=1;i<=8;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-i*20}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await expect.poll(()=>scroll.evaluate(e=>e.scrollTop)).toBeGreaterThan(before);
 }
 await page.setViewportSize({width:700,height:390});
 await expect(page.locator('.comb-skill-card input').first()).toBeChecked();
 assert(await page.getByRole('dialog').evaluate(d=>d.scrollWidth<=d.clientWidth+2));
 console.log(JSON.stringify({engine:name,touchSelection:true,orientationState:true,swipe:name==='chromium'?'passed':'not supported by harness'}));
 await context.close();
 }finally{await browser.close();}
}
