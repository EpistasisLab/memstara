import { useEffect, useRef, useState } from 'react';
import { Activity, History, X } from 'lucide-react';
import { useViewer, useHealth, POLL_MS } from '../store/viewer';
import { useControl } from '../store/control';
import { usePipelines } from '../store/pipelines';

export default function WorkspaceActions({only}: {only?: 'history' | 'status'}) {
  const [open,setOpen]=useState<'history'|'status'|null>(null);
  const [search,setSearch]=useState('');
  const dialog=useRef<HTMLDialogElement>(null);
  const snapshot=useViewer(s=>s.snapshot),known=useViewer(s=>s.knownRuns);
  const tag=useViewer(s=>s.runTag),apiError=useViewer(s=>s.error),ticks=useViewer(s=>s.ticks);
  const controlUp=useControl(s=>s.up),controlError=useControl(s=>s.error);
  const health=useHealth();
  const pipelines=usePipelines(s=>s.items);
  useEffect(()=>{if(open)dialog.current?.showModal();},[open]);
  const close=()=>{dialog.current?.close();setOpen(null);};
  const label=(run: (typeof known)[number])=>{
    const p=pipelines.find(p=>p.latest?.run_tag===run.run_tag);
    return `${p?.name||'Saved analysis'} · ${run.first_seen?new Date(run.first_seen).toLocaleString():run.run_tag}`;
  };
  const runs=(snapshot?.runs??known).filter(r=>`${label(r)} ${r.run_tag} ${r.model??''}`.toLowerCase().includes(search.toLowerCase()));
  const issue=!!apiError||!!controlError||controlUp===false||health?.memstara.up===false||health?.core.up===false;
  return <>
    {only !== 'status' && <button className="workspace-action saved-analyses-action" aria-label="Saved analyses" title="Open saved analyses" onClick={()=>setOpen('history')}><History size={16}/><span>Saved analyses</span></button>}
    {only !== 'history' && <button className="workspace-action" onClick={()=>setOpen('status')}><Activity size={16}/>{issue?'Status · attention':'System status'}</button>}
    {open&&<dialog ref={dialog} onCancel={()=>setOpen(null)} aria-labelledby="workspace-action-title" className="workspace-dialog">
      <header><h2 id="workspace-action-title">{open==='history'?'Saved analyses':'System status'}</h2><button aria-label="Close workspace dialog" onClick={close}><X size={18}/></button></header>
      {open==='history'?<>
        <p>Open previous results here. Start a new analysis using a pipeline's Play button in Floor Plan.</p>
        <button className="workspace-action" onClick={()=>{usePipelines.getState().viewRun(null);close();}}>No saved analysis selected</button>
        <label className="block my-3">Find an analysis<input className="workspace-input" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Pipeline, date, model or run ID"/></label>
        <div className="space-y-2">{runs.map(run=><button key={run.run_tag} className="run-history-item" aria-pressed={run.run_tag===tag}
          onClick={()=>{usePipelines.getState().viewRun(run.run_tag);close();}}>
          <strong>{label(run)}</strong><span>{[run.model,run.status,`${run.tasks} tasks · ${run.done} done`].filter(Boolean).join(' · ')}</span>
          <small>{run.run_tag}</small></button>)}</div>
        {!runs.length&&<p>{apiError?'Saved analyses are currently unavailable. Check System status.':'No matching saved analyses.'}</p>}
      </>:<>
        <ul className="space-y-2 my-3">
          <li>Memstara: {health?health.memstara.up?'Connected':health.memstara.error:'Checking…'}</li>
          <li>Agent runtime: {health?health.core.up?'Connected':health.core.error:'Checking…'}</li>
          <li>Pipeline control: {controlUp===true?'Connected':controlUp===false?'Unavailable':'Checking…'}</li>
        </ul>
        <p>Refresh interval: {POLL_MS/1000}s · {ticks} polls</p>
        {apiError&&<p role="alert">{apiError}</p>}{controlError&&<p role="alert">{controlError}</p>}
      </>}
    </dialog>}
  </>;
}
