import {useEffect, useState} from 'react';
import {resetResearchSkills,setResearchCorpusProfile} from '../lib/researchSkills';
import ResearchInputs, {type ResearchConfig, type Inspection} from './ResearchInputs';
import type {RunRequest} from '../store/control';

type Defaults={dataset_available:boolean;knowledge_available:boolean;target_column:string};
type Record = {corpus_skill_profile?:string;id:string;input_checks_passed:boolean;configuration:ResearchConfig};
export default function ResearchInputSelect({value,onChange,disabled=false,onValidityChange}:{value:Partial<RunRequest>;onChange:(patch:Partial<RunRequest>)=>void;disabled?:boolean;onValidityChange?:(error:string)=>void}) {
 const [defaults,setDefaults]=useState<Defaults|null>(null);
 const [records,setRecords]=useState<Record[]>([]),[error,setError]=useState(''),[editing,setEditing]=useState(false);
 const [newInput,setNewInput]=useState(false);
 async function reload(){try{const r=await fetch('/control/research-inputs');const d=await r.json();if(!r.ok||!Array.isArray(d.inputs))throw Error(d.error||'Invalid research input response');for(const record of d.inputs)if(record.corpus_skill_profile)setResearchCorpusProfile(record.id,record.corpus_skill_profile);setRecords(d.inputs);setError('');}catch{setError('Research inputs could not be loaded. Retry before selecting a study.');}}
 useEffect(()=>{void reload();void fetch('/control/health').then(r=>r.json()).then(d=>{
  if(typeof d.input_defaults?.dataset_available==='boolean'&&typeof d.input_defaults?.knowledge_available==='boolean')setDefaults(d.input_defaults);
 }).catch(()=>{});},[]);
 const selected=records.find(r=>r.id===value.research_input_id);
 const readinessError=value.research_input_id
  ? selected&&!selected.input_checks_passed?'Review the selected research input before continuing.':!selected?'Loading or locating the selected research input…':''
  : value.knowledge_mode!=='llm_only'&&defaults?.knowledge_available===false?'No deployment OKF is configured. Select or register a research input, or choose LLM knowledge only.'
  : value.data_mode!=='proposal'&&defaults?.dataset_available===false?'No deployment CSV is configured. Select or register a research input, or choose proposal mode.'
  : value.data_mode!=='proposal'&&!value.y_column?.trim()?'Specify the exact outcome column, or select a saved research input.'
  : value.data_mode==='proposal'&&!value.research_objective?.trim()?'Describe the research objective before continuing.':'';
 useEffect(()=>{onValidityChange?.(editing ? 'Check and use your data, or cancel editing before continuing.' : readinessError);},[editing,readinessError,onValidityChange]);
 function applyRecord(record:Record|undefined){const id=record?.id??'';
  const modes={knowledge_mode:record?.configuration.knowledge_mode??'okf' as const,data_mode:record?.configuration.data_mode??'dataset' as const};
  onChange({...resetResearchSkills(value,{research_input_id:id,...modes}),research_input_id:id,
  y_column:record?record.configuration.target.column:'',...modes,
  research_objective:record?.configuration.target.description??'',
  ...(id?{playbook_data:value.playbook_data&&value.playbook_data!=='data_exact_features'?value.playbook_data:'data_training_heavy'}:{})});}
 function select(id:string){setEditing(false);setNewInput(false);applyRecord(records.find(r=>r.id===id));}
 async function savedRecord(record:Inspection){await reload();if(record.id&&record.input_checks_passed){applyRecord({...record,id:record.id});setEditing(false);}}
 return <div className="min-w-0 space-y-3 rounded border border-paper-line p-3">
  <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">Choose your data</h3><p className="text-sm text-slate-500">Use an existing study or upload your own CSV.</p></div><button type="button" className="rounded-lg border border-paper-line px-4 py-2 text-sm font-semibold hover:bg-slate-100 dark:hover:bg-slate-800" disabled={disabled} onClick={()=>{setNewInput(true);setEditing(true);}}>Upload new CSV</button></div>
  <label className="block text-sm">Existing study<select aria-label="Research inputs" className="mt-1 w-full min-w-0 rounded border border-paper-line bg-paper p-2" disabled={disabled} value={value.research_input_id??''} onChange={e=>select(e.target.value)}>
   <option value="">Server defaults (advanced)</option>
   {records.map(r=><option key={r.id} value={r.id} disabled={!r.input_checks_passed}>{r.configuration.name}{r.input_checks_passed?'':' — review needed'}</option>)}
   {value.research_input_id&&!selected&&<option value={value.research_input_id}>Saved research record unavailable</option>}
  </select></label>
  {!value.research_input_id&&!editing&&<details className="rounded-lg border border-paper-line p-3 text-sm"><summary className="cursor-pointer font-medium">Use server defaults</summary><div className="mt-3 space-y-3">
   <p className="text-sm">Server dataset: {defaults?(defaults.dataset_available?'available':'not configured'):'not verified'}. Knowledge source: {defaults?(defaults.knowledge_available?'available':'not configured'):'not verified'}.</p>
   <label className="block">Knowledge mode<select aria-label="Pipeline knowledge mode" className="w-full rounded border p-2" disabled={disabled} value={value.knowledge_mode??'okf'} onChange={e=>onChange({...resetResearchSkills(value,{knowledge_mode:e.target.value as RunRequest['knowledge_mode']}),knowledge_mode:e.target.value as RunRequest['knowledge_mode'],skill:''})}><option value="okf">Configured OKF corpus</option><option value="llm_only">LLM knowledge only — no corpus</option></select></label>
   <label className="block">Data mode<select aria-label="Pipeline data mode" className="w-full rounded border p-2" disabled={disabled} value={value.data_mode??'dataset'} onChange={e=>onChange({...resetResearchSkills(value,{data_mode:e.target.value as RunRequest['data_mode']}),data_mode:e.target.value as RunRequest['data_mode'],baseline_columns:[]})}><option value="dataset">Configured CSV — empirical evaluation</option><option value="proposal">No CSV — research proposal and analysis plan</option></select></label>
   {value.data_mode!=='proposal'&&<label className="block">Target column (Y)<input aria-label="Deployment target column" className="w-full rounded border p-2" disabled={disabled} value={value.y_column??''} placeholder='Enter the exact CSV outcome column' onChange={e=>onChange({y_column:e.target.value})}/><span className="text-sm">Choose Upload new CSV to set up your own data and target.</span></label>}
   {value.data_mode==='proposal'&&<label className="block">Research objective<textarea aria-label="Research objective" className="w-full rounded border p-2" disabled={disabled} value={value.research_objective??''} onChange={e=>onChange({research_objective:e.target.value})}/><span className="text-sm">No model fitting or measured metrics will be produced.</span></label>}
  </div></details>}
  {selected&&!editing&&<p className="text-sm">Knowledge: {selected.configuration.knowledge_mode==='llm_only'?'Model knowledge; no retrieval':'Selected OKF corpus'}. Data: {selected.configuration.data_mode==='proposal'?'Proposal only; empirical evaluation not executed':'CSV evaluation'}.</p>}
  {selected&&!editing&&<details className="text-sm"><summary>Selected CSV and OKF files</summary><dl className="mt-2 space-y-2">
   <div><dt className="font-semibold">Dataset CSV</dt><dd className="break-all">{selected.configuration.data_mode==='proposal'?'No CSV — proposal only':selected.configuration.dataset_path||'Path unavailable in this record'}</dd></div>
   <div><dt className="font-semibold">OKF corpus folder</dt><dd className="break-all">{selected.configuration.knowledge_mode==='llm_only'?'No corpus — model knowledge only':selected.configuration.knowledge_path||'Path unavailable in this record'}</dd></div>
  </dl></details>}
  {selected&&!editing&&<p className="break-words text-sm">Objective: {selected.configuration.target.description} {selected.configuration.target.column&&<>Target: {selected.configuration.target.column}. </>}Predictor timing: {selected.configuration.target.prediction_time||'To be specified in the research plan'}.</p>}
  {selected&&!editing&&<p className="text-sm">Positive label: {selected.configuration.target.positive_label||'Not specified'}. Negative label: {selected.configuration.target.negative_label||'Not specified'}. Horizon: {selected.configuration.target.horizon||'Not established'}.</p>}
  {readinessError&&!editing&&<p role="alert" className="text-sm">{readinessError}</p>}
  {error&&<p role="alert">{error} <button type="button" onClick={()=>void reload()}>Retry</button></p>}
  {selected&&!editing&&<button type="button" disabled={disabled} className="rounded-lg border border-paper-line px-3 py-2 text-sm" onClick={()=>{setNewInput(false);setEditing(true);}}>Edit data & target</button>}
  {editing&&<div className="border-t border-paper-line pt-3"><div className="flex items-center justify-between gap-3"><h4 className="font-semibold">{newInput?'Set up your CSV':'Edit study inputs'}</h4><button type="button" disabled={disabled} className="text-sm underline" onClick={()=>setEditing(false)}>Cancel editing</button></div><ResearchInputs key={newInput?'new':selected?.id??'new'} initialConfig={newInput?undefined:selected?.configuration} disabled={disabled} onSaved={record=>void savedRecord(record)}/></div>}
  {selected&&editing&&!newInput&&<p className="text-sm">Changes apply to new runs only.</p>}
 </div>;
}
