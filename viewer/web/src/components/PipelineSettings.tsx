import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { usePipelines } from '../store/pipelines';

export default function PipelineSettings({id,section,close}:{id:string;section:'runtime'|'data';close:()=>void}) {
  const pipeline=usePipelines(s=>s.items.find(p=>p.id===id));
  const busy=usePipelines(s=>s.busy);
  const dialog=useRef<HTMLDialogElement>(null);
  const [provider,setProvider]=useState(pipeline?.configuration.provider??'');
  const [model,setModel]=useState(pipeline?.configuration.model??'');
  const [target,setTarget]=useState(pipeline?.configuration.y_column??'');
  useEffect(()=>{dialog.current?.showModal();},[]);
  if(!pipeline)return null;
  const locked=!!pipeline.running||busy;
  return <dialog ref={dialog} onCancel={close} className="workspace-dialog" aria-labelledby="pipeline-settings-title">
    <header><h2 id="pipeline-settings-title">{pipeline.name} · {section==='data'?'Data & target':'Pipeline settings'}</h2><button aria-label="Close pipeline settings" onClick={close}><X size={18}/></button></header>
    {section==='data'?<>
      <p>This pipeline uses the configured research dataset. Select the fixed outcome column to predict; data cleaning is outside this workflow.</p>
      <label>Target column (Y)<input className="workspace-input" value={target} onChange={e=>setTarget(e.target.value)} disabled={locked}/></label>
    </>:<>
      <p>These settings choose the language model used by this pipeline's agents. Predictive models and evaluation settings are configured on the ML agent card.</p>
      <label>Provider<input className="workspace-input" value={provider} onChange={e=>setProvider(e.target.value)} disabled={locked}/></label>
      <label>LLM model<input className="workspace-input" value={model} onChange={e=>setModel(e.target.value)} disabled={locked}/></label>
    </>}
    {pipeline.running&&<p>Stop this pipeline before changing its settings.</p>}
    <footer><button className="workspace-action" onClick={close}>Cancel</button><button className="workspace-action" disabled={locked||!(section==='data'?target.trim():provider.trim()&&model.trim())} onClick={()=>{
      usePipelines.getState().save(id,{...pipeline.configuration,...(section==='data'?{y_column:target.trim()}:{provider:provider.trim(),model:model.trim()})});close();
    }}>Save settings</button></footer>
  </dialog>;
}
