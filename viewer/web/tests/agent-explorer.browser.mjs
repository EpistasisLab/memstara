import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try{for(const width of [1440,900,390]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],api=[];
 page.setDefaultTimeout(10000);page.setDefaultNavigationTimeout(15000);
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.startsWith('/api/')||path.startsWith('/control/')){api.push(path);return route.abort();}
  const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/developer.html');
  return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://localhost/developer.html?view=agents');
 await page.getByRole('button',{name:'Open optional technical explorer',exact:true}).click();
 await page.getByRole('heading',{name:'From knowledge to evidence.'}).waitFor();
 console.log('Technical explorer loaded',width);
 const slider=page.getByRole('slider',{name:'Walkthrough position'});
 assert.equal(await slider.getAttribute('max'),'46');
 assert.equal(await page.locator('.agent-map .react-flow__node').count(),width===390?2:20);
 await page.getByRole('combobox',{name:'Walkthrough speed'}).selectOption('2');
 await page.getByRole('button',{name:'Play walkthrough',exact:true}).click();
 await page.locator('animateMotion').waitFor({state:'attached'});
 await page.waitForFunction(()=>Number(document.querySelector('[aria-label="Walkthrough position"]').value)>0);
 await page.getByRole('button',{name:'Pause walkthrough',exact:true}).click();
 assert.equal(await page.locator('animateMotion').count(),0);
 const paused=await slider.inputValue();await page.waitForTimeout(3000);assert.equal(await slider.inputValue(),paused);
 await page.getByRole('button',{name:'Next transfer',exact:true}).click();assert.equal(Number(await slider.inputValue()),Number(paused)+1);
 await page.getByRole('button',{name:'Previous transfer',exact:true}).click();assert.equal(await slider.inputValue(),paused);
 await page.getByRole('button',{name:'Restart walkthrough',exact:true}).click();assert.equal(await slider.inputValue(),'0');
 const component=page.getByRole('combobox',{name:'Inspect component'});
 for(const actor of ['hypothesis','data','ml','interpreter','report','knowledge','memdb','coredb','dataset']){
  await component.selectOption(actor);assert.equal(await component.inputValue(),actor);
 }
 await page.getByRole('button',{name:'Interpretation',exact:true}).click();
 await page.getByRole('complementary',{name:'Component details'}).getByText('Allowed tools',{exact:true}).click();
 await page.getByRole('complementary',{name:'Component details'}).getByText('claim_task',{exact:true}).waitFor();
 const scene=page.getByRole('combobox',{name:'Tour scenario'});
 for(const value of ['1','2','3']){
  await scene.selectOption(value);assert.equal(await slider.inputValue(),'0');
  await slider.focus();await slider.press('End');assert.equal(await slider.inputValue(),await slider.getAttribute('max'));
  assert.equal(await page.getByRole('button',{name:'Next transfer',exact:true}).isDisabled(),true);
 }
 await scene.selectOption('0');
 if(width>700){await page.getByRole('button',{name:'Focus transfer',exact:true}).click();assert.equal(await page.locator('.agent-map .react-flow__node').count(),2);await page.getByRole('button',{name:'Show full system',exact:true}).click();}
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.getByRole('button',{name:'Play walkthrough',exact:true}).click();assert.equal(await page.locator('animateMotion').count(),0);
 await page.getByRole('button',{name:'Pause walkthrough',exact:true}).click();
 await page.emulateMedia({reducedMotion:'no-preference'});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'No page overflow');

 await page.getByRole('button',{name:'Inspect recorded execution',exact:true}).click();
 await page.getByRole('button',{name:'Load executions',exact:true}).waitFor();
 assert.deepEqual(api,[],'Educational walkthrough must never fetch evidence or issue commands');
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({width,transfers:47,playPause:'pass',scenarios:4,reducedMotion:'pass',apiCalls:0,errors}));await page.close();
}}finally{await browser.close();}
