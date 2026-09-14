import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp, HelpCircle, Maximize2, Minimize2, RotateCcw } from "lucide-react";

import ExplorationSummary from "./ExplorationSummary";
import ThemeToggle from "./ThemeToggle";

type Box = { x: number; y: number; w: number; h: number };
type Item = { id: string; title: string; content: ReactNode };
const key = "memstara-windows-v1";
const secondary = ["feed", "results", "report"];
const collapsible = ["navigation", ...secondary];
const initiallyClosed = ["navigation", "feed", "results"];
const edges = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];
export default function WindowWorkspace({ items, toolbar }: { items: Item[]; toolbar?:ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [bounds, setBounds] = useState({ w: 1400, h: 900 });
  const [boxes, setBoxes] = useState<Record<string, Box>>(() => {
    try { const parsed = JSON.parse(localStorage.getItem(key) || "{}");
      return Object.fromEntries(Object.entries(parsed).filter(([id, b]) => {
        if (["pipeline", ...collapsible].includes(id)) return false;
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
  const [maximized, setMaximized] = useState("");
  const drag = useRef<{ id: string; edge: string; x: number; y: number; box: Box } | null>(null);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setBounds({ w: entry.contentRect.width, h: entry.contentRect.height }));
    if (root.current) observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(boxes)); } catch { /* Private browsing. */ } }, [boxes]);
  const fit = (box: Box): Box => {
    const w = Math.min(Math.max(280, box.w), bounds.w), h = Math.min(Math.max(180, box.h), bounds.h);
    return { w, h, x: Math.max(0, Math.min(box.x, bounds.w - w)), y: Math.max(0, Math.min(box.y, bounds.h - h)) };
  };
  const initial = (id: string): Box => {
    const control = Math.min(320, Math.max(280, bounds.w * .2)), nav = items.some(i => i.id === "navigation") && !collapsed.includes("navigation") ? 280 : 0;
    const x = control + 12 + (nav ? nav + 12 : 0), w = Math.max(240, bounds.w - x);
    const opened = items.filter(item => secondary.includes(item.id) && !collapsed.includes(item.id));
    const columns = Math.max(1, Math.min(opened.length, Math.floor((w + 12) / 292)));
    const rows = Math.max(1, Math.ceil(opened.length / columns));
    const top = opened.length ? (bounds.h - 12) * (rows > 1 ? .45 : .68) : bounds.h;
    if (id === "control") return fit({ x: 0, y: 0, w: control, h: bounds.h });
    if (id === "navigation") return fit({ x: control + 12, y: 0, w: nav, h: bounds.h });
    if (id === "pipeline") return fit({ x, y: 0, w, h: top });
    const index = Math.max(0, opened.findIndex(item => item.id === id));
    const width = (w - 12 * (columns - 1)) / columns;
    const height = (bounds.h - top - 12 * rows) / rows;
    return fit({ x: x + (index % columns) * (width + 12), y: top + 12 + Math.floor(index / columns) * (height + 12), w: width, h: height });
  };
  return <div className="window-workspace-shell">
    <header className="memstara-header">
      <div className="memstara-brand" aria-label="Memstara">
        <svg className="memstara-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true">
          <rect x="1" y="1" width="46" height="46" rx="14" fill="currentColor" />
          <path d="M11 33V15L24 28L37 15V33" stroke="rgb(var(--accent-contrast))" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="11" cy="15" r="2.5" fill="rgb(var(--accent-contrast))"/><circle cx="24" cy="28" r="2.5" fill="rgb(var(--accent-contrast))"/><circle cx="37" cy="15" r="2.5" fill="rgb(var(--accent-contrast))"/>
        </svg>
        <div><strong>Memstara</strong><span>Research workspace</span></div>
      </div>
      <ExplorationSummary />
    </header>
    <div className="workspace-toolbar flex min-h-10 shrink-0 flex-wrap items-center gap-3 px-3 text-xs text-ink-soft">
      <div className="workspace-tools-primary">{toolbar}</div>
      <div className="workspace-tools-layout" role="group" aria-label="Window layout">
      <button className="workspace-layout-help" aria-label="Window layout help" title="Move windows by dragging their title bars. Resize using an edge or corner. Use the window buttons to show or hide a panel."><HelpCircle size={16}/></button>
      <button className="flex items-center gap-1 rounded px-2 py-1 hover:bg-paper-panel" onClick={() => { setBoxes({}); setMaximized(""); setCollapsed(initiallyClosed); }}><RotateCcw size={13} />Reset window layout</button>
      {items.filter(item => collapsible.includes(item.id)).map(item => <button key={item.id} type="button"
        aria-expanded={!collapsed.includes(item.id)} aria-controls={`workspace-${item.id}`}
        onClick={() => toggle(item.id)} className="flex items-center gap-1 rounded border border-paper-line bg-white px-3 py-1 font-semibold hover:bg-paper-panel">
        {collapsed.includes(item.id) ? <ChevronDown size={14} /> : <ChevronUp size={14} />}{item.title}
      </button>)}
      <span className="workspace-theme-control"><ThemeToggle /></span>
      </div>
    </div>
    <div className="window-workspace" ref={root}>
      {items.filter(item => !collapsed.includes(item.id)).map(item => {
        const normal = fit(boxes[item.id] || initial(item.id));
        const box = maximized === item.id ? { x: 0, y: 0, w: bounds.w, h: bounds.h } : normal;
        const begin = (event: React.PointerEvent, edge: string) => {
          if (event.button !== 0 || maximized === item.id) return;
          event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
          setFront(item.id); drag.current = { id: item.id, edge, x: event.clientX, y: event.clientY, box: normal };
        };
        return <section key={item.id} id={`workspace-${item.id}`} aria-label={`${item.title} window`} className="floating-window"
          style={{ left: box.x, top: box.y, width: box.w, height: box.h, zIndex: maximized === item.id ? 30 : front === item.id ? 20 : 1 }}
          onPointerDownCapture={() => setFront(item.id)}
          onPointerMove={event => {
            const d = drag.current; if (!d || d.id !== item.id) return;
            const dx = event.clientX - d.x, dy = event.clientY - d.y, b = { ...d.box };
            if (d.edge === "move") { b.x += dx; b.y += dy; }
            else {
              if (d.edge.includes("e")) b.w = Math.max(280, Math.min(bounds.w - b.x, b.w + dx));
              if (d.edge.includes("s")) b.h = Math.max(180, Math.min(bounds.h - b.y, b.h + dy));
              if (d.edge.includes("w")) { b.x = Math.max(0, Math.min(b.x + dx, d.box.x + d.box.w - 280)); b.w = d.box.x + d.box.w - b.x; }
              if (d.edge.includes("n")) { b.y = Math.max(0, Math.min(b.y + dy, d.box.y + d.box.h - 180)); b.h = d.box.y + d.box.h - b.y; }
            }
            setBoxes(prev => ({ ...prev, [item.id]: fit(b) }));
          }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }}>
          <div className="window-titlebar" onPointerDown={event => { if (!(event.target as HTMLElement).closest('button')) begin(event, "move"); }}>
            <span>{item.title}</span>
            <div className="flex items-center gap-1">
            {collapsible.includes(item.id) && <button className="window-collapse" aria-label={`Collapse ${item.title}`} title="Collapse this window"
              onClick={() => toggle(item.id)}><ChevronDown size={13} /></button>}
            <button aria-label={`Reset ${item.title} window`} title="Reset this window to its default size and position"
              onClick={() => {
                setBoxes(previous => { const next = { ...previous }; delete next[item.id]; return next; });
                if (maximized === item.id) setMaximized("");
              }}><RotateCcw size={13} /></button>
            <button aria-label={`${maximized === item.id ? "Restore" : "Maximize"} ${item.title} window`} onClick={() => setMaximized(maximized === item.id ? "" : item.id)}>
              {maximized === item.id ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
            </div>
          </div>
          <div className="window-content">{item.content}</div>
          {!maximized && edges.map(edge => <div key={edge} role="separator" tabIndex={0}
            aria-label={`Resize ${item.title} ${edge}`} aria-orientation={edge === "n" || edge === "s" ? "horizontal" : "vertical"}
            className={`window-edge window-edge-${edge}`} onPointerDown={event => begin(event, edge)}
            onKeyDown={event => {
              if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
              event.preventDefault();
              const dx = event.key === 'ArrowRight' ? 20 : event.key === 'ArrowLeft' ? -20 : 0;
              const dy = event.key === 'ArrowDown' ? 20 : event.key === 'ArrowUp' ? -20 : 0;
              setBoxes(prev => ({ ...prev, [item.id]: fit({ ...normal, w: normal.w + dx, h: normal.h + dy }) }));
            }} />)}
        </section>;
      })}
    </div>
  </div>;
}
