import type { Snapshot, Result } from '../types.ts';
import type { ExecutionUsage } from '../components/TelemetryTotals.tsx';
import { scheduleIdentity, type ReplicateIdentity } from './replicateIdentity.ts';
import { interpretationOutputs } from './interpretationOutputs.ts';

export type OutputView = 'results' | 'report' | 'agents';
export const outputViewNames = {results: 'Results', report: 'Conclusions', agents: 'Usage'} as const;
export type ExecutionTile = ReplicateIdentity & {
  loop: number;
  results: Result[];
  explanations: NonNullable<NonNullable<Snapshot['report']>['explanation_outputs']>;
  usage?: ExecutionUsage['loops'][number];
  failed: boolean;
};

/** Group by the frozen schedule, never by completion order or a neighbouring run. */
export function executionTiles(snapshot: Snapshot, usage?: ExecutionUsage): ExecutionTile[] {
  const config = snapshot.run_configuration;
  const plan = config?.combination_plan;
  const trials = Math.max(1, config?.trials ?? 1);
  const matchingUsage = usage?.run_tag === snapshot.run_tag ? usage : undefined;
  const tiles = new Map<number, ExecutionTile>();
  const ensure = (loop: number, identity?: ReplicateIdentity) => {
    if (!Number.isInteger(loop) || loop < 1) return undefined;
    let tile = tiles.get(loop);
    if (!tile) {
      tile = {loop, ...scheduleIdentity(loop, plan), results: [], explanations: [], failed: false};
      tiles.set(loop, tile);
    }
    if (identity?.pipeline_number && identity?.replicate_number) {
      tile.pipeline_number = identity.pipeline_number;
      tile.replicate_number = identity.replicate_number;
    }
    return tile;
  };
  const total = plan?.total_loops ?? (config?.continuous ? 0 : config?.waves ?? 0);
  for (let loop = 1; loop <= total; loop++) ensure(loop);
  for (const result of snapshot.results) {
    if (result.run_tag && result.run_tag !== snapshot.run_tag) continue;
    const loop = result.iteration ?? Math.floor(result.trial / trials) + 1;
    ensure(loop, result)?.results.push(result);
  }
  for (const output of snapshot.report?.explanation_outputs ?? []) ensure(output.loop, output)?.explanations.push(output);
  for (const metric of matchingUsage?.loops ?? []) {
    const tile = ensure(metric.number, metric);
    if (tile) tile.usage = metric;
  }
  for (const task of snapshot.board?.tasks ?? []) {
    const tile = ensure(Math.floor(task.trial / trials) + 1);
    if (tile && task.status === 'failed') tile.failed = true;
  }
  for (const tile of tiles.values()) tile.results.sort((a, b) => a.trial - b.trial || a.result_id - b.result_id);
  return [...tiles.values()].sort((a, b) => (a.pipeline_number ?? Infinity) - (b.pipeline_number ?? Infinity)
    || (a.replicate_number ?? a.loop) - (b.replicate_number ?? b.loop) || a.loop - b.loop);
}

/** Completion belongs to this view, not to another stage or a partial text. */
export function tileComplete(tile: ExecutionTile, view: OutputView): boolean {
  if (view === 'results') return tile.results.length > 0 && tile.results.every(result => {
    const outputs = interpretationOutputs(result);
    return outputs.length > 0 && outputs.every(output => output.status === 'done' && !!output.text?.trim());
  });
  if (view === 'report') return tile.explanations.length > 0
    && tile.explanations.every(output => output.status === 'completed' && !!output.text?.trim());
  return tile.usage?.status === 'completed';
}

export function tileStatus(tile: ExecutionTile, view: OutputView): string {
  if (tileComplete(tile, view)) return 'Ready';
  if (view === 'results') {
    const outputs = tile.results.flatMap(interpretationOutputs);
    if (outputs.some(o => o.text)) return 'Partial output';
  } else if (view === 'report') {
    if (tile.explanations.some(o => o.text)) return 'Partial output';
  } else if (tile.usage) return tile.usage.status?.replaceAll('_', ' ') || 'Recorded';
  return tile.failed ? 'Needs attention' : 'Awaiting output';
}

export function testAuroc(result: Result): string {
  // The result's auc is the recorded held-out test score; do not substitute CV/train.
  return typeof result.auc === 'number' && Number.isFinite(result.auc) ? result.auc.toFixed(3) : 'Not reported';
}
