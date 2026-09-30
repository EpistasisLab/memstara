import {floorCallRole as callRole, type FloorTrace as Trace, type FloorActivity} from '../lib/floorActivity';
import {createPortal} from "react-dom";
import {useEffect,useState,useRef,lazy,Suspense,type CSSProperties} from 'react';
import {Sparkles,Database,BrainCircuit,ScanEye,FileText,ArrowRight,ChevronLeft,ChevronRight,Layers3,Network,History,Play,Check,Clock3,AlertCircle,Search,ExternalLink} from 'lucide-react';
const SkillMarkdown=lazy(()=>import('./SkillMarkdown'));
import {useControl,PLAYBOOK_STAGES,type PlaybookStage} from '../store/control';
import {usePipelines,type PipelineDefinition} from '../store/pipelines';
import {STAGE_COLOR} from '../lib/stage';
import CombinationFloor from './CombinationFloor';
import FloorDetailDialog from './FloorDetailDialog';
import './combination-studio.css';

const roles={
 hypothesis:{name:'Hypothesis',description:'Generate research hypotheses',icon:Sparkles},
 data:{name:'Data',description:'Extract the selected features',icon:Database},
 ml:{name:'Machine learning',description:'Train and evaluate models',icon:BrainCircuit},
 interpreter:{name:'Interpretation',description:'Describe the observed evidence',icon:ScanEye},
 report:{name:'Explanation',description:'Explain meaning and next steps',icon:FileText},
};
type Flavor={stage:PlaybookStage;id:string;title?:string;hash?:string};
const statusLabel=(s?:string)=>s==='completed'?'Completed':(s==='running'||s==='started')?'Running':s==='failed'?'Failed':s==='cancelled'?'Cancelled':s??'Not recorded';
export default function CombinationDesign({pipeline:p,headerHost,onActivity}:{pipeline:PipelineDefinition;headerHost?:HTMLDivElement|null;onActivity?:(activity:FloorActivity|null)=>void}){
 const catalog=useControl(s=>s.catalog),busy=usePipelines(s=>s.busy);
 const board=useRef<HTMLDivElement>(null);
 const [view,setView]=useState<'floor'|'design'|'loop'>('floor'),[role,setRole]=useState<PlaybookStage|'all'>('all');
 const [search,setSearch]=useState(''),[detail,setDetail]=useState<Flavor|null>(null);
 const [preview,setPreview]=useState(false),[showGuide,setShowGuide]=useState(false);
 const [loop,setLoop]=useState(1),[retry,setRetry]=useState(0);
 const [response,setResponse]=useState<{key:string;data:Trace}|null>(null),[failure,setFailure]=useState<{key:string;message:string}|null>(null);
 useEffect(()=>{if(board.current)board.current.scrollLeft=0;},[role,search,view]);
 const choices=p.configuration.combination_skills??{};
 const lists=PLAYBOOK_STAGES.map(stage=>(choices[stage]??[]).filter((id,i,ids)=>ids.findIndex(other=>(catalog.find(s=>s.id===other)?.hash??other)===(catalog.find(s=>s.id===id)?.hash??id))===i));
 const count=lists.reduce((n,ids)=>n*ids.length,1),repetitions=p.configuration.combination_repetitions??1,total=p.configuration.combination_max_loops??count*repetitions;
 const following=view==='floor'&&!preview&&!!(p.running||p.latest);
 const requestedLoop=following?Math.max(1,p.progress.iteration??1):loop;
 const runTag=p.running?.run_tag??p.latest?.run_tag;
 const key=`${p.id}:${p.running?.run_tag??p.latest?.run_tag??'draft'}:${requestedLoop}`;
 const trace=response?.key===key?response.data:null,error=failure?.key===key?failure.message:'';
 const historyTotal=trace?.total_loops??total;
 const isRunning=!!p.running, executionState=p.running?.execution_state;
 useEffect(()=>{onActivity?.({pipelineId:p.id,runTag,loop:requestedLoop,mode:following?'live':view==='loop'?'history':'preview',trace,error,live:following&&isRunning&&!error&&executionState!=='paused',paused:following&&executionState==='paused'});},[onActivity,p.id,runTag,requestedLoop,following,view,trace,error,isRunning,executionState]);
 useEffect(()=>()=>onActivity?.(null),[onActivity]);
 useEffect(()=>{setLoop(1);setResponse(null);setFailure(null);setDetail(null);},[p.id,p.latest?.run_tag]);
 useEffect(()=>{
  if(view!=='loop'&&!following)return;
  let active=true,timer:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined;
  const read=async()=>{
   controller=new AbortController();const deadline=setTimeout(()=>controller?.abort(),8000);
   try{
    const r=await fetch(`/control/pipelines/${encodeURIComponent(p.id)}/combinations?loop=${requestedLoop}`,{signal:controller.signal});
    const data=await r.json();if(!r.ok)throw Error(data.error||'Could not read this Loop');
    if(data.run_tag&&runTag&&data.run_tag!==runTag)throw Error('Execution changed; waiting for matching records.');
    if(active){setResponse(previous=>previous?.key===key&&JSON.stringify(previous.data)===JSON.stringify(data)?previous:{key,data});setFailure(null);}
   }catch(e){if(active)setFailure(previous=>{const message=e instanceof Error&&e.name==='AbortError'?'The execution history did not respond in time.':String(e);return previous?.key===key&&previous.message===message?previous:{key,message};});}
   finally{clearTimeout(deadline);if(active)timer=setTimeout(()=>void read(),500);}
  };
  void read();return()=>{active=false;if(timer)clearTimeout(timer);controller?.abort();};
 },[view,key,retry,p.id,requestedLoop,following,runTag]);
 const visibleRoles=PLAYBOOK_STAGES.filter(s=>role==='all'||s===role);
 const skillFor=(id:string)=>catalog.find(s=>s.id===id);
 const selectedContent=detail?skillFor(detail.id):undefined;
 const sameVersion=!!selectedContent&&(!!detail?.hash&&detail.hash===selectedContent.hash);
 const header=(
  <header className="cs-unified-header" aria-label="Combination workspace controls">
   <div className="cs-heading-row">
    <div className="cs-compact-identity"><h3 title={p.name}>{p.name}</h3><span>All Combinations</span></div>
    <div className="cs-heading-actions">
     {view==='floor'&&(p.running||p.latest)&&<span className="cs-loop-status" data-live={following&&!!p.running&&p.running.execution_state!=='paused'} title="Updates every 0.5 seconds · recorded skills and call status">{following?`Loop ${requestedLoop} / ${historyTotal} · ${p.running?(p.running.execution_state==='paused'?'Paused':'Live'):'Latest execution'}`:'Combination preview'}</span>}
     {!p.latest&&!p.running&&<button className="cs-run" data-help="Run combinations" data-help-description="Start this pipeline using one skill from each agent role per Loop, up to its configured maximum Loops." disabled={busy||!count} onClick={()=>void usePipelines.getState().play(p.id)}><Play size={16}/>Run combinations</button>}
     <button className="cs-info-button" aria-label="Combination schedule and map guide" data-help="Pipeline details" data-help-description="Review the combination count, maximum Loops, start policy and the meaning of connections in the diagram." onClick={()=>setShowGuide(true)}>Details</button>
    </div>
   </div>
  <div className="cs-control-row"><nav className="cs-tabs" aria-label="Combination views">
   <button data-help="Floor plan" data-help-description="See the selected skills and recorded stage status for the current Loop. Preview mode explores possible combinations without changing execution." aria-pressed={view==='floor'} onClick={()=>setView('floor')}><Layers3 size={16}/>Floor plan</button>
   <button data-help="Skill architecture" data-help-description="Browse all configured skills by agent role. Search and read their instructions; this is the configuration, not the execution history." aria-pressed={view==='design'} onClick={()=>setView('design')}><Network size={16}/>Skill architecture</button>
   <button data-help="Loop explorer" data-help-description="Select a Loop to compare its planned skills with the actual recorded agent calls, sequence and status." aria-pressed={view==='loop'} onClick={()=>setView('loop')}><History size={16}/>Loop explorer</button>
  </nav>{view==='floor'&&(p.running||p.latest)&&<button className="cs-preview-toggle" data-help={preview?"Follow execution":"Preview combinations"} data-help-description={preview?"Return to the latest recorded Loop and refresh its agent activity every 0.5 seconds. This does not start or resume the pipeline.":"Explore possible skill combinations without running agents or changing pipeline settings."} aria-pressed={preview} onClick={()=>setPreview(v=>!v)}>{preview?'Follow execution':'Preview combinations'}</button>}</div>{view==="design"&&<div className="cs-filters" role="search" aria-label="Filter configured skills">
    <label className="cs-search"><Search size={16} aria-hidden="true"/><input type="search" aria-label="Find a combination skill" data-help="Find a skill" data-help-description="Filter the configured skills by name or matching text. This only changes what is shown, not the pipeline configuration." value={search} onChange={e=>setSearch(e.target.value)} placeholder="Find a skill…"/></label>
    <label className="cs-role-filter">Role<select aria-label="Filter agent role" data-help="Filter agent role" data-help-description="Show skills for one agent role, or choose All five roles to see the complete skill architecture." value={role} onChange={e=>setRole(e.target.value as PlaybookStage|'all')}><option value="all">All five roles</option>{PLAYBOOK_STAGES.map(s=><option key={s} value={s}>{roles[s].name}</option>)}</select></label>
   </div>}
  </header>
 );
 return <section className={`combination-studio ${view==='floor'?'cs-floor-view':''}`} aria-label="Combination design">
  {headerHost?createPortal(header,headerHost):header}
  {showGuide&&<FloorDetailDialog title="Combination schedule & map guide" close={()=>setShowGuide(false)}><dl className="cs-schedule-details"><dt>Possible combinations</dt><dd>{count.toLocaleString()}</dd><dt>Start policy</dt><dd>{p.configuration.combination_random_start?'Random Start':'Ordered start'} · then fixed-order cycles</dd><dt>Maximum Loops</dt><dd>{total.toLocaleString()}</dd><dt>Refresh interval</dt><dd>Every 0.5 seconds while viewing execution records.</dd></dl><p>One skill per role forms one complete path per Loop. Previewing does not change the execution plan.</p><p>Solid links indicate calls recorded at both stages. Dashed links indicate planned connections, not confirmed execution.</p></FloorDetailDialog>}
  {view==='floor'?<>

   {following&&error&&<div className="cs-error" role="alert"><AlertCircle size={16}/><span>{error} {trace?'Last available records; activity may have changed.':'Waiting for this Loop’s records.'}</span><button onClick={()=>setRetry(n=>n+1)}>Retry</button></div>}
   {following&&!trace?<p role="status" className="cs-empty">{error?'Execution records unavailable.':'Loading current Loop…'}</p>:<CombinationFloor
    skills={PLAYBOOK_STAGES.map((stage,i)=>{const configured=lists[i].map(id=>({stage,id,title:skillFor(id)?.title,hash:skillFor(id)?.hash}));const frozen=trace?.calls.filter(c=>callRole(c)===stage).at(-1)?.skill??trace?.planned?.agents.find(a=>a.stage===stage);return following&&frozen?[...configured.map(s=>s.id===frozen.id?frozen:s),...(!configured.some(s=>s.id===frozen.id)?[frozen]:[])]:configured;})}
    activeSkills={following?(trace?.planned?.agents??[]):undefined} recorded={following} calls={following?trace?.calls:undefined} live={following&&!!p.running&&!error&&p.running.execution_state!=='paused'} paused={following&&p.running?.execution_state==='paused'} stale={following&&!!error} inspect={setDetail}/>}
  </>:view==='design'?<>
   <p className="cs-architecture-caption">One skill from each column forms a Loop. Rows are not predefined pipelines. Scroll across, or filter by role.</p>

   <div ref={board} className="cs-board-scroll" tabIndex={0} role="region" aria-label="Agent skill architecture. Scroll horizontally to see all roles.">
    <div className={`cs-board ${role!=='all'?'cs-single-role':''}`}>
    {visibleRoles.map(stage=>{
     const index=PLAYBOOK_STAGES.indexOf(stage),Icon=roles[stage].icon;
     const ids=lists[index].filter(id=>`${skillFor(id)?.title??id} ${skillFor(id)?.description??''}`.toLowerCase().includes(search.toLowerCase()));
     return <section className="cs-column" key={stage} style={{'--role-color':STAGE_COLOR[stage]} as CSSProperties} aria-label={roles[stage].name+' skills'}>
      <header><span className="cs-role-icon"><Icon size={21}/></span><span className="cs-step">Stage {index+1}</span><h4>{roles[stage].name}</h4><p>{roles[stage].description}</p><span className="cs-variant-count">{lists[index].length} skill {lists[index].length===1?'variant':'variants'}</span></header>
      <div className="cs-skill-stack">{ids.map(id=>{const skill=skillFor(id);return <button key={id} className="cs-skill" aria-label={`Read ${skill?.title??id} skill`} onClick={()=>setDetail({stage,id,title:skill?.title,hash:skill?.hash})}>
       <span className="cs-skill-top"><span>Variant {lists[index].indexOf(id)+1}</span><ExternalLink size={14}/></span>
       <strong>{skill?.title??id}</strong><p>{skill?.description||'Open this skill to review its instructions.'}</p><span className="cs-skill-open">Read instructions <ArrowRight size={13}/></span>
      </button>;})}{!ids.length&&<p className="cs-empty">{search?'No matching skills in this role.':'No skill configured.'}</p>}</div>
     </section>;
    })}
    </div>
   </div>
   <p className="cs-note">Configured skills are shown here. Open Loop explorer to see the planned selection and actual recorded calls for a specific Loop.</p>
  </>:<>
   <div className="cs-loop-toolbar"><div><h4>Follow one execution path</h4><p>{trace?.run_tag?'Recorded execution · frozen skill versions':'Select a Loop to inspect its execution records'}</p></div>
    <div className="cs-loop-picker"><button aria-label="Previous combination Loop" disabled={loop<=1} onClick={()=>setLoop(n=>n-1)}><ChevronLeft size={18}/></button><label>Loop<input aria-label="Combination Loop" type="number" min={1} max={Math.max(1,historyTotal)} value={loop} onChange={e=>{const n=e.target.valueAsNumber;if(Number.isInteger(n)&&n>=1&&n<=historyTotal)setLoop(n);}}/></label><span>of {historyTotal.toLocaleString()}</span><button aria-label="Next combination Loop" disabled={loop>=historyTotal} onClick={()=>setLoop(n=>n+1)}><ChevronRight size={18}/></button></div>
   </div>
   {error&&<div className="cs-error" role="alert"><AlertCircle size={17}/><span>{error} {trace?'Showing the last records for this Loop.':'This does not mean the Loop is empty.'}</span><button onClick={()=>setRetry(n=>n+1)}>Retry</button></div>}
   {!trace&&!error?<p className="cs-empty" role="status">Loading this Loop’s execution path…</p>:trace&&<>
    <div className="cs-path-caption"><span>{trace.planned?`Combination ${trace.planned.combination} · cycle ${trace.planned.repetition}${trace.planned.start_combination ? ` · ${trace.planned.selection_policy==='random_start_then_cycle_v1'?'Random':'Ordered'} start: ${trace.planned.start_combination}` : ''}`:trace.preparing?'Preparing execution…':'No execution plan recorded'}</span><span>{trace.calls.length} recorded calls · refreshes every 0.5 seconds</span></div>
    <CombinationFloor recorded skills={PLAYBOOK_STAGES.map(stage=>{const flavor=trace.calls.filter(c=>callRole(c)===stage).at(-1)?.skill??trace.planned?.agents.find(a=>a.stage===stage);return flavor?[flavor]:[];})} calls={trace.calls} inspect={setDetail}/>
    <details className="cs-stage-details"><summary>Stage details and skill versions</summary><div className="cs-path">{PLAYBOOK_STAGES.map((stage,i)=>{
     const planned=trace.planned?.agents.find(a=>a.stage===stage),calls=trace.calls.filter(c=>callRole(c)===stage),last=calls.at(-1),actual=last?.skill,Icon=roles[stage].icon;
     const flavor=actual??planned,status=last?statusLabel(last.status):'Not recorded';
     return <article key={stage} className={`cs-path-stage ${last?'has-call':''} ${last?.status==='running'?'is-running':last?.status==='failed'?'is-failed':''}`} style={{'--role-color':STAGE_COLOR[stage]} as CSSProperties}>
      <span className="cs-role-icon"><Icon size={20}/></span><span className="cs-step">Stage {i+1}</span><h4>{roles[stage].name}</h4>
      <span className="cs-path-source">{actual?'Recorded skill':planned?'Planned skill':'Skill unavailable'}</span><strong>{flavor?.title??flavor?.id??'Not recorded'}</strong>
      <span className="cs-call-status">{last?.status==='completed'?<Check size={14}/>:<Clock3 size={14}/>} {status}</span>
      {flavor&&<button onClick={()=>setDetail(flavor)}>Inspect skill <ArrowRight size={13}/></button>}
     </article>;
    })}</div></details>
    <div className="cs-section-heading"><div><h4>Recorded call sequence</h4><p>Actual calls, in recorded order. A role may be called more than once.</p></div></div>
    {trace.calls.length?<ol className="cs-call-list">{trace.calls.map((c,i)=>{const s=callRole(c),Icon=s?roles[s].icon:Layers3;return <li key={c.run_id??i}><span className="cs-call-number">{i+1}</span><Icon size={18}/><div><strong>{s?roles[s].name:c.stage}</strong><span>{c.skill?.title??'Skill not recorded'}</span></div><span className="cs-call-status">{statusLabel(c.status)}</span><details><summary>Provenance</summary><dl><dt>Call stage</dt><dd>{c.stage}</dd><dt>Skill ID</dt><dd>{c.skill?.id??'Not recorded'}</dd><dt>Version hash</dt><dd>{c.skill?.hash??'Not recorded'}</dd><dt>Invocation</dt><dd>{c.run_id??'Not recorded'}</dd></dl></details></li>;})}</ol>:<p className="cs-empty">No actual calls recorded for this Loop yet. A planned selection is not evidence that an agent ran.</p>}
   </>}
  </>}
  {detail&&<FloorDetailDialog title={detail.title??detail.id} close={()=>setDetail(null)} className="cs-skill-dialog">
   <div className="cs-document-role"><span>{roles[detail.stage]?.name??detail.stage} agent</span><span>{sameVersion?'Skill instructions':'Recorded skill reference'}</span></div>
   {sameVersion?<><p className="cs-document-description">{selectedContent.description}</p><div className="cs-markdown"><Suspense fallback={<p>Loading instructions…</p>}><SkillMarkdown content={selectedContent.content||'No instructions are available for this skill.'}/></Suspense></div></>:<p>The recorded version is not available in the current skill catalog. Its current content is not substituted for the recorded instructions.</p>}
   <details className="cs-document-provenance"><summary>File and version details</summary><dl><dt>Skill ID</dt><dd>{detail.id}</dd><dt>Version hash</dt><dd>{detail.hash??'Not recorded'}</dd></dl></details>
  </FloorDetailDialog>}
 </section>;
}
