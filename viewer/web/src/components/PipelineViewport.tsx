import { useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Panel, useReactFlow, useViewport } from "@xyflow/react";
import { Expand, Maximize2, Minimize2, Minus, Plus, Scan } from "lucide-react";

/** Keep the reader's viewport through telemetry polls and panel resizing. */
export default function PipelineViewport({ expanded, toggle, topology, entryId, leftGutter = 0, dockInto }: {
  expanded: boolean; toggle: () => void; topology: string; entryId?: string; leftGutter?: number; dockInto?: HTMLElement|null;
}) {
  const docked=dockInto!==undefined;
  const { getNodes, getNodesBounds, setViewport, fitView, zoomIn, zoomOut, viewportInitialized } = useReactFlow();
  const { x, y, zoom } = useViewport();
  const initialized = useRef("");
  const readable = useCallback(() => {
    const nodes = getNodes();
    const entry = nodes.find(node => entryId ? node.id === entryId : node.id === "stage-knowledge" || node.id.endsWith("-source"));
    // Anchor the opening view to its input card, not the top of a tall agent stack.
    const bounds = getNodesBounds(entry ? [entry] : nodes);
    void setViewport({ x: 16 + leftGutter - bounds.x, y: (docked?24:116) - bounds.y, zoom: 1 }, { duration: 250 });
  }, [getNodes, getNodesBounds, setViewport, entryId, leftGutter,docked]);
  useEffect(() => {
    // Card positions are fixed; decorative node measurements must not block entry.
    if (!viewportInitialized || initialized.current === topology) return;
    initialized.current = topology;
    readable();
  }, [viewportInitialized, topology, readable]);
  const button = "flex h-8 items-center justify-center gap-1 rounded-md px-2 text-xs font-medium text-ink-soft hover:bg-paper focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink";
  const controls=<>
    <Panel position="top-left" className="pipeline-toolbar !m-3 flex flex-wrap items-center gap-1 rounded-xl border border-paper-line bg-white/95 p-1 shadow-sm backdrop-blur">
      <button className={button} onClick={() => void zoomOut({ duration: 180 })} aria-label="Zoom out"><Minus size={15} /></button>
      <button className={`${button} min-w-14 font-mono`} onClick={readable} title="Readable size (100%)">{Math.round(zoom * 100)}%</button>
      <button className={button} onClick={() => void zoomIn({ duration: 180 })} aria-label="Zoom in"><Plus size={15} /></button>
      <span className="mx-1 h-5 border-l border-paper-line" />
      <button className={button} onClick={readable}><Scan size={15} />Readable</button>
      <button className={button} onClick={() => void fitView({ padding: { top: docked?"24px":"116px", bottom: docked?"24px":"56px", left: `${32 + leftGutter}px`, right: "32px" }, duration: 250, maxZoom: 1 })}><Expand size={15} />Fit all</button>
      <select aria-label="Focus pipeline stage" value="" className={`${button} max-w-36 bg-transparent`}
        onChange={event => {
          const nodes = getNodes().filter(node => node.id === `stage-${event.target.value}` || node.id.endsWith(`-${event.target.value === "knowledge" ? "source" : event.target.value}`) ||
            (node.data.agent as { stage?: string } | undefined)?.stage === event.target.value);
          if (!nodes.length) return;
          const bounds = getNodesBounds(nodes);
          void setViewport({ x: 16 - bounds.x, y: (docked?24:116) - bounds.y, zoom: 1 }, { duration: 250 });
        }}>
        <option value="" disabled>Go to stage…</option>
        <option value="knowledge">Knowledge sources</option>
        <option value="hypothesis">1 · Hypothesis</option><option value="data">2 · Data</option>
        <option value="ml">3 · ML</option><option value="interpreter">4 · Interpretation</option><option value="report">5 · Report</option>
      </select>
      <button className={button} onClick={toggle} aria-pressed={expanded}>
        {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}{expanded ? "Restore" : "Expand"}
      </button>
    </Panel>
    <Panel position="bottom-right" className="!m-3 flex gap-1 rounded-lg border border-paper-line bg-white p-1" >
      {([{ label: "left", dx: 160, dy: 0, glyph: "←" }, { label: "up", dx: 0, dy: 160, glyph: "↑" },
        { label: "down", dx: 0, dy: -160, glyph: "↓" }, { label: "right", dx: -160, dy: 0, glyph: "→" }]).map(direction =>
        <button key={direction.label} type="button" className={button} aria-label={`Pan pipeline ${direction.label}`}
          onClick={() => void setViewport({ x: x + direction.dx, y: y + direction.dy, zoom }, { duration: 180 })}>{direction.glyph}</button>)}
    </Panel>
    <Panel position="bottom-left" className="pipeline-gesture-hint !m-3 rounded-md bg-white/90 px-2 py-1 text-[12px] text-ink-faint">
      Drag to explore · Scroll to move · Pinch or Ctrl + scroll to zoom
    </Panel>
  </>;
  return docked?(dockInto?createPortal(controls,dockInto):null):controls;
}
