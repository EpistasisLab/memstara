import type { PlaybookStage } from '../store/control';
export type FloorSkill = {stage: PlaybookStage; id: string; title?: string; hash?: string};
export type FloorCall = {stage: string; status: string; run_id?: string; skill?: FloorSkill};
export type FloorTrace = {calls: FloorCall[]; planned?: {combination: number; repetition: number; selection_policy?: string; start_combination?: number; agents: FloorSkill[]} | null; total_loops?: number; run_tag?: string; failure?: {message: string} | null; preparing?: boolean};
export type FloorActivity = {pipelineId: string; runTag?: string; loop: number; mode: 'live' | 'history' | 'preview'; trace: FloorTrace | null; error: string; live: boolean; paused: boolean; stopping?: boolean; currentStage?: string};
export function floorExecutionState(run?: {pause_requested?: boolean; execution_state?: string; waiting_for_questions?: boolean; connection_health?: {state?: string}} | null) {
 const paused = run?.execution_state === 'paused';
 const stopping = !paused && !!(run?.pause_requested || run?.execution_state === 'stopping');
 return {live: !!run && !paused && !stopping && !run.waiting_for_questions && run.connection_health?.state!=='verifying', paused, stopping};
}
const roles: PlaybookStage[] = ['hypothesis', 'data', 'ml', 'interpreter', 'report'];
export const floorCallRole = (c: FloorCall): PlaybookStage | undefined => c.skill?.stage ?? (c.stage.startsWith('question') ? 'hypothesis' : c.stage.startsWith('interpret') ? 'interpreter' : roles.find(s => c.stage.startsWith(s)));
export const pendingCall = (s?: string) => s === 'started' || s === 'running';
export function floorCallStatus(call: FloorCall | undefined, state: {stale?: boolean; paused?: boolean; stopping?: boolean; live?: boolean; currentStage?: string}) {
 if (call && pendingCall(call.status)) {
  if (state.stale || !state.live && !state.paused && !state.stopping) return 'Last recorded: call open';
  if (state.stopping) return 'Pause requested · finishing call';
  if (state.paused) return 'Paused · call open';
  return state.currentStage && floorCallRole(call) === floorCallRole({stage: state.currentStage, status: ''}) ? 'Running' : 'Call still open';
 }
 return call?.status === 'completed' ? 'Completed' : call?.status ?? 'Waiting · no call recorded';
}
export function floorActivityRows(activity: FloorActivity) {
 return roles.map(role => {
  const call = activity.trace?.calls.filter(c => floorCallRole(c) === role).at(-1);
  return {role, call, skill: call?.skill ?? activity.trace?.planned?.agents.find(s => s.stage === role), status: floorCallStatus(call, {stale: !!activity.error, live: activity.live, paused: activity.paused, stopping: activity.stopping, currentStage: activity.currentStage})};
 });
}
