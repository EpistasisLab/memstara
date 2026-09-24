import LoopLimitSettings from "./LoopLimitSettings";
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { usePipelines } from '../store/pipelines';
import { useControl } from '../store/control';

export default function PipelineSettings({id,section,close}:{id:string;section:'runtime'|'data';close:()=>void}) {
  const pipeline=usePipelines(s=>s.items.find(p=>p.id===id));
  const busy=usePipelines(s=>s.busy);
  const dialog=useRef<HTMLDialogElement>(null);
  const provider=useControl(s=>s.form.provider);
  const model=useControl(s=>s.form.model);
  const [target,setTarget]=useState(pipeline?.configuration.y_column??'');
  const [limit,setLimit]=useState(pipeline?.configuration.waves??10);
  useEffect(()=>{dialog.current?.showModal();},[]);
  if(!pipeline)return null;
  const locked=!!pipeline.running||busy;
  return <dialog ref={dialog} onCancel={close} className="workspace-dialog" aria-labelledby="pipeline-settings-title">
    <header><h2 id="pipeline-settings-title">{pipeline.name} · {section==='data'?'Data & target':'Pipeline settings'}</h2><button aria-label="Close pipeline settings" onClick={close}><X size={18}/></button></header>
    {section==='data'?<>
      <p>This pipeline uses the configured research dataset. Select the fixed outcome column to predict; data cleaning is outside this workflow.</p>
      <label>Target column (Y)<input className="workspace-input" value={target} onChange={e=>setTarget(e.target.value)} disabled={locked}/></label>
    </>:<>
      <p>The language model is configured centrally in motoro/.env and applies to every pipeline. Predictive models and evaluation settings are configured on the ML agent card.</p>
      <LoopLimitSettings value={limit} disabled={locked} onChange={setLimit}/>
      <label>Provider<input className="workspace-input" value={provider} readOnly aria-readonly="true" placeholder="Loading configured provider…"/></label>
      <label>LLM model<input className="workspace-input" value={model} readOnly aria-readonly="true" placeholder="Loading configured model…"/></label>
    </>}
    {pipeline.running&&<p>End this execution before changing its settings. Stopped executions retain their original settings for Resume.</p>}
    <footer><button className="workspace-action" onClick={close}>Cancel</button><button className="workspace-action" disabled={locked||(!Number.isInteger(limit)||limit<1||limit>10)||!(section==='data'?target.trim():provider.trim()&&model.trim())} onClick={()=>{
      usePipelines.getState().save(id,{...pipeline.configuration,...(section==='data'?{y_column:target.trim()}:{provider:provider.trim(),model:model.trim(),continuous:false,waves:limit})});close();
    }}>Save settings</button></footer>
  </dialog>;
}
