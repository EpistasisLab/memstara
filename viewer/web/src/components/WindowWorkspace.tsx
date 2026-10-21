import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { ChevronDown, ChevronUp, Settings2, X, HelpCircle, Maximize2, Minimize2, RotateCcw } from "lucide-react";

import {WorkspaceEvidenceContext} from "./WorkspaceEvidenceContext";
import { workspaceGeometry } from "../lib/workspaceGeometry";
import "./workspace-docking.css";
import HeaderStatus from "./HeaderStatus";
import {WorkspaceHeaderContext} from "./WorkspaceHeaderContext";
import WorkspaceActions from "./WorkspaceActions";
import "./workspace-topbar.css";
import "./pipeline-workspace-header.css";
import ViewErrorBoundary from './ViewErrorBoundary';
import ExplorationSummary from "./ExplorationSummary";
import ThemeToggle from "./ThemeToggle";
import ModelConnectionDialog from "./ModelConnectionDialog";

type Box = { x: number; y: number; w: number; h: number };
type Item = { id: string; title: string; content: ReactNode };
const key = "memstara-windows-v1";
const secondary = ["feed", "results", "report"];
const collapsible = ["navigation", ...secondary];
// Keep evidence panel headers accessible while prioritizing the question workspace.
const initiallyClosed: string[] = ["results", "report"];
const edges = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];
export default function WindowWorkspace({ items, toolbar }: { items: Item[]; toolbar?:ReactNode }) {
  const [pipelineHeader,setPipelineHeader]=useState<HTMLDivElement|null>(null);
  const root = useRef<HTMLDivElement>(null);
  const overviewDialog = useRef<HTMLDialogElement>(null);
  const settingsDialog = useRef<HTMLDialogElement>(null);
  const [overviewOpen, setOverviewOpen] = useState(false);
  const openOverview = () => { setOverviewOpen(true); overviewDialog.current?.showModal(); };
  const closeOverview = () => { overviewDialog.current?.close(); setOverviewOpen(false); };
  const [bounds, setBounds] = useState({ w: 1400, h: 900 });
  const [boxes, setBoxes] = useState<Record<string, Box>>(() => {
    try { const parsed = JSON.parse(localStorage.getItem(key) || "{}");
      return Object.fromEntries(Object.entries(parsed).filter(([id, b]) => {
        if (["pipeline", "control", ...collapsible].includes(id)) return false;
        const box = b as Box; return box && [box.x, box.y, box.w, box.h].every(Number.isFinite) && box.w >= 180 && box.h >= 180;
      })) as Record<string, Box>;
    } catch { return {}; }
  });
  const [collapsed, setCollapsed] = useState<string[]>(initiallyClosed);
  const toggle = (id: string) => {
    setCollapsed(previous => previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id]);
    // Reclaim the freed space instead of keeping the old half-height pipeline box.
    setBoxes(previous => Object.fromEntries(Object.entries(previous).filter(([key]) => !["pipeline", ...collapsible].includes(key))));
    setMaximized("");
    drag.current = null;
  };
  const [front, setFront] = useState("");
  const [maximizedId, setMaximized] = useState("");
  const maximized = items.some(item=>item.id===maximizedId) ? maximizedId : "";
  const fullscreenEvidence=secondary.includes(maximized);
  const maximizeEvidence=(id:string)=>{setCollapsed(previous=>previous.filter(value=>value!==id));setActivePanel(id);setMaximized(id);};
  const closeEvidence=()=>{setCollapsed(previous=>Array.from(new Set([...previous,maximized])));setMaximized('');};
  useEffect(()=>{
    if(!fullscreenEvidence)return;
    const previous=document.activeElement as HTMLElement|null;
    const panel=document.getElementById(`workspace-${maximized}`);
    panel?.focus();
    const keydown=(event:KeyboardEvent)=>{
      if(document.querySelector('dialog[open]'))return;
      if(event.key==='Escape'){event.preventDefault();closeEvidence();}
      if(event.key==='Tab'&&panel){
        const focusable=Array.from(panel.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')).filter(el=>el.getClientRects().length);
        const first=focusable[0],last=focusable.at(-1);
        if(!first){event.preventDefault();panel.focus();}
        else if(event.shiftKey&&(document.activeElement===first||document.activeElement===panel)){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    };
    document.addEventListener('keydown',keydown);
    return()=>{document.removeEventListener('keydown',keydown);if(previous?.isConnected)previous.focus();};
  },[fullscreenEvidence,maximized]);
  const drag = useRef<{ id: string; edge: string; x: number; y: number; box: Box } | null>(null);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setBounds({ w: entry.contentRect.width, h: entry.contentRect.height }));
    if (root.current) observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(boxes)); } catch { /* Private browsing. */ } }, [boxes]);
  const [activePanel, setActivePanel] = useState("results");
  const [splitOffset, setSplitOffset] = useState(0);
  const opened = items.filter(item=>secondary.includes(item.id)&&!collapsed.includes(item.id));
  const layout = workspaceGeometry(bounds.w,bounds.h,opened.map(item=>item.id),splitOffset);
  const active = opened.some(item=>item.id===activePanel)?activePanel:opened[0]?.id;
  const initial = (id:string):Box => layout.boxes[id] ?? {x:232,y:0,w:280,h:520};
  const fit = (box:Box,id:string):Box => {
    const slot=initial(id),w=Math.min(slot.w,Math.max(Math.min(slot.w,280),box.w));
    const h=Math.min(slot.h,Math.max(Math.min(slot.h,id==="pipeline"?520:280),box.h));
    return {w,h,x:Math.max(slot.x,Math.min(box.x,slot.x+slot.w-w)),y:Math.max(slot.y,Math.min(box.y,slot.y+slot.h-h))};
  };
  return <div className="window-workspace-shell">
    <a className="workspace-skip-link" href="#workspace-pipeline">Skip to current view</a>
    <header className="memstara-header unified-topbar">
      <div className="memstara-identity-row">
      <div className="memstara-brand" aria-label="Memstara">
        <svg className="memstara-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true">
          <rect x="1" y="1" width="46" height="46" rx="14" fill="currentColor" />
          <path d="M11 33V15L24 28L37 15V33" stroke="rgb(var(--accent-contrast))" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="11" cy="15" r="2.5" fill="rgb(var(--accent-contrast))"/><circle cx="24" cy="28" r="2.5" fill="rgb(var(--accent-contrast))"/><circle cx="37" cy="15" r="2.5" fill="rgb(var(--accent-contrast))"/>
        </svg>
        <div><strong>Memstara</strong><span>Research workspace</span></div>
      </div>
      <HeaderStatus onOpen={openOverview} />
      <nav className="topbar-actions" aria-label="Workspace tools">
        <button className="topbar-overview" aria-label="Exploration overview" aria-haspopup="dialog" onClick={openOverview}>Overview<ChevronDown size={14}/></button>
        {toolbar}
        <button className="topbar-settings" aria-label="Workspace settings" title="Model connection, system status and window layout" aria-haspopup="dialog" onClick={()=>settingsDialog.current?.showModal()}><Settings2 size={18}/><span>Settings</span></button>
        <span className="workspace-theme-control"><ThemeToggle /></span>
      </nav>
      </div>
    </header>
    <dialog ref={overviewDialog} className="workspace-dialog topbar-dialog topbar-overview-dialog" aria-labelledby="topbar-overview-title" onCancel={()=>setOverviewOpen(false)}>
      <header><h2 id="topbar-overview-title">Exploration overview</h2><button aria-label="Close overview" onClick={closeOverview}><X size={18}/></button></header>
      {overviewOpen && <div onClick={event=>{ if ((event.target as HTMLElement).closest(".exploration-summary-grid button")) closeOverview(); }}><ExplorationSummary /></div>}
    </dialog>
    <dialog ref={settingsDialog} className="workspace-dialog topbar-dialog" aria-labelledby="topbar-settings-title">
      <header><h2 id="topbar-settings-title">Workspace settings</h2><button aria-label="Close settings" onClick={()=>settingsDialog.current?.close()}><X size={18}/></button></header>
      <p className="topbar-settings-description">Manage connections and arrange your workspace.</p>
      <div className="topbar-settings-connections"><ModelConnectionDialog /><WorkspaceActions only="status"/></div>
      <details open className="workspace-layout-disclosure">

        <summary><span className="workspace-layout-label"><Maximize2 size={14}/>Window layout</span><span className="workspace-layout-caption">Show, hide or reset workspace panels</span><ChevronDown size={14} className="workspace-layout-chevron"/></summary>
        <div className="workspace-tools-layout" role="group" aria-label="Window layout">
          <div className="workspace-panel-toggles">
            {items.filter(item => collapsible.includes(item.id)).map(item => <button key={item.id} type="button"
              aria-expanded={!collapsed.includes(item.id)} aria-controls={`workspace-${item.id}`}
              onClick={() => toggle(item.id)}>
              {collapsed.includes(item.id) ? <ChevronDown size={14} /> : <ChevronUp size={14} />}{item.title}
            </button>)}
          </div>
          <div className="workspace-layout-actions">
            <button type="button" onClick={() => { setBoxes({}); setMaximized(""); setSplitOffset(0); setCollapsed(initiallyClosed); }}><RotateCcw size={14} />Reset window layout</button>
            <button type="button" className="workspace-layout-help" aria-label="Window layout help" title="Move windows by dragging their title bars. Resize using an edge or corner. Use the window buttons to show or hide a panel."><HelpCircle size={16}/></button>
          </div>
        </div>
      </details>
    </dialog>
    <div className="window-workspace docked-workspace" ref={root} role="main" aria-label="Research workspace">
      <div className="workspace-surface" style={{height:layout.contentHeight}}>
      {!!opened.length && !maximized && <div className="workspace-evidence-bar" style={{left:layout.x,top:layout.panelY-42,width:layout.w}}>
        <div role="tablist" aria-label="Analysis panels">
          {opened.map(item=><button key={item.id} role="tab"
            aria-selected={layout.tabbed?active===item.id:!collapsed.includes(item.id)}
            onKeyDown={event=>{const tabs=Array.from(event.currentTarget.parentElement!.querySelectorAll<HTMLButtonElement>('[role="tab"]'));const index=tabs.indexOf(event.currentTarget);const next=event.key==="ArrowRight"?(index+1)%tabs.length:event.key==="ArrowLeft"?(index+tabs.length-1)%tabs.length:event.key==="Home"?0:event.key==="End"?tabs.length-1:-1;if(next>=0){event.preventDefault();tabs[next].focus();tabs[next].click();}}} aria-controls={`workspace-${item.id}`}
            onClick={()=>{if(collapsed.includes(item.id))toggle(item.id);setActivePanel(item.id);}}>
            {item.id==="feed"?"Activity feed":item.id==="results"?"Results":"Final report"}
          </button>)}
        </div>
        <button className="workspace-split-handle" aria-label="Resize pipeline and analysis space" title="Drag to give the pipeline more or less room; arrow keys also work."
          onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);drag.current={id:"split",edge:"split",x:e.clientX,y:e.clientY,box:{x:0,y:splitOffset,w:0,h:0}};}}
          onPointerMove={e=>{if(drag.current?.id==="split") {setSplitOffset(Math.max(-500,Math.min(480,drag.current.box.y+e.clientY-drag.current.y)));setBoxes({});}}}
          onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}
          onKeyDown={e=>{if(["ArrowUp","ArrowDown"].includes(e.key)){e.preventDefault();setSplitOffset(v=>Math.max(-500,Math.min(480,v+(e.key==="ArrowDown"?24:-24))));setBoxes({});}}}>↕ Resize</button>
      </div>}
      {items.filter(item => !collapsed.includes(item.id)).map(item => {
        const normal = fit(item.id === "control" ? initial(item.id) : boxes[item.id] || initial(item.id),item.id);
        const leftInset = layout.x;
        const box = maximized === item.id ? { x: leftInset, y: initial("pipeline").y, w: bounds.w - leftInset, h: Math.max(520,bounds.h-initial("pipeline").y) } : normal;
        const begin = (event: React.PointerEvent, edge: string) => {
          if (item.id === "control" || event.button !== 0 || maximized === item.id) return;
          event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
          setFront(item.id); drag.current = { id: item.id, edge, x: event.clientX, y: event.clientY, box: normal };
        };
        return <section key={item.id} id={`workspace-${item.id}`} tabIndex={-1} aria-label={`${item.title} window`} className={`floating-window ${fullscreenEvidence&&maximized===item.id?"is-evidence-fullscreen":""}`} hidden={(!!maximized && item.id!=="control" && maximized!==item.id)||(!maximized && layout.tabbed && secondary.includes(item.id) && active!==item.id)}
          style={{ "--dock-x": `${box.x}px`, "--dock-y": `${box.y}px`, "--dock-w": `${box.w}px`, "--dock-h": `${box.h}px`, left: box.x, top: box.y, width: box.w, height: box.h, zIndex: item.id === "control" ? 40 : maximized === item.id ? 30 : front === item.id ? 20 : 1 } as CSSProperties}
          onPointerDownCapture={() => setFront(item.id)}
          onPointerMove={event => {
            const d = drag.current; if (!d || d.id !== item.id) return;
            const dx = event.clientX - d.x, dy = event.clientY - d.y, b = { ...d.box };
            if (d.edge === "move") { b.x += dx; b.y += dy; }
            else {
              if (d.edge.includes("e")) b.w = Math.max(item.id === "control" ? 200 : 280, Math.min(bounds.w - b.x, b.w + dx));
              if (d.edge.includes("s")) b.h = Math.max(180, Math.min(bounds.h - b.y, b.h + dy));
              if (d.edge.includes("w")) { b.x = Math.max(0, Math.min(b.x + dx, d.box.x + d.box.w - (item.id === "control" ? 200 : 280))); b.w = d.box.x + d.box.w - b.x; }
              if (d.edge.includes("n")) { b.y = Math.max(0, Math.min(b.y + dy, d.box.y + d.box.h - 180)); b.h = d.box.y + d.box.h - b.y; }
            }
            setBoxes(prev => ({ ...prev, [item.id]: fit(b,item.id) }));
          }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }}>
          <div className="window-titlebar" onPointerDown={event => { if (!(event.target as HTMLElement).closest('button,input,select,summary,a,[data-workspace-header]')) begin(event, "move"); }}>
            <span title={item.title}>{item.title}</span>
            {item.id==="pipeline"&&<div data-workspace-header className="workspace-header-slot" ref={setPipelineHeader}/> }
            <div className="flex items-center gap-1">
            {collapsible.includes(item.id) && <button className="window-collapse" aria-label={`Collapse ${item.title}`} title="Collapse this window"
              onClick={() => toggle(item.id)}><ChevronDown size={13} /></button>}
            <button data-help="Reset window layout" data-help-description="Restore this window to its default size and position. Pipeline settings and results are not changed." aria-label={`Reset ${item.title} window`} title="Reset this window to its default size and position"
              onClick={() => {
                setBoxes(previous => { const next = { ...previous }; delete next[item.id]; return next; });
                if (maximized === item.id) setMaximized("");
              }}><RotateCcw size={13} /></button>
            {item.id !== "control" && <button data-help={maximized === item.id ? "Restore window" : "Maximize window"} data-help-description={maximized === item.id ? "Return this window to its previous workspace layout." : "Expand this window to use the available workspace. Click again to restore the layout."} aria-label={`${maximized === item.id ? "Restore" : "Maximize"} ${item.title} window`} onClick={() => {if(fullscreenEvidence&&maximized===item.id)closeEvidence();else setMaximized(maximized===item.id?"":item.id);}}>
              {maximized === item.id ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>}
            </div>
          </div>
          <div className="window-content"><ViewErrorBoundary key={item.id === "pipeline" ? item.title.split(" · ")[0] : item.id} name={item.title}><WorkspaceEvidenceContext.Provider value={item.id==='pipeline'?<div className="workspace-evidence-launchers" role="group" aria-label="Analysis views">{items.filter(entry=>['results','report'].includes(entry.id)).map(entry=><button key={entry.id} type="button" aria-label={`Open ${entry.id==='results'?'Results':'Final report'} full screen`} onClick={()=>maximizeEvidence(entry.id)}><span>{entry.id==='results'?'Results':'Final report'}</span><Maximize2 size={13} aria-hidden="true"/></button>)}</div>:null}><WorkspaceHeaderContext.Provider value={item.id==="pipeline"?pipelineHeader:null}>{item.content}</WorkspaceHeaderContext.Provider></WorkspaceEvidenceContext.Provider></ViewErrorBoundary></div>
          {item.id !== "control" && !maximized && edges.map(edge => <div key={edge} role={edge === "se" ? "separator" : undefined} tabIndex={edge === "se" ? 0 : -1}
            aria-valuenow={edge === "se" ? Math.round(normal.w) : undefined}
            aria-valuemin={edge === "se" ? Math.min(200, bounds.w) : undefined}
            aria-valuemax={edge === "se" ? Math.round(bounds.w) : undefined}
            aria-valuetext={edge === "se" ? `${Math.round(normal.w)} pixels wide, ${Math.round(normal.h)} pixels tall. Use arrow keys to resize.` : undefined}
            aria-label={edge === "se" ? `Resize ${item.title}` : undefined} aria-orientation={edge === "se" ? "vertical" : undefined}
            className={`window-edge window-edge-${edge}`} onPointerDown={event => begin(event, edge)}
            onKeyDown={event => {
              if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
              event.preventDefault();
              const dx = event.key === 'ArrowRight' ? 20 : event.key === 'ArrowLeft' ? -20 : 0;
              const dy = event.key === 'ArrowDown' ? 20 : event.key === 'ArrowUp' ? -20 : 0;
              setBoxes(prev => ({ ...prev, [item.id]: fit({ ...normal, w: normal.w + dx, h: normal.h + dy },item.id) }));
            }} />)}
        </section>;
      })}
      </div>
    </div>

  </div>;
}
