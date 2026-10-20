import {controlResponse} from '../lib/controlResponse';
import LoopUsage from "./LoopUsage";
import CostEvidence from './CostEvidence';
import { costLabel, usageDuration } from "../lib/loopUsage";
import { useEffect, useState } from 'react';
import { usePipelines } from '../store/pipelines';

export type Metric = {calls:number;tokens:number;tokens_status?:string;cost:{usd:number;status:string;missing_costs:number};seconds?:number|null;duration_basis?:string;duration_status?:string;status?:string;attribution?:string};
export type Distribution = {mean:number;median:number;min:number;max:number};
export type LoopSummary = {sample_count:number;completed_count:number;excluded_completed:number;other_loops:number;seconds:Distribution|null;usd:Distribution|null;tokens:Distribution|null;basis:string};
export type ExecutionUsage = Metric & {run_tag:string;pipeline_id:string;model?:string;provider?:string;loops:(Metric&{number:number})[];loop_summary:LoopSummary;unassigned:Metric};
export type Totals = {scope:string;updated_at:string;total:Metric;pipelines:(Metric&{id:string;name:string;executions:number})[];executions:ExecutionUsage[];loop_summary:LoopSummary};
export function useTelemetryTotals(){
  const [data,setData]=useState<Totals|null>(null);const [error,setError]=useState('');
  useEffect(()=>{let disposed=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
    const poll=async()=>{controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),6500);
      try{const r=await fetch('/api/telemetry/totals',{signal:controller.signal});const body=await controlResponse(r);if(!r.ok)throw Error(body.detail||'Totals unavailable');if(!disposed){setData(body);setError('');}}
      catch(e){if(!disposed)setError(e instanceof Error?e.message:'Totals unavailable');}
      finally{clearTimeout(deadline);if(!disposed)timer=setTimeout(poll,6000);}};
    void poll();return()=>{disposed=true;clearTimeout(timer);controller?.abort();};},[]);
  return {data,error};
}
export function UsageCards({metric}:{metric:Metric}){
  const cards=[
    {label:'Agent calls',value:metric.calls.toLocaleString()},
    {label:'Tokens',value:`${metric.tokens.toLocaleString()}${metric.tokens_status==='partial'?' · partial':''}`},
    {label:'Estimated cost',value:costLabel(metric.cost),note:metric.cost.missing_costs?`Pricing unavailable for ${metric.cost.missing_costs} calls`:metric.cost.status==='partial'?'Incomplete · recorded subtotal only':undefined},
    ...(metric.duration_basis?[{label:'End-to-end time',value:usageDuration(metric.seconds),note:metric.duration_basis}]:[]),
  ];
  return <dl className="usage-metric-cards">{cards.map(({label,value,note})=><div key={label} className="min-w-0 rounded-lg border border-paper-line bg-paper p-3"><dt className="text-xs text-ink-soft">{label}</dt><dd className="mt-1 break-words text-lg font-bold text-ink">{value}</dd>{note&&<p className="mt-1 break-words text-xs leading-5 text-ink-soft">{note}</p>}</div>)}</dl>;
}
export default function TelemetryTotals({data,error,runTag,loop}:{data:Totals|null;error:string;runTag:string|null;loop:number|null}){
  const current=usePipelines(s=>s.items.find(p=>p.running?.run_tag===runTag));
  const execution=data?.executions.find(e=>e.run_tag===runTag);
  const metric=loop===null?execution:execution?.loops.find(l=>l.number===loop);
  return <section className="telemetry-overview" aria-label="Telemetry totals">
    <header><h3>{loop===null?'Execution overview':`Loop ${loop}`}</h3><p>{current?`${current.running?.pause_requested?'Pausing / paused':'Running'}${current.progress.iteration?` · Loop ${current.progress.iteration}`:''}${current.progress.stage?` · ${current.progress.stage}`:''}`:'Time and usage for the selected execution.'}</p></header>
    {error&&<p role="status">Updates are delayed. {data?'Last available measurements are shown.':'Waiting for measurements; missing values are not zero.'}</p>}
    {!runTag?<p>Choose a pipeline with a recorded execution.</p>:!data?<p role="status">Loading measurements…</p>:!metric?<p>No usage recorded for this selection yet.</p>:<>
      <dl className="telemetry-key-metrics">
        <div><dt>{loop===null?'Elapsed time · recorded agent span':'Elapsed time'}</dt><dd>{usageDuration(metric.seconds)}{metric.duration_status==='partial'&&metric.seconds!=null?' · partial':''}</dd></div>
        <div><dt>Estimated cost</dt><dd>{costLabel(metric.cost)}</dd></div>
        <div><dt>Agent calls</dt><dd>{metric.calls.toLocaleString()}</dd></div>
      </dl>
      {metric.duration_basis&&<p className="telemetry-usage-note">{metric.duration_basis}</p>}
      <p className="telemetry-usage-note">Cost is a Motoro estimate, not an actual charge.{metric.cost.missing_costs>0?` ${metric.cost.missing_costs} calls have no pricing; the estimate is incomplete.`:''}{metric.cost.status==='partial'?' Only the recorded subtotal is available.':''}</p>
      <details className="telemetry-disclosure"><summary>Usage & billing details</summary><div>
        <p>{metric.tokens.toLocaleString()} tokens{metric.tokens_status==='partial'?' · partial usage':''}{execution?.model?` · ${execution.model}`:''}</p>
        {metric.duration_basis&&<p>{metric.duration_basis}</p>}
        <CostEvidence runTag={runTag}/>
        <p className="text-xs text-ink-soft">Billing evidence covers the scope stated in that record; it is not automatically attributable to the selected Loop. Parallel agent durations are not added to calculate elapsed time.</p>
      </div></details>
    </>}
    {execution&&<details className="telemetry-disclosure"><summary>Compare loops <span>{execution.loops.length} recorded</span></summary><div><LoopUsage execution={execution} updatedAt={data?.updated_at}/></div></details>}
    {data&&<details className="telemetry-disclosure"><summary>All pipelines <span>{data.pipelines.length} pipelines</span></summary><div>
      <p className="text-sm text-ink-soft">All saved executions · {data.scope}</p><UsageCards metric={data.total}/>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Usage across all saved pipeline executions</caption><thead><tr>{['Pipeline','Calls','Estimated cost'].map(t=><th key={t} className="p-2">{t}</th>)}</tr></thead><tbody>{data.pipelines.map(p=><tr key={p.id} className="border-t border-paper-line"><td className="p-2"><button className="text-accent underline" onClick={()=>usePipelines.getState().select(p.id)}>{p.name}</button></td><td className="p-2">{p.calls}</td><td className="p-2">{costLabel(p.cost)}{p.cost.missing_costs>0&&<small className="block">{p.cost.missing_costs} unpriced calls</small>}</td></tr>)}</tbody></table></div>
    </div></details>}
    {data&&<p className="telemetry-updated">Updated {new Date(data.updated_at).toLocaleTimeString()} · refreshes automatically</p>}
  </section>;
}
