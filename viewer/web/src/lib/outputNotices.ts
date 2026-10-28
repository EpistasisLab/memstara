import type { Snapshot } from '../types.ts';
import type { ExecutionUsage } from '../components/TelemetryTotals.tsx';
import { executionTiles, tileComplete } from './executionTiles.ts';

export type NoticeView = 'report' | 'agents';

// A receipt contains an identifier and revision, never report text or credentials.
function revision(value: unknown): string {
  let hash = 2166136261;
  for (const character of JSON.stringify(value)) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  return (hash >>> 0).toString(36);
}

export function outputNoticeKeys(snapshot: Snapshot, usage: ExecutionUsage | undefined, view: NoticeView, loop?: number): string[] {
  return executionTiles(snapshot, usage).filter(tile => tileComplete(tile, view) && (loop === undefined || tile.loop === loop))
    .map(tile => `${snapshot.run_tag}:${view}:${tile.loop}:${revision(view === 'report'
      ? tile.explanations.map(output => [output.result_id, output.text]).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))
      : [tile.usage?.calls, tile.usage?.tokens, tile.usage?.tokens_status, tile.usage?.cost, tile.usage?.seconds, tile.usage?.duration_status])}`);
}
