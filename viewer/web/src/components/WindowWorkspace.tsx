import { useEffect, useRef, useState, type ReactNode } from "react";
import { Maximize2, Minimize2, RotateCcw } from "lucide-react";

type Box = { x: number; y: number; w: number; h: number };
type Item = { id: string; title: string; content: ReactNode };
const key = "memstara-windows-v1";
const edges = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];
export default function WindowWorkspace({ items }: { items: Item[] }) {
  const root = useRef<HTMLDivElement>(null);
  const [bounds, setBounds] = useState({ w: 1400, h: 900 });
  const [boxes, setBoxes] = useState<Record<string, Box>>(() => {
    try { const parsed = JSON.parse(localStorage.getItem(key) || "{}");
      return Object.fromEntries(Object.entries(parsed).filter(([, b]) => {
        const box = b as Box; return box && [box.x, box.y, box.w, box.h].every(Number.isFinite) && box.w >= 180 && box.h >= 180;
      })) as Record<string, Box>;
    } catch { return {}; }
  });
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
    const w = Math.min(Math.max(200, box.w), bounds.w), h = Math.min(Math.max(180, box.h), bounds.h);
    return { w, h, x: Math.max(0, Math.min(box.x, bounds.w - w)), y: Math.max(0, Math.min(box.y, bounds.h - h)) };
  };
  const initial = (id: string): Box => {
    const control = 240, nav = items.some(i => i.id === "navigation") ? 240 : 0;
    const x = control + 12 + (nav ? nav + 12 : 0), w = Math.max(240, bounds.w - x);
    const top = (bounds.h - 12) * .58;
    if (id === "control") return fit({ x: 0, y: 0, w: control, h: bounds.h });
    if (id === "navigation") return fit({ x: control + 12, y: 0, w: nav, h: bounds.h });
    if (id === "pipeline") return fit({ x, y: 0, w, h: top });
    return fit({ x: x + (id === "results" ? (w + 12) / 2 : 0), y: top + 12, w: (w - 12) / 2, h: bounds.h - top - 12 });
  };
  return <div className="window-workspace-shell">
    <div className="flex h-10 shrink-0 items-center gap-3 px-3 text-xs text-ink-soft">
      <span className="hidden lg:inline">Drag a title bar to move · Drag an edge or corner to resize</span>
      <button className="flex items-center gap-1 rounded px-2 py-1 hover:bg-paper-panel" onClick={() => { setBoxes({}); setMaximized(""); }}><RotateCcw size={13} />Reset window layout</button>
    </div>
    <div className="window-workspace" ref={root}>
      {items.map(item => {
        const normal = fit(boxes[item.id] || initial(item.id));
        const box = maximized === item.id ? { x: 0, y: 0, w: bounds.w, h: bounds.h } : normal;
        const begin = (event: React.PointerEvent, edge: string) => {
          if (event.button !== 0 || maximized === item.id) return;
          event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
          setFront(item.id); drag.current = { id: item.id, edge, x: event.clientX, y: event.clientY, box: normal };
        };
        return <section key={item.id} aria-label={`${item.title} window`} className="floating-window"
          style={{ left: box.x, top: box.y, width: box.w, height: box.h, zIndex: maximized === item.id ? 30 : front === item.id ? 20 : 1 }}
          onPointerDownCapture={() => setFront(item.id)}
          onPointerMove={event => {
            const d = drag.current; if (!d || d.id !== item.id) return;
            const dx = event.clientX - d.x, dy = event.clientY - d.y, b = { ...d.box };
            if (d.edge === "move") { b.x += dx; b.y += dy; }
            else {
              if (d.edge.includes("e")) b.w = Math.max(200, Math.min(bounds.w - b.x, b.w + dx));
              if (d.edge.includes("s")) b.h = Math.max(180, Math.min(bounds.h - b.y, b.h + dy));
              if (d.edge.includes("w")) { b.x = Math.max(0, Math.min(b.x + dx, d.box.x + d.box.w - 200)); b.w = d.box.x + d.box.w - b.x; }
              if (d.edge.includes("n")) { b.y = Math.max(0, Math.min(b.y + dy, d.box.y + d.box.h - 180)); b.h = d.box.y + d.box.h - b.y; }
            }
            setBoxes(prev => ({ ...prev, [item.id]: fit(b) }));
          }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }}>
          <div className="window-titlebar" onPointerDown={event => { if (!(event.target as HTMLElement).closest('button')) begin(event, "move"); }}>
            <span>{item.title}</span>
            <div className="flex items-center gap-1">
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
