type PipelineStatusInput = {
  deleting?: boolean;
  running: { pause_requested?: boolean; execution_state?: string; waiting_for_questions?: boolean } | null;
  latest: { recoverable?: boolean; exit_code?: number | null } | null;
  progress: { counts?: Record<string, number>; exploration?: { skipped?: number; completed?: number } };
};

export function pipelineState(p: PipelineStatusInput, starting = false) {
  if (p.deleting) return 'Deleting';
  if (p.running?.pause_requested || p.running?.execution_state === 'paused' || p.running?.execution_state === 'stopping') return p.running.execution_state === 'paused' ? 'Paused' : 'Stopping';
  if (p.running) return p.running.waiting_for_questions ? 'Waiting' : 'Running';
  if (starting) return 'Starting';
  if ((p.progress.counts?.failed ?? 0) > 0 || (p.latest?.exit_code != null && p.latest.exit_code !== 0)) return 'Needs attention';
  // A checkpoint may still be resumable after a terminal failure. The saved
  // non-zero exit is the execution outcome; recoverability only describes an
  // available action and must not mask that failure in the pipeline list.
  if (p.latest?.recoverable) return 'Interrupted';
  if (p.latest?.exit_code === 0 && p.progress.exploration?.skipped) return p.progress.exploration.completed ? 'Finished with skips' : 'No findings';
  return p.latest ? 'Completed' : 'Ready';
}
