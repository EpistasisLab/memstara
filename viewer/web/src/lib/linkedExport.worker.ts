import {readLinkedExport,linkedResultsCsv,linkedCompleteCsv,linkedExportEntries,zipBlob} from './linkedOutputExport';
import type {ExportRequest,ExportMessage} from './linkedDownload';

const send=(message:ExportMessage)=>self.postMessage(message);
self.onmessage=async(event:MessageEvent<ExportRequest>)=>{
 const {tags,kind}=event.data;
 try{
  send({type:'progress',message:'Fetching saved results and linked outputs…'});
  const bundle=await readLinkedExport(tags,kind!=='table');
  let blob:Blob;
  if(kind==='zip'){
   blob=zipBlob(linkedExportEntries(bundle),name=>send({type:'progress',message:`Adding ${name}…`}));
  }else{
   send({type:'progress',message:kind==='complete'?'Formatting complete evidence CSV…':'Formatting results table CSV…'});
   blob=new Blob([kind==='table'?linkedResultsCsv(bundle):linkedCompleteCsv(bundle)],{type:'text/csv;charset=utf-8'});
  }
  send({type:'complete',value:{blob,results:bundle.results.length,executions:bundle.run_tags.length,warnings:bundle.warnings.length}});
 }catch(error){send({type:'error',message:error instanceof Error?error.message:'Linked evidence is unavailable.'});}
};
