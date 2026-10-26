/** Display-only schedule mapping. Internal loop/trial IDs remain stable for replay. */
export type Schedule = {combinations:number;total_loops:number;start_index?:number;repetitions?:number;execution_order?:'all_pipelines_first'|'pipeline_replicates_first'};
export type ReplicateIdentity = {pipeline_number?:number;pipeline_count?:number;replicate_number?:number;replicate_count?:number|null};
export function scheduleIdentity(position:number|undefined|null,plan?:Schedule|null):ReplicateIdentity {
 if(!Number.isInteger(position)||position!<1)return {};
 if(!plan)return {pipeline_number:1,pipeline_count:1,replicate_number:position!};
 const n=plan.combinations,start=plan.start_index??0,total=plan.total_loops;
 if(!Number.isInteger(n)||n<1||!Number.isInteger(total)||position!>total||!Number.isInteger(start)||start<0||start>=n)return {};
 if(plan.execution_order==='pipeline_replicates_first') {
  const repeats=plan.repetitions??0;
  if(!Number.isInteger(repeats)||repeats<1)return {};
  const cycle=n*repeats,offset=Math.floor((position!-1)/repeats)%n,remainder=total%cycle;
  return {pipeline_number:(start+offset)%n+1,pipeline_count:n,
   replicate_number:Math.floor((position!-1)/cycle)*repeats+(position!-1)%repeats+1,
   replicate_count:Math.floor(total/cycle)*repeats+Math.min(repeats,Math.max(0,remainder-offset*repeats))};
 }
 const offset=(position!-1)%n;
 return {pipeline_number:(start+offset)%n+1,pipeline_count:n,replicate_number:Math.floor((position!-1)/n)+1,
  replicate_count:Math.floor(total/n)+(offset<total%n?1:0)};
}
export function identityLabel(identity:ReplicateIdentity, totals=false):string {
 const p=identity.pipeline_number,r=identity.replicate_number;
 return `Pipeline ${p??'—'}${totals&&identity.pipeline_count?` / ${identity.pipeline_count}`:''} · Replicate ${r??'—'}${totals&&identity.replicate_count?` / ${identity.replicate_count}`:''}`;
}
export function scheduledLabel(position:number|undefined|null,plan?:Schedule|null,totals=false):string {
 return identityLabel(scheduleIdentity(position,plan),totals);
}
