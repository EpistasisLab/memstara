import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
export default function FloorDetailDialog({title,close,children,className=''}:{title:string;close:()=>void;children:ReactNode;className?:string}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{ref.current?.showModal();},[]);
  return createPortal(<dialog ref={ref} className={`workspace-dialog floor-detail-dialog ${className}`} aria-label={title} onCancel={close}>
    <header><h2>{title}</h2><button aria-label="Close pipeline details" onClick={close}><X size={18}/></button></header>
    <div className="floor-detail-dialog-body">{children}</div>
  </dialog>,document.body);
}
