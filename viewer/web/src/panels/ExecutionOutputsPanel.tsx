import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BarChart3, FileText, Layers3, Download } from 'lucide-react';
import { useViewer } from '../store/viewer';
import { usePipelines } from '../store/pipelines';
import { useOutputNavigation } from '../store/outputNavigation';
import { useResultNotices } from '../store/resultNotices';
import { outputNoticeKeys } from '../lib/outputNotices';
import { useOutputReadReceipt } from '../lib/useOutputReadReceipt';
import { useExecutionContext } from '../components/ExecutionContext';
import { useTelemetryTotals } from '../components/TelemetryTotals';
import InterpretationOutput from '../components/InterpretationOutput';
import ReportBody from '../components/ReportBody';
import TelemetryPanel from './TelemetryPanel';
import { executionTiles, tileComplete, tileStatus, testAuroc, outputViewNames, type ExecutionTile, type OutputView } from '../lib/executionTiles';
import { identityLabel } from '../lib/replicateIdentity';
import { costLabel, usageDuration } from '../lib/loopUsage';
import type { Result } from '../types';
import { recordedModels } from '../lib/recordedModel';
import type {Observation} from '../lib/confusionMetrics';
import {resultForObservation} from '../lib/skillComparison';
import './execution-outputs.css';

const views = ['results', 'report', 'agents'] as const;
const icons = {results: BarChart3, report: FileText, agents: Layers3};
const positions = new Map<string, {top: number; loop?: number}>();

function ResultMetadata({result, compact = false}: {result: Result; compact?: boolean}) {
  const predictors = result.columns_used?.filter(column => column !== result.y_column) ?? [];
  const models = recordedModels(result);
  return <dl className={`output-record-meta${compact ? ' is-compact' : ''}`}>
    <div className="output-model-meta"><dt>Model</dt><dd>{models.map(model => model.family + (model.primary ? ' (primary)' : '')).join(', ')}</dd></div>
    <div className="output-parameter-meta"><dt>Recorded parameters</dt><dd>{models.map(model => <div key={model.family} className="output-model-parameters">
      {models.length > 1 && <strong>{model.family}</strong>}
      {model.fits.length ? model.fits.map(fit => <div key={fit.index}>
        {model.fits.length > 1 && <strong>Fit {fit.index}: </strong>}
        <span>{fit.parameters ? `Fitted: ${fit.parameters}` : 'Fitted parameters not recorded'}</span>
        {fit.seed !== undefined && <p>Recorded fit seed: {fit.seed}</p>}
        {fit.threshold !== undefined && <p>Decision threshold: {fit.threshold}</p>}
      </div>) : <span>Fitted parameters not recorded</span>}
      {!model.fits.some(fit => fit.parameters) && model.configured && <p>Configured (not verified as fitted): {model.configured}</p>}
    </div>)}</dd></div>
    <div className="output-target-meta"><dt>Target</dt><dd title={compact ? result.y_column : undefined}>{result.y_column || 'Not recorded'}</dd></div>
    <div className="output-predictor-meta"><dt>Predictors{predictors.length ? ` · ${predictors.length}` : ''}</dt><dd className={compact ? 'output-column-preview' : undefined} title={compact ? predictors.join(', ') : undefined}>{predictors.length ? predictors.join(', ') : 'Not recorded'}</dd></div>
    <div className="output-test-metric"><dt>Test AUROC</dt><dd data-reported={testAuroc(result) !== 'Not reported'}>{testAuroc(result)}</dd></div>
  </dl>;
}

function Tile({tile, view, target, onOpen}: {tile: ExecutionTile; view: OutputView; target?: string; onOpen: () => void}) {
  const status = tileStatus(tile, view);
  const metric = tile.usage;
  return <button type="button" className="execution-output-tile" data-view={view} data-loop={tile.loop} onClick={onOpen} aria-label={`Open ${outputViewNames[view]}: ${identityLabel(tile)}`}>
    <span className="output-tile-heading"><span className="output-tile-identity"><strong>Pipeline {tile.pipeline_number ?? '—'}</strong><span>Replicate {tile.replicate_number ?? tile.loop}</span></span><span className="output-status" data-ready={status === 'Ready'} data-warning={tile.failed || status === 'Partial output'}>{status}</span></span>
    {tile.results.length ? <div className="output-tile-records">{tile.results.map(result => <div key={result.result_id}>{tile.results.length > 1 && <p className="output-analysis-label">Analysis {result.result_id}</p>}<ResultMetadata result={result} compact/></div>)}</div>
      : <dl className="output-record-meta"><div><dt>Target</dt><dd>{target || 'Not recorded'}</dd></div><div><dt>Predictors & model</dt><dd>Available when recorded</dd></div><div><dt>Test AUROC</dt><dd>Not reported</dd></div></dl>}
    {view === 'report' && <p className="output-tile-note">{tile.explanations.filter(o => o.text).length} saved Explanation {tile.explanations.filter(o => o.text).length === 1 ? 'output' : 'outputs'}</p>}
    {view === 'agents' && <dl className="output-usage-preview"><div><dt>Time</dt><dd>{usageDuration(metric?.seconds)}</dd></div><div><dt>Estimated cost</dt><dd>{costLabel(metric?.cost)}</dd></div><div><dt>Tokens</dt><dd>{!metric || metric.tokens_status === 'unavailable' ? 'Not recorded' : `${metric.tokens.toLocaleString()}${metric.tokens_status === 'partial' ? ' · partial' : ''}`}</dd></div></dl>}
    <span className="output-tile-link">View {outputViewNames[view].toLowerCase()}<ArrowRight size={16} aria-hidden="true"/></span>
  </button>;
}

function downloadOutput(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob([text], {type: 'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** One shared list/detail boundary for Results, Conclusions and Usage. */
import HypothesisResultsTable from '../components/HypothesisResultsTable';

export default function ExecutionOutputsPanel({view}: {view: OutputView}) {
  const snapshot = useViewer(s => s.snapshot);
  const requested = useViewer(s => s.runTag);
  const error = useViewer(s => s.error);
  const items = usePipelines(s => s.items);
  const context = useExecutionContext();
  const totals = useTelemetryTotals();
  const tag = snapshot?.run_tag ?? '';
  const usage = (totals.data?.experiments ?? totals.data?.executions)?.find(e => e.run_tag === tag);
  const allTiles = useMemo(() => snapshot ? executionTiles(snapshot, usage) : [], [snapshot, usage]);
  const tiles = allTiles.filter(tile => tileComplete(tile, view));
  const [chartSelection,setChartSelection]=useState<{tag:string;observation:Observation}|null>(null);
  const [chartError,setChartError]=useState('');
  const chartTile=view==='results'&&chartSelection?.tag===tag?allTiles.find(tile=>resultForObservation(tile.results.map(result=>({...result,run_tag:result.run_tag??tag})),chartSelection.observation)):undefined;
  const selection = useOutputNavigation(s => s.selection);
  const active = selection?.tag === tag ? tiles.find(tile => tile.loop === selection.loop)??(chartTile?.loop===selection.loop?chartTile:undefined) : undefined;
  const waiting = !!requested && requested !== tag;
  const root = useRef<HTMLDivElement>(null);
  const comparison=useRef<HTMLDivElement>(null),selectedDocument=useRef<HTMLElement>(null);
  const noticeKeys = useMemo(() => snapshot && active && view !== 'results'
    ? outputNoticeKeys(snapshot, usage, view, active.loop) : [], [snapshot, active, usage, view]);
  useOutputReadReceipt(root, noticeKeys, !!active && !waiting && !error && !snapshot?.stale
    && snapshot?.health.memstara.up !== false && (view !== 'agents' || !totals.error));
  const heading = useRef<HTMLHeadingElement>(null);
  const listKey = `${tag}:${view}`;
  const detailLoop = active?.loop;
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (!root.current) return;
      if (detailLoop !== undefined) { root.current.scrollTop = 0; heading.current?.focus({preventScroll: true}); }
      else {
        const saved = positions.get(listKey);
        root.current.scrollTop = saved?.top ?? 0;
        if (saved?.loop) root.current.querySelector<HTMLButtonElement>(`button[data-loop="${saved.loop}"]`)?.focus({preventScroll: true});
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [listKey, detailLoop]);
  useEffect(() => {
    if (view === 'results' && active && !waiting && !error && !snapshot?.stale) useResultNotices.getState().acknowledge(active.results.map(result => ({...result, run_tag: result.run_tag ?? tag})));
  }, [view, active, waiting, error, snapshot?.stale, tag]);
  const open = (tile: ExecutionTile) => {
    setChartSelection(null);setChartError('');
    positions.set(listKey, {top: root.current?.scrollTop ?? 0, loop: tile.loop});
    useOutputNavigation.getState().open(tag, tile.loop);
  };
  const openChartResult=(observation:Observation)=>{
    const tile=allTiles.find(item=>resultForObservation(item.results.map(result=>({...result,run_tag:result.run_tag??tag})),observation));
    if(!tile){setChartError('This evaluation could not be linked to a saved result in this experiment. Refresh and try again.');return;}
    positions.set(listKey,{top:root.current?.scrollTop??0,loop:tile.loop});
    setChartError('');setChartSelection({tag,observation});
    useOutputNavigation.getState().open(tag,tile.loop);
  };
  useEffect(()=>{
    if(chartSelection?.tag!==tag||view!=='results'||chartTile?.loop!==detailLoop)return;
    const frame=requestAnimationFrame(()=>{
      const document=selectedDocument.current;if(!document)return;
      document.focus({preventScroll:true});document.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    });
    return ()=>cancelAnimationFrame(frame);
  },[chartSelection,chartTile?.loop,detailLoop,tag,view]);
  const backToComparison=()=>{
    comparison.current?.focus({preventScroll:true});comparison.current?.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  };
  const navigate = (next: OutputView, preserveOutputSelection = false) =>
    useViewer.getState().setView(next, {preserveOutputSelection});
  const pipelineCount = new Set(tiles.map(tile => tile.pipeline_number).filter(Boolean)).size;
  return <div ref={root} className="execution-outputs" data-testid="execution-outputs" onScroll={() => {
    if (!active) positions.set(listKey, {...positions.get(listKey), top: root.current?.scrollTop ?? 0});
  }}>
    <header className="output-workspace-header">
      <div><p className="output-eyebrow">Experiment outputs</p><h2>{context.name}</h2><p>{tag ? context.startedLabel : 'Choose an experiment with a saved execution.'}</p>
        {snapshot?.experiment&&<p className="output-experiment-scope">{snapshot.experiment.result_combinations} of {snapshot.experiment.scheduled_combinations??snapshot.experiment.result_combinations} combinations recorded · {snapshot.experiment.run_tags.length} execution {snapshot.experiment.run_tags.length===1?'attempt':'attempts'} · One experiment</p>}
      </div>
      <label className="output-experiment-picker">Experiment<select aria-label="Experiment outputs to inspect" value={context.owner?.id ?? ''} onChange={e => {useOutputNavigation.getState().back(); usePipelines.getState().select(e.target.value);}}>
        <option value="" disabled>{tag ? context.name : 'Choose an experiment'}</option>
        {items.map(item => <option key={item.id} value={item.id}>{item.name}{item.latest ? '' : ' · not started'}</option>)}
      </select></label>
    </header>
    <nav className="output-view-navigation" aria-label="Output views">{views.map(next => {const Icon = icons[next]; return <button type="button" key={next} aria-current={view === next ? 'page' : undefined} onClick={() => navigate(next)}><Icon size={17} aria-hidden="true"/>{outputViewNames[next]}</button>;})}</nav>
    {view === 'results' && !waiting && <div ref={comparison} tabIndex={-1} className="result-comparison-anchor" aria-label="Hypothesis performance comparison"><HypothesisResultsTable key={tag} runTag={tag} results={(snapshot?.results ?? []).map(result => ({...result, run_tag: result.run_tag ?? tag}))} plannedSkills={snapshot?.run_configuration?.combination_plan?.skills?.hypothesis?.map(skill=>skill.id)}
      skillTitles={Object.fromEntries((snapshot?.run_configuration?.combination_plan?.skills?.hypothesis??[]).filter(skill=>skill.title).map(skill=>[skill.id,skill.title!]))} onOpenResult={openChartResult}/>
      {chartError&&<p role="alert" className="output-notice">{chartError}</p>}
    </div>}
    {(snapshot?.report?.run_tags?.length ?? 0) > 1 && <p className="output-notice">Includes retained outputs and usage from {snapshot?.report?.run_tags?.length} continued executions of this experiment.</p>}
    {(error || snapshot?.stale || (view === 'agents' && totals.error)) && <p className="output-notice" role="status">Updates are delayed. Showing the last available records for this execution. Missing records do not indicate a completed or empty run.</p>}
    {waiting ? <p className="output-empty" role="status">Loading the selected execution…</p> : !snapshot ? <p className="output-empty" role="status">{requested ? 'Loading execution records…' : 'Select an experiment to browse its outputs.'}</p> : active ? <>
      <header className="output-detail-header">
        <button type="button" className="output-back" onClick={() => useOutputNavigation.getState().back()}><ArrowLeft size={17} aria-hidden="true"/>Back to {outputViewNames[view]}</button>
        <div><p className="output-eyebrow">{view === 'results' ? 'Interpretation agent output' : view === 'report' ? 'Explanation agent output' : 'Recorded usage'}</p><h3 ref={heading} tabIndex={-1}>{identityLabel(active)}</h3></div>
        <nav aria-label="Related execution views">{views.filter(next => next !== view).map(next => <button type="button" key={next} disabled={!tileComplete(active, next)} title={tileComplete(active, next) ? undefined : 'Available when complete'} onClick={() => navigate(next, true)}>
          {(next === 'results' || (view === 'agents' && next === 'report')) && <ArrowLeft size={15} aria-hidden="true"/>}
          {outputViewNames[next]}
          {next !== 'results' && !(view === 'agents' && next === 'report') && <ArrowRight size={15} aria-hidden="true"/>}
        </button>)}</nav>
      </header>
      <details className="output-data-details"><summary>Model parameters, data columns & recorded metrics</summary>{active.results.length ? active.results.map(result => <section key={result.result_id}><h4>Analysis {result.result_id}</h4><ResultMetadata result={result}/></section>) : <p>No model or column record has been saved for this replicate yet.</p>}</details>
      {view === 'results' && <div className="output-documents">{active.results.length ? active.results.map(result => {
        const observation=chartSelection?.tag===tag?chartSelection.observation:null;
        const selected=!!(observation&&resultForObservation([{...result,run_tag:result.run_tag??tag}],observation));
        return <article key={`${result.run_tag??tag}:${result.result_id}`} ref={selected?selectedDocument:undefined} tabIndex={selected?-1:undefined} className={selected?'selected-result-card':undefined} data-chart-selected={selected?'true':undefined} aria-label={`Interpretation output for analysis ${result.result_id}`}>
          {selected&&observation&&<header className="result-chart-context"><div><strong>Selected from performance comparison</strong><button type="button" onClick={backToComparison}>Back to comparison</button></div><p>Result {observation.resultId} · {observation.model} · Fit {observation.replicate} · Seed {observation.seed??'not recorded'}</p><p>Original execution: {observation.runTag}</p></header>}
          <header className="output-document-header"><h4>Interpretation · Analysis {result.result_id}</h4></header><InterpretationOutput result={result} includeLimitations={false}/></article>;
      }) : <p className="output-empty">No Interpretation output has been saved for this replicate yet.</p>}</div>}
      {view === 'report' && <div className="output-documents">{active.explanations.length ? active.explanations.map((output, index) => <article key={`${output.result_id}:${index}`} aria-label={`Explanation output ${index + 1}`}><header className="output-document-header"><h4>Explanation output {index + 1}<span>{output.status}</span></h4><button type="button" disabled={!output.text} onClick={() => downloadOutput(output.text, `${tag}_pipeline-${active.pipeline_number}_replicate-${active.replicate_number}_explanation-${index + 1}.md`)}><Download size={15} aria-hidden="true"/>Download Markdown</button></header>{output.text ? <ReportBody verbatim text={output.text}/> : <p>No Explanation text has been saved for this output yet.</p>}</article>) : <p className="output-empty">No Explanation output has been saved for this replicate yet.</p>}</div>}
      {view === 'agents' && <TelemetryPanel key={`${tag}:${active.loop}:${active.record_run_tag}`} lockedLoop={active.loop} recordRunTag={active.record_run_tag}/>}
    </> : <>
      <div className="output-list-heading"><div><h3>{outputViewNames[view]}</h3><p>Completed {view === 'agents' ? 'replicates' : 'outputs'} only. Choose a tile to view details.</p></div><span>{pipelineCount} {pipelineCount === 1 ? 'pipeline' : 'pipelines'} · {tiles.length} {tiles.length === 1 ? 'replicate' : 'replicates'}</span></div>
      <div className="execution-output-grid">{tiles.map(tile => <Tile key={`${tag}:${tile.loop}`} tile={tile} view={view} target={snapshot.run_configuration?.y_column} onOpen={() => open(tile)}/>)}</div>
      {!tiles.length && <p className="output-empty">{view === 'agents' ? 'No completed replicates yet. Usage tiles appear when each replicate finishes.' : `No completed ${outputViewNames[view].toLowerCase()} yet. Tiles appear when the outputs are complete.`}</p>}
    </>}
  </div>;
}
