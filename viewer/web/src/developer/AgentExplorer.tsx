import {useEffect, useMemo, useReducer, useState, useSyncExternalStore} from 'react';
import {ReactFlow, Background, Controls, BaseEdge, getBezierPath, MarkerType, Position, type EdgeProps, type Edge, type Node} from '@xyflow/react';
import {BookOpen, Bot, Database, FileBox, Globe, Network, Pause, Play, RotateCcw, SkipBack, SkipForward, ArrowRight, Maximize2, Focus, Code2, Eye} from 'lucide-react';
import {actors, scenarios, type ComponentKind} from './agentStories';
import './agent-explorer.css';
import PipelineNarrative from './PipelineNarrative';
import HypothesisLesson from './HypothesisLesson';

const byId=new Map(actors.map(actor=>[actor.id,actor]));
const colors:Record<ComponentKind,string>={source:'#e7bf75',tool:'#b49afa',runtime:'#8dacf8',agent:'#66d8bc',database:'#e69db8',ui:'#7bcbdc'};
const icons={source:FileBox,tool:Network,runtime:Globe,agent:Bot,database:Database,ui:Eye};
const labels={source:'Knowledge & files',tool:'Tool servers',runtime:'Runtime & API',agent:'Agents',database:'Databases',ui:'Interface'};
const reducedQuery=matchMedia('(prefers-reduced-motion: reduce)');
const narrowQuery=matchMedia('(max-width: 700px)');
const reducedSubscribe=(fn:()=>void)=>{reducedQuery.addEventListener('change',fn);return()=>reducedQuery.removeEventListener('change',fn);};
const narrowSubscribe=(fn:()=>void)=>{narrowQuery.addEventListener('change',fn);return()=>narrowQuery.removeEventListener('change',fn);};
type TourState={scenario:number;index:number;playing:boolean};
type Action={type:'play'|'pause'|'next'|'previous'|'restart'}|{type:'select';index:number}|{type:'scenario';scenario:number};
function reducer(state:TourState,action:Action):TourState{
 const last=scenarios[state.scenario].steps.length-1;
 switch(action.type){
  case 'play':return {...state,index:state.index===last?0:state.index,playing:true};
  case 'pause':return {...state,playing:false};
  case 'next':return {...state,index:Math.min(last,state.index+1),playing:state.index<last&&state.playing};
  case 'previous':return {...state,index:Math.max(0,state.index-1),playing:false};
  case 'restart':return {...state,index:0,playing:false};
  case 'select':return {...state,index:Math.max(0,Math.min(last,action.index)),playing:false};
  case 'scenario':return {scenario:action.scenario,index:0,playing:false};
 }
}
function TransferEdge(props:EdgeProps){
 const [path,labelX,labelY]=getBezierPath(props);
 const active=Boolean(props.data?.moving);
 return <><BaseEdge path={path} markerEnd={props.markerEnd} style={{stroke:'#69dbc2',strokeWidth:3}}/>
  {props.data?.showLabel&&<g className="transfer-label" transform={`translate(${labelX},${labelY-18})`}><rect x="-74" y="-12" width="148" height="24" rx="12"/><text textAnchor="middle" y="4">{String(props.data?.label??'Transfer')}</text></g>}
  {active?<circle key={String(props.data?.step)} r="6" fill="#e6fff8" className="transfer-packet"><animateMotion dur={`${2/Number(props.data?.speed??1)}s`} repeatCount="indefinite" path={path}/></circle>:<circle cx={labelX} cy={labelY} r="5" fill="#69dbc2"/>}
 </>;
}
const edgeTypes={transfer:TransferEdge};
function TechnicalAgentExplorer({onSource,onRecords}:{onSource:(path:string)=>void;onRecords:()=>void}){
 const [state,dispatch]=useReducer(reducer,{scenario:0,index:0,playing:false});
 const [speed,setSpeed]=useState(1),[focus,setFocus]=useState(false),[inspected,setInspected]=useState<string|null>(null);
 const reduced=useSyncExternalStore(reducedSubscribe,()=>reducedQuery.matches);
 const narrow=useSyncExternalStore(narrowSubscribe,()=>narrowQuery.matches);
 const [allowMotion,setAllowMotion]=useState(true);
 const scenario=scenarios[state.scenario],step=scenario.steps[state.index];
 const selected=byId.get(inspected??step.owner)!;
 const from=byId.get(step.fromId)!,to=byId.get(step.toId)!;
 const focused=focus||narrow;
 const moving=state.playing&&allowMotion&&!reduced;
 useEffect(()=>{if(!state.playing)return;const id=setTimeout(()=>dispatch({type:'next'}),5500/speed);return()=>clearTimeout(id);},[state.playing,state.index,state.scenario,speed]);
 useEffect(()=>{const stop=()=>{if(document.hidden)dispatch({type:'pause'});};document.addEventListener('visibilitychange',stop);return()=>document.removeEventListener('visibilitychange',stop);},[]);
 const graph=useMemo(()=>{
  const shown=focused?[from,to]:actors;
  const dx=focused?(narrow?0:360):to.x-from.x,dy=focused?(narrow?190:0):to.y-from.y;
  const vertical=Math.abs(dy)>Math.abs(dx);
  const sourceSide=vertical?(dy>0?Position.Bottom:Position.Top):(dx>0?Position.Right:Position.Left);
  const targetSide=vertical?(dy>0?Position.Top:Position.Bottom):(dx>0?Position.Left:Position.Right);
  const nodes:Node[]=shown.map((actor,i)=>{const Icon=icons[actor.kind];const active=actor.id===from.id||actor.id===to.id;
   return {id:actor.id,position:focused?{x:narrow?0:i*360,y:narrow?i*190:0}:{x:actor.x,y:actor.y},sourcePosition:actor.id===from.id?sourceSide:Position.Right,targetPosition:actor.id===to.id?targetSide:Position.Left,
    data:{label:<div><span className="actor-kind"><Icon size={15}/>{labels[actor.kind]}</span><b>{actor.name}</b><small>{actor.subtitle}</small>{active&&<em>{actor.id===from.id?'SENDING':'RECEIVING'}</em>}</div>},className:`agent-map-node ${active?'active':''} ${actor.id===selected.id?'inspected':''}`,style:{'--actor-color':colors[actor.kind]} as React.CSSProperties};});
  const edges:Edge[]=[{id:'active-transfer',source:from.id,target:to.id,type:'transfer',data:{moving,label:step.operation,step:step.id,speed,showLabel:focused},markerEnd:{type:MarkerType.ArrowClosed,color:'#69dbc2',width:18,height:18}}];
  return {nodes,edges};
 },[focused,from,to,narrow,selected.id,moving,step.operation,step.id,speed]);
 const go=(index:number)=>{dispatch({type:'select',index});setInspected(null);};
 return <section className="agent-explorer" aria-label="Animated Agent Explorer">
  <div className="agent-heading"><div><p className="eyebrow">AGENT EXPLORER / FOLLOW THE INFORMATION</p><h2>From knowledge to evidence.</h2><p>Explore the agents, tools and stores behind a research investigation.</p></div><span className="tour-badge"><BookOpen size={15}/> Educational walkthrough</span></div>
  <div className="tour-disclosure">Illustrative sequence · no model calls or database writes · animation speed is not execution time. Real tasks can overlap; this tour follows one logical investigation.</div>
  <div className="tour-topbar"><label>Explore a scenario<select aria-label="Tour scenario" value={state.scenario} onChange={e=>{dispatch({type:'scenario',scenario:Number(e.target.value)});setInspected(null);}}>{scenarios.map((s,i)=><option value={i} key={s.id}>{s.name}</option>)}</select></label><p>{scenario.caption}</p><button className="record-jump" onClick={onRecords}><Eye size={16}/> Inspect recorded execution <ArrowRight size={15}/></button></div>
  <div className="agent-role-tabs" aria-label="Agent roles">{actors.filter(a=>a.kind==='agent').map(a=><button key={a.id} aria-pressed={selected.id===a.id} onClick={()=>{dispatch({type:'pause'});setInspected(a.id);}}><Bot size={15}/>{a.name}</button>)}</div>
  <div className="agent-tour-grid"><div className="tour-map-column">
   <div className="map-toolbar"><div><span className={`play-dot ${moving?'moving':''}`}/><b>{state.playing?'Walkthrough playing':'Walkthrough paused'}</b><small>{state.index+1} / {scenario.steps.length}</small></div><button aria-pressed={focused} disabled={narrow} onClick={()=>setFocus(v=>!v)}>{focused?<Maximize2 size={15}/>:<Focus size={15}/>} {narrow?'Mobile transfer view':focused?'Show full system':'Focus transfer'}</button></div>
   <div className={`agent-map ${focused?'focused':''}`}><ReactFlow key={focused?`focus-${step.id}-${narrow}`:'full'} nodes={graph.nodes} edges={graph.edges} edgeTypes={edgeTypes} fitView fitViewOptions={{padding:.17,maxZoom:1.1}} minZoom={.25} maxZoom={1.8} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_,node)=>{dispatch({type:'pause'});setInspected(node.id);}} colorMode="dark" proOptions={{hideAttribution:true}}><Background gap={22} color="#20374b"/><Controls showInteractive={false}/></ReactFlow></div>
   <div className="map-legend">{Object.entries(labels).map(([kind,label])=><span key={kind}><i style={{background:colors[kind as ComponentKind]}}/>{label}</span>)}</div>
   <div className="tour-playback"><div className="playback-buttons"><button aria-label="Restart walkthrough" onClick={()=>{dispatch({type:'restart'});setInspected(null);}}><RotateCcw size={16}/></button><button aria-label="Previous transfer" disabled={state.index===0} onClick={()=>go(state.index-1)}><SkipBack size={18}/></button><button className="play-tour" aria-label={state.playing?'Pause walkthrough':'Play walkthrough'} onClick={()=>{setInspected(null);dispatch({type:state.playing?'pause':'play'});}}>{state.playing?<Pause size={19}/>:<Play size={19}/>} {state.playing?'Pause':'Play'}</button><button aria-label="Next transfer" disabled={state.index===scenario.steps.length-1} onClick={()=>go(state.index+1)}><SkipForward size={18}/></button></div><label>Speed<select aria-label="Walkthrough speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option></select></label><label className="motion-control"><input type="checkbox" checked={allowMotion&&!reduced} disabled={reduced} onChange={e=>setAllowMotion(e.target.checked)}/>{reduced?'Reduced motion':'Animate transfers'}</label></div>
   <label className="tour-scrubber">Transfer {state.index+1}: {step.title}<input aria-label="Walkthrough position" type="range" min="0" max={scenario.steps.length-1} value={state.index} onChange={e=>go(Number(e.target.value))}/></label>
   <article className="transfer-story" aria-label="Current transfer"><div className="transfer-heading"><span>{String(state.index+1).padStart(2,'0')}</span><div><p>{from.name} <ArrowRight size={14}/> {to.name}</p><h3>{step.title}</h3></div><span className="operation-chip">{step.operation}</span></div><p className="story-body">{step.body}</p><div className="transfer-io"><div><small>INPUT / CONTEXT</small><p>{step.input}</p></div><ArrowRight size={20}/><div><small>OUTPUT / HANDOFF</small><p>{step.output}</p></div></div><button className="story-source" onClick={()=>onSource(step.source)}><Code2 size={15}/> Inspect implementation <span>{step.source}</span><ArrowRight size={14}/></button></article>
  </div><aside className="actor-inspector" aria-label="Component details"><p className="eyebrow">{labels[selected.kind]} / COMPONENT DETAIL</p><h3>{selected.name}</h3><p className="actor-subtitle">{selected.subtitle}</p><p>{selected.description}</p>
   <label className="component-picker">Inspect any component<select aria-label="Inspect component" value={selected.id} onChange={e=>{dispatch({type:'pause'});setInspected(e.target.value);}}>{actors.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
   {selected.profile?<><div className="role-boundary"><b>Responsibility boundary</b><p>{selected.profile.boundary}</p></div><details open><summary>Inputs</summary><ul>{selected.profile.inputs.map(t=><li key={t}>{t}</li>)}</ul></details><details open><summary>Outputs</summary><ul>{selected.profile.outputs.map(t=><li key={t}>{t}</li>)}</ul></details><details><summary>Allowed tools</summary><ul>{selected.profile.tools.map(t=><li key={t}>{t}</li>)}</ul></details><details><summary>Failure & recovery</summary><p>{selected.profile.failure}</p></details><details><summary>Instructions & implementation</summary><p>Base prompt plus the selected playbook form the role instructions. Actual prompt hashes and selected skills belong to each execution archive.</p>{[selected.source,...selected.profile.sources].map((path,i)=><button key={i} className="connection" onClick={()=>onSource(path)}>{path} ↗</button>)}</details></>:<button className="connection" onClick={()=>onSource(selected.source)}>Inspect implementation ↗</button>}
   <h4>Transfers involving this component</h4><div className="component-transfers">{scenario.steps.map((s,i)=>({s,i})).filter(({s})=>s.fromId===selected.id||s.toId===selected.id).map(({s,i})=><button key={s.id} aria-current={i===state.index?'step':undefined} onClick={()=>go(i)}><span>{String(i+1).padStart(2,'0')}</span>{s.title}</button>)}</div>{!scenario.steps.some(s=>s.fromId===selected.id||s.toId===selected.id)&&<p>No transfer in this scenario. Choose the complete investigation to explore its role.</p>}
  </aside></div>
  <section className="tour-chapters" aria-label="All walkthrough transfers"><div><h3>The complete sequence</h3><p>Choose any transfer. Playback explains a reviewed path; use recorded execution inspection to establish what actually happened.</p></div><ol>{scenario.steps.map((s,i)=><li key={s.id}><button aria-current={i===state.index?'step':undefined} onClick={()=>go(i)}><span>{String(i+1).padStart(2,'0')}</span><b>{s.title}</b><small>{byId.get(s.fromId)!.name} → {byId.get(s.toId)!.name}</small></button></li>)}</ol></section>
 </section>;
}

export default function AgentExplorer(props:{onSource:(path:string)=>void;onRecords:()=>void}){
 const [technical,setTechnical]=useState(false);
 if(new URLSearchParams(location.search).get('lesson')==='hypothesis')return <HypothesisLesson onSource={props.onSource}/>;
 return <><PipelineNarrative onSource={props.onSource}/><button className="technical-toggle" aria-expanded={technical} onClick={()=>setTechnical(v=>!v)}>{technical?'Hide technical explorer':'Open optional technical explorer'}</button>{technical&&<TechnicalAgentExplorer {...props}/>}</>;
}
