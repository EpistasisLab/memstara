import DetailPreview from "../components/DetailPreview";
import {costLabel} from '../lib/loopUsage';
import { createColumnHelper } from "@tanstack/react-table";
import { AlertTriangle, Coins, Repeat } from "lucide-react";
import { agentDisplayName } from "../lib/telemetry";
import DataTable from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import { STAGE_COLOR } from "../lib/stage";
import { useAgentTotals, useHealth, useScene, useViewer } from "../store/viewer";
import type { AgentTotals, StageId } from "../types";

const col = createColumnHelper<AgentTotals>();

const COLUMNS = [
  col.accessor("label", {
    header: "Agent",
    cell: (c) => (
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: STAGE_COLOR[c.row.original.id as StageId] ?? "#c9c7c1" }} />
        <div>
          <div className="font-bold">{agentDisplayName(c.getValue())}</div>
          <details className="mt-1 text-xs text-ink-faint"><DetailPreview title="Agent identifier" text={c.row.original.name}><summary className="cursor-pointer">Full agent identifier</summary></DetailPreview><code className="break-all">{c.row.original.name}</code></details>
        </div>
      </div>
    ),
  }),
  col.accessor("path", {
    header: "Path",
    cell: (c) => (
      <span className={`rounded px-1.5 py-0.5 text-[12px] font-bold ${
        c.getValue() === "board" ? "bg-emerald-100 text-emerald-800" : "bg-paper text-ink-soft"}`}>
        {c.getValue() === "board" ? "Board" : "Supervisor"}
      </span>
    ),
  }),
  col.accessor("runs", { header: "Agent calls", meta: { align: "right" } }),
  col.accessor("completed", { header: "Completed", meta: { align: "right" } }),
  col.accessor("avg_iterations", {
    header: "Avg reasoning steps", meta: { align: "right" },
    cell: (c) => c.getValue() ?? "—",
  }),
  col.accessor((r) => r.tokens.prompt + r.tokens.completion, {
    id: "tokens", header: "Tokens", meta: { align: "right" },
    cell: (c) => <span className="font-mono text-xs">{c.getValue().toLocaleString()}</span>,
  }),
  col.accessor("cost", {
    header: "Cost", meta: { align: "right" },
    cell: (c) => <span className="font-mono text-xs">{costLabel({usd:c.getValue(),status:c.row.original.runs ? 'partial' : 'complete'})}</span>,
  }),
];

export default function AgentsTab() {
  const totals = useAgentTotals();
  const scene = useScene();
  const health = useHealth();
  const selected = useViewer((s) => s.selectedAgent);

  // core holds the run history; without it we say so rather than showing an empty
  // table that reads like "this agent never ran".
  if (health && !health.core.up)
    return (
      <div className="m-6 rounded-lg border border-amber-300 bg-amber-50 p-6">
        <div className="flex items-center gap-2 font-bold text-amber-900">
          <AlertTriangle className="h-5 w-5" /> Agent history is temporarily unavailable
        </div>
        <p className="mt-2 text-sm text-amber-900/80">
          The agent history query could not be completed. The Board and Results tabs are available separately.
        </p>
        <p className="mt-2 font-mono text-xs text-amber-900/60">{health.core.error}</p>
      </div>
    );
  if (!totals) return <EmptyState what="the agent totals" />;

  const cost = totals.reduce((n, a) => n + a.cost, 0);
  const runs = totals.reduce((n, a) => n + a.runs, 0);

  return (
    <div className="space-y-4 p-4">
      <details className="text-sm text-ink-soft"><summary className="cursor-pointer">How to read these numbers</summary><p className="mt-2">Agent calls are individual agent invocations. Reasoning steps are internal to a call; neither counts complete pipeline loops. Usage and estimated cost cover only the selected scope identified above. The workspace header combines multiple pipelines.</p></details>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { icon: Repeat, label: "Agent calls", value: runs.toLocaleString() },
          { icon: Coins, label: "Recorded cost subtotal", value: costLabel({usd:cost,status:runs?'partial':'complete'}) },
          { icon: Repeat, label: "Agents", value: `${totals.length}` },
        ].map((s) => (
          <div key={s.label} className="rounded-lg border border-paper-line bg-white p-4">
            <div className="flex items-center gap-2 text-xs text-ink-faint">
              <s.icon className="h-3.5 w-3.5" /> {s.label}
            </div>
            <div className="mt-1 text-2xl font-bold">{s.value}</div>
          </div>
        ))}
      </div>

      <DataTable
        columns={COLUMNS}
        data={totals}
        initialSorting={[{ id: "runs", desc: true }]}
        rowClass={(r) => (selected === r.name ? "bg-amber-50" : undefined)}
      />

      <section>
        <h2 className="mb-1 text-sm font-bold">Tools available to each stage</h2>
        <p className="mb-3 text-xs text-ink-soft">
          Tools are handed over <span className="font-bold">at run time</span>, not in the agent
          definition (<span className="font-mono">available_tools</span>).
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {scene?.agents.filter((a) => a.slot === 0).map((a) => (
            <div key={a.id} className="rounded-lg border border-paper-line bg-white p-3">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: STAGE_COLOR[a.stage] }} />
                <span className="text-sm font-bold">{a.label}</span>
              </div>
              <ul className="mt-2 space-y-1">
                {a.windows.map((w) => (
                  <li key={w} className="font-mono text-[12px] text-ink-soft">{w}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
