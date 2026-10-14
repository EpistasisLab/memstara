import {compatibleResearchSkill} from '../lib/researchSkills';
import {useEffect,useRef,useState} from 'react';
import {ArrowRight,ArrowLeft,Check,Layers3,Search,Brain,Database,ChartNoAxesCombined,ScanSearch,Lightbulb} from 'lucide-react';
import './combinations.css';
import FloorDetailDialog from './FloorDetailDialog';
import KnowledgeSelect from './KnowledgeSelect';
import ResearchInputSelect from './ResearchInputSelect';
import CustomSkillUpload from './CustomSkillUpload';
import HypothesisSkillWizard from './HypothesisSkillWizard';
import EvaluationSettings from './EvaluationSettings';
import {evaluationPlanError} from '../lib/evaluationPlan';
import {useControl,PLAYBOOK_STAGES,type PlaybookStage,type RunRequest} from '../store/control';
import {usePipelines} from '../store/pipelines';
import {newPipelineConfiguration} from '../lib/newPipelineConfiguration';
export const flavorNames:Record<PlaybookStage,string>={hypothesis:'Hypothesis',data:'Data',ml:'Machine learning',interpreter:'Interpretation',report:'Explanation'};
export default function CombinationWizard(){
 const {catalog,form,loadPlaybooks,loadSkills}=useControl();
 const {create,closeCreation,busy,error}=usePipelines();
 const [draft,setDraft]=useState<RunRequest>(()=>({...newPipelineConfiguration(form),combination_skills:{},combination_repetitions:1,combination_random_start:false,combination_max_loops:10,trials:1,hypothesis_agents:1,interpret_agents:1,continuous:false,waves:1}));
 const [sourceError,setSourceError]=useState('');
 const [skillMode,setSkillMode]=useState<'library'|'custom'|'ai'>('library');
 const [step,setStep]=useState(0);const [activeRole,setActiveRole]=useState<PlaybookStage>('hypothesis');const [search,setSearch]=useState('');
 const icons={hypothesis:Brain,data:Database,ml:ChartNoAxesCombined,interpreter:ScanSearch,report:Lightbulb};
 const descriptions={hypothesis:'Generate questions and testable hypotheses from your knowledge sources.',data:'Extract the features required to test each hypothesis.',ml:'Configure LR and XGBoost, then evaluate both on identical data splits.',interpreter:'Describe measured observations, uncertainty and limitations.',report:'Explain the findings and distinguish evidence from possible next steps.'};
 const [name,setName]=useState('');const [uploading,setUploading]=useState(false);const [reviewed,setReviewed]=useState(false);
 useEffect(()=>{void loadPlaybooks();void loadSkills();},[loadPlaybooks,loadSkills]);
 const selected=draft.combination_skills??{};
 const counts=PLAYBOOK_STAGES.map(stage=>new Set((selected[stage]??[]).map(id=>catalog.find(s=>s.id===id)?.hash).filter(Boolean)).size);
 const count=counts.reduce((a,b)=>a*b,1),total=draft.combination_max_loops??10,randomStart=!!draft.combination_random_start;
 function toggle(stage:PlaybookStage,id:string,checked:boolean){setReviewed(false);setDraft(d=>({...d,combination_skills:{...d.combination_skills,[stage]:checked?[...new Set([...(d.combination_skills?.[stage]??[]),id])]:(d.combination_skills?.[stage]??[]).filter(x=>x!==id)}}));}
 const modelError=evaluationPlanError(draft.evaluation);
 const valid=!sourceError&&name.trim()&&name.length<=80&&count>0&&Number.isInteger(total)&&total>=1&&total<=10000&&!evaluationPlanError(draft.evaluation)&&reviewed;
 const activeIndex=PLAYBOOK_STAGES.indexOf(activeRole);
 const lastRole=activeIndex===PLAYBOOK_STAGES.length-1;
 const roleHeading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{if(step===1)roleHeading.current?.focus();},[step,activeRole]);
 function moveRole(index:number){setActiveRole(PLAYBOOK_STAGES[index]);setSearch('');setSkillMode('library');}
 function next(){
  if(step===0&&!sourceError){moveRole(0);setStep(1);}
  else if(step===1&&counts[activeIndex]>0&&!(activeRole==='ml'&&modelError)){if(lastRole){if(count)setStep(2);}else moveRole(activeIndex+1);}
 }
 function back(){if(step===1&&activeIndex>0)moveRole(activeIndex-1);else setStep(step-1);}
 const RoleIcon=icons[activeRole];
 const visible=catalog.filter(s=>compatibleResearchSkill(s,draft)&&s.stage===activeRole&&`${s.title} ${s.description??''}`.toLowerCase().includes(search.toLowerCase()));
 return <FloorDetailDialog title="All Combinations" close={()=>{if(!busy&&!uploading)closeCreation();}} className="pipeline-management-dialog combination-dialog">
  <div className="comb-builder">
   <div className="comb-intro"><span className="comb-symbol"><Layers3 size={22}/></span><div><h3>Design once. Explore skill combinations.</h3><p>Choose a set of skills for each agent. One skill from each set forms one complete Loop.</p></div></div>
   <nav className="comb-steps" aria-label="Combination setup steps">{['Research inputs','Agent skills','Review & create'].map((label,i)=><button key={label} aria-current={step===i?'step':undefined} disabled={busy||uploading||(i>0&&!!sourceError)||(i===2&&!count)} onClick={()=>setStep(i)}><span>{step>i?<Check size={14}/>:i+1}</span>{label}</button>)}</nav>
   <div className="comb-budget" role="status"><div><strong>{count.toLocaleString()}</strong><span>possible combinations</span></div><ArrowRight size={18} aria-hidden="true"/><div className="comb-total"><strong>{Number.isInteger(total)?total.toLocaleString():'—'}</strong><span>maximum Loops per execution</span></div><div><strong>{randomStart?'Random':'First'}</strong><span>starting combination</span></div></div>
   <div className="comb-step-content">
   {step===0&&<section className="comb-inputs"><span className="comb-eyebrow">Start with your research context</span><h3>What should the agents explore?</h3><p>Every combination uses the same knowledge selection and model settings, so you can follow how different skills shape the findings.</p><ResearchInputSelect onValidityChange={setSourceError} value={draft} onChange={patch=>{setDraft(d=>({...d,...patch}));setReviewed(false);}}/>{!draft.research_input_id&&draft.knowledge_mode!=='llm_only'&&<KnowledgeSelect value={draft.skill} onChange={skill=>{setDraft(d=>({...d,skill}));setReviewed(false);}}/>}</section>}
   {step===1&&<div className="comb-skill-layout">
    <nav className="comb-roles" aria-label="Agent roles">
     <div className="comb-roles-caption">Configure your agents<span>{counts.filter(n=>n>0).length} of 5 ready</span></div>
     {PLAYBOOK_STAGES.map((stage,i)=>{const Icon=icons[stage];return <button key={stage} aria-pressed={activeRole===stage} disabled={uploading||busy} onClick={()=>moveRole(i)}>
      <Icon size={19}/><span>{flavorNames[stage]}<small>{counts[i]?`${counts[i]} unique skill${counts[i]===1?'':'s'} selected`:'Needs a skill'}</small></span>{counts[i]>0&&<Check size={15}/>}</button>;})}
    </nav>
    <section className="comb-library">
     <header><span className="comb-symbol"><RoleIcon size={22}/></span><div><span className="comb-eyebrow">Agent {activeIndex+1} of 5</span><h3 ref={roleHeading} tabIndex={-1}>{flavorNames[activeRole]} skills</h3><p>{descriptions[activeRole]}</p></div></header>
     <div className="comb-selection-summary"><div><strong>{counts[activeIndex]?`${counts[activeIndex]} unique skills selected`:'Choose at least one skill'}</strong><span>One selected skill is used per Loop. Different contents create different combinations.</span></div><span className="comb-ready">{counts[activeIndex]?'Ready':'Required'}</span></div>
     {(selected[activeRole]??[]).length>0&&<div className="comb-selected-skills" aria-label="Selected skills">{(selected[activeRole]??[]).map(id=><span key={id}>{catalog.find(s=>s.id===id)?.title??id}<button type="button" disabled={busy||uploading} aria-label={`Remove ${catalog.find(s=>s.id===id)?.title??id}`} onClick={()=>toggle(activeRole,id,false)}>×</button></span>)}</div>}
     <div className="comb-skill-methods" role="group" aria-label="How to add skills">
      <button aria-pressed={skillMode==='library'} disabled={busy||uploading} onClick={()=>setSkillMode('library')}>Skill library<span>Choose existing instructions</span></button>
      <button aria-pressed={skillMode==='custom'} disabled={busy||uploading} onClick={()=>setSkillMode('custom')}>Upload or write<span>Use your own Markdown</span></button>
      {<button aria-pressed={skillMode==='ai'} disabled={busy||uploading} onClick={()=>setSkillMode('ai')}>Create with AI<span>Guided clinical questions</span></button>}
     </div>
     <div hidden={skillMode!=='library'}>
      <details className="comb-skill-picker" key={`picker-${activeRole}`}><summary><span>Choose {flavorNames[activeRole]} skills</span><strong>{(selected[activeRole]??[]).length} selected</strong></summary>
       <div className="comb-picker-content"><label className="comb-search"><Search size={16}/><input aria-label="Search skills" placeholder="Search by name or description" value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button aria-label="Clear skill search" onClick={()=>setSearch('')}>×</button>}</label>
        <p className="comb-library-count">{visible.length} matching skills · select one or more</p>
        <div className="comb-skill-cards" role="group" aria-label={`${flavorNames[activeRole]} skill options`}>{visible.map(s=><div className={`comb-skill-card ${(selected[activeRole]??[]).includes(s.id)?'is-selected':''}`} key={s.id}>
         <label><input type="checkbox" disabled={busy||uploading} checked={(selected[activeRole]??[]).includes(s.id)} onChange={e=>toggle(activeRole,s.id,e.target.checked)}/><span><strong>{s.title}</strong><small>{s.description||'Agent instructions from your skill library.'}</small></span></label><details><summary>Read instructions</summary><pre>{s.content}</pre></details></div>)}
         {!visible.length&&<p className="comb-empty">No matching skills. Clear your search or use Upload or write to add a skill.</p>}
        </div>
       </div>
      </details>
     </div>
     <div hidden={skillMode!=='custom'}><CustomSkillUpload includeAssistant={false} multiple key={`custom-${activeRole}`} stage={activeRole} disabled={busy||uploading} onBusy={setUploading} onSelect={s=>toggle(activeRole,s.id,true)}/></div>
     {<div hidden={skillMode!=='ai'} className="comb-ai-section"><HypothesisSkillWizard key={activeRole} stage={activeRole} multiple disabled={busy||uploading} onBusy={setUploading} onSelect={s=>toggle(activeRole,s.id,true)}/></div>}
     {activeRole==='ml'&&<details className="comb-settings comb-ml-settings" open={modelError?true:undefined}><summary><span><strong>Model &amp; evaluation settings</strong><small>LR + XGBoost · agent-selected parameters · {draft.evaluation.replicates} split evaluations</small></span><span>Edit settings</span></summary>
      <p>Data skills inherit the split defaults below. For new All Combinations runs, the ML Agent configures both LR and XGBoost before fitting; its validated plan replaces the engine, CV and search defaults.</p><EvaluationSettings proposal={draft.data_mode==='proposal'} paired dataSkill="combinations" value={draft.evaluation} disabled={busy||uploading} onChange={evaluation=>{setDraft(d=>({...d,evaluation}));setReviewed(false);}}/>
     </details>}
    </section>
   </div>}
   {step===2&&<section className="comb-review"><span className="comb-eyebrow">Your execution plan</span><h3>Review before creating</h3><div className="comb-review-roles">{PLAYBOOK_STAGES.map((stage,i)=><div key={stage}><span>{flavorNames[stage]}</span><strong>{counts[i]} skills</strong><p>{(selected[stage]??[]).map(id=>catalog.find(s=>s.id===id)?.title??id).join(' · ')}</p></div>)}</div><p className="comb-notice"><strong>Feature selection:</strong> Guided and random hypothesis skills each use 4–20 distinct original predictors. Random-feature selection uses a saved seed and cannot be changed by the agent. Random Start below only changes the first skill combination.</p>{draft.data_mode==='proposal'?<p className="comb-notice">Proposal only: these Loops produce research and analysis plans, not fitted models, measured metrics or computed SHAP/LIME explanations.</p>:<p className="comb-notice"><strong>Shared ML settings:</strong> Agent-configured LR + XGBoost · {draft.evaluation.replicates} split evaluations. Both LR and XGBoost are fitted in every Loop. The ML Agent chooses supported parameters, scaling, cutoff and training CV; CPU, memory and time limits are enforced by the server. Training-heavy and balanced Data skills override the split fraction and seed for their Loop; other Data skills use these shared settings. Balanced means 50:50 training/evaluation within exploration rows. The separate 20% validation reserve stays untouched.</p>}<div className="comb-fields"><label>Name<input value={name} placeholder="e.g. Addiction knowledge exploration" maxLength={80} onChange={e=>setName(e.target.value)}/></label><label>Maximum Loops per execution<input aria-describedby="comb-limit-help" type="number" min={1} max={10000} step={1} value={Number.isNaN(total)?'':total} onChange={e=>{setDraft(d=>({...d,combination_max_loops:e.target.valueAsNumber}));setReviewed(false);}}/></label></div>
    <label className="comb-consent comb-random-start"><input type="checkbox" checked={randomStart} onChange={e=>{setDraft(d=>({...d,combination_random_start:e.target.checked}));setReviewed(false);}}/><span><strong>Random Start</strong><br/>Choose the first skill combination at random when you Run. Then follow the fixed order, wrapping around at the end. Resume keeps the same starting point.</span></label>
    <p className="comb-notice" id="comb-limit-help"><strong>Stops after at most {Number.isInteger(total)?total.toLocaleString():'—'} Loops.</strong><br/>Each Loop runs one complete skill combination. Blocked Loops count toward this limit; internal retries do not add Loops. This is a Loop limit, not a currency budget. {count>0&&total<count?'The limit covers only part of the combination set.':count>0&&total>count?'Combinations repeat after one full cycle.':'Each combination is scheduled once.'} A fresh execution {randomStart?'draws a new starting point (which may be the same by chance)':'starts at the first combination'}. This is random selection, not manager-agent guidance.</p>
    <label className="comb-consent"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/><span>I reviewed the total Loops and model settings. Each Loop consumes model tokens and compute. Creating this design does not start it.</span></label></section>}
   </div>
   {total>10000&&<p role="alert">Choose a maximum of 10,000 Loops per execution.</p>}{error&&<p role="alert">{error}</p>}
   <footer className="comb-footer"><span>{step===1?`${counts.filter(n=>n>0).length} of 5 agents configured · ${counts[activeIndex]?'Ready to continue':'Select at least one skill to continue'}`:step===2?'You choose when to Run.':'Build your skill combinations in the next step.'}</span><div>{step>0&&<button disabled={busy||uploading} onClick={back}><ArrowLeft size={16}/>Back</button>}{step<2?<button className="comb-primary" disabled={busy||uploading||(step===0&&!!sourceError)||(step===1&&(!counts[activeIndex]||(activeRole==='ml'&&!!modelError)||(lastRole&&!count)))} onClick={next}>{step===0?'Choose skills':lastRole?'Review plan':`Next: ${flavorNames[PLAYBOOK_STAGES[activeIndex+1]]}`}<ArrowRight size={16}/></button>:<button className="comb-primary" disabled={!valid||busy||uploading} onClick={()=>void create(name.trim(),{...draft,waves:total})}>{busy?'Creating…':'Create combination design'}<Check size={16}/></button>}</div></footer>
  </div>
 </FloorDetailDialog>;
}
