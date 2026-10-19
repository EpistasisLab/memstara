import type {Point3} from '../components/discovery/geometry';
export interface SemanticData {
 status:string; indexed_count?:number; total_questions?:number; coverage?:string;
 identity?:{model:string; revision:string}; index_hash?:string; limitations?:string;
 points:{question_id:number;x:number;y:number;z:number}[];
 neighbors:{question_id:number;text?:string;similarity:number}[];
}
export function positions(data:SemanticData|null):Record<number,Point3> {
 return Object.fromEntries((data?.points??[]).filter(p=>[p.x,p.y,p.z].every(Number.isFinite)).map(p=>[p.question_id,{x:p.x,y:p.y,z:p.z}]));
}
