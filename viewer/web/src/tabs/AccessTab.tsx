import { createColumnHelper } from "@tanstack/react-table";
import { CircleSlash, ArrowRight } from "lucide-react";
import { useMemo } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import DataTable from "../components/DataTable";
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
    header: "에이전트",
    cell: (c) => (
      <span className="inline-flex items-center gap-2 font-bold">
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: STAGE_COLOR[c.row.original.agent as StageId] ?? "#c9c7c1" }}
        />
        {c.getValue()}
      </span>
    ),
  }),
  col.accessor("tool", { header: "창구·도구", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
  col.accessor("server", { header: "서버", cell: (c) => <span className="font-mono text-xs text-ink-faint">{c.getValue()}</span> }),
  col.accessor("store", { header: "저장소", cell: (c) => STORE_LABEL[c.getValue()] }),
  col.accessor("calls", { header: "호출", meta: { align: "right" }, cell: (c) => <span className="font-bold">{c.getValue()}</span> }),
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

  if (!access) return <div className="p-8 text-ink-faint">불러오는 중…</div>;

  const board = access.rows.filter((r) => r.path === "board");
  const supervisor = access.rows.filter((r) => r.path === "supervisor");

  return (
    <div className="space-y-8 p-6">
      <section className="grid grid-cols-3 gap-6">
        <div className="col-span-2">
          <h2 className="mb-3 text-sm font-bold">판의 창구 여섯 — 누가 쓰나</h2>
          <div className="grid grid-cols-2 gap-2">
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
                <div className="mt-1 flex items-center gap-1 text-[11px] text-ink-soft">
                  {w.holder} <ArrowRight className="h-3 w-3" /> {STORE_LABEL[w.store]}
                </div>
                {!w.called_by_agent && (
                  <div className="mt-1 text-[11px] text-ink-faint">에이전트가 부르지 않는다 — 정상</div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-3 text-sm font-bold">저장소별 접근</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={byStore} layout="vertical" margin={{ left: 8, right: 24 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="label" width={64} tickLine={false} axisLine={false}
                     tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => [`${Number(v)}회`, "호출"]} />
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
        { rows: board, title: "판 경로", sub: "03_board_pipeline.py" },
        { rows: supervisor, title: "감독자 경로", sub: "02_mvp_pipeline.py" },
      ].map((g) => (
        <section key={g.title}>
          <h2 className="mb-3 flex items-baseline gap-2 text-sm font-bold">
            {g.title}
            <span className="font-mono text-xs font-normal text-ink-faint">{g.sub}</span>
            <span className="font-normal text-ink-soft">{g.rows.reduce((n, r) => n + r.calls, 0)}회</span>
          </h2>
          <DataTable columns={COLUMNS} data={g.rows} initialSorting={[{ id: "calls", desc: true }]} />
        </section>
      ))}
    </div>
  );
}
