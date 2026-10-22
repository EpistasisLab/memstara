import { useEffect, useState } from 'react';
import { usePipelines } from '../store/pipelines';
import { costLabel } from './loopUsage';

export type ExecutionCost = {
  run_tag: string; usd: number; status: string; missing_costs: number;
  pending_runs: number; missing_archives: number;
};
export type WorkspaceCost = Omit<ExecutionCost, 'run_tag'> & {
  run_tags: string[]; executions: ExecutionCost[]; shared_agent_runs: number;
  updated_at?: string;
};

/** Mounted once by the workspace; opening a summary never starts another poller. */
export function useWorkspaceCost() {
  const pipelines = usePipelines(s => s.items);
  const loaded = usePipelines(s => s.loaded);
  const workspaceError = usePipelines(s => s.error);
  const tags = [...new Set(pipelines.flatMap(p => p.latest ? [p.latest.run_tag] : []))].sort().join(',');
  const [snapshot, setSnapshot] = useState<WorkspaceCost | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stopped = false, busy = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | null = null;
    setSnapshot(null); setError(false);
    if (!loaded) return;
    if (!tags) {
      setSnapshot({usd: 0, status: 'complete', missing_costs: 0, pending_runs: 0,
        missing_archives: 0, run_tags: [], executions: [], shared_agent_runs: 0});
      return;
    }
    const poll = async () => {
      if (stopped || busy) return;
      clearTimeout(timer);
      if (document.hidden) return;
      busy = true;
      request = new AbortController();
      const deadline = setTimeout(() => request?.abort(), 5500);
      try {
        const response = await fetch(`/api/workspace-cost?run_tags=${encodeURIComponent(tags)}`, {signal: request.signal});
        if (!response.ok) throw new Error('Cost unavailable');
        const next = await response.json() as WorkspaceCost;
        if (!Array.isArray(next.run_tags) || [...next.run_tags].sort().join(',') !== tags ||
            !Number.isFinite(next.usd) || next.usd < 0 || !Array.isArray(next.executions)) {
          throw new Error('Cost scope unavailable');
        }
        if (!stopped) { setSnapshot(next); setError(false); }
      } catch {
        if (!stopped) setError(true);
      } finally {
        clearTimeout(deadline); busy = false;
        if (!stopped) timer = setTimeout(poll, 10000);
      }
    };
    const visible = () => { if (!document.hidden) void poll(); };
    document.addEventListener('visibilitychange', visible);
    void poll();
    return () => { stopped = true; clearTimeout(timer); request?.abort(); document.removeEventListener('visibilitychange', visible); };
  }, [tags, loaded]);

  // Never display an old execution's cost under a newly selected workspace scope.
  const cost = loaded && snapshot?.run_tags.join(',') === tags ? snapshot : null;
  const delayed = error || !!workspaceError;
  const empty = loaded && !tags && !workspaceError;
  const partial = !!cost && cost.status !== 'complete';
  const label = empty ? '—' : cost ? costLabel(cost) : delayed ? 'Not available' : '—';
  const value = label.replace(' · recorded subtotal', '');
  const status = delayed ? 'Update delayed' : empty ? 'No executions' : !cost ? 'Loading cost' : partial ? 'Partial estimate' : null;
  const description = delayed ? (cost ? 'Update delayed · last available estimate' : 'Cost records unavailable')
    : empty ? 'No executions in this workspace' : !cost ? 'Awaiting cost records'
    : cost.missing_costs > 0 ? `Pricing unavailable for ${cost.missing_costs} agent executions; recorded subtotal only`
    : partial ? 'Incomplete usage · recorded subtotal only' : 'Latest executions · estimated, not billed';
  return {cost, value, label, status, description, delayed, partial, empty};
}

export type WorkspaceCostState = ReturnType<typeof useWorkspaceCost>;
