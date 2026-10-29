import {identityLabel,scheduledLabel} from '../lib/replicateIdentity';
import { displayText, skillLabel } from '../lib/displayText';
import {floorCallRole as callRole, type FloorTrace as Trace, type FloorActivity, floorExecutionState} from '../lib/floorActivity';
import {createPortal} from "react-dom";
import {memo,useEffect,useState,useRef,lazy,Suspense,type CSSProperties} from 'react';
import {Sparkles,Database,BrainCircuit,ScanEye,FileText,ArrowRight,Layers3,Network,Play,AlertCircle,Search,ExternalLink} from 'lucide-react';
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
function CombinationDesign({pipeline:p,headerHost,onActivity}:{pipeline:PipelineDefinition;headerHost?:HTMLDivElement|null;onActivity?:(activity:FloorActivity|null)=>void}){
 const catalog=useControl(s=>s.catalog),busy=usePipelines(s=>s.busy);
 const controlError=usePipelines(s=>s.error==='Error: Pipeline workspace is unavailable; last settings are retained.'?s.error:null);
 const board=useRef<HTMLDivElement>(null);
 const [view,setView]=useState<'floor'|'design'>('floor'),[role,setRole]=useState<PlaybookStage|'all'>('all');
 const [search,setSearch]=useState(''),[detail,setDetail]=useState<Flavor|null>(null);
 const [retry,setRetry]=useState(0);
 const [response,setResponse]=useState<{key:string;data:Trace}|null>(null),[failure,setFailure]=useState<{key:string;message:string}|null>(null);
 useEffect(()=>{if(board.current)board.current.scrollLeft=0;},[role,search,view]);
 const choices=p.configuration.combination_skills??{};
 const lists=PLAYBOOK_STAGES.map(stage=>(choices[stage]?.length?choices[stage]:[{hypothesis:'hypothesis_general',data:'data_manual_split',ml:'ml_default_logistic_regression',interpreter:'shared-shap',report:'shared-heart-failure-cardiovascular'}[stage]]).filter((id,i,ids)=>ids.findIndex(other=>(catalog.find(s=>s.id===other)?.hash??other)===(catalog.find(s=>s.id===id)?.hash??id))===i));
 const count=lists.reduce((n,ids)=>n*ids.length,1);
 const following=!!(p.running||p.latest);
 const activityMode=p.running?'live':'history';
 const requestedLoop=following?Math.max(1,p.progress.iteration??1):1;
 const runTag=p.running?.run_tag??p.latest?.run_tag;
 const key=`${p.id}:${p.running?.run_tag??p.latest?.run_tag??'draft'}:${requestedLoop}`;
 const trace=response?.key===key?response.data:null,error=controlError||(failure?.key===key?failure.message:'');

 const currentStage=following?p.progress.stage:undefined;
 const executionState=floorExecutionState(p.failure?null:p.running);
 const {paused,stopping}=executionState;
 const live=executionState.live&&!p.progress.iteration_completed;
 useEffect(()=>{onActivity?.(following?{pipelineId:p.id,runTag,loop:requestedLoop,currentStage,mode:activityMode,trace,error,live:live&&!error,paused,stopping}:null);},[currentStage,onActivity,p.id,runTag,requestedLoop,following,activityMode,trace,error,live,paused,stopping]);
 useEffect(()=>()=>onActivity?.(null),[onActivity]);
 useEffect(()=>{setResponse(null);setFailure(null);setDetail(null);},[p.id,p.latest?.run_tag]);
 useEffect(()=>{
  if(!following)return;
  let active=true,timer:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined;
  const read=async()=>{
   if(document.hidden){timer=setTimeout(()=>void read(),3000);return;}
   controller=new AbortController();const deadline=setTimeout(()=>controller?.abort(),8000);
   try{
    const r=await fetch(`/control/pipelines/${encodeURIComponent(p.id)}/combinations?loop=${requestedLoop}`,{signal:controller.signal});
    const data=await r.json();if(!r.ok)throw Error(data.error||'Could not read this Replicate');
    if(data.run_tag&&runTag&&data.run_tag!==runTag)throw Error('Execution changed; waiting for matching records.');
    if(active){setResponse(previous=>previous?.key===key&&JSON.stringify(previous.data)===JSON.stringify(data)?previous:{key,data});setFailure(null);}
   }catch(e){if(active)setFailure(previous=>{const message=e instanceof Error&&e.name==='AbortError'?'The execution history did not respond in time.':String(e);return previous?.key===key&&previous.message===message?previous:{key,message};});}
   finally{clearTimeout(deadline);if(active)timer=setTimeout(()=>void read(),500);}
  };
  void read();return()=>{active=false;if(timer)clearTimeout(timer);controller?.abort();};
 },[key,retry,p.id,requestedLoop,following,runTag]);
 const visibleRoles=PLAYBOOK_STAGES.filter(s=>role==='all'||s===role);
 const skillFor=(id:string)=>catalog.find(s=>s.id===id);
 const selectedContent=detail?skillFor(detail.id):undefined;
 const sameVersion=!!selectedContent&&(!!detail?.hash&&detail.hash===selectedContent.hash);
 const header=(
  <header className="cs-unified-header" aria-label="Combination workspace controls">
   <div className="cs-heading-row">
    <div className="cs-compact-identity"><h3 title={p.name}>{p.name}</h3><span>Pipeline design</span></div>
    <div className="cs-heading-actions">
     {view==='floor'&&following&&<span className="cs-loop-status" data-live={live&&!error} title="Updates every 0.5 seconds · recorded skills and call status">{`${trace?.combination_plan?scheduledLabel(requestedLoop,trace.combination_plan,true):trace?.planned?identityLabel({pipeline_number:trace.planned.combination,replicate_number:trace.planned.repetition}):'Pipeline — · Replicate —'} · ${p.running?(error?'Updates unavailable':paused?'Paused':stopping?'Pausing':live?'Live':'Waiting'):'Latest execution'}`}</span>}
     {!p.latest&&!p.running&&<button className="cs-run" data-help="Run combinations" data-help-description="Start this pipeline using one skill from each agent role per Replicate, up to its configured maximum Replicates." disabled={busy||!count} onClick={()=>void usePipelines.getState().play(p.id)}><Play size={16}/>Run combinations</button>}
    </div>
   </div>
  <div className="cs-control-row"><nav className="cs-tabs" aria-label="Combination views">
   <button data-help="Experiments" data-help-description="See the selected skills and recorded stage status for the current Replicate." aria-pressed={view==='floor'} onClick={()=>setView('floor')}><Layers3 size={16}/>Experiments</button>
   <button data-help="Skill architecture" data-help-description="Browse all configured skills by agent role. Search and read their instructions; this is the configuration, not the execution history." aria-pressed={view==='design'} onClick={()=>setView('design')}><Network size={16}/>Skill architecture</button>
  </nav></div>{view==="design"&&<div className="cs-filters" role="search" aria-label="Filter configured skills">
    <label className="cs-search"><Search size={16} aria-hidden="true"/><input type="search" aria-label="Find a combination skill" data-help="Find a skill" data-help-description="Filter the configured skills by name or matching text. This only changes what is shown, not the pipeline configuration." value={search} onChange={e=>setSearch(e.target.value)} placeholder="Find a skill…"/></label>
    <label className="cs-role-filter">Role<select aria-label="Filter agent role" data-help="Filter agent role" data-help-description="Show skills for one agent role, or choose All five roles to see the complete skill architecture." value={role} onChange={e=>setRole(e.target.value as PlaybookStage|'all')}><option value="all">All five roles</option>{PLAYBOOK_STAGES.map(s=><option key={s} value={s}>{roles[s].name}</option>)}</select></label>
   </div>}
  </header>
 );
 return <section className={`combination-studio ${view==='floor'?'cs-floor-view':''}`} aria-label="Combination design">
  {headerHost?createPortal(header,headerHost):header}
  {view==='floor'?<>

   {following&&error&&<div className="cs-error" role="alert"><AlertCircle size={16}/><span>{displayText(error)} {trace?'Last available records; activity may have changed.':'Waiting for this Replicate’s records.'}</span><button onClick={()=>setRetry(n=>n+1)}>Retry</button></div>}
   {following&&!trace&&<p role="status" className="cs-empty">{error?'Execution records unavailable.':'Loading current Replicate…'}</p>}
   <CombinationFloor
    skills={PLAYBOOK_STAGES.map((stage,i)=>{const configured=lists[i].map(id=>({stage,id,title:skillFor(id)?.title,hash:skillFor(id)?.hash}));const frozen=trace?.calls.filter(c=>callRole(c)===stage).at(-1)?.skill??trace?.planned?.agents.find(a=>a.stage===stage);return following&&frozen?[...configured.map(s=>s.id===frozen.id?frozen:s),...(!configured.some(s=>s.id===frozen.id)?[frozen]:[])]:configured;})}
    currentStage={currentStage} activeSkills={following?(trace?.planned?.agents??[]):undefined} recorded={following} calls={following?trace?.calls:undefined} live={following&&!!trace&&live&&!error} paused={following&&paused} stopping={following&&stopping} stale={following&&!!error} inspect={setDetail}/>
  </>:<>
   <p className="cs-architecture-caption">One skill from each agent column defines a Pipeline. A Replicate repeats its complete research process. Scroll across, or filter by role.</p>

   <div ref={board} className="cs-board-scroll" tabIndex={0} role="region" aria-label="Agent skill architecture. Scroll horizontally to see all roles.">
    <div className={`cs-board ${role!=='all'?'cs-single-role':''}`}>
    {visibleRoles.map(stage=>{
     const index=PLAYBOOK_STAGES.indexOf(stage),Icon=roles[stage].icon;
     const ids=lists[index].filter(id=>displayText(`${skillLabel(id,skillFor(id)?.title)} ${skillFor(id)?.description??''}`).toLowerCase().includes(search.toLowerCase()));
     return <section className="cs-column" key={stage} style={{'--role-color':STAGE_COLOR[stage]} as CSSProperties} aria-label={roles[stage].name+' skills'}>
      <header><span className="cs-role-icon"><Icon size={21}/></span><span className="cs-step">Stage {index+1}</span><h4>{roles[stage].name}</h4><p>{roles[stage].description}</p><span className="cs-variant-count">{lists[index].length} skill {lists[index].length===1?'variant':'variants'}</span></header>
      <div className="cs-skill-stack">{ids.map(id=>{const skill=skillFor(id);return <button key={id} className="cs-skill" aria-label={`Read ${skillLabel(id,skill?.title)} skill`} onClick={()=>setDetail({stage,id,title:skill?.title,hash:skill?.hash})}>
       <span className="cs-skill-top"><span>Variant {lists[index].indexOf(id)+1}</span><ExternalLink size={14}/></span>
       <strong>{skillLabel(id,skill?.title)}</strong><p>{displayText(skill?.description)||'Open this skill to review its instructions.'}</p><span className="cs-skill-open">Read instructions <ArrowRight size={13}/></span>
      </button>;})}{!ids.length&&<p className="cs-empty">{search?'No matching skills in this role.':'No skill configured.'}</p>}</div>
     </section>;
    })}
    </div>
   </div>
  </>}
  {detail&&<FloorDetailDialog title={skillLabel(detail.id,detail.title)} close={()=>setDetail(null)} className="cs-skill-dialog">
   <div className="cs-document-role"><span>{roles[detail.stage]?.name??detail.stage} agent</span><span>{sameVersion?'Skill instructions':'Recorded skill reference'}</span></div>
   {sameVersion?<><p className="cs-document-description">{displayText(selectedContent.description)}</p><div className="cs-markdown"><Suspense fallback={<p>Loading instructions…</p>}><SkillMarkdown content={selectedContent.content||'No instructions are available for this skill.'}/></Suspense></div></>:<p>The recorded version is not available in the current skill catalog. Its current content is not substituted for the recorded instructions.</p>}
   <details className="cs-document-provenance"><summary>File and version details</summary><dl><dt>Skill</dt><dd>{skillLabel(detail.id,detail.title)}</dd><dt>Version hash</dt><dd>{detail.hash??'Not recorded'}</dd></dl></details>
  </FloorDetailDialog>}
 </section>;
}
export default memo(CombinationDesign);
