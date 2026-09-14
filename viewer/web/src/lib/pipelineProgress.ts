import type { PipelineDefinition } from "../store/pipelines";
const stages=["hypothesis","data","ml","interpreter","report"];
/** One display rule shared by Floor Plan and Status; this is not a time estimate. */
export function pipelinePercent(pipeline: PipelineDefinition): number | null {
  const recorded=pipeline.progress.stage_percent;
  if(typeof recorded==="number"&&Number.isFinite(recorded))return Math.max(0,Math.min(100,recorded));
  const index=stages.indexOf(pipeline.progress.stage??"");
  return index<0?null:index*20;
}
