import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { usePipelines } from '../store/pipelines';
import { useLiveOutputs } from '../store/liveOutputs';

/** Reuse existing polling stores; do not add a second status request stream. */
export default function HeaderStatus({onOpen}: {onOpen: () => void}) {
  const items = usePipelines(s => s.items);
  const loaded = usePipelines(s => s.loaded);
  const error = usePipelines(s => s.error);
  const live = useLiveOutputs();
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  const tags = [...new Set(items.flatMap(p => p.latest ? [p.latest.run_tag] : []))].sort();
  const stale = !!error || (tags.length > 0 && (!!live.error || live.tags !== tags.join(',') || !live.updatedAt || now - Date.parse(live.updatedAt) > 15000));
  const running = items.filter(p => p.running && (!('execution_state' in p.running) || p.running.execution_state !== 'paused')).length;
  const results = live.results.filter(r => r.run_tag && tags.includes(r.run_tag)).length;
  const label = stale ? 'Updates delayed' : !loaded ? 'Connecting…' : running ? `${running} running` : 'No pipelines running';
  return <button className={`topbar-live-status ${stale ? 'is-delayed' : ''}`} onClick={onOpen}
    aria-label={`${label}. Open workspace summary`} title="Current workspace status. Open Workspace summary for details and data freshness.">
    <Activity size={16}/><span>{label}</span>
    {loaded && !stale && <span className="topbar-result-count">{results} results loaded</span>}
  </button>;
}
