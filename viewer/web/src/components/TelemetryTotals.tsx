import {useLoopLabel} from '../lib/useLoopLabel';
import type {ReplicateIdentity} from '../lib/replicateIdentity';
import {controlResponse} from '../lib/controlResponse';
import LoopUsage from "./LoopUsage";
import CostEvidence from './CostEvidence';
import { costLabel, usageDuration } from "../lib/loopUsage";
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Activity, AlertCircle, Clock3, Coins, Database, GitCompareArrows, Layers3, LoaderCircle, ReceiptText } from 'lucide-react';
import { usePipelines } from '../store/pipelines';

export type Metric = {calls:number;tokens:number;tokens_status?:string;cost:{usd:number;status:string;missing_costs:number};seconds?:number|null;duration_basis?:string;duration_status?:string;status?:string;attribution?:string};
export type Distribution = {mean:number;median:number;min:number;max:number};
export type LoopSummary = {sample_count:number;completed_count:number;excluded_completed:number;other_loops:number;seconds:Distribution|null;usd:Distribution|null;tokens:Distribution|null;basis:string};
export type ExecutionUsage = Metric & {run_tag:string;pipeline_id:string;model?:string;provider?:string;loops:(Metric&ReplicateIdentity&{number:number})[];loop_summary:LoopSummary;unassigned:Metric};
export type Totals = {scope:string;updated_at:string;total:Metric;pipelines:(Metric&{id:string;name:string;executions:number})[];executions:ExecutionUsage[];loop_summary:LoopSummary};
export function useTelemetryTotals(){
  const [data,setData]=useState<Totals|null>(null);const [error,setError]=useState('');
  const [revision,setRevision]=useState(0),[refreshing,setRefreshing]=useState(false);
  const refresh=useCallback(()=>setRevision(n=>n+1),[]);
  useEffect(()=>{let disposed=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
    const poll=async()=>{controller=new AbortController();setRefreshing(true);const deadline=setTimeout(()=>controller.abort(),6500);
      try{const r=await fetch('/api/telemetry/totals',{signal:controller.signal});const body=await controlResponse(r);if(!r.ok)throw Error(body.detail||'Totals unavailable');if(!disposed){setData(body);setError('');}}
      catch(e){if(!disposed)setError(e instanceof Error?e.message:'Totals unavailable');}
      finally{clearTimeout(deadline);if(!disposed){setRefreshing(false);timer=setTimeout(poll,6000);}}};
    void poll();return()=>{disposed=true;clearTimeout(timer);controller?.abort();};},[revision]);
  return {data,error,refresh,refreshing};
}
export function TelemetryState({title,loading=false,children}:{title:string;loading?:boolean;children:ReactNode}){
  const Icon=loading?LoaderCircle:Activity;
  return <div className="tm-empty" role="status"><span className="tm-empty-icon"><Icon size={23} aria-hidden="true" className={loading?'tm-loading':undefined}/></span><h3>{title}</h3><p>{children}</p></div>;
}
export function UsageCards({metric}:{metric:Metric}){
  const cards=[
    {label:'Agent executions',value:metric.calls.toLocaleString()},
    {label:'Tokens',value:metric.tokens_status==='unavailable'?'Not available':`${metric.tokens.toLocaleString()}${metric.tokens_status==='partial'?' · partial':''}`},
    {label:'Estimated cost',value:costLabel(metric.cost),note:metric.cost.missing_costs?`Pricing unavailable for ${metric.cost.missing_costs} agent executions`:metric.cost.status==='partial'?'Incomplete · recorded subtotal only':undefined},
    ...(metric.duration_basis?[{label:'Recorded elapsed time',value:usageDuration(metric.seconds),note:metric.duration_basis}]:[]),
  ];
  return <dl className="usage-metric-cards tm-summary-cards">{cards.map(({label,value,note})=><div key={label}><dt>{label}</dt><dd>{value}</dd>{note&&<p>{note}</p>}</div>)}</dl>;
}
export default function TelemetryTotals({data,error,runTag,loop,onRetry,refreshRevision=0,scopedOnly=false}:{data:Totals|null;error:string;runTag:string|null;loop:number|null;onRetry?:()=>void;refreshRevision?:number;scopedOnly?:boolean}){
 const labelReplicate=useLoopLabel();
  const [evidenceOpen,setEvidenceOpen]=useState(false);
  const current=usePipelines(s=>s.items.find(p=>p.running?.run_tag===runTag));
  const execution=data?.executions.find(e=>e.run_tag===runTag);
  const metric=loop===null?execution:execution?.loops.find(l=>l.number===loop);
  const cost=metric?costLabel(metric.cost):'';
  const subtotal=cost.endsWith(' · recorded subtotal');
  const running=current?`${current.running?.pause_requested?'Pausing / paused':'Running'}${current.progress.iteration?` · ${labelReplicate({iteration:current.progress.iteration,run_tag:runTag})}`:''}${current.progress.stage?` · ${current.progress.stage}`:''}`:null;
  return <section className="telemetry-overview" aria-label="Usage totals">
    <header className="tm-section-heading"><div><h3>{loop===null?'Execution overview':`${labelReplicate({iteration:loop,run_tag:runTag})} overview`}</h3><p>{running??'Time and usage for the selected execution.'}</p></div><span className="tm-scope-badge">{loop===null?'All replicates':labelReplicate({iteration:loop,run_tag:runTag})}</span></header>
    {error&&<div className="tm-notice" role="status"><AlertCircle size={16} aria-hidden="true"/><p>Updates are delayed. {data?'Last available measurements are shown.':'Waiting for measurements; missing values are not zero.'}</p>{onRetry&&<button type="button" className="tm-button" onClick={onRetry}>Retry</button>}</div>}
    {!runTag?<TelemetryState title="Choose an execution">Select a pipeline with a recorded execution to view its time and usage.</TelemetryState>:!data?<TelemetryState loading={!error} title={error?'Measurements are temporarily unavailable':'Loading measurements'}>{error?'Retry above, or wait for the next automatic update.':'Retrieving recorded time and usage from this workspace.'}</TelemetryState>:!metric?<TelemetryState title="No measurements yet">No usage has been recorded for this selection. Measurements will appear as records become available.</TelemetryState>:<>
      <dl className="telemetry-key-metrics">
        <div><dt><Clock3 size={16} aria-hidden="true"/>Elapsed time</dt><dd>{usageDuration(metric.seconds)}</dd><p>{loop===null?'Recorded agent span':'Recorded replicate span'}{metric.duration_status==='partial'&&metric.seconds!=null?' · partial':''}</p></div>
        <div data-partial={subtotal}><dt><Coins size={16} aria-hidden="true"/>Estimated cost</dt><dd>{subtotal?cost.slice(0,-' · recorded subtotal'.length):cost}</dd><p>{subtotal?'Recorded subtotal · incomplete':cost==='Not available'?'No complete pricing available':'USD · Motoro estimate'}</p></div>
        <div><dt><Database size={16} aria-hidden="true"/>Tokens</dt><dd>{metric.tokens_status==='unavailable'?'Not available':metric.tokens.toLocaleString()}</dd><p>{metric.tokens_status==='partial'?'Partial usage recorded':metric.tokens_status==='unavailable'?'Usage not available':'Recorded input + output'}</p></div>
        <div><dt><Layers3 size={16} aria-hidden="true"/>Agent executions</dt><dd>{metric.calls.toLocaleString()}</dd><p>Distinct Motoro executions</p></div>
      </dl>
      <p className="telemetry-usage-note">Cost is a Motoro estimate, not an actual charge.{metric.cost.missing_costs>0?` Pricing is missing for ${metric.cost.missing_costs} agent executions.`:''}{metric.cost.status==='partial'?' Incomplete estimates show only the recorded subtotal.':''}</p>
      <details className="telemetry-disclosure" onToggle={e=>setEvidenceOpen(e.currentTarget.open)}><summary><span><ReceiptText size={17} aria-hidden="true"/>Usage & cost details</span><small>Sources & request records</small></summary><div>
        <dl className="tm-evidence-metadata"><div><dt>Model</dt><dd>{execution?.model||'Not recorded'}</dd></div><div><dt>Provider</dt><dd>{execution?.provider||'Not recorded'}</dd></div></dl>
        {metric.duration_basis&&<div className="tm-method-note"><strong>How elapsed time is measured</strong><p>{metric.duration_basis}</p></div>}
        {evidenceOpen&&<CostEvidence key={`${runTag}:${loop}`} runTag={runTag} loop={loop} refreshRevision={refreshRevision}/>}
        <p className="telemetry-usage-note">Overview sums distinct Motoro agent execution records for the selected scope. Request details use saved LLM requests in that same scope. Elapsed time is a span, not the sum of parallel durations.</p>
      </div></details>
    </>}
    {!scopedOnly&&execution&&<details className="telemetry-disclosure"><summary><span><GitCompareArrows size={17} aria-hidden="true"/>Compare replicates</span><small>{execution.loops.length} recorded</small></summary><div><LoopUsage execution={execution} updatedAt={data?.updated_at}/></div></details>}
    {!scopedOnly&&data&&<details className="telemetry-disclosure"><summary><span><Layers3 size={17} aria-hidden="true"/>All pipelines</span><small>{data.pipelines.length} pipelines</small></summary><div>
      <p className="telemetry-usage-note">All saved executions · {data.scope}</p><UsageCards metric={data.total}/>
      <div className="tm-table-scroll" role="region" aria-label="All pipeline usage; scroll horizontally for more columns" tabIndex={0}><table className="tm-table"><caption className="sr-only">Usage across all saved pipeline executions</caption><thead><tr><th>Pipeline</th><th className="tm-number">Agent executions</th><th className="tm-number">Estimated cost</th></tr></thead><tbody>{data.pipelines.map(p=><tr key={p.id}><td><button className="tm-text-button" onClick={()=>usePipelines.getState().select(p.id)}>{p.name}</button><small>{p.executions} saved executions</small></td><td className="tm-number">{p.calls.toLocaleString()}</td><td className="tm-number">{costLabel(p.cost)}{p.cost.missing_costs>0&&<small>{p.cost.missing_costs} unpriced agent executions</small>}</td></tr>)}</tbody></table>{!data.pipelines.length&&<p className="telemetry-usage-note">No saved pipeline usage yet.</p>}</div>
    </div></details>}
  </section>;
}
