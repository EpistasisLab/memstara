import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useBoard, useScene, useViewer } from "../store/viewer";
import { STAGE_COLOR } from "../lib/stage";
import { nodeTypes } from "./nodes";
import type { StageId } from "../types";

/**
 * The floor plan, as a React Flow graph.
 *
 * Places and characters are nodes; a tool call is an animated edge from the character
 * to the store it touched. React Flow gives pan, zoom, a minimap and clean edge routing
 * for free — all of which a hand-rolled SVG had to do without.
 *
 * Positions come from the API (stores.PLACES / HOME), so the layout stays in one place
 * and a character cannot end up somewhere its place no longer is.
 */

export default function Scene() {
  const scene = useScene();
  const board = useBoard();
  const setTab = useViewer((s) => s.setTab);
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
      const pos = at ? { x: at.x - 64, y: at.y + 80 } : { x: a.home.x - 64, y: a.home.y };
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

    // Only the newest call per agent. Several at once turns the floor into a cat's
    // cradle and stops meaning anything.
    const seen = new Set<string>();
    const live: Edge[] = [];
    for (const f of scene.flashes) {
      if (seen.has(f.agent) || f.place === "unknown") continue;
      seen.add(f.agent);
      live.push({
        id: `flash-${f.agent}-${f.at}`,
        source: `agent-${f.agent}`,
        target: `place-${f.place}`,
        label: f.tool,
        animated: true,
        style: { stroke: STAGE_COLOR[f.agent as StageId], strokeWidth: 2.5 },
        labelStyle: { fill: STAGE_COLOR[f.agent as StageId], fontSize: 11, fontWeight: 700 },
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
        style: { stroke: STAGE_COLOR[a.id], strokeWidth: 1.5, strokeDasharray: "4 4" },
      });
    }

    return live;
  }, [scene]);

  if (!scene) return <div className="p-8 text-ink-faint">장면을 불러오는 중…</div>;

  return (
    <div className="h-[calc(100vh-9.5rem)] w-full">
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
          if (node.id === "place-board") setTab("board");
          else if (node.id === "place-results") setTab("results");
          else if (node.type === "agent") {
            selectAgent((node.data.agent as { name: string }).name);
            setTab("agents");
          }
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#dcdbd4" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) =>
            n.type === "agent" ? STAGE_COLOR[(n.data.agent as { id: StageId }).id] : "#dcdbd4"
          }
          className="!bg-white"
        />
      </ReactFlow>
    </div>
  );
}
