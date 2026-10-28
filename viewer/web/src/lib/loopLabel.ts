import {identityLabel,scheduleIdentity,type Schedule,type ReplicateIdentity} from './replicateIdentity.ts';
/** Prefer recorded identity; a global scheduler position is not a per-pipeline repeat. */
export function loopLabel(record: ReplicateIdentity & {iteration?:number|null;trial?:number|null},analysesPerLoop?:number|null,plan?:Schedule|null):string {
 if(record.replicate_number)return identityLabel(record);
 const position=Number.isInteger(record.iteration)&&record.iteration!>0?record.iteration:
  Number.isInteger(record.trial)&&record.trial!>=0&&Number.isInteger(analysesPerLoop)&&analysesPerLoop!>0?Math.floor(record.trial!/analysesPerLoop!)+1:undefined;
 return identityLabel(scheduleIdentity(position,plan));
}
export function executionLoopLabel(iteration:number|undefined,limit:number|null|undefined,started:boolean,continuous=false,plan?:Schedule|null):string {
 if(!started)return plan?`${plan.combinations} pipelines · ${plan.total_loops} total runs`:`1 pipeline · ${limit??'—'} replicates`;
 const identity=scheduleIdentity(iteration,plan);
 if(!plan)identity.replicate_count=continuous?null:limit;
 return identityLabel(identity,true)+(continuous?' · Continuous':'');
}
