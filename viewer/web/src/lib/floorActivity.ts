import type { PlaybookStage } from '../store/control';
export type FloorSkill = {stage: PlaybookStage; id: string; title?: string; hash?: string};
export type FloorCall = {stage: string; status: string; run_id?: string; skill?: FloorSkill};
export type FloorTrace = {calls: FloorCall[]; planned?: {combination: number; repetition: number; selection_policy?: string; start_combination?: number; agents: FloorSkill[]} | null; total_loops?: number; run_tag?: string; preparing?: boolean};
export type FloorActivity = {pipelineId: string; runTag?: string; loop: number; mode: 'live' | 'history' | 'preview'; trace: FloorTrace | null; error: string; live: boolean; paused: boolean};
const roles: PlaybookStage[] = ['hypothesis', 'data', 'ml', 'interpreter', 'report'];
export const floorCallRole = (c: FloorCall): PlaybookStage | undefined => c.skill?.stage ?? (c.stage.startsWith('question') ? 'hypothesis' : c.stage.startsWith('interpret') ? 'interpreter' : roles.find(s => c.stage.startsWith(s)));
export const pendingCall = (s?: string) => s === 'started' || s === 'running';
export function floorCallStatus(call: FloorCall | undefined, state: {stale?: boolean; paused?: boolean; live?: boolean}) {
 return pendingCall(call?.status) ? (state.stale ? 'Last recorded: running' : state.paused ? 'Paused' : state.live ? 'Running' : 'Last recorded: running') : call?.status === 'completed' ? 'Completed' : call?.status ?? 'Waiting · no call recorded';
}
export function floorActivityRows(activity: FloorActivity) {
 return roles.map(role => {
  const call = activity.trace?.calls.filter(c => floorCallRole(c) === role).at(-1);
  return {role, call, skill: call?.skill ?? activity.trace?.planned?.agents.find(s => s.stage === role), status: floorCallStatus(call, {stale: !!activity.error, live: activity.live, paused: activity.paused})};
 });
}
