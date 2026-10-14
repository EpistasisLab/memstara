import {useEffect, useState} from 'react';
import {resetResearchSkills} from '../lib/researchSkills';
import ResearchInputs from './ResearchInputs';
import type {RunRequest} from '../store/control';

type Record = {id:string;input_checks_passed:boolean;configuration:{name:string;knowledge_mode?:'okf'|'llm_only';data_mode?:'dataset'|'proposal';target:{column:string;description:string;prediction_time:string}}};
export default function ResearchInputSelect({value,onChange,disabled=false}:{value:Partial<RunRequest>;onChange:(patch:Partial<RunRequest>)=>void;disabled?:boolean}) {
 const [records,setRecords]=useState<Record[]>([]),[error,setError]=useState(''),[editing,setEditing]=useState(false);
 async function reload(){try{const r=await fetch('/control/research-inputs');const d=await r.json();if(!r.ok||!Array.isArray(d.inputs))throw Error(d.error||'Invalid research input response');setRecords(d.inputs);setError('');}catch{setError('Research inputs could not be loaded. Retry before selecting a study.');}}
 useEffect(()=>{void reload();},[]);
 const selected=records.find(r=>r.id===value.research_input_id);
 function select(id:string){const record=records.find(r=>r.id===id);onChange({...resetResearchSkills(),research_input_id:id,
  y_column:record?.configuration.target.column||'outcome',
  knowledge_mode:record?.configuration.knowledge_mode??'okf',data_mode:record?.configuration.data_mode??'dataset',
  research_objective:record?.configuration.target.description??'',
  ...(id?{combination_skills:{},playbook_hypothesis:'hypothesis_general',playbook_data:value.playbook_data&&value.playbook_data!=='data_exact_features'?value.playbook_data:'data_training_heavy',playbook_explanation:'report_general'}:{})});}
 return <div className="min-w-0 space-y-3 rounded border border-paper-line p-3">
  <label className="block">Research inputs<select aria-label="Research inputs" className="mt-1 w-full min-w-0 rounded border border-paper-line bg-paper p-2" disabled={disabled} value={value.research_input_id??''} onChange={e=>select(e.target.value)}>
   <option value="">Deployment inputs — configure paths and target explicitly</option>
   {records.map(r=><option key={r.id} value={r.id} disabled={!r.input_checks_passed}>{r.configuration.name} · {r.id.slice(0,8)}{r.input_checks_passed?'':' — review needed'}</option>)}
   {value.research_input_id&&!selected&&<option value={value.research_input_id}>Saved research record unavailable</option>}
  </select></label>
  {!value.research_input_id&&<div className="space-y-2">
   <label className="block">Knowledge mode<select aria-label="Pipeline knowledge mode" className="w-full rounded border p-2" disabled={disabled} value={value.knowledge_mode??'okf'} onChange={e=>onChange({...resetResearchSkills(),knowledge_mode:e.target.value as RunRequest['knowledge_mode'],skill:'',playbook_hypothesis:'hypothesis_general',playbook_explanation:'report_general'})}><option value="okf">Configured OKF corpus</option><option value="llm_only">LLM knowledge only — no corpus</option></select></label>
   <label className="block">Data mode<select aria-label="Pipeline data mode" className="w-full rounded border p-2" disabled={disabled} value={value.data_mode??'dataset'} onChange={e=>onChange({...resetResearchSkills(),data_mode:e.target.value as RunRequest['data_mode'],baseline_columns:[],playbook_hypothesis:'hypothesis_general',playbook_explanation:'report_general'})}><option value="dataset">Configured CSV — empirical evaluation</option><option value="proposal">No CSV — research proposal and analysis plan</option></select></label>
   {value.data_mode==='proposal'&&<label className="block">Research objective<textarea aria-label="Research objective" className="w-full rounded border p-2" disabled={disabled} value={value.research_objective??''} onChange={e=>onChange({research_objective:e.target.value})}/><span className="text-sm">No model fitting or measured metrics will be produced.</span></label>}
  </div>}
  {selected&&<p className="text-sm">Knowledge: {selected.configuration.knowledge_mode==='llm_only'?'Model knowledge; no retrieval':'Selected OKF corpus'}. Data: {selected.configuration.data_mode==='proposal'?'Proposal only; empirical evaluation not executed':'CSV evaluation'}.</p>}
  {selected&&<p className="break-words text-sm">Objective: {selected.configuration.target.description} {selected.configuration.target.column&&<>Target: {selected.configuration.target.column}. </>}Predictor timing: {selected.configuration.target.prediction_time||'To be specified in the research plan'}. {selected.configuration.knowledge_mode!=='llm_only'&&'The selected corpus is available for retrieval. '}Available files and execution settings are checked again before execution.</p>}
  {selected&&<p className="text-sm">Changing research inputs resets source filters, fixed baseline columns and domain-specific Hypothesis/Explanation defaults. Review every selected skill for compatibility; existing execution records stay unchanged.</p>}
  {error&&<p role="alert">{error} <button type="button" onClick={()=>void reload()}>Retry</button></p>}
  <button type="button" disabled={disabled} className="underline" onClick={()=>setEditing(!editing)}>{editing?'Close input editor':'Register or revise research inputs'}</button>
  {editing&&<ResearchInputs onSaved={()=>void reload()}/>}
 </div>;
}
