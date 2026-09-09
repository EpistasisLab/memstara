import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Map } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Panel from "../components/Panel";
import { nodeTypes } from "../components/nodes";
import { STAGE_COLOR } from "../lib/stage";
import { useBoard, useScene, useViewer } from "../store/viewer";
import type { StageId } from "../types";

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
 * Positions come from the API (`stores.PLACES` / `stores.HOME`), so the layout stays in
 * one place and a character cannot end up somewhere its place no longer is.
 *
 * This panel shares one slot with `ChainPanel` and the `tabs/*` views: the control panel's
 * nav decides which of them the top-right region holds. `FeedPanel` and `ResultsPanel`
 * stay put.
 */

export default function ScenePanel() {
  const scene = useScene();
  const board = useBoard();
  const setView = useViewer((s) => s.setView);
  const selectAgent = useViewer((s) => s.selectAgent);

  const nodes: Node[] = useMemo(() => {
    if (!scene) return [];

    const counts: Record<string, number> = {
      board: board?.tasks.filter((t) => t.status !== "done").length ?? 0,
      results: board?.tasks.filter((t) => t.status === "done").length ?? 0,
    };

    const places: Node[] = scene.places.map((p) => ({
      id: `place-${p.id}`,
      type: "place",
      position: { x: p.x - 112, y: p.y - 40 },
      data: { place: p, count: counts[p.id] },
      draggable: false,
    }));

    const agents: Node[] = scene.agents.map((a) => {
      // Working characters stand at the store they last touched; the rest stay home.
      const at = a.state === "working" && a.at
        ? scene.places.find((p) => p.id === a.at)
        : null;
      const base = at ? { x: at.x - 64, y: at.y + 80 } : { x: a.home.x - 64, y: a.home.y };
      // Several workers of one stage would otherwise be drawn on the same spot — the
      // position is settled by the station or the store, and every worker of a stage
      // shares both. Stacking upwards rather than sideways: the five homes sit 175 apart
      // on one row (`stores.HOME`), so a sideways fan walks into the next stage's slot,
      // whereas the space above the row is empty down to y=300. The small x step keeps
      // the figures from looking like one column and hiding the one behind.
      //
      // **One of the five stations stacks** (`stores.SPLITTABLE`), and the row has room
      // for a stack at any of them: a figure is 128 wide, so three span 172 and clear the
      // next station's column by 3px — the same 3px everywhere, because it is the same
      // 175. Three is therefore the ceiling and it is not enforced here: the limit belongs
      // to the drawing, so it lives where the drawing's requests are checked
      // (`_MAX_HYPOTHESIS_AGENTS` in `src/memstara/control/request.py`). Clamping the slot
      // here would put two workers on one spot, which is what this line exists to prevent.
      //
      // `slot` is 0 for a stage running a single worker, so this is a no-op for a
      // default run and the floor plan is pixel-identical to what it was.
      const pos = { x: base.x + a.slot * 22, y: base.y - a.slot * 62 };
      return {
        id: `agent-${a.id}`,
        type: "agent",
        position: pos,
        data: { agent: a },
        draggable: false,
      };
    });

    return [...places, ...agents];
  }, [scene, board]);

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
    for (const f of scene.flashes) {
      if (seen.has(f.agent) || f.place === "unknown") continue;
      seen.add(f.agent);
      const color = STAGE_COLOR[stageOf[f.agent]];
      live.push({
        id: `flash-${f.agent}-${f.at}`,
        source: `agent-${f.agent}`,
        target: `place-${f.place}`,
        label: f.tool,
        animated: true,
        style: { stroke: color, strokeWidth: 2.5 },
        labelStyle: { fill: color, fontSize: 11, fontWeight: 700 },
        labelBgStyle: { fill: "#fff" },
        labelBgPadding: [4, 2] as [number, number],
      });
    }

    // A character holding a card keeps a standing line back to the board — the visible
    // form of "claimed but not yet submitted".
    for (const a of scene.agents) {
      if (a.carrying === null) continue;
      live.push({
        id: `hold-${a.id}`,
        source: `agent-${a.id}`,
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
    const dataFigure = scene.agents.find((a) => a.stage === "data");
    const pipe: Edge[] = dataFigure
      ? scene.agents
          .filter((a) => a.stage === "hypothesis")
          .map((a) => ({
            id: `feeds-${a.id}`,
            source: `agent-${a.id}`,
            target: `agent-${dataFigure.id}`,
            animated: false,
            selectable: false,
            style: { stroke: "#cbd5e1", strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#cbd5e1",
                         width: 14, height: 14 },
          }))
      : [];

    // The static arrows go first so React Flow paints them under the flashes: a pale line
    // crossing a live one should be the one that gives way.
    return [...pipe, ...live];
  }, [scene]);

  const working = scene?.agents.filter((a) => a.state === "working").length ?? 0;

  return (
    <Panel
      icon={Map}
      title="Floor plan"
      count={scene?.agents.length}
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
            <span title="The floor plan always shows what is running now, not the run selected above.">
              All runs
            </span>
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
        <div className="h-full w-full">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.4}
            maxZoom={1.6}
            proOptions={{ hideAttribution: true }}
            nodesConnectable={false}
            onNodeClick={(_, node) => {
              if (node.id === "place-board") setView("board");
              else if (node.id === "place-results") {
                // Results is not a view — its panel is already on screen at bottom-right.
                // On a narrow screen the layout stacks, so bring it into sight instead of
                // swapping this slot for a room that is already open.
                document.getElementById("results-panel")?.scrollIntoView({ behavior: "smooth" });
              } else if (node.type === "agent") {
                selectAgent((node.data.agent as { name: string }).name);
                setView("agents");
              }
            }}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#dcdbd4" />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              nodeColor={(n) =>
                n.type === "agent"
                  ? STAGE_COLOR[(n.data.agent as { stage: StageId }).stage]
                  : "#dcdbd4"
              }
              className="!bg-white"
            />
          </ReactFlow>
        </div>
      )}
    </Panel>
  );
}
