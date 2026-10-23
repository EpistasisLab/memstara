import { featureImportance, rankedContributions } from "../lib/featureImportance";
import {useState} from 'react';
import type {Result} from '../types';
import {featureLabel} from './ResultExplorer';
import './feature-contributions.css';

export default function FeatureContributionChart({result:r}:{result:Result}) {
 const [method,setMethod]=useState<'importance'|'shap'>('importance');
 const [all,setAll]=useState(false);
 const e=r.evaluation?.explanation;
 const shap=e?.shap?.mean_absolute;
 const hasShap=!!shap&&Object.values(shap).some(v=>Number.isFinite(v)&&v>=0);
 const useShap=method==='shap'&&hasShap;
 const contributions=featureImportance(r.importance);
 const permutation=(e?.method||contributions.method)==='holdout_permutation_auc';
 const entries=rankedContributions(useShap?shap:contributions.values,r.y_column,useShap);
 const spread=(c:string)=>!useShap&&permutation?e?.permutation?.standard_deviation?.[c]:undefined;
 const sd=(c:string)=>{const v=spread(c);return v!=null&&Number.isFinite(v)&&v>=0?v:undefined;};
 const lo=Math.min(0,...entries.map(([c,v])=>v-(sd(c)??0)));
 const hi=Math.max(0,...entries.map(([c,v])=>v+(sd(c)??0)));
 const range=hi-lo||1;
 const position=(v:number)=>(v-lo)/range*100;
 const format=(v:number)=>v===0?'0':v.toPrecision(3);
 const title=useShap?'Average prediction influence (SHAP)':permutation?'Prediction performance contribution':'Recorded feature importance';
 const unit=useShap?`Mean |SHAP| · ${e?.shap?.units||'units not recorded'}`:permutation?'AUC decrease after shuffling':'Method and units not recorded';
 return <section className="result-chart-card" aria-label="Feature contribution chart">
  <h4>{title}</h4>
  <div className="result-view-toggle" role="group" aria-label="Feature importance method">
   <button aria-pressed={!useShap} onClick={()=>setMethod('importance')} data-help={permutation?"Permutation importance":"Recorded importance"} data-help-description={permutation?"How much measured model performance changes when a feature is shuffled. Negative values mean the score improved after shuffling, not that the feature is protective.":"Stored feature-importance values. Without recorded method metadata, the interface does not infer how these values were calculated."}>{permutation?'Permutation importance':'Recorded importance'}</button>
   <button aria-pressed={useShap} disabled={!hasShap} onClick={()=>setMethod('shap')} data-help="SHAP magnitude" data-help-description="Average absolute contribution to predictions. This measures influence, not whether predictions rise or fall, and is not a measure of AUC improvement.">SHAP magnitude</button>
  </div>
  <p>{useShap?'Which inputs influenced predictions most on average? Magnitude does not show whether a feature raises or lowers the prediction.':permutation?'How much did AUC fall when each input was shuffled? Larger positive values indicate more reliance on that input in this evaluation.':'These recorded values are shown without assuming the calculation method from the model name.'}</p>
  <p className="result-caveat"><strong>{unit}.</strong> Values are ordered highest to lowest. Each method has its own scale; do not compare bar lengths across tabs, models or Replicates.</p>
  <div className="contribution-scope">
   <strong>Analysis scope</strong>
   <span>{e?.scope||'Evaluation scope was not recorded for this result.'}</span>
   {e?.evaluated_replicate!=null&&<span>Split evaluation {e.evaluated_replicate} of {e.total_replicates??'unknown'} · seed {e.evaluated_seed??'not recorded'} · {e.evaluation_rows??'unknown'} held-out rows. This is not a separate pipeline Replicate.</span>}
  </div>
  {!useShap&&contributions.note&&<p className="result-caveat">{contributions.note}</p>}
  {!hasShap&&<p className="result-caveat">SHAP values were not recorded for this analysis.</p>}
  {!entries.length?<p className="result-empty">No feature contribution values were recorded.</p>:<>
   <div className="contribution-axis" aria-label={`Scale: ${format(lo)} to ${format(hi)} ${unit}`}><span>{format(lo)}</span><span>{unit}</span><span>{format(hi)}</span></div>
   <div className="result-feature-bars">{(all?entries:entries.slice(0,10)).map(([column,value])=>{
    const deviation=sd(column);
    return <div key={column} className="result-feature-row" data-feature={column}>
     <details><summary>{featureLabel(column)}</summary><code>{column}</code>{useShap&&<p className="result-caveat">SHAP may refer to an encoded model input, such as a category, rather than the original column.</p>}</details>
     <div className="contribution-value"><strong>{format(value)}</strong>{deviation!=null&&<small>± {format(deviation)} SD</small>}</div>
     <div className="result-feature-track contribution-track" aria-hidden="true"><i className="contribution-zero" style={{left:`${position(0)}%`}}/>
      <span style={{width:`${Math.abs(value)/range*100}%`,left:`${position(Math.min(value,0))}%`,background:value<0?'#ad643d':'rgb(var(--accent))'}}/>
      {deviation!=null&&<i className="contribution-whisker" style={{left:`${position(value-deviation)}%`,width:`${2*deviation/range*100}%`}}/>}
     </div>
     {deviation!=null&&e?.permutation?.repeat_values?.[column]&&<details className="contribution-repeats"><summary>Repeated shuffle values</summary><p>{e.permutation.repeat_values[column].map(format).join(' · ')}</p></details>}
    </div>;
   })}</div>
  </>}
  {entries.length>10&&<button className="result-more" onClick={()=>setAll(v=>!v)}>{all?'Show top 10':`Show all ${entries.length} features`}</button>}
  {!useShap&&permutation&&<p className="result-caveat">{e?.permutation?`Whiskers and ± values show one standard deviation across ${e.permutation.n_repeats} shuffles of the same held-out data. This is not a confidence interval or variation across train/test splits. A small number of shuffles gives a limited estimate of variability.`:'Shuffle variability was not recorded. It cannot be recovered from the stored mean alone; new evaluations record it.'} Negative values mean shuffling improved AUC in this evaluation; they are not evidence of a protective effect.</p>}
  {useShap&&<p className="result-caveat">These are mean absolute contributions, not percentages or AUC changes. Log-odds, when recorded, are model score units: 0.1 does not mean a 10-percentage-point increase in probability. A high SHAP magnitude can coexist with low permutation importance: the measures answer different questions. Correlated inputs and model behavior may contribute; this chart alone cannot establish the reason.</p>}
  <p className="result-caveat">Calculated from the fitted model, not an LLM rating. Neither chart establishes biological causality or clinical benefit.</p>
 </section>;
}
