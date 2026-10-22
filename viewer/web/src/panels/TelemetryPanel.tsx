import { useEffect, useState } from 'react';
import { Activity, AlertCircle, ChevronLeft, ChevronRight, Layers3, LayoutDashboard, RefreshCw } from 'lucide-react';
import MotoroRecords from '../components/MotoroRecords';
import TelemetryTotals, { TelemetryState, useTelemetryTotals } from '../components/TelemetryTotals';
import ExperimentRegistry from '../components/ExperimentRegistry';
import ExecutionLogs from '../components/ExecutionLogs';
import { controlResponse } from '../lib/controlResponse';
import { usePipelines } from '../store/pipelines';
import { useViewer } from '../store/viewer';
import { SnapshotScope } from '../lib/SnapshotScope';
import { loopLabel } from '../lib/loopLabel';
import type { Snapshot } from '../types';
import AgentsTab from '../tabs/AgentsTab';
import AccessTab from '../tabs/AccessTab';
import TaskTab from '../tabs/TaskTab';
import FeedPanel from './FeedPanel';
import ResultsPanel from './ResultsPanel';
import './telemetry.css';

type Tab = 'Experiments' | 'Totals' | 'Agents' | 'Activity' | 'Logs' | 'Access' | 'Tasks' | 'Results';
type Loop = { number: number; status: string; tasks: number; results: number };
type LoopSnapshot = Snapshot & {
  telemetry: {loop: number | null; loops: Loop[]; legacy_attribution: boolean; unassigned_calls: number};
  loop_log: {lines: string[]; note: string; truncated: boolean};
};
const primaryTabs = [
  {id: 'Totals', label: 'Overview', icon: LayoutDashboard},
  {id: 'Agents', label: 'Agents', icon: Layers3},
  {id: 'Activity', label: 'Activity', icon: Activity},
] as const;
const recordTabs = ['Logs', 'Access', 'Tasks', 'Results', 'Experiments'] as const;
const labels: Record<Tab, string> = {
  Totals: 'Overview', Agents: 'Agents', Activity: 'Activity', Logs: 'Logs',
  Access: 'Tools & resources', Tasks: 'Tasks', Results: 'Results', Experiments: 'Experiment registry',
};
const descriptions: Record<Tab, string> = {
  Experiments: 'Compare registered experiments and inspect their saved evidence.',
  Totals: 'Time and usage for the selected execution.',
  Agents: 'Agent executions, reasoning steps and recorded usage.',
  Activity: 'Recorded tool actions and agent text, in local time.',
  Logs: 'Agent outputs and original console messages.',
  Access: 'Recorded tool calls and resources used by each agent.',
  Tasks: 'Inspect task evidence and handoffs between stages.',
  Results: 'Review recorded findings and their supporting evidence.',
};

export default function TelemetryPanel() {
  const totals = useTelemetryTotals();
  const runTag = useViewer(s => s.runTag);
  const pipelines = usePipelines(s => s.items);
  const selectedPipelineId = usePipelines(s => s.selected);
  const pipelineError = usePipelines(s => s.error?.includes('Pipeline workspace is unavailable') ? s.error : null);
  const [selection, setSelection] = useState<{tag: string | null; loop: number | null}>({tag: null, loop: null});
  const loop = selection.tag === runTag ? selection.loop : null;
  const [tab, setTab] = useState<Tab>('Totals');
  const [taskSelection, setTaskSelection] = useState<{scope: string; id: number | null}>({scope: '', id: null});
  const taskScope = `${runTag ?? ''}:${loop ?? 'all'}`;
  const chosenTask = taskSelection.scope === taskScope ? taskSelection.id : null;
  const [record, setRecord] = useState<{key: string; data: LoopSnapshot} | null>(null);
  const [failure, setFailure] = useState<{key: string; text: string} | null>(null);
  const [catalog, setCatalog] = useState<{tag: string; loops: Loop[]} | null>(null);
  const [revision, setRevision] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const key = `${runTag ?? ''}:${loop ?? 'all'}:${tab}`;
  const data = record?.key === key ? record.data : null;
  const error = failure?.key === key ? failure.text : '';
  const execution = totals.data?.executions.find(e => e.run_tag === runTag);
  const owner = pipelines.find(p => p.latest?.run_tag === runTag || p.running?.run_tag === runTag);
  const pipeline = owner ?? (!runTag ? pipelines.find(p => p.id === selectedPipelineId) : undefined);
  const choices = execution?.loops.map(l => ({number: l.number, status: l.status ?? 'recorded'}))
    ?? (catalog?.tag === runTag ? catalog.loops : []);
  const globalScope = tab === 'Experiments';
  const selectLoop = (value: number | null) => {setSelection({tag: runTag, loop: value});};
  const refresh = () => {totals.refresh(); setRevision(n => n + 1); void usePipelines.getState().poll();};

  useEffect(() => {
    if (!runTag || tab === 'Experiments' || tab === 'Totals') return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController | null = null;
    const poll = async () => {
      request = new AbortController();
      setRefreshing(true);
      let retryDelay = 4000;
      const deadline = setTimeout(() => request?.abort(), 10000);
      try {
        const response = await fetch(`/api/telemetry?run_tag=${encodeURIComponent(runTag)}${loop === null ? '' : `&loop=${loop}`}&view=${encodeURIComponent(tab)}`, {signal: request.signal});
        const body = await controlResponse(response);
        if (response.status === 202 && body.detail?.status === 'loading' && body.detail.run_tag === runTag && body.detail.loop === loop) {
          retryDelay = 1000;
          if (!disposed) setFailure(null);
          return;
        }
        if (!response.ok) throw Error(body.detail || 'Telemetry is temporarily unavailable.');
        if (body.run_tag !== runTag || body.telemetry?.loop !== loop) throw Error('The response did not match the selected scope.');
        if (!disposed) {setRecord({key, data: body}); setCatalog({tag: runTag, loops: body.telemetry.loops}); setFailure(null);}
      } catch (e) {
        if (!disposed) setFailure({key, text: e instanceof Error ? e.name === 'AbortError' ? 'Telemetry timed out. Retrying automatically.' : e.message : 'Telemetry is temporarily unavailable.'});
      } finally {
        clearTimeout(deadline);
        if (!disposed) {setRefreshing(false); timer = setTimeout(poll, retryDelay);}
      }
    };
    void poll();
    return () => {disposed = true; clearTimeout(timer); request?.abort(); setRefreshing(false);};
  }, [runTag, loop, key, tab, revision]);

  const scope = globalScope ? 'All saved executions' : loop === null ? 'All loops' : `Loop ${loop}`;
  const index = choices.findIndex(c => c.number === loop);
  const taskId = data?.board.tasks.some(t => t.task_id === chosenTask) ? chosenTask : null;
  const delayed = !!(totals.error || error || data?.stale || pipelineError);
  const updated = totals.data?.updated_at ? new Date(totals.data.updated_at) : null;
  const updatedLabel = updated && Number.isFinite(updated.getTime()) ? updated.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : null;

  return <SnapshotScope.Provider value={data ?? undefined}>
    <div className="telemetry-workspace">
      <div className="tm-toolbar">
        <div className="tm-toolbar-copy"><strong>Execution monitoring</strong><span>Time, usage and recorded activity</span></div>
        <div className="tm-refresh-group">
          <span className="tm-update-status" data-delayed={delayed}><span aria-hidden="true"/>{delayed ? 'Updates delayed' : updatedLabel ? `Updated ${updatedLabel}` : 'Connecting'}</span>
          <button type="button" className="tm-button tm-refresh" disabled={totals.refreshing || refreshing} onClick={refresh} aria-label="Refresh telemetry" title="Refresh recorded measurements and the selected view"><RefreshCw size={15} aria-hidden="true"/><span>Refresh</span></button>
        </div>
      </div>
      <section className="tm-scope" aria-label="Pipeline and loop selection">
        <label className="tm-field tm-pipeline-field"><span>Pipeline</span>
          <select aria-label="Pipeline to inspect" title={pipeline?.name} value={pipeline?.id ?? ''} disabled={globalScope} onChange={e => usePipelines.getState().select(e.target.value)}>
            <option value="" disabled>{runTag ? 'Saved execution' : 'Choose a pipeline'}</option>
            {pipelines.map(p => <option key={p.id} value={p.id}>{p.name}{p.latest || p.running ? '' : ' · not started'}</option>)}
          </select>
        </label>
        <div className="tm-loop-field">
          <label className="tm-field"><span>Loop</span>
            <select aria-label="Loop to inspect" disabled={globalScope || !runTag || !choices.length} value={loop ?? 'all'} onChange={e => selectLoop(e.target.value === 'all' ? null : Number(e.target.value))}>
              <option value="all">All loops</option>{choices.map(c => <option key={c.number} value={c.number}>Loop {c.number} · {c.status.replaceAll('_', ' ')}</option>)}
            </select>
          </label>
          <div className="tm-stepper" role="group" aria-label="Browse loops">
            <button type="button" aria-label="Previous loop" title="Previous loop" disabled={globalScope || index <= 0} onClick={() => selectLoop(choices[index - 1].number)}><ChevronLeft size={17}/></button>
            <button type="button" aria-label="Next loop" title="Next loop" disabled={globalScope || !choices.length || index >= choices.length - 1} onClick={() => selectLoop(choices[index + 1].number)}><ChevronRight size={17}/></button>
          </div>
        </div>
        <div className="tm-scope-caption">{globalScope && <span>The registry covers all saved executions.</span>}
          {runTag && !globalScope && <details className="tm-execution-id"><summary>Execution ID</summary><code>{runTag}</code></details>}
        </div>
      </section>
      {pipelineError && <div className="tm-notice" role="status"><AlertCircle size={16}/><p>Pipeline list updates are delayed. Retained selections remain available.</p></div>}
      <nav aria-label="Telemetry tabs" className="tm-navigation">
        <div className="tm-primary-tabs">{primaryTabs.map(({id, label, icon: Icon}) => <button type="button" key={id} aria-pressed={tab === id} aria-controls="telemetry-content" onClick={() => setTab(id)}><Icon size={16} aria-hidden="true"/>{label}</button>)}</div>
        <label className="tm-detail-picker"><span className="sr-only">Detailed records</span>
          <select aria-label="Detailed records" data-active={recordTabs.some(t => t === tab)} value={recordTabs.some(t => t === tab) ? tab : ''} onChange={e => {if (e.target.value) setTab(e.target.value as Tab);}}>
            <option value="" disabled>More records</option>{recordTabs.map(name => <option key={name} value={name}>{labels[name]}</option>)}
          </select>
        </label>
      </nav>
      {tab !== 'Totals' && <div className="tm-section-heading"><div><h3>{labels[tab]}</h3><p>{descriptions[tab]}</p></div><span className="tm-scope-badge">{scope}</span></div>}
      {error && <div role="alert" className="tm-notice"><AlertCircle size={16}/><p>{error}{data ? ' Showing the last available records for this same selection.' : ''}</p><button className="tm-button" onClick={refresh}>Retry</button></div>}
      {data?.stale && <div role="status" className="tm-notice"><AlertCircle size={16}/><p>{data.health.core.up && data.health.memstara.up ? 'Refreshing this selection. Previously loaded records remain visible.' : 'Updates are delayed. This does not confirm an empty or completed loop.'}</p></div>}
      {(data?.telemetry.legacy_attribution || !!data?.telemetry.unassigned_calls) && <details className="tm-attribution"><summary>Record attribution</summary>
        {data?.telemetry.legacy_attribution && <p>Legacy agent calls are grouped by recorded loop start times. New executions record the loop directly.</p>}
        {!!data?.telemetry.unassigned_calls && <p>{data.telemetry.unassigned_calls} execution-wide or unassigned calls appear only in All loops.</p>}
      </details>}
      <div id="telemetry-content" key={globalScope ? 'experiments' : key} tabIndex={0} role="region" aria-label="Telemetry details" className="telemetry-tab-body">
        {tab === 'Experiments' ? <div className="tm-records"><ExperimentRegistry refreshRevision={revision}/></div>
          : tab === 'Totals' ? <TelemetryTotals data={totals.data} error={totals.error} runTag={runTag} loop={loop} onRetry={totals.refresh} refreshRevision={revision}/>
          : !runTag ? <TelemetryState title="Choose an execution">Select a pipeline with saved activity to inspect its records.</TelemetryState>
          : !data ? <TelemetryState loading={!error} title={error ? 'Records are temporarily unavailable' : `Loading ${scope.toLowerCase()}`}>
            {error ? 'Retry above, or wait for the next automatic update.' : 'Preparing the saved history. Larger executions may take a little longer.'}
          </TelemetryState> : <div className="tm-records">
            {tab === 'Agents' && <><AgentsTab/><MotoroRecords key={`${runTag}:${loop}`} tag={runTag} loop={loop}/></>}
            {tab === 'Activity' && <div className="tm-embedded-activity"><FeedPanel embedded/></div>}{tab === 'Access' && <AccessTab/>}{tab === 'Results' && <ResultsPanel telemetry/>}
            {tab === 'Tasks' && <><label className="tm-field tm-task-picker"><span>Task</span><select aria-label="Task in selected loop" value={taskId ?? ''} onChange={e => setTaskSelection({scope: taskScope, id: e.target.value ? Number(e.target.value) : null})}>
              <option value="">Select a task</option>{data.board.tasks.map(t => <option key={t.task_id} value={t.task_id}>#{t.task_id} · {loopLabel(t, data.run_configuration?.trials)} · {t.task_type} · {t.status}</option>)}
            </select></label><TaskTab taskId={taskId}/></>}
            {tab === 'Logs' && <ExecutionLogs runTag={runTag} loop={loop} lines={data.loop_log.lines} note={data.loop_log.note}/>}
          </div>}
      </div>
    </div>
  </SnapshotScope.Provider>;
}
