import { create } from "zustand";
import { useControl, type RunRequest, type RunningRun } from "./control";
import { useViewer } from "./viewer";
import { usePipelineSetup } from "./pipelineSetup";

export interface PipelineDefinition {
  id: string; number: number; name: string; configuration: RunRequest;
  running: RunningRun | null;
  latest: (RunningRun & { exit_code?: number }) | null;
  progress: { stage_percent?: number | null; iteration_completed?: boolean; iteration?: number; stage?: string; updated_at?: string; counts?: Record<string, number> };
}
const selectionKey = 'memstara.pipelineSelection';
function remember(id: string | null) {
  try { if(id) localStorage.setItem(selectionKey,id); else localStorage.removeItem(selectionKey); } catch { /* Storage may be unavailable. */ }
}
function remembered(): string | null {
  try { return localStorage.getItem(selectionKey); } catch { return null; }
}
let inFlight = false;
let saveQueue: Promise<unknown> = Promise.resolve();
async function request(body: object) {
  const response = await fetch('/control/pipelines', { method: 'POST', headers: {'Content-Type':'application/json'}, body:JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Pipeline settings could not be saved');
  return data;
}
export const usePipelines = create<{
  creationOpen: boolean; closeCreation: () => void; create: (name: string, configuration: RunRequest) => Promise<boolean>;
  focusRevision: number; focus: (id:string)=>void;
  resultsScope: "all" | "selected"; viewRun: (tag:string|null)=>void;
  items: PipelineDefinition[]; selected: string | null; loaded: boolean; busy: boolean; error: string | null;
  poll: () => Promise<void>; select: (id: string) => void; add: () => Promise<void>;
  save: (id: string, config: RunRequest) => void; rename: (id:string,name:string)=>Promise<void>;
  remove: (id:string)=>Promise<void>; play: (id:string)=>Promise<void>; stop: (id:string)=>Promise<void>;
}>((set,get)=>({
  creationOpen:false,
  closeCreation:()=>{if(!get().busy)set({creationOpen:false});},
  focusRevision:0,
  focus:id=>{
    if(!get().items.some(p=>p.id===id))return;
    get().select(id);
    set(state=>({focusRevision:state.focusRevision+1}));
  },
  resultsScope:"selected", items:[], selected:null, loaded:false, busy:false, error:null,
  poll: async()=>{
    if(inFlight || get().busy) return;
    inFlight=true;
    try {
      const response=await fetch('/control/pipelines',{signal:AbortSignal.timeout(10000)});
      if(!response.ok) throw new Error('Pipeline workspace is unavailable; last settings are retained.');
      const data=await response.json();
      if(!get().busy) {
        const firstLoad = !get().loaded;
        const previousTag=get().items.find(p=>p.id===get().selected)?.latest?.run_tag;
        set({items:data.pipelines,loaded:true,error:null});
        const restored = remembered();
        if(firstLoad && restored) get().select(restored);
        const refreshed=get().items.find(p=>p.id===get().selected);
        if(refreshed&&refreshed.latest?.run_tag!==previousTag&&
          (useViewer.getState().runTag===previousTag||useViewer.getState().runTag===null))
          get().select(refreshed.id);
      }
      const selected=get().items.find(p=>p.id===get().selected);
      if(selected) useControl.setState({running:selected.running});
    } catch(e){set({error:String(e)});} finally{inFlight=false;}
  },
  select:id=>{
    const pipeline=get().items.find(p=>p.id===id); if(!pipeline) return;
    const changed=get().selected!==id;
    set({selected:id,resultsScope:"selected"}); remember(id);
    useControl.setState({form:pipeline.configuration,running:pipeline.running,...(changed?{editor:null}:{})});
    const tag=pipeline.latest?.run_tag||null;
    if(useViewer.getState().runTag!==tag)useViewer.getState().setRunTag(tag);
  },
  viewRun:tag=>{
    const matching=get().items.find(p=>p.latest?.run_tag===tag);
    if(matching){get().select(matching.id);return;}
    set({selected:null,resultsScope:"selected"});remember(null);
    useControl.setState({running:null,editor:null});
    useViewer.getState().setRunTag(tag);
  },
  add:async()=>{
    if(get().busy || get().items.length>=3) return;
    set({creationOpen:true,error:null});
  },
  create:async(name,configuration)=>{
    if(get().busy || get().items.length>=3) return false;
    set({busy:true,error:null});
    try {
      const item=await request({action:'add',name,configuration:{...configuration,question:"",
        hypothesis_agents:1,interpret_agents:1,trials:1,waves:1,continuous:true}});
      set({items:[...get().items,{...item,running:null,latest:null,progress:{}}],creationOpen:false});
      get().select(item.id);
      return true;
    }catch(e){set({error:String(e)});return false;}finally{set({busy:false});}
  },
  save:(id,configuration)=>{
    set({busy:true,error:null,items:get().items.map(p=>p.id===id?{...p,configuration}:p)});
    saveQueue=saveQueue.catch(()=>{}).then(async()=>{
      try{await request({action:'update',id,configuration});}
      catch(e){set({error:`Settings not saved: ${String(e)}`}); throw e;}
    });
    const current=saveQueue;
    void current.catch(()=>{}).finally(()=>{if(saveQueue===current)set({busy:false});});
  },
  rename:async(id,name)=>{
    if(get().busy)return;
    set({busy:true,error:null});
    try{const item=await request({action:'update',id,name});set({items:get().items.map(p=>p.id===id?{...p,name:item.name}:p)});}
    catch(e){set({error:String(e)});throw e;}finally{set({busy:false});}
  },
  remove:async id=>{
    if(get().busy)return;set({busy:true,error:null});
    try{await request({action:'remove',id});set({items:get().items.filter(p=>p.id!==id)});usePipelineSetup.getState().remove(id);
      if(get().selected===id){set({selected:null});remember(null);useControl.setState({running:null,editor:null});useViewer.getState().setRunTag(null);}}
    catch(e){set({error:String(e)});}finally{set({busy:false});}
  },
  play:async id=>{
    if(get().busy)return;set({busy:true,error:null});
    try{await saveQueue;const response=await fetch('/control/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pipeline_id:id})});
      const run=await response.json();if(!response.ok)throw new Error(run.error);
      set({items:get().items.map(p=>p.id===id?{...p,running:run,latest:run,progress:{}}:p)});get().select(id);
    }catch(e){set({error:String(e)});}finally{set({busy:false});}
  },
  stop:async id=>{
    const run=get().items.find(p=>p.id===id)?.running;if(!run || get().busy)return;set({busy:true,error:null});
    try{const response=await fetch(`/control/runs/${encodeURIComponent(run.run_tag)}/stop`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      if(!response.ok)throw new Error((await response.json()).error);
    }catch(e){set({error:String(e)});}finally{set({busy:false});}
  },
}));
