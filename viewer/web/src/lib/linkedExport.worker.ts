import {readLinkedFile} from './linkedFileDownload';
import {readPreparedExport} from './preparedExport';
import type {ExportRequest,ExportMessage} from './linkedDownload';

const send=(message:ExportMessage)=>self.postMessage(message);
self.onmessage=async(event:MessageEvent<ExportRequest>)=>{
 const {tags,kind}=event.data;
 try{
  send({type:'progress',message:'Preparing the export file on the server…',progress:{phase:'preparing'}});
  const progress=(message:string,progress?:import('./linkedDownload').ExportProgress)=>send({type:'progress',message,progress});
  const value=kind==='complete'?await readLinkedFile(tags,kind,progress):await readPreparedExport(tags,kind,progress);
  send({type:'complete',value});
 }catch(error){send({type:'error',message:error instanceof Error?error.message:'Linked evidence is unavailable.'});}
};
