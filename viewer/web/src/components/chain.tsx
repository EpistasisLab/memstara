import { agentStageLabel } from "../lib/stage";
import KnowledgeNode from "./KnowledgeNode";
import PipelineStage from "./PipelineStage";
import Help from "./Help";
import {
  BaseEdge,
  Handle,
  Position,
  getSmoothStepPath,
  type EdgeProps,
  type NodeProps,
} from "@xyflow/react";
import { motion, useReducedMotion } from "framer-motion";
import { BookMarked, Plus, X } from "lucide-react";
import { STAGE_ICON, STATE_ICON, STORE_ICON } from "../lib/icons";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
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
  inspected?: boolean;
  onInspect?: () => void;
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
  onConfigure: () => void;
  predictiveModel: string | null;
  /** Takes this slot back out of the form, or null when it cannot be.
   *
   *  Only ever set on a `planned` card. Every other card stands for a worker the database
   *  has a row for, and the form does not get to delete one of those: `withPlannedAgents`
   *  drops a resting observed figure when the count falls, but it drops the tail, so an
   *  `×` on such a card would remove a different card than the one it sits on. */
  onRemove: (() => void) | null;
}

export function ChainNode({ data }: NodeProps) {
  const { agent, step, elapsed, editable, choice, onConfigure, onRemove, predictiveModel } =
    data as ChainNodeData;
  const { inspected, onInspect } = data as ChainNodeData;
  const reducedMotion = useReducedMotion();
  const color = STAGE_COLOR[agent.stage];
  const busy = agent.state === "working";
  const tone = STATE_TONE[agent.state];
  // Read here rather than passed down: it is one list for the whole screen, it changes only
  // when the control service comes back up, and threading it through the panel's node data
  // would put a new array into every card's props on every poll.

  const StageGlyph = STAGE_ICON[agent.stage];
  const StateGlyph = STATE_ICON[agent.state];
  const StoreGlyph = agent.last_tool ? STORE_ICON[agent.last_tool.store] : null;

  return (
    <div
      role="group" tabIndex={0} aria-label={`${agent.label}: ${STATE_LABEL[agent.state]}`}
      onKeyDown={event => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onInspect?.(); } }}
      className={`relative w-[280px] rounded-xl border-2 border-t-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 bg-white px-4 py-3.5 shadow-xs transition
                  hover:shadow-md ${tone.ring}`}
      style={{ borderTopColor: color, ...(busy ? { borderColor: color } : {}), ...(inspected ? { boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 19%, transparent), 0 8px 24px #00000010` } : {}) }}
    >
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0" />


      {onRemove && (
        <button
          type="button"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="nodrag nopan absolute -right-2 -top-2 flex h-7 w-7 items-center
                     justify-center rounded-full border border-paper-line bg-white
                     text-ink-faint shadow-xs hover:border-ink hover:text-ink"
          aria-label={`Remove ${agentStageLabel(agent.stage)} ${agent.slot + 1}`}
          title={`Remove this ${agentStageLabel(agent.stage)} and its skill from the next run`}
        >
          <X className="h-3 w-3" strokeWidth={2.4} />
        </button>
      )}

      <div className="flex items-center gap-2">
        <Help topic={agent.stage} />
        <div className="relative shrink-0">
          {/* The pulse marks a run that is genuinely open, not merely a recent call. */}
          {busy && !reducedMotion && (
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
          <div className="font-mono text-xs leading-none text-ink-faint">{step}</div>
          {/* The label gets about 108px here (w-[280px], less the padding, the border, the
              32px glyph and the gap), which is roughly 15 characters at this size. A
              longer one is cut with an ellipsis and nothing is raised anywhere, so the
              `title` is what keeps that from being silent. "Explanation" is the
              longest label there is and sits near that limit; whether it actually clips
              has not been measured. */}
          <div className="break-words text-base font-bold leading-snug" title={agent.label}>
            {agent.label}
          </div>
          {/* The worker's own name, and only when it has one. Every card of a stacked
              column carries the station's label, so without this line three hypothesis
              cards read identically and the stack says how many rather than which. It is
              the same string the board writes to `claimed_by`, which is what lets a card
              be matched against the task row that names its holder. */}
          {agent.worker && (
            <div className="truncate font-mono text-xs leading-tight" style={{ color }}
                 title={agent.worker}>
              {agent.worker}
            </div>
          )}
        </div>
      </div>

      <div className={`mt-2 flex items-center gap-1.5 text-xs font-bold ${tone.text}`}>
        <StateGlyph className={`h-3.5 w-3.5 shrink-0 ${busy && !reducedMotion ? "animate-spin" : ""}`} strokeWidth={2.2} />
        <Help topic={STATE_LABEL[agent.state]}><span tabIndex={0} className="cursor-help truncate">{STATE_LABEL[agent.state]}</span></Help>
        {/* Elapsed time is what separates "working" from "wedged". Without it a stuck run
            and a healthy one look identical for as long as anyone cares to watch. */}
        {elapsed && <span className="ml-auto shrink-0 font-mono font-normal">{elapsed}</span>}
      </div>


      {(editable || agent.playbook || agent.stage === "hypothesis") && (
        <div className="mt-1.5 flex items-center gap-1 text-xs leading-tight">
          <BookMarked className="h-3 w-3 shrink-0"
                      style={{ color: (editable ? choice : agent.playbook) ? color : "#9c9a94" }}
                      strokeWidth={1.8} />
          {editable ? (
            <button type="button" onClick={e => { e.stopPropagation(); onConfigure(); }}
              className="nodrag nopan min-w-0 flex-1 break-words rounded border border-dashed border-paper-line px-2 py-1.5 text-left text-xs font-bold"
              style={{ color }} title="Read or change this agent's skill">
              {choice || "Choose skill"}
            </button>
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

      {agent.last_status && agent.state !== "planned" && !busy && <p className={`mt-1 text-xs ${agent.last_status === "failed" ? "text-red-700" : "text-ink-faint"}`}>Last call: {agent.last_status}</p>}
      {predictiveModel && <div className="mt-1 truncate font-mono text-xs text-ink-faint" title="Selected predictive model">{predictiveModel}</div>}

      {/* What this figure's **last** run was given, when that is not what the select above
          would give its next one. The select has to show the form or it is a control that
          sets one thing and displays another; this line is what keeps that from erasing the
          record on the card. It appears only where the two genuinely differ, so an
          untouched screen does not grow a second line under every card. */}
      {editable && agent.playbook && agent.playbook !== choice && (
        <div className="truncate pl-4 font-mono text-xs leading-tight text-ink-faint"
             title={`This agent's last run used the ${agent.playbook} standard`}>
          ran as {agent.playbook}
        </div>
      )}

      {agent.carrying !== null && (
        <div className="mt-1.5 inline-flex rounded-md border px-1.5 py-0.5 font-mono text-xs
                        font-bold"
             style={{ borderColor: color, color }}>
          holding #{agent.carrying}
        </div>
      )}

      {/* Kept even while the stage is idle: a chain of grey cards that each say what they
          last did, and when, is still a readable picture of where a run stopped. */}
      {StoreGlyph && agent.last_tool && (
        <div className="mt-1.5 flex items-center gap-1.5 border-t border-paper-line pt-1.5
                        text-xs text-ink-faint">
          <StoreGlyph className="h-3 w-3 shrink-0" strokeWidth={1.8} />
          <span className="truncate font-mono">{agent.last_tool.tool}</span>
        </div>
      )}
    </div>
  );
}

export interface ChainAddData extends Record<string, unknown> {
  stage: "hypothesis" | "interpreter";
  maximum: number;
  onAdd: () => void;
  atCeiling: boolean;
}

/** Expansion controls open the skill editor without becoming pipeline agents. */
export function ChainAddNode({ data }: NodeProps) {
  const { stage, maximum, onAdd, atCeiling } = data as ChainAddData;
  const color = STAGE_COLOR[stage];

  return (
    <button
      type="button"
      disabled={atCeiling}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onAdd();
      }}
      className="nodrag nopan flex w-[280px] items-center justify-center gap-1.5 rounded-xl
                 border-2 border-dashed border-paper-line bg-white/60 px-3 py-2.5
                 text-xs font-bold text-ink-faint transition hover:border-ink-faint
                 hover:text-ink disabled:cursor-not-allowed disabled:opacity-60
                 disabled:hover:border-paper-line disabled:hover:text-ink-faint"
      aria-label={`Add ${agentStageLabel(stage)} agent`}
      title={atCeiling
        ? `Maximum of ${maximum} ${agentStageLabel(stage)} agents reached.`
        : `Add a ${agentStageLabel(stage)} agent with a different skill to the next run`}
    >
      <Plus className="h-3.5 w-3.5" strokeWidth={2.4} style={atCeiling ? undefined : { color }} />
      {atCeiling ? `${agentStageLabel(stage)} agents · max ${maximum}` : `${agentStageLabel(stage)} agent`}
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
  const reducedMotion = useReducedMotion();
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
      {live && !reducedMotion && (
        <circle r="4.5" fill={color}>
          <animateMotion dur="1.8s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
    </>
  );
}

export const chainNodeTypes = { knowledge: KnowledgeNode, pipelineStage: PipelineStage, chain: ChainNode, chainAdd: ChainAddNode };
export const chainEdgeTypes = { chain: ChainEdge };
