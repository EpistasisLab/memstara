import {useEffect,useId,useRef,useState} from 'react';
import {Archive,Trash2,X} from 'lucide-react';
import {useHistoryReset} from '../store/historyReset';
import {usePipelines} from '../store/pipelines';
import {historyNoticeKey,resetActive,resetPhaseLabels,resetRequestId,type HistoryResetState} from '../lib/historyReset';
import './history-clear.css';

function restoredNotice():HistoryResetState|null {
 try{return JSON.parse(sessionStorage.getItem(historyNoticeKey)||'null');}catch{return null;}
}
export default function HistoryClearButton() {
 const dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement>(null),id=useId();
 const {state,error,submitting,poll,begin}=useHistoryReset();
 const [mode,setMode]=useState<'backup'|'no_backup'>('backup');
 const items=usePipelines(s=>s.items),selected=usePipelines(s=>s.selected);
 const [scope,setScope]=useState<'all'|'selected'>('all');
 const [pipelineId,setPipelineId]=useState('');
 const [confirmation,setConfirmation]=useState('');
 const [notice,setNotice]=useState(restoredNotice);
 const request=useRef<string|null>(null);
 const active=resetActive(state),busy=active||submitting;
 const locked=!!state?.blocked;
 const effectiveScope=locked?(state.scope??'all'):scope;
 const effectiveId=locked?(state.pipeline_id??''):pipelineId;
 const target=items.find(p=>p.id===effectiveId);
 const expected=effectiveScope==='selected'?'CLEAR SELECTED HISTORY':'CLEAR ALL HISTORY';
 const validTarget=effectiveScope==='all'||!!target&&!target.deleting;
 const change=()=>{setConfirmation('');request.current=null;};
 const result=notice;
 useEffect(()=>{if(notice||active)dialog.current?.showModal();},[notice,active]);
 const close=()=>{dialog.current?.close();setNotice(null);try{sessionStorage.removeItem(historyNoticeKey);}catch{/* Session still works. */}trigger.current?.focus();};
 const submit=()=>{
  if(confirmation!==expected||busy||!validTarget)return;
  if(!request.current||state?.state==='failed')request.current=resetRequestId();
  void begin(mode,confirmation,request.current,effectiveScope,effectiveId);
 };
 return <>
  <button ref={trigger} type="button" className="history-clear-trigger" aria-haspopup="dialog"
    aria-controls={id} onClick={()=>{change();setPipelineId(selected??items[0]?.id??'');dialog.current?.showModal();void poll();void usePipelines.getState().poll();}}>
    <Trash2 size={14} aria-hidden="true"/><span>{busy?'Clearing…':'Clear'}</span>
  </button>
  <dialog ref={dialog} id={id} className="history-clear-dialog" aria-labelledby={`${id}-title`} onCancel={close}>
   <header><h2 id={`${id}-title`}>Clear experiment history</h2><button type="button" aria-label="Close history clearing" onClick={close}><X size={18}/></button></header>
   {result ? <div role="status">
    <p>{result.scope==='selected'?`History for ${result.pipeline_name||'the selected experiment'} has been cleared, including its continuation attempts. Other experiments are retained; their costs remain in Estimated total.`:'All experiment history has been cleared. Estimated total is $0.'} Settings and research inputs were preserved.</p>
    {result.backup&&<div className="history-clear-backup"><Archive size={18}/><div><p>Verified backup: <code>{result.backup.location}</code></p><a href={result.backup.download} download>Download verified backup</a></div></div>}
    <button type="button" className="history-clear-primary" onClick={close}>Done</button>
   </div> : busy ? <div role="status" aria-live="polite">
    <p>{resetPhaseLabels[state?.state||'stopping']||'Requesting history clearing…'}</p>
    <p>{state?.scope==='selected'?`Selected experiment: ${state.pipeline_name||state.pipeline_id}. Other running experiments are not stopped.`:'All experiments are included.'}</p>
    <p>This job continues if you close this dialog. Starting or editing experiments is temporarily locked until it finishes.</p>
   </div> : <>
    <fieldset disabled={locked}><legend>History to clear</legend>
     <label><input type="radio" name={`${id}-scope`} checked={effectiveScope==='all'} onChange={()=>{change();setScope('all');}}/><span><strong>All experiments</strong><small>Clear execution history for every experiment.</small></span></label>
     <label><input type="radio" name={`${id}-scope`} checked={effectiveScope==='selected'} onChange={()=>{change();setScope('selected');}}/><span><strong>Selected experiment</strong><small>Clear one experiment, including all of its resumed and retried executions.</small></span></label>
     {effectiveScope==='selected'&&<label>Experiment<select aria-label="Experiment to clear" value={effectiveId} onChange={e=>{change();setPipelineId(e.target.value);}}><option value="">Choose an experiment</option>{items.filter(p=>!p.deleting).map(p=><option value={p.id} key={p.id}>{p.name} (#{p.number})</option>)}</select></label>}
    </fieldset>
    <p>This clears {effectiveScope==='all'?<strong>every experiment’s</strong>:<strong>{target?.name||'the selected experiment’s'}</strong>} execution history, results, interpretations, explanations, logs, token usage and costs. {effectiveScope==='selected'&&'Other experiments and shared records they still use are retained.'}</p>
    <p>Pipeline and model settings, CSV datasets, OKF knowledge, skills and .env are preserved. {effectiveScope==='all'?'All running executions will be ended safely first.':target?.running?'This experiment is running. Clearing will end its active execution first; other experiments will continue.':'Only the selected experiment will be stopped if it starts running before confirmation.'}</p>
    <fieldset><legend>Backup option</legend>
     <label><input type="radio" name={`${id}-mode`} checked={mode==='backup'} onChange={()=>{change();setMode('backup');}}/><span><strong>Back up and clear</strong><small>Save and verify both complete databases and the execution files selected for deletion. The database backup includes other experiments; only the chosen history is deleted. If backup fails, nothing is deleted.</small></span></label>
     <label><input type="radio" name={`${id}-mode`} checked={mode==='no_backup'} onChange={()=>{change();setMode('no_backup');}}/><span><strong>Clear without backup</strong><small>Permanently delete this history without creating a new backup.</small></span></label>
    </fieldset>
    <p>Existing backups are kept separately. Clearing cannot be undone without a valid backup.</p>
    {state?.state==='failed'&&<p role="alert">{state.message}{state.failed_phase&&<> Failed stage: {state.failed_phase}.</>}{state.backup&&<> Verified backup: <a href={state.backup.download} download>Download backup</a>.</>}</p>}
    {error&&<p role="alert">{error} Check the job status before retrying.</p>}
    <label className="history-clear-confirm">Type <strong>{expected}</strong> to confirm<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} autoComplete="off" spellCheck={false}/></label>
    <footer><button type="button" onClick={close}>Cancel</button><button type="button" className="history-clear-primary" disabled={confirmation!==expected||busy||!validTarget} onClick={submit}>{mode==='backup'?'Back up and clear':'Clear without backup'}</button></footer>
   </>}
  </dialog>
 </>;
}
