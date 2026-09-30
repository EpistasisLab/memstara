import { outputArrivals } from '../lib/outputArrival';
import { create } from 'zustand';
import { usePipelines } from './pipelines';
import type { Result } from '../types';
export interface OutputEvent { id:string; pipeline_id?:string; revision:string; run_tag:string; pipeline_name:string; stage:string; title:string; detail:string; at:string|null; question_id:number|null; result_id:number|null; trial:number|null; iteration:number|null; status:string; receivedAt:number; fresh:boolean }
export interface LiveQuestion { question_id:number; text:string; okf_tags:string[]; rationale:string; origin_run:string; origin_wave:number; writer:string; times_used:number; best_auc:number|null; status:string; created_at:string }
interface Payload { events:OutputEvent[]; questions:LiveQuestion[]; results:Result[]; reports:Record<string,{status:string;text:string;error?:string}>; generated_at:string; record_limit:number }
let busy=false;
let initialized=false;
let revisions=new Map<string,string>();
export const useLiveOutputs=create<{
  events:OutputEvent[]; questions:LiveQuestion[]; results:Result[]; reports:Payload['reports'];
  error:string|null; updatedAt:string|null; tags:string; pending:number; limit:number; poll:()=>Promise<void>; acknowledge:()=>void;
}>((set,get)=>({
  events:[],questions:[],results:[],reports:{},error:null,updatedAt:null,tags:'',pending:0,limit:200,
  acknowledge:()=>set({pending:0,events:get().events.map(e=>({...e,fresh:false}))}),
  poll:async()=>{
    if(busy||document.hidden)return;
    const tags=usePipelines.getState().items.map(p=>(p.running??p.latest)?.run_tag).filter(Boolean).sort().join(',');
    if(!tags){set({tags:'',error:null});return;}
    busy=true;
    try{
      const response=await fetch(`/api/discovery/live?run_tags=${encodeURIComponent(tags)}`,{signal:AbortSignal.timeout(5500)});
      if(!response.ok)throw Error('Live output updates are unavailable. Previously received records are retained.');
      const body=await response.json() as Payload;
      const nowTags=usePipelines.getState().items.map(p=>(p.running??p.latest)?.run_tag).filter(Boolean).sort().join(',');
      if(nowTags!==tags)return;
      const receivedAt=Date.now();
      const changes=outputArrivals(revisions,body.events,receivedAt,initialized);
      const additions=changes.arrivals;revisions=changes.versions;
      const results=new Map(get().results.map(r=>[r.result_id,r]));body.results.forEach(r=>results.set(r.result_id,r));
      const questions=new Map(get().questions.map(q=>[q.question_id,q]));body.questions.forEach(q=>questions.set(q.question_id,q));
      set(s=>({tags,error:null,updatedAt:body.generated_at,limit:body.record_limit,
        events:[...additions.reverse(),...s.events].slice(0,500),pending:s.pending+additions.filter(e=>e.fresh).length,
        results:[...results.values()].sort((a,b)=>b.result_id-a.result_id).slice(0,600),
        questions:[...questions.values()].sort((a,b)=>b.question_id-a.question_id).slice(0,400),reports:{...s.reports,...body.reports}}));
      initialized=true;
    }catch(error){set({error:String(error)});}finally{busy=false;}
  },
}));
