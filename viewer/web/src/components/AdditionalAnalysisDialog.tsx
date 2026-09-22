import { useState } from 'react';
import { Plus, Play } from 'lucide-react';
import FloorDetailDialog from './FloorDetailDialog';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';

export default function AdditionalAnalysisDialog({pipeline:p,close,fresh=false}:{pipeline:PipelineDefinition;close:()=>void;fresh?:boolean}) {
  const [loops,setLoops]=useState('5');
  // Pin the reviewed execution so a second tab cannot silently start against a new one.
  const [expectedRunTag]=useState(p.latest?.run_tag??'');
  const busy=usePipelines(s=>s.busy),error=usePipelines(s=>s.error);
  const count=Number(loops),valid=loops.trim()!==''&&Number.isInteger(count)&&count>=1&&count<=10;
  const total=p.loop_totals;
  const prior=total && total.unknown_executions===0 ? total.attempted : undefined;
  const changed=p.latest?.run_tag!==expectedRunTag||!!p.running;
  const start=async()=>{if(changed||(!fresh&&!valid))return;
    if(await usePipelines.getState().play(p.id,{mode:fresh?'fresh':'additional',loops:fresh?undefined:count,expectedRunTag}))close();};
  return <FloorDetailDialog title={fresh?'Start a new execution':'Additional analysis'} close={()=>{if(!busy)close();}} className="pipeline-management-dialog">
    <div className="pipeline-management">
      <div className="pipeline-management-identity"><span>Pipeline {p.number}</span><h3>{p.name}</h3></div>
      {fresh?<section><h3>A new execution with your saved settings</h3><p>This starts up to {p.configuration.waves} Loops, beginning at Loop 1. Existing results remain saved. This does not clear the pipeline’s research history.</p></section>:<section>
        <h3>How many more Loops?</h3><p>Run more analysis with this pipeline’s current settings. Each Loop generates and evaluates a research hypothesis.</p>
        <label className="block mt-4 text-sm font-semibold" htmlFor="additional-loop-count">Additional Loops</label>
        <input id="additional-loop-count" type="number" min={1} max={10} step={1} value={loops} onChange={e=>setLoops(e.target.value)} disabled={busy} aria-describedby="additional-loop-help" className="mt-2 w-full rounded-lg border border-paper-line bg-paper p-3 text-lg"/>
        <p id="additional-loop-help">Choose 1–10. Only this many extra Loops may run; the pipeline stops at that limit.</p>
        <div className="pipeline-management-confirm" role="status"><strong>{prior===undefined?'Previous total unavailable':`${prior} previous Loops`} + {valid?count:'—'} additional{prior!==undefined&&valid?` → up to ${prior+count} total`:''}</strong><p>Previous Loops include blocked attempts. Additional analysis is saved as a separate execution with its own Loop numbers; existing results stay available.</p></div>
      </section>}
      <p className="text-sm text-ink-soft">New analysis uses model tokens and may incur additional cost. You can pause it from the pipeline list.</p>
      {changed&&<p role="alert">This pipeline’s execution changed. Close this window and review its current state.</p>}
      {error&&<p role="alert">{error}</p>}
      <div className="pipeline-management-buttons"><button disabled={busy} onClick={close}>Cancel</button><button disabled={busy||changed||(!fresh&&!valid)} onClick={()=>void start()}>{fresh?<Play size={16}/>:<Plus size={16}/>} {busy?'Starting…':fresh?'Start new execution':`Run ${valid?count:'…'} additional Loops`}</button></div>
    </div>
  </FloorDetailDialog>;
}
