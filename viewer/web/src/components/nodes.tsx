import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import { STAGE_ICON, STORE_ICON } from "../lib/icons";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
import type { SceneAgent, Place } from "../types";

/** Custom React Flow nodes: the places agents reach, and the agents themselves. */

export function PlaceNode({ data }: NodeProps) {
  const place = data.place as Place;
  const count = data.count as number | undefined;
  // From the shared vocabulary, and exhaustive over StoreId — the table this replaced
  // had no `matcher` entry and fell through to the dataset's icon, drawing two different
  // places with one picture.
  const Icon = STORE_ICON[place.id];

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
          {count} items
        </div>
      )}
    </div>
  );
}

export function AgentNode({ data }: NodeProps) {
  const agent = data.agent as SceneAgent;
  const color = STAGE_COLOR[agent.stage];
  const busy = agent.state === "working";
  const unknown = agent.state === "unknown";
  const Icon = STAGE_ICON[agent.stage];

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
          {/* The stage's own pictogram, not two letters of its name. "In" and "Re" were
              the interpreter and the report agent, which is a thing to be worked out
              rather than seen. */}
          <Icon className="h-6 w-6" strokeWidth={1.8} />
        </motion.div>

        {/* How many workers this one figure stands for. Only `hypothesis` is drawn one
            figure per worker; `data`, `ml`, `interpreter` and `report` are a single
            character however many run behind them, because that is what the meeting asked
            for — the user chooses the number of hypothesis agents and should not have to
            know the rest are internally run more than once.

            "Should not have to know" is not "must not be able to find out", and this badge
            is the difference. Without it a folded station is indistinguishable from a
            station running one worker, and A-13 — which put the parallelism on the screen
            in the first place — would be undone for four stages out of five.

            Left of the circle, opposite the card on the right, so a data agent that is
            both running two workers and holding a task shows both without them
            overlapping. */}
        {agent.running > 1 && (
          <div
            className="absolute -left-9 -top-3 rounded-full border-2 bg-white px-1.5 py-0.5
                       font-mono text-[11px] font-bold leading-none shadow-sm"
            style={{ borderColor: color, color }}
            title={`${agent.running} workers, drawn as one`}
          >
            ×{agent.running}
          </div>
        )}

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
        {/* The worker's own name, and only when it has one. Two figures at one station
            are both labelled "Hypothesis", so without this line the fix for drawing N of
            them stops one step short: they would be visible and still not tellable
            apart. It is the same string the board writes to `claimed_by`, so the figure
            holding card #12 can be matched against the row that says who holds it.
            Monospaced because it is an identifier, not prose. */}
        {agent.worker && (
          <div className="font-mono text-[10px] leading-tight" style={{ color }}>
            {agent.worker}
          </div>
        )}
        {/* The standard it is running under. Same rule as the pipeline card: always on a
            hypothesis figure because the stack is there to be compared and a blank would
            not say which of "none" and "lost on the way" it meant, and elsewhere only when
            there is one. Two stacked figures reading `Hypothesis` over `hypothesis#1` and
            `hypothesis#2` say which worker; this is what says what each was told. */}
        {(agent.playbook || agent.stage === "hypothesis") && (
          <div
            className={agent.playbook
              ? "truncate font-mono text-[10px] font-bold leading-tight"
              : "truncate text-[10px] leading-tight text-ink-faint"}
            style={agent.playbook ? { color } : undefined}
            title={agent.playbook
              ? `Running under the ${agent.playbook} standard`
              : "No standard attached — the prompt as written"}
          >
            {agent.playbook || "no standard"}
          </div>
        )}
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
