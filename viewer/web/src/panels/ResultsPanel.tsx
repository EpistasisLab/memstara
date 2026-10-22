import { displayText, displayJson, skillLabel } from '../lib/displayText';
import AucAssessment from '../components/AucAssessment';
import SpecialistEvidence from "../components/SpecialistEvidence";
import ExecutionStatusNotice from "../components/ExecutionStatusNotice";
import { floorExecutionState } from '../lib/floorActivity';
import { rankedContributions } from "../lib/featureImportance";
import ContentOrigin from "../components/ContentOrigin";
import { loopLabel } from '../lib/loopLabel';
import ResultExplorer, { resultKey } from "../components/ResultExplorer";
import ResultEvidenceVisuals from "../components/ResultEvidenceVisuals";
import { useExecutionContext } from '../components/ExecutionContext';
import { lazy, Suspense } from "react";
const ReportBody = lazy(() => import("../components/ReportBody"));
import { useEffect, useState, useMemo } from "react";
import { usePipelines } from "../store/pipelines";
import type { Result } from "../types";
import FinalReport from "../components/FinalReport";
import ExplanationEvidence from "../components/ExplanationEvidence";
import Help from "../components/Help";
import { BarChart3 } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Panel from "../components/Panel";
import WhyColumns from "../components/WhyColumns";
import { useBoard, useResults, useViewer, useSnapshot } from "../store/viewer";
import { newestResult, unreadResults, useResultNotices } from '../store/resultNotices';
import { useResultsReadReceipt } from '../lib/useResultsReadReceipt';

/**
 * Finished results — the results table, not the board.
 *
 * Available in the Floor plan analysis area; hidden in other workspace views. It carries `id="results-panel"` so the scene's results place can bring it
 * into view on a narrow screen (see ScenePanel's `onNodeClick`).
 *
 * Experimental records are read-only. Read receipts live only in this browser.
 */

export default function ResultsPanel({ telemetry = false }: { telemetry?: boolean } = {}) {
  const snapshot = useSnapshot();
  const [chosenResult, setChosenResult] = useState('');
  const executionContext = useExecutionContext();
  const selectedResults = useResults();
  const savedConfig=snapshot?.run_configuration;
  const savedTag=snapshot?.run_tag;
  const labeledSelected=useMemo(()=>selectedResults?.map(r=>({...r,run_tag:savedTag,
    pipeline_name:savedConfig?.pipeline_name,
    iteration:savedConfig?.trials?Math.floor(r.trial/savedConfig.trials)+1:null})),[selectedResults,savedTag,savedConfig?.pipeline_name,savedConfig?.trials]);
  const globalScope=usePipelines(s=>s.resultsScope);
  const scope=telemetry ? "selected" : globalScope;
  const setScope=(resultsScope:"all"|"selected")=>usePipelines.setState({resultsScope});
  const definitions = usePipelines(s=>s.items);
  const tags=scope==="selected"?"":definitions.map(p=>p.latest?.run_tag).filter(Boolean).sort().join(",");
  const [all,setAll]=useState<{tags:string;results:Result[];failures:(Pick<Result,"trial"|"run_tag"|"pipeline_name"|"iteration"> & {task_id:number;task_type:string;error:string})[]} | null>(null);
  const [fetchError,setFetchError]=useState("");
  useEffect(()=>{
    setFetchError("");
    if(!tags)return;
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>;
    const controller=new AbortController();
    const poll=async()=>{
      try{
        const response=await fetch(`/api/pipeline-results?run_tags=${encodeURIComponent(tags)}`,
          {signal:AbortSignal.any([controller.signal,AbortSignal.timeout(6000)])});
        const body=await response.json();
        if(!response.ok)throw Error(body.detail||"Results unavailable");
        if(!disposed){setAll({tags,results:body.results,failures:body.failures??[]});setFetchError("");}
      }catch(e){if(!disposed)setFetchError(String(e));}
      finally{if(!disposed)timer=setTimeout(poll,5000);}
    };
    void poll();
    return ()=>{disposed=true;controller.abort();clearTimeout(timer);};
  },[tags]);
  const results=scope==="all" ? (tags ? (all?.tags===tags?all.results:null) : []) : labeledSelected;
  const resultName=(r:Pick<Result,"trial"|"pipeline_name"|"iteration"|"run_tag">)=>
    `${r.pipeline_name || r.run_tag || 'Analysis'} · ${loopLabel(r, scope === 'selected' ? savedConfig?.trials : undefined)}`;
  const globalUnavailable = useViewer(s => !s.newRunMode && (s.snapshot?.health.memstara.up === false || !!s.error));
  const dataUnavailable = telemetry ? snapshot?.health.memstara.up === false : globalUnavailable;
  const pipeline = telemetry ? null : snapshot?.pipeline;
  const executionOwner=definitions.find(p=>p.running?.run_tag===savedTag);
  const controlError=usePipelines(s=>s.error);
  const statusStale = !!dataUnavailable || !!snapshot?.stale || !!controlError;
  const selectedFailed = (useBoard()?.tasks ?? []).filter(task => task.status === "failed");
  const failed = scope==="all" ? (tags && all?.tags===tags?all.failures:[]) : selectedFailed;

  const read = useResultNotices(state => state.read);
  const unread = unreadResults(results ?? [], read);
  const receiptRef = useResultsReadReceipt(results, scope === 'selected' ? savedTag ?? '' : tags,
    !telemetry && !dataUnavailable && !snapshot?.stale && !(scope === 'all' && fetchError));
  const activeResult = results?.find(r=>resultKey(r)===chosenResult) ?? newestResult(results ?? []);
  useEffect(()=>{if(activeResult && chosenResult !== resultKey(activeResult))setChosenResult(resultKey(activeResult));},[activeResult,chosenResult]);
  const chooseResult = (key: string) => {
    setChosenResult(key);
    const result = results?.find(item => resultKey(item) === key);
    if (!telemetry && result) useResultNotices.getState().acknowledge([result]);
  };

  return (
    <Panel id="results-panel" icon={BarChart3} title="Results">
      {scope==="selected" && <ExecutionStatusNotice key={savedTag} pipeline={pipeline} stale={statusStale} execution={floorExecutionState(executionOwner?.running)} label={executionContext.label} runTag={savedTag} loading={executionContext.loading}/>}
      {scope==="selected" && dataUnavailable && <p role="status" className="m-4 text-sm text-amber-800">Connection interrupted. Showing the last available results; this is not an empty or completed run.</p>}
      {!telemetry && <div className="m-4 flex flex-wrap gap-2 text-sm"><button className="rounded border border-paper-line px-3 py-2" aria-pressed={scope==="all"} onClick={()=>setScope("all")}>Latest executions across pipelines</button><button className="rounded border border-paper-line px-3 py-2" aria-pressed={scope==="selected"} onClick={()=>setScope("selected")}>This execution</button></div>}
      {!telemetry && scope==="selected" && <p className="mx-4 text-sm text-ink-soft">Viewing: <strong>{executionContext.label}</strong>. Includes its recorded loops.</p>}
      {tags&&<p className="mx-4 mt-3 text-xs text-ink-soft">All recorded loops from each pipeline's latest execution. Select an older run to inspect its archived results.</p>}
      {scope==="all"&&fetchError&&<p role="alert" className="m-4 text-sm text-amber-800">{fetchError}. Last available results are retained.</p>}
      {failed.length > 0 && <div role="status" className="m-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
        <p className="font-bold">{failed.length} analysis task(s) could not be completed</p>
        <p>Failed tasks have no reported performance. Check the execution status before continuing.</p>
        {failed.map(task => <p key={task.task_id} className="mt-2">{resultName(task)} · {task.task_type}: {task.error || "No diagnostic recorded"}</p>)}
      </div>}
      {!results ? (
        <EmptyState what="the results" />
      ) : results.length === 0 ? (
        <div className="p-8 text-ink-faint">{savedConfig?.data_mode==='proposal'?'Research proposal mode: no dataset is attached. Training, model metrics and SHAP/LIME computations are not executed. View the proposal report below.':'No finished results yet.'}</div>
      ) : (
        <div ref={receiptRef} className="space-y-5 p-4">
          {!telemetry && unread.length > 0 && <div className="results-arrival-note" role="status">
            <span>New results are ready.</span><button type="button" onClick={() => {
              const latest = newestResult(unread);
              if (latest) setChosenResult(resultKey(latest));
              useResultNotices.getState().acknowledge(results);
            }}>View latest results</button>
          </div>}
          <ResultExplorer results={results} selected={activeResult ? resultKey(activeResult) : ''} onSelect={chooseResult} />
          <h3 className="result-detail-heading">Selected analysis · evidence and interpretation</h3>
          {(activeResult ? [activeResult] : []).map((r) => {
            // The importances come off the result, not off the board. The board row is
            // cleaned away eventually and `memstara_results.task_id` is ON DELETE SET
            // NULL, so reading them from the task made the explanation disappear from
            // finished work — the AUC stayed and the reason for it did not.
            // Asked for, but not in the cohort — the data stage's own list, not
            // `columns` minus `columns_used`. A hypothesis half of whose columns were
            // missing is a different claim from one that got everything it asked for.
            const missing = r.columns_missing ?? [];
            const predictors = [...new Set(r.columns_used ?? [])].filter(column => column !== r.y_column);

            return (
              <article key={resultKey(r)} className="selected-result-card rounded-lg border border-paper-line p-4" aria-label="Selected analysis evidence">
                <header className="flex items-baseline justify-between gap-4">
                  <h3 className="font-bold">
                    {resultName(r)}
                    <span className="ml-2 font-normal text-ink-soft">{displayText(r.perspective)}</span>
                    {r.run_tag&&<span className="block break-all text-xs font-normal text-ink-faint">{r.run_tag}</span>}
                  </h3>
                  <span className="text-right">
                    <span className="font-mono text-xl font-bold">AUC {r.auc?.toFixed(4) ?? "—"}</span>
                    {r.y_column && (
                      <span className="block font-mono text-[12px] text-ink-faint">
                        → {r.y_column}
                      </span>
                    )}
                  </span>
                </header>

                <ContentOrigin kind="proposal" compact/><p className="mt-2 text-sm leading-relaxed text-ink-soft">{displayText(r.hypothesis)}</p>

                <p className="mt-2 font-mono text-[12px] text-ink-faint">
                  {predictors.length} predictor
                  {predictors.length === 1 ? "" : "s"} used
                  {missing.length > 0 && `, ${missing.length} asked for and missing`}
                  {(r.okf_concept_ids ?? []).length > 0 &&
                    ` · ${r.okf_concept_ids.length} OKF concept${r.okf_concept_ids.length === 1 ? "" : "s"} behind them`}
                </p>

                {r.evaluation?.data_allocation && <section aria-label="Data allocation" className="mt-3 rounded border border-paper-line p-3 text-sm">
                  <strong>Data allocation · {skillLabel(r.evaluation.data_allocation.request.skill)}</strong>
                  <p>Requested training/evaluation: {Math.round((1-r.evaluation.data_allocation.agent_plan.test_size)*100)}% / {Math.round(r.evaluation.data_allocation.agent_plan.test_size*100)}% of {r.evaluation.data_allocation.exploration_count} exploration rows.</p>
                  <p>{r.evaluation.data_allocation.reserved_count} independent validation rows remain reserved{r.evaluation.data_allocation.validation_partition ? ` (${Math.round(r.evaluation.data_allocation.validation_partition.fraction*100)}%, seed ${r.evaluation.data_allocation.validation_partition.seed})` : ''}. Stratification preserves observed class proportions; no class resampling.</p>
                  {r.evaluation.data_allocation.replicates.map((split, index)=><p key={index}>
                    Split {index+1} · seed {split.seed} · training {split.n_train} rows · evaluation {split.n_test} rows.
                    {' '}Class counts (training / evaluation): {Object.keys(split.train_class_counts).map(k=>`${k}: ${split.train_class_counts[k]} / ${split.test_class_counts[k] ?? 0}`).join('; ')}
                  </p>)}
                </section>}
                {r.evaluation?.model_results && <section aria-label="Selected ML model results" className="mt-3 rounded border border-paper-line p-3 text-sm">
                  <strong>Selected model · {Object.keys(r.evaluation.model_results)[0]}</strong>
                  <p>These are exploratory scores, not independent validation.</p>
                  <div className="grid gap-3 md:grid-cols-2">
                    {Object.entries(r.evaluation.model_results ?? {}).map(([name, model])=><div key={name} className="min-w-0 rounded border border-paper-line p-2">
                      <strong>{name}</strong><p>AUROC {model.auc.toFixed(4)} · training {model.n_train} · evaluation {model.n_test}</p>
                      {model.evaluation.replicates.map((split,i)=><div key={i}>
                        <p>Split {i+1} · seed {split.seed} · AP {split.average_precision.toFixed(4)} · cutoff {split.operating_point.probability_cutoff}</p>
                        <table aria-label={`${name} confusion matrix split ${i+1}`} className="w-full text-xs"><thead><tr><th>Actual / predicted</th><th>0</th><th>1</th></tr></thead><tbody>
                          <tr><th>0</th><td>{split.operating_point.true_negative}</td><td>{split.operating_point.false_positive}</td></tr>
                          <tr><th>1</th><td>{split.operating_point.false_negative}</td><td>{split.operating_point.true_positive}</td></tr>
                        </tbody></table>
                      </div>)}
                      <SpecialistEvidence evidence={model.specialist_xai} />
                      <p>Replay: {model.evaluation.reproducibility?.status ?? 'not recorded'}</p>
                      <details><summary>Model parameters and replay location</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{displayJson({configuration:model.ml_configuration,replay:model.evaluation.reproducibility})}</pre></details>
                    </div>)}
                  </div>
                  <details><summary>Agent proposal and enforced limits</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{displayJson(r.evaluation.ml_configuration)}</pre></details>
                </section>}
                <ResultEvidenceVisuals key={resultKey(r)} result={r} />
                <section className="mt-3 rounded-lg border border-[#c9d9e8] bg-stage-data/5 p-3" aria-label="Clinical interpretation summary">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-bold text-ink">Clinical interpretation</h4>
                    <AucAssessment auc={r.auc}/>
                  </div>
                  <ContentOrigin kind="rule" compact/><p className="text-xs text-ink-soft">The status above uses a fixed rule: AUC unavailable, AUC &lt; 0.5, AUC = 0.5, or AUC &gt; 0.5. It is not a research-priority assessment.</p><p className="mt-2 text-xs text-ink-soft">Predictor inputs used by the model:</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {r.evaluation?.feature_selection && <p className="w-full text-xs text-ink-soft">
                      Hypothesis selection: {r.evaluation.feature_selection.mode} · {r.evaluation.feature_selection.actual_count} original predictors
                      {' '}· allowed {r.evaluation.feature_selection.minimum}–{r.evaluation.feature_selection.maximum}
                      {' '}· eligible pool {r.evaluation.feature_selection.pool_size}
                      {r.evaluation.feature_selection.seed != null && <> · random seed {r.evaluation.feature_selection.seed}</>}
                      {' '}· Loop {r.evaluation.feature_selection.loop} · combination {r.evaluation.feature_selection.combination}.
                      The list below contains the predictors recorded for this evaluated result.
                    </p>}
                    {predictors.map(column => <span key={column} className="rounded border border-[#c9d9e8] bg-white px-1.5 py-0.5 font-mono text-[12px] text-ink-soft">{column}</span>)}
                    {(r.columns_used ?? []).length === 0 && <span className="text-xs text-ink-faint">No features were recorded.</span>}
                  </div>
                  {r.evaluation?.interpreter && <p className="mt-2 text-xs text-ink-faint">Interpreter: {displayText(r.evaluation.interpreter.worker)} · Skill: {skillLabel(r.evaluation.interpreter.skill,null,"Default instructions")}</p>}
                  {r.evaluation?.interpretations && <div className="mt-3 space-y-2">
                    <p className="text-xs font-bold">Interpreter perspectives: {r.evaluation.interpretations.filter(i => i.status === "done").length}/{r.evaluation.interpretations.length} complete</p>
                    {r.evaluation.interpretations.map(i => <details key={i.slot} className="rounded border border-paper-line p-2">
                      <summary className="cursor-pointer text-xs">{displayText(i.worker)} · {skillLabel(i.skill,null,"Default instructions")} · {i.status}</summary>
                      <Suspense fallback={<p>Loading formatted explanation…</p>}><ReportBody origin={i.status === "done" ? "llm" : undefined} text={i.status === "done" ? i.text : "This perspective is not yet available."} /></Suspense>
                    </details>)}
                  </div>}
                  <p className="mt-2 text-sm text-ink-soft">Prediction target (not an input): <strong>{r.y_column || "Not recorded"}</strong></p>
                  <details className="mt-3" open><summary className="cursor-pointer font-semibold">Read the interpreter’s explanation</summary><Suspense fallback={<p>Loading formatted explanation…</p>}><ReportBody origin={r.interpretation ? "llm" : undefined} text={r.interpretation || "No interpretation was recorded."} /></Suspense></details>
                  <p className="mt-2 text-[12px] text-ink-faint">Predictive association is not causation. A model response curve is not a validated treatment threshold.</p>
                </section>

                {/* Same red as a negative bar below — in this panel that colour means
                    "this is the direction that hurt", and a column the agent asked for
                    and did not get is that. */}
                {missing.length > 0 && (
                  <p className="mt-1 font-mono text-[12px] text-[#c0392b]">
                    missing: {missing.join(", ")}
                  </p>
                )}

                <details className="mt-4"><summary className="cursor-pointer font-semibold">Review detailed explainability evidence and limitations</summary><ExplanationEvidence result={r} /></details>
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm font-bold hover:text-ink-soft">
                    Full interpretation document
                  </summary>
                  <Suspense fallback={<p>Loading formatted explanation…</p>}><ReportBody origin={r.interpretation ? "llm" : undefined} text={r.interpretation || "No interpretation was recorded."} /></Suspense>
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
                  <summary className="cursor-pointer font-bold">Evaluation and explainability</summary>
                  <p className="mt-2"><Help topic="Evaluation and explainability" /> How to read evaluation evidence</p>
                  <p className="mt-2">{r.hypothesis_id} · seed {r.evaluation.seed ?? "not recorded"} · hold-out {r.evaluation.test_size ?? "not recorded"}</p>
                  <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs">{displayJson(r.evaluation.evaluation?.plan)}</pre>
                  <Suspense fallback={null}><ReportBody origin="rule" text={r.evaluation.explanation?.scope || ""} /></Suspense>
                  {r.evaluation.explanation?.shap?.mean_absolute && <div className="mt-2">
                    <p className="font-bold">TreeSHAP · mean absolute contribution ({r.evaluation.explanation.shap.units})</p>
                    {rankedContributions(r.evaluation.explanation.shap.mean_absolute, r.y_column, true).slice(0,10).map(([name, value]) =>
                      <p key={name} className="text-xs">{name}: {value.toFixed(4)}</p>)}
                  </div>}
                  {r.evaluation.explanation?.partial_dependence?.map(curve => <div key={curve.feature} className="mt-2">
                    <p className="text-xs font-bold">{curve.feature} · model response (not a clinical threshold)</p>
                    <div className="report-table-scroll" role="region" aria-label="Model response values" tabIndex={0}><table className="result-values-table"><thead><tr><th scope="col">Value</th><th scope="col">Predicted probability</th></tr></thead>
                      <tbody>{curve.values.map((v,i) => <tr key={i}><td>{v.toPrecision(4)}</td><td>{curve.predicted_probability[i]?.toFixed(3)}</td></tr>)}</tbody></table></div>
                  </div>)}
                  <Suspense fallback={null}><ReportBody origin="rule" text={r.evaluation.explanation?.actionability || ""} /></Suspense>
                </details>}
                <WhyColumns resultId={r.result_id} />
              </article>
            );
          })}
        </div>
      )}
      {!telemetry && scope==="selected" && <details className="m-4 rounded-lg border border-paper-line p-4"><summary className="cursor-pointer font-semibold">Open the report for this execution</summary><FinalReport /></details>}
    </Panel>
  );
}
