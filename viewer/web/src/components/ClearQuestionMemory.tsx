import { useEffect, useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';

type Preview = {count:number;through:number;token:string;blocked:boolean};
export default function ClearQuestionMemory({onCleared,iconOnly=false}:{onCleared:(through:number)=>void;iconOnly?:boolean}) {
  const [open,setOpen]=useState(false);
  const [preview,setPreview]=useState<Preview|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');
  const request=useRef('');
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    if(!open)return;
    dialog.current?.showModal();
    let disposed=false;
    const controller=new AbortController();
    void fetch('/control/question-memory',{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(12000)])})
      .then(async r=>{const body=await r.json();if(!r.ok)throw Error(body.error||'Question memory is unavailable.');if(!disposed)setPreview(body);})
      .catch(e=>{if(!disposed)setError(e instanceof Error?e.message:'Question memory is unavailable.');});
    return()=>{disposed=true;controller.abort();};
  },[open]);
  const close=()=>{if(!busy){dialog.current?.close();setOpen(false);}};
  const clear=async()=>{
    if(!preview||preview.blocked||busy)return;
    setBusy(true);setError('');
    try {
      const response=await fetch('/control/question-memory/clear',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({confirm:'CLEAR QUESTION MEMORY',request_id:request.current,token:preview.token}),signal:AbortSignal.timeout(20000)});
      const body=await response.json();
      if(!response.ok){if(response.status===409)setPreview(null);throw Error(body.error||'Clear could not be confirmed. Retry to check its outcome.');}
      onCleared(body.cleared_through);setNotice(`${body.cleared} questions cleared from active memory. Saved analyses and reports are retained.`);
      dialog.current?.close();setOpen(false);
    } catch(e){setError(e instanceof Error?e.message:'Clear could not be confirmed. Retry this confirmation to check its outcome.');}
    finally{setBusy(false);}
  };
  return <>
    <button className={iconOnly?'universe-clear-questions':undefined} aria-label={iconOnly?'Clear questions':undefined} title={iconOnly?'Clear questions':undefined} onClick={()=>{setPreview(null);setError('');setNotice('');request.current=crypto.randomUUID();setOpen(true);}}><Trash2 size={16}/>{!iconOnly&&'Clear memory'}</button>
    {notice&&<p role="status">{notice}</p>}
    {open&&<dialog ref={dialog} className="workspace-dialog universe-clear-dialog" aria-labelledby="clear-memory-title" onCancel={e=>{e.preventDefault();close();}}>
      <h2 id="clear-memory-title">Clear Question Universe memory?</h2>
      <p>Are you sure you want to clear the active question memory across all pipelines and knowledge sources?</p>
      <p>This archives the questions from the Universe and excludes them from future question selection and duplicate checks. Saved hypotheses, analyses, results, reports and their question links are retained. New questions can be generated again.</p>
      <p>This does not erase historical data. Restoring questions to active memory is not available in this interface.</p>
      {preview?<p>{preview.count} questions will be cleared.</p>:!error&&<p role="status">Checking the current question memory…</p>}
      {preview?.blocked&&<p role="alert">End all running or paused executions before clearing memory.</p>}
      {error&&<p role="alert">{error}{!preview&&' Close this dialog and reopen it to review the current memory.'}</p>}
      <div className="flex flex-wrap gap-3 mt-4">
        <button autoFocus disabled={busy} onClick={close}>Cancel</button>
        <button disabled={busy||!preview||preview.blocked||preview.count===0} onClick={()=>void clear()}>{busy?'Clearing…':'Clear memory'}</button>
      </div>
    </dialog>}
  </>;
}
