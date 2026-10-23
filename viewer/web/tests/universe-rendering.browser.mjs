import {openRetainedView,retainedWorkspaceUrl} from './retained-views.mjs';
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.universePaints=0;
   const clear=CanvasRenderingContext2D.prototype.clearRect;
   CanvasRenderingContext2D.prototype.clearRect=function(...args){if(this.canvas.classList.contains('space-overlay-canvas'))window.universePaints++;return clear.apply(this,args);};
  });
  const questions=Array.from({length:120},(_,i)=>({question_id:i+1,text:`Synthetic question ${i+1}`,okf_tags:['Fixture'],rationale:'Fixture',origin_run:'fixture',origin_wave:0,writer:'fixture',times_used:1,status:'done'}));
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/api/discovery/questions'){const query=new URL(route.request().url()).searchParams.get('query')||'';const matched=questions.filter(q=>q.text.toLowerCase().includes(query.toLowerCase()));return route.fulfill({json:{questions:matched,total:matched.length,next_before:null}});}
   if(/^\/api\/discovery\/questions\/\d+$/.test(path))return route.fulfill({json:{question:questions.find(q=>q.question_id===Number(path.split('/').at(-1))),tasks:[],results:[],record_limit:100}});
   if(path.startsWith('/control/'))return route.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:{}});
   if(path.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Unrelated fixture endpoint unavailable'}});
   if(new URL(route.request().url()).port==='4177')return route.continue();
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto(retainedWorkspaceUrl);
  await openRetainedView(page);
  const field=page.locator('.space-surface');
  await field.scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelectorAll('.space-label').length===120&&window.universePaints>0);
  const paints=()=>page.evaluate(()=>window.universePaints);
  const idle=async(label,ms=1200)=>{
   // Camera easing takes frames, not fixed wall time, on a busy software renderer.
   const deadline=Date.now()+15000;
   let before=await paints(),settled=false;
   while(Date.now()<deadline){await page.waitForTimeout(600);const after=await paints();if(after===before){settled=true;break;}before=after;}
   assert.ok(settled,`${label}: renderer did not settle within 15 seconds`);
   await page.waitForTimeout(ms);assert.equal(await paints(),before,label);
  };
  await idle('Idle universe must stop painting even across identical polling responses',5300);
  await page.mouse.move(0,0);await field.scrollIntoViewIfNeeded();
  // Keep the pointer off labels: hovering a label intentionally pauses rotation.
  await page.getByRole('button',{name:'Toggle gentle rotation',exact:true}).evaluate(el=>el.click());
  const spinning=await paints();await page.waitForFunction(before=>window.universePaints>before,spinning);
  await page.getByRole('button',{name:'Toggle gentle rotation',exact:true}).evaluate(el=>el.click());
  await idle('Paused rotation must settle');
  const beforeZoom=await paints();
  await page.getByRole('button',{name:'Zoom in',exact:true}).click();await page.waitForTimeout(500);assert.ok(await paints()>beforeZoom,'Zoom must wake the renderer');
  await idle('Zoom must settle');
  const beforeTheme=await paints();await page.evaluate(()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='light'?'dark':'light';});
  await page.waitForTimeout(150);assert.ok(await paints()>beforeTheme,'Theme must repaint an idle scene');
  const beforeResize=await paints();await page.setViewportSize({width:width-20,height:1000});await page.waitForTimeout(300);assert.ok(await paints()>beforeResize,'Resize must repaint an idle scene');
  await page.getByRole('button',{name:'View options',exact:true}).click();
  await page.getByRole('button',{name:'List',exact:true}).click();
  await page.keyboard.press('Escape');
  await page.locator('.universe-list button').first().click();
  await page.getByRole('button',{name:'Close Universe panel',exact:true}).click();
  await page.getByRole('button',{name:'View options',exact:true}).click();
  await page.getByRole('button',{name:'Map',exact:true}).click();
  await page.keyboard.press('Escape');
  await field.scrollIntoViewIfNeeded();await idle('Selected evidence must settle');
  await page.getByRole('button',{name:'Back to question field',exact:true}).click();
  await idle('Returning from evidence must settle');
  const lost=await page.evaluate(()=>{const canvas=document.querySelector('.space-gpu');const gl=canvas.getContext('webgl');const ext=gl?.getExtension('WEBGL_lose_context');if(!ext)return false;window.restoreUniverse=()=>ext.restoreContext();ext.loseContext();return true;});
  if(lost){await page.waitForTimeout(300);await idle('Canvas fallback must settle');await page.evaluate(()=>window.restoreUniverse());await page.waitForTimeout(300);await idle('Restored WebGL must settle');}
  await page.getByRole('textbox',{name:'Search questions'}).fill('no match');
  await page.locator('.space-empty').waitFor();
  assert.match(await page.locator('.space-empty').innerText(),/^No questions match this search in this source\./);
  assert.equal(await page.locator('.space-label').count(),0);
  assert.equal(await page.getByText(/could not be displayed/).count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({width,questions:120,idlePaints:0,rotation:'pass',zoom:'pass',theme:'pass',resize:'pass',selection:'pass',contextRecovery:lost?'pass':'unavailable',errors}));
  await page.close();
 }
}finally{await browser.close();}
