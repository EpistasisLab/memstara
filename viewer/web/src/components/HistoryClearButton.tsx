import {useEffect,useId,useRef,useState} from 'react';
import {Archive,Trash2,X} from 'lucide-react';
import {useHistoryReset} from '../store/historyReset';
import {historyNoticeKey,resetActive,resetPhaseLabels,resetRequestId,type HistoryResetState} from '../lib/historyReset';
import './history-clear.css';

function restoredNotice():HistoryResetState|null {
 try{return JSON.parse(sessionStorage.getItem(historyNoticeKey)||'null');}catch{return null;}
}
export default function HistoryClearButton() {
 const dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement>(null),id=useId();
 const {state,error,submitting,poll,begin}=useHistoryReset();
 const [mode,setMode]=useState<'backup'|'no_backup'>('backup');
 const [confirmation,setConfirmation]=useState('');
 const [notice,setNotice]=useState(restoredNotice);
 const request=useRef<string|null>(null);
 const active=resetActive(state),busy=active||submitting;
 const result=notice;
 useEffect(()=>{if(notice||active)dialog.current?.showModal();},[notice,active]);
 const close=()=>{dialog.current?.close();setNotice(null);try{sessionStorage.removeItem(historyNoticeKey);}catch{/* Session still works. */}trigger.current?.focus();};
 const submit=()=>{
  if(confirmation!=='CLEAR ALL HISTORY'||busy)return;
  if(!request.current||state?.state==='failed')request.current=resetRequestId();
  void begin(mode,confirmation,request.current);
 };
 return <>
  <button ref={trigger} type="button" className="history-clear-trigger" aria-haspopup="dialog"
    aria-controls={id} onClick={()=>{setConfirmation('');dialog.current?.showModal();void poll();}}>
    <Trash2 size={14} aria-hidden="true"/><span>{busy?'Clearing…':'Clear'}</span>
  </button>
  <dialog ref={dialog} id={id} className="history-clear-dialog" aria-labelledby={`${id}-title`} onCancel={close}>
   <header><h2 id={`${id}-title`}>Clear all experiment history</h2><button type="button" aria-label="Close history clearing" onClick={close}><X size={18}/></button></header>
   {result ? <div role="status">
    <p>All experiment history has been cleared. Estimated total is $0. Settings and research inputs were preserved.</p>
    {result.backup&&<div className="history-clear-backup"><Archive size={18}/><div><p>Verified backup: <code>{result.backup.location}</code></p><a href={result.backup.download} download>Download verified backup</a></div></div>}
    <button type="button" className="history-clear-primary" onClick={close}>Done</button>
   </div> : busy ? <div role="status" aria-live="polite">
    <p>{resetPhaseLabels[state?.state||'stopping']||'Requesting history clearing…'}</p>
    <p>This job continues if you close this dialog. Do not start another experiment until it finishes.</p>
   </div> : <>
    <p>This clears <strong>every pipeline’s</strong> execution history, results, interpretations, explanations, logs, token usage and costs from both databases and execution files.</p>
    <p>Pipeline and model settings, CSV datasets, OKF knowledge, skills and .env are preserved. Any running executions will be ended safely first.</p>
    <fieldset><legend>Backup option</legend>
     <label><input type="radio" name={`${id}-mode`} checked={mode==='backup'} onChange={()=>setMode('backup')}/><span><strong>Back up and clear</strong><small>Save and verify both databases and execution files before deletion. If backup fails, nothing is deleted.</small></span></label>
     <label><input type="radio" name={`${id}-mode`} checked={mode==='no_backup'} onChange={()=>setMode('no_backup')}/><span><strong>Clear without backup</strong><small>Permanently delete this history without creating a new backup.</small></span></label>
    </fieldset>
    <p>Existing backups are kept separately. Clearing cannot be undone without a valid backup.</p>
    {state?.state==='failed'&&<p role="alert">{state.message}{state.failed_phase&&<> Failed stage: {state.failed_phase}.</>}{state.backup&&<> Verified backup: <a href={state.backup.download} download>Download backup</a>.</>}</p>}
    {error&&<p role="alert">{error} Check the job status before retrying.</p>}
    <label className="history-clear-confirm">Type <strong>CLEAR ALL HISTORY</strong> to confirm<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} autoComplete="off" spellCheck={false}/></label>
    <footer><button type="button" onClick={close}>Cancel</button><button type="button" className="history-clear-primary" disabled={confirmation!=='CLEAR ALL HISTORY'||busy} onClick={submit}>{mode==='backup'?'Back up and clear':'Clear without backup'}</button></footer>
   </>}
  </dialog>
 </>;
}
