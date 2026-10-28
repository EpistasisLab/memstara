import {useId,useState} from 'react';
import {csvClassValues} from './csvClassValues';
import {automaticPredictorTypes} from './automaticPredictorTypes';
import KnowledgeModelInfo from './KnowledgeModelInfo';
import {UploadCloud, FileUp, CheckCircle2, AlertTriangle, CircleAlert} from 'lucide-react';
import './research-inputs.css';
import ResearchInputFeedback, {type InputFeedback} from './ResearchInputFeedback';

type Target={column:string;description:string;positive_label:string;negative_label:string;prediction_time:string;horizon:string};
export type ResearchConfig={name:string;dataset_path:string;knowledge_path:string;target:Target;excluded_columns:string[];missing_policy:'reject'|'impute_train_v1';categorical_columns?:string[];predictor_types?:Record<string,'continuous'|'categorical'>;knowledge_mode?:'okf'|'llm_only';data_mode?:'dataset'|'proposal'};
export type Inspection={id?:string;configuration:ResearchConfig;fingerprint:string;input_checks_passed:boolean;execution_ready:boolean;execution_note:string;
 dataset:{rows:number;column_count:number;columns:string[];missing_cells:number;eligible_predictor_count:number};
 knowledge:{documents:number;domains:string[]};issues:{code:string;message:string}[]};
const initial:ResearchConfig={name:'',dataset_path:'',knowledge_path:'',target:{column:'',description:'',positive_label:'',negative_label:'',prediction_time:'',horizon:''},excluded_columns:[],missing_policy:'reject',predictor_types:{}};
type UploadInspection={dataset_path:string;columns:string[];rows:number;missing_cells:number;columns_with_missing:Record<string,number>;message:string;nonfinite_columns:string[];nonnumeric_columns?:string[];binary_columns?:string[];column_kinds?:Record<string,string>;type_confirmation_columns?:string[];suggested_predictor_types?:Record<string,'continuous'|'categorical'>;column_examples?:Record<string,(string|number)[]>;setup_options?:{knowledge_sources:{label:string;path:string}[];preset:{name:string;target:Target;categorical_columns:string[];knowledge_path:string}|null}};
const style='w-full min-w-0 rounded border border-paper-line bg-paper px-3 py-2 text-sm';

export default function ResearchInputs({onSaved,onFeedback,initialConfig,disabled=false}:{onSaved?:(record:Inspection)=>void|Promise<void>;onFeedback?:(feedback:InputFeedback)=>void;initialConfig?:ResearchConfig;disabled?:boolean}={}){
 const knowledgePathHelpId=useId();
 const [feedback,setFeedback]=useState<InputFeedback|null>(null);
 function notify(feedback:InputFeedback){if(onFeedback)onFeedback(feedback);else setFeedback(feedback);}
 const [form,setForm]=useState<ResearchConfig>(initialConfig??initial),[result,setResult]=useState<Inspection|null>(null);
 const [uploaded,setUploaded]=useState<UploadInspection|null>(null);
 const [dragging,setDragging]=useState(false);
 const [filename,setFilename]=useState('');
 const [classValues,setClassValues]=useState<Record<string,string[]>|null>(null);
 const savedTarget=initialConfig?.target;
 const outcomeValues=classValues?.[form.target.column]??(savedTarget?.column===form.target.column&&savedTarget?.positive_label&&savedTarget?.negative_label&&savedTarget.positive_label!==savedTarget.negative_label?[savedTarget.positive_label,savedTarget.negative_label]:undefined);
 const invalidOutcome=!!form.target.column&&!!classValues&&outcomeValues?.length!==2;
 const [customKnowledge,setCustomKnowledge]=useState(!!initialConfig?.knowledge_path&&!initialConfig.knowledge_path.replace(/\\/g,'/').endsWith('/heart-failure/okf'));
 const sources=uploaded?.setup_options?.knowledge_sources??[{label:'Heart failure research library',path:'/app/examples/heart-failure/okf'}];
 const requiredDetails=[invalidOutcome?'Binary outcome column':'',!form.name.trim()?'Study name':'',!form.dataset_path.trim()&&form.data_mode!=='proposal'?'CSV file':'',form.data_mode==='proposal'&&!form.target.description.trim()?'Research objective':'',...(form.data_mode==='proposal'?[]:[!form.target.column?'Outcome column':'',!outcomeValues?'CSV class values':'']),form.knowledge_mode!=='llm_only'&&!form.knowledge_path.trim()?'Knowledge source':''].filter(Boolean);
 function chooseTarget(column:string){
  const values=classValues?.[column];
  // Stable encoding, independent of row order; this does not infer class meaning.
  const sorted=values?.length===2?[...values].sort():[];
  const target=!classValues&&savedTarget?.column===column?{...savedTarget}:{...initial.target,column,positive_label:sorted[1]??'',negative_label:sorted[0]??''};
  edit({...form,excluded_columns:form.excluded_columns.filter(value=>value!==column),target});
 }
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 function edit(next:ResearchConfig){setForm({...next,categorical_columns:(next.categorical_columns??[]).filter(column=>column!==next.target.column&&!next.excluded_columns.includes(column))});setResult(null);setError('');}
 async function upload(file:File){
  if(busy||disabled)return;
  setBusy(true);setError('');setResult(null);setUploaded(null);setClassValues(null);setFilename('');
  try{
   if(!file.name.toLowerCase().endsWith('.csv'))throw Error('Choose a CSV file.');
   if(file.size>5*1024*1024)throw Error('CSV upload limit is 5 MiB.');
   const content=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Could not read CSV'));reader.readAsDataURL(file);});
   const response=await fetch('/control/research-inputs/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,content_base64:content})});
   const data=await response.json();if(!response.ok)throw Error(data.error||'Upload failed');
   setClassValues(csvClassValues(await file.text()));setUploaded(data);setFilename(file.name);setForm(f=>({...f,dataset_path:data.dataset_path,missing_policy:'reject',categorical_columns:[],predictor_types:automaticPredictorTypes(data),excluded_columns:[],target:{...initial.target},name:file.name.replace(/\.csv$/i,'').trim()||'Uploaded dataset'}));
  }catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function submit(action:'register'){
  if(requiredDetails.length){
   const guidance:Record<string,string>={'Study name':'Enter a study name.','CSV file':'Upload a CSV file.','Research objective':'Describe the research objective for your plan.','Outcome column':'Choose the outcome column you want to predict.','Binary outcome column':'Choose an outcome column with exactly two distinct non-missing values. This workflow supports binary classification.','CSV class values':'Upload the CSV to read the values in the selected target column.','Knowledge source':'Choose the included library, LLM only, or enter the full path to your research document folder.'};
   setResult(null);setError(`Please complete: ${requiredDetails.join(', ')}.`);
   notify({ready:false,messages:requiredDetails.map(item=>guidance[item]??item)});return;
  }
  setBusy(true);setError('');setResult(null);
  try{const r=await fetch(`/control/research-inputs/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...form,...(form.predictor_types?{predictor_types:Object.fromEntries(Object.entries(form.predictor_types).filter(([column])=>column!==form.target.column&&!form.excluded_columns.includes(column)))}:{}),target:form.data_mode==='proposal'?form.target:{...form.target,negative_label:outcomeValues?.find(value=>value!==form.target.positive_label)??form.target.negative_label}})});
   const d=await r.json();if(!r.ok)throw Error(d.error||'The check could not be completed. Please try again.');setResult(d);
   if(d.input_checks_passed){await onSaved?.(d);notify({ready:true,messages:[]});}
   else notify({ready:false,messages:d.issues?.length?d.issues.map((issue:{message:string})=>issue.message):['The input check did not pass. Review your CSV and outcome settings.']});
  }catch(e){const message=e instanceof Error?e.message:String(e);setError(message);notify({ready:false,messages:[message]});}finally{setBusy(false);}
 }
 return <section className="research-setup min-w-0 space-y-5 p-4 sm:p-5" aria-label="Research input preparation">
  <p className="research-setup-intro">Choose a CSV. We’ll check it and guide you through the next step.</p>
  <fieldset disabled={busy||disabled} className="research-setup-fields min-w-0 space-y-5">
   {form.data_mode==='proposal'&&<p>Without a dataset, this creates an analysis plan, not measured results. Describe your research objective below.</p>}
   {form.data_mode!=='proposal'&&<div className="space-y-3">
    <h4 className="text-sm font-semibold">1 · Upload your CSV</h4>
    <div role="group" aria-label="CSV upload area" aria-disabled={busy||disabled}
      onDragEnter={event=>{event.preventDefault();if(!busy&&!disabled)setDragging(true);}}
      onDragOver={event=>{event.preventDefault();event.dataTransfer.dropEffect=busy||disabled?'none':'copy';}}
      onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setDragging(false);}}
      onDrop={event=>{event.preventDefault();setDragging(false);if(busy||disabled)return;const files=event.dataTransfer.files;if(files.length!==1){setError('Drop one CSV file at a time.');return;}void upload(files[0]);}}
      className={`research-upload-dropzone ${uploaded?'is-uploaded':''} rounded-xl border-2 border-dashed p-5 text-center transition-colors ${dragging?'border-sky-500 bg-sky-50 dark:bg-sky-950/30':'border-paper-line bg-paper'}`}>
      <UploadCloud size={26} className="mx-auto mb-2 text-slate-500" aria-hidden="true"/>
      <p className="text-sm font-semibold">{dragging?'Drop your CSV here':'Drag your CSV here'}</p>
      <p className="research-upload-format">UTF-8 CSV · up to 5 MiB</p>
      <div className="research-file-action">
       <label className="research-file-picker"><FileUp size={16} aria-hidden="true"/><span>{busy?'Uploading…':uploaded?'Change CSV':'Choose CSV file'}</span><input type="file" accept=".csv,text/csv" aria-label="Upload CSV" onChange={event=>{const file=event.target.files?.[0];if(file)void upload(file);event.target.value='';}}/></label>
       {filename&&<span className="research-file-name">{filename}</span>}
      </div>
      <p className="mt-3 text-xs text-slate-500">We check for missing values as soon as the file uploads.</p>
    </div>
    {uploaded&&<div role="status" className={`research-upload-status ${uploaded.nonfinite_columns.length?'is-error':uploaded.missing_cells?'is-warning':'is-success'}`}>
     <div className="research-upload-status-heading">{uploaded.nonfinite_columns.length?<CircleAlert size={22} aria-hidden="true"/>:uploaded.missing_cells?<AlertTriangle size={22} aria-hidden="true"/>:<CheckCircle2 size={22} aria-hidden="true"/>}<div><strong>{uploaded.nonfinite_columns.length?'CSV needs correction':uploaded.missing_cells?'Missing values found':'No missing values found'}</strong><p>{uploaded.rows.toLocaleString()} rows · {uploaded.columns.length} columns</p></div></div>
     {uploaded.missing_cells>0?<><p className="research-upload-count">{uploaded.missing_cells.toLocaleString()} empty {uploaded.missing_cells===1?'cell':'cells'} across {Object.keys(uploaded.columns_with_missing).length.toLocaleString()} {Object.keys(uploaded.columns_with_missing).length===1?'column':'columns'}</p><p>Review the affected columns, then choose how to handle missing values below. Uploading your file does not fill these gaps.</p></>:<p>No empty cells detected. Continue with the outcome and knowledge source settings below.</p>}
     {uploaded.missing_cells>0&&<details className="research-upload-findings"><summary>View columns with missing values</summary><dl>{Object.entries(uploaded.columns_with_missing).map(([column,count])=><div key={column}><dt>{column}</dt><dd>{count.toLocaleString()} missing</dd></div>)}</dl></details>}
     {uploaded.nonfinite_columns.length>0&&<p role="alert" className="research-input-error">Replace infinite values with valid values in your CSV, then upload it again. Affected columns: {uploaded.nonfinite_columns.join(', ')}</p>}
     {!!uploaded.nonnumeric_columns?.length&&<p className="research-setup-help">Text columns detected. We’ll check whether they can be used with your selected outcome.</p>}
    </div>}
    {uploaded && uploaded.missing_cells>0 && <div className="research-missing-panel" role="group" aria-label="Missing value consent">
     <div className="research-missing-heading"><AlertTriangle className="research-missing-icon" size={20} aria-hidden="true"/><div><h4>How should we handle missing values?</h4><p>Some models need these gaps filled before they can run.</p></div></div>
     <div className="research-missing-options">
      <label className={`research-missing-option ${form.missing_policy==='reject'?'is-selected':''}`}>
       <input type="radio" name="missing-policy" aria-label="I’ll fix the CSV" checked={form.missing_policy==='reject'} onChange={()=>edit({...form,missing_policy:'reject'})}/>
       <span><strong>I’ll fix the CSV</strong><small>Correct the missing values in your CSV, then upload it again.</small></span>
      </label>
      <label className={`research-missing-option ${form.missing_policy==='impute_train_v1'?'is-selected':''}`}>
       <input type="radio" name="missing-policy" aria-label="Fill missing values for me" checked={form.missing_policy==='impute_train_v1'} onChange={()=>edit({...form,missing_policy:'impute_train_v1'})}/>
       <span><strong>Fill missing values for me</strong><small>During the experiment, missing predictor values will be filled in (imputed): measurements and counts use the average; categories, including binary values, use the most common value. These replacement values are calculated from training data only. Your original CSV stays unchanged.</small></span>
      </label>
     </div>
    </div>}
   </div>}
   {(uploaded||form.dataset_path||form.data_mode==='proposal')&&!(uploaded&&uploaded.missing_cells>0&&form.missing_policy==='reject')&&<>
   <div className="research-setup-step">
    <header><span>2</span><div><h4>What do you want to predict?</h4><p>Choose the outcome column — the answer you want the model to learn.</p></div></header>

    {form.data_mode!=='proposal'&&<>
     <label className="research-setup-field">Outcome column <small>Required</small>{uploaded?<select aria-label="Target column" className={style} value={form.target.column} onChange={e=>chooseTarget(e.target.value)}><option value="">Choose a column from your CSV</option>{uploaded.columns.map(c=><option key={c} value={c}>{c}</option>)}</select>:<input aria-label="Target column" className={style} placeholder="Upload your CSV to choose from its columns" value={form.target.column} onChange={e=>chooseTarget(e.target.value)}/>}</label>
     {invalidOutcome?<p role="alert" className="research-input-error">This workflow supports binary classification. Choose a column with exactly two distinct non-missing values.</p>:form.target.column&&(outcomeValues?<>
      <p className="research-setup-help">Binary classification · Values: {outcomeValues.map(value=>JSON.stringify(value)).join(', ')}</p>
     </>:<p className="research-setup-help">Upload the CSV to read the values in this target column.</p>)}
    </>}
    {form.data_mode==='proposal'?<label className="research-setup-field">Research objective <small>Required for a plan without data</small><textarea aria-label="Prediction objective and target meaning" className={style} placeholder="Describe the research question you want to investigate" value={form.target.description} onChange={e=>edit({...form,target:{...form.target,description:e.target.value}})}/></label>:<p className="research-setup-help">Values such as 0 and 1 are labels; their meaning depends on your dataset.</p>}
   </div>
   <div className="research-setup-step research-knowledge-step">
    <header><span>3</span><div><h4>Knowledge source</h4><p>Choose a research library or continue without documents.</p></div></header>
    <fieldset className="research-knowledge-options" aria-label="Knowledge source">
     {sources.map(source=>{
      const isExample=source.path.replace(/\\/g,'/').endsWith('/heart-failure/okf');
      const selected=form.knowledge_mode!=='llm_only'&&!customKnowledge&&form.knowledge_path===source.path;
      return <label key={source.path} className={`research-knowledge-option ${selected?'is-selected':''}`}>
       <input type="radio" name={`${knowledgePathHelpId}-source`} aria-label={isExample?'Heart Failure example':source.label} checked={selected} onChange={()=>{setCustomKnowledge(false);edit({...form,knowledge_mode:'okf',knowledge_path:source.path});}}/>
       <span><strong>{isExample?'Heart Failure example':source.label}<small>Included</small></strong><span>{isExample?'Use the heart failure research library provided with Memstara.':'Use this available research library.'}</span></span>
      </label>;
     })}
     <label className={`research-knowledge-option ${form.knowledge_mode!=='llm_only'&&customKnowledge?'is-selected':''}`}>
      <input type="radio" name={`${knowledgePathHelpId}-source`} aria-label="My research folder" checked={form.knowledge_mode!=='llm_only'&&customKnowledge} onChange={()=>{setCustomKnowledge(true);edit({...form,knowledge_mode:'okf',knowledge_path:''});}}/>
      <span><strong>My research folder</strong><span>Connect your own OKF documents using a folder path.</span></span>
     </label>
     <label className={`research-knowledge-option ${form.knowledge_mode==='llm_only'?'is-selected':''}`}>
      <input type="radio" name={`${knowledgePathHelpId}-source`} aria-label="LLM only" checked={form.knowledge_mode==='llm_only'} onChange={()=>{setCustomKnowledge(false);edit({...form,knowledge_mode:'llm_only',knowledge_path:''});}}/>
      <span><strong>LLM only</strong><span>Use the model’s knowledge without research documents.</span><KnowledgeModelInfo/></span>
     </label>
    </fieldset>
    {form.knowledge_mode!=='llm_only'&&(customKnowledge?<div className="research-knowledge-detail">
     <label className="research-setup-field">Full folder path <small>Required</small><input aria-label="Research document folder path" aria-describedby={knowledgePathHelpId} className={style} placeholder="Paste the full path to your OKF folder" spellCheck={false} autoCapitalize="none" autoCorrect="off" value={form.knowledge_path} onChange={e=>edit({...form,knowledge_path:e.target.value})}/><span id={knowledgePathHelpId}>Enter the full folder path, not just the folder name.</span></label>
     <details className="research-knowledge-help"><summary>What path should I enter?</summary><div><p>Use the folder containing <code>index.md</code>. Memstara must be able to access this folder.</p><span>Example path in Docker</span><code>/app/user-inputs/my-research/okf</code></div></details>
    </div>:form.knowledge_path?<div className="research-knowledge-detail">
     <p className="research-knowledge-ready"><CheckCircle2 size={18} aria-hidden="true"/>Library selected. No folder setup needed.</p>
     <details className="research-knowledge-help"><summary>View library folder path</summary><div><code>{form.knowledge_path}</code></div></details>
    </div>:null)}
   </div>
   <div className="research-setup-readiness" aria-live="polite">{requiredDetails.length?`Still needed: ${requiredDetails.join(' · ')}`:'✓ Required details filled. Check & use this data will validate your settings.'}</div>
   <div className="research-setup-actions"><button type="button" className="research-check-button" onClick={()=>void submit('register')}>Check & use this data</button></div>
   </>}
  </fieldset>
  {feedback&&<ResearchInputFeedback feedback={feedback} onClose={()=>setFeedback(null)}/>}
  {busy&&<p role="status">Checking inputs…</p>}
  {error&&<p role="alert" className="research-input-error"><CircleAlert size={20} aria-hidden="true"/><span>{error}</span></p>}
  {result&&<div className="space-y-2" role="status">
   <p>{result.id?'Study saved.':'Input check complete.'} {result.dataset.rows.toLocaleString()} rows · {result.dataset.column_count} columns · {result.dataset.missing_cells.toLocaleString()} missing cells · {result.knowledge.documents} OKF documents.</p>
   <p className="font-semibold">{result.input_checks_passed?'Inputs are ready to use':'Resolve input issues before execution'}</p>
   <ul className="list-disc pl-5">{result.issues.map(x=><li key={x.code}>{x.message}</li>)}</ul>
   <details><summary>Dataset columns</summary><ul>{result.dataset.columns.map(c=><li className="break-all" key={c}>{c}</li>)}</ul></details>
  </div>}

 </section>;
}
