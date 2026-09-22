import { useEffect, useState } from 'react';
import { Activity, Sparkles, Layers3, AlertCircle, Clock3, DollarSign, ArrowUpRight } from 'lucide-react';
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
  const active = pipelines.filter(p => p.running && p.running.execution_state !== 'paused');
  const waiting = active.filter(p => p.running?.waiting_for_questions).length;
  const issues = pipelines.filter(p => (p.progress.counts?.failed ?? 0) > 0 || (p.latest?.exit_code != null && p.latest.exit_code !== 0));
  const age = live.updatedAt ? Math.max(0, Math.floor((now - Date.parse(live.updatedAt)) / 1000)) : null;
  const currentTags = [...tags].sort().join(',');
  const [cost, setCost] = useState<{usd:number; status:string; run_tags:string[]; pending_runs:number; missing_costs:number} | null>(null);
  const [costError, setCostError] = useState(false);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController | null = null;
    setCost(null); setCostError(false);
    const poll = async () => {
      if (stopped) return;
      if (!currentTags) { setCost({usd:0,status:'complete',run_tags:[],pending_runs:0,missing_costs:0}); return; }
      if (!document.hidden) {
        request = new AbortController();
        const timeout = setTimeout(() => request?.abort(), 5500);
        try {
          const response = await fetch(`/api/workspace-cost?run_tags=${encodeURIComponent(currentTags)}`, {signal:request.signal});
          if (!response.ok) throw new Error('Cost lookup failed');
          const next = await response.json();
          if (!stopped) { setCost(next); setCostError(false); }
        } catch { if (!stopped) setCostError(true); }
        finally { clearTimeout(timeout); }
      }
      if (!stopped) timer = setTimeout(poll, 10000);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); request?.abort(); };
  }, [currentTags]);
  const scopedCost = cost?.run_tags.join(',') === currentTags ? cost : null;
  const costValue = scopedCost && Number.isFinite(scopedCost.usd) ? `$${scopedCost.usd.toFixed(4)}` : '—';
  const costDescription = costError ? 'Update delayed · last available estimate' : !scopedCost ? 'Awaiting cost records'
    : !tags.size ? 'No executions in this workspace' : scopedCost.status === 'partial' ? 'Partial · active calls or pricing missing' : 'Latest executions · estimated, not billed';
  const stale = !!controlError || !!live.error || (tags.size > 0 && (live.tags !== currentTags || age === null || age > 15));
  const starts = active.map(p => Date.parse(p.running!.started)).filter(Number.isFinite);
  const seconds = starts.length ? Math.max(0, Math.floor((now - Math.min(...starts)) / 1000)) : null;
  const elapsed = seconds === null ? '—' : seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const navigate = (view: 'scene' | 'clinician' | 'discovery' | 'chain' | 'agents') => useViewer.getState().setView(view);
  const ready = loaded && live.tags === currentTags && (!tags.size || live.updatedAt !== null);
  return <section className="exploration-summary" aria-label="Live exploration summary">
    <div className="exploration-summary-heading">
      <div><h2>Exploration overview</h2><p>Current pipelines and their latest executions.</p></div>
      <span data-help="Connection freshness" tabIndex={0} className={`summary-connection ${stale ? 'summary-warning' : ''}`} title={controlError || live.error || 'Latest output refresh; inactive browser tabs pause polling.'}>
        <i aria-hidden="true" />{!loaded ? 'Connecting' : stale ? 'Updates delayed' : tags.size ? 'Live updates' : 'Ready to start'}
        {age !== null && tags.size > 0 && ` · ${age}s since sync`}
      </span>
    </div>
    <div className="exploration-summary-grid">
      <button className="summary-primary" onClick={() => navigate('scene')}>
        <span className="summary-card-label"><Activity size={16}/><span>Active pipelines</span><ArrowUpRight size={13}/></span>
        <strong>{!loaded || stale ? '—' : active.length}<b> / {loaded ? pipelines.length : '—'}</b></strong>
        <span className="summary-card-description">{stale ? 'Status unconfirmed' : waiting > 0 ? `${waiting} waiting for knowledge` : 'Running / configured pipelines'}</span>
      </button>
      <button className={unread > 0 ? 'summary-fresh' : ''} onClick={() => { setSeen(new Set([...seen, ...fresh])); navigate('clinician'); }}>
        <span className="summary-card-label"><Sparkles size={16}/><span>New results to review</span><ArrowUpRight size={13}/></span>
        <strong>{ready ? unread : '—'}</strong>
        <span className="summary-card-description">New arrivals this visit; not validated discoveries</span>
      </button>
      <button onClick={() => navigate('discovery')}>
        <span className="summary-card-label"><Layers3 size={16}/><span>Results loaded</span><ArrowUpRight size={13}/></span>
        <strong>{ready ? results.length : '—'}</strong>
        <span className="summary-card-description">{ready ? `${questions.length} questions loaded · not lifetime totals` : 'Waiting for execution records'}</span>
      </button>
      <button className={issues.length || stale ? 'summary-warning' : ''} onClick={() => { if (issues[0]) { usePipelines.getState().focus(issues[0].id); navigate('scene'); } else navigate(stale ? 'agents' : 'chain'); }}>
        <span className="summary-card-label"><AlertCircle size={16}/><span>Pipelines to inspect</span><ArrowUpRight size={13}/></span>
        <strong>{!loaded || stale ? '—' : issues.length}</strong>
        <span className="summary-card-description">{stale ? 'Check connection before interpreting status' : 'Recorded failures or unsuccessful exits; check retries'}</span>
      </button>
      <button onClick={() => navigate('agents')}>
        <span className="summary-card-label"><Clock3 size={16}/><span>Active execution age</span><ArrowUpRight size={13}/></span>
        <strong>{stale ? '—' : elapsed}</strong>
        <span className="summary-card-description">{stale ? 'Active status unconfirmed' : !active.length ? 'No active execution' : seconds === null ? 'Start time not recorded' : 'Since the earliest active start; includes pauses'}</span>
      </button>
      <button className={`summary-cost ${costError ? 'summary-warning' : ''}`} onClick={() => navigate('agents')}>
        <span className="summary-card-label"><DollarSign size={16}/><span>Estimated LLM cost</span><ArrowUpRight size={13}/></span>
        <strong>{costValue}</strong>
        <span className="summary-card-description">{costDescription}</span>
        <span className="cost-refresh-note">Updates every 10 seconds</span>
      </button>
    </div>
    <p className="summary-scope-note">{stale ? 'Updates are delayed; retained results may be out of date. ' : ''}Results reflect records loaded in this browser (up to 600 results and 400 questions). Cost covers the latest execution of each current pipeline, not account-wide spending. Select a card to inspect its details.</p>
  </section>;
}
