import {
  BaseEdge,
  Handle,
  Position,
  getSmoothStepPath,
  type EdgeProps,
  type NodeProps,
} from "@xyflow/react";
import { motion } from "framer-motion";
import { BookMarked, Plus, X } from "lucide-react";
import { STAGE_ICON, STATE_ICON, STORE_ICON } from "../lib/icons";
import { MAX_HYPOTHESIS_AGENTS } from "../lib/planned";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
import { useControl } from "../store/control";
import type { SceneAgent } from "../types";

/**
 * The two custom React Flow parts the chain view is made of: one stage as a card, and one
 * link as a line a dot travels along.
 *
 * Separate from `components/nodes.tsx` on purpose. Those are floor-plan pieces — a
 * character standing somewhere, a store it can walk to — and they are drawn small because
 * a dozen of them share a canvas. Here there are five cards and nothing else, so each can
 * afford to say what the stage is doing, since when, and what it last touched. Merging the
 * two would mean one component with a mode flag and two layouts inside it.
 *
 * Both files draw from the same three icon tables in `lib/icons.ts`, which is the point of
 * that file: the knowledge source is the same book in either view.
 */

/** Every state gets its own glyph as well as its own colour, so the card still reads when
 *  the colours do not — greyscale, a projector, or a red/green colour deficiency. */
const STATE_TONE: Record<SceneAgent["state"], { text: string; ring: string }> = {
  working: { text: "text-ink", ring: "border-transparent" },
  moving: { text: "text-ink-soft", ring: "border-transparent" },
  idle: { text: "text-ink-faint", ring: "border-paper-line" },
  unknown: { text: "text-amber-700", ring: "border-amber-300" },
  // The only dashed border on the screen, and that is the point: the outline says *not
  // filled in yet* before any label is read. Faint like `idle` because it is equally not
  // busy, and unlike `unknown` because nothing here is wrong.
  planned: { text: "text-ink-faint", ring: "border-dashed border-paper-line" },
};

export interface ChainNodeData extends Record<string, unknown> {
  /** One figure. At the hypothesis station that is one worker and the column holds a card
   *  for each of them; at the other four it is the whole stage, and `agent.running` is how
   *  many workers are behind this one card. See `chainAgents`. */
  agent: SceneAgent;
  /** 1-based, shown on the card. Steps read as a sequence far more readily when they are
   *  numbered — the one convention every stepper in the wild agrees on. */
  step: number;
  /** Pre-formatted by the panel so every card on one frame measures from one `now`. */
  elapsed: string | null;
  /** Whether this card's standard may be **chosen** here rather than only read.
   *
   *  Decided by the panel, not here, because it is a fact about the whole pipeline: while
   *  any worker is running, every card shows what that run is actually using and none of
   *  them may be edited. See `ChainPanel`. */
  editable: boolean;
  /** What the run form says for this card's slot — the value the select shows while
   *  `editable`. Not the same field as `agent.playbook`, and the difference is the point:
   *  that one is what the database says the last run used, this one is what the next run
   *  would use. They are shown together when they disagree. */
  choice: string;
  /** Writes `choice` back to the form. Called with a playbook stem, or `""` for the prompt
   *  as written. A no-op when `editable` is false; the select is not rendered then. */
  onPlaybook: (book: string) => void;
  /** Takes this slot back out of the form, or null when it cannot be.
   *
   *  Only ever set on a `planned` card. Every other card stands for a worker the database
   *  has a row for, and the form does not get to delete one of those: `withPlannedAgents`
   *  drops a resting observed figure when the count falls, but it drops the tail, so an
   *  `×` on such a card would remove a different card than the one it sits on. */
  onRemove: (() => void) | null;
}

export function ChainNode({ data }: NodeProps) {
  const { agent, step, elapsed, editable, choice, onPlaybook, onRemove } =
    data as ChainNodeData;
  const color = STAGE_COLOR[agent.stage];
  const busy = agent.state === "working";
  const tone = STATE_TONE[agent.state];
  // Read here rather than passed down: it is one list for the whole screen, it changes only
  // when the control service comes back up, and threading it through the panel's node data
  // would put a new array into every card's props on every poll.
  const playbooks = useControl((s) => s.playbooks);

  const StageGlyph = STAGE_ICON[agent.stage];
  const StateGlyph = STATE_ICON[agent.state];
  const StoreGlyph = agent.last_tool ? STORE_ICON[agent.last_tool.store] : null;

  return (
    <div
      className={`relative w-44 rounded-xl border-2 bg-white px-3 py-2.5 shadow-sm transition
                  hover:shadow-md ${tone.ring}`}
      style={busy ? { borderColor: color } : undefined}
    >
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0" />

      {/* Takes back a slot the form asked for and nothing has started. The counterpart of
          the `+` below the column: between them the stack is grown and shrunk where it is
          drawn, which is what the `확장 슬롯` in the meeting's figure is

          the left rail still does both and is still the only way to shrink past the
          observed figures. */}
      {onRemove && (
        <button
          type="button"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="nodrag nopan absolute -right-2 -top-2 flex h-5 w-5 items-center
                     justify-center rounded-full border border-paper-line bg-white
                     text-ink-faint shadow-sm hover:border-ink hover:text-ink"
          title="Do not start this one — take the slot back off the form"
        >
          <X className="h-3 w-3" strokeWidth={2.4} />
        </button>
      )}

      <div className="flex items-center gap-2">
        <div className="relative shrink-0">
          {/* The pulse marks a run that is genuinely open, not merely a recent call. */}
          {busy && (
            <motion.span
              className="absolute inset-0 rounded-full"
              style={{ border: `2px solid ${color}` }}
              animate={{ scale: [1, 1.55], opacity: [0.6, 0] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
            />
          )}
          <div
            className="flex h-8 w-8 items-center justify-center rounded-full text-white"
            style={{ backgroundColor: agent.state === "unknown" ? "#c9c7c1" : color }}
          >
            <StageGlyph className="h-4 w-4" strokeWidth={2} />
          </div>
        </div>

        <div className="min-w-0">
          <div className="font-mono text-[10px] leading-none text-ink-faint">{step}</div>
          {/* The label gets about 108px here (w-44, less the padding, the border, the
              32px glyph and the gap), which is roughly 15 characters at this size. A
              longer one is cut with an ellipsis and nothing is raised anywhere, so the
              `title` is what keeps that from being silent. "Report · Insight" is the
              longest label there is and sits near that limit; whether it actually clips
              has not been measured. */}
          <div className="truncate text-[13px] font-bold leading-tight" title={agent.label}>
            {agent.label}
          </div>
          {/* The worker's own name, and only when it has one. Every card of a stacked
              column carries the station's label, so without this line three hypothesis
              cards read identically and the stack says how many rather than which. It is
              the same string the board writes to `claimed_by`, which is what lets a card
              be matched against the task row that names its holder. */}
          {agent.worker && (
            <div className="truncate font-mono text-[10px] leading-tight" style={{ color }}
                 title={agent.worker}>
              {agent.worker}
            </div>
          )}
        </div>
      </div>

      <div className={`mt-2 flex items-center gap-1.5 text-[11px] font-bold ${tone.text}`}>
        <StateGlyph className={`h-3.5 w-3.5 shrink-0 ${busy ? "animate-spin" : ""}`} strokeWidth={2.2} />
        <span className="truncate">{STATE_LABEL[agent.state]}</span>
        {/* How many workers this **one card** stands for, which is only ever more than one
            at a folded station. The hypothesis station is not folded — it gets a card per
            worker — so this badge now appears exactly where a stage is running several and
            drawing one, which is the case that would otherwise be invisible.

            Read off `agent.running` rather than off a count of cards. Those are different
            numbers and the difference is the whole point: `--data-agents 2` sends one
            figure with `running: 2`, so counting cards would say 1 and say it silently.
            Until 2026-09-09 this badge was fed by the card count and therefore never fired
            for any folded stage at all — the one place it was needed. */}
        {agent.running > 1 && (
          <span className="shrink-0 rounded-full px-1.5 font-mono text-[10px] font-bold"
                style={{ backgroundColor: `${color}22`, color }}
                title={`${agent.running} workers of this stage, drawn as one`}>
            x{agent.running}
          </span>
        )}
        {/* Elapsed time is what separates "working" from "wedged". Without it a stuck run
            and a healthy one look identical for as long as anyone cares to watch. */}
        {elapsed && <span className="ml-auto shrink-0 font-mono font-normal">{elapsed}</span>}
      </div>

      {/* The behavioural standard this figure is running under.

          **Always on a hypothesis card, even when there is none.** The meeting's own figure
          labels each hypothesis with its skill, and several hypothesis agents running to
          several standards is the comparison this column exists to make readable

          be ambiguous between "the prompt as written" and "the standard never reached the
          screen", and the second of those was a real bug one level down.

          On the other four it appears only when there is one to show, because a row of
          cards each saying "no standard" is four lines of nothing. `data` is on that side
          of the line deliberately: attaching a skill to the data agent was not among the
          roles the meeting listed (`:157`). */}
      {(editable || agent.playbook || agent.stage === "hypothesis") && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] leading-tight">
          <BookMarked className="h-3 w-3 shrink-0"
                      style={{ color: (editable ? choice : agent.playbook) ? color : "#9c9a94" }}
                      strokeWidth={1.8} />
          {editable ? (
            // **The requirement's own figure**: each hypothesis box carries its skill, and
            // several agents running to several standards is what the stacked column exists
            // to make comparable (`:111-139`). Until 2026-09-09 that choice lived only in a
            // collapsed disclosure in the left rail, so the picture showed the skills and
            // could not set them — which `:151` names as the separate half of the work.
            //
            // `nodrag nopan` and the stopped mousedown are not styling. React Flow treats a
            // press inside a node as the start of a drag, and this panel's `onNodeClick`
            // navigates to the agents view: without both, opening this select leaves the
            // page instead.
            <select
              value={choice}
              onChange={(e) => onPlaybook(e.target.value)}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
              className={`nodrag nopan min-w-0 flex-1 cursor-pointer truncate rounded
                          border border-dashed border-paper-line bg-white px-1 py-0.5
                          text-[10px] leading-tight focus:border-ink focus:outline-none
                          ${choice ? "font-mono font-bold" : "text-ink-faint"}`}
              style={choice ? { color } : undefined}
              title={choice
                ? `The next run gives this agent the ${choice} standard`
                : "No standard — this agent gets the prompt as written"}
            >
              {/* Named rather than blank, and worded exactly as the disclosure words it:
                  two controls over one value that describe it differently read as two
                  different settings. */}
              <option value="">prompt as written</option>
              {(playbooks ?? []).map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          ) : (
            <span
              className={agent.playbook ? "truncate font-mono font-bold" : "truncate text-ink-faint"}
              style={agent.playbook ? { color } : undefined}
              title={agent.playbook
                ? `Running under the ${agent.playbook} standard`
                : "No standard attached — the prompt as written"}
            >
              {agent.playbook || "no standard"}
            </span>
          )}
        </div>
      )}

      {/* What this figure's **last** run was given, when that is not what the select above
          would give its next one. The select has to show the form or it is a control that
          sets one thing and displays another; this line is what keeps that from erasing the
          record on the card. It appears only where the two genuinely differ, so an
          untouched screen does not grow a second line under every card. */}
      {editable && agent.playbook && agent.playbook !== choice && (
        <div className="truncate pl-4 font-mono text-[10px] leading-tight text-ink-faint"
             title={`This agent's last run used the ${agent.playbook} standard`}>
          ran as {agent.playbook}
        </div>
      )}

      {agent.carrying !== null && (
        <div className="mt-1.5 inline-flex rounded-md border px-1.5 py-0.5 font-mono text-[10px]
                        font-bold"
             style={{ borderColor: color, color }}>
          holding #{agent.carrying}
        </div>
      )}

      {/* Kept even while the stage is idle: a chain of grey cards that each say what they
          last did, and when, is still a readable picture of where a run stopped. */}
      {StoreGlyph && agent.last_tool && (
        <div className="mt-1.5 flex items-center gap-1.5 border-t border-paper-line pt-1.5
                        text-[10px] text-ink-faint">
          <StoreGlyph className="h-3 w-3 shrink-0" strokeWidth={1.8} />
          <span className="truncate font-mono">{agent.last_tool.tool}</span>
        </div>
      )}
    </div>
  );
}

export interface ChainAddData extends Record<string, unknown> {
  /** Adds one hypothesis slot to the run form. */
  onAdd: () => void;
  /** The form is already at `MAX_HYPOTHESIS_AGENTS`. Drawn and disabled rather than
   *  removed: a control that disappears at its limit leaves the reader to guess whether
   *  there is a limit or the screen broke. */
  atCeiling: boolean;
}

/**
 * The dashed slot at the foot of the hypothesis column — the meeting figure's `확장 슬롯`.
 *

 * and the third is dashed and labelled as an expansion slot, which is a statement about the
 * screen and not only about the run: the stack is meant to look like something you add to.
 * Until 2026-09-09 the only way to add one was the `Hypothesis` number in the left rail, so
 * the drawing showed a stack that could grow and offered no way to grow it.
 *
 * It is not an agent and is not in `steps`, so it takes part in no edge and `onNodeClick`
 * cannot find it — which is why the button carries its own stopped events rather than
 * relying on the panel to ignore it.
 */
export function ChainAddNode({ data }: NodeProps) {
  const { onAdd, atCeiling } = data as ChainAddData;
  const color = STAGE_COLOR.hypothesis;

  return (
    <button
      type="button"
      disabled={atCeiling}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onAdd();
      }}
      className="nodrag nopan flex w-44 items-center justify-center gap-1.5 rounded-xl
                 border-2 border-dashed border-paper-line bg-white/60 px-3 py-2.5
                 text-[11px] font-bold text-ink-faint transition hover:border-ink-faint
                 hover:text-ink disabled:cursor-not-allowed disabled:opacity-60
                 disabled:hover:border-paper-line disabled:hover:text-ink-faint"
      title={atCeiling
        ? `The service starts at most ${MAX_HYPOTHESIS_AGENTS} hypothesis agents ` +
          `(src/memstara/control/request.py). The number field will still let you ask for ` +
          `more, and the service will say why it refuses.`
        : "Add a hypothesis agent to the next run"}
    >
      <Plus className="h-3.5 w-3.5" strokeWidth={2.4} style={atCeiling ? undefined : { color }} />
      {atCeiling ? `max ${MAX_HYPOTHESIS_AGENTS}` : "hypothesis agent"}
    </button>
  );
}

export interface ChainEdgeData extends Record<string, unknown> {
  live: boolean;
  color: string;
}

/**
 * A link between two stages, with a dot running along it while work is flowing.
 *
 * The dot is React Flow's own recipe for this: take the path back out of
 * `getSmoothStepPath`, draw it once with `BaseEdge`, then hand the same string to an
 * `animateMotion` so the marker follows the exact line the reader sees. React Flow's
 * built-in `animated` flag instead scrolls a `stroke-dasharray`, which reads as "this wire
 * is energised" rather than "something is moving from here to there".
 */
export function ChainEdge({
  id,
  sourceX,
  sourceY,
  sourcePosition,
  targetX,
  targetY,
  targetPosition,
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const { live, color } = (data ?? { live: false, color: "#dcdbd4" }) as ChainEdgeData;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{ stroke: live ? color : "#dcdbd4", strokeWidth: live ? 2.5 : 1.5 }}
      />
      {live && (
        <circle r="4.5" fill={color}>
          <animateMotion dur="1.8s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
    </>
  );
}

export const chainNodeTypes = { chain: ChainNode, chainAdd: ChainAddNode };
export const chainEdgeTypes = { chain: ChainEdge };
