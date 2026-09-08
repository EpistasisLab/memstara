import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AlertTriangle, Workflow } from "lucide-react";
import EmptyState from "../components/EmptyState";
import FitOnResize from "../components/FitOnResize";
import Panel from "../components/Panel";
import { chainEdgeTypes, chainNodeTypes } from "../components/chain";
import { CHAIN, chainAgents, elapsedSince, linkIsLive } from "../lib/chain";
import { STAGE_COLOR } from "../lib/stage";
import { useScene, useViewer } from "../store/viewer";

/**
 * The pipeline as a left-to-right chain: six stages drawn as five cards in the order they
 * run, four links between them, and a dot travelling along a link while work is flowing
 * into the stage on its right. The curator shares the first card with the hypothesis
 * stage — `lib/chain.ts:CHAIN` says why.
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
 * zooming, no minimap. Five cards in a fixed row are not a map to be explored, and a reader
 * who has dragged the layout off-screen has only lost the picture.
 */

/** Card width plus the gap. Nothing else depends on it — `fitView` scales the row to
 *  whatever the panel is, so this only sets how the cards sit relative to each other.
 *
 *  It has to move whenever the card does: the card is `w-44` (176px), so this leaves
 *  56px between cards. Change one without the other and they either crowd or drift. */
const STEP_X = 232;

export default function ChainPanel() {
  const scene = useScene();
  const fetchedAt = useViewer((s) => s.fetchedAt);
  const setView = useViewer((s) => s.setView);
  const selectAgent = useViewer((s) => s.selectAgent);
  // Read for the *badge* only. What an empty canvas says is `EmptyState`'s job now.
  //
  // It may not pre-empt a scene we already have. The store keeps the last good snapshot
  // through a failure on purpose (it sets `error` beside it, not instead of it), and a
  // panel that reads `error` first throws that away: one dropped poll — which at p90
  // 1.09s against a 2s interval is a routine event, not an outage — wiped a correctly
  // drawn pipeline and put a sentence in its place for a tick.
  const error = useViewer((s) => s.error);
  // A 200 the API filled from its own previous answer because it gave up waiting for a
  // fresh one. It is not an error — nothing failed — but the picture is older than the
  // response, so it earns the same badge for the same reason.
  const stale = useViewer((s) => s.snapshot?.stale ?? false);

  // One step per stage, however many workers are running it — see `chainAgents`.
  const steps = useMemo(() => chainAgents(scene?.agents ?? []), [scene]);

  const nodes: Node[] = useMemo(() => {
    // One `now` for the whole frame, so two cards can never disagree about the time by a
    // millisecond and render "3s" beside "2s" for the same instant.
    const now = Date.now();

    return steps.map(({ agent, workers }, i) => ({
      id: `chain-${agent.stage}`,
      type: "chain",
      position: { x: i * STEP_X, y: 0 },
      // While a run is open, `since` is when it opened; otherwise the freshest thing the
      // stage has is its last tool call. The state word beside the figure says which of
      // the two is being counted.
      data: {
        agent,
        workers,
        step: i + 1,
        elapsed: elapsedSince(agent.since ?? agent.last_tool?.at ?? null, now),
      },
      draggable: false,
      selectable: false,
    }));
  }, [steps, fetchedAt]);

  const edges: Edge[] = useMemo(
    () =>
      steps.slice(0, -1).map(({ agent: from }, i) => {
        const to = steps[i + 1].agent;
        const live = linkIsLive(to);
        const color = STAGE_COLOR[to.stage];
        return {
          id: `link-${from.stage}-${to.stage}`,
          type: "chain",
          source: `chain-${from.stage}`,
          target: `chain-${to.stage}`,
          data: { live, color },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: live ? color : "#dcdbd4",
          },
        };
      }),
    [steps],
  );

  // Counted over the workers the scene sent, not over the five cards: with three
  // hypothesis workers running, "1 working" would be true of the cards and wrong about
  // the pipeline.
  const working = scene?.agents.filter((a) => a.state === "working").length ?? 0;
  // Measured browser-clock to browser-clock, unlike the ages on the cards. "Is this screen
  // still live" must not be answerable only when two machines' clocks agree.
  const age = fetchedAt === null ? null : Math.max(0, Math.round((Date.now() - fetchedAt) / 1000));

  return (
    <Panel
      icon={Workflow}
      title="Pipeline"
      count={steps.length || undefined}
      status={
        scene ? (
          <>
            {/* The whole message goes in `title`, not on screen: the header has room for
                a few words, and "why" is what someone hovers for. `age` beside it is
                already counting up, so the two together say "stale, and this stale". */}
            {(error !== null || stale) && (
              <span
                className="flex items-center gap-1 font-medium text-amber-700"
                title={
                  error !== null
                    ? `The API did not answer: ${error}`
                    : "The API gave up waiting for fresh data and re-sent its previous answer."
                }
              >
                <AlertTriangle className="h-3 w-3" strokeWidth={2.4} />
                not updating
              </span>
            )}
            {/* Same caveat as the floor plan, and for the same reason: these cards come
                from `scene`, which carries no run tag at all. The run selector above
                changes the board and the results beneath it but cannot change this. */}
            <span title="The pipeline always shows what is running now, not the run selected above.">
              All runs
            </span>
            <span>{working} working</span>
            {age !== null && <span className="font-mono">{age}s ago</span>}
          </>
        ) : undefined
      }
      bodyClassName="overflow-hidden"
    >
      {/* Only ever reached before the first successful response. After that there is a
          scene, and a scene is drawn whatever else is going on — an old picture with a
          badge saying so beats a blank one. */}
      {!scene ? (
        <EmptyState what="the pipeline" />
      ) : steps.length < CHAIN.length ? (
        // Not padded with placeholders: a stage the API did not send is a definitions
        // problem, and inventing a grey card for it would hide exactly that.
        <div className="p-8 text-ink-faint">
          Only {steps.length} of {CHAIN.length} stages came back from the API.
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
              const step = steps.find((s) => `chain-${s.agent.stage}` === node.id);
              if (!step) return;
              selectAgent(step.agent.name);
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
