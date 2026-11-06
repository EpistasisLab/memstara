export type ExportKind='table'|'complete'|'zip';
export type ExportRequest={tags:string[];kind:ExportKind};
export type PreparedExport={blob:Blob;results:number;executions:number;warnings:number};
export type ExportProgress={phase:'preparing'|'downloading'|'verifying';receivedBytes?:number;totalBytes?:number;completedUnits?:number;totalUnits?:number};
export type ExportMessage={type:'progress';message:string;progress?:ExportProgress}|{type:'complete';value:PreparedExport}|{type:'error';message:string};

/** Fetching, JSON parsing, CSV formatting and ZIP assembly all stay off the UI. */
export function prepareLinkedDownload(tags:string[],kind:ExportKind,{signal,onProgress}:{signal?:AbortSignal;onProgress?:(message:string,progress?:ExportProgress)=>void}={}):Promise<PreparedExport>{
 return new Promise((resolve,reject)=>{
  if(signal?.aborted){reject(new DOMException('Export cancelled.','AbortError'));return;}
  let worker:Worker;
  try{worker=new Worker(new URL('./linkedExport.worker.ts',import.meta.url),{type:'module'});}
  catch{reject(Error('The export worker could not start. Refresh this page and try again.'));return;}
  const cleanup=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);worker.terminate();};
  const fail=(error:Error)=>{cleanup();reject(error);};
  const cancel=()=>fail(new DOMException('Export cancelled.','AbortError'));
  const timeout=()=>fail(Error('The export made no progress for three minutes. Saved results are unchanged; retry or export fewer executions.'));
  let timer=setTimeout(timeout,180000);
  signal?.addEventListener('abort',cancel,{once:true});
  worker.onmessage=(event:MessageEvent<ExportMessage>)=>{
   const message=event.data;
   if(message.type==='progress'){
    clearTimeout(timer);timer=setTimeout(timeout,180000);
    onProgress?.(message.message,message.progress);return;
   }
   if(message.type==='error'){fail(Error(message.message));return;}
   if(message.type==='complete'){cleanup();resolve(message.value);}
  };
  worker.onerror=event=>{event.preventDefault();fail(Error('The export worker stopped before the file was ready. Saved results are unchanged. Refresh and try again.'));};
  worker.onmessageerror=()=>fail(Error('The prepared download could not be received. No substitute file was downloaded.'));
  worker.postMessage({tags,kind} satisfies ExportRequest);
 });
}
