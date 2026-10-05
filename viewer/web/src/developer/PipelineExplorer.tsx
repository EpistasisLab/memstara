import {useEffect, useMemo, useState} from 'react';
import {ReactFlow, Background, Controls, MarkerType, Position} from '@xyflow/react';
import {pipelineSteps, pipelineLinks} from './pipelineFlow';
import type {RunSummary} from '../types';

type Call = {run_id?:string; stage:string; seq:number; loop:number|null; loop_source:string; status:string; started_at?:number; ended_at?:number; [key:string]:unknown};
type Archive = {run_tag:string; calls:Call[]; pipeline?:{status?:string}; note:string};
type Steps = {steps:Record<string,unknown>[]; next_offset:number|null};
async function read<T>(path:string, signal:AbortSignal):Promise<T>{
 const response=await fetch(path,{signal,cache:'no-store'});
 if(!response.ok)throw new Error(`Read failed (${response.status}). Retry when the read API is available.`);
 return response.json();
}
function JsonRecord({value,label}:{value:unknown;label:string}){
 return <details className="trace-json"><summary>{label}</summary><pre>{JSON.stringify(value,null,2)}</pre></details>;
}
function StoredStep({record}:{record:Record<string,unknown>}){
 const raw=record.tool_call;
 let parsed:unknown=raw;
 if(typeof raw==='string'){try{parsed=JSON.parse(raw);}catch{/* Keep the original field below. */}}
 const object=parsed&&typeof parsed==='object'?parsed as Record<string,unknown>:null;
 const tools=object?(Array.isArray(object.calls)?object.calls:[object]):[];
 return <><div className="record-flow"><div>Recorded input</div><span>↓</span>{tools.length?tools.map((value,i)=>{
  const tool=value&&typeof value==='object'?value as Record<string,unknown>:{};
  return <section key={i}><b>{String(tool.tool??tool.name??'Stored tool call')}</b><small>{String(tool.server??'')}</small><JsonRecord label="Arguments" value={tool.arguments??null}/><JsonRecord label="Tool result" value={tool.result??null}/></section>;
 }):<div>Recorded model / agent step</div>}<span>↓</span><div>Recorded output</div></div>
 <p className="muted">Tool cards preserve stored batch order; the arrows indicate input/output, not timing or a dependency between parallel calls. Missing fields mean unrecorded evidence.</p>
 {Object.entries(record).map(([key,value])=><JsonRecord key={key} label={key} value={value}/>)}</>;
}
function StepReader({tag,call}:{tag:string;call:Call}){
 const [offset,setOffset]=useState(0),[selected,setSelected]=useState<number|null>(null);
 const [page,setPage]=useState<Steps|null>(null),[detail,setDetail]=useState<Steps|null>(null),[error,setError]=useState('');
 const [retry,setRetry]=useState(0);
 useEffect(()=>{const controller=new AbortController();
  read<Steps>(`/api/developer/steps?run_tag=${encodeURIComponent(tag)}&run_id=${encodeURIComponent(call.run_id!)}&offset=${offset}`,controller.signal).then(data=>{if(!controller.signal.aborted)setPage(data);}).catch(e=>{if(!controller.signal.aborted)setError(String(e));});
  return()=>controller.abort();
 },[tag,call.run_id,offset,retry]);
 useEffect(()=>{if(selected===null)return;const controller=new AbortController();
  read<Steps>(`/api/developer/steps?run_tag=${encodeURIComponent(tag)}&run_id=${encodeURIComponent(call.run_id!)}&offset=${selected}&detail=true`,controller.signal).then(data=>{if(!controller.signal.aborted)setDetail(data);}).catch(e=>{if(!controller.signal.aborted)setError(String(e));});
  return()=>controller.abort();
 },[tag,call.run_id,selected,retry]);
 return <section className="call-detail"><h3>{call.stage} · invocation {call.seq}</h3><code>{call.run_id}</code><div className="trace-toolbar"><button onClick={()=>{setError('');setPage(null);setDetail(null);setRetry(n=>n+1);}}>Refresh stored steps</button></div><JsonRecord label="Invocation input, configuration and recorded outcome" value={call}/>
  <p className="muted">Steps below follow the stored sequence within this invocation, not a guessed stage order. Select a step to load its complete stored fields, including tool arguments/results and model metadata where recorded.</p>
  {error&&<p role="alert">{error} <button onClick={()=>{setError('');setRetry(n=>n+1);}}>Retry trace read</button></p>}
  {!page&&!error&&<p role="status">Loading stored steps…</p>}
  {page&&<><div className="step-list">{page.steps.map((step,i)=><button key={String(step.id)} aria-pressed={selected===offset+i} onClick={()=>{setDetail(null);setSelected(offset+i);setError('');}}>Step {offset+i+1} · {String(step.phase??'phase unavailable')}<small>Sequence {String(step.sequence??'unavailable')} · iteration {String(step.iteration??'unavailable')}</small><small>{String(step.started_at??'Timestamp unavailable')}</small></button>)}</div>{page.steps.length===0&&<p>No stored steps are available for this invocation.</p>}
  <div className="trace-pagination"><button disabled={offset===0} onClick={()=>{setPage(null);setSelected(null);setDetail(null);setOffset(Math.max(0,offset-50));}}>Previous steps</button><button disabled={page.next_offset===null} onClick={()=>{setPage(null);setSelected(null);setDetail(null);setOffset(page.next_offset!);}}>Next steps</button></div></>}
  {selected!==null&&!detail&&!error&&<p role="status">Loading step payload…</p>}
  {detail&&<div className="step-payload"><h4>Stored step {selected!+1}</h4>{detail.steps.length===0?<p>This step is unavailable.</p>:<StoredStep record={detail.steps[0]}/>}</div>}
 </section>;
}
function ExecutionReader({tag,loop}:{tag:string;loop:string}){
 const [archive,setArchive]=useState<Archive|null>(null),[error,setError]=useState(''),[selected,setSelected]=useState<string|null>(null);
 const [refresh,setRefresh]=useState(0),[auto,setAuto]=useState(false),[at,setAt]=useState('');
 useEffect(()=>{const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
  async function poll(){try{const data=await read<Archive>(`/api/developer/execution?run_tag=${encodeURIComponent(tag)}${loop?'&loop='+loop:''}`,controller.signal);if(controller.signal.aborted)return;setArchive(data);setError('');setAt(new Date().toLocaleTimeString());}catch(e){if(!controller.signal.aborted)setError(String(e));}finally{if(auto&&!controller.signal.aborted)timer=setTimeout(poll,3000);}}
  void poll();return()=>{controller.abort();clearTimeout(timer);};
 },[tag,loop,auto,refresh]);
 const current=archive?.calls.find(c=>c.run_id===selected);
 return <section className="execution-reader"><div className="trace-toolbar"><button onClick={()=>setRefresh(n=>n+1)}>Refresh execution</button><label><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/> Refresh every 3 seconds</label></div>
  {error&&<p role="alert">{error} {archive?'Previously loaded records are retained; they may be stale.':''}</p>}
  {!archive&&!error&&<p role="status">Loading execution archive…</p>}
  {archive&&<><p className="muted">Loaded {at} · Recorded pipeline status: {archive.pipeline?.status??'unavailable'}. This archive does not establish process liveness. An unfinished call is not proof that it is still running.</p><p>{archive.note}</p>
   <ol className="invocation-list">{archive.calls.map((c,i)=><li key={`${c.run_id}-${i}`}><button disabled={!c.run_id} aria-pressed={selected===c.run_id} onClick={()=>setSelected(c.run_id!)}><span className="trace-status">{c.status}</span><b>{c.stage}</b><small>Loop {c.loop??'unassigned'} · {c.loop_source} · call {c.seq}</small><code>{c.run_id??'No invocation ID'}</code><small>{c.started_at?new Date(c.started_at*1000).toLocaleString():'No start timestamp'}</small></button></li>)}</ol>
   {archive.calls.length===0&&<p>No invocations were recorded for this scope.</p>}
   {current&&<StepReader key={current.run_id} tag={tag} call={current}/>}
  </>}
 </section>;
}
export default function PipelineExplorer({onSource,initialView='map'}:{onSource:(path:string)=>void;initialView?:'map'|'execution'}){
 const [view,setView]=useState<'map'|'execution'>(initialView),[selected,setSelected]=useState('launch');
 const [runs,setRuns]=useState<RunSummary[]>([]),[runError,setRunError]=useState(''),[loaded,setLoaded]=useState(false);
 const [tag,setTag]=useState(''),[loop,setLoop]=useState('');
 const [load,setLoad]=useState(0);
 useEffect(()=>{if(!load)return;const controller=new AbortController();
  read<{runs:RunSummary[]}>('/api/runs',controller.signal).then(data=>{setRuns(data.runs);setLoaded(true);setRunError('');}).catch(e=>{if(!controller.signal.aborted)setRunError(String(e));});return()=>controller.abort();
 },[load]);
 const current=pipelineSteps.find(s=>s.id===selected)!;
 const graph=useMemo(()=>({nodes:pipelineSteps.map((s,i)=>({id:s.id,position:i<14?{x:(i%2)*330,y:Math.floor(i/2)*130}:{x:680,y:(i-14)*300+150},sourcePosition:Position.Bottom,targetPosition:Position.Top,data:{label:<><b>{String(i+1).padStart(2,'0')} · {s.title}</b><span>{s.owner}</span></>},className:`atlas-node ${s.id===selected?'selected':''}`})),edges:pipelineLinks.map(([source,target,label],i)=>({id:String(i),source,target,label:label==='handoff'?'':label,type:'smoothstep',markerEnd:{type:MarkerType.ArrowClosed},style:{stroke:label==='handoff'?'#69dbc2':'#cfab77',strokeDasharray:label==='handoff'?undefined:'5 5'},labelStyle:{fill:'#e7d8bb',fontSize:10},labelBgStyle:{fill:'#182639'}}))}),[selected]);
 return <div className="pipeline-explorer"><p className="eyebrow">04 / PIPELINE INTERNALS</p><h2>Follow every recorded handoff.</h2><div className="journey-tabs"><button aria-pressed={view==='map'} onClick={()=>setView('map')}>Execution blueprint</button><button aria-pressed={view==='execution'} onClick={()=>setView('execution')}>Inspect an execution</button></div>
  {view==='map'?<><p className="muted">Source-reviewed guide for this checkout's board pipeline. Solid arrows: logical handoffs; dashed arrows: conditional paths. These are not timing or measured invocation edges. Independent tasks may overlap. Pause/end applies across phases.</p><div className="pipeline-canvas"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={.15} maxZoom={1.5} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_,n)=>setSelected(n.id)} colorMode="dark" proOptions={{hideAttribution:true}}><Background gap={24}/><Controls showInteractive={false}/></ReactFlow></div>
   <label className="step-picker">Inspect a phase<select aria-label="Pipeline phase" value={selected} onChange={e=>setSelected(e.target.value)}>{pipelineSteps.map((s,i)=><option key={s.id} value={s.id}>{i+1}. {s.title}</option>)}</select></label>
   <article className="phase-detail"><p className="eyebrow">{current.owner}</p><h3>{current.title}</h3><div className="phase-io"><div><h4>Input</h4><p>{current.input}</p></div><div><h4>Output / handoff</h4><p>{current.output}</p></div></div><h4>What happens inside</h4><p>{current.detail}</p><h4>Implementation sources</h4>{current.sources.map(path=><button className="connection" key={path} onClick={()=>onSource(path)}>{path} ↗</button>)}<p className="muted">For individual LLM/tool turns, choose Inspect an execution. The blueprint cannot prove which conditional path a particular run took.</p></article></>:<><p className="muted">Read-only inspection. Loading this view does not start a pipeline or call a model. Load executions, select one and optionally narrow to a loop. Call order is archive order; timestamps may overlap.</p><button className="trace-load" onClick={()=>setLoad(n=>n+1)}>Load executions</button>{runError&&<p role="alert">{runError}</p>}
   {loaded&&<div className="trace-toolbar"><label>Execution<select aria-label="Execution archive" value={tag} onChange={e=>setTag(e.target.value)}><option value="">Choose an execution</option>{runs.map(r=><option key={r.run_tag} value={r.run_tag}>{r.run_tag}</option>)}</select></label><label>Loop (blank = all)<input aria-label="Execution loop" type="number" min="1" step="1" value={loop} onChange={e=>setLoop(e.target.value&&Number(e.target.value)>=1&&Number.isInteger(Number(e.target.value))?String(Number(e.target.value)):'')}/></label></div>}
   {loaded&&!runs.length&&<p>No executions are available.</p>}{tag&&<ExecutionReader key={`${tag}:${loop}`} tag={tag} loop={loop}/>}
  </>}
 </div>;
}
