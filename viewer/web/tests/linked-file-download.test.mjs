import test from 'node:test';
import assert from 'node:assert/strict';
import {readLinkedFile} from '../src/lib/linkedFileDownload.ts';

const headers={'Content-Type':'application/zip','X-Memstara-Export-Results':'64','X-Memstara-Export-Executions':'3','X-Memstara-Export-Warnings':'0'};
test('binary download never parses a large response as JSON',async()=>{
 const original=globalThis.fetch,calls=[];
 try{
  globalThis.fetch=async url=>{calls.push(url);return new Response(new Uint8Array([80,75,3,4,5]),{headers});};
  const value=await readLinkedFile(['continued','continued'],'zip');
  assert.equal(value.blob.size,5);assert.equal(value.results,64);assert.equal(value.executions,3);
  assert(calls[0].includes('linked-download?'));assert(calls[0].includes('format=zip'));
  assert(!calls[0].includes('include_evidence'));
 }finally{globalThis.fetch=original;}
});
test('HTTP 200 timeout, HTML, incomplete bytes and invalid ZIP are distinct failures',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async()=>({ok:true,status:200,headers:new Headers(headers),blob:async()=>{throw new DOMException('expired','TimeoutError');}});
  await assert.rejects(()=>readLinkedFile(['run'],'zip'),/timed out/);
  globalThis.fetch=async()=>new Response('<html>login</html>',{headers:{'Content-Type':'text/html'}});
  await assert.rejects(()=>readLinkedFile(['run'],'zip'),/returned a page/);
  globalThis.fetch=async()=>new Response(new Uint8Array([80,75,3,4]),{headers:{...headers,'X-Memstara-Export-Bytes':'100'}});
  await assert.rejects(()=>readLinkedFile(['run'],'zip'),/complete file/);
  globalThis.fetch=async()=>new Response('not a zip',{headers});
  await assert.rejects(()=>readLinkedFile(['run'],'zip'),/valid ZIP/);
  globalThis.fetch=async()=>new Response('',{status:404});
  await assert.rejects(()=>readLinkedFile(['run'],'zip'),/Update both the API and web/);
 }finally{globalThis.fetch=original;}
});
test('complete CSV downloads as a file and validates the uncompressed receipt size',async()=>{
 const original=globalThis.fetch;
 try{
  const data='\ufeff"record_type"\r\n"execution"\r\n';
  globalThis.fetch=async()=>new Response(data,{headers:{...headers,'Content-Type':'text/csv','Content-Encoding':'gzip','Content-Length':'1','X-Memstara-Export-Bytes':String(new TextEncoder().encode(data).length)}});
  assert.deepEqual(new Uint8Array(await (await readLinkedFile(['run'],'complete')).blob.arrayBuffer()),new TextEncoder().encode(data));
 }finally{globalThis.fetch=original;}
});

test('stream progress reports actual bytes before completion and verifies the finished file',async()=>{
 const original=globalThis.fetch,events=[];let stream;
 try{
  globalThis.fetch=async()=>new Response(new ReadableStream({start(controller){stream=controller;}}),{
   headers:{...headers,'X-Memstara-Export-Bytes':'8'},
  });
  const pending=readLinkedFile(['run'],'zip',(message,progress)=>events.push(progress));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.deepEqual(events[0],{phase:'downloading',receivedBytes:0,totalBytes:8});
  await new Promise(resolve=>setTimeout(resolve,210));
  stream.enqueue(new Uint8Array([80,75,3,4]));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert(events.some(event=>event.receivedBytes===4&&event.totalBytes===8));
  assert(!events.some(event=>event.phase==='verifying'));
  stream.enqueue(new Uint8Array([5,6,7,8]));stream.close();
  const result=await pending;
  assert.equal(result.blob.size,8);
  assert.deepEqual(events.at(-1),{phase:'verifying',receivedBytes:8,totalBytes:8});
 }finally{globalThis.fetch=original;}
});

test('unknown transfer length stays indeterminate and interrupted streams do not complete',async()=>{
 const original=globalThis.fetch,events=[];
 try{
  globalThis.fetch=async()=>new Response(new Uint8Array([80,75,3,4]),{headers});
  await readLinkedFile(['run'],'zip',(message,progress)=>events.push(progress));
  assert(events.every(event=>event.totalBytes===undefined));
  globalThis.fetch=async()=>new Response(new ReadableStream({start(controller){controller.error(new TypeError('connection lost'));}}),{headers});
  await assert.rejects(()=>readLinkedFile(['run'],'zip'),/connection was interrupted/);
 }finally{globalThis.fetch=original;}
});
