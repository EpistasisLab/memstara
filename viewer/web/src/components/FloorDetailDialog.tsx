import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
export default function FloorDetailDialog({title,close,children,className='',dismissible=true,initialFocus}:{title:string;close:()=>void;children:ReactNode;className?:string;dismissible?:boolean;initialFocus?:string}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{ref.current?.showModal();if(initialFocus)ref.current?.querySelector<HTMLElement>(initialFocus)?.focus();},[initialFocus]);
  return createPortal(<dialog ref={ref} className={`workspace-dialog floor-detail-dialog ${className}`} aria-label={title} onCancel={event=>{event.preventDefault();if(dismissible)close();}}>
    <header><h2>{title}</h2><button disabled={!dismissible} aria-label="Close pipeline details" onClick={close}><X size={18}/></button></header>
    <div className="floor-detail-dialog-body">{children}</div>
  </dialog>,document.body);
}
