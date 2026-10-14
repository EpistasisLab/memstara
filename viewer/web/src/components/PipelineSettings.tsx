import LoopLimitSettings from "./LoopLimitSettings";
import ResearchInputSelect from './ResearchInputSelect';
import type {RunRequest} from '../store/control';
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { usePipelines } from '../store/pipelines';
import { useControl } from '../store/control';

export default function PipelineSettings({id,section,close,title}:{id:string;title?:string;section:'runtime'|'data';close:()=>void}) {
  const pipeline=usePipelines(s=>s.items.find(p=>p.id===id));
  const busy=usePipelines(s=>s.busy);
  const error=usePipelines(s=>s.error);
  const [sourceError,setSourceError]=useState('');
  const dialog=useRef<HTMLDialogElement>(null);
  const provider=useControl(s=>s.form.provider);
  const model=useControl(s=>s.form.model);
  const [target,setTarget]=useState(pipeline?.configuration.y_column??'');
  const [research,setResearch]=useState<Partial<RunRequest>>({...pipeline?.configuration});
  const [limit,setLimit]=useState(pipeline?.configuration.combination_max_loops??pipeline?.configuration.waves??10);
  useEffect(()=>{dialog.current?.showModal();},[]);
  if(!pipeline)return null;
  const combinations=pipeline.configuration.combination_max_loops!=null;
  const maximum=combinations?10000:10;
  const validData=research.data_mode==='proposal'?!!research.research_objective?.trim():!!target.trim();
  const locked=!!pipeline.running||busy;
  return <dialog ref={dialog} onCancel={close} className="workspace-dialog" aria-labelledby="pipeline-settings-title">
    <header><h2 id="pipeline-settings-title">{pipeline.name} · {title??(section==='data'?'Data & target':'Pipeline settings')}</h2><button aria-label="Close pipeline settings" onClick={close}><X size={18}/></button></header>
    {section==='data'?<>
      <ResearchInputSelect onValidityChange={setSourceError} value={research} disabled={locked} onChange={patch=>{setResearch(current=>({...current,...patch}));if(patch.y_column)setTarget(patch.y_column);}}/>
      <p>A saved research version supplies its own dataset, corpus, target meaning and label mapping. Edit the version to change these together.</p>
      {research.data_mode!=='proposal'&&<label>Target column (Y)<input className="workspace-input" value={target} onChange={e=>setTarget(e.target.value)} disabled={locked||!!research.research_input_id}/></label>}
    </>:<>
      <p>The fields below show deployment defaults. Role overrides for non-Explanation agents and the Explanation agent are configured in this installation's .env. Explicit environment injection is reserved for supervised deployments; restart the services after changing them. Predictive models and evaluation settings are configured on the ML agent card.</p>
      {combinations?<label>Maximum Loops per execution<input aria-label="Maximum Loops per execution" className="workspace-input" type="number" min={1} max={10000} step={1} value={Number.isFinite(limit)?limit:''} disabled={locked} onChange={e=>setLimit(e.target.valueAsNumber)}/></label>:<LoopLimitSettings value={limit} disabled={locked} onChange={setLimit}/>}
      <label>Default provider<input className="workspace-input" value={provider} readOnly aria-readonly="true" placeholder="Loading configured provider…"/></label>
      <label>Default LLM model<input className="workspace-input" value={model} readOnly aria-readonly="true" placeholder="Loading configured model…"/></label>
    </>}
    {pipeline.running&&<p>End this execution before changing its settings. Stopped executions retain their original settings for Resume.</p>}
    {error&&<p role="alert">{error}</p>}
    <footer><button className="workspace-action" onClick={close}>Cancel</button><button className="workspace-action" disabled={locked||(section==='runtime'&&(!Number.isInteger(limit)||limit<1||limit>maximum))||(section==='data'&&(!validData||!!sourceError))} onClick={async()=>{
      const saved=await usePipelines.getState().save(id,{...pipeline.configuration,...(section==='data'?{...research,y_column:target.trim()}:{provider:provider.trim(),model:model.trim(),continuous:false,waves:limit,...(combinations?{combination_max_loops:limit}:{})})});if(saved)close();
    }}>Save settings</button></footer>
  </dialog>;
}
