import { BarChart3 } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Panel from "../components/Panel";
import { useBoard, useResults } from "../store/viewer";

/**
 * Finished results — the results table, not the board.
 *
 * Permanently on screen at bottom-right, which is why Results is not in the control
 * panel's nav. It carries `id="results-panel"` so the scene's results place can bring it
 * into view on a narrow screen (see ScenePanel's `onNodeClick`).
 *
 * Read-only, always. Nothing here writes to the store.
 */

export default function ResultsPanel() {
  const results = useResults();
  const board = useBoard();

  const compare = (results ?? []).map((r) => ({ name: `trial ${r.trial}`, auc: r.auc ?? 0 }));

  return (
    <Panel id="results-panel" icon={BarChart3} title="Results" count={results?.length}>
      {!results ? (
        <div className="p-8 text-ink-faint">Loading…</div>
      ) : results.length === 0 ? (
        <div className="p-8 text-ink-faint">No finished results yet.</div>
      ) : (
        <div className="space-y-5 p-4">
          <section className="rounded-lg border border-paper-line p-3">
            <h3 className="mb-2 text-sm font-bold">Performance by trial</h3>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={compare}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eceae4" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 12 }} />
                {/* 0.5 is chance for AUC; anchoring the axis there stops a coin-flip result
                    from looking like a tall bar. */}
                <YAxis domain={[0.5, 1]} tickLine={false} axisLine={false} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => [Number(v).toFixed(4), "AUC"]} />
                <Bar dataKey="auc" radius={[4, 4, 0, 0]} fill="#2a5f8f" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
            <p className="mt-1 text-xs text-ink-faint">The axis starts at 0.5 — 0.5 is a coin flip.</p>
          </section>

          {results.map((r) => {
            // task_id is null once the board row has been cleaned away; the result stands
            // on its own, it just cannot show the per-column importances any more.
            const task = r.task_id === null
              ? undefined
              : board?.tasks.find((t) => t.task_id === r.task_id);
            const imp = Object.entries(task?.importance ?? {}).sort((a, b) => b[1] - a[1])
              .map(([col, v]) => ({ col, v }));

            return (
              <article key={r.result_id} className="rounded-lg border border-paper-line p-4">
                <header className="flex items-baseline justify-between gap-4">
                  <h3 className="font-bold">
                    Trial {r.trial}
                    <span className="ml-2 font-normal text-ink-soft">{r.perspective}</span>
                  </h3>
                  <span className="text-right">
                    <span className="font-mono text-xl font-bold">AUC {r.auc?.toFixed(4) ?? "—"}</span>
                    {r.y_column && (
                      <span className="block font-mono text-[11px] text-ink-faint">
                        → {r.y_column}
                      </span>
                    )}
                  </span>
                </header>

                <p className="mt-2 text-sm leading-relaxed text-ink-soft">{r.hypothesis}</p>

                {r.task_id === null && (
                  <p className="mt-3 text-xs text-ink-faint">
                    Cleaned away from the board — the contributions live only on the board,
                    so they can no longer be shown.
                  </p>
                )}

                {imp.length > 0 && (
                  <div className="mt-4">
                    <h4 className="mb-2 text-sm font-bold">Contributions</h4>
                    <ResponsiveContainer width="100%" height={Math.max(140, imp.length * 26)}>
                      <BarChart data={imp} layout="vertical" margin={{ left: 12, right: 24 }}>
                        <XAxis type="number" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                        <YAxis type="category" dataKey="col" width={96} tick={{ fontSize: 11 }}
                               axisLine={false} tickLine={false} />
                        <Tooltip formatter={(v) => [Number(v).toFixed(5), "contribution"]} />
                        {/* A column can be chosen and contribute nothing — or less than
                            nothing. Negative bars are the point, not an artefact. */}
                        <Bar dataKey="v" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                          {imp.map((d) => (
                            <Cell key={d.col} fill={d.v < 0 ? "#c0392b" : "#2a5f8f"} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                <details className="mt-3">
                  <summary className="cursor-pointer text-sm font-bold hover:text-ink-soft">
                    Interpretation
                  </summary>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{r.interpretation}</p>
                </details>
              </article>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
