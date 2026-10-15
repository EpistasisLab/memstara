interface PipelineStatus {status: string; message?: string; stage?: string; loop?: number | null; code?: string}

/** A running snapshot is progress, not a warning. Stale data must not imply liveness. */
export function resultsStatus(pipeline?: PipelineStatus | null, stale = false, execution?: {paused:boolean; stopping:boolean}) {
  if (!pipeline || pipeline.status === 'completed') return null;
  if (stale) return {warning:true, text:`Last recorded pipeline status: ${pipeline.status}. Live updates are unavailable; saved results remain visible.`};
  if (!['failed','blocked','incomplete','interrupted'].includes(pipeline.status)) {
    if (execution?.paused) return {warning:false, text:'Pipeline is paused. Saved results remain available.'};
    if (execution?.stopping) return {warning:false, text:'Pause requested. An existing call may still be finishing; saved results remain available.'};
  }
  switch (pipeline.status) {
    case 'completed_with_skips':
      return {warning:false, text:'Execution finished with skipped Loops. Completed findings are saved; skipped Loops produced no analysis and are not counted as completed.'};
    case 'no_findings':
      return {warning:false, text:'Execution ended without findings. No executable question was saved for the attempted combinations; no analysis or report was produced.'};
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
      {
        const stages:Record<string,string>={question:'Question generation',hypothesis:'Hypothesis generation',
          data:'Data preparation',ml:'Model training',interpret:'Interpretation',interpreter:'Interpretation',report:'Explanation report',preflight:'Startup checks'};
        const role=pipeline.stage?.match(/^(question|hypothesis|data|ml|interpreter|interpret|report|preflight)(?:[#\d-].*)?$/)?.[1];
        const location=role ? ` at ${stages[role]}` : '';
        const loop=typeof pipeline.loop==='number' && pipeline.loop>0 ? ` (Loop ${pipeline.loop})` : '';
        const generic=pipeline.message?.includes('Pipeline could not safely continue; inspect console.log and trace/');
        const reason=generic || !pipeline.message ? 'The saved diagnostic does not identify the cause. Saved results remain available.' : pipeline.message;
        return {warning:true, text:`This execution ${pipeline.status==='failed'?'failed':pipeline.status==='blocked'?'was blocked':'is incomplete'}${location}${loop}. ${reason}`};
      }
    default:
      return {warning:true, text:`Recorded pipeline status: ${pipeline.status}. Completion has not been confirmed; review the recorded details.`};
  }
}
