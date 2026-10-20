import {useEffect,useState} from 'react';
import FloorDetailDialog from './FloorDetailDialog';
import {DEFAULT_REQUEST,type SkillInfo} from '../store/control';
import {usePipelines} from '../store/pipelines';
import {useViewer,type ViewId} from '../store/viewer';
import {setCorpusSkillBindings,setResearchCorpusProfile} from '../lib/researchSkills';
import {quickResearchConfiguration} from '../lib/guidedStudy';
import type {ResearchConfig} from './ResearchInputs';

type Study={id:string;input_checks_passed:boolean;corpus_skill_profile?:string;configuration:ResearchConfig};
const button='min-h-11 rounded-lg border border-paper-line px-4 py-2 text-sm disabled:opacity-40';
const primary=`${button} bg-accent text-accent-contrast`;
export default function GuidedStudyWizard({back}:{back:()=>void}) {
 const [studies,setStudies]=useState<Study[]>([]),[selected,setSelected]=useState(''),[step,setStep]=useState(0);
 const [loading,setLoading]=useState(true),[loadError,setLoadError]=useState(''),[reviewed,setReviewed]=useState(false),[name,setName]=useState('');
 const [pipelineId,setPipelineId]=useState<string|null>(null);
 const state=usePipelines();
 const [catalog,setCatalog]=useState<SkillInfo[]>([]);
 async function load(){setLoading(true);setLoadError('');try{
  const [response,skillsResponse]=await Promise.all([fetch('/control/research-inputs'),fetch('/control/playbooks')]);
  const data=await response.json(),skills=await skillsResponse.json();
  if(!response.ok||!Array.isArray(data.inputs))throw Error('Registered studies could not be loaded.');
  if(!skillsResponse.ok||!Array.isArray(skills.catalog))throw Error('Agent skills could not be loaded.');
  setCorpusSkillBindings(skills.corpus_skill_bindings);setCatalog(skills.catalog);
  for(const record of data.inputs)if(record.corpus_skill_profile)setResearchCorpusProfile(record.id,record.corpus_skill_profile);
  setStudies(data.inputs);
 }catch{setLoadError('Study inputs could not be loaded. Retry, or prepare your inputs from the setup menu.');}finally{setLoading(false);}}
 useEffect(()=>{void load();},[]);
 const study=studies.find(s=>s.id===selected);
 let draft:ReturnType<typeof quickResearchConfiguration>|null=null,setupError='';
 if(study)try{draft=quickResearchConfiguration(DEFAULT_REQUEST,study,catalog);}catch(error){setupError=(error as Error).message;}
 const pipeline=state.items.find(p=>p.id===pipelineId);
 const pending=state.pendingStart?.pipelineId===pipelineId;
 function openView(view:ViewId){if(pipelineId)state.select(pipelineId);state.closeCreation();useViewer.getState().setView(view);}
 async function create(){if(!draft||!reviewed)return;if(await state.create(name.trim(),draft,{keepOpen:true})){setPipelineId(usePipelines.getState().selected);setStep(2);}}
 async function start(){if(!pipelineId)return;const started=await state.play(pipelineId);if(started||usePipelines.getState().pendingStart?.pipelineId===pipelineId)setStep(3);}
 const complete=!pipeline?.running&&pipeline?.latest?.exit_code===0&&pipeline?.progress.exploration?.outcome==='completed';
 return <FloorDetailDialog title="Start a guided study" dismissible={!state.busy} close={()=>state.closeCreation()} className="quick-research-dialog">
  <div className="flex min-w-0 flex-col gap-4 p-1">
   <ol aria-label="Guided study steps" className="grid grid-cols-[repeat(2,minmax(0,1fr))] gap-2 text-sm sm:grid-cols-4">{['Choose study','Review target','Run once','View results'].map((label,i)=><li key={label} aria-current={step===i?'step':undefined} className={`rounded-lg border p-2 ${step===i?'border-accent bg-accent/10 font-semibold':'border-paper-line text-ink-soft'}`}>{i+1}. {label}</li>)}</ol>
   {step===0&&<>
    <h3 className="text-lg font-semibold">Which study would you like to try?</h3>
    <p className="text-sm">Choose the bundled Heart failure demonstration or your own registered study. One run will generate a hypothesis and follow it through the available analysis stages.</p>
    <label className="grid gap-2 text-sm">Study<select aria-label="Guided study" className="min-h-11 w-full min-w-0 rounded-lg border border-paper-line p-2" value={selected} disabled={loading} onChange={e=>{setSelected(e.target.value);setReviewed(false);const s=studies.find(s=>s.id===e.target.value);setName(s?`${s.configuration.name} — first run`.slice(0,80):'');}}><option value="">{loading?'Loading studies…':'Choose a registered study'}</option>{studies.map(s=><option key={s.id} value={s.id} disabled={!s.input_checks_passed}>{s.configuration.name}{!s.input_checks_passed?' — inputs need review':''}</option>)}</select></label>
    {!loading&&!studies.length&&!loadError&&<p>No registered studies are available. Return to setup and choose Prepare research inputs. The bundled example is registered by ./start.sh.</p>}
    {loadError&&<p role="alert">{loadError} <button className="underline" onClick={()=>void load()}>Retry</button></p>}
    <div className="flex flex-wrap justify-between gap-2"><button className={button} onClick={back}>Back to setup</button><button className={primary} disabled={loading||!!loadError||!study?.input_checks_passed} onClick={()=>setStep(1)}>Review study</button></div>
   </>}
   {step===1&&study&&<>
    <h3 className="text-lg font-semibold">Confirm what this run will study</h3>
    <dl className="grid gap-3 rounded-lg border border-paper-line p-3 text-sm break-words">
     <div><dt className="font-semibold">Research objective</dt><dd>{study.configuration.target.description||'Not provided'}</dd></div>
     <div><dt className="font-semibold">Prediction target</dt><dd>{study.configuration.data_mode==='proposal'?'Proposal only — no fitted model':study.configuration.target.column}</dd></div>
     {study.configuration.data_mode!=='proposal'&&<div><dt className="font-semibold">Target labels</dt><dd>Positive: {study.configuration.target.positive_label||'Not specified'} · Negative: {study.configuration.target.negative_label||'Not specified'}</dd></div>}
     <div><dt className="font-semibold">Knowledge</dt><dd>{study.configuration.knowledge_mode==='llm_only'?'Model knowledge only; no corpus retrieval':'Registered OKF corpus'}</dd></div>
    </dl>
    <p className="text-sm">{study.configuration.data_mode==='proposal'?'This produces a research proposal, not measured model performance.':'One Loop · Logistic regression · Training-heavy split · SHAP interpretation.'} For research and software demonstration, not clinical decisions.</p>
    <details className="rounded-lg border border-paper-line p-3 text-sm"><summary className="cursor-pointer font-semibold">View selected agent skills and source paths</summary><div className="mt-3 space-y-2 break-words"><p>CSV: {study.configuration.dataset_path||'None'}</p><p>OKF: {study.configuration.knowledge_path||'None'}</p>{draft&&Object.entries(draft.combination_skills??{}).map(([role,ids])=><p key={role}>{role}: {catalog.find(s=>s.id===ids[0])?.title}</p>)}<p>One Loop · one split evaluation · no user-fixed model overrides. Model deployments come from the server’s agent-specific settings.</p></div></details>
    {setupError&&<p role="alert">{setupError} <button className="underline" onClick={()=>void load()}>Reload</button></p>}
    <label className="grid gap-2 text-sm">Pipeline name<input className="min-h-11 w-full rounded-lg border p-2" maxLength={80} value={name} onChange={e=>setName(e.target.value)}/></label>
    <label className="flex items-start gap-3 text-sm"><input className="mt-1" type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I checked the study, target and default analysis. Creating this pipeline does not start a paid model request.</label>
    <div className="flex flex-wrap justify-between gap-2"><button className={button} disabled={state.busy} onClick={()=>setStep(0)}>Back</button><button className={primary} disabled={state.busy||loading||!!loadError||!draft||!reviewed||!name.trim()} onClick={()=>void create()}>{state.busy?'Creating…':'Create one-run pipeline'}</button></div>
   </>}
   {step===2&&<>
    <h3 className="text-lg font-semibold">Ready for one run</h3><p>Your pipeline is saved. Start it when you are ready. This sends requests to your configured models and may incur usage charges. It attempts one hypothesis Loop; internal retries may make multiple model calls.</p>
    <button className={primary} disabled={state.busy||!!state.pendingStart} onClick={()=>void start()}>{state.busy?'Starting…':'Start one run'}</button>
    <button className={button} onClick={()=>openView('scene')}>Inspect saved pipeline without running</button>
   </>}
   {step===3&&<>
    <h3 className="text-lg font-semibold">{pending?'Confirming the start request':complete?'Recorded run completed':'Follow your run and its results'}</h3>
    <p>{pending?'The response was delayed. The app is checking server status; do not start another copy.':complete?'Open the report and review the measured evidence and limitations.':'The Floor plan shows the latest recorded execution state and any failure details. Results appear as agents save their outputs; opening a view does not confirm completion.'}</p>
    <div className="grid gap-2 sm:grid-cols-2"><button className={primary} onClick={()=>openView('scene')}>Track progress</button><button className={button} onClick={()=>openView('report')}>Open final report</button></div>
   </>}
   {step>0&&loadError&&<p role="alert">{loadError}</p>}
   {state.error&&<p role="alert" className="text-sm break-words">{state.error}</p>}
  </div>
 </FloorDetailDialog>;
}
