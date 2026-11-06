import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {stat} from 'node:fs/promises';
const results=['before','after'].map((tag,i)=>({run_tag:tag,result_uid:`r${i}`,result_id:i+1,trial:i,
 model:'logistic_regression',auc:.7,interpretation_output_ids:i?[]:['i1','i2'],explanation_output_ids:i?[]:['e1'],
 interpretation_status:i?'not_recorded':'complete',explanation_status:i?'not_recorded':'complete',
 evaluation:{skills:{hypothesis:['hiv-no-knowledge']},evaluation:{replicates:[{seed:42,auc:.7}]}}}));
const bundle={schema_version:'linked_agent_outputs_v1',generated_at:'2026-11-05T05:00:00Z',
 requested_run_tags:['continued-experiment'],run_tags:['before','after'],results,
 interpretations:[{output_id:'i1',run_tag:'before',text:'\n# Original 한글\n',result_uids:['r0']},
 {output_id:'i2',run_tag:'before',text:'Second interpretation\n',result_uids:['r0']}],
 explanations:[{output_id:'e1',run_tag:'before',text:'Exact explanation\n',result_uids:['r0']}],
 executions:results.map(r=>({run_tag:r.run_tag,results:[r]})),warnings:[]};
const browser=await chromium.launch({headless:true,...(process.env.MEMSTARA_BROWSER_EXECUTABLE?{executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE}:{})});
try{
 const page=await browser.newPage({acceptDownloads:true,viewport:{width:768,height:900}});
 const errors=[],requests=[];let failed=false,held=false,release=null,responseBundle=bundle;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/experiments/linked-export?*',async route=>{
  requests.push(new URL(route.request().url()));
  if(held)await new Promise(resolve=>{release=resolve;});
  return route.fulfill({status:failed?503:200,json:failed?{detail:'Archive temporarily unavailable'}:responseBundle}).catch(()=>{});
 });
 await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/hypothesis-metrics.fixture.html`);
 await page.evaluate(rows=>window.deliverMetricResults(rows),results);
 await page.getByRole('button',{name:/Compare hypothesis results/}).click();
 for(const label of ['Download table CSV','Download complete evidence CSV','Download linked results ZIP']){
  const event=page.waitForEvent('download');await page.getByRole('button',{name:label,exact:true}).click();
  const download=await event,stream=await download.createReadStream(),chunks=[];for await(const c of stream)chunks.push(c);
  const data=Buffer.concat(chunks);
  if(label.includes('ZIP')){
   const files=JSON.parse(execFileSync('python3',['-c','import sys,io,zipfile,json; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); assert z.testzip() is None; print(json.dumps({n:z.read(n).decode("utf-8") for n in z.namelist()}))'],{input:data,encoding:'utf8'}));
   assert.equal(JSON.parse(files['interpretations.json'])[0].text,'\n# Original 한글\n');
   assert.equal(JSON.parse(files['explanations.json'])[0].result_uids[0],'r0');
   assert(files['results.csv'].includes('[""i1"",""i2""]'));
   assert(files['complete_evidence.csv'].includes('"before"'));assert(files['complete_evidence.csv'].includes('"after"'));
  }else{assert(data.toString().includes('interpretation_output_ids'));assert(!data.toString().includes('Original 한글'));}
  await expect(page.getByRole('status').filter({hasText:'2 saved results from 2 execution(s)'})).toHaveCount(1);
 }
 assert.equal(requests[0].searchParams.get('include_evidence'),'false');
 assert.equal(requests[1].searchParams.get('include_evidence'),'true');
 assert.equal(requests[2].searchParams.get('run_tags'),'continued-experiment');
 failed=true;let downloads=0;page.on('download',()=>downloads++);
 await page.getByRole('button',{name:'Download linked results ZIP',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Archive temporarily unavailable');
 assert.equal(downloads,0);assert.deepEqual(errors,[]);
 failed=false;held=true;
 await page.getByRole('button',{name:'Download linked results ZIP',exact:true}).click();
 await expect(page.getByRole('button',{name:'Cancel export',exact:true})).toBeVisible();
 await expect.poll(()=>release!==null).toBe(true);
 // Other UI remains usable during an outstanding export request.
 await page.getByLabel('Performance metric').selectOption('f1');
 await expect(page.getByLabel('Performance metric')).toHaveValue('f1');
 await page.getByRole('button',{name:'Cancel export',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'Export cancelled.'})).toHaveCount(1);
 held=false;release();await page.waitForTimeout(100);assert.equal(downloads,0);
 // Match the observed production lower bound without using clinical records.
 const padding='x'.repeat(32*1024*1024);
 responseBundle={...bundle,executions:bundle.executions.map(execution=>({...execution,metadata:{padding}}))};
 await page.evaluate(()=>{
  window.exportHeartbeat={ticks:0,maxGap:0,last:performance.now()};
  window.exportHeartbeatTimer=setInterval(()=>{const now=performance.now(),state=window.exportHeartbeat;state.ticks++;state.maxGap=Math.max(state.maxGap,now-state.last);state.last=now;},10);
 });
 const largeEvent=page.waitForEvent('download',{timeout:120000});
 await page.getByRole('button',{name:'Download linked results ZIP',exact:true}).click();
 const large=await largeEvent;
 const heartbeat=await page.evaluate(()=>{clearInterval(window.exportHeartbeatTimer);return window.exportHeartbeat;});
 assert(heartbeat.ticks>10);assert(heartbeat.maxGap<1000,JSON.stringify(heartbeat));
 assert.equal(await large.failure(),null);
 const path=await large.path();assert((await stat(path)).size>128*1024*1024);
 execFileSync('python3',['-c','import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; assert "complete_evidence.json" in z.namelist()',path]);
 assert.deepEqual(errors,[]);
 console.log('PASS: all download buttons, continued execution scope, exact JSON/ZIP relationships and failure without substitute download');
 console.log(`PASS: cancellation and 64+ MiB payload; UI heartbeat max gap ${Math.round(heartbeat.maxGap)} ms; complete evidence and CRC preserved`);
}finally{await browser.close();}
