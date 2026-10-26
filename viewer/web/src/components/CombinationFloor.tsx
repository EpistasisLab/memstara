import { skillLabel } from '../lib/displayText';
import {floorCallRole as callRole, floorCallStatus, floorStageProcessing} from '../lib/floorActivity';
import {useMemo, useCallback, useState, useEffect, useRef, type CSSProperties} from 'react';
import {createPortal} from 'react-dom';
import {ReactFlow, useReactFlow, useStore, getViewportForBounds, Background, BackgroundVariant, Controls, Handle, Position, MarkerType, type NodeProps, type Node} from '@xyflow/react';
import {Sparkles, Database, BrainCircuit, ScanEye, FileText, ExternalLink} from 'lucide-react';
import {PLAYBOOK_STAGES, type PlaybookStage} from '../store/control';
import {STAGE_COLOR} from '../lib/stage';
import '@xyflow/react/dist/style.css';
import './combination-floor.css';

type Skill={id:string;title?:string;hash?:string;stage:PlaybookStage};
type Call={stage:string;status:string;skill?:Skill};
const EMPTY_CALLS:Call[]=[];
type RoomData={role:PlaybookStage;skills:Skill[];selected?:string;status?:string;processing:boolean;recorded:boolean;inspect:(s:Skill)=>void};
const labels={hypothesis:'Hypothesis',data:'Data',ml:'Machine learning',interpreter:'Interpretation',report:'Explanation'};
const icons={hypothesis:Sparkles,data:Database,ml:BrainCircuit,interpreter:ScanEye,report:FileText};
const descriptions={hypothesis:'Ask a testable question',data:'Map the selected features',ml:'Evaluate the prediction',interpreter:'Describe the evidence',report:'Explain its meaning'};
function Room({data}:NodeProps<Node<RoomData>>){
 const Icon=icons[data.role];
 const active=data.status==='Running'||data.processing;
 return <div className={`cf-room ${data.recorded?'is-recorded':''} ${active?'cf-active-room':''}`} style={{'--role-color':STAGE_COLOR[data.role]} as CSSProperties}>
  <header><span className="cf-room-icon"><Icon size={23}/></span><div><small>Stage {PLAYBOOK_STAGES.indexOf(data.role)+1}</small><h4>{labels[data.role]}</h4></div></header>
  {active&&<div className="cf-stage-running" role="status" aria-label={`${labels[data.role]} stage is ${data.processing?'processing':'running'}`}><span aria-hidden="true"/>{data.processing?'Stage in progress':'Running now'}</div>}
  <p className="cf-room-purpose">{descriptions[data.role]}</p>
  {data.status==='Call still open'&&<p className="cf-room-purpose">Call not yet returned. Main-task activity is not confirmed.</p>}
  <div className="cf-desks">{data.skills.map((s,i)=><div className={`cf-desk ${data.selected===s.id?'is-selected':data.recorded?'cf-unused':''}`} key={s.id}>
   <Handle type="target" position={Position.Left} id={`in-${i}`} isConnectable={false}/>
   <div className="cf-skill-label"><span className="cf-orbit"><Icon size={17}/></span><span><small>{data.recorded?(data.selected===s.id?'Selected for this Replicate':'Other variant'):`Variant ${i+1}`}</small><strong>{skillLabel(s.id,s.title)}</strong></span></div>
   <button className="cf-inspect nodrag" aria-label={`Inspect ${skillLabel(s.id,s.title)} instructions`} onClick={()=>data.inspect(s)}><ExternalLink size={14}/></button>
   <Handle type="source" position={Position.Right} id={`out-${i}`} isConnectable={false}/>
  </div>)}</div>
  {active&&<div className="cf-running-track" aria-hidden="true"><span/><span/><span/></div>}
  <footer>{data.recorded?<span className={`cf-status ${active?'is-running':''}`}>{data.processing?(data.status==='Completed'?'Call completed · stage in progress':'Preparing agent call'):(data.status??'No call recorded')}</span>:<span>{data.skills.length} configured {data.skills.length===1?'skill':'skills'}</span>}</footer>
 </div>;
}
const nodeTypes={room:Room};
const fitOptions={padding:{top:'24px',bottom:'48px',left:'24px',right:'24px'},minZoom:.05,maxZoom:1,duration:0} as const;
function Navigation({host}:{host:HTMLDivElement|null}){
 const {getNodes,getNodesBounds,getViewport,setViewport}=useReactFlow();
 const element=useStore(s=>s.domNode);
 const geometry=useStore(s=>Array.from(s.nodeLookup.values()).map(n=>`${n.id}:${n.measured.width}:${n.measured.height}`).join('|'));
 const [focus,setFocus]=useState('all');
 const initiallyFitted=useRef(false);
 const fit=useCallback((id:string)=>{
  if(!element)return;
  const {width,height}=element.getBoundingClientRect();
  if(!width||!height)return;
  const nodes=getNodes().filter(n=>id==='all'||n.id===id);
  if(!nodes.length)return;
  const next=getViewportForBounds(getNodesBounds(nodes),width,height,.05,1,fitOptions.padding);
  const current=getViewport();
  if(Math.abs(current.x-next.x)<.1&&Math.abs(current.y-next.y)<.1&&Math.abs(current.zoom-next.zoom)<.0001)return;
  void setViewport(next,{duration:0});
 },[element,getNodes,getNodesBounds,getViewport,setViewport]);
 useEffect(()=>{
  if(initiallyFitted.current||!element)return;
  const nodes=getNodes();
  if(!nodes.length||nodes.some(n=>!n.measured?.width||!n.measured?.height))return;
  const frame=requestAnimationFrame(()=>{
   if(!element.clientWidth||!element.clientHeight)return;
   fit('all');initiallyFitted.current=true;
  });
  return()=>cancelAnimationFrame(frame);
 },[element,geometry,fit,getNodes]);
 return host ? createPortal(<div className="cf-navigation"><label>Go to agent <select aria-label="Focus floor plan agent" value={focus} onChange={e=>{setFocus(e.target.value);fit(e.target.value);}}><option value="all">Overview</option>{PLAYBOOK_STAGES.map(s=><option key={s} value={s}>{labels[s]}</option>)}</select></label><button onClick={()=>{setFocus('all');fit('all');}}>Fit all</button><span>Drag to explore · + / − to zoom</span></div>,host) : null;
}

export default function CombinationFloor({skills,inspect,recorded=false,calls=EMPTY_CALLS,activeSkills,live=false,paused=false,stale=false,stopping=false,currentStage}:{skills:Skill[][];inspect:(s:Skill)=>void;recorded?:boolean;calls?:Call[];activeSkills?:Skill[];live?:boolean;paused?:boolean;stale?:boolean;stopping?:boolean;currentStage?:string}){
 const [navigationHost,setNavigationHost]=useState<HTMLDivElement|null>(null);
 const contentKey=JSON.stringify(skills);
 const callsKey=JSON.stringify(calls);
 const lastCalls=PLAYBOOK_STAGES.map(role=>calls.filter(c=>callRole(c)===role).at(-1));
 const chosen=skills.map((s,i)=>recorded?(lastCalls[i]?.skill?.id??activeSkills?.find(a=>a.stage===PLAYBOOK_STAGES[i])?.id??(activeSkills===undefined&&s.length===1?s[0]?.id:undefined)):undefined);
 const {nodes,edges}=useMemo(()=>{
  const nodes:Node<RoomData>[]=PLAYBOOK_STAGES.map((role,i)=>({id:role,type:'room',position:{x:i*340,y:38},draggable:false,data:{role,skills:skills[i],selected:chosen[i],recorded,processing:floorStageProcessing(role,lastCalls[i],{stale,paused,stopping,live,currentStage}),status:floorCallStatus(lastCalls[i],{stale,paused,stopping,live,currentStage}),inspect}}));
  const edges=PLAYBOOK_STAGES.slice(0,-1).flatMap((role,i)=>{
   const from=skills[i].findIndex(s=>s.id===chosen[i]),to=skills[i+1].findIndex(s=>s.id===chosen[i+1]);
   if(from<0||to<0)return [];
   const observed=recorded&&!!lastCalls[i]&&!!lastCalls[i+1];
   return [{id:`${role}-route`,source:role,target:PLAYBOOK_STAGES[i+1],sourceHandle:`out-${from}`,targetHandle:`in-${to}`,type:'smoothstep',animated:observed&&floorCallStatus(lastCalls[i+1],{live,paused,stopping,stale,currentStage})==='Running',className:observed?'cf-observed-edge':'cf-planned-edge',style:{stroke:STAGE_COLOR[role],strokeWidth:observed?3:2,strokeDasharray:observed?undefined:'6 5'},markerEnd:{type:MarkerType.ArrowClosed,color:STAGE_COLOR[role]},pathOptions:{borderRadius:20}}];
  });return {nodes,edges};
 },[contentKey,chosen.join('|'),recorded,callsKey,inspect,live,paused,stopping,stale,currentStage]);
 return <div className="cf-floor-shell">
  <div className="cf-navigation-dock" ref={setNavigationHost}/>

  <div className="cf-map" role="region" aria-label={recorded?'Recorded combination floor plan':'Configured combination floor plan'}>
   <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} minZoom={.05} maxZoom={1.4} nodesConnectable={false} nodesDraggable={false} elementsSelectable={false} panOnScroll zoomOnScroll={false} preventScrolling={false} proOptions={{hideAttribution:true}}>
    <Navigation host={navigationHost}/><Background variant={BackgroundVariant.Lines} gap={32} color="var(--cf-grid)" size={.5}/><Controls showInteractive={false} fitViewOptions={fitOptions}/>
   </ReactFlow>
  </div>

 </div>;
}
