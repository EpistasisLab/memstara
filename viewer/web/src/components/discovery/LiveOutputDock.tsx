import ContentOrigin from "../ContentOrigin";
import { loopLabel } from '../../lib/loopLabel';
import { pipelineLoopLabel } from "../../lib/pipelineProgress";
import { pipelineLabel } from '../../lib/pipelineLabel';
import { useState } from 'react';
import { Activity, ArrowUpRight } from 'lucide-react';
import { usePipelines } from '../../store/pipelines';
import { useLiveOutputs, type OutputEvent } from '../../store/liveOutputs';
import './live-outputs.css';
const labels:Record<string,string>={question:'Question',hypothesis:'Hypothesis',data:'Data',ml:'ML',interpretation:'Interpretation',report:'Explanation',result:'Finding'};
export default function LiveOutputDock({ clinical=false, compact=false, open }: { clinical?:boolean; compact?:boolean; open?:(event:OutputEvent)=>void }) {
  const live=useLiveOutputs();const pipelines=usePipelines(s=>s.items);const pipelineError=usePipelines(s=>s.error);
  const runningCount=pipelines.filter(p=>p.running).length;
  const [pipeline,setPipeline]=useState('all');const [expanded,setExpanded]=useState(false);
  const events=live.events.filter(e=>(pipeline==='all'||e.run_tag===pipeline)&&(!clinical||['result','interpretation','report'].includes(e.stage)));
  return <section className={`live-output-dock ${clinical?'clinical-output-dock':''} ${compact?'is-compact':''}`} aria-label={clinical?'Live clinical findings':'Live pipeline outputs'}>
    <header><div><Activity size={17}/><h2>{compact?'Pipeline activity':clinical?'Findings arriving now':'Across your pipelines'}</h2><span className={`live-connection ${live.error||pipelineError?'is-stale':''}`}>{live.error||pipelineError?'Updates interrupted':live.updatedAt?(pipelines.some(p=>p.running)?(compact?`${runningCount} ${runningCount===1?'pipeline':'pipelines'} running`:'Live · checks every 0.5s'):'Saved outputs · standing by'):'Connecting'}</span></div><button aria-expanded={expanded} onClick={()=>{setExpanded(v=>!v);live.acknowledge();}}>{live.pending>0?`${live.pending} new updates`:(expanded?'Hide outputs':compact?'Show outputs':'Received outputs')} <ArrowUpRight size={13}/></button></header>
    {(live.error||pipelineError)&&<p role="alert" className="live-error">{live.error||pipelineError}</p>}
    {(!compact||expanded)&&<>
    <div className="live-pipeline-strip"><button aria-pressed={pipeline==='all'} onClick={()=>setPipeline('all')}>All pipelines</button>{pipelines.map(p=><button key={p.id} disabled={!p.latest} aria-pressed={pipeline===p.latest?.run_tag} onClick={()=>setPipeline(p.latest?.run_tag||'all')}><i className={p.running?'is-running':''}/><strong>{p.name}</strong><span>{p.running?(p.progress.stage||'Running'):'Not running'}{p.progress.iteration!=null?` · ${pipelineLoopLabel(p)}`:''}</span></button>)}</div>
    <div className={`live-output-cards ${expanded?'is-expanded':''}`}>{events.slice(0,expanded?80:6).map(event=><button data-help="Recorded pipeline output" data-help-description="Open this recorded output and its linked evidence. The pipeline name, stage and loop identify where it came from; receiving it does not mean the hypothesis is validated." key={`${event.id}:${event.revision}`} className={event.fresh?'is-new':''} onClick={()=>open?.(event)} disabled={!open}><div><span>{pipelineLabel(event,pipelines)}</span><b>{labels[event.stage]||event.stage}</b>{event.fresh&&<em>NEW</em>}</div><ContentOrigin kind={event.stage === "data" && event.status !== "failed" ? "rule" : event.stage === "question" || event.stage === "hypothesis" || event.stage === "result" ? "proposal" : "mixed"} compact/><h3>{event.title}</h3><p>{event.detail.replace(/[#*_`]/g,'').slice(0,190)}</p><footer>{event.iteration!=null||event.trial!=null?loopLabel(event):'Run output'} · {event.fresh?`Received ${new Date(event.receivedAt).toLocaleTimeString()}`:'Previously recorded'}</footer></button>)}</div>
    {!events.length&&<p className="live-output-empty">{pipelines.some(p=>p.running)?'Waiting for the next recorded output. Each pipeline is observed independently.':'New outputs will appear here when a pipeline runs.'}</p>}
    <p className="live-output-footnote">{live.updatedAt?`Last synchronized ${new Date(live.updatedAt).toLocaleTimeString()}. `:''}New outputs accumulate without changing the finding you are reading. This session retains up to 500 output updates.</p>
    </>}
  </section>;
}
