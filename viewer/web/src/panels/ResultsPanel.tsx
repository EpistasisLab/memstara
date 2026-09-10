import FinalReport from "../components/FinalReport";
import ExplanationEvidence from "../components/ExplanationEvidence";
import Help from "../components/Help";
import { BarChart3 } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import EmptyState from "../components/EmptyState";
import Panel from "../components/Panel";
import WhyColumns from "../components/WhyColumns";
import { useBoard, useResults, useViewer } from "../store/viewer";

/**
 * Finished results — the results table, not the board.
 *
 * Permanently on screen at bottom-right, which is why Results is not in the control
 * panel's nav. It carries `id="results-panel"` so the scene's results place can bring it
 * into view on a narrow screen (see ScenePanel's `onNodeClick`).
 *
 * Read-only, always. Nothing here writes to the store.
 */

/** What the numbers under Contributions actually measure, given the engine that made them.
 *
 *  Three states reach here and they are said differently on purpose:
 *
 *    a name we know   the engine and the quantity, so two results can be compared or not
 *                     compared knowingly
 *    a name we do not the engine alone. A new engine added to `ml._make_model` and not to
 *                     this table should read as unfamiliar, never as unrecorded
 *    `""`             not recorded. Every result from before 2026-09-08 says this, and it
 *                     cannot be backfilled: the engine was an environment variable read
 *                     inside the call and nothing wrote it down
 *                     (`src/memstara/mcp_servers/ml.py:335`)
 *
 *  The wording comes from `_importance`'s own docstring, which measured it: random_forest
 *  sums to exactly 1.0000 on all four sub-datasets, sklearn_hgb's permutation maps sum to
 *  0.0819 and 0.2572 with a minimum entry of -0.0131.
 *
 *  **Two of the three engines below no longer exist and their rows stay in this table.**
 *  `sklearn_hgb` and `random_forest` were removed from `ml._make_model` on 2026-09-08,
 *  leaving `xgboost` the only engine a new result can name. This panel does not render new
 *  results — it renders whatever is on the board, and 81 rows there say `sklearn_hgb`,
 *  whose numbers are AUC drops rather than gain. Pruning this table to match what the tool
 *  can produce today would turn every one of those rows into "scale not described here",
 *  which is the one thing the table exists to prevent. It shrinks when the rows do. */
function scaleNote(model: string): string {
  if (model === "") return "scale not recorded — this result predates the engine being stored";
  const measure: Record<string, string> = {
    sklearn_hgb: "mean AUC drop under permutation, no fixed scale, negative is possible",
    random_forest: "impurity decrease, non-negative, sums to about 1",
    xgboost: "gain, non-negative, sums to about 1",
  };
  return measure[model] ? `${model} · ${measure[model]}` : `${model} · scale not described here`;
}

export default function ResultsPanel() {
  const results = useResults();
  const dataUnavailable = useViewer(s => !s.newRunMode && (s.snapshot?.health.memstara.up === false || !!s.error));
  const pipeline = useViewer(s => s.snapshot?.pipeline);
  const failed = (useBoard()?.tasks ?? []).filter(task => task.status === "failed");

  const compare = (results ?? []).filter(r => r.auc != null).map((r) => ({ name: `trial ${r.trial}`, auc: r.auc }));

  return (
    <Panel id="results-panel" icon={BarChart3} title="Results" count={results?.length}>
      {pipeline && pipeline.status !== "completed" && <p role="status" className="m-4 text-sm text-amber-800">Pipeline status: {pipeline.status}. Check stage results and report status.</p>}
      {dataUnavailable && <p role="status" className="m-4 text-sm text-amber-800">Connection interrupted. Showing the last available results; this is not an empty or completed run.</p>}
      <FinalReport />
      {failed.length > 0 && <div role="status" className="m-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
        <p className="font-bold">{failed.length} trial(s) could not be completed</p>
        <p>Other trials can continue. Failed trials have no reported performance.</p>
        {failed.map(task => <p key={task.task_id} className="mt-2">Trial {task.trial} · {task.task_type}: {task.error || "No diagnostic recorded"}</p>)}
      </div>}
      {!results ? (
        <EmptyState what="the results" />
      ) : results.length === 0 ? (
        <div className="p-8 text-ink-faint">No finished results yet.</div>
      ) : (
        <div className="space-y-5 p-4">
          <section className="rounded-lg border border-paper-line p-3">
            <h3 className="mb-2 text-sm font-bold">Performance by trial <Help topic="Performance by trial" /></h3>
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
            // The importances come off the result, not off the board. The board row is
            // cleaned away eventually and `memstara_results.task_id` is ON DELETE SET
            // NULL, so reading them from the task made the explanation disappear from
            // finished work — the AUC stayed and the reason for it did not.
            const imp = Object.entries(r.importance ?? {}).sort((a, b) => b[1] - a[1])
              .map(([col, v]) => ({ col, v }));
            // Asked for, but not in the cohort — the data stage's own list, not
            // `columns` minus `columns_used`. A hypothesis half of whose columns were
            // missing is a different claim from one that got everything it asked for.
            const missing = r.columns_missing ?? [];

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

                <p className="mt-2 font-mono text-[11px] text-ink-faint">
                  {(r.columns_used ?? []).length} column
                  {(r.columns_used ?? []).length === 1 ? "" : "s"} used
                  {missing.length > 0 && `, ${missing.length} asked for and missing`}
                  {(r.okf_concept_ids ?? []).length > 0 &&
                    ` · ${r.okf_concept_ids.length} OKF concept${r.okf_concept_ids.length === 1 ? "" : "s"} behind them`}
                </p>

                <section className="mt-3 rounded-lg border border-[#c9d9e8] bg-[#f6f9fc] p-3" aria-label="Clinical interpretation summary">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-bold text-ink">Clinical interpretation</h4>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${r.auc == null ? "bg-slate-100 text-slate-600" : r.auc <= 0.5 ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"}`}>
                      {r.auc == null ? "Evidence unavailable" : r.auc <= 0.5 ? "Hypothesis not supported by discrimination" : "Exploratory signal · requires validation"}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-ink-soft">The model used these features for this trial:</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(r.columns_used ?? []).map(column => <span key={column} className="rounded border border-[#c9d9e8] bg-white px-1.5 py-0.5 font-mono text-[10px] text-ink-soft">{column}</span>)}
                    {(r.columns_used ?? []).length === 0 && <span className="text-xs text-ink-faint">No features were recorded.</span>}
                  </div>
                  {r.evaluation?.interpreter && <p className="mt-2 text-xs text-ink-faint">Interpreter: {r.evaluation.interpreter.worker} · Skill: {r.evaluation.interpreter.skill || "Default instructions"}</p>}
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink">{r.interpretation || "No clinician-readable interpretation was recorded."}</p>
                  <p className="mt-2 text-[10px] text-ink-faint">Predictive association is not causation. A model response curve is not a validated treatment threshold.</p>
                </section>

                {/* Same red as a negative bar below — in this panel that colour means
                    "this is the direction that hurt", and a column the agent asked for
                    and did not get is that. */}
                {missing.length > 0 && (
                  <p className="mt-1 font-mono text-[11px] text-[#c0392b]">
                    missing: {missing.join(", ")}
                  </p>
                )}

                {imp.length > 0 && (
                  <div className="mt-4">
                    <h4 className="text-sm font-bold">Contributions <Help topic="Contributions" /></h4>
                    {/* The scale, beside the bars. Two engines produce two quantities and
                        neither the chart nor the tooltip could say which: gain sums to
                        about 1 and is never negative, permutation is an AUC delta on no
                        fixed scale and goes negative. Drawn without a scale, one result's
                        bar looks directly comparable to another's, and for two engines it
                        is not — the same reading `ml._importance` warns against. */}
                    <p className="mb-2 font-mono text-[11px] text-ink-faint">
                      {r.evaluation?.explanation?.method === "holdout_permutation_auc" ? "Hold-out permutation importance · change in AUC" : scaleNote(r.model)}
                    </p>
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

                <ExplanationEvidence result={r} />
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm font-bold hover:text-ink-soft">
                    Raw interpretation <Help topic="Interpretation" />
                  </summary>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{r.interpretation}</p>
                </details>

                {/* The one thing on this panel that is not in the snapshot. The matcher
                    record is too big to poll, so it is fetched per result when opened —
                    see WhyColumns. */}
                {r.evaluation?.data_quality && <div className="mt-3 rounded-lg border border-paper-line p-3 text-sm">
                  <p className="font-bold">Data quality &amp; training safeguards</p>
                  <p>{r.evaluation.data_quality.preprocessing}</p>
                  <p>Missing/non-finite predictor cells: {r.evaluation.data_quality.missing_predictor_cells}</p>
                  {r.evaluation.data_quality.warnings?.map((warning, index) => <p key={index} className="mt-1">{warning}</p>)}
                </div>}
                {r.evaluation && Object.keys(r.evaluation).length > 0 && <details className="mt-3 text-sm">
                  <summary className="cursor-pointer font-bold">Evaluation and explainability <Help topic="Evaluation and explainability" /></summary>
                  <p className="mt-2">{r.hypothesis_id} · seed {r.evaluation.seed ?? "not recorded"} · hold-out {r.evaluation.test_size ?? "not recorded"}</p>
                  <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(r.evaluation.evaluation?.plan, null, 2)}</pre>
                  <p className="mt-2 text-xs">{r.evaluation.explanation?.scope}</p>
                  {r.evaluation.explanation?.shap?.mean_absolute && <div className="mt-2">
                    <p className="font-bold">TreeSHAP · mean absolute contribution ({r.evaluation.explanation.shap.units})</p>
                    {Object.entries(r.evaluation.explanation.shap.mean_absolute).sort((a,b) => b[1]-a[1]).slice(0,10).map(([name, value]) =>
                      <p key={name} className="text-xs">{name}: {value.toFixed(4)}</p>)}
                  </div>}
                  {r.evaluation.explanation?.partial_dependence?.map(curve => <div key={curve.feature} className="mt-2">
                    <p className="text-xs font-bold">{curve.feature} · model response (not a clinical threshold)</p>
                    <table className="w-full text-xs"><thead><tr><th>Value</th><th>Predicted probability</th></tr></thead>
                      <tbody>{curve.values.map((v,i) => <tr key={i}><td>{v.toPrecision(4)}</td><td>{curve.predicted_probability[i]?.toFixed(3)}</td></tr>)}</tbody></table>
                  </div>)}
                  <p className="mt-2 text-xs text-ink-soft">{r.evaluation.explanation?.actionability}</p>
                </details>}
                <WhyColumns resultId={r.result_id} />
              </article>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
