export type ModelName='logistic_regression'|'xgboost';
export type ModelOverrides={parameters?:Record<string,number|string|boolean|null>;scale_numeric?:boolean;threshold?:number};
export type MlOverrides={version?:1;models?:Partial<Record<ModelName,ModelOverrides>>;folds?:number};
export type ParameterSpec={type:'number'|'integer'|'choice';min?:number;max?:number;choices?:Array<string|boolean|null>};
export type MlSettingsSchema={version:number;models:Record<ModelName,{parameters:Record<string,ParameterSpec>}>;folds:number[];threshold:{min:number;max:number};resource_limits:{threads:number;memory_bytes:number;wall_seconds:number;max_fits:number}};
export const modelLabels:Record<ModelName,string>={logistic_regression:'Logistic Regression (LR)',xgboost:'XGBoost'};
let schema:MlSettingsSchema|null=null;
export function setMlSettingsSchema(value?:MlSettingsSchema):void{schema=value??null;}
export function getMlSettingsSchema():MlSettingsSchema|null{return schema;}
export function modelsForSkills(skills:string[]):ModelName[]{return [...new Set(skills.flatMap(s=>s==='ml_logistic_regression'?['logistic_regression' as const]:s==='ml_xgboost'?['xgboost' as const]:[]))];}
export function overridesForSkills(value:MlOverrides|undefined,skills:string[]):MlOverrides{
 const selected=modelsForSkills(skills);const models=Object.fromEntries(Object.entries(value?.models??{}).filter(([name,settings])=>selected.includes(name as ModelName)&&Object.keys(settings).length));
 return Object.keys(models).length||selected.length&&value?.folds!==undefined?{version:1,models,...(value?.folds!==undefined?{folds:value.folds}:{})}:{};
}
export function overrideCount(value:MlOverrides|undefined):number{return (value?.folds!==undefined?1:0)+Object.values(value?.models??{}).reduce((n,model)=>n+Object.keys(model.parameters??{}).length+Number(model.scale_numeric!==undefined)+Number(model.threshold!==undefined),0);}
export function mlOverridesError(value:MlOverrides|undefined,skills:string[],replicates=1):string|null{
 if(!value||!Object.keys(value).length)return null;
 if(!schema)return 'Load the supported ML settings before saving custom values.';
 if(value.version!==1)return 'Unsupported advanced ML settings version.';
 const selected=modelsForSkills(skills);
 for(const [key,model] of Object.entries(value.models??{})){
  const name=key as ModelName;
  if(!selected.includes(name))return 'Custom model settings must match the selected ML skills.';
  for(const [parameter,v] of Object.entries(model.parameters??{})){
   const spec=schema.models[name]?.parameters[parameter];
   if(!spec)return `${parameter} is controlled by the server.`;
   if(spec.type==='choice'){if(!spec.choices?.some(option=>option===v))return `Choose a supported ${parameter}.`;}
   else if(typeof v!=='number'||!Number.isFinite(v)||v<spec.min!||v>spec.max!||(spec.type==='integer'&&!Number.isInteger(v)))return `${modelLabels[name]} ${parameter} must be ${spec.type==='integer'?'an integer':'a number'} from ${spec.min} to ${spec.max}.`;
  }
  if(model.threshold!==undefined&&(!Number.isFinite(model.threshold)||model.threshold<schema.threshold.min||model.threshold>schema.threshold.max))return `Prediction threshold must be from ${schema.threshold.min} to ${schema.threshold.max}.`;
  if(model.parameters?.penalty==='l1'&&model.parameters?.solver==='lbfgs')return 'LR l1 requires the liblinear solver.';
 }
 if(value.folds!==undefined&&!schema.folds.includes(value.folds))return 'Training CV folds must be 0 or 2–5.';
 if(value.folds!==undefined&&replicates*(value.folds+2)>schema.resource_limits.max_fits)return 'Reduce split evaluations or CV folds to remain within the ML fit budget.';
 return null;
}
