import { useEffect, useRef } from 'react';
import { useViewer } from '../store/viewer';
import { usePipelines } from '../store/pipelines';

/** Navigate once on observed completion, never when opening saved history. */
export function useCompletedResults() {
  const snapshot = useViewer(s => s.snapshot);
  const requested = useViewer(s => s.runTag);
  const error = useViewer(s => s.error);
  const active = useRef(new Set<string>());
  const handled = useRef(new Set<string>());
  const previousRequest = useRef(requested);
  useEffect(() => {
    if (previousRequest.current !== requested) {
      active.current.clear();
      previousRequest.current = requested;
    }
    if (!snapshot || error || snapshot.stale || snapshot.health.memstara.up === false ||
        snapshot.run_tag !== requested) return;
    const tag = snapshot.run_tag;
    const status = snapshot.pipeline?.status;
    if (status === 'running' || status === 'paused') active.current.add(tag);
    if (status !== 'completed' || !active.current.has(tag) || handled.current.has(tag)) return;
    // A proposal-only run has no model results; its output belongs in Conclusions.
    if (!snapshot.results.length && !snapshot.report?.text) return;
    handled.current.add(tag);
    const dialogOpen = [...document.querySelectorAll('dialog[open], [role="dialog"]')]
      .some(element => element.getClientRects().length > 0);
    if (useViewer.getState().view !== 'scene' || usePipelines.getState().creationOpen ||
        document.hidden || dialogOpen) return;
    usePipelines.setState({resultsScope: 'selected'});
    useViewer.getState().setView(snapshot.results.length ? 'results' : 'report');
  }, [snapshot, requested, error]);
}
