import {Fragment, useEffect, useId, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import glossary from './lessonTerms.json';

type Language = 'en' | 'ko';
const names = Object.keys(glossary).sort((a, b) => b.length - a.length);
const pattern = new RegExp(`(?<![\\w])(${names.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?![\\w])`, 'g');

function Term({name, language}: {name: keyof typeof glossary; language: Language}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({left: 12, top: 0, bottom: undefined as number | undefined});
  const ref = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const id = useId();
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancelLeave = () => clearTimeout(leaveTimer.current);
  const delayLeave = () => { cancelLeave(); leaveTimer.current = setTimeout(() => {if(document.activeElement!==ref.current)setOpen(false);}, 180); };
  useEffect(() => () => clearTimeout(leaveTimer.current), []);
  const entry = glossary[name][language];
  function show() {
    cancelLeave();
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(340, window.innerWidth - 24);
    const above = window.innerHeight - rect.bottom < 220 && rect.top > 220;
    setPosition({left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
      top: above ? 0 : Math.max(12, rect.bottom + 8), bottom: above ? window.innerHeight - rect.top + 8 : undefined});
    setOpen(true);
  }
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node) && !tip.current?.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    const close = (event: Event) => {
      if (event.target instanceof Node && tip.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', key);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', key);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);
  return <><button ref={ref} type="button" className="hyp-term" aria-describedby={open ? id : undefined}
    aria-label={`${name}: ${entry.title}`} onMouseEnter={show} onMouseLeave={delayLeave}
    onFocus={show} onBlur={() => setOpen(false)} onClick={show}>{name}</button>
    {open && createPortal(<div ref={tip} id={id} role="tooltip" lang={language} className="hyp-term-tooltip" onMouseEnter={cancelLeave} onMouseLeave={delayLeave}
      style={{left: position.left, top: position.bottom === undefined ? position.top : undefined, bottom: position.bottom}}>
      <strong>{entry.title}</strong><code>{name}</code><p>{entry.description}</p>
    </div>, document.body)}</>;
}

export default function ExplainTerms({text, language}: {text: string; language: Language}) {
  return <>{text.split(pattern).map((part, index) => Object.hasOwn(glossary, part)
    ? <Term key={index} name={part as keyof typeof glossary} language={language}/>
    : <Fragment key={index}>{part}</Fragment>)}</>;
}
