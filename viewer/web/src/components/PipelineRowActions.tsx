import { useState } from 'react';
import { Play, Pause } from 'lucide-react';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';
import PipelineRetryDialog from './PipelineRetryDialog';
import AdditionalAnalysisDialog from './AdditionalAnalysisDialog';

export default function PipelineRowActions({pipeline:p,compact=false}:{pipeline:PipelineDefinition;compact?:boolean}) {
  const busy=usePipelines(s=>s.busy);
  const pendingStart=usePipelines(s=>s.pendingStart);
  const checkingStart=pendingStart?.pipelineId===p.id;
  const [additionalOpen,setAdditionalOpen]=useState(false);
  const [retryOpen,setRetryOpen]=useState(false);
  const paused=!!p.running&&(p.running.pause_requested||p.running.execution_state==='paused'||p.running.execution_state==='stopping');
  const combinations=!!p.configuration.combination_skills&&Object.keys(p.configuration.combination_skills).length>0;
  const recoverable=!p.running&&!!p.latest?.recoverable;
  const failed=!p.running&&!!p.latest&&!!p.failure&&!recoverable;
  const retryable=failed&&Number.isInteger(p.failure?.loop)&&Number(p.failure?.loop)>0;
  const action=retryable?'Retry remaining replicates':paused?'Resume':p.running?'Pause':recoverable?'Resume from checkpoint':p.latest?(combinations?'Run combinations again':'Additional analysis'):'Run';
  const finished=!p.running&&!!p.latest;
  return <div className={`pipeline-row-actions ${compact?"is-compact":""}`} role="group" aria-label={`Actions for ${p.name}`}>
    <button className="pipeline-row-primary" disabled={busy||checkingStart||!!pendingStart&&!p.running} aria-label={`${checkingStart?'Checking start':action} ${p.name}`} onClick={()=>{if(retryable){setRetryOpen(true);return;}if(finished&&!recoverable){setAdditionalOpen(true);return;}void(paused||recoverable?usePipelines.getState().pause(p.id,false):p.running?usePipelines.getState().stop(p.id):usePipelines.getState().play(p.id));}}>{action==='Pause'?<Pause size={15}/>:<Play size={15}/>} {checkingStart?'Checking start…':action}</button>
    {failed&&!retryable&&<span className="text-xs text-ink-soft" role="status">Retry unavailable: the failed replicate is not identified.</span>}
    {retryOpen&&<PipelineRetryDialog pipeline={p} close={()=>setRetryOpen(false)}/>}
    {additionalOpen&&<AdditionalAnalysisDialog pipeline={p} fresh={combinations} close={()=>setAdditionalOpen(false)}/>}
  </div>;
}
