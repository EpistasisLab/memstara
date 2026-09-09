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
import { playbookAt, withPlannedAgents, withPlaybookAt } from "../lib/planned";
import { STAGE_COLOR } from "../lib/stage";
import { PLAYBOOK_STAGES, useControl, type PlaybookStage } from "../store/control";
import { useScene, useViewer } from "../store/viewer";

/**
 * The pipeline as a left-to-right chain: six stages drawn as five columns in the order they
 * run, links between them, and a dot travelling along a link while work is flowing into the
 * stage on its right. The curator shares the first column with the hypothesis stage —
 * `lib/chain.ts:CHAIN` says why.
 *
 * **The first column is a stack.** The hypothesis station draws one card per worker and
 * every one of them points at the single data card, which is the screen the 2026-08-26
 * meeting adopted over three tabs and over three complete pipeline rows

 * one card however many workers run behind them and carry the count as a badge — the same
 * split `stores.SPLITTABLE` makes on the floor plan, decided in the same meeting.
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

/** The gap between two cards of one stacked column.
 *
 *  A card is between about 76px and 124px tall depending on how many of its optional lines
 *  it is showing — the standard, the held card, the last tool — so this is the tallest of
 *  those plus a margin rather than a measurement. React Flow does not lay out; a value too
 *  small overlaps two cards silently, and `fitView` scales whatever this produces to the
 *  panel, so being generous costs only zoom. */
const ROW_Y = 148;

/** Whether `stage` is one the form has a `playbook_<stage>` field for.
 *
 *  `SceneAgent.stage` is `StageId`, which includes `curator` — a stage with no playbook
 *  field and no `{{playbook}}` prompt. Narrowing here rather than casting is what keeps a
 *  card from building `playbook_curator`, a key the service refuses as unknown. */
function isPlaybookStage(stage: string): stage is PlaybookStage {
  return (PLAYBOOK_STAGES as readonly string[]).includes(stage);
}

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

  // The run form, which is what makes this panel answer to the control beside it: the
  // hypothesis column holds the number the form asks for, with the ones no worker has
  // opened a run for yet drawn as `planned`. `lib/planned.ts` holds the one exception —
  // a figure that is not resting is never taken off the screen by a number changing.
  //
  // The whole form rather than the two fields that are read, because the store holds it as
  // one object and a selector returning a slice of it would allocate a new one on every
  // call, which is the shape zustand re-renders on. Editing an unrelated field therefore
  // re-runs the memo below; it is a pure function over five cards, called on a keystroke.
  const form = useControl((s) => s.form);
  const setForm = useControl((s) => s.setForm);
  // Which stages can be handed a standard at all, read off the prompt files by the service
  // (`GET /control/playbooks`). Not a list written here: a prompt gains a `{{playbook}}`
  // line and a card gains a select, with no edit to this panel.
  const playbookStages = useControl((s) => s.playbookStages);

  // One column per stage; the hypothesis column holds one card per worker — see
  // `chainAgents`.
  const steps = useMemo(
    () => chainAgents(withPlannedAgents(scene?.agents ?? [], form)),
    [scene, form],
  );

  // **While anything is running, every card is read-only.** A card must then show what the
  // run is actually using — `agent.playbook`, which came from the database — and that is
  // not a value a select can change: a control offering to change it would be claiming the
  // screen can re-skill a worker mid-run.
  //
  // Read off the scene rather than off `useControl(s => s.running)`, because that field is
  // only set for a run *this* control service started. A pipeline launched by hand in a
  // terminal has workers on this screen and no entry there, and it must lock the cards just
  // the same.
  const live = (scene?.agents ?? []).some(
    (a) => a.state === "working" || a.state === "moving",
  );

  const nodes: Node[] = useMemo(() => {
    // One `now` for the whole frame, so two cards can never disagree about the time by a
    // millisecond and render "3s" beside "2s" for the same instant.
    const now = Date.now();

    return steps.flatMap(({ agents }, i) =>
      agents.map((agent, row) => {
        // A stage the service says can take one, and nothing running to contradict the
        // form. Both halves are needed: `curator` has no playbook field at all, and a live
        // run makes the whole column a report rather than a control.
        const stage = isPlaybookStage(agent.stage) ? agent.stage : null;
        const editable = !live && stage !== null && playbookStages.includes(stage);
        return {
          id: `chain-${agent.id}`,
          type: "chain",
          // The column is centred on its own stack, so the four single-card columns line up
          // with the middle of the hypothesis stack rather than with its top. A stack of one
          // puts its card at y=0, which is where every card was before this panel stacked
          // anything — a default run is laid out exactly as it always was.
          position: { x: i * STEP_X, y: (row - (agents.length - 1) / 2) * ROW_Y },
          // While a run is open, `since` is when it opened; otherwise the freshest thing the
          // stage has is its last tool call. The state word beside the figure says which of
          // the two is being counted.
          data: {
            agent,
            step: i + 1,
            elapsed: elapsedSince(agent.since ?? agent.last_tool?.at ?? null, now),
            editable,
            // The form's value for this card's slot, which is what the select shows. Slot
            // comes from the figure, and `withPlannedAgents` is what put the figure there,
            // so card *i* of the hypothesis column and select *i* of the field are the same
            // slot by construction rather than by two counts agreeing.
            choice: stage ? playbookAt(form, stage, agent.slot) : "",
            onPlaybook: (book: string) => {
              if (!stage) return;
              setForm((f) => withPlaybookAt(f, stage, agent.slot, book));
            },
          },
          draggable: false,
          selectable: false,
        };
      }),
    );
  }, [steps, fetchedAt, form, live, playbookStages, setForm]);

  const edges: Edge[] = useMemo(
    () =>
      // Every card of one column to every card of the next. With only the hypothesis
      // station splitting that is a fan-in of N arrows onto the single data card and then
      // one arrow per link the rest of the way — which is the meeting's figure. Written
      // as a full cross product rather than special-casing `hypothesis` so that the panel
      // stays correct if `stores.SPLITTABLE` ever gains a station; it would then be wrong
      // about nothing, only busy.
      steps.slice(0, -1).flatMap(({ agents: from }, i) =>
        from.flatMap((source) =>
          steps[i + 1].agents.map((to) => {
            const live = linkIsLive(to);
            const color = STAGE_COLOR[to.stage];
            return {
              id: `link-${source.id}-${to.id}`,
              type: "chain",
              source: `chain-${source.id}`,
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
        ),
      ),
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
              // Found by figure id, not by stage: with three hypothesis cards on screen a
              // stage lookup would send all three to the same agent — the one thing three
              // separate cards exist to stop.
              const agent = steps
                .flatMap((s) => s.agents)
                .find((a) => `chain-${a.id}` === node.id);
              if (!agent) return;
              // A planned card has no agent page to go to. Its `name` is the row the run
              // *would* provision, and that row may not exist yet, so following it would
              // land on an empty panel — worse than not moving at all.
              if (agent.state === "planned") return;
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
