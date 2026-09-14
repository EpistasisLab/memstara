import { useRunForm } from "../lib/useRunForm";
import { useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Map, Activity, Layers3, Sparkles, ArrowUpRight, X, Pause, Play } from "lucide-react";
import FitOnResize from "../components/FitOnResize";
import EmptyState from "../components/EmptyState";
import Panel from "../components/Panel";
import { nodeTypes } from "../components/nodes";
import { withPlannedAgents } from "../lib/planned";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
import { useScene, useViewer } from "../store/viewer";
import type { SceneAgent, StageId } from "../types";
import "./floor-plan.css";

/**
 * The floor plan: every agent and every store at once, laid out by place.
 *
 * The second of the two agent-state views, and it answers the second question — who is
 * touching what. `ChainPanel` leads with how far along the run is.
 *
 * Places and characters are nodes; a tool call is an animated edge from the character to
 * the store it touched. React Flow gives pan, zoom, a minimap and clean edge routing for
 * free — all of which a hand-rolled SVG had to do without.
 *
 * Places use a spaced grid and agents stay in stage columns. Stable positions prevent
 * simultaneous calls to one store from stacking several characters over one another.
 *
 * This panel shares one slot with `ChainPanel` and the `tabs/*` views: the control panel's
 * nav decides which of them the top-right region holds. `FeedPanel` and `ResultsPanel`
 * stay put.
 */

export default function ScenePanel() {
  const scene = useScene();
  const stale = useViewer(s => !s.newRunMode && (s.snapshot?.stale || !!s.error));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showTools, setShowTools] = useState(true);
  const [motion, setMotion] = useState(true);
  const setView = useViewer((s) => s.setView);
  const selectAgent = useViewer((s) => s.selectAgent);
  const form = useRunForm();

  // The figures the API sent, with the hypothesis station brought to the number the run form
  // asks for (`lib/planned.ts`): short of it, `planned` figures; past it, resting figures
  // dropped and busy ones kept. Everything below counts, places and draws off this list
  // rather than `scene.agents`, so the fan spacing, the fan-in arrows and the header count
  // all describe the same picture.
  //
  // `withPlannedAgents` returns its input unchanged when the two already agree, so the memo
  // below sees the same array it saw last poll.
  const drawn: SceneAgent[] = useMemo(
    () => (scene ? withPlannedAgents(scene.agents, form) : []),
    [scene, form],
  );

  const selected = drawn.find(a => a.id === selectedId);
  const selectedFlash = scene?.flashes.find(f => {
    const source = scene.agents.find(a => a.id === f.agent);
    return selected && (selected.id === f.agent || (selected.stage === "hypothesis" &&
      source?.stage === "hypothesis" && source.playbook === selected.playbook));
  });

  const nodes: Node[] = useMemo(() => {
    if (!scene) return [];

    const places: Node[] = scene.places.map((p, index) => ({
      id: `place-${p.id}`,
      type: "place",
      position: { x: 24 + index * 172, y: 40 },
      data: { place: p },
      draggable: false,
    }));

    const agents: Node[] = drawn.map((a) => {
      // Keep stations stable while tools run. Live edges identify the touched store;
      // moving several agents to that store made their labels occupy the same pixels.
      const stages = ["hypothesis", "data", "ml", "interpreter", "report"];
      const column = stages.indexOf(a.stage);
      const row = drawn.filter(b => b.stage === a.stage).findIndex(b => b.id === a.id);
      const rows = Math.max(form.hypothesis_agents, form.interpret_agents);
      const count = drawn.filter(b => b.stage === a.stage).length;
      const pos = { x: 24 + column * 208, y: 194 + (row + (rows - count) / 2) * 116 };
      return {
        id: `agent-${a.id}`,
        type: "agent",
        position: pos,
        data: { agent: a, step: column + 1, selected: selectedId === a.id, inspect: () => setSelectedId(a.id) },
        draggable: false,
      };
    });

    const rows = Math.max(1, form.hypothesis_agents, form.interpret_agents);
    const zones: Node[] = [
      { id: "resources-zone", type: "zone", position: { x: 0, y: 0 }, zIndex: -2,
        data: { title: "Resources", caption: "Knowledge · Data · Tools", width: 1056, height: 134 }, selectable: false, draggable: false },
      { id: "execution-zone", type: "zone", position: { x: 0, y: 150 }, zIndex: -2,
        data: { title: "Agent workspace", caption: `${form.hypothesis_agents} hypothesis · ${form.interpret_agents} interpretation · 5 stages`,
          width: 1056, height: 164 + (rows - 1) * 116, execution: true }, selectable: false, draggable: false },
    ];
    const focused = drawn.find(a => a.id === selectedId);
    const touched = focused?.last_tool?.store ?? selectedFlash?.place;
    return [...zones, ...places.map(p => ({ ...p, style: { opacity: focused && p.id !== `place-${touched}` &&
      !(focused.carrying !== null && p.id === "place-board") ? .45 : 1 } })),
      ...agents.map(a => ({ ...a, style: { opacity: focused && a.id !== `agent-${focused.id}` ? .58 : 1 } }))];
  }, [scene, drawn, selectedId, selectedFlash]);

  const edges: Edge[] = useMemo(() => {
    if (!scene) return [];

    // A flash is keyed by **worker**, and the colour table is keyed by stage, so the
    // stage has to be looked up rather than cast to. `STAGE_COLOR["hypothesis#2"]` is
    // undefined, which React Flow accepts and draws as a black line — a wrong colour
    // that raises nothing.
    // A plain object rather than a `Map`, because `Map` in this file is the lucide icon
    // this panel's header is drawn with — `new Map(...)` here compiles to a `new` on a
    // React component.
    const stageOf: Record<string, StageId> = {};
    for (const a of scene.agents) stageOf[a.id] = a.stage;

    // Only the newest call per worker. Several at once turns the floor into a cat's
    // cradle and stops meaning anything. Per worker rather than per stage: with three
    // hypothesis workers running, keying this by stage would draw one line and drop two,
    // which is the very thing the scene stopped doing.
    const seen = new Set<string>();
    const live: Edge[] = [];
    const visibleId = (id: string) => {
      const source = scene.agents.find(a => a.id === id);
      return drawn.find(a => a.id === id || (source && a.stage === source.stage &&
        a.playbook === source.playbook))?.id;
    };
    for (const f of scene.flashes) {
      const source = visibleId(f.agent);
      if (!source || !scene.places.some(p => p.id === f.place)) continue;
      if (seen.has(source) || f.place === "unknown") continue;
      seen.add(source);
      const color = STAGE_COLOR[stageOf[f.agent]];
      live.push({
        id: `flash-${f.agent}-${f.at}`,
        source: `agent-${source}`, sourceHandle: "tool",
        target: `place-${f.place}`,
        label: f.tool,
        animated: true,
        style: { stroke: color, strokeWidth: 2.5 },
        labelStyle: { fill: color, fontSize: 12, fontWeight: 700 },
        labelBgStyle: { fill: "#fff" },
        labelBgPadding: [4, 2] as [number, number],
      });
    }

    // A character holding a card keeps a standing line back to the board — the visible
    // form of "claimed but not yet submitted".
    for (const a of drawn) {
      if (a.carrying === null) continue;
      live.push({
        id: `hold-${a.id}`,
        source: `agent-${a.id}`, sourceHandle: "tool",
        target: "place-board",
        style: { stroke: STAGE_COLOR[a.stage], strokeWidth: 1.5, strokeDasharray: "4 4" },
      });
    }

    // The one line on this floor that is not something happening: an arrow from **each**
    // hypothesis figure to the single data figure. It is the shape of the pipeline, not
    // the traffic on it, so it is still and pale where the other two are animated and
    // coloured — a viewer who cannot tell those apart at a glance learns nothing from
    // either.
    //
    // This is what the vertical stack was chosen for (meeting of 2026-08-26): three
    // hypothesis agents above one another, three arrows converging on one data agent, and
    // the fan-in readable without being told. Until 2026-09-08 the stack was drawn and the
    // arrows were not, so the layout was there and the thing it was the layout *for* was
    // missing.
    //
    // Drawn at one hypothesis worker too, not only at two or more. An element that appears
    // only under a non-default flag is an element the default run never checks.
    // Over `drawn`, so a planned figure is wired into the shape like any other. It is the
    // shape of the pipeline that is being drawn here, not the traffic on it, and a figure
    // standing on the floor with no line leaving it would read as one that feeds nothing.
    const flowStages = ["hypothesis", "data", "ml", "interpreter", "report"];
    const pipe: Edge[] = flowStages.slice(0, -1).flatMap((stage, index) =>
      drawn.filter(a => a.stage === stage).flatMap(source =>
        drawn.filter(a => a.stage === flowStages[index + 1]).map(target => ({
          id: `feeds-${source.id}-${target.id}`,
          source: `agent-${source.id}`, sourceHandle: "flow",
          target: `agent-${target.id}`, type: "smoothstep",
          animated: false, selectable: false,
          style: { stroke: "#cbd5e1", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#cbd5e1", width: 14, height: 14 },
        })),
      ),
    );

    // The static arrows go first so React Flow paints them under the flashes: a pale line
    // crossing a live one should be the one that gives way.
    const order = ["data", "ml", "interpreter", "report"];
    for (let i = 0; i < order.length - 1; i++) {
      const from = drawn.find(a => a.stage === order[i]);
      const to = drawn.find(a => a.stage === order[i + 1]);
      if (from && to) pipe.push({ id: `route-${from.id}`, source: `agent-${from.id}`, sourceHandle: "flow",
        target: `agent-${to.id}`, type: "smoothstep", selectable: false,
        style: { stroke: "#b8c5d1", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#b8c5d1" } });
    }
    return [...pipe, ...live];
  }, [scene, drawn]);

  const working = drawn.filter((a) => a.state === "working").length;
  const visibleEdges = edges.filter(e => showTools || (!e.id.startsWith("flash-") && !e.id.startsWith("hold-")))
    .map(e => ({ ...e, animated: Boolean(e.animated && motion),
      className: e.id.startsWith("flash-") ? "floor-tool-edge" : "floor-route-edge",
      style: { ...e.style, opacity: selected && e.source !== `agent-${selected.id}` && e.target !== `agent-${selected.id}` ? .14 : 1 },
    }));

  return (
    <Panel
      icon={Map}
      title="Floor plan"
      // Figures on the floor, planned ones included, because the number beside the title is
      // read as "how many of these am I looking at". `working` below stays on `scene`: a
      // planned figure is not working, and never counting one keeps that number about the
      // pipeline rather than about the form.
      count={scene ? drawn.length : undefined}
      status={
        scene ? (
          <>
            {/* Says what the feed already says about itself. The scene is built from
                who is running *now*, with no run tag anywhere in it — verified: two
                different run_tags return a byte-identical `scene`. Sitting under a
                control rail headed "Run", it reads as though the selector governs it,
                so picking an older run would show the current picture under that run's
                name. Labelling it is the honest half of the fix; actually scoping the
                scene to a run is a larger change and is not done here. */}
            <span>{stale ? "Last known state · connection delayed" : "Selected run"}</span>
            <span>{working} working</span>
          </>
        ) : undefined
      }
      // React Flow measures its own container and draws its own scrollbars; the panel's
      // scroll region must not add a second set.
      bodyClassName="overflow-hidden"
    >
      {!scene ? (
        <EmptyState what="the floor plan" />
      ) : (
        <div className={`floor-observatory ${motion ? "" : "floor-still"}`}>
          <div className="floor-toolbar">
            <div className="floor-title"><span className="floor-emblem"><Layers3 size={18} /></span>
              <div><div className="floor-eyebrow">MEMSTARA / SPATIAL VIEW</div><h3>Research workspace</h3></div>
            </div>
            <div className="floor-actions">
              <span className="floor-live"><Activity size={12} />{working} working</span>
              <button type="button" aria-pressed={showTools} onClick={() => setShowTools(v => !v)}><Layers3 size={13} />Tool activity</button>
              <button type="button" aria-label={motion ? "Pause flow animation" : "Resume flow animation"}
                aria-pressed={motion} onClick={() => setMotion(v => !v)}>{motion ? <Pause size={13} /> : <Play size={13} />}</button>
            </div>
          </div>
          <div className="floor-canvas min-h-0 flex-1">
          <ReactFlow
            nodes={nodes}
            edges={visibleEdges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.08 }}
            minZoom={0.15}
            maxZoom={1.6}
            proOptions={{ hideAttribution: true }}
            nodesConnectable={false}
            elementsSelectable={false}
            onPaneClick={() => setSelectedId(null)}
            onNodeClick={(_, node) => {
              if (node.id === "place-board") setView("board");
              else if (node.id === "place-results") {
                // Results is not a view — its panel is already on screen at bottom-right.
                // On a narrow screen the layout stacks, so bring it into sight instead of
                // swapping this slot for a room that is already open.
                document.getElementById("results-panel")?.scrollIntoView({ behavior: "smooth" });
              } else if (node.type === "agent") {
                const agent = node.data.agent as SceneAgent;
                // Nothing to open for a figure that has not run — its agent row may not
                // exist yet. Same rule as `ChainPanel`.
                setSelectedId(agent.id);
              }
            }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={0.65} color="#dfe6eb" />
            <Controls showInteractive={false} />
            <FitOnResize padding={0.08} />
          </ReactFlow>
          <div className="floor-map-key" aria-hidden="true"><span><i />Stage sequence</span><span><i className="floor-key-tool" />Recent tool call</span></div>
          </div>
          <div className="floor-inspector" aria-live="polite">
            {selected ? <>
              <div className="floor-inspector-icon" style={{ color: STAGE_COLOR[selected.stage] }}><Sparkles size={18} /></div>
              <div className="floor-inspector-copy"><strong>{selected.label} <span>{STATE_LABEL[selected.state]}</span></strong>
                <p>{selected.playbook ? `Skill: ${selected.playbook}` : "Default stage instructions"}
                  {selected.carrying !== null ? ` · Task #${selected.carrying}` : ""}
                  {selected.running > 1 ? ` · ${selected.running} concurrent workers` : ""}</p>
                <p>{selected.last_tool || selectedFlash ? `Last observed tool: ${selected.last_tool?.tool ?? selectedFlash?.tool}` : "No tool activity recorded for this agent."}</p>
              </div>
              {selected.state !== "planned" && <button className="floor-details" onClick={() => { selectAgent(selected.name); setView("agents"); }}>Details <ArrowUpRight size={14} /></button>}
              <button className="floor-close" aria-label="Clear agent selection" onClick={() => setSelectedId(null)}><X size={15} /></button>
            </> : <><div className="floor-inspector-icon"><Sparkles size={18} /></div><div className="floor-inspector-copy">
              <strong>One view. Multiple research paths.</strong>
              <p>Select an agent to trace its connections. Shared stages can represent multiple workers.</p>
              <p>Tool activity shows recent observations, not continuous data transfer. Scope: selected run.</p>
            </div></>}
          </div>
        </div>
      )}
    </Panel>
  );
}
