import FeatureContributionChart from './FeatureContributionChart';
import ModelComparisonView from './ModelComparisonView';
import ValidationStatus from './ValidationStatus';
import { precisionExplanation } from '../lib/metricEvidence';
import { useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Result } from '../types';
import { featureLabel, predictorNames } from './ResultExplorer';

export default function ResultEvidenceVisuals({result:r}:{result:Result}) {
  const predictors=predictorNames(r);
  const explanation=r.evaluation?.explanation;
  const [chosen,setChosen]=useState('');
  const curves=(explanation?.partial_dependence??[]).filter(c=>c.feature!==r.y_column);
  const curve=curves.find(c=>c.feature===chosen)||curves[0];
  const points=curve?.values.map((value,i)=>({value,probability:curve.predicted_probability[i]})).filter(p=>Number.isFinite(p.value)&&Number.isFinite(p.probability));
  const point=explanation?.operating_point;
  return <div className="result-evidence-visuals">
    <ValidationStatus result={r}/>
    <ModelComparisonView comparison={r.evaluation?.comparison}/>
    <div className="result-evidence-path" aria-label="Evidence and model inputs"><div><small>Knowledge references</small><strong>{r.okf_concept_ids?.length??0}</strong><span>Recorded supporting references</span></div><span aria-hidden="true">→</span><div><small>Predictor inputs</small><strong>{predictors.length}</strong><span>Selected columns, excluding the target</span></div><span aria-hidden="true">→</span><div><small>Prediction target</small><strong className="result-target-label">{r.y_column||'Not recorded'}</strong><span>{r.model||'Model not recorded'}</span></div></div>
    <FeatureContributionChart result={r}/>
    <section className="result-chart-card" aria-label="Model response chart"><h4>How does the model respond to a feature?</h4>
      {curve&&points?.length?<><label className="result-curve-select">Feature<select aria-label="Model response feature" value={curve.feature} onChange={e=>setChosen(e.target.value)}>{curves.map(c=><option key={c.feature} value={c.feature}>{featureLabel(c.feature)}</option>)}</select></label>
        <ResponsiveContainer width="100%" height={235}><LineChart data={points} margin={{top:12,right:20,bottom:24,left:4}}><CartesianGrid stroke="rgb(var(--line))" strokeDasharray="3 4"/><XAxis type="number" dataKey="value" domain={['dataMin','dataMax']} tickFormatter={v=>Number(v).toPrecision(3)} label={{value:'Recorded feature value',position:'insideBottom',offset:-16,fill:'rgb(var(--ink-soft))'}}/><YAxis domain={[0,1]} tickFormatter={v=>`${Math.round(Number(v)*100)}%`} width={50}/><Tooltip content={({active,payload})=>{const p=payload?.[0]?.payload;return active&&p?<div className="result-chart-tooltip"><strong>{featureLabel(curve.feature)}</strong><p>Feature value: {p.value}</p><p>Mean predicted probability: {(p.probability*100).toFixed(1)}%</p></div>:null;}}/><Line type="linear" dataKey="probability" stroke="rgb(var(--accent))" strokeWidth={3} dot={{r:3}} isAnimationActive={false}/></LineChart></ResponsiveContainer>
        <p className="result-caveat">Average model response on the recorded evaluation grid. This is not a causal effect, a patient-specific forecast or a validated clinical threshold. Units are not inferred from column names.</p></>:<p className="result-empty">No response curve was recorded for this analysis. The interface does not infer one from feature importance.</p>}
    </section>
    {point&&<section className="result-chart-card" aria-label="Prediction cutoff performance"><h4>What happened at the recorded prediction cutoff?</h4><p>Probability cutoff: {point.probability_cutoff}. These rates describe the evaluated data at this cutoff.</p>
      <div className="result-rate-grid">{[
        {name:'Sensitivity',value:point.sensitivity,meaning:'Share of actual positive outcomes detected'},
        {name:'Specificity',value:point.specificity,meaning:'Share of actual negative outcomes correctly excluded'},
        {name:'Precision',value:point.precision,meaning:'Share of positive predictions that were correct'},
      ].map(m=><div key={m.name}><span>{m.name}</span><strong>{m.value==null||!Number.isFinite(m.value)?'Not estimable':`${(m.value*100).toFixed(1)}%`}</strong><div className="result-rate-track" aria-hidden="true"><i style={{width:`${Math.max(0,Math.min(1,m.value??0))*100}%`}}/></div><small>{m.meaning}</small></div>)}</div>
      <p className="result-caveat">False alerts: {point.false_positive} · Missed positive outcomes: {point.false_negative}. {point.selection}. {point.status}.</p>
      {precisionExplanation(point) && <p className="result-caveat" data-testid="precision-reason"><strong>Why precision is unavailable: </strong>{precisionExplanation(point)}</p>}
    </section>}
  </div>;
}
