import { useEffect, useMemo, useRef, useState } from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
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
import { executionTiles, tileComplete, testAuroc, outputViewNames, type ExecutionTile, type OutputView } from '../lib/executionTiles';
import {useOutputDetail} from '../lib/useOutputDetail';
import { identityLabel } from '../lib/replicateIdentity';
import type { Result, Snapshot } from '../types';
import { recordedModels } from '../lib/recordedModel';
import {experimentProgressLabel} from '../lib/pipelineProgress';
import type {Observation} from '../lib/confusionMetrics';
import {resultForObservation} from '../lib/skillComparison';
import OutputSkillFlow from '../components/OutputSkillFlow';
import {tileSkillConfiguration} from '../lib/tileSkills';
import {DEFAULT_TILE_FILTERS, filterOutputTiles, outputTileFilterIndex, type TileSort} from '../lib/outputTileFilters';
import {skillLabel} from '../lib/displayText';
import './execution-outputs.css';

const views = ['results', 'report', 'agents'] as const;
const icons = {results: BarChart3, report: FileText, agents: Layers3};
const positions = new Map<string, {top: number; loop?: number}>();

function Predictors({columns, compact}: {columns: string[]; compact: boolean}) {
  const preview = useRef<HTMLElement>(null);
  const [open, setOpen] = useState(false);
  const text = columns.length ? columns.join(' ● ') : 'Not recorded';
  if (!compact || !columns.length) return <dd>{text}</dd>;
  return <Tooltip.Root open={open} delayDuration={200} disableHoverableContent={false}
    onOpenChange={next => setOpen(next && !!preview.current && preview.current.scrollHeight > preview.current.clientHeight)}>
    <Tooltip.Trigger asChild>
      <dd ref={preview} className="output-column-preview" data-context-help-managed>{text}</dd>
    </Tooltip.Trigger>
    <Tooltip.Portal>
      <Tooltip.Content className="output-predictors-popup" side="bottom" align="start" sideOffset={8}
        collisionPadding={12} hideWhenDetached onClick={event => event.stopPropagation()}>
        <strong>Predictors · {columns.length}</strong>
        <ul>{columns.map((column, index) => <li key={`${index}:${column}`}><span aria-hidden="true">●</span><span>{column}</span></li>)}</ul>
      </Tooltip.Content>
    </Tooltip.Portal>
  </Tooltip.Root>;
}

function RecordedParameters({models, compact}: {models: ReturnType<typeof recordedModels>; compact: boolean}) {
  const preview = useRef<HTMLElement>(null);
  const [open, setOpen] = useState(false);
  const body = models.map(model => <div key={model.family} className="output-model-parameters">
      {models.length > 1 && <strong>{model.family}</strong>}
      {model.fits.length ? model.fits.map(fit => <div key={fit.index}>
        {model.fits.length > 1 && <strong>Fit {fit.index}: </strong>}
        <span>{fit.parameters ? `Fitted: ${fit.parameters}` : 'Fitted parameters not recorded'}</span>
        {fit.seed !== undefined && <p>Recorded fit seed: {fit.seed}</p>}
        {fit.threshold !== undefined && <p>Decision threshold: {fit.threshold}</p>}
      </div>) : <span>Fitted parameters not recorded</span>}
      {!model.fits.some(fit => fit.parameters) && model.configured && <p>Configured (not verified as fitted): {model.configured}</p>}
    </div>);
  if (!compact) return <dd>{body}</dd>;
  const summary = models.map(model => [
    ...(models.length > 1 ? [model.family] : []),
    ...(model.fits.length ? model.fits.map(fit => [
      models.length > 1 || model.fits.length > 1 ? `Fit ${fit.index}` : '',
      fit.parameters ? `Fitted: ${fit.parameters}` : 'Fitted parameters not recorded',
      fit.seed !== undefined ? `Recorded fit seed: ${fit.seed}` : '',
      fit.threshold !== undefined ? `Decision threshold: ${fit.threshold}` : '',
    ].filter(Boolean).join(' · ')) : ['Fitted parameters not recorded']),
    !model.fits.some(fit => fit.parameters) && model.configured ? `Configured (not verified as fitted): ${model.configured}` : '',
  ].filter(Boolean).join(' · ')).join(' | ');
  return <Tooltip.Root open={open} delayDuration={200} disableHoverableContent={false}
    onOpenChange={next => setOpen(next && !!preview.current && preview.current.scrollHeight > preview.current.clientHeight)}>
    <Tooltip.Trigger asChild>
      <dd ref={preview} className="output-column-preview output-parameter-preview" data-context-help-managed>{summary}</dd>
    </Tooltip.Trigger>
    <Tooltip.Portal>
      <Tooltip.Content className="output-parameters-popup" side="bottom" align="start" sideOffset={8}
        collisionPadding={12} hideWhenDetached onClick={event => event.stopPropagation()}>
        <strong className="output-parameters-popup-title">Recorded parameters</strong>
        {body}
      </Tooltip.Content>
    </Tooltip.Portal>
  </Tooltip.Root>;
}

function ResultMetadata({result, compact = false}: {result: Result; compact?: boolean}) {
  const predictors = result.columns_used?.filter(column => column !== result.y_column) ?? [];
  const models = recordedModels(result);
  return <dl className={`output-record-meta${compact ? ' is-compact' : ''}`}>
    <div className="output-model-meta"><dt>Model</dt><dd>{models.map(model => model.family + (model.primary ? ' (primary)' : '')).join(', ')}</dd></div>
    <div className="output-parameter-meta"><dt>Recorded parameters</dt><RecordedParameters models={models} compact={compact}/></div>
    {!compact && <div className="output-target-meta"><dt>Target</dt><dd>{result.y_column || 'Not recorded'}</dd></div>}
    <div className="output-predictor-meta"><dt>Predictors{predictors.length ? ` · ${predictors.length}` : ''}</dt><Predictors columns={predictors} compact={compact}/></div>
    {!compact && <div className="output-test-metric"><dt>Test AUROC</dt><dd data-reported={testAuroc(result) !== 'Not reported'}>{testAuroc(result)}</dd></div>}
  </dl>;
}

function Tile({tile, view, target, snapshot, onOpen}: {tile: ExecutionTile; view: OutputView; target?: string; snapshot: Snapshot; onOpen: () => void}) {
  const metric = tile.usage;
  const sources = [...new Set(view === 'results' ? tile.results.map(result => result.run_tag ?? snapshot.run_tag)
    : view === 'report' ? tile.explanations.map(output => output.run_tag ?? snapshot.run_tag)
    : metric?.run_tags?.length ? metric.run_tags : [tile.record_run_tag])];
  const source = sources.length === 1 ? sources[0] : undefined;
  return <article className="execution-output-tile" data-view={view} data-loop={tile.loop} aria-label={identityLabel(tile)} onClick={onOpen}>
    <button type="button" className="output-tile-open" data-loop={tile.loop} onClick={event => {event.stopPropagation(); onOpen();}}
      aria-label={`Open ${outputViewNames[view]}: ${identityLabel(tile)}`}/>
    <div className="output-tile-overviews">{tile.results.length ? tile.results.map(result =>
      <dl key={result.result_id} className="output-tile-overview" aria-label={`Analysis ${result.result_id}`}>
        <div><dt className="sr-only">Test AUROC</dt><dd title={`Test AUROC: ${testAuroc(result)}`}>{testAuroc(result) === 'Not reported' ? '—' : testAuroc(result)}</dd></div>
        <div><dt>Predictors:</dt><dd>{result.columns_used?.filter(column => column !== (result.y_column || target)).length ?? '—'}</dd></div>
      </dl>) : <dl className="output-tile-overview"><div><dt className="sr-only">Test AUROC</dt><dd title="Test AUROC not recorded">—</dd></div><div><dt>Predictors:</dt><dd>—</dd></div></dl>}</div>
    <OutputSkillFlow config={source ? tileSkillConfiguration(snapshot, source) : undefined} loop={tile.loop}
      results={source ? tile.results.filter(result => (result.run_tag ?? snapshot.run_tag) === source) : []} runTag={source ?? ''}/>
    <footer className="output-tile-footer">Rep: {tile.replicate_number ?? tile.loop}</footer>
  </article>;
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
  const selected = usePipelines(s => s.selected);
  const context = useExecutionContext();
  const selectedOwner = items.find(item => item.id === selected);
  const totals = useTelemetryTotals(view === 'agents');
  const tag = snapshot?.run_tag ?? '';
  const comparisonResults = useMemo(() => (snapshot?.results ?? []).map(result =>
    ({...result, run_tag: result.run_tag ?? tag})), [snapshot?.results, tag]);
  const usage = (totals.data?.experiments ?? totals.data?.executions)?.find(e => e.run_tag === tag);
  const allTiles = useMemo(() => snapshot ? executionTiles(snapshot, usage) : [], [snapshot, usage]);
  const completedTiles = useMemo(() => allTiles.filter(tile => tileComplete(tile, view)), [allTiles, view]);
  const filterScope = selectedOwner?.id ?? snapshot?.experiment?.id ?? tag;
  const filters = useOutputNavigation(state => state.filters[filterScope] ?? DEFAULT_TILE_FILTERS);
  const filterIndex = useMemo(() => snapshot ? outputTileFilterIndex(snapshot, allTiles) : {metadata: new Map(), options: []}, [snapshot, allTiles]);
  const tiles = useMemo(() => filterOutputTiles(completedTiles, filterIndex.metadata, filters), [completedTiles, filterIndex, filters]);
  const [chartSelection,setChartSelection]=useState<{tag:string;observation:Observation}|null>(null);
  const [chartError,setChartError]=useState('');
  const chartTile=view==='results'&&chartSelection?.tag===tag?allTiles.find(tile=>resultForObservation(tile.results.map(result=>({...result,run_tag:result.run_tag??tag})),chartSelection.observation)):undefined;
  const selection = useOutputNavigation(s => s.selection);
  const selectedTile = selection?.tag === tag ? completedTiles.find(tile => tile.loop === selection.loop)??(chartTile?.loop===selection.loop?chartTile:undefined) : undefined;
  const detail = useOutputDetail(tag, selectedTile, view, snapshot?.scene_scope === 'outputs', snapshot?.output_revision);
  const active = detail.tile;
  const [paging, setPaging] = useState({key: '', page: 0});
  const changeTileFilters = (value: Partial<typeof filters>) => {
    setPaging({key: '', page: 0});
    useOutputNavigation.getState().setFilters(filterScope, value);
  };
  const pageKey = JSON.stringify([tag, view, filters.skill, filters.sort]);
  const pageCount = Math.max(1, Math.ceil(tiles.length / 100));
  const page = Math.min(paging.key === pageKey ? paging.page : 0, pageCount - 1);
  const visibleTiles = tiles.slice(page * 100, (page + 1) * 100);
  const waiting = !!requested && requested !== tag;
  const unavailableEmpty = !!snapshot && !completedTiles.length &&
    (snapshot.stale || snapshot.health.memstara.up === false || !!error || (view === 'agents' && !!totals.error));
  const root = useRef<HTMLDivElement>(null);
  const comparison=useRef<HTMLDivElement>(null),selectedDocument=useRef<HTMLElement>(null);
  const noticeKeys = useMemo(() => snapshot && active && view !== 'results'
    ? outputNoticeKeys(snapshot, usage, view, active.loop) : [], [snapshot, active, usage, view]);
  useOutputReadReceipt(root, noticeKeys, !!active && detail.ready && !waiting && !error && !snapshot?.stale
    && snapshot?.health.memstara.up !== false && (view !== 'agents' || !totals.error));
  const heading = useRef<HTMLHeadingElement>(null);
  const listKey = pageKey;
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
    if (view === 'results' && active && detail.ready && !waiting && !error && !snapshot?.stale) useResultNotices.getState().acknowledge(active.results.map(result => ({...result, run_tag: result.run_tag ?? tag})));
  }, [view, active, detail.ready, waiting, error, snapshot?.stale, tag]);
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
        {selectedOwner&&<p className="output-experiment-scope" aria-label="Experiment completion">{experimentProgressLabel(selectedOwner)}</p>}
        {snapshot?.experiment && !waiting && !unavailableEmpty && <p className="output-experiment-scope">{snapshot.experiment.result_combinations} scheduled replicates with saved results · {snapshot.experiment.scheduled_combinations??snapshot.experiment.result_combinations} planned · {snapshot.experiment.run_tags.length} execution {snapshot.experiment.run_tags.length===1?'session':'sessions'} · One experiment</p>}
        {snapshot && !waiting && !unavailableEmpty && <p className="output-experiment-scope">{snapshot.results.length.toLocaleString()} saved result records in this experiment{snapshot.stale || error || snapshot.health.memstara.up === false ? ' · last available snapshot' : ''}. Tile counts below include only completed outputs for the selected view.</p>}
      </div>
      <label className="output-experiment-picker">Experiment<select aria-label="Experiment outputs to inspect" value={context.owner?.id ?? ''} onChange={e => {useOutputNavigation.getState().back(); usePipelines.getState().select(e.target.value);}}>
        <option value="" disabled>{tag ? context.name : 'Choose an experiment'}</option>
        {items.map(item => <option key={item.id} value={item.id}>{item.name}{item.latest ? '' : ' · not started'}</option>)}
      </select></label>
    </header>
    <nav className="output-view-navigation" aria-label="Output views">{views.map(next => {const Icon = icons[next]; return <button type="button" key={next} aria-current={view === next ? 'page' : undefined} onClick={() => navigate(next)}><Icon size={17} aria-hidden="true"/>{outputViewNames[next]}</button>;})}</nav>
    {view === 'results' && !waiting && !unavailableEmpty && <div ref={comparison} tabIndex={-1} className="result-comparison-anchor" aria-label="Hypothesis performance comparison"><HypothesisResultsTable key={tag} runTag={tag} results={comparisonResults} plannedSkills={snapshot?.run_configuration?.combination_plan?.skills?.hypothesis?.map(skill=>skill.id)}
      skillTitles={Object.fromEntries((snapshot?.run_configuration?.combination_plan?.skills?.hypothesis??[]).filter(skill=>skill.title).map(skill=>[skill.id,skill.title!]))} onOpenResult={openChartResult}/>
      {chartError&&<p role="alert" className="output-notice">{chartError}</p>}
    </div>}
    {!active && snapshot && !waiting && <section className="output-tile-controls" aria-label="Filter and sort output tiles">
      <div className="output-tile-control-fields">
        <label>Hypothesis skill<select aria-label="Filter tiles by hypothesis skill" value={filters.skill}
          onChange={event => changeTileFilters({skill: event.target.value})}>
          <option value="">All hypothesis skills</option>
          {filterIndex.options.map(option => <option key={option.id} value={option.id}>{option.title}</option>)}
          {filters.skill && !filterIndex.options.some(option => option.id === filters.skill) && <option value={filters.skill}>{skillLabel(filters.skill)} · unavailable in this execution</option>}
        </select></label>
        <label>Sort tiles<select aria-label="Sort output tiles" value={filters.sort}
          onChange={event => changeTileFilters({sort: event.target.value as TileSort})}>
          <option value="schedule">Original order</option>
          <option value="auroc_desc">AUROC: high to low</option>
          <option value="auroc_asc">AUROC: low to high</option>
        </select></label>
        <button type="button" disabled={!filters.skill && filters.sort === 'schedule'}
          onClick={() => changeTileFilters(DEFAULT_TILE_FILTERS)}>Reset tile view</button>
      </div>
      <p>Selections apply to tiles across Results, Conclusions and Usage. Charts and downloads include all results.</p>
      {filters.sort !== 'schedule' && <p>Tiles with multiple results use the mean of recorded test AUROCs. Unavailable scores appear last.</p>}
    </section>}
    {(snapshot?.report?.run_tags?.length ?? 0) > 1 && <p className="output-notice">Includes retained outputs and usage from {snapshot?.report?.run_tags?.length} continued executions of this experiment.</p>}
    {error && (waiting || !snapshot) && <div className="output-notice" role="alert"><p>Could not load the selected execution. Saved results have not been deleted.</p><p>{error}</p><button type="button" onClick={() => void useViewer.getState().fetchOnce()}>Retry loading</button></div>}
    {!waiting && snapshot && (error || snapshot.stale || (view === 'agents' && totals.error)) && <p className="output-notice" role="status">Updates are delayed. Showing the last available records for this execution. Missing records do not indicate a completed or empty run.</p>}
    {waiting ? (!error && <p className="output-empty" role="status">Loading the selected execution…</p>) : !snapshot ? (!error && <p className="output-empty" role="status">{requested ? 'Loading execution records…' : 'Select an experiment to browse its outputs.'}</p>) : unavailableEmpty ? <div className="output-notice" role="alert"><p>Saved outputs could not be loaded. This does not mean the experiment has no results.</p><p>The saved result count is unavailable until the connection recovers. Retrying automatically.</p><button type="button" onClick={() => void useViewer.getState().fetchOnce()}>Retry loading</button></div> : active ? <>
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
      {(!detail.ready || detail.error) && <div className="output-notice" role={detail.error ? 'alert' : 'status'}>{detail.error ?? 'Loading the selected replicate’s saved output…'}{detail.error && <button type="button" onClick={detail.retry}>Retry details</button>}</div>}
      {detail.ready && <>
      {view === 'results' && <div className="output-documents">{active.results.length ? active.results.map(result => {
        const observation=chartSelection?.tag===tag?chartSelection.observation:null;
        const selected=!!(observation&&resultForObservation([{...result,run_tag:result.run_tag??tag}],observation));
        return <article key={`${result.run_tag??tag}:${result.result_id}`} ref={selected?selectedDocument:undefined} tabIndex={selected?-1:undefined} className={selected?'selected-result-card':undefined} data-chart-selected={selected?'true':undefined} aria-label={`Interpretation output for analysis ${result.result_id}`}>
          {selected&&observation&&<header className="result-chart-context"><div><strong>Selected from performance comparison</strong><button type="button" onClick={backToComparison}>Back to comparison</button></div><p>Result {observation.resultId} · {observation.model} · Fit {observation.replicate} · Seed {observation.seed??'not recorded'}</p><p>Original execution: {observation.runTag}</p></header>}
          <header className="output-document-header"><h4>Interpretation · Analysis {result.result_id}</h4></header><InterpretationOutput result={result} includeLimitations={false}/></article>;
      }) : <p className="output-empty">No Interpretation output has been saved for this replicate yet.</p>}</div>}
      {view === 'report' && <div className="output-documents">{active.explanations.length ? active.explanations.map((output, index) => <article key={`${output.result_id}:${index}`} aria-label={`Explanation output ${index + 1}`}><header className="output-document-header"><h4>Explanation output {index + 1}<span>{output.status}</span></h4><button type="button" disabled={!output.text} onClick={() => downloadOutput(output.text, `${tag}_pipeline-${active.pipeline_number}_replicate-${active.replicate_number}_explanation-${index + 1}.md`)}><Download size={15} aria-hidden="true"/>Download Markdown</button></header>{output.text ? <ReportBody verbatim text={output.text}/> : <p>No Explanation text has been saved for this output yet.</p>}</article>) : <p className="output-empty">No Explanation output has been saved for this replicate yet.</p>}</div>}
      </>}
      {view === 'agents' && <TelemetryPanel key={`${tag}:${active.loop}:${active.record_run_tag}`} lockedLoop={active.loop} recordRunTag={active.record_run_tag}/>}
    </> : <>
      <div className="output-list-heading"><div><h3>{outputViewNames[view]}</h3><p>Completed {view === 'agents' ? 'replicates' : 'outputs'} only. Choose a tile to view details.</p></div><span>{pipelineCount} {pipelineCount === 1 ? 'pipeline' : 'pipelines'} · {tiles.length} {tiles.length === 1 ? 'replicate' : 'replicates'}{filters.skill && ` of ${completedTiles.length}`}</span></div>
      {pageCount > 1 && <nav className="output-pagination" aria-label="Output pages">
        <button type="button" disabled={page === 0} onClick={() => setPaging({key: pageKey, page: page - 1})}>Previous page</button>
        <label>Page <select aria-label="Output page" value={page} onChange={e => setPaging({key: pageKey, page: Number(e.target.value)})}>{Array.from({length: pageCount}, (_, i) => <option key={i} value={i}>{i + 1}</option>)}</select> of {pageCount}</label>
        <span>Showing {page * 100 + 1}–{Math.min((page + 1) * 100, tiles.length)} of {tiles.length}. Charts and downloads include all results.</span>
        <button type="button" disabled={page + 1 === pageCount} onClick={() => setPaging({key: pageKey, page: page + 1})}>Next page</button>
      </nav>}
      <div className="execution-output-grid">{visibleTiles.map(tile => <Tile key={`${tag}:${tile.loop}`} tile={tile} view={view} target={snapshot.run_configuration?.y_column}
        snapshot={snapshot} onOpen={() => open(tile)}/>)}</div>
      {!tiles.length && <p className="output-empty" role="status">{filters.skill
        ? 'No completed tiles match this hypothesis skill. Choose another skill or reset the tile view.'
        : view === 'agents' ? 'No completed replicates yet. Usage tiles appear when each replicate finishes.' : `No completed ${outputViewNames[view].toLowerCase()} yet. Tiles appear when the outputs are complete.`}</p>}
    </>}
  </div>;
}
