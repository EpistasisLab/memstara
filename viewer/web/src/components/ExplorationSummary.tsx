import { useEffect, useState } from 'react';
import { Activity, Sparkles, Layers3, AlertCircle, Clock3 } from 'lucide-react';
import { usePipelines } from '../store/pipelines';
import { useLiveOutputs } from '../store/liveOutputs';
import { useViewer } from '../store/viewer';
import './exploration-summary.css';

/** Workspace scope only: retained records are never presented as lifetime totals. */
export default function ExplorationSummary() {
  const pipelines = usePipelines(s => s.items);
  const loaded = usePipelines(s => s.loaded);
  const controlError = usePipelines(s => s.error);
  const live = useLiveOutputs();
  const [now, setNow] = useState(() => Date.now());
  const [seen, setSeen] = useState<Set<number>>(() => new Set());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const tags = new Set(pipelines.flatMap(p => p.latest ? [p.latest.run_tag] : []));
  const results = live.results.filter(r => r.run_tag && tags.has(r.run_tag));
  const questions = live.questions.filter(q => tags.has(q.origin_run));
  const fresh = new Set(live.events.filter(e => tags.has(e.run_tag) && e.stage === 'result' && e.fresh && e.result_id !== null).map(e => e.result_id!));
  const unread = [...fresh].filter(id => !seen.has(id)).length;
  const active = pipelines.filter(p => p.running);
  const waiting = active.filter(p => p.running?.waiting_for_questions).length;
  const issues = pipelines.filter(p => (p.progress.counts?.failed ?? 0) > 0 || (p.latest?.exit_code != null && p.latest.exit_code !== 0));
  const age = live.updatedAt ? Math.max(0, Math.floor((now - Date.parse(live.updatedAt)) / 1000)) : null;
  const currentTags = [...tags].sort().join(',');
  const stale = !!controlError || !!live.error || (tags.size > 0 && (live.tags !== currentTags || age === null || age > 15));
  const starts = active.map(p => Date.parse(p.running!.started)).filter(Number.isFinite);
  const seconds = starts.length ? Math.max(0, Math.floor((now - Math.min(...starts)) / 1000)) : null;
  const elapsed = seconds === null ? '—' : seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const navigate = (view: 'scene' | 'clinician' | 'discovery' | 'chain' | 'agents') => useViewer.getState().setView(view);
  const ready = loaded && live.tags === currentTags && (!tags.size || live.updatedAt !== null);
  return <section className="exploration-summary" aria-label="Live exploration summary">
    <div className="exploration-summary-heading"><span>Exploration</span><span className={`summary-connection ${stale ? 'summary-warning' : ''}`} title={controlError || live.error || 'Latest output refresh; inactive browser tabs pause polling.'}>
      <i aria-hidden="true" />{!loaded ? 'Connecting' : stale ? 'Updates delayed' : tags.size ? 'Live' : 'Ready'}
      {age !== null && tags.size > 0 && ` · synced ${age}s ago`}
    </span></div>
    <div className="exploration-summary-grid">
      <button onClick={() => navigate('scene')} title="Open Floor plan to inspect each independent pipeline."><Activity/><span><small>Active pipelines</small><strong>{!loaded || stale ? '—' : active.length}<b> / {pipelines.length}</b></strong><em>{stale ? 'Status unconfirmed' : waiting > 0 ? `${waiting} awaiting knowledge` : active.length ? 'Exploring independently' : 'Ready when you are'}</em></span></button>
      <button onClick={() => { setSeen(new Set([...seen, ...fresh])); navigate('clinician'); }} title="New completed results received since this page opened, excluding initial history. These are not automatically recommended hypotheses."><Sparkles/><span><small>New findings</small><strong>{ready ? unread : '—'}</strong><em>Results to review</em></span></button>
      <button onClick={() => navigate('discovery')} title="Received records for current pipeline runs, retained in this browser: up to 400 questions and 600 results. Not lifetime totals; reused questions may originate in earlier runs."><Layers3/><span><small>Recent results</small><strong>{ready ? results.length : '—'}</strong><em>{ready ? `${questions.length} questions received` : 'Awaiting records'}</em></span></button>
      <button className={issues.length || stale ? 'summary-warning' : ''} onClick={() => { if (issues[0]) { usePipelines.getState().focus(issues[0].id); navigate('scene'); } else navigate(stale ? 'agents' : 'chain'); }} title="Recorded failed tasks or nonzero run exits. Open the affected pipeline to inspect; a failed task may subsequently have been retried."><AlertCircle/><span><small>Attention</small><strong>{!loaded || stale ? '—' : issues.length}</strong><em>{issues.length ? 'Pipelines to inspect' : stale ? 'Check connection' : 'No recorded failures'}</em></span></button>
      <button onClick={() => navigate('agents')} title="Elapsed time since the earliest currently running pipeline started; not a sum of parallel runtimes. Workspace-wide cost is not provided by the current telemetry contract."><Clock3/><span><small>Elapsed time</small><strong>{elapsed}</strong><em>Total cost · unavailable</em></span></button>
    </div>
  </section>;
}
