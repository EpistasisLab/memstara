import {useSnapshot} from '../store/viewer';
import {usePipelines} from '../store/pipelines';
import {loopLabel} from './loopLabel';
import type {ReplicateIdentity} from './replicateIdentity';
/** Use the record's saved execution, never an editable next-execution draft. */
export function useLoopLabel() {
 const snapshot=useSnapshot(),items=usePipelines(s=>s.items);
 return (record:ReplicateIdentity & {iteration?:number|null;trial?:number|null;run_tag?:string|null})=>{
  const tag=record.run_tag??snapshot?.run_tag;
  const saved=tag===snapshot?.run_tag?snapshot?.run_configuration:
   items.flatMap(p=>[p.running,p.latest]).find(e=>e?.run_tag===tag)?.configuration;
  return loopLabel(record,saved?.trials,saved?.combination_plan);
 };
}
