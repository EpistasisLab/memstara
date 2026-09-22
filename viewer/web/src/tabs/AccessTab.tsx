import DetailPreview from "../components/DetailPreview";
import { agentDisplayName, TOOL_ACTIONS } from "../lib/telemetry";
import { createColumnHelper } from "@tanstack/react-table";
import { CircleSlash, ArrowRight } from "lucide-react";
import { useMemo } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import DataTable from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import { STAGE_COLOR, STORE_LABEL } from "../lib/stage";
import { useAccess } from "../store/viewer";
import type { AccessRow, StageId } from "../types";

/**
 * Who reached which store through which window.
 *
 * The windows table is here for what is *missing*: `read_board` and `count_waiting`
 * show no agent calls, because the first belongs to the driving script and the second
 * to nobody. Tool-level separation is why an agent cannot claim another stage's work,
 * and this is where you can see it holding.
 */

const col = createColumnHelper<AccessRow>();

const COLUMNS = [
  col.accessor("agent_label", {
    header: "Agent",
    cell: (c) => (
      <span className="inline-flex items-center gap-2 font-bold">
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: STAGE_COLOR[c.row.original.agent as StageId] ?? "#c9c7c1" }}
        />
        <DetailPreview title="Agent" text={c.getValue()}><span tabIndex={0}>{agentDisplayName(c.getValue())}</span></DetailPreview>
      </span>
    ),
  }),
  col.accessor("tool", { header: "Action / tool", cell: (c) => <details><DetailPreview title="Tool action" text={`${TOOL_ACTIONS[c.getValue()] ?? c.getValue()}. Tool identifier: ${c.getValue()}`}><summary className="cursor-pointer">{TOOL_ACTIONS[c.getValue()] ?? c.getValue()}</summary></DetailPreview><code className="mt-2 block break-all text-xs">{c.getValue()}</code></details> }),
  col.accessor("server", { header: "Server", cell: (c) => <span className="font-mono text-xs text-ink-faint">{c.getValue()}</span> }),
  col.accessor("store", { header: "Resource", cell: (c) => STORE_LABEL[c.getValue()] }),
  col.accessor("calls", { header: "Calls", meta: { align: "right" }, cell: (c) => <span className="font-bold">{c.getValue()}</span> }),
];

export default function AccessTab() {
  const access = useAccess();

  const byStore = useMemo(() => {
    if (!access) return [];
    const m = new Map<string, number>();
    for (const r of access.rows) m.set(r.store, (m.get(r.store) ?? 0) + r.calls);
    return [...m].map(([store, calls]) => ({ store, label: STORE_LABEL[store as keyof typeof STORE_LABEL] ?? store, calls }))
      .sort((a, b) => b.calls - a.calls);
  }, [access]);

  if (!access) return <EmptyState what="the access map" />;

  const board = access.rows.filter((r) => r.path === "board");
  const supervisor = access.rows.filter((r) => r.path === "supervisor");

  return (
    <div className="space-y-8 p-6">
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <h2 className="mb-3 text-sm font-bold">Task coordination tools — who uses them</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {access.windows.map((w) => (
              <div
                key={w.tool}
                className={`rounded-lg border p-3 ${
                  w.called_by_agent ? "border-paper-line bg-white" : "border-dashed border-paper-line bg-paper/50"
                }`}
              >
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-xs font-bold">{w.tool}</span>
                  {w.called_by_agent ? (
                    <span className="text-lg font-bold">{w.calls}</span>
                  ) : (
                    <CircleSlash className="h-4 w-4 text-ink-faint" />
                  )}
                </div>
                <div className="mt-1 flex items-center gap-1 text-[12px] text-ink-soft">
                  {w.holder} <ArrowRight className="h-3 w-3" /> {STORE_LABEL[w.store]}
                </div>
                {!w.called_by_agent && (
                  <div className="mt-1 text-[12px] text-ink-faint">no agent calls this — correct</div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-3 text-sm font-bold">Calls by resource</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={byStore} layout="vertical" margin={{ left: 8, right: 24 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="label" width={115} tickLine={false} axisLine={false}
                     tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => [`${Number(v)} calls`, "Calls"]} />
              <Bar dataKey="calls" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                {byStore.map((d) => (
                  <Cell key={d.store} fill={d.store === "board" ? "#2f6b47" : d.store === "results" ? "#8f2f4f" : "#8a8880"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {[
        { rows: board, title: "Pipeline agent calls", sub: "Shared task coordination" },
        { rows: supervisor, title: "Supervisor agent calls", sub: "Legacy orchestration" },
      ].filter(g => g.rows.length > 0).map((g) => (
        <section key={g.title}>
          <h2 className="mb-3 flex items-baseline gap-2 text-sm font-bold">
            {g.title}
            <span className="font-mono text-xs font-normal text-ink-faint">{g.sub}</span>
            <span className="font-normal text-ink-soft">{g.rows.reduce((n, r) => n + r.calls, 0)} calls</span>
          </h2>
          <DataTable columns={COLUMNS} data={g.rows} initialSorting={[{ id: "calls", desc: true }]} />
        </section>
      ))}
    </div>
  );
}
