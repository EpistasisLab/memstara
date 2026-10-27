import {useEffect, useRef} from 'react';
import {createPortal} from 'react-dom';
import {CheckCircle2, CircleAlert} from 'lucide-react';

export type InputFeedback={ready:boolean;messages:string[]};
export default function ResearchInputFeedback({feedback,onClose}:{feedback:InputFeedback;onClose:()=>void}){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const dialog=ref.current;dialog?.showModal();return ()=>dialog?.close();},[]);
 const title=feedback.ready?'Your data is ready':'Review your data settings';
 const Icon=feedback.ready?CheckCircle2:CircleAlert;
 return createPortal(<dialog ref={ref} className="research-feedback-dialog" aria-label={title} aria-describedby="research-feedback-description" onCancel={event=>{event.preventDefault();event.stopPropagation();onClose();}} onKeyDown={event=>event.stopPropagation()}>
  <div className={`research-feedback-icon ${feedback.ready?'is-ready':''}`}><Icon size={26} aria-hidden="true"/></div>
  <h2>{title}</h2>
  <p id="research-feedback-description">{feedback.ready?'Input checks passed. Click “Choose skills” to continue to agent setup.':'Please fix the items below, then click “Check & use this data” again.'}</p>
  {!feedback.ready&&<ul>{feedback.messages.map((message,index)=><li key={index}>{message}</li>)}</ul>}
  <button type="button" autoFocus onClick={onClose}>{feedback.ready?'Got it':'Back to settings'}</button>
 </dialog>,document.body);
}
