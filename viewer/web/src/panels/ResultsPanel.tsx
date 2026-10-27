import ExecutionStatusNotice from "../components/ExecutionStatusNotice";
import { floorExecutionState } from '../lib/floorActivity';
import { loopLabel } from '../lib/loopLabel';
import { useExecutionContext } from '../components/ExecutionContext';
import { lazy, Suspense } from "react";
const InterpretationOutput = lazy(() => import("../components/InterpretationOutput"));
import { useEffect, useState, useMemo } from "react";
import { usePipelines } from "../store/pipelines";
import type { Result } from "../types";
import { BarChart3 } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Panel from "../components/Panel";
import { useBoard, useResults, useViewer, useSnapshot } from "../store/viewer";
import { newestResult, unreadResults, useResultNotices } from '../store/resultNotices';
import { useResultsReadReceipt } from '../lib/useResultsReadReceipt';

const resultKey = (result: Result) => `${result.run_tag || ''}:${result.result_id}`;

/**
 * Saved Interpretation documents only. Navigation and execution status stay outside
 * the agent documents; measured evidence and hypothesis prose are not added here.
 *
 * Opened as a dedicated Control view, or embedded in Telemetry for an inspected run.
 *
 * Experimental records are read-only. Read receipts live only in this browser.
 */

export default function ResultsPanel({ telemetry = false, embedded = false }: { telemetry?: boolean; embedded?: boolean } = {}) {
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
    `${r.pipeline_name || r.run_tag || 'Analysis'} · ${loopLabel(r, scope === 'selected' ? savedConfig?.trials : undefined, scope === 'selected' ? savedConfig?.combination_plan : undefined)}`;
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
    <Panel id="results-panel" icon={BarChart3} title="Results" embedded={embedded}>
      {scope==="selected" && <ExecutionStatusNotice key={savedTag} pipeline={pipeline} stale={statusStale} execution={floorExecutionState(executionOwner?.running)} label={executionContext.label} runTag={savedTag} loading={executionContext.loading}/>}
      {scope==="selected" && dataUnavailable && <p role="status" className="m-4 text-sm text-amber-800">Connection interrupted. Showing the last available results; this is not an empty or completed run.</p>}
      {!telemetry && <div className="m-4 flex flex-wrap gap-2 text-sm"><button className="rounded border border-paper-line px-3 py-2" aria-pressed={scope==="all"} onClick={()=>setScope("all")}>Latest executions across pipelines</button><button className="rounded border border-paper-line px-3 py-2" aria-pressed={scope==="selected"} onClick={()=>setScope("selected")}>This execution</button></div>}
      {!telemetry && scope==="selected" && <p className="mx-4 text-sm text-ink-soft">Viewing: <strong>{executionContext.label}</strong>. Includes its recorded replicates.</p>}
      {tags&&<p className="mx-4 mt-3 text-xs text-ink-soft">All recorded replicates from each pipeline's latest execution. Select an older run to inspect its archived results.</p>}
      {scope==="all"&&fetchError&&<p role="alert" className="m-4 text-sm text-amber-800">{fetchError}. Last available results are retained.</p>}
      {failed.length > 0 && <div role="status" className="m-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
        <p className="font-bold">{failed.length} analysis task(s) could not be completed</p>
        <p>Failed tasks have no reported performance. Check the execution status before continuing.</p>
        {failed.map(task => <p key={task.task_id} className="mt-2">{resultName(task)} · {task.task_type}: {task.error || "No diagnostic recorded"}</p>)}
      </div>}
      {!results ? (
        <EmptyState what="the results" />
      ) : results.length === 0 ? (
        <div className="p-8 text-ink-faint">{savedConfig?.data_mode==='proposal'?'Research proposal mode: no dataset is attached. Training, model metrics and SHAP/LIME computations are not executed. Open Conclusions to read the proposal.':'No finished results yet.'}</div>
      ) : (
        <div ref={receiptRef} className="space-y-5 p-4">
          {!telemetry && unread.length > 0 && <div className="results-arrival-note" role="status">
            <span>New results are ready.</span><button type="button" onClick={() => {
              const latest = newestResult(unread);
              if (latest) setChosenResult(resultKey(latest));
              useResultNotices.getState().acknowledge(results);
            }}>View latest results</button>
          </div>}
          <label className="analysis-select-label">Analysis
            <select aria-label="Analysis to inspect" value={activeResult ? resultKey(activeResult) : ''} onChange={e => chooseResult(e.target.value)}>
              {results.map(r => <option key={resultKey(r)} value={resultKey(r)}>{resultName(r)}</option>)}
            </select>
          </label>
          {activeResult && <article key={resultKey(activeResult)} className="selected-result-card rounded-lg border border-paper-line p-4" aria-label="Selected interpretation outputs">
            <p className="mb-4 text-xs font-semibold text-ink-soft">{resultName(activeResult)}</p>
            <Suspense fallback={<p role="status">Loading interpretation…</p>}>
              <InterpretationOutput result={activeResult} includeLimitations={false}/>
            </Suspense>
          </article>}
        </div>
      )}
      {!telemetry && <div className="m-4"><button type="button" className="text-sm font-semibold text-accent underline underline-offset-4" onClick={() => useViewer.getState().setView('report')}>Read Conclusions</button></div>}
    </Panel>
  );
}
