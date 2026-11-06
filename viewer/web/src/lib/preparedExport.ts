import {readLinkedFile} from './linkedFileDownload.ts';
import type {ExportProgress,PreparedExport} from './linkedDownload';

/** Preparation reports stages; only a verified ready receipt starts binary transfer. */
export async function readPreparedExport(tags:string[],kind:'table'|'zip',onProgress?:(message:string,progress?:ExportProgress)=>void,signal?:AbortSignal):Promise<PreparedExport>{
 const selected=[...new Set(tags.filter(Boolean))];
 if(!selected.length)throw Error('Choose a recorded execution first.');
 const controller=new AbortController();
 const cancel=()=>controller.abort(signal?.reason);
 const expire=()=>controller.abort(new DOMException('Preparation connection stalled','TimeoutError'));
 let timer=setTimeout(expire,180000);
 const activity=()=>{clearTimeout(timer);timer=setTimeout(expire,180000);};
 signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)cancel();
 let reader:ReadableStreamDefaultReader<Uint8Array>|undefined;
 let ready:{download_url:string;bytes:number;results:number;executions:number;warnings:number}|undefined;
 try{
  const query=new URLSearchParams({run_tags:selected.join(','),format:kind});
  const response=await fetch(`/api/experiments/prepare-download?${query}`,{credentials:'same-origin',signal:controller.signal,headers:{Accept:'application/x-ndjson'}});
  if(!response.ok){
   if(response.status===401)throw Error('Your browser login expired. Reload the page and sign in again.');
   if(response.status===404)throw Error('The export preparation API is not available. Update the API and web services, then refresh.');
   let detail='';try{const body=await response.json();detail=typeof body.detail==='string'?body.detail:typeof body.error==='string'?body.error:'';}catch{/* Never display an HTML error page. */}
   throw Error(detail||`Export preparation failed (HTTP ${response.status}). Saved results are unchanged.`);
  }
  if(!response.headers.get('content-type')?.startsWith('application/x-ndjson')||!response.body)throw Error('The export preparation URL returned an unexpected response. Update the API and web services together.');
  reader=response.body.getReader();const decoder=new TextDecoder();let buffer='';
  while(!ready){
   const {value,done}=await reader.read();if(done)break;
   activity();buffer+=decoder.decode(value,{stream:true});
   if(buffer.length>65536)throw Error('The export preparation response is invalid.');
   let newline;
   while((newline=buffer.indexOf('\n'))>=0){
    const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(!line.trim())continue;
    const event=JSON.parse(line);
    if(event.type==='error')throw Error(typeof event.message==='string'?event.message:'Export preparation failed.');
    if(event.type==='progress'){
     if(typeof event.message!=='string')throw Error('Invalid export progress response.');
     const p=event.progress??{};const progress:ExportProgress={phase:'preparing'};
     if(Number.isSafeInteger(p.completedUnits)&&Number.isSafeInteger(p.totalUnits)&&p.totalUnits>0&&p.completedUnits>=0&&p.completedUnits<=p.totalUnits){progress.completedUnits=p.completedUnits;progress.totalUnits=p.totalUnits;}
     onProgress?.(event.message+(event.heartbeat?' — server is still preparing.':''),progress);
    }else if(event.type==='ready'){
     if(!/^\/api\/experiments\/prepared-file\/[a-f0-9]{32}$/.test(event.download_url)||event.kind!==kind||
       !['bytes','results','executions','warnings'].every(key=>Number.isSafeInteger(event[key])&&event[key]>=0)||event.bytes===0)
       throw Error('The prepared download receipt is invalid. No file was downloaded.');
     ready=event;break;
    }else throw Error('Unknown export preparation response.');
   }
  }
  if(!ready)throw Error('Export preparation ended before the file was ready. Saved results are unchanged.');
 }finally{
  clearTimeout(timer);signal?.removeEventListener('abort',cancel);
  try{await reader?.cancel();}catch{/* Preserve the preparation error. */}
 }
 const value=await readLinkedFile(selected,kind,onProgress,signal,ready.download_url);
 if(value.blob.size!==ready.bytes||value.results!==ready.results||value.executions!==ready.executions||value.warnings!==ready.warnings)
  throw Error('The downloaded file does not match its preparation receipt. No substitute file was saved.');
 return value;
}
