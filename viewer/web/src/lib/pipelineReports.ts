import {scheduleIdentity, type Schedule, type ReplicateIdentity} from './replicateIdentity.ts';
import {findingHeading} from './findingHeading.ts';

type Output = ReplicateIdentity & {loop:number;result_id:number|null;text:string;status:string};
type Finding = ReplicateIdentity & {run_tag?:string;iteration?:number|null;trial:number;result_id:number;hypothesis:string};
export type PipelineReport = {number:number;title:string;outputs:Output[];expected:number|null};

/** One report per frozen skill combination. Narratives remain verbatim and separate. */
export function pipelineReports(outputs:Output[], findings:Finding[], tag:string, plan?:Schedule|null, trials=1):PipelineReport[] {
 const groups=new Map<number,PipelineReport>();
 for(const output of outputs){
  const identity=output.pipeline_number?output:scheduleIdentity(output.loop,plan);
  if(!identity.pipeline_number)continue;
  const number=identity.pipeline_number;
  const group=groups.get(number)??{number,title:`Pipeline ${number}`,outputs:[],expected:identity.replicate_count??null};
  group.outputs.push({...output,...identity});groups.set(number,group);
 }
 for(const group of groups.values()){
  const finding=[...findings].filter(r=>(!r.run_tag||r.run_tag===tag)&&r.hypothesis?.trim()&&
   (r.pipeline_number??scheduleIdentity(r.iteration??Math.floor(r.trial/Math.max(1,trials))+1,plan).pipeline_number)===group.number)
   .sort((a,b)=>a.trial-b.trial||a.result_id-b.result_id)[0];
  if(finding)group.title=`Pipeline ${group.number} · ${findingHeading(finding.hypothesis)}`;
  group.outputs.sort((a,b)=>(a.replicate_number??a.loop)-(b.replicate_number??b.loop)||(a.result_id??0)-(b.result_id??0));
 }
 return [...groups.values()].sort((a,b)=>a.number-b.number);
}

/** No generated titles or status prose inside downloaded agent narratives. */
export function pipelineReportMarkdown(report:PipelineReport):string {
 return report.outputs.map(output=>output.text).join('\n\n');
}
