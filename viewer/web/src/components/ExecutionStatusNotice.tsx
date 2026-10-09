import {useState} from 'react';
import {resultsStatus} from '../lib/resultsStatus';

type Props={pipeline:Parameters<typeof resultsStatus>[0];stale?:boolean;
 execution?:Parameters<typeof resultsStatus>[2];label:string;runTag?:string|null;loading?:boolean};

/** Scope an execution outcome to its saved record, never to the whole application. */
export default function ExecutionStatusNotice({pipeline,stale=false,execution,label,runTag,loading=false}:Props){
 const [expanded,setExpanded]=useState(false);
 if(loading)return <div role="status" className="m-4 rounded-lg border border-paper-line p-3 text-sm">Loading the selected execution. Results still shown belong to {label}.</div>;
 const notice=resultsStatus(pipeline,stale,execution);
 if(!notice)return null;
 const terminal=['failed','blocked','incomplete','interrupted'].includes(pipeline?.status??'');
 const code=pipeline?.code;
 const summary=code==='model_connection'
   ? 'A model request did not finish. This execution stopped before completing every step.'
   : code==='model_request_rejected'
   ? 'The model request was rejected. This execution stopped before completing every step.'
   : 'This execution did not complete every required step.';
 return <section role="status" aria-label="Execution outcome" data-testid="results-status" data-tone={notice.warning?'warning':'progress'} className="m-4 min-w-0 rounded-lg border border-paper-line bg-paper p-3 text-sm">
  <p className="break-words font-semibold">{terminal?'Saved execution outcome':'Execution progress'} · {label}</p>
  {terminal&&!stale?<><p className="mt-2">{summary}</p><p className="mt-1 text-ink-soft">Completed results remain available below. This status applies only to the execution identified here.</p>
   <button type="button" aria-expanded={expanded} className="mt-2 rounded border border-paper-line px-3 py-2" onClick={()=>setExpanded(!expanded)}>{expanded?'Hide execution details':'Show execution details'}</button>
   {expanded&&<div className="mt-2 space-y-2 break-words"><p className="whitespace-pre-wrap">{notice.text}</p><p className="break-all text-xs">Execution ID: {runTag??'Not recorded'}</p></div>}
  </>:<p className="mt-2 break-words">{notice.text}</p>}
 </section>;
}
