import {useEffect, useState} from 'react';
import {ArrowUpRight, Check, Database, FileUp, ShieldCheck} from 'lucide-react';
import './research-inputs.css';
import {resetResearchSkills,setResearchCorpusProfile} from '../lib/researchSkills';
import ResearchInputs, {type Inspection} from './ResearchInputs';
import ResearchInputFeedback, {type InputFeedback} from './ResearchInputFeedback';
import ResearchStudyLibrary, {type SavedStudy} from './ResearchStudyLibrary';
import type {RunRequest} from '../store/control';

type Record = SavedStudy;
export default function ResearchInputSelect({value,onChange,disabled=false,onValidityChange}:{value:Partial<RunRequest>;onChange:(patch:Partial<RunRequest>)=>void;disabled?:boolean;onValidityChange?:(error:string)=>void}) {
 const [feedback,setFeedback]=useState<InputFeedback|null>(null);
 const [records,setRecords]=useState<Record[]>([]),[error,setError]=useState(''),[editing,setEditing]=useState(false);
 const [browsingSaved,setBrowsingSaved]=useState(false);
 const [newInput,setNewInput]=useState(false);
 const [sourceChoice,setSourceChoice]=useState<'existing'|'upload'>();
 const [uploadedRecordId,setUploadedRecordId]=useState<string>();
 const [reviewId,setReviewId]=useState<string>();
 const reviewRecord=records.find(record=>record.id===reviewId);
 async function reload(){try{const r=await fetch('/control/research-inputs');const d=await r.json();if(!r.ok||!Array.isArray(d.inputs))throw Error(d.error||'Invalid research input response');for(const record of d.inputs)if(record.corpus_skill_profile)setResearchCorpusProfile(record.id,record.corpus_skill_profile);setRecords(d.inputs);setError('');}catch{setError('Research inputs could not be loaded. Retry before selecting a study.');}}
 useEffect(()=>{void reload();},[]);
 const selected=records.find(r=>r.id===value.research_input_id);
 const selectedWasUploaded=!!selected&&(selected.id===uploadedRecordId||/[/\\]uploads[/\\][a-f0-9]{32}[/\\]dataset\.csv$/.test(selected.configuration.dataset_path??''));
 const uploadSelected=sourceChoice?sourceChoice==='upload':selectedWasUploaded;
 const readinessError=value.research_input_id
  ? selected&&!selected.input_checks_passed?'Review the selected research input before continuing.':!selected?'Loading or locating the selected research input…':''
  : 'Select saved data or upload a CSV to continue.';
 useEffect(()=>{onValidityChange?.(editing ? 'Check and use your data, or cancel editing before continuing.' : readinessError);},[editing,readinessError,onValidityChange]);
 function applyRecord(record:Record|undefined){const id=record?.id??'';
  const modes={knowledge_mode:record?.configuration.knowledge_mode??'okf' as const,data_mode:record?.configuration.data_mode??'dataset' as const};
  onChange({...resetResearchSkills(value,{research_input_id:id,...modes}),research_input_id:id,
  y_column:record?record.configuration.target.column:'',...modes,
  research_objective:record?.configuration.target.description??'',
  ...(id?{playbook_data:value.playbook_data&&value.playbook_data!=='data_exact_features'?value.playbook_data:'data_training_heavy'}:{})});}
 function select(id:string){setBrowsingSaved(false);setSourceChoice('existing');setEditing(false);setNewInput(false);setReviewId(undefined);applyRecord(records.find(r=>r.id===id));}
 async function savedRecord(record:Inspection){await reload();if(record.id&&record.input_checks_passed){setBrowsingSaved(false);if(newInput||uploadSelected){setUploadedRecordId(record.id);setSourceChoice('upload');}setRecords(current=>[...current.filter(item=>item.id!==record.id),{...record,id:record.id!}]);applyRecord({...record,id:record.id});setEditing(false);}}
 return <div className="research-input-shell">
  <div className="research-source-options" role="group" aria-label="Data source">
   <button type="button" className={`research-source-option ${!uploadSelected?'is-active':''}`} aria-pressed={!uploadSelected} disabled={disabled} onClick={()=>{setBrowsingSaved(true);setSourceChoice('existing');setEditing(false);setNewInput(false);setReviewId(undefined);}}>
    <span className="research-source-icon"><Database size={21}/></span><span className="research-source-copy"><strong>Use saved data</strong><small>Choose data you have already checked.</small></span><span className="research-source-check">{(!uploadSelected)?<Check size={16}/>:null}</span>
   </button>
   <button type="button" aria-label="Upload new CSV" className={`research-source-option ${uploadSelected?'is-active':''}`} aria-pressed={uploadSelected} disabled={disabled} onClick={()=>{setBrowsingSaved(false);setSourceChoice('upload');setReviewId(undefined);setNewInput(true);setEditing(true);}}>
    <span className="research-source-icon"><FileUp size={21}/></span><span className="research-source-copy"><strong>Upload a new CSV</strong><small>Choose a file and confirm what to predict.</small></span><span className="research-source-check">{uploadSelected?<Check size={16}/>:<ArrowUpRight size={17} className="research-option-arrow"/>}</span>
   </button>
  </div>
  {!editing&&!browsingSaved&&selected&&<section className="research-selected" aria-label="Selected dataset">
   <header><span className="research-section-label">YOUR DATASET</span><span className={`research-ready ${selected.input_checks_passed?'is-ready':''}`}><ShieldCheck size={14}/>{selected.input_checks_passed?'Input checks passed':'Needs review'}</span></header>
   <h3>{selected.configuration.name}</h3>
   <dl className="research-data-facts">
    <div><dt>Data file</dt><dd>{selected.configuration.data_mode==='proposal'?'Research proposal':selected.configuration.dataset_path?.split(/[\\/]/).pop()||'Not specified'}</dd></div>
    <div><dt>Prediction target</dt><dd>{selected.configuration.target.column||'Not set'}</dd></div>
    <div><dt>Knowledge source</dt><dd>{selected.configuration.knowledge_mode==='llm_only'?'LLM only': selected.configuration.knowledge_path?.includes('/heart-failure/okf')?'Heart failure research library':'Research documents'}</dd></div>
   </dl>
   <footer><p>Your data is selected. Choose skills below to continue.</p><button type="button" className="research-secondary-button" disabled={disabled} onClick={()=>{setReviewId(undefined);setNewInput(false);setEditing(true);}}>Edit data & target</button></footer>
  </section>}
  {!editing&&(selected&&!browsingSaved?<details className="research-library-disclosure"><summary>Change dataset <span>{records.length} saved</span></summary><ResearchStudyLibrary studies={records} selectedId={value.research_input_id} disabled={disabled} onSelect={select} onReview={id=>{setSourceChoice('existing');setReviewId(id);setNewInput(false);setEditing(true);}}/></details>:<ResearchStudyLibrary studies={records} selectedId={value.research_input_id} disabled={disabled} onSelect={select} onReview={id=>{setSourceChoice('existing');setReviewId(id);setNewInput(false);setEditing(true);}}/>)}
  {!editing&&value.research_input_id&&!selected&&<p role="status" className="text-sm">Loading the selected study…</p>}
  {readinessError&&!editing&&value.research_input_id&&<p role="status" className="text-sm">{readinessError}</p>}
  {error&&<p role="alert">{error} <button type="button" onClick={()=>void reload()}>Retry</button></p>}
  {editing&&<div className="research-input-editor"><div className="research-editor-heading"><h4 className="font-semibold">{newInput?'Set up your CSV':'Edit study inputs'}</h4><button type="button" disabled={disabled} className="text-sm underline" onClick={()=>{setEditing(false);setSourceChoice(undefined);}}>Cancel editing</button></div><ResearchInputs key={newInput?'new':reviewRecord?.id??selected?.id??'new'} initialConfig={newInput?undefined:(reviewRecord??selected)?.configuration} disabled={disabled} onSaved={savedRecord} onFeedback={setFeedback}/></div>}
  {feedback&&<ResearchInputFeedback feedback={feedback} onClose={()=>setFeedback(null)}/>}
  {selected&&editing&&!newInput&&<p className="text-sm">Changes apply to new runs only.</p>}
 </div>;
}
