import { useCallback, useEffect, useMemo, useState } from "react";
import { ReactFlow, Background, BackgroundVariant, MarkerType, useNodesState, useReactFlow, useNodesInitialized, useStore as useFlowStore, getViewportForBounds, type NodeProps, type Node } from "@xyflow/react";
import { Plus, Play, Square, Trash2, Layers3, Activity, Pause, Sparkles, Settings2, X } from "lucide-react";
import { usePipelines, type PipelineDefinition } from "../store/pipelines";
import { useControl, type PlaybookStage } from "../store/control";
import { AgentNode, nodeTypes as floorNodeTypes } from "../components/nodes";
import { useViewer } from "../store/viewer";
import { STAGE_COLOR } from "../lib/stage";
import "./floor-plan.css";
import KnowledgeNode from "../components/KnowledgeNode";
import PipelineViewport from "../components/PipelineViewport";
import ResourceEdge from "../components/ResourceEdge";
import { pipelinePercent } from "../lib/pipelineProgress";
import type { SceneAgent } from "../types";
import PipelineSetupGuide from "../components/PipelineSetupGuide";
import PipelineNameEditor from "../components/PipelineNameEditor";
import PipelineSettings from "../components/PipelineSettings";
import { setupStages, skillSignature, usePipelineSetup } from "../store/pipelineSetup";
import "@xyflow/react/dist/style.css";

const stages = ['source','hypothesis','data','ml','interpreter','report'] as const;
const labels = {source:'Knowledge source',hypothesis:'Hypothesis',data:'Data',ml:'Machine learning',interpreter:'Interpreter',report:'Report'};
type StationData = {pipeline: PipelineDefinition; stage: typeof stages[number]; inspect: () => void; selected: boolean};
function Station(props: NodeProps<Node<StationData>>) {
  const {pipeline,stage}=props.data;
  const busy=usePipelines(s=>s.busy);
  const selected=usePipelines(s=>s.selected);
  const review=usePipelineSetup(s=>s.reviews[pipeline.id]);
  const guided=selected===pipeline.id&&review&&!review.paused&&
    setupStages.find(s=>review.confirmed?.[s]!==skillSignature(pipeline.configuration,s))===stage;
  const active=!!pipeline.running && !pipeline.running.waiting_for_questions && pipeline.progress.stage===stage;

  if(stage==='source') return <KnowledgeNode {...props} data={{
    compact:true,value:pipeline.configuration.skill,locked:!!pipeline.running||busy,saved:false,
    description:"Evidence used by this pipeline's hypothesis agent.",
    onChange:(skill:string)=>usePipelines.getState().save(pipeline.id,{...pipeline.configuration,skill})
  }}/>;
  const book=stage==='data'?'':pipeline.configuration[`playbook_${stage}`];
  const agent: SceneAgent={
    id:`${pipeline.id}-${stage}`,stage,label:labels[stage],slot:0,
    name:`${pipeline.name} · ${labels[stage]}`,worker:null,playbook:book,
    running:active?1:0,state:active?'working':pipeline.latest?'idle':'planned',
    at:null,home:{x:0,y:0},carrying:null,run_id:null,since:null,last_tool:null,windows:[],
  };
  return <AgentNode {...props} data={{
    agent,step:stages.indexOf(stage),selected:props.data.selected,inspect:props.data.inspect,guided,
  }}/>;

}
function PipelineFocus(){
  const selected=usePipelines(s=>s.selected);
  const focusRevision=usePipelines(s=>s.focusRevision);
  const initialized=useNodesInitialized();
  const domNode=useFlowStore(s=>s.domNode);
  const {getNodes,getNodesBounds,setViewport}=useReactFlow();
  useEffect(()=>{
    if(!selected||!initialized||!domNode)return;
    const center=()=>{
      const nodes=getNodes().filter(n=>n.id===`zone-${selected}`||n.id.startsWith(selected+"-"));
      if(!nodes.length)return;
      const canvas=domNode.getBoundingClientRect();
      let left=Math.max(canvas.left,0),top=Math.max(canvas.top,0);
      let right=Math.min(canvas.right,window.innerWidth),bottom=Math.min(canvas.bottom,window.innerHeight);
      for(let parent=domNode.parentElement;parent;parent=parent.parentElement){
        const style=getComputedStyle(parent),r=parent.getBoundingClientRect();
        if(/auto|scroll|hidden|clip/.test(style.overflowX)){left=Math.max(left,r.left+parent.clientLeft);right=Math.min(right,r.left+parent.clientLeft+parent.clientWidth);}
        if(/auto|scroll|hidden|clip/.test(style.overflowY)){top=Math.max(top,r.top+parent.clientTop);bottom=Math.min(bottom,r.top+parent.clientTop+parent.clientHeight);}
      }
      if(right<=left||bottom<=top)return;
      const viewport=getViewportForBounds(getNodesBounds(nodes),right-left,bottom-top,.1,1,.18);
      void setViewport({...viewport,x:viewport.x+left-canvas.left,y:viewport.y+top-canvas.top},
        {duration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:250});
    };
    // Wait for layout and the initial overview positioning before applying selection.
    let frame=requestAnimationFrame(center);
    const observer=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(center);});
    for(let parent:HTMLElement|null=domNode;parent;parent=parent.parentElement)observer.observe(parent);
    return ()=>{cancelAnimationFrame(frame);observer.disconnect();};
  },[selected,focusRevision,initialized,domNode,getNodes,getNodesBounds,setViewport]);
  return null;
}
const nodeTypes={...floorNodeTypes,station:Station};
const edgeTypes={resource:ResourceEdge};
export function PipelineStatus(){
  const pipelines=usePipelines(s=>s.items),selected=usePipelines(s=>s.selected);
  const shortLabels=['Hypothesis','Data','ML','Interpretation','Report'];
  return <section aria-label="Pipeline status" className="pipeline-status-section">
    <header className="pipeline-status-heading">
      <div><h2>Pipeline progress</h2><p>Each research path advances independently.</p></div>
      <span title="Five equally weighted stages per iteration. This is not a time estimate.">Stage-based progress</span>
    </header>
    {!pipelines.length?<p className="text-sm text-ink-faint">Add a pipeline to see its progress here.</p>:
    <div className="pipeline-progress-list">{pipelines.map(p=>{
      const index=stages.indexOf(p.progress.stage as typeof stages[number])-1;
      const waiting=!!p.running?.waiting_for_questions;
      const failed=(p.progress.counts?.failed??0)>0;
      const percent=pipelinePercent(p);
      const status=failed?'Needs attention':waiting?'Waiting for knowledge':p.running?'Running':p.latest?(p.latest.exit_code===0?'Completed':'Stopped'):'Ready';
      const current=index>=0?shortLabels[index]:'Not started';
      return <article key={p.id} className={`pipeline-progress-card ${selected===p.id?'is-selected':''} ${failed?'needs-attention':''}`}>
        <header className="pipeline-progress-header">
          <button className="pipeline-progress-identity" onClick={()=>usePipelines.getState().select(p.id)}>
            <span className="pipeline-number">P{p.number}</span>
            <span><strong>{p.name}</strong><span className="pipeline-cycle">Iteration {p.progress.iteration??'—'}</span></span>
          </button>
          <div className="pipeline-progress-value" title="Stage-based progress in this iteration, not elapsed time">
            <strong>{percent??'—'}{percent!=null&&<small>%</small>}</strong><span>of this iteration</span>
          </div>
        </header>
        <div className="pipeline-progress-context">
          <span className="pipeline-current-stage">{current}</span>
          <span className="pipeline-state"><i className={p.running&&!waiting&&!failed?'is-live':''}/>{status}</span>
        </div>
        <div className="pipeline-stage-track" role="progressbar" aria-label={`${p.name} stage-based progress`}
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent??undefined}
          aria-valuetext={`${current}, iteration ${p.progress.iteration??'not started'}. ${status}. Not a time estimate.`}>
          {shortLabels.map((label,i)=><div key={label} className={`pipeline-track-stage ${i===index?'is-current':''} ${i<index||percent===100?'is-past':''}`}>
            <span className="pipeline-track-line">{i===index&&percent!==100&&<i/>}</span><span className="pipeline-track-label">{label}</span>
          </div>)}
        </div>
        <footer className="pipeline-progress-footer">
          <span>{failed?'An analysis step failed; review Results.':waiting?'Waiting before the next attempt.':p.running?'Following the latest observed stage.':'Progress is retained when execution stops.'}</span>
          <time>{p.progress.updated_at?new Date(p.progress.updated_at).toLocaleTimeString():'No activity yet'}</time>
        </footer>
      </article>;
    })}</div>}
  </section>;
}
export function PipelineOverview(){
  const pipelines=usePipelines(s=>s.items),select=usePipelines(s=>s.select);
  return <div className="space-y-2 p-3">{pipelines.length?pipelines.map(p=><button key={p.id} onClick={()=>select(p.id)} className="block w-full rounded-lg border border-paper-line p-3 text-left text-sm text-ink">
    <strong className="block">{p.name}</strong><span className="text-xs text-ink-soft">Pipeline {p.number} · Iteration {p.progress.iteration??'—'} · {p.running?'Active':'Idle'}</span>
  </button>):<p className="text-sm text-ink-faint">No pipelines yet.</p>}</div>;
}
export default function PipelineWorkspace(){
  const {items,selected,loaded,busy,error,add,remove,play,stop,select}=usePipelines();
  const documents=useControl(s=>s.bundle?.documents);
  const [deleting,setDeleting]=useState<string|null>(null);
  const [expanded,setExpanded]=useState(false);
  const [toolbarHost,setToolbarHost]=useState<HTMLDivElement|null>(null);
  const [motion,setMotion]=useState(true);
  const [showTools,setShowTools]=useState(true);
  const [inspected,setInspected]=useState<{id:string;stage:string}|null>(null);
  const [settings,setSettings]=useState<{id:string;section:'runtime'|'data'}|null>(null);
  const configureStation=useCallback((id:string,stage:string)=>{
    select(id);
    setInspected({id,stage});
    if(stage==='data')setSettings({id,section:'data'});
    if(['hypothesis','ml','interpreter','report'].includes(stage))
      useControl.getState().openEditor(stage as PlaybookStage);
  },[select]);
  const snapshot=useViewer(s=>s.snapshot);
  const focused=items.find(p=>p.id===inspected?.id&&p.id===selected);
  const places=useMemo(()=>[
    {id:'okf',label:'Knowledge',sub:`${documents??'—'} documents`},
    {id:'matcher',label:'Feature matching',sub:'Semantic mappings'},
    {id:'dataset',label:'Research dataset',sub:'Fixed target'},
    {id:'ml',label:'ML tools',sub:'Models & evaluation'},
    {id:'board',label:'Blackboard',sub:'Tasks & coordination'},
    {id:'results',label:'Results',sub:'Evidence & reports'},
  ],[documents]);
  useEffect(()=>{void usePipelines.getState().poll();},[]);
  const [nodes,setNodes,onNodesChange]=useNodesState<Node>([]);
  useEffect(()=>{
    setNodes(previous=>{
      const definitions:Node[]=[
        {id:'resources-zone',type:'zone',position:{x:0,y:0},zIndex:-2,selectable:false,
          data:{title:'Resources',caption:'Knowledge · Data · Tools',width:1370,height:146}},
        ...places.map((place,i)=>({id:`place-${place.id}`,type:'place',position:{x:24+i*224,y:48},data:{place,...(place.id==='dataset'&&selected?{activate:()=>setSettings({id:selected,section:'data'}),actionLabel:'Configure data and target for the selected pipeline'}:{})}})),
        ...items.flatMap((p,row)=>[
          {id:`zone-${p.id}`,type:'zone',position:{x:0,y:172+row*252},zIndex:-2,selectable:false,
            data:{title:`PIPELINE ${p.number} · ${p.name}`,caption:`Iteration ${p.progress.iteration??'—'} · ${p.running?'Running':'Ready'}`,width:1370,height:196,execution:true,selected:p.id===selected,onSelect:()=>select(p.id),number:p.number,iteration:p.progress.iteration,stageIndex:stages.indexOf(p.progress.stage as typeof stages[number])-1,percent:pipelinePercent(p),stageLabel:labels[p.progress.stage as keyof typeof labels]??"Not started",failed:(p.progress.counts?.failed??0)>0}},
          ...stages.map((stage,col)=>({id:`${p.id}-${stage}`,type:'station',position:{x:24+col*224,y:224+row*252},
            data:{pipeline:p,stage,selected:selected===p.id&&inspected?.id===p.id&&inspected?.stage===stage,
              inspect:()=>configureStation(p.id,stage)}})),
        ]),
      ];
      return definitions.map(node=>({...previous.find(old=>old.id===node.id),...node}));
    });
  },[items,inspected,selected,places,setNodes,select,configureStation]);
  const edges=useMemo(()=>{
    const routes=items.flatMap(p=>stages.slice(1).map((stage,i)=>({
      id:`${p.id}-${stage}`,source:`${p.id}-${stages[i]}`,sourceHandle:i===0?undefined:'flow',target:`${p.id}-${stage}`,
      type:'smoothstep',className:'floor-route-edge',markerEnd:{type:MarkerType.ArrowClosed,color:'#b8c5d1'},
      style:{stroke:'#b8c5d1',strokeWidth:1.6},
    })));
    if(!showTools || !snapshot) return routes;
    // Only actual observations from the selected run produce animated resource links.
    const owner=items.find(p=>p.latest?.run_tag===snapshot.run_tag);
    if(!owner || snapshot.stale) return routes;
    const seen=new Set<string>();
    const tools=snapshot.scene.flashes.flatMap(f=>{
      const agent=snapshot.scene.agents.find(a=>a.id===f.agent);
      if(!agent || agent.stage==='curator' || seen.has(agent.stage) || !places.some(p=>p.id===f.place))return [];
      seen.add(agent.stage);
      return [{id:`tool-${owner.id}-${agent.stage}`,source:`${owner.id}-${agent.stage}`,sourceHandle:'tool',target:`place-${f.place}`,
        type:'resource',className:'floor-tool-edge',animated:motion,label:`P${owner.number} · ${f.tool}`,data:{lane:stages.indexOf(agent.stage)-1},
        style:{stroke:STAGE_COLOR[agent.stage],strokeWidth:2},markerEnd:{type:MarkerType.ArrowClosed,color:STAGE_COLOR[agent.stage]}}];
    });
    return [...routes,...tools];
  },[items,snapshot,showTools,motion,places]);
  return <div className={`floor-observatory flex h-full min-h-0 flex-col overflow-y-auto bg-paper ${motion?"":"floor-still"} ${expanded?"fixed inset-3 z-50 rounded-xl border border-paper-line shadow-xl":""}`}>
    {settings&&<PipelineSettings key={settings.id+settings.section} id={settings.id} section={settings.section} close={()=>setSettings(null)}/>}
    <header className="floor-toolbar">
      <div className="floor-title"><span className="floor-emblem"><Layers3 size={18}/></span>
        <div><div className="floor-eyebrow">MEMSTARA / SPATIAL VIEW</div><h3>Research workspace</h3></div></div>
      <div className="floor-actions">
        <span className="floor-live"><Activity size={12}/>{items.filter(p=>p.running).length} running</span>
        <button aria-pressed={showTools} onClick={()=>setShowTools(v=>!v)}><Layers3 size={13}/>Tool activity</button>
        <button aria-label={motion?'Pause flow animation':'Resume flow animation'} aria-pressed={motion} onClick={()=>setMotion(v=>!v)}>{motion?<Pause size={13}/>:<Play size={13}/>}</button>
        <button disabled={!loaded||busy||items.length>=3} onClick={()=>void add()}><Plus size={15}/>Add Pipeline {items.length}/3</button>
      </div>
    </header>
    {error&&<p role="alert" className="m-3 rounded border border-red-300 p-2 text-sm text-red-700">{error}</p>}
    {items.length>0&&<div className="flex flex-wrap gap-2 px-4 pb-3">{items.map(p=><div key={p.id} className={`pipeline-selector relative flex flex-wrap items-center gap-1 rounded-lg border p-2 ${selected===p.id?'border-accent':'border-paper-line'}`}>
      <button className="absolute inset-0 rounded-lg hover:bg-accent/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent" aria-label={`Center ${p.name} in Floor Plan`} aria-pressed={selected===p.id} onClick={()=>usePipelines.getState().focus(p.id)}/>
      <span className="pointer-events-none relative rounded px-2 text-xs font-bold text-ink">P{p.number}</span>
      <PipelineNameEditor pipeline={p}/>
      <span className="px-1 text-xs text-ink-faint">Iteration {p.progress.iteration??'—'}</span>
      <button aria-label={`Settings for ${p.name}`} title="Pipeline language model settings" onClick={()=>{select(p.id);setSettings({id:p.id,section:'runtime'});}} className="rounded border border-paper-line p-2 text-ink"><Settings2 size={14}/></button>
      {p.running?.pause_requested&&<button disabled={busy} aria-label={`Resume ${p.name}`} onClick={()=>{select(p.id);void useControl.getState().pauseRun(false);}} className="rounded border border-paper-line p-2 text-ink"><Play size={14}/>Resume</button>}
      <button disabled={busy} aria-label={`${p.running?'Stop':'Play'} ${p.name}`} onClick={()=>void(p.running?stop(p.id):play(p.id))} className="rounded border border-paper-line p-2 text-ink">{p.running?<Square size={14}/>:<Play size={14}/>}</button>
      <button disabled={busy||!!p.running} aria-label={`Remove ${p.name}`} onClick={()=>setDeleting(p.id)} className="rounded p-2 text-ink-faint disabled:opacity-30"><Trash2 size={14}/></button>
      {deleting===p.id&&<div className="w-full text-xs text-ink-soft">Remove this pipeline setup? Saved results remain.<div className="mt-1 flex gap-2"><button onClick={()=>setDeleting(null)}>Cancel</button><button className="text-red-600" onClick={()=>{void remove(p.id);setDeleting(null);}}>Remove pipeline</button></div></div>}
    </div>)}</div>}
    <PipelineSetupGuide/>
    <div ref={setToolbarHost} className="floor-docked-controls" role="group" aria-label="Floor Plan view controls"/>
    <div className="floor-canvas min-h-[460px] shrink-0" style={{height:Math.max(490,items.length*252+240)}}>
      <ReactFlow nodes={nodes} onNodesChange={onNodesChange} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
        defaultViewport={{x:16,y:60,zoom:1}} minZoom={.1} maxZoom={1.6} nodesDraggable={false} nodesConnectable={false}
        panOnScroll zoomOnScroll={false} onNodeClick={(_,node)=>{if(node.type==="station"){const p=node.data.pipeline as PipelineDefinition;configureStation(p.id,String(node.data.stage));}}} onPaneClick={()=>setInspected(null)}>
        <Background className="pipeline-background" variant={BackgroundVariant.Dots} gap={20} size={.65} color="#dfe6eb"/>
        <PipelineViewport entryId="resources-zone" leftGutter={96} dockInto={toolbarHost} expanded={expanded} toggle={()=>setExpanded(v=>!v)} topology={items.map(p=>p.id).join(",")}/><PipelineFocus/>
      </ReactFlow>
    </div>
    <div className="floor-inspector" aria-live="polite">
      <div className="floor-inspector-icon"><Sparkles size={18}/></div>
      <div className="floor-inspector-copy">
        <strong>{focused&&inspected?`${focused.name} · ${labels[inspected.stage as keyof typeof labels]}`:'One view. Independent research paths.'}</strong>
        <p>{focused&&inspected?(inspected.stage==='data'?'Extract selected features from the configured dataset.':`Skill: ${focused.configuration[`playbook_${inspected.stage}` as keyof typeof focused.configuration]??'Choose knowledge on the source card'}`):items.length?'Select an agent to inspect its skill and configure this pipeline.':'Your resources are ready. Add a pipeline to build your first research path.'}</p>
        <p>Tool activity shows recent observations for the selected run.</p>
      </div>
      {focused&&inspected&&['hypothesis','ml','interpreter','report'].includes(inspected.stage)&&
        <button className="floor-details" disabled={!!focused.running||busy} onClick={()=>{select(focused.id);useControl.getState().openEditor(inspected.stage as PlaybookStage);}}><Settings2 size={14}/>Configure</button>}
      {inspected&&<button className="floor-close" aria-label="Clear agent selection" onClick={()=>setInspected(null)}><X size={15}/></button>}
    </div>
    <PipelineStatus/>
  </div>;
}
