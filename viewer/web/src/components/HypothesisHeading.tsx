import {useRef,useState} from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';

/** Keep cards compact; render the complete current hypothesis outside clipping panels. */
export default function HypothesisHeading({text}:{text:string}) {
 const trigger=useRef<HTMLElement>(null);
 const [side,setSide]=useState<'right'|'left'|'bottom'>('bottom');
 const position=(open:boolean)=>{
  if(!open||!trigger.current)return;
  const bounds=trigger.current.getBoundingClientRect();
  const needed=Math.min(380,window.innerWidth-24)+22;
  setSide(window.innerWidth-bounds.right>=needed?'right':bounds.left>=needed?'left':'bottom');
 };
 return <Tooltip.Root key={text} delayDuration={180} disableHoverableContent={false} onOpenChange={position}>
  <Tooltip.Trigger asChild>
   <strong ref={trigger} className="pipeline-card-name hypothesis-popup-trigger" tabIndex={0} aria-label={text}>{text}</strong>
  </Tooltip.Trigger>
  <Tooltip.Portal>
   <Tooltip.Content side={side} align="start" sideOffset={10} collisionPadding={12}
    hideWhenDetached className="hypothesis-popup" onClick={event=>event.stopPropagation()}>
    <span className="hypothesis-popup-label">Current hypothesis</span>
    <p>{text}</p>
   </Tooltip.Content>
  </Tooltip.Portal>
 </Tooltip.Root>;
}
