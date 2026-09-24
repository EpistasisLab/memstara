import LoopUsage from "./LoopUsage";
import { usageDuration } from "../lib/loopUsage";
import { useEffect, useState } from 'react';
import { usePipelines } from '../store/pipelines';

export type Metric = {calls:number;tokens:number;tokens_status?:string;cost:{usd:number;status:string;missing_costs:number};seconds?:number|null;duration_basis?:string;status?:string;attribution?:string};
export type Distribution = {mean:number;median:number;min:number;max:number};
export type LoopSummary = {sample_count:number;completed_count:number;excluded_completed:number;other_loops:number;seconds:Distribution|null;usd:Distribution|null;tokens:Distribution|null;basis:string};
export type ExecutionUsage = Metric & {run_tag:string;pipeline_id:string;model?:string;provider?:string;loops:(Metric&{number:number})[];loop_summary:LoopSummary;unassigned:Metric};
export type Totals = {scope:string;updated_at:string;total:Metric;pipelines:(Metric&{id:string;name:string;executions:number})[];executions:ExecutionUsage[];loop_summary:LoopSummary};
export function useTelemetryTotals(){
  const [data,setData]=useState<Totals|null>(null);const [error,setError]=useState('');
  useEffect(()=>{let disposed=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
    const poll=async()=>{controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),6500);
      try{const r=await fetch('/api/telemetry/totals',{signal:controller.signal});const body=await r.json();if(!r.ok)throw Error(body.detail||'Totals unavailable');if(!disposed){setData(body);setError('');}}
      catch(e){if(!disposed)setError(e instanceof Error?e.message:'Totals unavailable');}
      finally{clearTimeout(deadline);if(!disposed)timer=setTimeout(poll,6000);}};
    void poll();return()=>{disposed=true;clearTimeout(timer);controller?.abort();};},[]);
  return {data,error};
}
export function UsageCards({metric}:{metric:Metric}){
  return <dl className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-4">{[
    ['Agent calls',metric.calls.toLocaleString()],['Tokens',`${metric.tokens.toLocaleString()}${metric.tokens_status==='partial'?' · partial':''}`],
    ['Estimated cost',`$${metric.cost.usd.toFixed(4)}${metric.cost.status==='complete'?'':' · partial'}`],
    ...(metric.duration_basis?[['End-to-end time',usageDuration(metric.seconds)]]:[]),
  ].map(([label,value])=><div key={label} className="min-w-0 rounded-lg border border-paper-line bg-paper p-3"><dt className="text-xs text-ink-soft">{label}</dt><dd className="mt-1 break-words text-lg font-bold text-ink">{value}{label==='End-to-end time'&&<p className="text-xs text-ink-faint">{metric.duration_basis}</p>}</dd></div>)}</dl>;
}
export default function TelemetryTotals({data,error,runTag,loop}:{data:Totals|null;error:string;runTag:string|null;loop:number|null}){
  const execution=data?.executions.find(e=>e.run_tag===runTag);
  const metric=loop===null?execution:execution?.loops.find(l=>l.number===loop);
  return <section className="space-y-4 p-3" aria-label="Telemetry totals">
    {error&&<p role="alert">{error}. {data?'Last available totals are shown.':'Totals are not assumed to be zero.'}</p>}
    {!data?<p>Loading totals…</p>:<>
      <h3 className="text-lg font-bold">All pipelines</h3><p className="text-sm text-ink-soft">{data.scope}. Calls are counted once by ID. Updated {new Date(data.updated_at).toLocaleTimeString()}.</p><UsageCards metric={data.total}/>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="pb-2 text-left font-bold">Totals for each pipeline · all saved executions</caption><thead><tr>{['Pipeline','Executions','Agent calls','Tokens','Estimated cost'].map(t=><th key={t} className="p-2">{t}</th>)}</tr></thead><tbody>{data.pipelines.map(p=><tr key={p.id} className="border-t border-paper-line"><td className="p-2"><button className="font-bold text-accent underline" onClick={()=>usePipelines.getState().select(p.id)}>{p.name}</button></td><td className="p-2">{p.executions}</td><td className="p-2">{p.calls}</td><td className="p-2">{p.tokens.toLocaleString()}{p.tokens_status==='partial'?' · partial':''}</td><td className="p-2">${p.cost.usd.toFixed(4)}{p.cost.status!=='complete'?' · partial':''}</td></tr>)}</tbody></table></div>
      <h3 className="font-bold">Selected execution · {loop===null?'All loops':`Loop ${loop}`}</h3>{metric?<UsageCards metric={metric}/>:<p>No matching usage record is available.</p>}
      {execution&&<div>
        <h3 className="font-bold">Execution-wide Loop comparison</h3>
        <p className="mt-1 text-sm text-ink-soft">The cards above follow your Loop selection. The comparison below covers every Loop in this execution, using the same measurements as Final report and Status.</p>
        <LoopUsage execution={execution} updatedAt={data.updated_at}/>
      </div>}
      <p className="text-xs text-ink-faint">Cost is recorded estimated usage, not an invoice. Agent-call durations may overlap; elapsed time is not the sum of parallel calls. Missing pricing is marked partial.</p>
    </>}
  </section>;
}
