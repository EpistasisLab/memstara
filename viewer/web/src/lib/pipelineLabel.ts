import type { PipelineDefinition } from '../store/pipelines';
/** Display current user names while retaining original run IDs and archive provenance. */
export function pipelineLabel(record:{pipeline_id?:string;run_tag?:string;pipeline_name?:string}, pipelines:PipelineDefinition[]) {
  return pipelines.find(p=>p.id===record.pipeline_id || (!!record.run_tag&&p.latest?.run_tag===record.run_tag))?.name || record.pipeline_name || record.run_tag || 'Analysis';
}
