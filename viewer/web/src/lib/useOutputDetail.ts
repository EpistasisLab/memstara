import {useEffect, useState} from 'react';
import type {ExecutionTile, OutputView} from './executionTiles';
import type {Result, Snapshot} from '../types';

type Detail = {run_tag: string; loop: number; results: Result[];
  explanation_outputs: NonNullable<NonNullable<Snapshot['report']>['explanation_outputs']>};

export function useOutputDetail(tag: string, tile: ExecutionTile | undefined, view: OutputView, deferred: boolean, revision?: string) {
  const loop = tile?.loop;
  const needed = deferred && loop !== undefined && view !== 'agents';
  const scope = `${tag}:${loop}`;
  const [saved, setSaved] = useState<{scope: string; data?: Detail; error?: string} | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!needed) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(`/api/output-detail?run_tag=${encodeURIComponent(tag)}&loop=${loop}`,
          {signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)])});
        if (!response.ok) throw Error('Saved output details could not be loaded. Retry; saved records are unchanged.');
        const data: Detail = await response.json();
        if (data.run_tag !== tag || data.loop !== loop) throw Error('The output response belongs to a different execution.');
        if (!controller.signal.aborted) setSaved({scope, data});
      } catch (error) {
        if (!controller.signal.aborted) setSaved(previous => ({scope,
          data: previous?.scope === scope ? previous.data : undefined,
          error: error instanceof Error ? error.message : 'Details unavailable.'}));
      }
    })();
    return () => controller.abort();
  }, [tag, loop, needed, scope, revision, retry]);
  const current = saved?.scope === scope ? saved : null;
  return {tile: tile && current?.data ? {...tile, results: current.data.results, explanations: current.data.explanation_outputs} : tile,
    ready: !needed || !!current?.data, error: needed ? current?.error : undefined, retry: () => setRetry(n => n + 1)};
}
