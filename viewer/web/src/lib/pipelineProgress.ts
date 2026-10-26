import { executionLoopLabel } from './loopLabel';
import type { PipelineDefinition } from "../store/pipelines";
const stages=["hypothesis","data","ml","interpreter","report"];
/** One display rule shared by Experiments and Status; this is not a time estimate. */
export function pipelinePercent(pipeline: PipelineDefinition): number | null {
  const recorded=pipeline.progress.stage_percent;
  if(typeof recorded==="number"&&Number.isFinite(recorded))return Math.max(0,Math.min(100,recorded));
  const index=stages.indexOf(pipeline.progress.stage??"");
  return index<0?null:index*20;
}

/** A loop is one iteration, whether it completes or is blocked. */
export function pipelineLoopLabel(pipeline: PipelineDefinition): string {
  const execution = pipeline.running ?? pipeline.latest;
  const config = execution ? execution.configuration : pipeline.configuration;
  const draft=pipeline.configuration;
  const count=Object.values(draft.combination_skills??{}).reduce((n,ids)=>n*(ids?.length??0),1);
  const plan=config?.combination_plan??(!execution&&draft.combination_skills?{combinations:count,repetitions:draft.combination_repetitions??1,execution_order:draft.combination_execution_order,total_loops:draft.combination_max_loops??count*(draft.combination_repetitions??1)}:undefined);
  return executionLoopLabel(pipeline.progress.iteration,config?.waves,!!execution,!!config?.continuous,plan);
}
