import type {FloorActivity} from '../lib/floorActivity';
import {createPortal} from "react-dom";
import {WorkspaceHeaderContext} from "../components/WorkspaceHeaderContext";
import PipelineRowActions from "../components/PipelineRowActions";
import MasterStop from "../components/MasterStop";
import CombinationDesign from '../components/CombinationDesign';
import PipelineBrowser from "../components/PipelineBrowser";
import ClinicalLogPanel from "../components/ClinicalLogPanel";
import { floorCallDestination, floorCallCategory } from "../lib/floorCallDestination";
import FloorDatabaseNode from "../components/FloorDatabaseNode";
import LoopUsage from "../components/LoopUsage";
import { useTelemetryTotals } from "../components/TelemetryTotals";
import { useContext, useCallback, useEffect, useMemo, useState } from "react";
import { ReactFlow, Controls, Background, BackgroundVariant, MarkerType, useNodesState, useReactFlow, useNodesInitialized, useStore as useFlowStore, getViewportForBounds, type NodeProps, type Node } from "@xyflow/react";
import { Plus, Activity, Sparkles, Settings2, X } from "lucide-react";
import { usePipelines, type PipelineDefinition } from "../store/pipelines";
import { useControl, type PlaybookStage } from "../store/control";
import { AgentNode, nodeTypes as floorNodeTypes } from "../components/nodes";
import { useViewer } from "../store/viewer";
import { STAGE_COLOR } from "../lib/stage";
import "./floor-plan.css";
import "./floor-responsive.css";
import KnowledgeNode from "../components/KnowledgeNode";
import PipelineViewport from "../components/PipelineViewport";
import ResourceEdge from "../components/ResourceEdge";
import { pipelinePercent, pipelineLoopLabel } from "../lib/pipelineProgress";
import type { SceneAgent } from "../types";
import FloorDetailDialog from "../components/FloorDetailDialog";
import PipelineSettings from "../components/PipelineSettings";
import { setupStages, skillSignature, usePipelineSetup } from "../store/pipelineSetup";
import "@xyflow/react/dist/style.css";

const stages = ['source','hypothesis','data','ml','interpreter','report'] as const;
const labels = {source:'Knowledge source',hypothesis:'Hypothesis',data:'Data',ml:'Machine learning',interpreter:'Interpreter',report:'Explanation'};
type StationData = {pipeline: PipelineDefinition; stage: typeof stages[number]; inspect: () => void; selected: boolean};
function Station(props: NodeProps<Node<StationData>>) {
  const {pipeline,stage}=props.data;
  const busy=usePipelines(s=>s.busy);
  const selected=usePipelines(s=>s.selected);
  const review=usePipelineSetup(s=>s.reviews[pipeline.id]);
  const guided=selected===pipeline.id&&review&&!review.paused&&
    setupStages.find(s=>review.confirmed?.[s]!==skillSignature(pipeline.configuration,s))===stage;
  const active=!!pipeline.running && pipeline.running.execution_state!=='paused' && !pipeline.running.waiting_for_questions && pipeline.progress.stage===stage;

  if(stage==='source') return <KnowledgeNode {...props} data={{
    compact:true,value:pipeline.configuration.skill,locked:!!pipeline.running||busy,saved:false,
    description:"Evidence used by this pipeline's hypothesis agent.",
    onChange:(skill:string)=>usePipelines.getState().save(pipeline.id,{...pipeline.configuration,skill})
  }}/>;
  const book=stage==='data'?'':pipeline.configuration[`playbook_${stage === "report" ? "explanation" : stage}`];
  const agent: SceneAgent={
    id:`${pipeline.id}-${stage}`,stage,label:labels[stage],slot:0,
    name:`${pipeline.name} · ${labels[stage]}`,worker:null,playbook:book,
    running:active?1:0,state:active?'working':pipeline.latest?'idle':'planned',
    at:null,home:{x:0,y:0},carrying:null,run_id:null,since:null,last_tool:null,windows:[],
  };
  return <AgentNode {...props} data={{
    agent,step:stages.indexOf(stage),selected:props.data.selected,inspect:props.data.inspect,guided,
    roleSummary:stage==='hypothesis'?'Propose & map features':stage==='data'?'Extract selected features':stage==='ml'?'Train & evaluate models':undefined,
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
      // Focus the selected research path; shared resources have their own overview.
      const nodes=getNodes().filter(n=>n.id.startsWith(selected+"-"));
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
      const pathBounds=getNodesBounds(nodes);
      const viewport=getViewportForBounds(pathBounds,right-left,bottom-top,.85,1,.12);
      // Prefer readable cards and a clear starting point over shrinking every label.
      if(pathBounds.width*viewport.zoom>right-left-32)viewport.x=16-pathBounds.x*viewport.zoom;
      void setViewport({...viewport,x:viewport.x+left-canvas.left,y:viewport.y+top-canvas.top},
        {duration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:250});
    };
    // Wait for layout and the initial overview positioning before applying selection.
    let frame=requestAnimationFrame(center);
    // User pan/zoom survives resize and auxiliary-panel changes.
    return ()=>cancelAnimationFrame(frame);
  },[selected,focusRevision,initialized,domNode,getNodes,getNodesBounds,setViewport]);
  return null;
}
const nodeTypes={...floorNodeTypes,station:Station,database:FloorDatabaseNode};
const edgeTypes={resource:ResourceEdge};
export function PipelineStatus({ids}: {ids?: string[]} = {}){
  const usage=useTelemetryTotals();
  const pipelines=usePipelines(s=>s.items),selected=usePipelines(s=>s.selected);
  const shortLabels=['Hypothesis','Data','ML','Interpretation','Explanation'];
  return <section aria-label="Pipeline status" className="pipeline-status-section">
    <header className="pipeline-status-heading">
      <div><h2>Pipeline progress</h2><p>Each research path advances independently.</p></div>
      <span title="Five equally weighted stages per loop. This is not a time estimate.">Stage-based progress</span>
    </header>
    {!pipelines.length?<p className="text-sm text-ink-faint">Add a pipeline to see its progress here.</p>:
    <div className="pipeline-progress-list">{pipelines.filter(p=>!ids||ids.includes(p.id)).map(p=>{
      const index=stages.indexOf(p.progress.stage as typeof stages[number])-1;
      const waiting=!!p.running?.waiting_for_questions;
      const failed=(p.progress.counts?.failed??0)>0 || p.progress.exploration?.outcome === "blocked";
      const percent=pipelinePercent(p);
      const status=p.running?.pause_requested?(p.running.execution_state==='paused'?'Stopped':'Stopping'):failed?'Needs attention':waiting?'Waiting for knowledge':p.running?'Running':p.latest?(p.latest.exit_code===0?'Completed':'Stopped'):'Ready';
      const current=index>=0?shortLabels[index]:'Not started';
      return <article key={p.id} className={`pipeline-progress-card ${selected===p.id?'is-selected':''} ${failed?'needs-attention':''}`}>
        <header className="pipeline-progress-header">
          <button className="pipeline-progress-identity" onClick={()=>usePipelines.getState().select(p.id)}>
            <span className="pipeline-number">P{p.number}</span>
            <span><strong>{p.name}</strong><span className="pipeline-cycle" data-help="Loop" tabIndex={0}>{pipelineLoopLabel(p)}</span></span>
          </button>
          <div className="pipeline-progress-value" data-help="Stage-based progress" tabIndex={0} title="Stage-based progress in this loop, not elapsed time">
            <strong>{percent??'—'}{percent!=null&&<small>%</small>}</strong><span>of this loop</span>
          </div>
        </header>
        {p.progress.exploration && <p className="text-xs text-ink-soft" role="status">
          {p.progress.exploration.attempted} loops · {p.progress.exploration.completed} completed · {p.progress.exploration.blocked} blocked
        </p>}
        <div className="pipeline-progress-context">
          <span className="pipeline-current-stage">{current}</span>
          <span className="pipeline-state"><i className={p.running&&p.running.execution_state!=='paused'&&!waiting&&!failed?'is-live':''}/>{status}</span>
        </div>
        <div className="pipeline-stage-track" role="progressbar" aria-label={`${p.name} stage-based progress`}
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent??undefined}
          aria-valuetext={`${current}, loop ${p.progress.iteration??'not started'}. ${status}. Not a time estimate.`}>
          {shortLabels.map((label,i)=><div key={label} className={`pipeline-track-stage ${i===index?'is-current':''} ${i<index||percent===100?'is-past':''}`}>
            <span className="pipeline-track-line">{i===index&&percent!==100&&<i/>}</span><span className="pipeline-track-label">{label}</span>
          </div>)}
        </div>
        <LoopUsage execution={usage.data?.executions.find(e=>e.run_tag===p.latest?.run_tag)} updatedAt={usage.data?.updated_at} error={usage.error}/>
        <footer className="pipeline-progress-footer">
          <span>{(p.running?.pause_requested?'Progress is preserved. Resume continues this execution.':'') || p.progress.exploration?.reason || (failed?'An analysis step failed; review Results.':waiting?'Waiting before the next loop.':p.running?'Following the latest observed stage.':'Progress is retained when execution stops.')}</span>
          <time>{p.progress.updated_at?new Date(p.progress.updated_at).toLocaleTimeString():'No activity yet'}</time>
        </footer>
      </article>;
    })}</div>}
  </section>;
}
export default function PipelineWorkspace(){
  const {items,selected,loaded,busy,error,add,select}=usePipelines();
  const [comparison,setComparison]=useState<string[]>([]);
  const visibleItems=useMemo(()=>comparison.length?items.filter(p=>comparison.includes(p.id)):items.filter(p=>p.id===(selected??items[0]?.id)),[items,comparison,selected]);
  useEffect(()=>{setComparison(ids=>ids.every(id=>items.some(p=>p.id===id))?ids:ids.filter(id=>items.some(p=>p.id===id)));},[items]);
  useEffect(()=>{if(loaded&&items.length&&!items.some(p=>p.id===selected))select(items[0].id);},[loaded,items,selected,select]);
  const documents=useControl(s=>s.bundle?.documents);
  const [expanded,setExpanded]=useState(false);
  const [showResources,setShowResources]=useState(false);
  const [detail,setDetail]=useState<"progress"|"agent"|"tools"|null>(null);
  const workspaceHeader=useContext(WorkspaceHeaderContext);
  const [combinationHeader,setCombinationHeader]=useState<HTMLDivElement|null>(null);
  const [toolbarHost,setToolbarHost]=useState<HTMLDivElement|null>(null);
  const motion = true;
  const showTools = true;
  const technical = true;
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
  const [floorActivity,setFloorActivity]=useState<FloorActivity|null>(null);
  const combinationPipeline=comparison.length?undefined:items.find(p=>p.id===selected&&Object.keys(p.configuration.combination_skills??{}).length>0);
  const selectedPipeline=items.find(p=>p.id===selected);
  const focused=items.find(p=>p.id===inspected?.id&&p.id===selected);
  const allPlaces=useMemo(()=>[
    {id:'okf',label:'Knowledge sources',sub:`${documents??'—'} available documents`},
    {id:'dataset',label:'Research dataset',sub:'Data and prediction target'},
    {id:'matcher',label:'Column mapping',sub:'Clinical concepts → columns'},
    {id:'ml',label:'Model execution',sub:'Training and evaluation'},
    {id:'board',label:'Blackboard',sub:'Tasks, progress and intermediate information'},
    {id:'results',label:'Results',sub:'Analysis outcomes and findings'},
  ],[documents]);
  const places=useMemo(()=>technical?allPlaces:allPlaces.slice(0,2),[allPlaces,technical]);
  const observedOwner=visibleItems.find(p=>p.latest?.run_tag===snapshot?.run_tag);
  const observedCalls=observedOwner&&!snapshot?.stale?snapshot?.scene.flashes??[]:[];
  useEffect(()=>{void usePipelines.getState().poll();},[]);
  const [nodes,setNodes,onNodesChange]=useNodesState<Node>([]);
  useEffect(()=>{
    setNodes(previous=>{
      const definitions:Node[]=[
        {id:'resources-zone',type:'zone',position:{x:0,y:0},zIndex:-2,selectable:false,
          data:{title:'Research inputs',caption:'Knowledge & data',width:440,height:174}},
        ...(technical?[
          {id:'mapping-zone',type:'zone',position:{x:448,y:0},zIndex:-2,selectable:false,data:{title:'Column mapping',caption:'',width:216,height:174}},
          {id:'model-zone',type:'zone',position:{x:672,y:0},zIndex:-2,selectable:false,data:{title:'Model execution',caption:'',width:216,height:174}},
          {id:'storage-zone',type:'database',position:{x:896,y:0},selectable:false,data:{}},
        ]:[]),
        ...places.map((place,i)=>{
          const table=place.id==='board'||place.id==='results';
          return {id:`place-${place.id}`,type:'place',
            ...(table?{parentId:'storage-zone',extent:'parent' as const}:{}),
            position:table?{x:place.id==='board'?16:246,y:66}:{x:16+i*224,y:60},
            data:{place,table,...(place.id==='dataset'&&selected?{activate:()=>setSettings({id:selected,section:'data'}),actionLabel:'Configure data and target for the selected pipeline'}:{})}};
        }),
        ...visibleItems.flatMap((p,row)=>[
          {id:`zone-${p.id}`,type:'zone',position:{x:0,y:208+row*252},zIndex:-2,selectable:false,
            data:{title:`PIPELINE ${p.number} · ${p.name}`,caption:`${pipelineLoopLabel(p)} · ${p.progress.exploration?`${p.progress.exploration.completed} completed · ${p.progress.exploration.blocked} blocked`:p.running?'Running':'Ready'}`,width:1370,height:196,execution:true,selected:p.id===selected,onSelect:()=>select(p.id),number:p.number,iteration:p.progress.iteration,loopLabel:pipelineLoopLabel(p),stageIndex:stages.indexOf(p.progress.stage as typeof stages[number])-1,percent:pipelinePercent(p),stageLabel:labels[p.progress.stage as keyof typeof labels]??"Not started",failed:(p.progress.counts?.failed??0)>0||p.progress.exploration?.outcome==='blocked'}},
          ...stages.map((stage,col)=>({id:`${p.id}-${stage}`,type:'station',position:{x:24+col*224,y:260+row*252},
            data:{pipeline:p,stage,selected:selected===p.id&&inspected?.id===p.id&&inspected?.stage===stage,
              inspect:()=>configureStation(p.id,stage)}})),
        ]),
      ];
      return definitions.map(node=>({...previous.find(old=>old.id===node.id),...node}));
    });
  },[visibleItems,inspected,selected,places,technical,setNodes,select,configureStation]);
  const edges=useMemo(()=>{
    const routes=visibleItems.flatMap(p=>stages.slice(1).map((stage,i)=>({
      id:`${p.id}-${stage}`,source:`${p.id}-${stages[i]}`,sourceHandle:i===0?undefined:'flow',target:`${p.id}-${stage}`,
      type:'smoothstep',className:'floor-route-edge',markerEnd:{type:MarkerType.ArrowClosed,color:'#b8c5d1'},
      style:{stroke:'#b8c5d1',strokeWidth:1.6},
    })));
    if(!showTools || !snapshot) return routes;
    // Only actual observations from the selected run produce animated resource links.
    const owner=visibleItems.find(p=>p.latest?.run_tag===snapshot.run_tag);
    if(!owner || snapshot.stale) return routes;
    const seen=new Set<string>();
    const tools=snapshot.scene.flashes.flatMap(f=>{
      const agent=snapshot.scene.agents.find(a=>a.id===f.agent);
      const destination=floorCallDestination(f.tool,f.place);
      if(!agent || agent.stage==='curator' || seen.has(agent.stage) || !destination || (destination==='database'?!technical:!places.some(p=>p.id===destination)))return [];
      seen.add(agent.stage);
      return [{id:`tool-${owner.id}-${agent.stage}`,source:`${owner.id}-${agent.stage}`,sourceHandle:'tool',target:destination==='database'?'storage-zone':`place-${destination}`,
        type:'resource',className:'floor-tool-edge',animated:motion,label:`P${owner.number} · ${f.tool}`,data:{lane:stages.indexOf(agent.stage)-1},
        style:{stroke:STAGE_COLOR[agent.stage],strokeWidth:2},markerEnd:{type:MarkerType.ArrowClosed,color:STAGE_COLOR[agent.stage]}}];
    });
    return [...routes,...tools];
  },[visibleItems,snapshot,showTools,motion,places,technical]);
  const canvasNodes=showResources?nodes:nodes.filter(n=>visibleItems.some(p=>n.id===`zone-${p.id}`||n.id.startsWith(p.id+"-")));
  const canvasIds=new Set(canvasNodes.map(n=>n.id));
  const canvasEdges=edges.filter(e=>canvasIds.has(e.source)&&canvasIds.has(e.target));
  const header=<div className="pipeline-unified-header" role="group" aria-label="Pipeline workspace header">
    <div ref={setCombinationHeader} className="pipeline-context-header"/>
    {!combinationPipeline&&<div className="pipeline-context-title"><strong>{comparison.length?'Compare pipelines':selectedPipeline?.name??'Research pipelines'}</strong><span>{comparison.length?`${comparison.length} selected`:'Floor plan'}</span></div>}
    <div className="pipeline-global-actions" role="group" aria-label="Controls for all pipelines">
      <span className="pipeline-running-count" data-help="Running pipelines" data-help-description="Number of pipelines currently executing. Paused pipelines are excluded; this is not the number of Loops or combinations." tabIndex={0} title="Pipelines currently executing; paused pipelines are excluded"><Activity size={13}/>{items.filter(p=>p.running&&p.running.execution_state!=='paused').length} running</span>
      <MasterStop/>
      <button className="pipeline-add-primary" data-help="Add pipeline" data-help-description={items.length>=3?"The maximum of 3 pipelines has been reached. Delete one before creating another.":"Open the setup wizard to choose knowledge sources, agent skills, execution limits and a pipeline name. Creating a pipeline does not start it."} disabled={!loaded||busy||items.length>=3} title={items.length>=3?'Maximum of 3 pipelines reached. Delete a pipeline to create another.':'Create a pipeline and choose its sources, agents and skills'} onClick={()=>void add()}><Plus size={17}/><span>Add pipeline</span></button>
    </div>
  </div>;
  return <div className={`floor-observatory flex h-full min-h-0 flex-col overflow-hidden bg-paper ${motion?"":"floor-still"} ${expanded?"fixed inset-3 z-50 rounded-xl border border-paper-line shadow-xl":""}`}>
    {settings&&<PipelineSettings key={settings.id+settings.section} id={settings.id} section={settings.section} close={()=>setSettings(null)}/>}
    {workspaceHeader?createPortal(header,workspaceHeader):header}
    {error&&<p role="alert" className="m-3 rounded border border-red-300 p-2 text-sm text-red-700">{error}</p>}
    <div className="pipeline-explorer-layout">
      <PipelineBrowser onSettings={id=>{select(id);setSettings({id,section:"runtime"});}} items={items} selected={selected} onSelect={id=>{if(comparison.length&&!comparison.includes(id))setComparison([]);usePipelines.getState().focus(id);}} compare={comparison} onCompare={ids=>{setComparison(ids);if(ids.length&&!ids.includes(selected??""))usePipelines.getState().focus(ids[0]);}}/>
      <div className={`pipeline-detail-workspace ${combinationPipeline||comparison.length?"has-combination-studio":""}`}>
      {selectedPipeline&&<div className="floor-compact-actions" aria-label="Selected pipeline controls"><strong title={selectedPipeline.name}>{selectedPipeline.name}</strong><PipelineRowActions compact pipeline={selectedPipeline} onSettings={()=>setSettings({id:selectedPipeline.id,section:"runtime"})}/></div>}
    {comparison.length>0&&<div className="floor-comparison-heading" role="status"><strong>Comparing {visibleItems.length} pipelines</strong><span>Each pipeline keeps its own visualization, Loop and execution state. Pan and zoom each view independently.</span></div>}
    {comparison.length>0&&<div className="floor-comparison-grid">{visibleItems.map(p=>{
      const isCombination=Object.keys(p.configuration.combination_skills??{}).length>0;
      const ownNodes=nodes.filter(n=>n.id.startsWith(p.id+"-"));
      const ids=new Set(ownNodes.map(n=>n.id));const ownEdges=edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
      return <section className="floor-comparison-pane" key={p.id} aria-label={`Comparison · ${p.name}`}>
       <header className="floor-comparison-pane-heading"><strong>{p.name}</strong><span>{isCombination?'All Combinations':'Selected pipeline'} · Loop {p.progress.iteration??'—'} · {p.running?(p.running.execution_state==='paused'?'Paused':labels[p.progress.stage as keyof typeof labels]??'Running'):'Not running'}</span></header>
       {isCombination?<CombinationDesign pipeline={p}/>:<div className="floor-comparison-standard"><ReactFlow nodes={ownNodes} edges={ownEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{padding:.12}} minZoom={.15} maxZoom={1.6} nodesDraggable={false} nodesConnectable={false} panOnScroll zoomOnScroll={false} onNodeClick={(_,node)=>{if(node.type==='station')configureStation(p.id,String(node.data.stage));}}><Background variant={BackgroundVariant.Lines} gap={32} color="rgb(var(--ink) / .05)"/><Controls showInteractive={false}/></ReactFlow></div>}
      </section>;
    })}</div>}
    {combinationPipeline&&<CombinationDesign key={combinationPipeline.id} pipeline={combinationPipeline} headerHost={combinationHeader} onActivity={setFloorActivity}/>}
    <div className="floor-detail-links"><button aria-pressed={showResources} title="Show shared knowledge, data, tools and storage alongside the pipeline" onClick={()=>setShowResources(v=>!v)}>Shared resources</button><button onClick={()=>setDetail('tools')}>Recent tool calls</button><button onClick={()=>setDetail('progress')}>Pipeline progress</button>{focused&&inspected&&<button onClick={()=>setDetail('agent')}>Selected agent details</button>}</div>
    <div ref={setToolbarHost} className="floor-docked-controls floor-visible-controls" role="group" aria-label="Floor Plan view controls"/>
    {!combinationPipeline&&!comparison.length&&<div className="floor-canvas">
      <ReactFlow nodes={canvasNodes} onNodesChange={onNodesChange} edges={canvasEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
        defaultViewport={{x:16,y:60,zoom:1}} minZoom={.1} maxZoom={1.6} nodesDraggable={false} nodesConnectable={false}
        panOnScroll zoomOnScroll={false} onNodeClick={(_,node)=>{if(node.type==="station"){const p=node.data.pipeline as PipelineDefinition;configureStation(p.id,String(node.data.stage));}}} onPaneClick={()=>setInspected(null)}>
        <Background className="pipeline-background" variant={BackgroundVariant.Dots} gap={20} size={.65} color="#dfe6eb"/>
        <PipelineViewport entryId="resources-zone" leftGutter={96} dockInto={toolbarHost} expanded={expanded} toggle={()=>setExpanded(v=>!v)} allowExpand={false} topology={visibleItems.map(p=>p.id).join(",")+":"+showResources}/><PipelineFocus/>
      </ReactFlow>
    </div>}
    {detail==='agent'&&<FloorDetailDialog title="Selected agent details" close={()=>setDetail(null)}><div className="floor-inspector" aria-live="polite">
      <div className="floor-inspector-icon"><Sparkles size={18}/></div>
      <div className="floor-inspector-copy">
        <strong>{focused&&inspected?`${focused.name} · ${labels[inspected.stage as keyof typeof labels]}`:'One view. Independent research paths.'}</strong>
        <p>{focused&&inspected?(inspected.stage==='data'?'Extract the columns already selected for this hypothesis. Concept-to-column matching is a tool available to the hypothesis agent; it is not a separate input dataset.':`${inspected.stage==='hypothesis'?'Propose a testable hypothesis and map clinical concepts to available columns. ':inspected.stage==='ml'?'Train and evaluate models using the configured model tools. ':''}Skill: ${focused.configuration[`playbook_${inspected.stage === "report" ? "explanation" : inspected.stage}` as keyof typeof focused.configuration]??'Choose knowledge on the source card'}`):items.length?'Select an agent to inspect its skill and configure this pipeline.':'Your resources are ready. Add a pipeline to build your first research path.'}</p>
        <p>Tool activity shows recent tool-call categories for the selected execution, not exact SQL reads or writes.</p>
      </div>
      {focused&&inspected&&['hypothesis','ml','interpreter','report'].includes(inspected.stage)&&
        <button className="floor-details" disabled={!!focused.running||busy} onClick={()=>{setDetail(null);select(focused.id);useControl.getState().openEditor(inspected.stage as PlaybookStage);}}><Settings2 size={14}/>Configure</button>}
      {inspected&&<button className="floor-close" aria-label="Clear agent selection" onClick={()=>setInspected(null)}><X size={15}/></button>}
    </div>
    </FloorDetailDialog>}
    {detail==='tools'&&<FloorDetailDialog title="Recent tool calls" close={()=>setDetail(null)}>
      <div className="floor-tool-observations">
        <p>Observed calls from the selected pipeline's latest execution. This is a recent activity window, not the full history. Hidden categories are included here. Categories come from tool names; a call may touch multiple tables. These arrows are not a database audit or proof of data movement.</p>
        <details><summary>How to read the diagram</summary><ul>
          <li><strong>Research inputs</strong><span>Knowledge documents and a configured dataset. The source card inside each pipeline selects its knowledge; the shared catalog count is not that pipeline's selected document count.</span></li>
          <li><strong>Column mapping</strong><span>A hypothesis-agent tool that returns candidate columns for clinical concepts. It does not train a model or establish clinical validity. The data agent extracts the selected columns.</span></li>
          <li><strong>Model execution</strong><span>Tools used to train and evaluate the configured ML model. This is a capability, not another dataset or an extra agent.</span></li>
          <li><strong>Memstara DB</strong><span>Blackboard and Results are selected tables in the same application database. Question records also live there. Results holds analysis outcomes used by reporting, not every report artifact. Motoro execution history is stored separately.</span></li>
          <li><strong>Connections</strong><span>Pipeline arrows show stage order. Tool-activity arrows show recent calls, grouped by tool category. For example, submit_result can update the task board and insert a completed result; question tools use question records. These calls point to the DB container rather than a falsely specific table.</span></li>
        </ul></details>
        <p>{observedOwner?`Pipeline: ${observedOwner.name}`:'No matching execution selected.'}{snapshot?.stale?' Live activity is currently unavailable.':''}</p>
        {observedCalls.length?<ul>{observedCalls.map((call,i)=><li key={`${call.agent}-${call.at}-${i}`}><strong>{call.agent} → {call.tool}</strong><span>{floorCallCategory(call.tool,call.place)} · {call.server}</span><time>{call.at}</time></li>)}</ul>:<p>No recent calls observed. This does not mean the pipeline has never used a tool.</p>}
        <button onClick={()=>{setDetail(null);useViewer.getState().setView('agents');}}>Open Telemetry for history</button>
      </div>
    </FloorDetailDialog>}
    {detail==='progress'&&<FloorDetailDialog title="Pipeline progress" close={()=>setDetail(null)}><PipelineStatus ids={visibleItems.map(p=>p.id)}/></FloorDetailDialog>}
      </div>
      <ClinicalLogPanel pipelines={visibleItems} floorActivity={combinationPipeline && floorActivity?.pipelineId===combinationPipeline.id && floorActivity.runTag===(combinationPipeline.running??combinationPipeline.latest)?.run_tag ? floorActivity : null}/>
    </div>
  </div>;
}
