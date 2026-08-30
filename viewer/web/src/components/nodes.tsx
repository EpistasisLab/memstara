import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import { Database, FileSpreadsheet, BookOpen, Cpu, ClipboardList } from "lucide-react";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
import type { SceneAgent, Place, StageId } from "../types";

/** Custom React Flow nodes: the places agents reach, and the agents themselves. */

const PLACE_ICON = {
  okf: BookOpen,
  board: ClipboardList,
  results: FileSpreadsheet,
  dataset: Database,
  ml: Cpu,
} as const;

export function PlaceNode({ data }: NodeProps) {
  const place = data.place as Place;
  const count = data.count as number | undefined;
  const Icon = PLACE_ICON[place.id as keyof typeof PLACE_ICON] ?? Database;

  return (
    <div
      className="w-56 rounded-xl border border-paper-line bg-white px-4 py-3 shadow-sm
                 transition hover:border-ink-faint hover:shadow-md"
    >
      {/* Handles on every side so edges from any character meet the box cleanly. */}
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0" />
      <Handle type="target" position={Position.Bottom} className="!bg-transparent !border-0" />
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0" />
      <Handle type="target" position={Position.Right} className="!bg-transparent !border-0" />

      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-5 w-5 shrink-0 text-ink-soft" strokeWidth={1.8} />
        <div className="min-w-0">
          <div className="font-bold leading-tight">{place.label}</div>
          <div className="truncate font-mono text-[11px] text-ink-faint">{place.sub}</div>
        </div>
      </div>

      {count !== undefined && (
        <div className="mt-2 border-t border-paper-line pt-2 text-[11px] text-ink-soft">
          {count}건
        </div>
      )}
    </div>
  );
}

export function AgentNode({ data }: NodeProps) {
  const agent = data.agent as SceneAgent;
  const color = STAGE_COLOR[agent.id as StageId];
  const busy = agent.state === "working";
  const unknown = agent.state === "unknown";

  return (
    <div className="flex w-32 flex-col items-center">
      <Handle type="source" position={Position.Top} className="!bg-transparent !border-0" />
      <Handle type="source" position={Position.Left} className="!bg-transparent !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0" />

      <div className="relative">
        {/* A pulse only while a run is genuinely open — see RUN_ALIVE_SECONDS. */}
        {busy && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ border: `2px solid ${color}` }}
            animate={{ scale: [1, 1.5], opacity: [0.7, 0] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <motion.div
          className={cnCircle(unknown)}
          style={{ backgroundColor: unknown ? "#c9c7c1" : color }}
          animate={busy ? { y: [0, -3, 0] } : { y: 0 }}
          transition={busy ? { duration: 1.4, repeat: Infinity } : { duration: 0.3 }}
        >
          {agent.label.slice(0, 2)}
        </motion.div>

        {/* The card it is holding: claimed but not yet submitted. */}
        {agent.carrying !== null && (
          <motion.div
            initial={{ scale: 0.6, opacity: 0, x: -8 }}
            animate={{ scale: 1, opacity: 1, x: 0 }}
            className="absolute -right-10 -top-3 rounded-md border-2 bg-white px-2 py-1
                       font-mono text-[11px] font-bold shadow-sm"
            style={{ borderColor: color, color }}
          >
            #{agent.carrying}
          </motion.div>
        )}
      </div>

      <div className="mt-2 text-center">
        <div className="text-sm font-bold leading-tight">{agent.label}</div>
        <div className={unknown ? "text-[11px] font-bold text-amber-700" : "text-[11px] text-ink-faint"}>
          {STATE_LABEL[agent.state]}
        </div>
      </div>
    </div>
  );
}

function cnCircle(unknown: boolean) {
  return [
    "flex h-14 w-14 items-center justify-center rounded-full",
    "text-sm font-bold text-white shadow-sm",
    unknown ? "opacity-70" : "",
  ].join(" ");
}

export const nodeTypes = { place: PlaceNode, agent: AgentNode };
