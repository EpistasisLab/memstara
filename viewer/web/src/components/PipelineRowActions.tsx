import FloorDetailDialog from './FloorDetailDialog';
import { useState } from 'react';
import { Play, Pause, Settings2, ArrowUpRight } from 'lucide-react';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';
import AdditionalAnalysisDialog from './AdditionalAnalysisDialog';
import PipelineManagementDialog from './PipelineManagementDialog';

export default function PipelineRowActions({pipeline:p,onSettings,compact=false}:{pipeline:PipelineDefinition;onSettings:()=>void;compact?:boolean}) {
  const [detailsOpen,setDetailsOpen]=useState(false);
  const busy=usePipelines(s=>s.busy);
  const [settingsOpen,setSettingsOpen]=useState(false);
  const [additionalOpen,setAdditionalOpen]=useState(false);
  const paused=!!p.running&&(p.running.pause_requested||p.running.execution_state==='paused'||p.running.execution_state==='stopping');
  const combinations=!!p.configuration.combination_skills&&Object.keys(p.configuration.combination_skills).length>0;
  const recoverable=!p.running&&!!p.latest?.recoverable;
  const action=paused?'Resume':p.running?'Pause':recoverable?'Resume from checkpoint':p.latest?(combinations?'Run combinations again':'Additional analysis'):'Run';
  const executionConfig=(p.running??p.latest)?.configuration??(!p.latest?p.configuration:undefined);
  const finished=!p.running&&!!p.latest;
  const infrastructure=(p.running??p.latest)?.infrastructure_status;
  const exploration=p.progress.exploration;
  const completed=finished&&p.latest?.exit_code===0&&exploration?.outcome==='completed';
  return <div className={`pipeline-row-actions ${compact?"is-compact":""}`} role="group" aria-label={`Actions for ${p.name}`}>
    {!compact&&finished&&<div className="pipeline-execution-summary" role="status">
      <strong>{infrastructure?.status==='interrupted'?'Connection interrupted — results retained':recoverable?'Execution interrupted — checkpoint available':completed?'Execution completed':p.latest?.exit_code===0?'Execution ended':'Execution stopped — review results'}</strong>
      {exploration&&<span>{exploration.completed} Loops completed · {exploration.blocked} blocked</span>}
      {p.failure&&<span role="alert">{p.failure.message}</span>}
      {p.latest?.recovery_blocked&&<span>Automatic recovery requires review. See execution details.</span>}
    </div>}
    {!compact&&infrastructure&&<p className="pipeline-row-note" role="status">{infrastructure.message}</p>}
    <button className="pipeline-row-primary" disabled={busy} aria-label={`${action} ${p.name}`} onClick={()=>{if(finished&&!recoverable){setAdditionalOpen(true);return;}void(paused||recoverable?usePipelines.getState().pause(p.id,false):p.running?usePipelines.getState().stop(p.id):usePipelines.getState().play(p.id));}}>{action==='Pause'?<Pause size={15}/>:<Play size={15}/>} {action}</button>
    {!compact&&paused&&<p className="pipeline-row-note">{p.running?.execution_state==='paused'?'Paused — ready to resume.':'Pausing after the current agent call.'}</p>}
    {!compact&&<details className="pipeline-card-disclosure"><summary>Execution details</summary>
    <p className="pipeline-row-limit">{executionConfig?.continuous?'Continuous execution':`Maximum ${executionConfig?.waves??'—'} Loops per execution`}</p>
      {finished&&(recoverable?<p className="pipeline-row-note">Resume restores this execution from its saved checkpoint. Completed Loops and results are retained.</p>:<p className="pipeline-row-note">Results are saved. Additional analysis runs only the extra Loops you approve. Each execution retains its own Loop numbering.</p>)}
      {p.latest?.recovery_blocked&&<p className="pipeline-row-note">Automatic recovery is blocked: {p.latest.recovery_blocked}</p>}
      {p.running&&<p className="pipeline-row-note">Pause finishes the current agent call, then waits. Resume continues the same execution.</p>}
    </details>}
    {!compact&&p.loop_totals&&<p className="pipeline-row-note">{p.loop_totals.unknown_executions ? "Recorded total" : "Pipeline total"}: {p.loop_totals.attempted} Loops attempted</p>}
    {additionalOpen&&<AdditionalAnalysisDialog pipeline={p} fresh={combinations} close={()=>setAdditionalOpen(false)}/>}
    {compact&&<button className="pipeline-details-launch" aria-label={`Execution details for ${p.name}`} onClick={()=>setDetailsOpen(true)}>Details</button>}
    {detailsOpen&&<FloorDetailDialog title={`Execution details · ${p.name}`} close={()=>setDetailsOpen(false)}><PipelineRowActions pipeline={p} onSettings={onSettings}/></FloorDetailDialog>}
    <button className="pipeline-management-launch" aria-haspopup="dialog" aria-label={`Settings and more for ${p.name}`} onClick={()=>setSettingsOpen(true)}><Settings2 size={14}/><span>{compact?"Settings":"Settings and more"}</span><ArrowUpRight size={14}/></button>
    {settingsOpen&&<PipelineManagementDialog pipeline={p} onSettings={onSettings} close={()=>setSettingsOpen(false)}/>}
  </div>;
}
