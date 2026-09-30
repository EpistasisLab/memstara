import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { MessageSquareText, ChevronLeft, ChevronRight, ArrowDown } from 'lucide-react';
import { useLiveOutputs } from '../store/liveOutputs';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';
import { clinicalEventText, clinicalPipelineStatus, clinicalRoles, scopedClinicalEvents } from '../lib/clinicalLog';
import ActivityDetails, { type ActivityScope } from './ActivityDetails';
import './clinical-log.css';

export default function ClinicalLogPanel({pipelines}: {pipelines: PipelineDefinition[]}) {
  const live = useLiveOutputs();
  const pipelineError = usePipelines(s => s.error);
  const [narrow, setNarrow] = useState(false);
  const [preference, setPreference] = useState<boolean | null>(null);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const floor = panel.current?.closest('.floor-observatory');
    if (!floor) return;
    const observer = new ResizeObserver(entries => setNarrow(entries[0].contentRect.width <= 900));
    observer.observe(floor); return () => observer.disconnect();
  }, []);
  const collapsed = preference ?? narrow;
  const scope = pipelines.map(p => `${p.id}:${(p.running ?? p.latest)?.run_tag ?? ''}`).join('|');
  return <aside ref={panel} className={`clinical-log ${collapsed ? 'is-collapsed' : ''}`} aria-label="Clinical activity log">
    <header className="clinical-log-heading"><MessageSquareText size={17}/><h3>Live log</h3><button aria-label={collapsed ? 'Expand live log' : 'Collapse live log'} aria-expanded={!collapsed} onClick={() => setPreference(!collapsed)}>{collapsed ? <ChevronLeft size={17}/> : <ChevronRight size={17}/>}</button></header>
    {!collapsed && <ClinicalLogBody key={scope} pipelines={pipelines} live={live} pipelineError={pipelineError}/>}
  </aside>;
}

function ClinicalLogBody({pipelines, live, pipelineError}: {
  pipelines: PipelineDefinition[]; live: ReturnType<typeof useLiveOutputs.getState>; pipelineError: string | null;
}) {
  const [now, setNow] = useState(Date.now);
  const [following, setFollowing] = useState(true);
  const [detail, setDetail] = useState<ActivityScope | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 3000); return () => clearInterval(timer); }, []);
  const events = scopedClinicalEvents(live.events, pipelines);
  const last = events.at(-1);
  const lastKey = last ? `${last.id}:${last.revision}` : '';
  useLayoutEffect(() => {
    if (following && !detail && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [lastKey, following, detail]);
  const hasExecution = pipelines.some(p => p.running || p.latest);
  const delayed = hasExecution && (!live.updatedAt || now - Date.parse(live.updatedAt) > 15000);
  const interrupted = !!(live.error || pipelineError);
  const connection = interrupted ? 'Updates interrupted' : delayed ? 'Waiting for fresh updates' : pipelines.some(p => p.running) ? 'Live · checks every 0.5 seconds' : hasExecution ? 'Saved activity · standing by' : 'Waiting for an execution';
  return <>
    <div className="clinical-log-context"><p>Recorded activity in plain language.</p><span role="status" className={interrupted || delayed ? 'clinical-log-delayed' : ''}>{connection}</span>
      {(interrupted || delayed) && hasExecution && <p>Previously received records remain visible. This does not confirm that execution has stopped.</p>}
    </div>
    {detail && <div className="clinical-log-detail-view"><button className="clinical-log-back" onClick={() => setDetail(null)}>Back to live updates</button><ActivityDetails key={`${detail.run_tag}:${detail.iteration}:${detail.stage}`} event={detail}/></div>}
    <div hidden={!!detail} className="clinical-log-scroll" ref={scroll} tabIndex={0} aria-label="Recorded clinical activity" onScroll={e => {
      const el = e.currentTarget; setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 30);
    }}>
      <section className="clinical-log-current" aria-label="Current pipeline activity">
        {!pipelines.length && <p>Select or create a pipeline to see its activity.</p>}
        {pipelines.map(p => <article key={p.id}><strong>{p.name}</strong><small>{p.progress.iteration != null ? `Loop ${p.progress.iteration}` : 'Loop not recorded'} · {clinicalRoles[p.progress.stage ?? ''] ?? 'Execution'}</small><p>{pipelineError ? 'Current execution status is unavailable. The last recorded state is retained.' : clinicalPipelineStatus(p)}</p>{(p.running ?? p.latest)?.run_tag && <button className="clinical-log-details-button" onClick={() => {setFollowing(false);setDetail({run_tag:(p.running ?? p.latest)!.run_tag,iteration:null,stage:'',pipeline_name:p.name,detail:''});}}>Browse activity</button>}{p.progress.updated_at && <time dateTime={p.progress.updated_at}>Last recorded {new Date(p.progress.updated_at).toLocaleTimeString()}</time>}</article>)}
      </section>
      {!events.length && <p className="clinical-log-empty">No saved output updates for this execution yet. New records will appear here automatically.</p>}
      <ol className="clinical-log-events" aria-label="Saved output updates">{events.map(event => {
        const owner = pipelines.find(p => (p.running ?? p.latest)?.run_tag === event.run_tag);
        return <li key={`${event.id}:${event.revision}`}><small>{owner?.name ?? event.pipeline_name} · {event.iteration != null ? `Loop ${event.iteration}` : 'Loop not recorded'} · {clinicalRoles[event.stage] ?? 'Analysis'}</small><p>{clinicalEventText(event)}</p>
          <time dateTime={new Date(event.receivedAt).toISOString()}>Received {new Date(event.receivedAt).toLocaleTimeString()}</time>
          <button className="clinical-log-details-button" onClick={() => {setFollowing(false);setDetail(event);}}>View details</button>
          {!!event.detail && <details><summary>Read recorded excerpt</summary><p>{event.detail}</p><small>Saved text excerpt; may be shortened. Agent-written content requires review.</small></details>}
        </li>;
      })}</ol>
    </div>
    {!following && !detail && <button className="clinical-log-latest" onClick={() => setFollowing(true)}><ArrowDown size={14}/> Follow latest updates</button>}
    <footer>Received order · Recent updates only. Saved outputs do not establish clinical validity.</footer>
  </>;
}
