import { useEffect, useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Workflow } from "lucide-react";
import Panel from "../components/Panel";
import { chainEdgeTypes, chainNodeTypes } from "../components/chain";
import { CHAIN, chainAgents, elapsedSince, linkIsLive } from "../lib/chain";
import { STAGE_COLOR } from "../lib/stage";
import { useScene, useViewer } from "../store/viewer";
import type { StageId } from "../types";

/**
 * The pipeline as a left-to-right chain: six stages in the order they run, five links
 * between them, and a dot travelling along a link while work is flowing into the stage on
 * its right.
 *
 * This is the default view because it is the one that answers the first question anyone
 * asks of a running pipeline — how far along is it. The floor plan answers "who is
 * touching what", which is the second question.
 *
 * Two things it refuses to do, both copied from other people's mistakes:
 *
 *  - It never infers position by walking the chain. Every card reads its own state (see
 *    `lib/chain.ts:linkIsLive`), because stages here genuinely overlap and a single
 *    "we are at step 3" pointer would be wrong most of the time.
 *  - It never draws a tick. Nothing in the snapshot distinguishes "finished" from "not
 *    started yet", so both are `idle`, and both are drawn as `idle`.
 *
 * The canvas keeps React Flow's edge routing and drops everything else: no panning, no
 * zooming, no minimap. Six cards in a fixed row are not a map to be explored, and a reader
 * who has dragged the layout off-screen has only lost the picture.
 */

/** Card width plus the gap. Nothing else depends on it — `fitView` scales the row to
 *  whatever the panel is, so this only sets how the cards sit relative to each other. */
const STEP_X = 232;

/** `fitView` fits once, at mount. The panel is inside a responsive grid that restacks at
 *  `lg`, so without this the row keeps the width it had when it first drew. */
function FitOnResize() {
  const { fitView } = useReactFlow();

  useEffect(() => {
    const refit = () => void fitView({ padding: 0.08, duration: 0 });
    window.addEventListener("resize", refit);
    return () => window.removeEventListener("resize", refit);
  }, [fitView]);

  return null;
}

export default function ChainPanel() {
  const scene = useScene();
  const fetchedAt = useViewer((s) => s.fetchedAt);
  const setView = useViewer((s) => s.setView);
  const selectAgent = useViewer((s) => s.selectAgent);

  const agents = useMemo(() => chainAgents(scene?.agents ?? []), [scene]);

  const nodes: Node[] = useMemo(() => {
    // One `now` for the whole frame, so two cards can never disagree about the time by a
    // millisecond and render "3s" beside "2s" for the same instant.
    const now = Date.now();

    return agents.map((agent, i) => ({
      id: `chain-${agent.id}`,
      type: "chain",
      position: { x: i * STEP_X, y: 0 },
      // While a run is open, `since` is when it opened; otherwise the freshest thing the
      // stage has is its last tool call. The state word beside the figure says which of
      // the two is being counted.
      data: {
        agent,
        step: i + 1,
        elapsed: elapsedSince(agent.since ?? agent.last_tool?.at ?? null, now),
      },
      draggable: false,
      selectable: false,
    }));
  }, [agents, fetchedAt]);

  const edges: Edge[] = useMemo(
    () =>
      agents.slice(0, -1).map((from, i) => {
        const to = agents[i + 1];
        const live = linkIsLive(to);
        const color = STAGE_COLOR[to.id as StageId];
        return {
          id: `link-${from.id}-${to.id}`,
          type: "chain",
          source: `chain-${from.id}`,
          target: `chain-${to.id}`,
          data: { live, color },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: live ? color : "#dcdbd4",
          },
        };
      }),
    [agents],
  );

  const working = agents.filter((a) => a.state === "working").length;
  // Measured browser-clock to browser-clock, unlike the ages on the cards. "Is this screen
  // still live" must not be answerable only when two machines' clocks agree.
  const age = fetchedAt === null ? null : Math.max(0, Math.round((Date.now() - fetchedAt) / 1000));

  return (
    <Panel
      icon={Workflow}
      title="Pipeline"
      count={agents.length || undefined}
      status={
        scene ? (
          <>
            <span>{working} working</span>
            {age !== null && <span className="font-mono">{age}s ago</span>}
          </>
        ) : undefined
      }
      bodyClassName="overflow-hidden"
    >
      {!scene ? (
        <div className="p-8 text-ink-faint">Loading the pipeline…</div>
      ) : agents.length < CHAIN.length ? (
        // Not padded with placeholders: a stage the API did not send is a definitions
        // problem, and inventing a grey card for it would hide exactly that.
        <div className="p-8 text-ink-faint">
          Only {agents.length} of {CHAIN.length} stages came back from the API.
        </div>
      ) : (
        <div className="h-full w-full">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={chainNodeTypes}
            edgeTypes={chainEdgeTypes}
            fitView
            fitViewOptions={{ padding: 0.08 }}
            minZoom={0.25}
            maxZoom={1}
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnDrag={false}
            panOnScroll={false}
            zoomOnScroll={false}
            zoomOnPinch={false}
            zoomOnDoubleClick={false}
            preventScrolling={false}
            onNodeClick={(_, node) => {
              const agent = agents.find((a) => `chain-${a.id}` === node.id);
              if (!agent) return;
              selectAgent(agent.name);
              setView("agents");
            }}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#dcdbd4" />
            <FitOnResize />
          </ReactFlow>
        </div>
      )}
    </Panel>
  );
}
