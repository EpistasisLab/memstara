import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const python=process.env.MEMSTARA_TEST_PYTHON??'python3';
const api=fileURLToPath(new URL('../../api',import.meta.url));
const results=['before','after'].map((tag,i)=>({run_tag:tag,result_uid:`r${i}`,result_id:i+1,trial:i,
 model:'logistic_regression',auc:.7,interpretation_output_ids:i?[]:['i1','i2'],explanation_output_ids:i?[]:['e1'],
 interpretation_status:i?'not_recorded':'complete',explanation_status:i?'not_recorded':'complete',
 evaluation:{skills:{hypothesis:['hiv-no-knowledge']},evaluation:{replicates:[{seed:42,auc:.7}]}}}));
const bundle={schema_version:'linked_agent_outputs_v1',generated_at:'2026-11-05T05:00:00Z',
 requested_run_tags:['continued-experiment'],run_tags:['before','after'],results,
 interpretations:[{output_id:'i1',run_tag:'before',text:'\n# Original 한글\n',result_uids:['r0']},
 {output_id:'i2',run_tag:'before',text:'Second interpretation\n',result_uids:['r0']}],
 explanations:[{output_id:'e1',run_tag:'before',text:'Exact explanation\n',result_uids:['r0']}],
 executions:results.map(result=>({run_tag:result.run_tag,results:[result]})),warnings:[]};
const prepared=new Map();
function nativeFile(kind,large){
 const key=kind+large;if(prepared.has(key))return prepared.get(key);
 const body=execFileSync(python,['-c',
  'import sys,json,shutil; sys.path.insert(0,sys.argv[1]); import export_files; b=json.load(sys.stdin); '+
  'payload="x"*(1024*1024); '+
  'b["executions"]=[{**e,"costs":[{"id":i,"receipt":{"payload":payload}} for i in range(256)]} for e in b["executions"]] if sys.argv[3]=="large" else b["executions"]; '+
  'target,size=export_files.build_file(b,sys.argv[2]); shutil.copyfileobj(target,sys.stdout.buffer); target.close()',
  api,kind,large?'large':'small'],{input:JSON.stringify(bundle),maxBuffer:64*1024*1024});
 prepared.set(key,body);return body;
}
const browser=await chromium.launch({headless:true,...(process.env.MEMSTARA_BROWSER_EXECUTABLE?{executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE}:{})});
try{
 const page=await browser.newPage({acceptDownloads:true,viewport:{width:768,height:900}});
 const errors=[],requests=[];let failed=false,held=false,release=null,large=false;
 page.on('pageerror',error=>errors.push(error.message));
 await page.route(/\/api\/experiments\/(?:linked-(?:export|download)\?|prepare-download\?|prepared-file\/)/,async route=>{
  const url=new URL(route.request().url());requests.push(url);
  if(held)await new Promise(resolve=>{release=resolve;});
  if(failed)return route.fulfill({status:503,json:{detail:'Archive temporarily unavailable'}}).catch(()=>{});
  assert(!url.pathname.endsWith('linked-export'),'Table CSV must not fetch the full result JSON');
  const kind=url.searchParams.get('format')??(url.pathname.endsWith('1'.repeat(32))?'table':'zip'),body=nativeFile(kind,large);
  if(url.pathname.endsWith('prepare-download')){
   const token=(kind==='table'?'1':'2').repeat(32);
   return route.fulfill({status:200,contentType:'application/x-ndjson',body:
    JSON.stringify({type:'progress',message:'Preparing files',progress:{phase:'preparing',completedUnits:1,totalUnits:8}})+'\n'+
    JSON.stringify({type:'ready',kind,download_url:'/api/experiments/prepared-file/'+token,bytes:body.length,results:2,executions:2,warnings:0})+'\n'}).catch(()=>{});
  }
  return route.fulfill({status:200,body,headers:{'Content-Type':kind==='zip'?'application/zip':'text/csv',
   'X-Memstara-Export-Results':'2','X-Memstara-Export-Executions':'2','X-Memstara-Export-Warnings':'0',
   'X-Memstara-Export-Bytes':String(body.length)}}).catch(()=>{});
 });
 await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/hypothesis-metrics.fixture.html`);
 await page.evaluate(rows=>window.deliverMetricResults(rows),results);
 await page.getByRole('button',{name:/Compare hypothesis results/}).click();
 for(const label of ['Download table CSV','Download complete evidence CSV','Download linked results ZIP']){
  const event=page.waitForEvent('download');await page.getByRole('button',{name:label,exact:true}).click();
  const download=await event,stream=await download.createReadStream(),chunks=[];for await(const chunk of stream)chunks.push(chunk);
  const data=Buffer.concat(chunks);
  if(label.includes('ZIP')){
   const files=JSON.parse(execFileSync(python,['-c','import sys,io,zipfile,json; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); assert z.testzip() is None; print(json.dumps({n:z.read(n).decode("utf-8") for n in z.namelist()}))'],{input:data,encoding:'utf8'}));
   assert.equal(JSON.parse(files['interpretations.json'])[0].text,'\n# Original 한글\n');
   assert.equal(JSON.parse(files['explanations.json'])[0].result_uids[0],'r0');
   assert(files['results.csv'].includes('[""i1"",""i2""]'));
   assert(files['complete_evidence.csv'].includes('"before"'));assert(files['complete_evidence.csv'].includes('"after"'));
   assert.deepEqual(JSON.parse(files['complete_evidence.json']),bundle.executions);
  }else{assert(data.toString().includes('interpretation_output_ids'));assert(!data.toString().includes('Original 한글'));}
  await expect(page.getByRole('status').filter({hasText:'2 saved results from 2 execution(s)'})).toHaveCount(1);
 }
 assert.equal(requests[0].searchParams.get('format'),'table');
 assert.equal(requests[2].searchParams.get('format'),'complete');
 assert.equal(requests[3].searchParams.get('format'),'zip');
 assert(requests.filter(url=>!url.pathname.includes('/prepared-file/')).every(url=>url.searchParams.get('run_tags')==='continued-experiment'));
 failed=true;let downloads=0;page.on('download',()=>downloads++);
 await page.getByRole('button',{name:'Download linked results ZIP',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Archive temporarily unavailable');assert.equal(downloads,0);
 failed=false;held=true;
 // Exercise the rendered worker progress contract with deterministic byte counts.
 await page.evaluate(()=>{
  const NativeWorker=window.Worker;
  window.Worker=class extends NativeWorker{constructor(...args){super(...args);window.activeExportWorker=this;}};
 });
 await page.getByRole('button',{name:'Download linked results ZIP',exact:true}).click();
 await expect(page.getByRole('button',{name:'Cancel export',exact:true})).toBeVisible();
 await expect.poll(()=>release!==null).toBe(true);
 const progress=page.getByRole('progressbar',{name:'Export preparation progress'});
 await expect(progress).toBeVisible();
 assert.equal(await progress.getAttribute('value'),null,'Preparation must not invent a completion percentage');
 await expect(page.getByText('Waiting for server progress.',{exact:true})).toBeVisible();
 await expect(page.getByText('Elapsed 0:01',{exact:true})).toBeVisible();
 await page.evaluate(()=>window.activeExportWorker.onmessage({data:{type:'progress',message:'Preparing ZIP: complete_evidence.csv',progress:{phase:'preparing',completedUnits:4,totalUnits:8}}}));
 await expect(progress).toHaveAttribute('value','50');
 await expect(page.getByText('Current stage: 4 / 8 · 50% (not overall completion)',{exact:true})).toBeVisible();
 await page.evaluate(()=>window.activeExportWorker.onmessage({data:{type:'progress',message:'Downloading the prepared export file…',progress:{phase:'downloading',receivedBytes:524288,totalBytes:1048576}}}));
 await expect(page.getByRole('progressbar',{name:'Export download progress'})).toHaveAttribute('value','50');
 await expect(page.getByText('512.0 KiB / 1.0 MiB · 50%',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Downloading…',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:/Compare performance by hypothesis skill/}).click();
 await page.getByLabel('Performance metric').selectOption('f1');
 await expect(page.getByLabel('Performance metric')).toHaveValue('f1');
 await page.getByRole('button',{name:'Cancel export',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'Export cancelled.'})).toHaveCount(1);
 await expect(page.getByRole('progressbar')).toHaveCount(0);
 held=false;release();await page.waitForTimeout(100);assert.equal(downloads,0);
 large=true;
 await page.evaluate(()=>{
  window.exportHeartbeat={ticks:0,maxGap:0,last:performance.now()};
  window.exportHeartbeatTimer=setInterval(()=>{const now=performance.now(),state=window.exportHeartbeat;state.ticks++;state.maxGap=Math.max(state.maxGap,now-state.last);state.last=now;},10);
 });
 const event=page.waitForEvent('download',{timeout:120000});
 await page.getByRole('button',{name:'Download linked results ZIP',exact:true}).click();
 const download=await event;
 const heartbeat=await page.evaluate(()=>{clearInterval(window.exportHeartbeatTimer);return window.exportHeartbeat;});
 assert(heartbeat.ticks>10);assert(heartbeat.maxGap<1000,JSON.stringify(heartbeat));
 assert.equal(await download.failure(),null);
 const path=await download.path();assert((await stat(path)).size<5*1024*1024);
 execFileSync(python,['-c','import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; assert z.getinfo("complete_evidence.json").file_size>512*1024*1024; assert z.getinfo("complete_evidence.csv").file_size>512*1024*1024',path]);
 assert.deepEqual(errors,[]);
 console.log('PASS: all buttons, native ZIP/CSV, exact agent text and IDs, errors, cancellation; no large evidence JSON requested');
 console.log(`PASS: 512+ MiB evidence compressed without omissions; UI heartbeat max gap ${Math.round(heartbeat.maxGap)} ms`);
}finally{await browser.close();}
