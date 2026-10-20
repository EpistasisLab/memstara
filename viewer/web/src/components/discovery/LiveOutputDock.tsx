import ContentOrigin from "../ContentOrigin";
import { loopLabel } from '../../lib/loopLabel';
import { pipelineLoopLabel } from "../../lib/pipelineProgress";
import { pipelineLabel } from '../../lib/pipelineLabel';
import { useState } from 'react';
import { Activity, ArrowUpRight, ChevronDown } from 'lucide-react';
import { usePipelines } from '../../store/pipelines';
import { useLiveOutputs, type OutputEvent } from '../../store/liveOutputs';
import './live-outputs.css';
const labels:Record<string,string>={question:'Question',hypothesis:'Hypothesis',data:'Data',ml:'ML',interpretation:'Interpretation',report:'Explanation',result:'Finding'};
export default function LiveOutputDock({ clinical=false, compact=false, open }: { clinical?:boolean; compact?:boolean; open?:(event:OutputEvent)=>void }) {
  const live=useLiveOutputs();const pipelines=usePipelines(s=>s.items);const pipelineError=usePipelines(s=>s.error);
  const pipelinesLoaded=usePipelines(s=>s.loaded);
  const runningCount=pipelines.filter(p=>p.running).length;
  const [pipeline,setPipeline]=useState('all');const [expanded,setExpanded]=useState(false);
  const events=live.events.filter(e=>(pipeline==='all'||e.run_tag===pipeline)&&(!clinical||['result','interpretation','report'].includes(e.stage)));
  if(compact){
    const groups=new Map<string,{name:string;state:string;events:OutputEvent[]}>();
    pipelines.forEach(p=>{const tag=(p.running??p.latest)?.run_tag;if(tag)groups.set(tag,{name:p.name,state:`${p.running?(p.progress.stage||'Running'):'Not running'}${p.progress.iteration!=null?` · ${pipelineLoopLabel(p)}`:''}`,events:[]});});
    live.events.forEach(e=>{if(!groups.has(e.run_tag))groups.set(e.run_tag,{name:pipelineLabel(e,pipelines),state:'Saved outputs',events:[]});groups.get(e.run_tag)!.events.push(e);});
    const status=live.error||pipelineError?'Updates interrupted':!pipelinesLoaded?'Connecting':runningCount?`${runningCount} ${runningCount===1?'pipeline':'pipelines'} running`:'No pipelines running';
    const output=(event:OutputEvent)=><button key={`${event.id}:${event.revision}`} className="universe-activity-output" onClick={()=>open?.(event)} disabled={!open}><span><strong>{labels[event.stage]||event.stage}</strong>{event.iteration!=null||event.trial!=null?` · ${loopLabel(event)}`:''}</span><span>{event.title}</span><ArrowUpRight size={14}/></button>;
    return <section className="live-output-dock is-compact" aria-label="Live pipeline outputs">
      <header><div><Activity size={16}/><h2>Pipeline activity</h2><span className={`live-connection ${live.error||pipelineError?'is-stale':''}`}>{status}</span>{live.pending>0&&<span className="universe-update-count">{live.pending} new outputs</span>}</div><button aria-expanded={expanded} onClick={()=>{setExpanded(v=>!v);if(!expanded)live.acknowledge();}}>{expanded?'Hide outputs':'Show outputs'}<ChevronDown size={15} style={{transform:expanded?'rotate(180deg)':undefined}}/></button></header>
      {(live.error||pipelineError)&&<p role="alert" className="live-error">{live.error||pipelineError}</p>}
      {expanded&&<div className="live-output-cards universe-activity-list">{[...groups].map(([tag,group])=><article key={tag}><header><strong>{group.name}</strong><span>{group.state}</span></header>{group.events.slice(0,3).map(output)}{group.events.length>3&&<details><summary>Earlier outputs ({group.events.length-3})</summary>{group.events.slice(3).map(output)}</details>}{!group.events.length&&<p>Waiting for a recorded output.</p>}</article>)}{!groups.size&&<p>No pipeline activity yet.</p>}</div>}
    </section>;
  }
  return <section className={`live-output-dock ${clinical?'clinical-output-dock':''} `} aria-label={clinical?'Live clinical findings':'Live pipeline outputs'}>
    <header><div><Activity size={17}/><h2>{clinical?'Findings arriving now':'Across your pipelines'}</h2><span className={`live-connection ${live.error||pipelineError?'is-stale':''}`}>{live.error||pipelineError?'Updates interrupted':live.updatedAt?(pipelines.some(p=>p.running)?'Live · checks every 0.5s':'Saved outputs · standing by'):'Connecting'}</span></div><button aria-expanded={expanded} onClick={()=>{setExpanded(v=>!v);live.acknowledge();}}>{live.pending>0?`${live.pending} new updates`:(expanded?'Hide outputs':'Received outputs')} <ArrowUpRight size={13}/></button></header>
    {(live.error||pipelineError)&&<p role="alert" className="live-error">{live.error||pipelineError}</p>}
    {<>
    <div className="live-pipeline-strip"><button aria-pressed={pipeline==='all'} onClick={()=>setPipeline('all')}>All pipelines</button>{pipelines.map(p=><button key={p.id} disabled={!p.latest} aria-pressed={pipeline===p.latest?.run_tag} onClick={()=>setPipeline(p.latest?.run_tag||'all')}><i className={p.running?'is-running':''}/><strong>{p.name}</strong><span>{p.running?(p.progress.stage||'Running'):'Not running'}{p.progress.iteration!=null?` · ${pipelineLoopLabel(p)}`:''}</span></button>)}</div>
    <div className={`live-output-cards ${expanded?'is-expanded':''}`}>{events.slice(0,expanded?80:6).map(event=><button data-help="Recorded pipeline output" data-help-description="Open this recorded output and its linked evidence. The pipeline name, stage and loop identify where it came from; receiving it does not mean the hypothesis is validated." key={`${event.id}:${event.revision}`} className={event.fresh?'is-new':''} onClick={()=>open?.(event)} disabled={!open}><div><span>{pipelineLabel(event,pipelines)}</span><b>{labels[event.stage]||event.stage}</b>{event.fresh&&<em>NEW</em>}</div><ContentOrigin kind={event.stage === "data" && event.status !== "failed" ? "rule" : event.stage === "question" || event.stage === "hypothesis" || event.stage === "result" ? "proposal" : "mixed"} compact/><h3>{event.title}</h3><p>{event.detail.replace(/[#*_`]/g,'').slice(0,190)}</p><footer>{event.iteration!=null||event.trial!=null?loopLabel(event):'Run output'} · {event.fresh?`Received ${new Date(event.receivedAt).toLocaleTimeString()}`:'Previously recorded'}</footer></button>)}</div>
    {!events.length&&<p className="live-output-empty">{pipelines.some(p=>p.running)?'Waiting for the next recorded output. Each pipeline is observed independently.':'New outputs will appear here when a pipeline runs.'}</p>}
    <p className="live-output-footnote">{live.updatedAt?`Last synchronized ${new Date(live.updatedAt).toLocaleTimeString()}. `:''}New outputs accumulate without changing the finding you are reading. This session retains up to 500 output updates.</p>
    </>}
  </section>;
}
