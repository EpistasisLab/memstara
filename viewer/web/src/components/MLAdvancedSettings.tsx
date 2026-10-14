import {useState} from 'react';
import {useControl} from '../store/control';
import {getMlSettingsSchema,modelsForSkills,modelLabels,overridesForSkills,overrideCount,mlOverridesError,type MlOverrides,type ModelName,type ModelOverrides} from '../lib/mlOverrides';
const labels:Record<string,string>={C:'Inverse regularization strength (C)',max_iter:'Maximum solver iterations',tol:'Convergence tolerance',solver:'Solver',penalty:'Regularization penalty',class_weight:'Class weighting',fit_intercept:'Fit intercept',n_estimators:'Number of trees',max_depth:'Maximum tree depth',learning_rate:'Learning rate',min_child_weight:'Minimum child weight',subsample:'Row sampling fraction',colsample_bytree:'Feature sampling fraction',reg_alpha:'L1 regularization',reg_lambda:'L2 regularization',gamma:'Minimum split gain',scale_pos_weight:'Positive-class weight',max_bin:'Histogram bins'};
const field='mt-1 block w-full min-w-0 rounded border border-paper-line bg-paper px-2 py-1.5 text-sm';
export default function MLAdvancedSettings({skills,value={},onChange,replicates=1,disabled=false,proposal=false}:{skills:string[];value?:MlOverrides;onChange:(value:MlOverrides)=>void;replicates?:number;disabled?:boolean;proposal?:boolean}){
 const [expanded,setExpanded]=useState(false);
 useControl(s=>s.catalog); // Catalog responses carry the authoritative settings schema.
 const schema=getMlSettingsSchema(),models=modelsForSkills(skills);
 if(!models.length)return null;
 const error=mlOverridesError(value,skills,replicates);
 function changeModel(name:ModelName,key:string,item:unknown,parameter=false){
  const next=structuredClone(value);next.version=1;next.models??={};
  const model:ModelOverrides={...next.models[name]};
  if(parameter){const parameters={...model.parameters};if(item===undefined)delete parameters[key];else parameters[key]=item as number|string|boolean|null;if(Object.keys(parameters).length)model.parameters=parameters;else delete model.parameters;}
  else if(item===undefined)delete model[key as 'threshold'|'scale_numeric'];
  else Object.assign(model,{[key]:item});
  if(Object.keys(model).length)next.models[name]=model;else delete next.models[name];
  onChange(overridesForSkills(next,skills));
 }
 return <section className="mt-3 rounded border border-paper-line p-3">
  <button type="button" className="cursor-pointer text-left font-semibold" aria-expanded={expanded||!!error} onClick={()=>setExpanded(v=>!v)}>Advanced model settings · {overrideCount(value)} fixed values</button>
  {(expanded||!!error)&&<div className="mt-3 space-y-4">
   <p className="text-sm">Blank or Auto fields are chosen by the ML Agent. Your explicit values are fixed before fitting and recorded separately from automatic settings. Both LR and XGBoost are fitted; only the selected ML skills have editable model panels here. Unselected comparator settings remain automatic.</p>
   {models.length>1&&<p className="text-sm">These model-specific values apply to that model in every Loop, regardless of which selected skill is primary. They are not shared between LR and XGBoost.</p>}
   {proposal&&<p className="text-sm">Proposal only: these are planned settings; no models are fitted without a CSV.</p>}
   {!schema?<p role="status">Advanced settings are unavailable. <button type="button" className="underline" onClick={()=>void useControl.getState().loadPlaybooks()}>Reload supported settings</button></p>:<fieldset disabled={disabled} className="min-w-0 space-y-4">
    {models.map(name=><fieldset key={name} className="min-w-0 rounded border border-paper-line p-3"><legend className="px-1 font-semibold">{modelLabels[name]} settings</legend>
     <div className="grid min-w-0 gap-3" style={{gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,220px),1fr))'}}>
      {Object.entries(schema.models[name].parameters).map(([key,spec])=>{const v=value.models?.[name]?.parameters?.[key];return <label key={key} className="min-w-0 text-sm">{labels[key]??key}
       {spec.type==='choice'?<select aria-label={`${modelLabels[name]} ${key}`} className={field} value={v===undefined?'auto':JSON.stringify(v)} onChange={e=>changeModel(name,key,e.target.value==='auto'?undefined:JSON.parse(e.target.value),true)}><option value="auto">Auto — ML Agent</option>{spec.choices?.map(option=><option key={JSON.stringify(option)} value={JSON.stringify(option)}>{option===null?'None':String(option)}</option>)}</select>:<input aria-label={`${modelLabels[name]} ${key}`} className={field} type="number" min={spec.min} max={spec.max} step={spec.type==='integer'?1:'any'} placeholder="Auto — ML Agent" value={typeof v==='number'&&Number.isFinite(v)?v:''} onChange={e=>changeModel(name,key,e.target.value===''?undefined:e.target.valueAsNumber,true)}/>}
       {spec.type!=='choice'&&<span className="text-xs text-ink-muted">Allowed: {spec.min}–{spec.max}. Blank = Auto.</span>}
      </label>;})}
      <label className="text-sm">Numeric scaling<select aria-label={`${modelLabels[name]} numeric scaling`} className={field} value={value.models?.[name]?.scale_numeric===undefined?'auto':String(value.models[name]?.scale_numeric)} onChange={e=>changeModel(name,'scale_numeric',e.target.value==='auto'?undefined:e.target.value==='true')}><option value="auto">Auto — ML Agent</option><option value="true">Scale numeric predictors</option><option value="false">Do not scale numeric predictors</option></select></label>
      <label className="text-sm">Prediction threshold<input aria-label={`${modelLabels[name]} prediction threshold`} className={field} type="number" min={schema.threshold.min} max={schema.threshold.max} step="any" placeholder="Auto — ML Agent" value={Number.isFinite(value.models?.[name]?.threshold)?value.models?.[name]?.threshold:''} onChange={e=>changeModel(name,'threshold',e.target.value===''?undefined:e.target.valueAsNumber)}/></label>
     </div>
    </fieldset>)}
    <label className="block text-sm">Shared training cross-validation<select aria-label="Advanced training CV folds" className={field} value={value.folds??'auto'} onChange={e=>{const next={...value,version:1 as const};if(e.target.value==='auto')delete next.folds;else next.folds=Number(e.target.value);onChange(overridesForSkills(next,skills));}}><option value="auto">Auto — ML Agent</option>{schema.folds.map(n=><option key={n} value={n}>{n===0?'No training CV':`${n} folds`}</option>)}</select><span className="text-xs text-ink-muted">The two models share training folds. Held-out and reserved validation outcomes never select these settings.</span></label>
    <p className="text-xs text-ink-muted">Server limits remain fixed: {schema.resource_limits.threads} CPU thread, one ML job at a time, up to {Math.round(schema.resource_limits.memory_bytes/1024**2)} MiB and {schema.resource_limits.wall_seconds} seconds. The server also checks class counts and total fit count before training.</p>
   </fieldset>}
   {error&&<p role="alert" className="text-sm text-red-700">{error}</p>}
   <button type="button" disabled={disabled||!overrideCount(value)} className="text-sm underline disabled:opacity-40" onClick={()=>onChange({})}>Reset all advanced settings to Auto</button>
  </div>}
 </section>;
}
