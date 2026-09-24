import { useRunForm } from "../lib/useRunForm";
import { useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Activity, AlertTriangle, ArrowUpRight, Sparkles, Workflow, X } from "lucide-react";
import EmptyState from "../components/EmptyState";
import PipelineSummary from "../components/PipelineSummary";
import PathProgress from "../components/PathProgress";
import PipelineViewport from "../components/PipelineViewport";
import Panel from "../components/Panel";
import { chainEdgeTypes, chainNodeTypes } from "../components/chain";
import { CHAIN, chainAgents, elapsedSince, linkIsLive } from "../lib/chain";
import {
  MAX_HYPOTHESIS_AGENTS,
  playbookAt,
  withPlannedAgents,
  withPlaybookAt,
  withoutSlot,
  withoutInterpreterSlot,
} from "../lib/planned";
import { STAGE_COLOR } from "../lib/stage";
import { PLAYBOOK_STAGES, useControl, type PlaybookStage } from "../store/control";
import { useScene, useViewer } from "../store/viewer";



/** A 280px card with 80px of routing space between stages. */
const STEP_X = 360;

/** Reserve room for skill, state and tool details without overlapping stacked cards. */
const ROW_Y = 340;

/** Whether `stage` is one the form has a `playbook_<stage>` field for.
 *
 *  `SceneAgent.stage` is `StageId`, which includes `curator` — a stage with no playbook
 *  field and no `{{playbook}}` prompt. Narrowing here rather than casting is what keeps a
 *  card from building `playbook_curator`, a key the service refuses as unknown. */
function isPlaybookStage(stage: string): stage is PlaybookStage {
  return (PLAYBOOK_STAGES as readonly string[]).includes(stage);
}

export default function ChainPanel() {
  const [inspectedId, setInspectedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!expanded) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape" && !document.querySelector("dialog[open]")) setExpanded(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [expanded]);
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
  const newRunMode = useViewer((s) => s.newRunMode);
  const savedKnowledge = useViewer(s => s.snapshot?.run_configuration?.skill);
  const interpretationMode = useViewer((s) => s.snapshot?.run_configuration?.interpretation_mode);
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
  const form = useRunForm();
  const controlledRun = useControl(s => s.running);
  const submitting = useControl(s => s.busy);
  const setForm = useControl((s) => s.setForm);
  // Which stages can be handed a standard at all, read off the prompt files by the service
  // (`GET /control/playbooks`). Not a list written here: a prompt gains a `{{playbook}}`
  // line and a card gains a select, with no edit to this panel.
  const playbookStages = useControl((s) => s.playbookStages);

  // One column per stage; the hypothesis column holds one card per worker — see
  // `chainAgents`.
  const steps = useMemo(
    () => chainAgents(withPlannedAgents(scene?.agents ?? [], form, newRunMode)),
    [scene, form, newRunMode],
  );
  const inspected = useMemo(
    () => steps.flatMap((step) => step.agents).find((agent) => agent.id === inspectedId) ?? null,
    [steps, inspectedId],
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
  const live = !!controlledRun || submitting || (scene?.agents ?? []).some(
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
        const editable = !live && !useControl.getState().running && stage !== null && stage !== "data" && playbookStages.includes(stage);
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
            inspected: inspectedId === agent.id,
            onInspect: () => setInspectedId(agent.id),
            step: i + 1,
            elapsed: elapsedSince(agent.since ?? agent.last_tool?.at ?? null, now),
            editable,
            predictiveModel: stage === "ml" ? form.evaluation.engine : null,
            // The form's value for this card's slot, which is what the select shows. Slot
            // comes from the figure, and `withPlannedAgents` is what put the figure there,
            // so card *i* of the hypothesis column and select *i* of the field are the same
            // slot by construction rather than by two counts agreeing.
            choice: stage ? playbookAt(form, stage, agent.slot) : "",
            onConfigure: () => stage && useControl.getState().openEditor(stage, agent.slot),
            onPlaybook: (book: string) => {
              if (!stage) return;
              setForm((f) => withPlaybookAt(f, stage, agent.slot, book));
            },
            // Only a figure the form invented and nothing has started. See `onRemove` in
            // `ChainNodeData` for why an observed card does not get one.
            onRemove:
              !live && !useControl.getState().running && agent.stage === "hypothesis" && form.hypothesis_agents > 1
                ? () => setForm((f) => withoutSlot(f, agent.slot))
                : !live && !useControl.getState().running && agent.stage === "interpreter" && form.interpret_agents > 1
                ? () => setForm((f) => withoutInterpreterSlot(f, agent.slot))
                : null,
          },
          draggable: false,
          selectable: false,
        };
      }),
    );
  }, [steps, fetchedAt, form, live, playbookStages, setForm, inspectedId]);

  // Keep each expansion control directly beneath its stage's last card.
  const addNodes: Node[] = useMemo(() => {
    if (live) return [];
    return steps.flatMap((step, column) => {
      const stage = step.stage;
      if (stage !== "hypothesis" && stage !== "interpreter") return [];
      const count = stage === "hypothesis" ? form.hypothesis_agents : form.interpret_agents;
      const maximum = stage === "hypothesis" ? MAX_HYPOTHESIS_AGENTS : 4;
      const rows = step.agents.length;
      return [{
        id: stage === "hypothesis" ? "chain-add" : "chain-add-interpreter",
        type: "chainAdd",
        position: { x: column * STEP_X, y: (rows - (rows - 1) / 2) * ROW_Y },
        data: {
          stage,
          maximum,
          onAdd: () => useControl.getState().openEditor(stage, count, true),
          atCeiling: count >= maximum,
        },
        draggable: false,
        selectable: false,
      }];
    });
  }, [steps, live, form.hypothesis_agents, form.interpret_agents]);

  const lanes: Node[] = useMemo(() => {
    const rows = Math.max(1, ...steps.map(step => step.agents.length));
    const labels = [
      ["Hypothesis", "Generate ideas from knowledge"], ["Data", "Select the relevant features"],
      ["Machine learning", "Evaluate predictive evidence"], ["Interpretation", "Explain meaning and limitations"],
      ["Explanation", "Recommend promising hypotheses"],
    ];
    return steps.map((step, i) => ({
      id: `stage-${step.stage}`, type: "pipelineStage", zIndex: -1,
      position: { x: i * STEP_X - 16, y: -(rows - 1) / 2 * ROW_Y - 90 },
      data: { title: labels[i][0], purpose: labels[i][1], color: STAGE_COLOR[step.stage],
        count: step.agents.length, height: rows * ROW_Y + 140, step: i + 1 },
      selectable: false, draggable: false, focusable: false,
    }));
  }, [steps]);

  const edges: Edge[] = useMemo(
    () =>
      steps.slice(0, -1).flatMap(({ agents: from }, i) =>
        from.flatMap((source) =>
          steps[i + 1].agents.map((to) => {
            // Multiple incoming branches need task evidence; a busy destination
            // alone does not mean every hypothesis is feeding it right now.
            const live = linkIsLive(to) && (from.length === 1 ||
              (source.carrying !== null && source.carrying === to.carrying));
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
    <div className={expanded ? "fixed inset-3 z-40 grid rounded-xl bg-paper shadow-2xl" : "grid min-h-0 min-w-0"}>
    <Panel
      icon={Workflow}
      title="Pipeline"

      status={
        scene ? (
          <>
            {/* The whole message goes in `title`, not on screen: the header has room for
                a few words, and "why" is what someone hovers for. `age` beside it is
                already counting up, so the two together say "stale, and this stale". */}
            {!newRunMode && (error !== null || stale) && (
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
            <span>Selected run</span>
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
      {!scene && !newRunMode ? (
        <EmptyState what="the pipeline" />
      ) : steps.length < CHAIN.length ? (
        // Not padded with placeholders: a stage the API did not send is a definitions
        // problem, and inventing a grey card for it would hide exactly that.
        <div className="p-8 text-ink-faint">
          Only {steps.length} of {CHAIN.length} stages came back from the API.
        </div>
      ) : (
        <div className="flex h-full w-full min-h-0 flex-col">
          <PipelineSummary />
          <p className="px-4 py-2 text-xs text-ink-soft" role="note">
            {newRunMode || interpretationMode === "all_per_hypothesis"
              ? "Each ML result goes to every configured interpreter. Their perspectives are combined into one result per hypothesis, then synthesized in the report."
              : "This saved run uses shared interpretation workers: each ML result is handled by one available interpreter."}
          </p>
          <div className="min-h-0 flex-1">
            <ReactFlow
            nodes={[...lanes, ...nodes, ...addNodes, {
              id: "stage-knowledge", type: "knowledge", position: { x: -STEP_X, y: 0 },
              selectable: false, draggable: false,
              data: { value: newRunMode ? form.skill : savedKnowledge ?? null,
                locked: live, saved: !newRunMode,
                onChange: (skill: string) => setForm(f => ({ ...f, skill })) },
            }]}
            edges={[...edges, ...(steps[0]?.agents ?? []).map(agent => ({
              id: `knowledge-${agent.id}`, source: "stage-knowledge", target: `chain-${agent.id}`,
              type: "smoothstep", style: { stroke: "var(--color-ink-faint, #96958e)" },
              markerEnd: { type: MarkerType.ArrowClosed },
            }))]}
            nodeTypes={chainNodeTypes}
            edgeTypes={chainEdgeTypes}
            defaultViewport={{ x: STEP_X + 16, y: 116, zoom: 1 }}
            minZoom={0.25}
            maxZoom={1.75}
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnDrag
            panOnScroll
            zoomOnScroll={false}
            zoomOnPinch
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
              setInspectedId(agent.id);
            }}
          >
            <Background className="pipeline-background" variant={BackgroundVariant.Dots} gap={22} size={1} color="#dcdbd4" />
            <PipelineViewport expanded={expanded} toggle={() => setExpanded(value => !value)}
              topology={steps.map(step => `${step.stage}:${step.agents.length}`).join("|")} />
            </ReactFlow>
          </div>
          <details className="shrink-0 border-t border-paper-line bg-white">
            <summary className="cursor-pointer px-4 py-2 text-xs font-bold text-ink-soft">Hypothesis progress · Expand individual paths</summary>
            <PathProgress />
          </details>
          <div className="border-t border-paper-line bg-paper-panel px-3 py-2" aria-live="polite">
            {inspected ? (
              <div className="flex items-center gap-3 text-[12px]">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-paper text-ink-soft">
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 font-bold text-ink">
                    <span className="truncate">{inspected.label}</span>
                    <span className="font-normal text-ink-faint">{inspected.state}</span>
                  </div>
                  <div className="truncate text-ink-faint">
                    {inspected.playbook ? `Skill: ${inspected.playbook}` : "Default stage instructions"}
                    {inspected.carrying !== null ? ` · Task #${inspected.carrying}` : ""}
                    {inspected.running > 1 ? ` · ${inspected.running} workers` : ""}
                    {inspected.last_tool ? ` · Last tool: ${inspected.last_tool.tool}` : ""}
                  </div>
                </div>
                <button type="button" className="rounded border border-paper-line px-2 py-1 text-ink-soft hover:bg-paper"
                  onClick={() => { if (inspected.state !== "planned") { selectAgent(inspected.name); setView("agents"); } }}
                  disabled={inspected.state === "planned"}>
                  Details <ArrowUpRight className="ml-1 inline h-3 w-3" />
                </button>
                <button type="button" aria-label="Close agent details" className="rounded p-1 text-ink-faint hover:bg-paper hover:text-ink"
                  onClick={() => setInspectedId(null)}><X className="h-3.5 w-3.5" /></button>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-[12px] text-ink-faint">
                <Activity className="h-3.5 w-3.5" /> Select an agent card to see its skill, task, and most recent tool activity.
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
    </div>
  );
}
