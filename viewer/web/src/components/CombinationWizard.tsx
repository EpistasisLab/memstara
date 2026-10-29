import ExplanationLengthSettings, {explanationLengthError} from './ExplanationLengthSettings';
import { displayText, skillLabel } from '../lib/displayText';
import {overridesForSkills} from '../lib/mlOverrides';
import {compatibleResearchSkill,researchSkillProfile} from '../lib/researchSkills';
import {useEffect,useRef,useState} from 'react';
import {ArrowRight,ArrowLeft,Check,Search,Brain,Database,ChartNoAxesCombined,ScanSearch,Lightbulb} from 'lucide-react';
import './combinations.css';
import FloorDetailDialog from './FloorDetailDialog';
import ResearchInputSelect from './ResearchInputSelect';
import ExperimentModelSettings, {ExperimentModelContext, type ModelConnection} from './ExperimentModelSettings';
import CustomSkillUpload from './CustomSkillUpload';
import HypothesisSkillWizard from './HypothesisSkillWizard';
import {evaluationPlanError} from '../lib/evaluationPlan';
import {useControl,DEFAULT_REQUEST,PLAYBOOK_STAGES,type PlaybookStage,type RunRequest} from '../store/control';
import {usePipelines} from '../store/pipelines';
import {newPipelineConfiguration} from '../lib/newPipelineConfiguration';
export const flavorNames:Record<PlaybookStage,string>={hypothesis:'Hypothesis',data:'Data',ml:'Machine learning',interpreter:'Interpretation',report:'Explanation'};
export default function CombinationWizard(){
 const {catalog,loadPlaybooks,loadSkills}=useControl();
 const {create,closeCreation,busy,error}=usePipelines();
 // Each newly opened wizard starts from app defaults, independently of the selected experiment.
 // Keep draft changes local so editing or running saved experiments cannot seed new creation.
 const [draft,setDraft]=useState<RunRequest>(()=>({...newPipelineConfiguration(DEFAULT_REQUEST),combination_skills:{},ml_overrides:{},evaluation:{...DEFAULT_REQUEST.evaluation,engine:'logistic_regression',folds:0,replicates:1,search_trials:1},combination_repetitions:1,combination_execution_order:'all_pipelines_first',combination_random_start:false,combination_max_loops:null,trials:1,hypothesis_agents:1,interpret_agents:1,continuous:false,waves:1}));
 const [inputError,setSourceError]=useState('');
 const [connectionError,setConnectionError]=useState('');
 const [connection,setConnection]=useState<ModelConnection|null>(null);
 const sourceError=inputError||connectionError;
 const [skillMode,setSkillMode]=useState<'library'|'custom'|'ai'>('library');
 const [step,setStep]=useState(0);const [activeRole,setActiveRole]=useState<PlaybookStage>('hypothesis');const [search,setSearch]=useState('');
 const icons={hypothesis:Brain,data:Database,ml:ChartNoAxesCombined,interpreter:ScanSearch,report:Lightbulb};
 const descriptions={hypothesis:'Generate questions and testable hypotheses from your knowledge sources.',data:'Choose how to configure the training and test split for your data.',ml:'Each ML skill configures and fits only its selected model.',interpreter:'Describe measured observations, uncertainty and limitations.',report:'Explain the findings and distinguish evidence from possible next steps.'};
 const [name,setName]=useState('');const [uploading,setUploading]=useState(false);const [reviewed,setReviewed]=useState(false);
 useEffect(()=>{void loadPlaybooks();void loadSkills();},[loadPlaybooks,loadSkills]);
 const requested=draft.combination_skills??{};
 const defaults:Partial<Record<PlaybookStage,string>>={report:researchSkillProfile(draft).report[0],ml:'ml_logistic_regression',data:'data_training_heavy',interpreter:'shared-shap'};
 const selected=Object.fromEntries(PLAYBOOK_STAGES.map(stage=>{
  if(requested[stage]!==undefined)return [stage,requested[stage]];
  const available=catalog.filter(s=>s.stage===stage&&s.id!=='random_features'&&compatibleResearchSkill(s,draft));
  const fallback=available.find(s=>s.id===(stage==='hypothesis'?'heart-failure-all-categories':defaults[stage]))??available[0];
  return [stage,fallback?[fallback.id]:[]];
 })) as Partial<Record<PlaybookStage,string[]>>;
 const hypothesisDefault=catalog.filter(s=>s.stage==='hypothesis'&&compatibleResearchSkill(s,draft));
 const defaultHypothesis=hypothesisDefault.find(s=>s.id==='heart-failure-all-categories')??hypothesisDefault[0];
 const effectiveSelected={...selected,hypothesis:selected.hypothesis?.length?selected.hypothesis:defaultHypothesis?[defaultHypothesis.id]:[]};
 for(const stage of ['interpreter','report'] as const){
  if(!selected[stage]?.length){
   const available=catalog.filter(s=>s.stage===stage&&compatibleResearchSkill(s,draft));
   const fallback=available.find(s=>s.id===(stage==='interpreter'?'shared-shap':researchSkillProfile(draft).report[0]))??available[0];
   effectiveSelected[stage]=fallback?[fallback.id]:[];
  }
 }
 const manualSplit=selected.data?.length===0;
 const counts=PLAYBOOK_STAGES.map(stage=>(stage==='ml'&&!effectiveSelected.ml?.length)||(stage==='data'&&manualSplit)?1:new Set((effectiveSelected[stage]??[]).map(id=>catalog.find(s=>s.id===id)?.hash).filter(Boolean)).size);
 const count=counts.reduce((a,b)=>a*b,1),repetitions=draft.combination_repetitions??1,total=count*repetitions;
 const executionOrder=draft.combination_execution_order??'all_pipelines_first';
 const executionOrderLabel=executionOrder==='all_pipelines_first'?'All pipelines first':'One pipeline all replicates first';
 function toggle(stage:PlaybookStage,id:string,checked:boolean){setReviewed(false);setDraft(d=>{const choices=checked?[...new Set([...(d.combination_skills?.[stage]??selected[stage]??[]),id])]:(d.combination_skills?.[stage]??selected[stage]??[]).filter(x=>x!==id);return {...d,combination_skills:{...d.combination_skills,[stage]:choices},ml_overrides:stage==='ml'?overridesForSkills(d.ml_overrides,choices):d.ml_overrides};});}
 const modelError=evaluationPlanError(draft.evaluation);
 const reportError=explanationLengthError(draft.explanation_words);
 const valid=!sourceError&&name.trim()&&name.length<=80&&count>0&&Number.isInteger(repetitions)&&repetitions>=1&&repetitions<=100&&Number.isInteger(total)&&total>=1&&total<=10000&&!modelError&&!reportError&&reviewed;
 const activeIndex=PLAYBOOK_STAGES.indexOf(activeRole);
 const lastRole=activeIndex===PLAYBOOK_STAGES.length-1;
 const roleHeading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{if(step===1)roleHeading.current?.focus();},[step,activeRole]);
 function moveRole(index:number){setActiveRole(PLAYBOOK_STAGES[index]);setSearch('');setSkillMode('library');}
 function next(){
  if(step===0&&!sourceError){moveRole(0);setStep(1);}
  else if(step===1&&counts[activeIndex]>0&&!(activeRole==='report'&&reportError)&&!((activeRole==='ml'||activeRole==='data')&&modelError)){if(lastRole){if(count)setStep(2);}else moveRole(activeIndex+1);}
 }
 function back(){if(step===1&&activeIndex>0)moveRole(activeIndex-1);else setStep(step-1);}
 const missingAgents=PLAYBOOK_STAGES.filter((_,i)=>!counts[i]).map(stage=>flavorNames[stage]);
 const nextLabel=step===0?'Choose skills':lastRole?'Review plan':`Next: ${flavorNames[PLAYBOOK_STAGES[activeIndex+1]]}`;
 const blocker=uploading?'Wait for your skill to finish saving.':busy?'Saving your pipeline…':
  step===0?sourceError:
  step===1?(activeRole==='report'&&reportError?reportError:!counts[activeIndex]?`Select at least one ${flavorNames[activeRole]} skill.`:(activeRole==='ml'||activeRole==='data')&&modelError?modelError:lastRole&&!count?`Choose skills for: ${missingAgents.join(', ')}.`:''):
  sourceError||reportError||(!count?`Choose skills for: ${missingAgents.join(', ')}.`:'')||modelError||(!name.trim()?'Enter a name for your pipeline.':name.length>80?'Use a name with 80 characters or fewer.':!Number.isInteger(repetitions)||repetitions<1||repetitions>100?'Enter 1–100 replicates per pipeline.':total>10000?'Choose at most 10,000 total runs.':!reviewed?'Check the confirmation box after reviewing your settings.':'');
 const instruction=step===0?'Choose a prepared dataset or bring your own. Then configure your agents.':step===1&&activeRole==='data'?`Choose a split method, then select ${nextLabel}.`:step===1?
  skillMode==='library'?`Keep the default or choose skills, then select ${nextLabel}.`:
  skillMode==='custom'?'Upload or write a skill, then save and select it to continue.':'Create a skill with AI, then save and select it to continue.':
  'Name your pipeline, review the replicate count and settings, then check the confirmation box.';
 const RoleIcon=icons[activeRole];
 const visible=catalog.filter(s=>s.id!=='data_manual_split'&&compatibleResearchSkill(s,draft)&&s.stage===activeRole&&displayText(`${skillLabel(s.id,s.title)} ${s.description??''}`).toLowerCase().includes(search.toLowerCase()));
 return <FloorDetailDialog title="All Combinations" close={()=>{if(!busy&&!uploading)closeCreation();}} className="pipeline-management-dialog combination-dialog">
  <ExperimentModelContext.Provider value={connection?`Model: ${connection.model} (${connection.provider.replace(/_/g, ' ')})`:connectionError?'Choose your AI model above.':undefined}><div className="comb-builder">
   <nav className="comb-steps" aria-label="Combination setup steps">{['Research inputs','Agent skills','Review & create'].map((label,i)=><button key={label} aria-current={step===i?'step':undefined} disabled={busy||uploading||(i>0&&!!sourceError)||(i===2&&!count)} onClick={()=>setStep(i)}><span>{(i===0&&!sourceError&&step>0)||(i===1&&count>0&&!modelError)?<Check size={14}/>:i+1}</span>{label}</button>)}</nav>
   {step===2&&<div className="comb-budget" role="status" aria-label="Pipeline replicate summary"><div><strong>{count.toLocaleString()}</strong><span>total pipelines</span></div><span className="comb-budget-operator" aria-hidden="true">×</span><div><strong>{Number.isInteger(repetitions)?repetitions.toLocaleString():'—'}</strong><span>replicates per pipeline</span></div><span className="comb-budget-operator" aria-hidden="true">=</span><div className="comb-total"><strong>{Number.isInteger(total)?total.toLocaleString():'—'}</strong><span>total runs</span></div></div>}
   <div className="comb-step-content" data-context-help-managed={step===1&&activeRole==='hypothesis'?true:undefined}>
   <header className="comb-guidance"><span className="comb-eyebrow">Step {step+1} of 3{step===1?` · Agent ${activeIndex+1} of 5`:''}</span><h3>{step===0?'Set up your research':step===1?(activeRole==='data'?'Configure your data':`Choose ${flavorNames[activeRole]} skills`):'Confirm your pipeline'}</h3><p>{instruction}</p></header>
   <div hidden={step!==0}><ExperimentModelSettings onValidityChange={setConnectionError} onChange={value=>{setConnection(value);setDraft(d=>({...d,model_connection_id:value?.id??'',stage_models:{}}));setReviewed(false);}}/></div>
   {step===0&&<section className="comb-inputs"><ResearchInputSelect onValidityChange={setSourceError} value={draft} onChange={patch=>{setDraft(d=>({...d,...patch}));setReviewed(false);}}/></section>}
   {step===1&&<div className="comb-skill-layout">
    <nav className="comb-roles" aria-label="Agent roles">
     <div className="comb-roles-caption">Configure your agents<span>{counts.filter(n=>n>0).length} of 5 ready</span></div>
     {PLAYBOOK_STAGES.map((stage,i)=>{const Icon=icons[stage];return <button key={stage} aria-pressed={activeRole===stage} disabled={uploading||busy} onClick={()=>moveRole(i)}>
      <Icon size={19}/><span>{stage==='data'?'Data settings':flavorNames[stage]}<small>{counts[i]?stage==='data'&&manualSplit?'Manual split':`${counts[i]} skill${counts[i]===1?'':'s'} selected`:'Needs a skill'}</small></span>{counts[i]>0&&<Check size={15}/>}</button>;})}
    </nav>
    <section className="comb-library">
     <header><span className="comb-symbol"><RoleIcon size={22}/></span><div><h3 ref={roleHeading} tabIndex={-1}>{activeRole==='data'?'Data settings':`${flavorNames[activeRole]} skills`}</h3><p>{descriptions[activeRole]}</p></div></header>
     {activeRole==='data'&&<fieldset className="comb-split-choice" disabled={busy||uploading}>
      <legend>How should we split your data?</legend>
      <p className="comb-split-intro">Choose how much data is used to train the model and how much is held out for testing.</p>
      <div className="comb-split-modes">
       <label className={!manualSplit?'is-selected':''}><input type="radio" name="data-split-mode" aria-label="Use data skills" checked={!manualSplit} onChange={()=>{setReviewed(false);setDraft(d=>({...d,combination_skills:{...d.combination_skills,data:['data_training_heavy']},evaluation:{...d.evaluation,seed:42,test_size:.25}}));}}/><span><strong>Use data skills</strong><small>Choose predefined split settings from the skills below.</small></span></label>
       <label className={manualSplit?'is-selected':''}><input type="radio" name="data-split-mode" aria-label="Set the split myself" checked={manualSplit} onChange={()=>{setReviewed(false);setDraft(d=>({...d,combination_skills:{...d.combination_skills,data:[]}}));}}/><span><strong>Set the split myself</strong><small>Choose the percentage used for training.</small></span></label>
      </div>
      {manualSplit?<div className="comb-manual-split">
       <div className="comb-split-fields">
        <label htmlFor="manual-training-share"><span>Training data <small>50–90%</small></span><div className="comb-percent-input"><input id="manual-training-share" aria-label="Training data (%)" aria-describedby="manual-training-help" type="number" min={50} max={90} step={1} value={Number.isNaN(draft.evaluation.test_size)?'':Math.round((1-draft.evaluation.test_size)*100)} onChange={e=>{setReviewed(false);setDraft(d=>({...d,evaluation:{...d.evaluation,test_size:Number.isFinite(e.target.valueAsNumber)?Number(((100-e.target.valueAsNumber)/100).toFixed(4)):NaN}}));}}/><span aria-hidden="true">%</span></div><small id="manual-training-help">The remaining data is reserved for testing.</small></label>
        <label htmlFor="manual-fixed-seed"><span>Seed</span><input id="manual-fixed-seed" aria-label="Fixed seed" aria-describedby="manual-fixed-seed-help" type="number" min={0} max={2147483647} step={1} value={Number.isNaN(draft.evaluation.seed)?'':draft.evaluation.seed} onChange={e=>{setReviewed(false);setDraft(d=>({...d,evaluation:{...d.evaluation,seed:e.target.valueAsNumber}}));}}/><small id="manual-fixed-seed-help">Use this same seed for every pipeline and replicate.</small></label>
       </div>
       {Number.isFinite(draft.evaluation.test_size)&&draft.evaluation.test_size>=.1&&draft.evaluation.test_size<=.5?<div className="comb-split-preview" aria-label="Train and test allocation">
        <div className="comb-split-preview-labels"><span><i/>Training <strong>{Math.round((1-draft.evaluation.test_size)*100)}%</strong></span><span><i/>Testing <strong>{Math.round(draft.evaluation.test_size*100)}%</strong></span></div>
        <div className="comb-split-bar" aria-hidden="true"><span style={{width:`${(1-draft.evaluation.test_size)*100}%`}}/></div>
       </div>:<p className="comb-split-error" role="alert">Enter a training percentage from 50 to 90.</p>}
       <p className="comb-split-note">Seed {Number.isFinite(draft.evaluation.seed)?draft.evaluation.seed:'—'} stays fixed for every pipeline and replicate. The split and model use this same seed.</p>
      </div>:<p className="comb-split-note">Select data skills below to set the split. Every replicate across all pipelines gets its own automatically generated seed. No two executions in this experiment share a seed. Each execution uses the same seed for its data split and model; retries keep that seed.</p>}
     </fieldset>}
     {activeRole==='report'&&<ExplanationLengthSettings value={draft.explanation_words} disabled={busy||uploading} onChange={value=>{setDraft(d=>({...d,explanation_words:value}));setReviewed(false);}}/>}
     <div hidden={activeRole==='data'&&manualSplit}>
     <div className="comb-skill-methods" role="group" aria-label="How to add skills">
      <button aria-pressed={skillMode==='library'} disabled={busy||uploading} onClick={()=>setSkillMode('library')}>Skill library</button>
      {<button aria-pressed={skillMode==='custom'} disabled={busy||uploading} onClick={()=>setSkillMode('custom')}>Upload or write</button>}
      {<button aria-pressed={skillMode==='ai'} disabled={busy||uploading} onClick={()=>setSkillMode('ai')}>Create with AI</button>}
     </div>
     <div hidden={skillMode!=='library'}>
      <details className="comb-skill-picker" key={`picker-${activeRole}`} open><summary><span>Choose {flavorNames[activeRole]} skills</span><strong>{(selected[activeRole]??[]).length} selected</strong></summary>
       <div className="comb-picker-content"><label className="comb-search"><Search size={16}/><input aria-label="Search skills" placeholder="Search by name or description" value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button aria-label="Clear skill search" onClick={()=>setSearch('')}>×</button>}</label>
        <div className="comb-skill-cards" role="group" aria-label={`${flavorNames[activeRole]} skill options`}>{visible.map(s=><div className={`comb-skill-card ${(selected[activeRole]??[]).includes(s.id)?'is-selected':''}`} key={s.id}>
         <label><input type="checkbox" disabled={busy||uploading} checked={(selected[activeRole]??[]).includes(s.id)} onChange={e=>toggle(activeRole,s.id,e.target.checked)}/><span><strong>{skillLabel(s.id,s.title)}</strong><small>{displayText(s.description)||'Agent instructions from your skill library.'}</small></span></label><details><summary>Read instructions</summary><pre>{displayText(s.content)}</pre></details></div>)}
         {!visible.length&&<p className="comb-empty">No matching skills. Clear your search or use Upload or write to add a skill.</p>}
        </div>
       </div>
      </details>
     </div>
     {<div hidden={skillMode!=='custom'}><CustomSkillUpload includeAssistant={false} multiple key={`custom-${activeRole}`} stage={activeRole} disabled={busy||uploading} onBusy={setUploading} onSelect={s=>{setSearch('');toggle(activeRole,s.id,true);}}/></div>}
     {<div hidden={skillMode!=='ai'} className="comb-ai-section"><HypothesisSkillWizard key={`${activeRole}:${connection?.id || "defaults"}`} stage={activeRole} expanded={skillMode==='ai'} modelConnectionId={connection?.id} multiple disabled={busy||uploading} onBusy={setUploading} onSelect={s=>{setSearch('');toggle(activeRole,s.id,true);}}/></div>}
     </div>
     {activeRole==='hypothesis'&&!selected.hypothesis?.length&&defaultHypothesis&&<p className="comb-review-hint">Default: {skillLabel(defaultHypothesis.id,defaultHypothesis.title)}. Select Next to use this skill.</p>}
     {(['interpreter','report'] as string[]).includes(activeRole)&&!selected[activeRole]?.length&&effectiveSelected[activeRole]?.length&&<p className="comb-review-hint">Default: {skillLabel(effectiveSelected[activeRole]![0],catalog.find(s=>s.id===effectiveSelected[activeRole]![0])?.title)}. Select Next to continue.</p>}
     {activeRole==='ml'&&!selected.ml?.length&&<p className="comb-review-hint">Default: scikit-learn Logistic Regression. No tuning or additional model settings are required.</p>}
    </section>
   </div>}
   {step===2&&<section className="comb-review" aria-label="Review combination design">
    <header className="comb-review-heading"><div><h3>Review your design</h3><p>Review settings before creating your design.</p></div><span className="comb-review-count"><strong>{count.toLocaleString()}</strong> total pipelines</span></header>
    <div className="comb-review-layout">
     <section className="comb-review-card" aria-labelledby="comb-run-heading">
      <h4 id="comb-run-heading">Execution settings</h4>
      <div className="comb-review-fields">
       <label>Name<input value={name} placeholder="e.g. Study comparison" maxLength={80} onChange={e=>setName(e.target.value)}/></label>
       <label>Replicates per pipeline<input aria-describedby="comb-limit-help" type="number" min={1} max={100} step={1} value={Number.isNaN(repetitions)?'':repetitions} onChange={e=>{setDraft(d=>({...d,combination_repetitions:e.target.valueAsNumber,combination_max_loops:null}));setReviewed(false);}}/></label>
      </div>
      <p id="comb-limit-help" className="comb-review-hint">One Pipeline is one skill combination. One Replicate completes that Pipeline’s research process once. {count} pipelines × {Number.isInteger(repetitions)?repetitions:'—'} replicates per pipeline = {Number.isInteger(total)?total:'—'} total runs.</p>
      <details className="comb-review-rules"><summary>How execution works</summary><p>{draft.combination_execution_order==='pipeline_replicates_first'?'Complete every replicate of one pipeline before moving to the next pipeline.':'All pipelines complete their first replicate before the next replicate cycle begins.'} The schedule contains {Number.isInteger(total)?total.toLocaleString():'—'} total runs. A blocked attempt is recorded separately from successful completion; retries stay attached to the same scheduled replicate. Resume preserves the schedule.</p></details>
     </section>
     <section className="comb-review-card"><h4>AI model</h4><p className="break-words text-sm">{connection?`${connection.provider.replace(/_/g,' ')} · ${connection.model}`:'Current configured model'}</p><button type="button" className="mt-2 text-sm underline" onClick={()=>setStep(0)}>Edit model</button></section>
     <section className="comb-review-card"><h4>Explanation report</h4><p>Target length: {draft.explanation_words??250} words per report.</p></section>
     <section className="comb-review-card" aria-labelledby="comb-agents-heading"><h4 id="comb-agents-heading">Your agents</h4><ol className="comb-review-agents">{PLAYBOOK_STAGES.map((stage,i)=>{const Icon=icons[stage];return <li key={stage}>
      <div className="comb-review-agent-heading"><Icon size={18} aria-hidden="true"/><h5>{flavorNames[stage]}</h5><span>{stage==='data'&&manualSplit?'Manual split':`${counts[i]} ${counts[i]===1?'skill':'skills'}`}</span><button type="button" aria-label={stage==='data'?'Edit Data settings':`Edit ${flavorNames[stage]} skills`} disabled={busy||uploading} onClick={()=>{moveRole(i);setStep(1);}}>Edit</button></div>
      <ul>{stage==='data'&&manualSplit&&<li>Train {Math.round((1-draft.evaluation.test_size)*100)}% / Test {Math.round(draft.evaluation.test_size*100)}% · Fixed seed {draft.evaluation.seed}</li>}{stage==='ml'&&!selected.ml?.length&&<li>Default scikit-learn Logistic Regression</li>}{(effectiveSelected[stage]??[]).map(id=><li key={id}>{skillLabel(id,catalog.find(s=>s.id===id)?.title)}</li>)}</ul>
     </li>;})}</ol></section>
    </div>
    <fieldset className="comb-execution-order" disabled={busy||uploading} aria-describedby="comb-order-help">
     <legend>Execution order</legend>
     <p id="comb-order-help">Check how your pipelines will run before creating this experiment.</p>
     <div className="comb-order-options">
      {([{value:'all_pipelines_first',label:'All pipelines first',description:'Run each pipeline once, then start the next replicate cycle.'},{value:'pipeline_replicates_first',label:'One pipeline all replicates first',description:'Finish all replicates of one pipeline before starting the next.'}] as const).map(option=><label key={option.value} className={`comb-order-option ${executionOrder===option.value?'is-selected':''}`}>
       <input type="radio" name="comb-execution-order" aria-label={option.label} value={option.value} checked={executionOrder===option.value} onChange={()=>{setDraft(d=>({...d,combination_execution_order:option.value}));setReviewed(false);}}/>
       <span><strong>{option.label}</strong><small>{option.description}</small></span>
       {executionOrder===option.value&&<span className="comb-order-selected"><Check size={14} aria-hidden="true"/>Selected</span>}
      </label>)}
     </div>
    </fieldset>
    <label className="comb-consent comb-review-confirm"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/><span><strong>I reviewed the execution order, pipelines, replicates and model settings.</strong><small>Creation saves the design. Usage and costs begin when you select Run.</small></span></label>
   </section>}

   </div>
   {total>10000&&<p role="alert">Choose at most 10,000 total runs.</p>}{error&&<p role="alert">{error}</p>}
   <footer className="comb-footer"><div className="comb-next-help" id="comb-next-help" role="status" aria-live="polite"><strong>{busy?'Saving…':uploading?'Saving skill…':blocker?'To continue':'Ready to continue'}</strong><span>{blocker||(step===2?'Create pipeline saves your design. Select Run afterward to start.':`Select ${nextLabel} to continue.`)}</span>{step===2&&<span className="comb-order-footer">Execution order: {executionOrderLabel}</span>}</div><div className="comb-footer-actions">{step>0&&<button disabled={busy||uploading} onClick={back}><ArrowLeft size={16}/>Back</button>}{step<2?<button className="comb-primary" aria-describedby="comb-next-help" disabled={!!blocker} onClick={next}>{nextLabel}<ArrowRight size={16}/></button>:<button className="comb-primary" aria-label="Create combination design" aria-describedby="comb-next-help" disabled={!valid||busy||uploading} onClick={()=>void create(name.trim(),{...draft,combination_skills:effectiveSelected,ml_overrides:{},waves:total})}>{busy?'Creating…':'Create pipeline'}<Check size={16}/></button>}</div></footer>
  </div></ExperimentModelContext.Provider>
 </FloorDetailDialog>;
}
