import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { explainElement } from '../lib/interfaceHelp';

interface Tip { owner:HTMLElement; label:string; text:string }
const selector='[data-help],button,[role="button"],[role="tab"],input,select,textarea,summary,th,dt,small,h3,[title]';
/** Delegated help adds no wrappers to canvas nodes, grids, tables or controls. */
export default function InterfaceHelp(){
  const [tip,setTip]=useState<Tip|null>(null);
  const box=useRef<HTMLDivElement>(null);
  const owner=useRef<HTMLElement|null>(null);
  const reposition=useRef<()=>void>(()=>{});
  const timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const hideTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const hide=()=>{clearTimeout(timer.current);clearTimeout(hideTimer.current);owner.current=null;setTip(null);};
  const leave=()=>{clearTimeout(timer.current);hideTimer.current=setTimeout(hide,160);};
  useEffect(()=>{
    const find=(event:Event)=>{
      const target=event.target;
      if(!(target instanceof Element)||box.current?.contains(target))return;
      let element=target.closest<HTMLElement>(selector);
      while(element&&!explainElement(element)&&!element.closest('[data-context-help-managed]'))element=element.parentElement?.closest<HTMLElement>(selector)??null;
      if(!element||element.closest('[data-context-help-managed]')||['closed','delayed-open','instant-open'].includes(element.dataset.state??'')){leave();return;}
      clearTimeout(hideTimer.current);
      if(owner.current===element)return;
      hide();const explanation=explainElement(element);if(!explanation)return;
      owner.current=element;
      timer.current=setTimeout(()=>{if(element.isConnected)setTip({owner:element,...explanation});},event.type==='focusin'?200:380);
    };
    const exit=(event:Event)=>{const next=(event as PointerEvent).relatedTarget;if(next instanceof Node&&(owner.current?.contains(next)||box.current?.contains(next)))return;leave();};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&owner.current&&box.current){event.preventDefault();event.stopPropagation();hide();}};
    const scroll=(event:Event)=>{if(event.target instanceof Node&&box.current?.contains(event.target))return;if(box.current)reposition.current();};
    const down=(event:Event)=>{if(!(event.target instanceof Node)||!box.current?.contains(event.target))hide();};
    document.addEventListener('pointerover',find,true);document.addEventListener('focusin',find,true);
    document.addEventListener('pointerout',exit,true);document.addEventListener('focusout',exit,true);
    document.addEventListener('keydown',escape,true);document.addEventListener('pointerdown',down,true);
    document.addEventListener('scroll',scroll,true);window.addEventListener('resize',hide);
    return()=>{clearTimeout(timer.current);clearTimeout(hideTimer.current);document.removeEventListener('pointerover',find,true);document.removeEventListener('focusin',find,true);document.removeEventListener('pointerout',exit,true);document.removeEventListener('focusout',exit,true);document.removeEventListener('keydown',escape,true);document.removeEventListener('pointerdown',down,true);document.removeEventListener('scroll',scroll,true);window.removeEventListener('resize',hide);};
  },[]);
  useLayoutEffect(()=>{
    if(!tip||!box.current)return;
    const node=box.current;
    // Native top layer keeps help above full-screen canvases and modal dialogs.
    try{if(node.showPopover)node.showPopover();else node.removeAttribute('popover');}catch{node.removeAttribute('popover');}
    const originalTitle=tip.owner.getAttribute('title');
    if(originalTitle)tip.owner.removeAttribute('title');
    const previous=tip.owner.getAttribute('aria-describedby');
    tip.owner.setAttribute('aria-describedby',[previous,'interface-context-help'].filter(Boolean).join(' '));
    const place=()=>{
    const anchor=tip.owner.getBoundingClientRect(),rect=node.getBoundingClientRect();
    const left=Math.max(12,Math.min(anchor.left,window.innerWidth-rect.width-12));
    const top=anchor.bottom+rect.height+20<=window.innerHeight?anchor.bottom+9:Math.max(12,anchor.top-rect.height-9);
    node.style.left=`${left}px`;node.style.top=`${top}px`;
    };
    reposition.current=place;place();
    const check=setInterval(()=>{if(!tip.owner.isConnected)hide();},250);
    return()=>{clearInterval(check);if(originalTitle&&!tip.owner.hasAttribute('title'))tip.owner.setAttribute('title',originalTitle);
      const described=(tip.owner.getAttribute('aria-describedby')??'').split(' ').filter(id=>id&&id!=='interface-context-help').join(' ');
      if(described)tip.owner.setAttribute('aria-describedby',described);else tip.owner.removeAttribute('aria-describedby');};
  },[tip]);
  if(!tip)return null;
  const container=tip.owner.closest('dialog[open]') || (document.fullscreenElement?.contains(tip.owner)?document.fullscreenElement:null) || document.body;
  return createPortal(<div ref={box} id="interface-context-help" role="tooltip" popover="manual" className="interface-context-help"
    onPointerEnter={()=>clearTimeout(hideTimer.current)} onPointerLeave={leave}>
    <strong>{tip.label}</strong><p>{tip.text}</p>
  </div>,container);
}
