import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Pencil } from 'lucide-react';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';
function NameDialog({ pipeline, close }: { pipeline:PipelineDefinition; close:()=>void }) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [name,setName]=useState(pipeline.name),[error,setError]=useState(''),[saving,setSaving]=useState(false);
  useEffect(()=>{dialog.current?.showModal();},[]);
  const save=async()=>{
    if(!name.trim()||name.trim().length>80){setError('Use a name between 1 and 80 characters.');return;}
    if(usePipelines.getState().busy){setError('Another change is being saved. Please try again in a moment.');return;}
    setSaving(true);setError('');
    try{await usePipelines.getState().rename(pipeline.id,name.trim());close();}catch(e){setError(String(e));}finally{setSaving(false);}
  };
  return <dialog ref={dialog} className="workspace-dialog" aria-labelledby="pipeline-name-heading" onCancel={e=>{if(saving)e.preventDefault();else close();}}><form onSubmit={e=>{e.preventDefault();void save();}} className="space-y-4 p-5"><h2 id="pipeline-name-heading" className="text-lg font-semibold">Name your pipeline</h2><p className="text-sm text-ink-soft">Give Pipeline {pipeline.number} a recognizable research name. The name is saved across sessions; changing it does not restart the analysis.</p><label className="block text-sm">Pipeline name<input autoFocus aria-label="New pipeline name" maxLength={80} value={name} onChange={e=>setName(e.target.value)} className="mt-2 block w-full rounded-lg border border-paper-line bg-paper p-3 text-ink"/></label>{error&&<p role="alert" className="text-sm text-red-700">{error}</p>}<div className="flex justify-end gap-2"><button type="button" disabled={saving} onClick={close} className="rounded border border-paper-line px-4 py-2">Cancel</button><button type="submit" disabled={saving||!name.trim()} className="rounded bg-accent px-4 py-2 text-accent-contrast disabled:opacity-50">{saving?'Saving…':'Save name'}</button></div></form></dialog>;
}
export default function PipelineNameEditor({pipeline,buttonLabel}:{pipeline:PipelineDefinition;buttonLabel?:string}) {
  const [editing,setEditing]=useState(false);
  return <><button className="relative z-10 flex max-w-64 items-center gap-2 rounded px-2 py-1 text-sm text-ink hover:bg-paper" aria-label={`Rename ${pipeline.name}`} title="Change pipeline name" onClick={()=>setEditing(true)}><span className="truncate">{buttonLabel??pipeline.name}</span><Pencil size={12} className="shrink-0 text-ink-faint"/></button>{editing&&createPortal(<NameDialog pipeline={pipeline} close={()=>setEditing(false)}/>,document.body)}</>;
}
