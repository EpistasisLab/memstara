import {createPortal} from 'react-dom';
import {floorActivityRows, floorExecutionState, type FloorActivity} from '../lib/floorActivity';
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { MessageSquareText, ArrowDown } from 'lucide-react';
import { useLiveOutputs } from '../store/liveOutputs';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';
import { clinicalEventText, clinicalPipelineStatus, clinicalRoles, scopedClinicalEvents } from '../lib/clinicalLog';
import ActivityDetails, { type ActivityScope } from './ActivityDetails';
import './clinical-log.css';

export default function ClinicalLogPanel({pipelines,floorActivity,toggleHost}: {toggleHost:HTMLElement|null;pipelines: PipelineDefinition[];floorActivity?:FloorActivity|null}) {
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
    {toggleHost&&createPortal(<button className="floor-panel-toggle" aria-label={collapsed?'Expand live log':'Collapse live log'} aria-expanded={!collapsed} aria-pressed={!collapsed} onClick={()=>setPreference(!collapsed)}><MessageSquareText size={16} aria-hidden="true"/><span>Live log</span><span className="floor-panel-indicator" aria-hidden="true"/></button>,toggleHost)}
    <header className="clinical-log-heading"><MessageSquareText size={17}/><h3>Live log</h3></header>
    {!collapsed && <ClinicalLogBody key={`${scope}:${floorActivity?.loop??''}:${floorActivity?.mode??''}`} pipelines={pipelines} live={live} pipelineError={pipelineError} floorActivity={floorActivity}/>}
  </aside>;
}

function ClinicalLogBody({pipelines, live, pipelineError, floorActivity}: {
  pipelines: PipelineDefinition[]; live: ReturnType<typeof useLiveOutputs.getState>; pipelineError: string | null; floorActivity?:FloorActivity|null;
}) {
  const [now, setNow] = useState(Date.now);
  const [following, setFollowing] = useState(true);
  const [tab, setTab] = useState<'agents'|'outputs'>('agents');
  const tabId = useId();
  const [detail, setDetail] = useState<ActivityScope | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 3000); return () => clearInterval(timer); }, []);
  const events = scopedClinicalEvents(live.events, pipelines).filter(e => !floorActivity || (floorActivity.mode !== 'preview' && e.run_tag === floorActivity.runTag && e.iteration === floorActivity.loop));
  const owner = pipelines.find(p=>p.id===floorActivity?.pipelineId);
  const last = events.at(-1);
  const lastKey = last ? `${last.id}:${last.revision}` : '';
  useLayoutEffect(() => {if (tab === 'agents' && scroll.current) scroll.current.scrollTop = 0;}, [tab]);
  useLayoutEffect(() => {
    if (tab === 'outputs' && following && !detail && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [lastKey, following, detail, tab]);
  const hasExecution = pipelines.some(p => p.running || p.latest);
  const delayed = hasExecution && (!live.updatedAt || now - Date.parse(live.updatedAt) > 15000);
  const interrupted = !!(live.error || pipelineError || floorActivity?.error);
  const connection = interrupted ? 'Updates interrupted' : delayed ? 'Waiting for fresh updates' : pipelines.some(p => floorExecutionState(p.running).live) ? 'Live · checks every 0.5 seconds' : pipelines.some(p=>floorExecutionState(p.running).stopping) ? 'Pausing · waiting for existing calls' : pipelines.some(p=>floorExecutionState(p.running).paused) ? 'Paused · saved activity' : hasExecution ? 'Saved activity · standing by' : 'Waiting for an execution';
  return <>
    <div className="clinical-log-context"><span role="status" className={interrupted || delayed ? 'clinical-log-delayed' : ''}>{connection}</span>
      {(interrupted || delayed) && hasExecution && <p>Previously received records remain visible. This does not confirm that execution has stopped.</p>}
    </div>
    {!detail && <div className="clinical-log-tabs" role="tablist" aria-label="Live log sections" onKeyDown={e=>{
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
      e.preventDefault();
      const next=e.key==='Home'?'agents':e.key==='End'?'outputs':tab==='agents'?'outputs':'agents';
      setTab(next);document.getElementById(`${tabId}-${next}-tab`)?.focus();
    }}>
      <button id={`${tabId}-agents-tab`} aria-controls={`${tabId}-agents`} tabIndex={tab==='agents'?0:-1} role="tab" aria-selected={tab==='agents'} onClick={()=>setTab('agents')}>Agent activity</button>
      <button id={`${tabId}-outputs-tab`} aria-controls={`${tabId}-outputs`} tabIndex={tab==='outputs'?0:-1} role="tab" aria-selected={tab==='outputs'} onClick={()=>setTab('outputs')}>Saved outputs <span>{events.length}</span></button>
    </div>}
    {detail && <div className="clinical-log-detail-view"><button className="clinical-log-back" onClick={() => setDetail(null)}>Back to live updates</button><ActivityDetails key={`${detail.run_tag}:${detail.iteration}:${detail.stage}`} event={detail}/></div>}
    <div hidden={!!detail} className="clinical-log-scroll" ref={scroll} tabIndex={0} aria-label="Recorded clinical activity" onScroll={e => {
      const el = e.currentTarget; setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 30);
    }}>
      <section id={`${tabId}-agents`} role="tabpanel" aria-labelledby={`${tabId}-agents-tab`} hidden={tab!=='agents'} className="clinical-log-current" aria-label="Current pipeline activity">
        {!pipelines.length && <p>Select or create a pipeline to see its activity.</p>}
        {!floorActivity && pipelines.map(p => <article key={p.id}><strong>{p.name}</strong><small>{p.progress.iteration != null ? `Loop ${p.progress.iteration}` : 'Loop not recorded'} · {clinicalRoles[p.progress.stage ?? ''] ?? 'Execution'}</small><p>{pipelineError ? 'Current execution status is unavailable. The last recorded state is retained.' : clinicalPipelineStatus(p)}</p>{(p.running ?? p.latest)?.run_tag && <button className="clinical-log-details-button" onClick={() => {setFollowing(false);setDetail({run_tag:(p.running ?? p.latest)!.run_tag,iteration:null,stage:'',pipeline_name:p.name,detail:''});}}>Browse activity</button>}{p.progress.updated_at && <time dateTime={p.progress.updated_at}>Last recorded {new Date(p.progress.updated_at).toLocaleTimeString()}</time>}</article>)}
        {floorActivity && <article className="clinical-log-execution" data-testid="floor-log-activity">
          <div className="clinical-log-identity"><strong>{pipelines.find(p=>p.id===floorActivity.pipelineId)?.name}</strong>
          {floorActivity.runTag&&<button className="clinical-log-details-button" onClick={()=>{setFollowing(false);setDetail({run_tag:floorActivity.runTag!,iteration:null,stage:'',pipeline_name:owner?.name??'',detail:''});}}>Browse activity</button>}</div>
          <small>{floorActivity.mode==='preview'?'Configuration preview':`Loop ${floorActivity.loop} · ${floorActivity.mode==='history'?'Historical records':'Following floor plan'}`}</small>
          {owner && floorActivity.mode==='live' && (pipelineError || owner.failure || !owner.running || owner.running.pause_requested || owner.running.execution_state==='paused' || owner.running.execution_state==='stopping' || owner.running.connection_health?.state==='verifying') && <p role="status">{pipelineError?'Current execution status is unavailable.':clinicalPipelineStatus(owner)}</p>}
          {floorActivity.mode==='preview'?<p>This view shows possible skills, not executing agents. Follow execution to see current activity.</p>:<>
            {floorActivity.error && <p role="status">Updates unavailable. Showing last recorded calls for this Loop.</p>}
            {!floorActivity.trace?<p>Waiting for this Loop’s agent records.</p>:<ol className="clinical-agent-list" aria-label="Floor plan agent activity">{floorActivityRows(floorActivity).map(row=><li className="clinical-agent-card" key={row.role} data-role={row.role} data-state={row.status.toLowerCase()}>
              <div className="clinical-agent-heading">{row.call?<button className="clinical-agent-link" aria-label={`View ${clinicalRoles[row.role]} activity`} onClick={()=>{setFollowing(false);setDetail({run_tag:floorActivity.runTag!,iteration:floorActivity.loop,stage:row.role,pipeline_name:owner?.name??'',detail:''});}}>{clinicalRoles[row.role]} <span aria-hidden="true">›</span></button>:<strong>{clinicalRoles[row.role]}</strong>}<span className="clinical-agent-status">{row.status==='Waiting · no call recorded'?'Not started':row.status}</span></div>
              <p className="clinical-agent-skill">{row.skill?.title??row.skill?.id??'Skill not recorded'}</p>
              {row.status==='Call still open'&&<p>This agent call has not returned yet. It may be finishing after handing off its result; this does not confirm that its main task is still running.</p>}
              {row.status==='Running'&&<p>{({hypothesis:row.call?.stage.startsWith('question')?'Developing a research question.':'Developing a testable hypothesis.',data:'Preparing the selected measurements for analysis.',ml:'The task board is at model evaluation.',interpreter:'The task board is at interpretation of the analysis.',report:'Preparing an explanation of the findings and their limitations.'})[row.role]}</p>}
            </li>)}</ol>}
          </>}
        </article>}
      </section>
      <section id={`${tabId}-outputs`} role="tabpanel" aria-labelledby={`${tabId}-outputs-tab`} hidden={tab!=='outputs'} className="clinical-saved-outputs"><h4>Saved output updates{floorActivity&&floorActivity.mode!=='preview'?` · Loop ${floorActivity.loop}`:''}</h4>
      {!events.length && <p className="clinical-log-empty">No saved output updates for this execution yet. New records will appear here automatically.</p>}
      <ol className="clinical-log-events" aria-label="Saved output updates">{events.map(event => {
        const owner = pipelines.find(p => (p.running ?? p.latest)?.run_tag === event.run_tag);
        return <li key={`${event.id}:${event.revision}`}><small>{owner?.name ?? event.pipeline_name} · {event.iteration != null ? `Loop ${event.iteration}` : 'Loop not recorded'} · {clinicalRoles[event.stage] ?? 'Analysis'}</small><p>{clinicalEventText(event)}</p>
          <time dateTime={new Date(event.receivedAt).toISOString()}>Received {new Date(event.receivedAt).toLocaleTimeString()}</time>
          <button className="clinical-log-details-button" onClick={() => {setFollowing(false);setDetail(event);}}>View details</button>
          {!!event.detail && <details><summary>Read recorded excerpt</summary><p>{event.detail}</p><small>Saved text excerpt; may be shortened. Agent-written content requires review.</small></details>}
        </li>;
      })}</ol></section>
    </div>
    {tab==='outputs' && !following && !detail && <button className="clinical-log-latest" onClick={() => setFollowing(true)}><ArrowDown size={14}/> Follow latest updates</button>}
  </>;
}
