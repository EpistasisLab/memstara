import type {PreparedExport} from './linkedDownload';

function downloadFailure(error:unknown):Error {
 const name=error instanceof Error?error.name:'';
 if(name==='TimeoutError'||name==='AbortError')return Error('The export download timed out before the complete file arrived. Saved results are unchanged. Retry or export fewer executions.');
 if(name==='TypeError')return Error('The export connection was interrupted before the file finished downloading. Saved results are unchanged. Check the connection and retry.');
 return error instanceof Error?error:Error('The export file could not be downloaded. Saved results are unchanged.');
}

/** Receive a binary file, never turn the complete evidence into one JS string. */
export async function readLinkedFile(tags:string[],kind:'zip'|'complete',onProgress?:(message:string)=>void,signal?:AbortSignal):Promise<PreparedExport>{
 const selected=[...new Set(tags.filter(Boolean))];
 if(!selected.length)throw Error('Choose a recorded execution first.');
 const query=new URLSearchParams({run_tags:selected.join(','),format:kind});
 try{
  const response=await fetch(`/api/experiments/linked-download?${query}`,{
   credentials:'same-origin',signal:signal??AbortSignal.timeout(180000),headers:{Accept:kind==='zip'?'application/zip':'text/csv'},
  });
  if(!response.ok){
   if(response.status===401)throw Error('Your browser login expired. Reload the page and sign in again.');
   if(response.status===404)throw Error('The download API is not available. Update both the API and web services, then refresh this page.');
   let detail='';try{const value=await response.json();detail=typeof value.detail==='string'?value.detail:typeof value.error==='string'?value.error:'';}catch{/* Do not display HTML or private response content. */}
   throw Error(detail||`The export file is unavailable (HTTP ${response.status}). Saved results are unchanged.`);
  }
  const expectedType=kind==='zip'?'application/zip':'text/csv';
  if(!(response.headers.get('content-type')??'').toLowerCase().startsWith(expectedType)){
   await response.body?.cancel();
   throw Error('The download URL returned a page instead of the requested file. Refresh and check that the API and web versions match.');
  }
  const counts=['Results','Executions','Warnings'].map(key=>response.headers.get(`X-Memstara-Export-${key}`));
  if(counts.some(value=>value===null||!/^\d+$/.test(value))){
   await response.body?.cancel();throw Error('The export file receipt is missing. No substitute file was downloaded.');
  }
  onProgress?.('Downloading the prepared export file…');
  const blob=await response.blob(),length=response.headers.get('X-Memstara-Export-Bytes')??
   (!response.headers.get('content-encoding')?response.headers.get('content-length'):null);
  if(blob.size===0||(length!==null&&blob.size!==Number(length)))throw Error('The export transfer ended before the complete file arrived. Refresh and retry; saved results are unchanged.');
  if(kind==='zip'){
   const header=new Uint8Array(await blob.slice(0,4).arrayBuffer());
   if(header[0]!==0x50||header[1]!==0x4b||header[2]!==3||header[3]!==4)throw Error('The server did not return a valid ZIP file. No substitute file was downloaded.');
  }
  return {blob,results:Number(counts[0]),executions:Number(counts[1]),warnings:Number(counts[2])};
 }catch(error){throw downloadFailure(error);}
}
