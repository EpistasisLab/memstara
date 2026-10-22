import { displayText, displayJson } from '../lib/displayText';
import { useEffect, useRef, useState } from 'react';
type Experiment={id:string;combinations:number;executions:number};
type Row={id:string;run_tag:string|null;status:string|null;agent_seconds:number|null;estimated_usd:number|null;unpriced_calls:number;definition:unknown;metrics:{model:string;auc:number;f1:number;task_id:number}[]|null};
export default function ExperimentRegistry({refreshRevision=0}:{refreshRevision?:number}){
 const [experiments,setExperiments]=useState<Experiment[]>([]),[selected,setSelected]=useState('');
 const [rows,setRows]=useState<Row[]>([]),[error,setError]=useState('');
 const [detail,setDetail]=useState<Record<string,unknown>|null>(null),[busy,setBusy]=useState(false);
 const [loaded,setLoaded]=useState(false);
 const detailRequest=useRef<AbortController|null>(null);
 useEffect(()=>()=>detailRequest.current?.abort(),[]);
 useEffect(()=>{let stopped=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
  async function poll(){controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),10000);
   try{const response=await fetch('/api/experiments',{signal:controller.signal});if(!response.ok)throw Error('Experiment registry is unavailable.');
    const list:Experiment[]=await response.json();let data:Row[]=[];
    if(selected){const response=await fetch(`/api/experiments/combinations?experiment_id=${encodeURIComponent(selected)}`,{signal:controller.signal});if(!response.ok)throw Error('Could not load combinations.');data=await response.json();}
    if(!stopped){setExperiments(list);setRows(data);setError('');setLoaded(true);}
   }catch(e){if(!stopped)setError(e instanceof Error?e.message:'Registry unavailable.');}
   finally{clearTimeout(deadline);if(!stopped)timer=setTimeout(poll,10000);}
  }void poll();return()=>{stopped=true;clearTimeout(timer);controller?.abort();};
 },[selected,refreshRevision]);
 async function inspect(tag:string){
  detailRequest.current?.abort();const controller=new AbortController();detailRequest.current=controller;setBusy(true);setDetail(null);
  try{const r=await fetch(`/api/experiments/execution?run_tag=${encodeURIComponent(tag)}`,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15000)])});if(!r.ok)throw Error('Could not load execution evidence.');const value=await r.json();if(!controller.signal.aborted){setDetail(value);setError('');}}
  catch(e){if(!controller.signal.aborted)setError(e instanceof Error&&e.name==='TimeoutError'?'Execution evidence timed out. Retry Inspect to load it.':'Could not load execution evidence. Retry Inspect to load it.');}
  finally{if(detailRequest.current===controller)setBusy(false);}
 }
 function download(){if(!detail)return;const url=URL.createObjectURL(new Blob([JSON.stringify(detail,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${detail.run_tag}-evidence.json`;a.click();URL.revokeObjectURL(url);}
 return <section className="p-4 space-y-4" aria-label="Experiment registry">
  <h2 className="text-lg font-semibold">Experiments</h2><p>Saved records across executions. Costs are Motoro estimates, not actual charges. Agent time includes recorded retries.</p>
  <label>Experiment <select className="max-w-full border rounded bg-paper p-2" value={selected} onChange={e=>{detailRequest.current?.abort();setBusy(false);setSelected(e.target.value);setDetail(null);setRows([]);setError('');}}><option value="">Choose an experiment</option>{experiments.map(e=><option key={e.id} value={e.id}>{e.id} · {e.executions}/{e.combinations} executions/combinations</option>)}</select></label>
  {error&&<p role="alert">{error} Previously loaded data may be stale.</p>}
  {!loaded&&!error&&<p role="status">Loading registered experiments…</p>}
  {loaded&&!experiments.length&&!error&&<p>No registered experiments yet.</p>}
  <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr>{['Combination','Execution','Status','Agent seconds','Estimated USD','Exploratory AUROC / F1','Evidence'].map(x=><th className="p-2 text-left" key={x}>{x}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={`${r.id}-${i}`}><td className="p-2">{r.id}</td><td className="p-2 break-all">{r.run_tag??'Not started'}</td><td className="p-2">{r.status??'Planned'}</td><td className="p-2">{r.agent_seconds==null?'—':Number(r.agent_seconds).toFixed(1)}</td><td className="p-2">{r.estimated_usd==null?'Unknown':`$${Number(r.estimated_usd).toFixed(5)}`}{r.unpriced_calls>0?' (partial)':''}</td><td className="p-2">{r.metrics?.map(m=><div key={`${m.task_id}-${m.model}`}>{m.model}: {m.auc?.toFixed(3)??'—'} / {m.f1?.toFixed(3)??'—'}</div>)??'—'}</td><td className="p-2"><button disabled={!r.run_tag||busy} onClick={()=>r.run_tag&&void inspect(r.run_tag)}>Inspect</button></td></tr>)}</tbody></table></div>
  {busy&&<p role="status">Loading execution evidence…</p>}
  {detail&&<div className="space-y-3"><h3 className="font-semibold break-all">{String(detail.run_tag)}</h3><button onClick={download}>Download complete evidence JSON</button>{['configuration','prompts','agents','results','costs','artifacts','report','outcome'].map(key=><details key={key}><summary className="cursor-pointer capitalize">{key}</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs p-3">{typeof detail[key]==='string'?displayText(String(detail[key])):displayJson(detail[key])}</pre></details>)}</div>}
 </section>;
}
