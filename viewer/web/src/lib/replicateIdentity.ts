/** Display-only schedule mapping. Internal loop/trial IDs remain stable for replay. */
export type Schedule = {combinations:number;total_loops:number;start_index?:number;repetitions?:number};
export type ReplicateIdentity = {pipeline_number?:number;pipeline_count?:number;replicate_number?:number;replicate_count?:number|null};
export function scheduleIdentity(position:number|undefined|null,plan?:Schedule|null):ReplicateIdentity {
 if(!Number.isInteger(position)||position!<1)return {};
 if(!plan)return {pipeline_number:1,pipeline_count:1,replicate_number:position!};
 const n=plan.combinations,start=plan.start_index??0,total=plan.total_loops;
 if(!Number.isInteger(n)||n<1||!Number.isInteger(total)||position!>total||!Number.isInteger(start)||start<0||start>=n)return {};
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

/** Never present a capped historical schedule as a complete product. */
export function scheduleSummary(plan:Schedule):string {
 const count=plan.combinations,total=plan.total_loops;
 if(!Number.isInteger(count)||count<1||!Number.isInteger(total)||total<1)return 'Schedule totals unavailable';
 const pipelines=`${count.toLocaleString()} total pipelines`,replicates=`${total.toLocaleString()} total replicates`;
 return total%count===0?`${pipelines} × ${(total/count).toLocaleString()} replicates per pipeline = ${replicates}`:
  `${pipelines} · ${replicates} · Partial schedule`;
}
