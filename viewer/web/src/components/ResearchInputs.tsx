import {useEffect,useState} from 'react';

type Target={column:string;description:string;positive_label:string;negative_label:string;prediction_time:string;horizon:string};
type ResearchConfig={name:string;dataset_path:string;knowledge_path:string;target:Target;excluded_columns:string[];missing_policy:'reject';knowledge_mode?:'okf'|'llm_only';data_mode?:'dataset'|'proposal'};
type Inspection={id?:string;configuration:ResearchConfig;fingerprint:string;input_checks_passed:boolean;execution_ready:boolean;execution_note:string;
 dataset:{rows:number;column_count:number;columns:string[];missing_cells:number;eligible_predictor_count:number};
 knowledge:{documents:number;domains:string[]};issues:{code:string;message:string}[]};
const initial:ResearchConfig={name:'',dataset_path:'',knowledge_path:'',target:{column:'',description:'',positive_label:'',negative_label:'',prediction_time:'',horizon:''},excluded_columns:[],missing_policy:'reject'};
const style='w-full min-w-0 rounded border border-paper-line bg-paper px-3 py-2 text-sm';

export default function ResearchInputs({onSaved}:{onSaved?:()=>void}={}){
 const [form,setForm]=useState<ResearchConfig>(initial),[result,setResult]=useState<Inspection|null>(null),[saved,setSaved]=useState<Inspection[]>([]);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function reload(){try{const r=await fetch('/control/research-inputs');const d=await r.json();if(!r.ok||!Array.isArray(d.inputs))throw Error(d.error||'Research inputs unavailable');setSaved(d.inputs);}catch(e){setError(String(e));}}
 useEffect(()=>{void reload();},[]);
 function edit(next:ResearchConfig){setForm(next);setResult(null);setError('');}
 async function submit(action:'inspect'|'register'){
  setBusy(true);setError('');setResult(null);
  try{const r=await fetch(`/control/research-inputs/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form)});
   const d=await r.json();if(!r.ok)throw Error(d.error||'Inspection failed');setResult(d);if(action==='register'){await reload();onSaved?.();}
  }catch(e){setError(String(e));}finally{setBusy(false);}
 }
 return <section className="space-y-4 p-4" aria-label="Research input preparation">
  <h3 className="font-semibold">Research input preparation</h3>
  <p>Register your local OKF bundle, CSV and prediction target. Select the saved version in pipeline settings to use it. Saving does not start an experiment.</p>
  <p className="text-sm">Paths refer to the machine running Memstara. Source files remain unchanged. Missing values are reported; no automatic cleaning is performed.</p>
  <fieldset disabled={busy} className="min-w-0 space-y-3">
   <label className="block">Knowledge mode<select aria-label="Knowledge mode" className={style} value={form.knowledge_mode??'okf'} onChange={e=>edit({...form,knowledge_mode:e.target.value as ResearchConfig['knowledge_mode']})}><option value="okf">Use my OKF corpus</option><option value="llm_only">LLM knowledge only — no corpus</option></select></label>
   <label className="block">Data mode<select aria-label="Data mode" className={style} value={form.data_mode??'dataset'} onChange={e=>edit({...form,data_mode:e.target.value as ResearchConfig['data_mode']})}><option value="dataset">Use my CSV — empirical evaluation</option><option value="proposal">No CSV — research proposal and analysis plan</option></select></label>
   {form.data_mode==='proposal'&&<p>No dataset is attached. All agents produce a research proposal and analysis plan; training, metrics and SHAP/LIME computations are not executed. Describe the research objective below. A target column and observed label mapping are optional.</p>}
   {(['name','dataset_path','knowledge_path'] as const).filter(key=>key==='name'||(key==='dataset_path'?form.data_mode!=='proposal':form.knowledge_mode!=='llm_only')).map(key=><label className="block" key={key}>{({name:'Research name',dataset_path:'Dataset CSV path',knowledge_path:'OKF bundle folder (contains index.md)'})[key]}<input className={style} value={form[key]} onChange={e=>edit({...form,[key]:e.target.value})}/></label>)}
   <label className="block">Target column<input className={style} value={form.target.column} onChange={e=>edit({...form,target:{...form.target,column:e.target.value}})}/></label>
   <label className="block">Prediction objective and target meaning<textarea className={style} value={form.target.description} onChange={e=>edit({...form,target:{...form.target,description:e.target.value}})}/></label>
   {(['positive_label','negative_label','prediction_time','horizon'] as const).map(key=><label className="block" key={key}>{({positive_label:'Positive-class value (exact CSV value)',negative_label:'Negative-class value (exact CSV value)',prediction_time:'When are predictors available?',horizon:'Prediction horizon (if applicable)'})[key]}<input className={style} value={form.target[key]} onChange={e=>edit({...form,target:{...form.target,[key]:e.target.value}})}/></label>)}
   <label className="block">Excluded columns (one exact name per line)<textarea className={style} value={form.excluded_columns.join('\n')} onChange={e=>edit({...form,excluded_columns:e.target.value.split('\n')})}/></label>
   <div className="flex flex-wrap gap-2"><button type="button" className={style+' !w-auto'} onClick={()=>void submit('inspect')}>Inspect inputs</button><button type="button" className={style+' !w-auto'} onClick={()=>void submit('register')}>Save preparation record</button></div>
  </fieldset>
  {busy&&<p role="status">Inspecting local files. No model calls are made.</p>}
  {error&&<p role="alert" className="break-words">{error}</p>}
  {result&&<div className="space-y-2" role="status">
   <p>{result.id?'Preparation record saved.':'Inspection complete.'} {result.dataset.rows.toLocaleString()} rows · {result.dataset.column_count} columns · {result.dataset.missing_cells.toLocaleString()} missing cells · {result.knowledge.documents} OKF documents.</p>
   <p className="font-semibold">{result.input_checks_passed?'Input checks passed; select this saved version in a pipeline':'Resolve input issues before execution'}</p><p>{result.execution_note}</p>
   <ul className="list-disc pl-5">{result.issues.map(x=><li key={x.code}>{x.message}</li>)}</ul>
   <details><summary>Dataset columns</summary><ul>{result.dataset.columns.map(c=><li className="break-all" key={c}>{c}</li>)}</ul></details>
  </div>}
  {saved.length>0&&<div><h4 className="font-semibold">Saved research versions</h4><ul>{saved.map(x=><li className="my-2" key={x.id}><button type="button" className="underline" disabled={busy} onClick={()=>{setForm(x.configuration);setResult(null);setError('Saved record loaded. Inspect again and save a new version after editing.');}}>{x.configuration.name} · {x.id?.slice(0,8)}</button> — {x.input_checks_passed?'input checks passed':'input review needed'}</li>)}</ul></div>}
 </section>;
}
