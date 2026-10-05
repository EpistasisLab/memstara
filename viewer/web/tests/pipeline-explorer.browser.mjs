import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try {for(const width of [1440,390]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],requests=[];
 let fail=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname;
  if(path.startsWith('/api/')){
   requests.push({path,method:request.method(),query:url.search});
   if(path==='/api/runs')return route.fulfill({json:{runs:[{run_tag:'run-A'},{run_tag:'run-B'}]}});
   const tag=url.searchParams.get('run_tag');
   if(path==='/api/developer/execution'){
    if(fail)return route.fulfill({status:503,json:{detail:'Unavailable'}});
    return route.fulfill({json:{run_tag:tag,pipeline:{status:'paused'},note:'Recorded invocations.',calls:[{seq:1,run_id:tag==='run-A'?'11111111-1111-1111-1111-111111111111':'22222222-2222-2222-2222-222222222222',stage:'ml#1',loop:1,loop_source:'recorded',status:'completed',prompt:'Selected columns',started_at:1790800000}]}});
   }
   if(path==='/api/developer/steps')return route.fulfill({json:{steps:url.searchParams.get('detail')==='true'?[{id:'step-1',input_data:{columns:['x']},tool_call:{calls:[{tool:'train_and_score',arguments:{x:'subset'},result:{auc:.75}}]},output_data:{message:'Saved'}}]:[{id:'step-1',started_at:'2026-10-01T12:00:00Z'}],next_offset:null}});
   throw new Error('Unexpected API '+path);
  }
  const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/developer.html');
  return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://localhost/developer.html');
 await page.getByRole('button',{name:'Pipeline internals',exact:true}).click();
 await page.locator('.pipeline-canvas .react-flow__node').first().waitFor();
 assert.equal(await page.locator('.pipeline-canvas .react-flow__node').count(),16);
 assert.equal(requests.length,0,'Blueprint must not read private execution data');
 const picker=page.getByRole('combobox',{name:'Pipeline phase'});
 const values=await picker.locator('option').evaluateAll(options=>options.map(o=>o.value));
 for(const value of values){await picker.selectOption(value);assert.ok(await page.locator('.phase-detail .connection').count()>0);}
 await picker.selectOption('ml');await page.locator('.phase-detail .connection').filter({hasText:'mcp_servers/ml.py'}).click();
 await page.getByRole('complementary',{name:'File inspector'}).getByRole('heading',{name:'ml.py',exact:true}).waitFor();
 await page.getByRole('button',{name:'Inspect an execution',exact:true}).click();
 assert.equal(requests.length,0);
 await page.getByRole('button',{name:'Load executions',exact:true}).click();
 await page.getByRole('combobox',{name:'Execution archive'}).selectOption('run-A');
 await page.locator('.invocation-list button').click();
 await page.getByRole('button',{name:/Step 1/}).click();
 await page.locator('.step-payload').getByText('tool_call',{exact:true}).click();
 await page.locator('.step-payload .record-flow b').filter({hasText:'train_and_score'}).waitFor();
 assert.match(await page.locator('.step-payload').innerText(),/0.75/);
 fail=true;await page.getByRole('button',{name:'Refresh execution',exact:true}).click();
 await page.getByRole('alert').getByText(/may be stale/).waitFor();
 assert.equal(await page.locator('.invocation-list button').count(),1);
 fail=false;await page.getByRole('combobox',{name:'Execution archive'}).selectOption('run-B');
 await page.locator('.invocation-list code').filter({hasText:'22222222'}).waitFor();
 assert.equal(await page.locator('.step-payload').count(),0,'Scope change must clear old payload');
 await Promise.all([page.waitForResponse(r=>r.url().includes('loop=2')),page.getByRole('spinbutton',{name:'Execution loop'}).fill('2')]);
 assert.ok(requests.every(r=>r.method==='GET'));
 assert.deepEqual(errors,[]);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 await page.getByRole('button',{name:'Execution blueprint',exact:true}).click();
 await page.screenshot({path:`/private/tmp/memstara-pipeline-explorer-${width}.png`,fullPage:true});
 console.log(JSON.stringify({width,phases:16,scopeIsolation:'pass',payload:'pass',staleError:'pass',errors}));await page.close();
}}finally{await browser.close();}
