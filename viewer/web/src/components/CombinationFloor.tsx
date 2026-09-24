import {useMemo, useCallback, useState, useEffect, type CSSProperties} from 'react';
import {ReactFlow, Panel, useReactFlow, useStore, getViewportForBounds, Background, BackgroundVariant, Controls, Handle, Position, MarkerType, type NodeProps, type Node} from '@xyflow/react';
import {Sparkles, Database, BrainCircuit, ScanEye, FileText, ExternalLink} from 'lucide-react';
import {PLAYBOOK_STAGES, type PlaybookStage} from '../store/control';
import {STAGE_COLOR} from '../lib/stage';
import '@xyflow/react/dist/style.css';
import './combination-floor.css';

type Skill={id:string;title?:string;hash?:string;stage:PlaybookStage};
type Call={stage:string;status:string;skill?:Skill};
const EMPTY_CALLS:Call[]=[];
const callRole=(c:Call)=>c.skill?.stage??(c.stage.startsWith('question')?'hypothesis':c.stage.startsWith('interpret')?'interpreter':PLAYBOOK_STAGES.find(s=>c.stage.startsWith(s)));
const pending=(s?:string)=>s==='started'||s==='running';
type RoomData={role:PlaybookStage;skills:Skill[];selected?:string;status?:string;recorded:boolean;onSelect:(id:string)=>void;inspect:(s:Skill)=>void};
const labels={hypothesis:'Hypothesis',data:'Data',ml:'Machine learning',interpreter:'Interpretation',report:'Explanation'};
const icons={hypothesis:Sparkles,data:Database,ml:BrainCircuit,interpreter:ScanEye,report:FileText};
const descriptions={hypothesis:'Ask a testable question',data:'Map the selected features',ml:'Evaluate the prediction',interpreter:'Describe the evidence',report:'Explain its meaning'};
function Room({data}:NodeProps<Node<RoomData>>){
 const Icon=icons[data.role];
 return <div className={`cf-room ${data.recorded?'is-recorded':''} ${data.status==='Running'?'cf-active-room':''}`} style={{'--role-color':STAGE_COLOR[data.role]} as CSSProperties}>
  <header><span className="cf-room-icon"><Icon size={23}/></span><div><small>Stage {PLAYBOOK_STAGES.indexOf(data.role)+1}</small><h4>{labels[data.role]}</h4></div></header>
  {data.status==='Running'&&<div className="cf-stage-running" role="status" aria-label={`${labels[data.role]} stage is running`}><span aria-hidden="true"/>Running now</div>}
  <p className="cf-room-purpose">{descriptions[data.role]}</p>
  <div className="cf-desks">{data.skills.map((s,i)=><div className={`cf-desk ${data.selected===s.id?'is-selected':data.recorded?'cf-unused':''}`} key={s.id}>
   <Handle type="target" position={Position.Left} id={`in-${i}`} isConnectable={false}/>
   <button className="cf-select nodrag" aria-label={`Preview ${s.title??s.id}`} aria-pressed={data.selected===s.id} disabled={data.recorded} onClick={()=>data.onSelect(s.id)}><span className="cf-orbit"><Icon size={17}/></span><span><small>{data.recorded?(data.selected===s.id?'Selected for this Loop':'Other variant'):`Variant ${i+1}`}</small><strong>{s.title??s.id}</strong></span></button>
   <button className="cf-inspect nodrag" aria-label={`Inspect ${s.title??s.id} instructions`} onClick={()=>data.inspect(s)}><ExternalLink size={14}/></button>
   <Handle type="source" position={Position.Right} id={`out-${i}`} isConnectable={false}/>
  </div>)}</div>
  {data.status==='Running'&&<div className="cf-running-track" aria-hidden="true"><span/><span/><span/></div>}
  <footer>{data.recorded?<span className={`cf-status ${data.status==='Running'?'is-running':''}`}>{data.status??'No call recorded'}</span>:<span>{data.skills.length} skill {data.skills.length===1?'variant':'variants'} · choose one to trace</span>}</footer>
 </div>;
}
const nodeTypes={room:Room};
const fitOptions={padding:{top:'80px',bottom:'48px',left:'24px',right:'24px'},minZoom:.05,maxZoom:1,duration:0} as const;
function Navigation(){
 const {getNodes,getNodesBounds,getViewport,setViewport}=useReactFlow();
 const element=useStore(s=>s.domNode);
 const geometry=useStore(s=>Array.from(s.nodeLookup.values()).map(n=>`${n.id}:${n.measured.width}:${n.measured.height}`).join('|'));
 const [focus,setFocus]=useState('all');
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
  if(!element)return;
  let frame=0;
  const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>fit(focus));};
  const observer=new ResizeObserver(schedule);
  observer.observe(element);schedule();
  return()=>{observer.disconnect();cancelAnimationFrame(frame);};
 },[element,geometry,focus,fit]);
 return <Panel position="top-left" className="cf-navigation"><label>Go to agent <select aria-label="Focus floor plan agent" value={focus} onChange={e=>setFocus(e.target.value)}><option value="all">Overview</option>{PLAYBOOK_STAGES.map(s=><option key={s} value={s}>{labels[s]}</option>)}</select></label><button onClick={()=>{setFocus('all');fit('all');}}>Fit all</button><span>Drag to explore · + / − to zoom</span></Panel>;
}

export default function CombinationFloor({skills,inspect,recorded=false,calls=EMPTY_CALLS,activeSkills,live=false,paused=false,stale=false}:{skills:Skill[][];inspect:(s:Skill)=>void;recorded?:boolean;calls?:Call[];activeSkills?:Skill[];live?:boolean;paused?:boolean;stale?:boolean}){
 const [selection,setSelection]=useState<Record<string,string>>({});
 const contentKey=JSON.stringify(skills);
 const callsKey=JSON.stringify(calls);
 const signature=skills.map(s=>s.map(a=>a.id).join('|')).join(';');
 useEffect(()=>setSelection({}),[signature,recorded]);
 const lastCalls=PLAYBOOK_STAGES.map(role=>calls.filter(c=>callRole(c)===role).at(-1));
 const chosen=skills.map((s,i)=>recorded?(lastCalls[i]?.skill?.id??activeSkills?.find(a=>a.stage===PLAYBOOK_STAGES[i])?.id??(activeSkills===undefined&&s.length===1?s[0]?.id:undefined)):(s.find(a=>a.id===selection[PLAYBOOK_STAGES[i]])?.id??s[0]?.id));
 const {nodes,edges}=useMemo(()=>{
  const nodes:Node<RoomData>[]=PLAYBOOK_STAGES.map((role,i)=>({id:role,type:'room',position:{x:i*340,y:38},draggable:false,data:{role,skills:skills[i],selected:chosen[i],recorded,status:pending(lastCalls[i]?.status)?(stale?'Last recorded: running':paused?'Paused':live?'Running':'Last recorded: running'):(lastCalls[i]?.status==='completed'?'Completed':lastCalls[i]?.status??'Waiting · no call recorded'),onSelect:id=>setSelection(s=>({...s,[role]:id})),inspect}}));
  const edges=PLAYBOOK_STAGES.slice(0,-1).flatMap((role,i)=>{
   const from=skills[i].findIndex(s=>s.id===chosen[i]),to=skills[i+1].findIndex(s=>s.id===chosen[i+1]);
   if(from<0||to<0)return [];
   const observed=recorded&&!!lastCalls[i]&&!!lastCalls[i+1];
   return [{id:`${role}-route`,source:role,target:PLAYBOOK_STAGES[i+1],sourceHandle:`out-${from}`,targetHandle:`in-${to}`,type:'smoothstep',animated:observed&&live&&pending(lastCalls[i+1]?.status),className:observed?'cf-observed-edge':'cf-preview-edge',style:{stroke:STAGE_COLOR[role],strokeWidth:observed?3:2,strokeDasharray:observed?undefined:'6 5'},markerEnd:{type:MarkerType.ArrowClosed,color:STAGE_COLOR[role]},pathOptions:{borderRadius:20}}];
  });return {nodes,edges};
 },[contentKey,chosen.join('|'),recorded,callsKey,inspect,live,paused,stale]);
 return <div className="cf-floor-shell">

  <div className="cf-map" role="region" aria-label={recorded?'Recorded combination floor plan':'Interactive combination floor plan'}>
   <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={fitOptions} minZoom={.05} maxZoom={1.4} nodesConnectable={false} nodesDraggable={false} elementsSelectable={false} panOnScroll zoomOnScroll={false} preventScrolling={false} proOptions={{hideAttribution:true}}>
    <Navigation/><Background variant={BackgroundVariant.Lines} gap={32} color="var(--cf-grid)" size={.5}/><Controls showInteractive={false} fitViewOptions={fitOptions}/>
   </ReactFlow>
  </div>

 </div>;
}
