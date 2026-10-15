import { create } from "zustand";
import { useControl, type RunRequest, type RunningRun } from "./control";
import { useViewer } from "./viewer";
import { usePipelineSetup } from "./pipelineSetup";
import {startPipelines, type StartOutcome} from '../lib/startPipelines';
import {newPipelineRequest} from '../lib/newPipelineConfiguration';

export interface PipelineDefinition {
  id: string; number: number; name: string; configuration: RunRequest;
  running: RunningRun | null;
  failure?: {code: string; message: string; stage?: string; loop?: number | null} | null;
  latest: (RunningRun & { exit_code?: number }) | null;
  loop_totals?: {attempted:number;completed:number;blocked:number;unknown_executions:number};
  progress: { exploration?: { attempted: number; completed: number; blocked: number; skipped?: number; outcome: string; reason: string }; stage_percent?: number | null; iteration_completed?: boolean; iteration?: number; stage?: string; updated_at?: string; counts?: Record<string, number> };
}
const selectionKey = 'memstara.pipelineSelection';
function remember(id: string | null) {
  try { if(id) localStorage.setItem(selectionKey,id); else localStorage.removeItem(selectionKey); } catch { /* Storage may be unavailable. */ }
}
function remembered(): string | null {
  try { return localStorage.getItem(selectionKey); } catch { return null; }
}
let inFlight = false;
let workspaceRevision = 0;
let saveQueue: Promise<unknown> = Promise.resolve();
let bulkStart: Promise<void> | null = null;
let cancelBulkStart = false;
const delayedStartMessage = 'The start response was delayed. Checking server status; do not start again until its state updates.';
async function request(body: object) {
  const response = await fetch('/control/pipelines', { method: 'POST', headers: {'Content-Type':'application/json'}, body:JSON.stringify(body), signal:AbortSignal.timeout(10000) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Pipeline settings could not be saved');
  return data;
}
export const usePipelines = create<{
  creationOpen: boolean; closeCreation: () => void; create: (name: string, configuration: RunRequest) => Promise<boolean>;
  focusRevision: number; focus: (id:string)=>void;
  resultsScope: "all" | "selected"; viewRun: (tag:string|null)=>void;
  items: PipelineDefinition[]; selected: string | null; loaded: boolean; busy: boolean; error: string | null;
  pendingStart: {pipelineId:string; previousTag:string|null} | null;
  poll: () => Promise<void>; select: (id: string) => void; add: () => Promise<void>;
  save: (id: string, config: RunRequest) => Promise<boolean>; rename: (id:string,name:string)=>Promise<void>;
  stoppingAll: boolean; stopAll:()=>Promise<void>; end:(id:string,expectedRunTag?:string)=>Promise<boolean>; pause:(id:string,paused:boolean)=>Promise<void>;
  startingAll: boolean; startOutcomes: StartOutcome[]; playAll:()=>Promise<void>;
  remove: (id:string)=>Promise<boolean>; play: (id:string, options?:{mode:"additional"|"fresh";loops?:number;expectedRunTag:string})=>Promise<boolean>; stop: (id:string)=>Promise<void>;
}>((set,get)=>({
  creationOpen:false, stoppingAll:false, startingAll:false, startOutcomes:[],
  closeCreation:()=>{if(!get().busy)set({creationOpen:false});},
  focusRevision:0,
  focus:id=>{
    if(!get().items.some(p=>p.id===id))return;
    get().select(id);
    set(state=>({focusRevision:state.focusRevision+1}));
  },
  resultsScope:"selected", items:[], selected:null, loaded:false, busy:false, error:null, pendingStart:null,
  poll: async()=>{
    if(inFlight || get().busy) return;
    inFlight=true;
    const revision = workspaceRevision;
    try {
      const response=await fetch('/control/pipelines',{signal:AbortSignal.timeout(10000)});
      if(!response.ok) throw new Error('Pipeline workspace is unavailable; last settings are retained.');
      const data=await response.json();
      if(revision !== workspaceRevision) return;
      if(!get().busy) {
        const firstLoad = !get().loaded;
        const previousTag=get().items.find(p=>p.id===get().selected)?.latest?.run_tag;
        const previousItems=get().items;
        const refreshedItems:PipelineDefinition[]=data.pipelines.map((item:PipelineDefinition)=>{
          const previous=previousItems.find(p=>p.id===item.id);
          return previous&&JSON.stringify(previous)===JSON.stringify(item)?previous:item;
        });
        const unchanged=refreshedItems.length===previousItems.length&&refreshedItems.every((item,i)=>item===previousItems[i]);
        const pollingError = get().error === 'Error: Pipeline workspace is unavailable; last settings are retained.';
        const pending = get().pendingStart;
        const started = pending && refreshedItems.find(p=>p.id===pending.pipelineId);
        const confirmed = !!(started && (started.running?.run_tag || started.latest?.run_tag) &&
          (started.running?.run_tag || started.latest?.run_tag)!==pending!.previousTag);
        if(!unchanged||!get().loaded||pollingError||confirmed)set({items:unchanged?previousItems:refreshedItems,loaded:true,
          ...(confirmed?{pendingStart:null}:{}),
          ...(pollingError||(confirmed&&get().error===delayedStartMessage)?{error:null}:{})});
        const restored = remembered();
        if(firstLoad && restored) get().select(restored);
        const refreshed=get().items.find(p=>p.id===get().selected);
        if(refreshed&&refreshed.latest?.run_tag!==previousTag&&
          (useViewer.getState().runTag===previousTag||useViewer.getState().runTag===null))
          get().select(refreshed.id);
      }
      const selected=get().items.find(p=>p.id===get().selected);
      if(selected&&JSON.stringify(useControl.getState().running)!==JSON.stringify(selected.running)) useControl.setState({running:selected.running});
    } catch {
      // A background refresh must not replace a failed user action's diagnosis.
      if(revision === workspaceRevision && !get().error)
        set({error:'Error: Pipeline workspace is unavailable; last settings are retained.'});
    } finally{inFlight=false;}
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
    if(get().busy) return;
    set({creationOpen:true,error:null});
  },
  create:async(name,configuration)=>{
    if(get().busy) return false;
    set({busy:true,error:null});
    try {
      const item=await request({action:'add',name,configuration:{...newPipelineRequest(configuration),question:"",
        hypothesis_agents:1,interpret_agents:1,trials:1}});
      set({items:[...get().items,{...item,running:null,latest:null,progress:{}}],creationOpen:false});
      get().select(item.id);
      return true;
    }catch(e){set({error:String(e)});return false;}finally{set({busy:false});}
  },
  save:(id,configuration)=>{
    const previous=get().items.find(p=>p.id===id)?.configuration;
    set({busy:true,error:null,items:get().items.map(p=>p.id===id?{...p,configuration}:p)});
    saveQueue=saveQueue.catch(()=>{}).then(async()=>{
      try{await request({action:'update',id,configuration});}
      catch(e){set({error:`Settings not saved: ${String(e)}`,items:get().items.map(p=>p.id===id&&p.configuration===configuration&&previous?{...p,configuration:previous}:p)}); throw e;}
    });
    const current=saveQueue;
    void current.catch(()=>{}).finally(()=>{if(saveQueue===current)set({busy:false});});
    return current.then(()=>true,()=>false);
  },
  rename:async(id,name)=>{
    if(get().busy)return;
    set({busy:true,error:null});
    try{const item=await request({action:'update',id,name});set({items:get().items.map(p=>p.id===id?{...p,name:item.name}:p)});}
    catch(e){set({error:String(e)});throw e;}finally{set({busy:false});}
  },
  remove:async id=>{
    if(get().busy)return false;
    workspaceRevision++;
    set({busy:true,error:null});
    try{
      await request({action:'remove',id});
      set({items:get().items.filter(p=>p.id!==id)});
      usePipelineSetup.getState().remove(id);
      if(get().selected===id){set({selected:null});remember(null);useControl.setState({running:null,editor:null});useViewer.getState().setRunTag(null);}
      return true;
    }catch(e){set({error:`Could not delete pipeline: ${String(e)}`});return false;}
    finally{set({busy:false});}
  },
  playAll:async()=>{
    if(get().busy||get().pendingStart||get().stoppingAll||get().startingAll||!get().loaded||!get().items.length)return;
    cancelBulkStart=false;
    set({busy:true,startingAll:true,startOutcomes:[],error:null});
    bulkStart=(async()=>{
      try{
        await saveQueue;
        const outcomes=await startPipelines([...get().items],async(item,resume)=>{
          const url=resume?`/control/runs/${encodeURIComponent(item.running!.run_tag)}/resume`:'/control/runs';
          const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(resume?{}:{pipeline_id:item.id}),signal:AbortSignal.timeout(15000)});
          const run=await response.json();
          if(!response.ok)throw Error(run.error||`Request failed (${response.status})`);
          set(s=>({items:s.items.map(p=>p.id!==item.id?p:resume?{...p,running:p.running?{...p.running,pause_requested:false,execution_state:'running'}:null}:{...p,running:run,latest:run,progress:{}})}));
        },()=>cancelBulkStart);
        set({startOutcomes:outcomes});
      }catch(e){set({error:`Could not start pipelines: ${String(e)}`});}
      finally{set({busy:false,startingAll:false});}
    })();
    try{await bulkStart;}finally{bulkStart=null;void get().poll();}
  },
  play:async (id,options)=>{
    if(get().busy||get().pendingStart||get().stoppingAll)return false;
    const previousTag=get().items.find(p=>p.id===id)?.latest?.run_tag??null;
    set({busy:true,error:null});
    try{await saveQueue;const response=await fetch('/control/runs',{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(15000),body:JSON.stringify({pipeline_id:id,...(options?{execution_mode:options.mode,additional_loops:options.loops,expected_run_tag:options.expectedRunTag}:{})})});
      const run=await response.json();if(!response.ok)throw new Error(run.error);
      set({items:get().items.map(p=>p.id===id?{...p,running:run,latest:run,progress:{}}:p)});get().select(id);return true;
    }catch(e){
      // A lost response is not a rejected start. Reconcile with a new run for
      // this pipeline before allowing another start or dismissing the notice.
      const uncertain=e instanceof TypeError || (e instanceof DOMException && (e.name==='TimeoutError'||e.name==='AbortError'));
      set({error:uncertain?delayedStartMessage:String(e),pendingStart:uncertain?{pipelineId:id,previousTag}:null});
      return false;
    }finally{set({busy:false});void get().poll();}
  },
  pause:async(id,paused)=>{
    const pipeline=get().items.find(p=>p.id===id);
    const run=pipeline?.running||(!paused&&pipeline?.latest?.recoverable?pipeline.latest:null);if(!run||get().busy)return;
    set({busy:true,error:null});
    try{const r=await fetch(`/control/runs/${encodeURIComponent(run.run_tag)}/${paused?'pause':'resume'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error((await r.json()).error);}
    catch(e){set({error:String(e)});}finally{set({busy:false});void get().poll();}
  },
  stopAll:async()=>{
    if(get().stoppingAll)return;
    cancelBulkStart=true;
    set({stoppingAll:true,error:null});
    try{await bulkStart;const r=await fetch('/control/stop-all',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(10000)});
      const body=await r.json();if(!r.ok)throw Error(body.error||'Stop all failed');
      if(body.errors?.length)throw Error(body.errors.map((e:{pipeline:string;error:string})=>`${e.pipeline}: ${e.error}`).join('; '));
    }catch(e){set({error:String(e)});}finally{set({stoppingAll:false});void get().poll();}
  },
  end:async (id,expectedRunTag)=>{
    const run=get().items.find(p=>p.id===id)?.running;if(!run||get().busy)return false;
    if(expectedRunTag && run.run_tag!==expectedRunTag){set({error:'The execution changed. Review the current execution before ending it.'});return false;}
    set({busy:true,error:null});
    try{const r=await fetch(`/control/runs/${encodeURIComponent(run.run_tag)}/end`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error((await r.json()).error);return true;}
    catch(e){set({error:String(e)});return false;}finally{set({busy:false});void get().poll();}
  },
  stop:async id=>{
    const run=get().items.find(p=>p.id===id)?.running;if(!run || get().busy)return;set({busy:true,error:null});
    try{const response=await fetch(`/control/runs/${encodeURIComponent(run.run_tag)}/stop`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw new Error((await response.json()).error);
    }catch(e){set({error:String(e)});}finally{set({busy:false});}
  },
}));
