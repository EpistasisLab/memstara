import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BrainCircuit, Columns3, FileText, Lightbulb, Minus, Orbit, Pause, Plus, RotateCcw, ScanSearch } from 'lucide-react';
import { angleDelta, cameraForPoint, overlaps, pointForId, project, type Camera, type LabelRect } from './geometry';

export interface SpaceQuestion { question_id: number; text: string; okf_tags: string[]; status: string; times_used: number }
export interface EvidenceSummary { hypothesis: string; features: number | null; auc: number | null; interpretations: number | null; hasRun: boolean }
interface Props {
  questions: SpaceQuestion[]; selected: SpaceQuestion | null; select: (id: number) => void;
  clear: () => void; openStage: (stage: string) => void; summary: EvidenceSummary; activeStage: string;
}
const palette = ['#769bc8', '#ac8fc7', '#71ae9e', '#ca9d65', '#ce8793'];
const colorFor = (q: SpaceQuestion) => palette[(q.okf_tags[0] || '').split('').reduce((n, c) => n + c.charCodeAt(0), 0) % palette.length];
const home: Camera = { yaw: .3, pitch: -.12, zoom: 1 };

/** Canvas owns the animation loop; React updates only selection and readable overlays. */
export default function QuestionSpace(props: Props) {
  const host = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef(props);
  useEffect(() => { live.current = props; }, [props]);
  const camera = useRef<Camera>({ ...home }), target = useRef<Camera>({ ...home });
  const labels = useRef(new Map<number, HTMLButtonElement>());
  const hit = useRef<{ q: SpaceQuestion; x: number; y: number; z: number }[]>([]);
  const pointer = useRef<{ x: number; y: number; startX: number; startY: number; moved: boolean; id: number } | null>(null);
  const hover = useRef<number | null>(null);
  const [orbit, setOrbit] = useState(false), orbitRef = useRef(false);
  const [hovered, setHovered] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const selectedId = props.selected?.question_id;
  const expandedQuestion = expandedId === selectedId;
  const [available, setAvailable] = useState(true);
  const seen = useRef(new Map<number, number>());
  useEffect(() => { orbitRef.current = orbit; }, [orbit]);
  useEffect(() => {
    target.current = selectedId !== undefined ? cameraForPoint(pointForId(selectedId)) : { ...home };
  }, [selectedId]);
  useEffect(() => {
    const el = host.current, surface = canvas.current;
    if (!el || !surface) return;
    const context = surface.getContext('2d');
    if (!context) { setAvailable(false); return; }
    let width = 0, height = 0, frame = 0, last = 0;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const resize = new ResizeObserver(([entry]) => {
      width = entry.contentRect.width; height = entry.contentRect.height;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      surface.width = Math.round(width * dpr); surface.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    }); resize.observe(el);
    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      if (document.hidden || !width || now - last < 30) return;
      const dt = Math.min((now - last) / 1000, .1); last = now;
      const focused = live.current.selected;
      if (orbitRef.current && !pointer.current && !focused && !hover.current && !reduced.matches) target.current.yaw += dt * .065;
      const ease = reduced.matches ? 1 : 1 - Math.exp(-dt * 6);
      const c = camera.current, t = target.current;
      c.yaw += angleDelta(c.yaw, t.yaw) * ease;
      c.pitch += angleDelta(c.pitch, t.pitch) * ease; c.zoom += (t.zoom - c.zoom) * ease;
      const dark = document.documentElement.dataset.theme !== 'light';
      const ink = dark ? '#dce7f5' : '#344761';
      context.clearRect(0, 0, width, height);
      // Light volumes establish depth without inventing scientific connections.
      for (const [x, y, color] of [[.34,.48,'118,155,200'],[.67,.42,'172,143,199'],[.51,.65,'113,174,158']] as const) {
        const glow = context.createRadialGradient(width*x,height*y,0,width*x,height*y,Math.min(width,height)*.47);
        glow.addColorStop(0, `rgba(${color},${dark ? .12 : .09})`); glow.addColorStop(1, `rgba(${color},0)`);
        context.fillStyle=glow; context.fillRect(0,0,width,height);
      }
      context.strokeStyle=dark?'rgba(151,168,188,.11)':'rgba(85,110,141,.12)'; context.lineWidth=1;
      for (const tilt of [-.4,.55,1.2]) {
        context.beginPath(); context.ellipse(width/2,height*.49,Math.min(width*.35,height*.38),Math.min(width*.35,height*.38)*.38,tilt,0,Math.PI*2);context.stroke();
      }
      const points = live.current.questions.map(q => ({ q, ...project(pointForId(q.question_id),c,width,height) })).sort((a,b)=>a.z-b.z);
      hit.current=points;
      for (const p of points) {
        const color=colorFor(p.q), active=p.q.question_id===focused?.question_id || p.q.question_id===hover.current;
        const born=seen.current.get(p.q.question_id);
        if (born===undefined) seen.current.set(p.q.question_id,now);
        const arrival=reduced.matches?1:Math.min(1,(now-(born??now))/900);
        const alpha=(focused && !active ? .15 : .35+(p.z+1)*.28)*arrival;
        const r=(active?5.5:2.4)*p.perspective;
        context.globalAlpha=alpha;
        const bloom=context.createRadialGradient(p.x,p.y,0,p.x,p.y,r*5);
        bloom.addColorStop(0,color+'80');bloom.addColorStop(1,color+'00');context.fillStyle=bloom;
        context.beginPath();context.arc(p.x,p.y,r*5,0,Math.PI*2);context.fill();
        context.fillStyle=color;context.beginPath();context.arc(p.x,p.y,r,0,Math.PI*2);context.fill();
        context.strokeStyle=color;context.lineWidth=.7;context.beginPath();context.arc(p.x,p.y,r+4,0,Math.PI*2);context.stroke();
        if (arrival<1 && !reduced.matches) {context.globalAlpha=(1-arrival)*.6;context.beginPath();context.arc(p.x,p.y,r+arrival*28,0,Math.PI*2);context.stroke();}
      }
      context.globalAlpha=1;
      const occupied: LabelRect[]=[];let count=0;
      const ordered=[...points].sort((a,b)=>(b.q.question_id===hover.current?5:b.z)-(a.q.question_id===hover.current?5:a.z));
      for(const p of ordered){
        const button=labels.current.get(p.q.question_id);if(!button)continue;
        const rect={x:p.x+15,y:p.y-25,w:Math.min(184,width*.39),h:62};
        const active=p.q.question_id===hover.current;
        const visible=!focused && (active || (p.z>-.35 && count<(width<600?4:8) && !occupied.some(r=>overlaps(r,rect)))) && rect.x+rect.w<width-18 && rect.y>60 && rect.y+rect.h<height-70;
        button.style.visibility=visible?'visible':'hidden';button.style.pointerEvents=visible?'auto':'none';
        button.tabIndex=visible?0:-1;button.style.transform=`translate(${rect.x}px,${rect.y}px)`;
        button.style.width=`${rect.w}px`;button.style.setProperty('--question-color',colorFor(p.q));
        if(visible){occupied.push(rect);count++;context.strokeStyle=ink;context.globalAlpha=.26;context.beginPath();context.moveTo(p.x+6,p.y);context.lineTo(rect.x-3,p.y);context.stroke();context.globalAlpha=1;}
      }
      // These spokes represent recorded pipeline stages of the selected question, not similarity between questions.
      if(focused && width>=760){
        context.strokeStyle=dark?'rgba(174,194,220,.24)':'rgba(80,104,140,.24)';context.setLineDash([3,7]);
        for(const [x,y] of [[.18,.28],[.18,.68],[.82,.23],[.84,.49],[.8,.75]]){
          context.beginPath();context.moveTo(width*.5,height*.48);context.lineTo(width*x,height*y);context.stroke();
        }context.setLineDash([]);
      }
    };
    frame=requestAnimationFrame(draw);
    return()=>{cancelAnimationFrame(frame);resize.disconnect();};
  }, []);
  const stop=()=>{orbitRef.current=false;setOrbit(false);};
  const pick=(id:number)=>{stop();live.current.select(id);};
  const onMove=(e:React.PointerEvent<HTMLDivElement>)=>{
    const drag=pointer.current;
    if(drag){
      if(e.pointerId!==drag.id)return;
      if(Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)>5)drag.moved=true;
      if(drag.moved){target.current.yaw+=(e.clientX-drag.x)*.006;target.current.pitch=Math.max(-1.4,Math.min(1.4,target.current.pitch+(e.clientY-drag.y)*.006));}
      drag.x=e.clientX;drag.y=e.clientY;return;
    }
    if(props.selected)return;
    const bounds=e.currentTarget.getBoundingClientRect(),x=e.clientX-bounds.left,y=e.clientY-bounds.top;
    const nearest=[...hit.current].reverse().find(p=>Math.hypot(p.x-x,p.y-y)<18);
    const id=nearest?.q.question_id ?? null;
    if(hover.current!==id){hover.current=id;setHovered(id);}
  };
  const stages=[
    {name:'Hypothesis',icon:Lightbulb,kicker:'01 / PROPOSE',value:props.summary.hypothesis?'Hypothesis recorded':'Awaiting hypothesis',detail:props.summary.hypothesis.slice(0,100)||'The proposed relationship appears here.'},
    {name:'Data',icon:Columns3,kicker:'02 / EXTRACT',value:props.summary.features===null?'Awaiting features':`${props.summary.features} input features`,detail:'Follow the columns selected for analysis.'},
    {name:'ML',icon:BrainCircuit,kicker:'03 / EVALUATE',value:props.summary.auc===null?'Awaiting evaluation':`AUC ${props.summary.auc.toFixed(4)}`,detail:'Inspect the model and feature contributions.'},
    {name:'Interpretation',icon:ScanSearch,kicker:'04 / EXPLAIN',value:props.summary.interpretations===null?'Awaiting interpretation':`${props.summary.interpretations} recorded voices`,detail:'Read the independent interpretations.'},
    {name:'Report',icon:FileText,kicker:'05 / SYNTHESIZE',value:props.summary.hasRun?'Explore run report':'No linked run',detail:'Read the synthesis and its qualifications.'},
  ];
  const hoveredQuestion=props.questions.find(q=>q.question_id===hovered);
  return <section className={`question-space ${props.selected?'is-focused':''}`} aria-label="Question observatory">
    <div className="space-surface" ref={host}
      onPointerDown={e=>{if(pointer.current || props.selected || (e.target as HTMLElement).closest('button'))return;stop();pointer.current={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,moved:false,id:e.pointerId};e.currentTarget.setPointerCapture(e.pointerId);}}
      onPointerMove={onMove}
      onPointerUp={e=>{const drag=pointer.current;if(!drag || drag.id!==e.pointerId)return;pointer.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(!drag.moved){const rect=e.currentTarget.getBoundingClientRect();const nearest=[...hit.current].reverse().find(p=>Math.hypot(p.x-(e.clientX-rect.left),p.y-(e.clientY-rect.top))<22);if(nearest)pick(nearest.q.question_id);}}}
      onPointerCancel={()=>{pointer.current=null;}}
      onPointerLeave={()=>{hover.current=null;setHovered(null);}}>
      <canvas ref={canvas} aria-hidden="true" />
      {!available && <p className="space-unavailable">Canvas is unavailable. Use Question list to explore all recorded questions.</p>}
      <div className="space-coordinate" aria-hidden="true"><span>MEMSTARA / OBSERVATORY</span><span>{props.selected?'EVIDENCE IN FOCUS':'QUESTION FIELD'}</span></div>
      <div className="space-label-layer">{props.questions.map(q=><button key={q.question_id} className="space-label" ref={el=>{if(el)labels.current.set(q.question_id,el);else labels.current.delete(q.question_id);}}
        aria-label={`Explore question ${q.question_id}: ${q.text}`} onClick={()=>pick(q.question_id)} onFocus={()=>{hover.current=q.question_id;stop();}} onBlur={()=>{hover.current=null;}}>
        <span>Q{q.question_id}<i>{q.okf_tags[0] || 'Source not recorded'}</i></span><strong>{q.text}</strong>
      </button>)}</div>
      {!props.selected && !props.questions.length && <div className="space-empty">No matching questions.<small>Recorded questions will appear here as they arrive.</small></div>}
      {!props.selected && <div className="space-guide"><span className="space-guide-line"/><h2>Every question opens<br />a new line of inquiry.</h2><p>Orbit the field. Select a light to follow its evidence.</p></div>}
      {props.selected && <div className="space-focus-layer">
        <button className="space-back" onClick={()=>{stop();props.clear();}}><ArrowLeft size={14}/> Back to question field</button>
        <div className="space-question-core"><span className="space-core-id">Q{props.selected.question_id}</span><span className="universe-eyebrow">THE SELECTED QUESTION</span><h2 className={expandedQuestion?'expanded':''}>{props.selected.text}</h2><button className="space-read-question" onClick={()=>setExpandedId(v=>v===selectedId?null:selectedId??null)}>{expandedQuestion?'Collapse question':'Read full question'}</button><div>{props.selected.okf_tags.slice(0,2).map(tag=><span key={tag}>{tag}</span>)}</div></div>
        <div className="space-satellites">{stages.map((s,i)=><button key={s.name} className={`space-satellite satellite-${i}`} aria-pressed={props.activeStage===s.name} onClick={()=>props.openStage(s.name)} style={{'--satellite-color':palette[i]} as React.CSSProperties}><span className="satellite-kicker"><s.icon size={16}/>{s.kicker}</span><h3>{s.name}</h3><strong>{s.value}</strong><p>{s.detail}</p><ArrowRight className="satellite-arrow" size={16}/></button>)}</div>
      </div>}
      {!props.selected && hoveredQuestion && <div className="space-hover" role="status"><b>Q{hoveredQuestion.question_id}</b><span>{hoveredQuestion.text}</span></div>}
    </div>
    <footer className="space-controls"><span>{props.selected?'Recorded question → linked evidence':'Drag to orbit · Select a light'}<small>Spatial distance is decorative; colors follow the first recorded source tag.</small></span><div>
      <button disabled={!!props.selected} aria-label="Rotate cloud left" onClick={()=>{stop();target.current.yaw-=.35;}}><ArrowLeft size={15}/></button>
      <button disabled={!!props.selected} aria-label="Rotate cloud right" onClick={()=>{stop();target.current.yaw+=.35;}}><ArrowRight size={15}/></button>
      <button disabled={!!props.selected} aria-label="Zoom out" onClick={()=>{target.current.zoom=Math.max(.65,target.current.zoom-.15);}}><Minus size={15}/></button>
      <button disabled={!!props.selected} aria-label="Zoom in" onClick={()=>{target.current.zoom=Math.min(1.5,target.current.zoom+.15);}}><Plus size={15}/></button>
      <button disabled={!!props.selected} aria-pressed={orbit} aria-label="Toggle gentle rotation" onClick={()=>setOrbit(v=>!v)}>{orbit?<Pause size={15}/>:<Orbit size={15}/>}</button>
      <button aria-label="Reset question field" onClick={()=>{stop();target.current={...home};props.clear();}}><RotateCcw size={15}/></button>
    </div></footer>
  </section>;
}
