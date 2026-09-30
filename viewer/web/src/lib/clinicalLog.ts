import type { PipelineDefinition } from '../store/pipelines';
import type { OutputEvent } from '../store/liveOutputs';

export const clinicalRoles: Record<string, string> = {
  question: 'Question generation', hypothesis: 'Hypothesis', data: 'Data',
  ml: 'Machine learning', interpreter: 'Interpretation', interpretation: 'Interpretation',
  report: 'Explanation', result: 'Analysis result',
};
const working: Record<string, string> = {
  question: 'Developing a research question.', hypothesis: 'Developing a testable hypothesis.',
  data: 'Preparing the selected measurements for analysis.', ml: 'Training and evaluating the prediction model.',
  interpreter: 'Describing what the analysis found.', report: 'Preparing an explanation of the findings and their limitations.',
};

/** Describe recorded execution state; a zero exit code alone is not completion. */
export function clinicalPipelineStatus(p: PipelineDefinition) {
  if (p.failure) return p.failure.message;
  const execution = p.running ?? p.latest;
  if (execution?.infrastructure_status?.status === 'interrupted') return execution.infrastructure_status.message || 'Execution interrupted. Previously saved results are retained.';
  if (p.running?.connection_health?.state === 'verifying') return 'Checking the database connection. New model calls are waiting; saved results are retained.';
  if (p.running?.execution_state === 'paused') return 'Paused. The pipeline is waiting to resume.';
  if (p.running?.pause_requested || p.running?.execution_state === 'stopping') return 'Pausing after the current agent call finishes.';
  if ((p.progress.counts?.failed ?? 0) > 0 || p.progress.exploration?.outcome === 'blocked') return 'An analysis step needs attention. Review the recorded details.';
  if (p.running?.waiting_for_questions) return 'Waiting for an eligible research question.';
  if (p.running) return working[p.progress.stage ?? ''] ?? 'Execution is active. Waiting for the next recorded step.';
  if (!p.latest) return 'Ready. This pipeline has not started.';
  if (p.latest.recoverable) return 'Execution stopped. A saved checkpoint is available.';
  if (p.latest.exit_code === 0 && p.progress.exploration?.outcome === 'completed') return 'Execution completed. Review the findings and their limitations.';
  if (p.latest.exit_code !== undefined && p.latest.exit_code !== 0) return 'Execution stopped with an error. Previously saved results are retained.';
  return 'Execution ended. Completion has not been confirmed.';
}

/** Templates summarize recorded events, never infer clinical conclusions from them. */
export function clinicalEventText(event: OutputEvent) {
  if (['failed', 'error', 'blocked'].includes(event.status)) return 'This step needs attention. Review its recorded details.';
  if (['pending', 'running', 'in_progress', 'started'].includes(event.status)) return 'This step is in progress; a finished output has not been confirmed.';
  const messages: Record<string, string> = {
    question: 'A research question was recorded.', hypothesis: 'A hypothesis was recorded for analysis.',
    data: 'Selected measurements were recorded for this analysis.', ml: 'A model evaluation was recorded.',
    interpreter: 'An interpretation was saved.', interpretation: 'An interpretation was saved.',
    result: 'An analysis result is available for review.', report: 'The explanation record was updated.',
  };
  return messages[event.stage] ?? 'An analysis update was recorded.';
}

export function scopedClinicalEvents(events: OutputEvent[], pipelines: PipelineDefinition[]) {
  const tags = new Set(pipelines.map(p => (p.running ?? p.latest)?.run_tag).filter(Boolean));
  return events.filter(e => tags.has(e.run_tag)).sort((a, b) => a.receivedAt - b.receivedAt);
}
