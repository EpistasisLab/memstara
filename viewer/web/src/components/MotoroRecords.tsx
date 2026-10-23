import {useLoopLabel} from '../lib/useLoopLabel';
import { displayText, displayJson } from '../lib/displayText';
import {useEffect,useState} from 'react';
import {usageDuration} from '../lib/loopUsage';
type Call={run_id:string|null;stage:string;loop:number|null;seq:number;record:Record<string,unknown>|null;availability:string};
type Page={calls:Call[];note:string};
type Steps={steps:Record<string,unknown>[];next_offset:number|null};
async function read<T>(url:string,signal:AbortSignal):Promise<T>{
 const r=await fetch(url,{signal});if(!r.ok)throw Error(`Motoro records unavailable (${r.status}). Retry to refresh.`);return r.json();
}
function Timing({record}:{record:Record<string,unknown>}){
 const startValue=record.started_at??record.first_step_started_at;
 const start=typeof startValue==='string'?Date.parse(startValue):NaN;
 const finish=record.completed_at??record.last_heartbeat_at;
 const end=typeof finish==='string'?Date.parse(finish):NaN;
 const seconds=Number.isFinite(start)&&Number.isFinite(end)&&end>=start?(end-start)/1000:null;
 return <dl className="grid grid-cols-1 gap-2 rounded border border-paper-line p-3 text-sm sm:grid-cols-3">
 <div><dt>Elapsed time</dt><dd>{usageDuration(seconds)}{!record.completed_at&&seconds!==null?' · through last heartbeat':''}</dd></div>
 <div><dt>{record.started_at?'Started':'First recorded step'}</dt><dd>{Number.isFinite(start)?new Date(start).toLocaleString():'Not recorded'}</dd></div>
 <div><dt>{record.completed_at?'Completed':'Last heartbeat'}</dt><dd>{Number.isFinite(end)?new Date(end).toLocaleString():'Not recorded'}</dd></div>
 </dl>;
}
function Fields({record}:{record:Record<string,unknown>}){
 return <div className="space-y-2">{Object.entries(record).map(([key,value])=><details className="rounded border border-paper-line p-2" key={key}><summary className="cursor-pointer break-words">{displayText(key.replaceAll('_',' '))}</summary><pre className="mt-2 whitespace-pre-wrap break-all text-xs">{displayJson(value)}</pre></details>)}</div>;
}
function Invocation({tag,id}:{tag:string;id:string}){
 const [run,setRun]=useState<Record<string,unknown>|null>(null),[page,setPage]=useState<Steps|null>(null);
 const [offset,setOffset]=useState(0),[selected,setSelected]=useState<number|null>(null),[detail,setDetail]=useState<Record<string,unknown>|null>(null),[error,setError]=useState('');
 const [refresh,setRefresh]=useState(0);
 const query=`run_tag=${encodeURIComponent(tag)}&run_id=${encodeURIComponent(id)}`;
 useEffect(()=>{const c=new AbortController();setError('');setRun(null);
  read<{record:Record<string,unknown>;first_step_started_at?:string|null}>(`/api/motoro/run?${query}`,c.signal).then(d=>{if(!c.signal.aborted)setRun({...d.record,first_step_started_at:d.first_step_started_at});}).catch(e=>{if(!c.signal.aborted)setError(String(e));});return()=>c.abort();
 },[query,refresh]);
 useEffect(()=>{const c=new AbortController();setPage(null);setError('');
  read<Steps>(`/api/developer/steps?${query}&offset=${offset}`,c.signal).then(d=>{if(!c.signal.aborted)setPage(d);}).catch(e=>{if(!c.signal.aborted)setError(String(e));});return()=>c.abort();
 },[query,offset,refresh]);
 useEffect(()=>{setDetail(null);if(selected===null)return;const c=new AbortController();
  read<Steps>(`/api/developer/steps?${query}&offset=${selected}&detail=true`,c.signal).then(d=>{if(!c.signal.aborted)setDetail(d.steps[0]??null);}).catch(e=>{if(!c.signal.aborted)setError(String(e));});return()=>c.abort();
 },[query,selected,refresh]);
 return <div className="space-y-3 mt-3"><button onClick={()=>setRefresh(n=>n+1)}>Refresh Motoro record</button>{error&&<p role="alert">{error}</p>}
 {run&&<Timing record={run}/>}
 <details><summary className="cursor-pointer font-semibold">Run input, output, state and configuration</summary>{run?<Fields record={run}/>:<p>Reading Motoro record…</p>}</details>
 <h4 className="font-semibold">Recorded steps</h4><p className="text-xs text-ink-soft">Select a step to read its model usage, tool arguments/results and input/output. Credential fields are redacted.</p>
 {page?.steps.map((s,i)=><button className="block w-full rounded border border-paper-line p-2 text-left" key={String(s.id)} aria-pressed={selected===offset+i} onClick={()=>setSelected(offset+i)}>Step {String(s.sequence)} · {String(s.phase)} · {String(s.started_at??'Time unavailable')}</button>)}
 {page&&!page.steps.length&&<p>No steps recorded.</p>}
 <div className="flex gap-3"><button disabled={offset===0} onClick={()=>{setSelected(null);setOffset(Math.max(0,offset-50));}}>Previous steps</button><button disabled={page?.next_offset==null} onClick={()=>{setSelected(null);setOffset(page!.next_offset!);}}>Next steps</button></div>
 {detail&&<Fields record={detail}/>}</div>;
}
export default function MotoroRecords({tag,loop}:{tag:string;loop:number|null}){
 const labelReplicate=useLoopLabel();
 const [page,setPage]=useState<Page|null>(null),[error,setError]=useState(''),[selected,setSelected]=useState(''),[refresh,setRefresh]=useState(0);
 useEffect(()=>{const c=new AbortController();setPage(null);setSelected('');setError('');
  read<Page>(`/api/motoro/execution?run_tag=${encodeURIComponent(tag)}${loop===null?'':`&loop=${loop}`}`,c.signal).then(d=>{if(!c.signal.aborted)setPage(d);}).catch(e=>{if(!c.signal.aborted)setError(String(e));});return()=>c.abort();
 },[tag,loop,refresh]);
 return <section className="tm-motoro-records m-3 space-y-3 rounded-lg border border-paper-line p-3" aria-label="Motoro runtime records"><h3 className="font-semibold">Motoro runtime records</h3><p className="text-xs text-ink-soft">{page?.note??'Read model calls, tool execution, usage and saved state directly from Motoro.'}</p>
 <button onClick={()=>setRefresh(n=>n+1)}>Refresh agent records</button>{error&&<p role="alert">{error}</p>}
 <label className="block">Agent invocation<select aria-label="Motoro agent invocation" className="block w-full min-w-0 rounded border border-paper-line p-2" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select a recorded invocation</option>{page?.calls.filter(c=>c.run_id).map((c,i)=><option key={`${c.run_id}-${i}`} value={c.run_id!}>{c.stage} · {c.loop==null?'Execution-wide':labelReplicate({iteration:c.loop,run_tag:tag})} · {String(c.record?.status??'Record missing')} · {c.run_id}</option>)}</select></label>
 {page&&!page.calls.length&&<p>No invocations in this scope.</p>}
 {selected&&<Invocation key={`${tag}:${loop}:${selected}`} tag={tag} id={selected}/>}</section>;
}
