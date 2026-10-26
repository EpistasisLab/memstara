import {useState} from 'react';
import {UploadCloud} from 'lucide-react';

type Target={column:string;description:string;positive_label:string;negative_label:string;prediction_time:string;horizon:string};
export type ResearchConfig={name:string;dataset_path:string;knowledge_path:string;target:Target;excluded_columns:string[];missing_policy:'reject'|'impute_train_v1';categorical_columns?:string[];knowledge_mode?:'okf'|'llm_only';data_mode?:'dataset'|'proposal'};
export type Inspection={id?:string;configuration:ResearchConfig;fingerprint:string;input_checks_passed:boolean;execution_ready:boolean;execution_note:string;
 dataset:{rows:number;column_count:number;columns:string[];missing_cells:number;eligible_predictor_count:number};
 knowledge:{documents:number;domains:string[]};issues:{code:string;message:string}[]};
const initial:ResearchConfig={name:'',dataset_path:'',knowledge_path:'',target:{column:'',description:'',positive_label:'',negative_label:'',prediction_time:'',horizon:''},excluded_columns:[],missing_policy:'reject'};
type UploadInspection={dataset_path:string;columns:string[];rows:number;missing_cells:number;columns_with_missing:Record<string,number>;message:string;nonfinite_columns:string[]};
const style='w-full min-w-0 rounded border border-paper-line bg-paper px-3 py-2 text-sm';

export default function ResearchInputs({onSaved,initialConfig,disabled=false}:{onSaved?:(record:Inspection)=>void;initialConfig?:ResearchConfig;disabled?:boolean}={}){
 const [form,setForm]=useState<ResearchConfig>(initialConfig??initial),[result,setResult]=useState<Inspection|null>(null);
 const [uploaded,setUploaded]=useState<UploadInspection|null>(null);
 const [dragging,setDragging]=useState(false);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 function edit(next:ResearchConfig){setForm(next);setResult(null);setError('');}
 async function upload(file:File){
  if(busy||disabled)return;
  setBusy(true);setError('');setResult(null);setUploaded(null);
  try{
   if(!file.name.toLowerCase().endsWith('.csv'))throw Error('Choose a CSV file.');
   if(file.size>5*1024*1024)throw Error('CSV upload limit is 5 MiB.');
   const content=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Could not read CSV'));reader.readAsDataURL(file);});
   const response=await fetch('/control/research-inputs/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,content_base64:content})});
   const data=await response.json();if(!response.ok)throw Error(data.error||'Upload failed');
   setUploaded(data);setForm(f=>({...f,dataset_path:data.dataset_path,missing_policy:'reject',categorical_columns:[],excluded_columns:[],target:{...initial.target},name:f.name||file.name.replace(/\.csv$/i,'')}));
  }catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function submit(action:'inspect'|'register'){
  setBusy(true);setError('');setResult(null);
  try{const r=await fetch(`/control/research-inputs/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form)});
   const d=await r.json();if(!r.ok)throw Error(d.error||'Inspection failed');setResult(d);if(action==='register'){onSaved?.(d);}
  }catch(e){setError(String(e));}finally{setBusy(false);}
 }
 return <section className="space-y-4 p-4" aria-label="Research input preparation">
  <p>Add your dataset, knowledge source and prediction target.</p>
  <p className="text-sm">Upload a CSV or use an existing server file. Original data is never changed.</p>
  <fieldset disabled={busy||disabled} className="min-w-0 space-y-3">
   <label className="block">Knowledge mode<select aria-label="Knowledge mode" className={style} value={form.knowledge_mode??'okf'} onChange={e=>edit({...form,knowledge_mode:e.target.value as ResearchConfig['knowledge_mode']})}><option value="okf">Use my OKF corpus</option><option value="llm_only">LLM knowledge only — no corpus</option></select></label>
   <label className="block">Data mode<select aria-label="Data mode" className={style} value={form.data_mode??'dataset'} onChange={e=>edit({...form,data_mode:e.target.value as ResearchConfig['data_mode']})}><option value="dataset">Use my CSV — empirical evaluation</option><option value="proposal">No CSV — research proposal and analysis plan</option></select></label>
   {form.data_mode==='proposal'&&<p>Without a dataset, this creates an analysis plan, not measured results. Describe your research objective below.</p>}
   {form.data_mode!=='proposal'&&<div className="space-y-3">
    <div role="group" aria-label="CSV upload area" aria-disabled={busy||disabled}
      onDragEnter={event=>{event.preventDefault();if(!busy&&!disabled)setDragging(true);}}
      onDragOver={event=>{event.preventDefault();event.dataTransfer.dropEffect=busy||disabled?'none':'copy';}}
      onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setDragging(false);}}
      onDrop={event=>{event.preventDefault();setDragging(false);if(busy||disabled)return;const files=event.dataTransfer.files;if(files.length!==1){setError('Drop one CSV file at a time.');return;}void upload(files[0]);}}
      className={`rounded-xl border-2 border-dashed p-5 text-center transition-colors ${dragging?'border-sky-500 bg-sky-50 dark:bg-sky-950/30':'border-paper-line bg-paper'}`}>
      <UploadCloud size={26} className="mx-auto mb-2 text-slate-500" aria-hidden="true"/>
      <p className="text-sm font-semibold">{dragging?'Drop your CSV here':'Drag your CSV here'}</p>
      <p className="mt-1 text-xs text-slate-500">or choose a file below · UTF-8 CSV · up to 5 MiB</p>
      <label className="mt-3 block"><span className="sr-only">Upload CSV</span><input type="file" accept=".csv,text/csv" aria-label="Upload CSV" className="block w-full min-w-0 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-sky-600 file:px-3 file:py-2 file:text-white" onChange={event=>{const file=event.target.files?.[0];if(file)void upload(file);event.target.value='';}}/></label>
      <p className="mt-3 text-xs text-slate-500">We check for missing values as soon as the file uploads.</p>
    </div>
    {uploaded&&<div role="status" className="rounded border border-paper-line p-3 text-sm"><strong>{uploaded.rows.toLocaleString()} rows · {uploaded.columns.length} columns</strong><p>{uploaded.message}</p>{Object.entries(uploaded.columns_with_missing).map(([column,count])=><p key={column}>{column}: {count.toLocaleString()} missing</p>)}{uploaded.nonfinite_columns.length>0&&<p>Resolve infinite values in: {uploaded.nonfinite_columns.join(', ')}</p>}</div>}
    <fieldset className="space-y-2 rounded border border-paper-line p-3"><legend className="text-sm font-medium">Missing-value handling</legend>
     <p className="text-sm">Some classifiers cannot use missing values. Do you want us to impute your data?</p>
     <label className="flex gap-2 text-sm"><input type="radio" name="missing-policy" checked={form.missing_policy==='reject'} onChange={()=>edit({...form,missing_policy:'reject'})}/>No — require complete input before starting.</label>
     <label className="flex gap-2 text-sm"><input type="radio" name="missing-policy" checked={form.missing_policy==='impute_train_v1'} onChange={()=>edit({...form,missing_policy:'impute_train_v1'})}/>Yes — use training-only mean / most frequent values.</label>
     {form.missing_policy==='impute_train_v1'&&<><p className="text-sm">Continuous columns use the training mean; text and 0/1 binary columns use the most frequent training value. Target labels are never filled. Test data never determines fill values.</p><label className="block text-sm">Other categorical predictor columns (one exact name per line)<textarea className={style} value={(form.categorical_columns??[]).join('\n')} onChange={e=>edit({...form,categorical_columns:e.target.value.split('\n').map(x=>x.trim()).filter(Boolean)})}/></label><p className="text-sm">Include numeric category codes here so they use the most frequent value, not the mean.</p></>}
    </fieldset>
   </div>}
   <label className="block text-sm">Study name<input className={style} value={form.name} onChange={e=>edit({...form,name:e.target.value})}/></label>
   {form.data_mode!=='proposal'&&<details className="rounded-lg border border-paper-line p-3 text-sm"><summary className="cursor-pointer">Use a server file instead of uploading</summary><label className="mt-3 block">Dataset CSV path<input className={style} value={form.dataset_path} onChange={e=>{setUploaded(null);edit({...form,dataset_path:e.target.value,missing_policy:'reject',categorical_columns:[]});}}/></label></details>}
   {form.knowledge_mode!=='llm_only'&&<label className="block text-sm">OKF corpus folder<input aria-label="OKF corpus folder" className={style} placeholder="user-inputs/my-study/okf" value={form.knowledge_path} onChange={e=>edit({...form,knowledge_path:e.target.value})}/><span className="text-xs text-slate-500">Folder on the server containing index.md. Choose LLM knowledge only if you do not have an OKF corpus.</span></label>}
   <label className="block">Target column{uploaded?<select aria-label="Target column" className={style} value={form.target.column} onChange={e=>edit({...form,target:{...form.target,column:e.target.value}})}><option value="">Choose a target</option>{uploaded.columns.map(c=><option key={c} value={c}>{c}</option>)}</select>:<input className={style} value={form.target.column} onChange={e=>edit({...form,target:{...form.target,column:e.target.value}})}/>}</label>
   <label className="block">Prediction objective and target meaning<textarea className={style} value={form.target.description} onChange={e=>edit({...form,target:{...form.target,description:e.target.value}})}/></label>
   {(['positive_label','negative_label','prediction_time','horizon'] as const).map(key=><label className="block" key={key}>{({positive_label:'Positive-class value (exact CSV value)',negative_label:'Negative-class value (exact CSV value)',prediction_time:'When are predictors available?',horizon:'Prediction horizon (if applicable)'})[key]}<input className={style} value={form.target[key]} onChange={e=>edit({...form,target:{...form.target,[key]:e.target.value}})}/></label>)}
   <p className="text-sm text-ink-soft">Supply prepared numeric predictors. Memstara does not automatically encode categories or scale values. Missing-value replacement requires your explicit approval.</p>
   <label className="block">Excluded columns (one exact name per line)<textarea className={style} value={form.excluded_columns.join('\n')} onChange={e=>edit({...form,excluded_columns:e.target.value.split('\n')})}/></label>
   <div className="flex flex-wrap gap-2"><button type="button" className={style+' !w-auto'} onClick={()=>void submit('inspect')}>Check inputs</button><button type="button" className={style+' !w-auto'} onClick={()=>void submit('register')}>Check & use this data</button></div>
  </fieldset>
  {busy&&<p role="status">Checking inputs…</p>}
  {error&&<p role="alert" className="break-words">{error}</p>}
  {result&&<div className="space-y-2" role="status">
   <p>{result.id?'Study saved.':'Input check complete.'} {result.dataset.rows.toLocaleString()} rows · {result.dataset.column_count} columns · {result.dataset.missing_cells.toLocaleString()} missing cells · {result.knowledge.documents} OKF documents.</p>
   <p className="font-semibold">{result.input_checks_passed?'Inputs are ready to use':'Resolve input issues before execution'}</p>
   <ul className="list-disc pl-5">{result.issues.map(x=><li key={x.code}>{x.message}</li>)}</ul>
   <details><summary>Dataset columns</summary><ul>{result.dataset.columns.map(c=><li className="break-all" key={c}>{c}</li>)}</ul></details>
  </div>}

 </section>;
}
