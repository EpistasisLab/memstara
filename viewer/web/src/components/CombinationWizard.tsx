import {useEffect,useRef,useState} from 'react';
import {ArrowRight,ArrowLeft,Check,Layers3,Search,Brain,Database,ChartNoAxesCombined,ScanSearch,Lightbulb} from 'lucide-react';
import './combinations.css';
import FloorDetailDialog from './FloorDetailDialog';
import KnowledgeSelect from './KnowledgeSelect';
import CustomSkillUpload from './CustomSkillUpload';
import EvaluationSettings from './EvaluationSettings';
import {evaluationPlanError} from '../lib/evaluationPlan';
import {useControl,PLAYBOOK_STAGES,type PlaybookStage,type RunRequest} from '../store/control';
import {usePipelines} from '../store/pipelines';
export const flavorNames:Record<PlaybookStage,string>={hypothesis:'Hypothesis',data:'Data',ml:'Machine learning',interpreter:'Interpretation',report:'Explanation'};
export default function CombinationWizard(){
 const {catalog,form,loadPlaybooks,loadSkills}=useControl();
 const {create,closeCreation,busy,error}=usePipelines();
 const [draft,setDraft]=useState<RunRequest>(()=>({...structuredClone(form),combination_skills:{},combination_repetitions:1,combination_random_start:false,combination_max_loops:10,trials:1,hypothesis_agents:1,interpret_agents:1,continuous:false,waves:1}));
 const [step,setStep]=useState(0);const [activeRole,setActiveRole]=useState<PlaybookStage>('hypothesis');const [search,setSearch]=useState('');
 const icons={hypothesis:Brain,data:Database,ml:ChartNoAxesCombined,interpreter:ScanSearch,report:Lightbulb};
 const descriptions={hypothesis:'Generate questions and testable hypotheses from your knowledge sources.',data:'Extract the features required to test each hypothesis.',ml:'Train and evaluate models under the shared experiment settings.',interpreter:'Describe measured observations, uncertainty and limitations.',report:'Explain the findings and distinguish evidence from possible next steps.'};
 const [name,setName]=useState('');const [uploading,setUploading]=useState(false);const [reviewed,setReviewed]=useState(false);
 useEffect(()=>{void loadPlaybooks();void loadSkills();},[loadPlaybooks,loadSkills]);
 const selected=draft.combination_skills??{};
 const counts=PLAYBOOK_STAGES.map(stage=>new Set((selected[stage]??[]).map(id=>catalog.find(s=>s.id===id)?.hash).filter(Boolean)).size);
 const count=counts.reduce((a,b)=>a*b,1),total=draft.combination_max_loops??10,randomStart=!!draft.combination_random_start;
 function toggle(stage:PlaybookStage,id:string,checked:boolean){setReviewed(false);setDraft(d=>({...d,combination_skills:{...d.combination_skills,[stage]:checked?[...new Set([...(d.combination_skills?.[stage]??[]),id])]:(d.combination_skills?.[stage]??[]).filter(x=>x!==id)}}));}
 const valid=name.trim()&&name.length<=80&&count>0&&Number.isInteger(total)&&total>=1&&total<=10000&&!evaluationPlanError(draft.evaluation)&&reviewed;
 const activeIndex=PLAYBOOK_STAGES.indexOf(activeRole);
 const lastRole=activeIndex===PLAYBOOK_STAGES.length-1;
 const roleHeading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{if(step===1)roleHeading.current?.focus();},[step,activeRole]);
 function moveRole(index:number){setActiveRole(PLAYBOOK_STAGES[index]);setSearch('');}
 function next(){
  if(step===0){moveRole(0);setStep(1);}
  else if(step===1&&counts[activeIndex]>0){if(lastRole){if(count)setStep(2);}else moveRole(activeIndex+1);}
 }
 function back(){if(step===1&&activeIndex>0)moveRole(activeIndex-1);else setStep(step-1);}
 const RoleIcon=icons[activeRole];
 const visible=catalog.filter(s=>s.stage===activeRole&&`${s.title} ${s.description??''}`.toLowerCase().includes(search.toLowerCase()));
 return <FloorDetailDialog title="All Combinations" close={()=>{if(!busy&&!uploading)closeCreation();}} className="pipeline-management-dialog combination-dialog">
  <div className="comb-builder">
   <div className="comb-intro"><span className="comb-symbol"><Layers3 size={22}/></span><div><h3>Design once. Explore skill combinations.</h3><p>Choose a set of skills for each agent. One skill from each set forms one complete Loop.</p></div></div>
   <nav className="comb-steps" aria-label="Combination setup steps">{['Research inputs','Agent skills','Review & create'].map((label,i)=><button key={label} aria-current={step===i?'step':undefined} disabled={busy||uploading||(i===2&&!count)} onClick={()=>setStep(i)}><span>{step>i?<Check size={14}/>:i+1}</span>{label}</button>)}</nav>
   <div className="comb-budget" role="status"><div><strong>{count.toLocaleString()}</strong><span>possible combinations</span></div><ArrowRight size={18} aria-hidden="true"/><div className="comb-total"><strong>{Number.isInteger(total)?total.toLocaleString():'—'}</strong><span>maximum Loops per execution</span></div><div><strong>{randomStart?'Random':'First'}</strong><span>starting combination</span></div></div>
   <div className="comb-step-content">
   {step===0&&<section className="comb-inputs"><span className="comb-eyebrow">Start with your research context</span><h3>What should the agents explore?</h3><p>Every combination uses the same knowledge selection and model settings, so you can follow how different skills shape the findings.</p><KnowledgeSelect value={draft.skill} onChange={skill=>{setDraft(d=>({...d,skill}));setReviewed(false);}}/><details className="comb-settings"><summary>Model & evaluation settings</summary><EvaluationSettings value={draft.evaluation} disabled={busy||uploading} onChange={evaluation=>{setDraft(d=>({...d,evaluation}));setReviewed(false);}}/><p>These settings apply to every combination. ML skill instructions do not override the frozen evaluation settings.</p></details></section>}
   {step===1&&<div className="comb-skill-layout"><nav className="comb-roles" aria-label="Agent roles">{PLAYBOOK_STAGES.map((stage,i)=>{const Icon=icons[stage];return <button key={stage} aria-pressed={activeRole===stage} disabled={uploading||busy} onClick={()=>{setActiveRole(stage);setSearch('');}}><Icon size={19}/><span>{flavorNames[stage]}<small>{counts[i]?`${counts[i]} skill${counts[i]===1?'':'s'} selected`:'Select at least one skill'}</small></span>{counts[i]>0&&<Check size={15}/>}</button>;})}</nav><section className="comb-library"><header><span className="comb-symbol"><RoleIcon size={22}/></span><div><h3 ref={roleHeading} tabIndex={-1}>{flavorNames[activeRole]} skills</h3><p>{descriptions[activeRole]}</p></div></header><label className="comb-search"><Search size={16}/><input aria-label="Search skills" placeholder="Search this agent’s skills" value={search} onChange={e=>setSearch(e.target.value)}/></label><div className="comb-skill-cards">{visible.map(s=><div className={`comb-skill-card ${(selected[activeRole]??[]).includes(s.id)?'is-selected':''}`} key={s.id}><label><input type="checkbox" disabled={busy||uploading} checked={(selected[activeRole]??[]).includes(s.id)} onChange={e=>toggle(activeRole,s.id,e.target.checked)}/><span><strong>{s.title}</strong><small>{s.description||'Agent instructions from your skill library.'}</small></span></label><details><summary>Read instructions</summary><pre>{s.content}</pre></details></div>)}{!visible.length&&<p className="comb-empty">No matching skills. Try another search or add your own below.</p>}</div><CustomSkillUpload multiple key={activeRole} stage={activeRole} disabled={busy||uploading} onBusy={setUploading} onSelect={s=>toggle(activeRole,s.id,true)}/></section></div>}
   {step===2&&<section className="comb-review"><span className="comb-eyebrow">Your execution plan</span><h3>Review before creating</h3><div className="comb-review-roles">{PLAYBOOK_STAGES.map((stage,i)=><div key={stage}><span>{flavorNames[stage]}</span><strong>{counts[i]} skills</strong><p>{(selected[stage]??[]).map(id=>catalog.find(s=>s.id===id)?.title??id).join(' · ')}</p></div>)}</div><div className="comb-fields"><label>Name<input value={name} placeholder="e.g. Addiction knowledge exploration" maxLength={80} onChange={e=>setName(e.target.value)}/></label><label>Maximum Loops per execution<input aria-describedby="comb-limit-help" type="number" min={1} max={10000} step={1} value={Number.isNaN(total)?'':total} onChange={e=>{setDraft(d=>({...d,combination_max_loops:e.target.valueAsNumber}));setReviewed(false);}}/></label></div>
    <label className="comb-consent comb-random-start"><input type="checkbox" checked={randomStart} onChange={e=>{setDraft(d=>({...d,combination_random_start:e.target.checked}));setReviewed(false);}}/><span><strong>Random Start</strong><br/>Choose the first skill combination at random when you Run. Then follow the fixed order, wrapping around at the end. Resume keeps the same starting point.</span></label>
    <p className="comb-notice" id="comb-limit-help"><strong>Stops after at most {Number.isInteger(total)?total.toLocaleString():'—'} Loops.</strong><br/>Each Loop runs one complete skill combination. Blocked Loops count toward this limit; internal retries do not add Loops. This is a Loop limit, not a currency budget. {count>0&&total<count?'The limit covers only part of the combination set.':count>0&&total>count?'Combinations repeat after one full cycle.':'Each combination is scheduled once.'} A fresh execution {randomStart?'draws a new starting point (which may be the same by chance)':'starts at the first combination'}. This is random selection, not manager-agent guidance.</p>
    <label className="comb-consent"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/><span>I reviewed the total Loops and model settings. Each Loop consumes model tokens and compute. Creating this design does not start it.</span></label></section>}
   </div>
   {total>10000&&<p role="alert">Choose a maximum of 10,000 Loops per execution.</p>}{error&&<p role="alert">{error}</p>}
   <footer className="comb-footer"><span>{step===1?`${counts.filter(n=>n>0).length} of 5 agents configured · ${counts[activeIndex]?'Ready to continue':'Select at least one skill to continue'}`:step===2?'You choose when to Run.':'Build your skill combinations in the next step.'}</span><div>{step>0&&<button disabled={busy||uploading} onClick={back}><ArrowLeft size={16}/>Back</button>}{step<2?<button className="comb-primary" disabled={busy||uploading||(step===1&&(!counts[activeIndex]||(lastRole&&!count)))} onClick={next}>{step===0?'Choose skills':lastRole?'Review plan':`Next: ${flavorNames[PLAYBOOK_STAGES[activeIndex+1]]}`}<ArrowRight size={16}/></button>:<button className="comb-primary" disabled={!valid||busy||uploading} onClick={()=>void create(name.trim(),{...draft,waves:total})}>{busy?'Creating…':'Create combination design'}<Check size={16}/></button>}</div></footer>
  </div>
 </FloorDetailDialog>;
}
