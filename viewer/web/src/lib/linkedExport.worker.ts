import {readLinkedExport,linkedResultsCsv} from './linkedOutputExport';
import {readLinkedFile} from './linkedFileDownload';
import type {ExportRequest,ExportMessage} from './linkedDownload';

const send=(message:ExportMessage)=>self.postMessage(message);
self.onmessage=async(event:MessageEvent<ExportRequest>)=>{
 const {tags,kind}=event.data;
 try{
  if(kind!=='table'){
   send({type:'progress',message:'Preparing the export file on the server…',progress:{phase:'preparing'}});
   const value=await readLinkedFile(tags,kind,(message,progress)=>send({type:'progress',message,progress}));
   send({type:'complete',value});return;
  }
  send({type:'progress',message:'Fetching saved results and linked outputs…'});
  const bundle=await readLinkedExport(tags,false);
  send({type:'progress',message:'Formatting results table CSV…'});
  const blob=new Blob([linkedResultsCsv(bundle)],{type:'text/csv;charset=utf-8'});
  send({type:'complete',value:{blob,results:bundle.results.length,executions:bundle.run_tags.length,warnings:bundle.warnings.length}});
 }catch(error){send({type:'error',message:error instanceof Error?error.message:'Linked evidence is unavailable.'});}
};
