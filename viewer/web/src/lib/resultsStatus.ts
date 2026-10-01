interface PipelineStatus {status: string; message?: string}

/** A running snapshot is progress, not a warning. Stale data must not imply liveness. */
export function resultsStatus(pipeline?: PipelineStatus | null, stale = false, execution?: {paused:boolean; stopping:boolean}) {
  if (!pipeline || pipeline.status === 'completed') return null;
  if (stale) return {warning:true, text:`Last recorded pipeline status: ${pipeline.status}. Live updates are unavailable; saved results remain visible.`};
  if (!['failed','blocked','incomplete','interrupted'].includes(pipeline.status)) {
    if (execution?.paused) return {warning:false, text:'Pipeline is paused. Saved results remain available.'};
    if (execution?.stopping) return {warning:false, text:'Pause requested. An existing call may still be finishing; saved results remain available.'};
  }
  switch (pipeline.status) {
    case 'running':
      return {warning:false, text:'Pipeline is running. Completed results appear as they are saved; the final report is not complete yet.'};
    case 'paused':
      return {warning:false, text:'Pipeline is paused. Saved results remain available.'};
    case 'pending':
    case 'waiting':
      return {warning:false, text:'Pipeline is waiting for the next step. Saved results remain available.'};
    case 'cancelled':
    case 'stopped':
      return {warning:false, text:'Execution stopped. Saved results remain available; the final report may be incomplete.'};
    case 'interrupted':
      return {warning:true, text:`Execution interrupted. ${pipeline.message || 'Saved results are retained; review the execution before resuming.'} A saved report may cover earlier completed loops only.`};
    case 'failed':
    case 'blocked':
    case 'incomplete':
      return {warning:true, text:`Pipeline needs attention (${pipeline.status}). ${pipeline.message || 'Review the recorded stage details. Saved results remain available.'}`};
    default:
      return {warning:true, text:`Recorded pipeline status: ${pipeline.status}. Completion has not been confirmed; review the recorded details.`};
  }
}
