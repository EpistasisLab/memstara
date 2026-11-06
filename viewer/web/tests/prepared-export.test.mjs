import test from 'node:test';
import assert from 'node:assert/strict';
import {readPreparedExport} from '../src/lib/preparedExport.ts';

const url='/api/experiments/prepared-file/'+'a'.repeat(32);
const receipt={type:'ready',kind:'table',download_url:url,bytes:4,results:2,executions:1,warnings:0};
const eventResponse=events=>new Response(events.map(e=>JSON.stringify(e)+'\n').join(''),{headers:{'Content-Type':'application/x-ndjson'}});
const file=()=>new Response('csv\n',{headers:{'Content-Type':'text/csv','X-Memstara-Export-Bytes':'4','X-Memstara-Export-Results':'2','X-Memstara-Export-Executions':'1','X-Memstara-Export-Warnings':'0'}});

test('table receives progress then a small server CSV, never the full evidence JSON',async()=>{
 const original=globalThis.fetch,calls=[],progress=[];
 try{
  globalThis.fetch=async path=>{calls.push(path);return path===url?file():eventResponse([
   {type:'progress',message:'Reading records',progress:{completedUnits:1,totalUnits:3}},receipt]);};
  const result=await readPreparedExport(['saved'],'table',(message,value)=>progress.push(value));
  assert.equal(await result.blob.text(),'csv\n');
  assert(calls[0].includes('/prepare-download?'));assert(calls[0].includes('format=table'));
  assert.equal(calls[1],url);assert.equal(calls.length,2);
  assert.equal(progress[0].completedUnits,1);assert.equal(progress[0].totalUnits,3);
 }finally{globalThis.fetch=original;}
});

test('heartbeats keep preparation alive beyond three minutes without fake percentages',async(t)=>{
 t.mock.timers.enable({apis:['setTimeout']});
 const original=globalThis.fetch,progress=[];let stream,signal;
 const flush=()=>new Promise(resolve=>setImmediate(resolve));
 try{
  globalThis.fetch=async(path,options)=>{
   if(path===url)return file();
   signal=options.signal;
   return new Response(new ReadableStream({start(c){stream=c;}}),{headers:{'Content-Type':'application/x-ndjson'}});
  };
  const pending=readPreparedExport(['saved'],'table',(m,p)=>progress.push(p));
  await flush();
  for(let i=0;i<4;i++){
   t.mock.timers.tick(100000);
   stream.enqueue(new TextEncoder().encode(JSON.stringify({type:'progress',heartbeat:true,message:'Preparing file',progress:{phase:'preparing'}})+'\n'));
   await flush();assert.equal(signal.aborted,false);
  }
  assert(progress.every(p=>p.totalUnits===undefined));
  stream.enqueue(new TextEncoder().encode(JSON.stringify(receipt)+'\n'));stream.close();
  assert.equal((await pending).blob.size,4);
 }finally{globalThis.fetch=original;t.mock.timers.reset();}
});

test('explicit errors, truncated preparation, and external download URLs fail closed',async()=>{
 const original=globalThis.fetch;
 try{
  for(const [events,pattern] of [
   [[{type:'error',message:'Saved results unavailable'}],/Saved results unavailable/],
   [[{type:'progress',message:'Preparing'}],/ended before/],
   [[{...receipt,download_url:'https://example.com/private'}],/receipt is invalid/],
  ]){
   globalThis.fetch=async()=>eventResponse(events);
   await assert.rejects(()=>readPreparedExport(['saved'],'table'),pattern);
  }
  globalThis.fetch=async()=>new Response('<html>fallback</html>',{headers:{'Content-Type':'text/html'}});
  await assert.rejects(()=>readPreparedExport(['saved'],'table'),/unexpected response/);
 }finally{globalThis.fetch=original;}
});

test('downloaded counts must match the prepared receipt',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async path=>path===url?file():eventResponse([{...receipt,results:99}]);
  await assert.rejects(()=>readPreparedExport(['saved'],'table'),/does not match/);
 }finally{globalThis.fetch=original;}
});
