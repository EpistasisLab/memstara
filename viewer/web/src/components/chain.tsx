import {
  BaseEdge,
  Handle,
  Position,
  getSmoothStepPath,
  type EdgeProps,
  type NodeProps,
} from "@xyflow/react";
import { motion } from "framer-motion";
import { STAGE_ICON, STATE_ICON, STORE_ICON } from "../lib/icons";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
import type { SceneAgent, StageId } from "../types";

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
};

export interface ChainNodeData extends Record<string, unknown> {
  agent: SceneAgent;
  /** 1-based, shown on the card. Steps read as a sequence far more readily when they are
   *  numbered — the one convention every stepper in the wild agrees on. */
  step: number;
  /** Pre-formatted by the panel so every card on one frame measures from one `now`. */
  elapsed: string | null;
}

export function ChainNode({ data }: NodeProps) {
  const { agent, step, elapsed } = data as ChainNodeData;
  const color = STAGE_COLOR[agent.id as StageId];
  const busy = agent.state === "working";
  const tone = STATE_TONE[agent.state];

  const StageGlyph = STAGE_ICON[agent.id as StageId];
  const StateGlyph = STATE_ICON[agent.state];
  const StoreGlyph = agent.last_tool ? STORE_ICON[agent.last_tool.store] : null;

  return (
    <div
      className={`w-56 rounded-xl border-2 bg-white px-3 py-2.5 shadow-sm transition
                  hover:shadow-md ${tone.ring}`}
      style={busy ? { borderColor: color } : undefined}
    >
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0" />

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
          {/* `truncate` stays, so the label is one Tailwind class away from being cut
              short again with nothing raised anywhere — `w-56` is sized for the longest
              label there is today and not a character more. The tooltip is what makes
              that failure visible rather than silent. */}
          <div className="truncate text-[13px] font-bold leading-tight" title={agent.label}>
            {agent.label}
          </div>
        </div>
      </div>

      <div className={`mt-2 flex items-center gap-1.5 text-[11px] font-bold ${tone.text}`}>
        <StateGlyph className={`h-3.5 w-3.5 shrink-0 ${busy ? "animate-spin" : ""}`} strokeWidth={2.2} />
        <span className="truncate">{STATE_LABEL[agent.state]}</span>
        {/* Elapsed time is what separates "working" from "wedged". Without it a stuck run
            and a healthy one look identical for as long as anyone cares to watch. */}
        {elapsed && <span className="ml-auto shrink-0 font-mono font-normal">{elapsed}</span>}
      </div>

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

export const chainNodeTypes = { chain: ChainNode };
export const chainEdgeTypes = { chain: ChainEdge };
