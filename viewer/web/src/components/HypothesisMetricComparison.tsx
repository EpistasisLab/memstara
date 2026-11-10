import {useMemo,useState,useId} from 'react';
import {ArrowUpRight,BarChart3,ChevronDown,Info,SlidersHorizontal} from 'lucide-react';
import {boxSummary,calculateMetric,confusionMetrics,confusionObservations,type Metric,type Observation} from '../lib/confusionMetrics';
import {comparisonColor,comparisonLabel,metricValue} from '../lib/skillComparison';
import {useControl} from '../store/control';
import SkillMetricPlot,{type MetricGroup} from './SkillMetricPlot';
import './hypothesis-metric-comparison.css';

const primaryMetrics=[['balanced_accuracy','Balanced accuracy'],['mcc','MCC'],['f1','F1'],['sensitivity','Recall'],['specificity','Specificity'],['precision','Precision']];
function groupsFor(observations:Observation[],metric:Metric,beta:number,plannedSkills:readonly string[]=[]):MetricGroup[]{
 const groups=new Map<string,MetricGroup['points']>(plannedSkills.map(skill=>[skill,[]]));
 for(const observation of observations){
  const points=groups.get(observation.skill)??[];
  points.push({observation,metric:calculateMetric(metric,observation.matrix,beta,observation.error)});
  groups.set(observation.skill,points);
 }
 return [...groups].sort(([a],[b])=>a.localeCompare(b)).map(([skill,points])=>({skill,points}));
}

export default function HypothesisMetricComparison({results,plannedSkills,skillTitles={},onOpenResult}:{
 results:readonly unknown[];runTag?:string|null;plannedSkills?:readonly string[];skillTitles?:Record<string,string>;
 onOpenResult?:(observation:Observation)=>void;
}){
 const observations=useMemo(()=>confusionObservations(results),[results]);
 const catalog=useControl(state=>state.catalog);
 const titles=useMemo(()=>({...Object.fromEntries(catalog.map(skill=>[skill.id,skill.title])),...skillTitles}),[catalog,skillTitles]);
 const [metricId,setMetricId]=useState('balanced_accuracy'),[model,setModel]=useState('all');
 const [target,setTarget]=useState(''),[betaInput,setBetaInput]=useState('1'),[gallery,setGallery]=useState(false);
 const [order,setOrder]=useState('name'),[expanded,setExpanded]=useState(false),[selectedKey,setSelectedKey]=useState<string|null>(null);
 const panel=useId(),beta=Number(betaInput),betaValid=betaInput.trim()!==''&&Number.isFinite(beta)&&beta>0&&beta<=100;
 const targets=[...new Set(observations.map(observation=>observation.target))].sort(),models=[...new Set(observations.map(observation=>observation.model))].sort();
 const currentTarget=targets.includes(target)?target:targets[0]??'',currentModel=models.includes(model)?model:'all';
 const filtered=observations.filter(observation=>observation.target===currentTarget&&(currentModel==='all'||observation.model===currentModel));
 const metric=confusionMetrics.find(item=>item.id===metricId)??confusionMetrics[0];
 const metricBeta=metric.id.includes('fbeta')&&!betaValid?NaN:betaValid?beta:1;
 const groups=groupsFor(filtered,metric,metricBeta,plannedSkills).sort((a,b)=>{
  if(order==='name')return comparisonLabel(a.skill,titles).localeCompare(comparisonLabel(b.skill,titles));
  const median=(group:MetricGroup)=>boxSummary(group.points.flatMap(point=>point.metric.value===null?[]:[point.metric.value]))?.median;
  const left=median(a),right=median(b);
  return left===undefined?right===undefined?0:1:right===undefined?-1:(order==='high'?right-left:left-right);
 });
 const selected=filtered.find(observation=>observation.key===selectedKey);
 const finite=groups.reduce((sum,group)=>sum+group.points.filter(point=>point.metric.value!==null).length,0);
 const runs=new Set(filtered.map(observation=>observation.runTag).filter(Boolean)).size;
 const select=(observation:Observation)=>{setSelectedKey(observation.key);onOpenResult?.(observation);};
 return <section className="hypothesis-metric-comparison" aria-label="Hypothesis skill performance distributions">
  <button type="button" className="hmc-toggle" onClick={()=>setExpanded(value=>!value)} aria-expanded={expanded} aria-controls={panel}>
   <span className="hmc-heading-icon"><BarChart3 size={21} aria-hidden="true"/></span><span className="hmc-heading-text"><small>Performance comparison</small><strong>Compare performance by hypothesis skill</strong></span>
   <span className="hmc-heading-count">{observations.length} evaluations</span><ChevronDown size={18} aria-hidden="true" style={{transform:expanded?'rotate(180deg)':undefined}}/>
  </button>
  <div id={panel} hidden={!expanded} className="hmc-body">
   {expanded && <>
   <div className="hmc-overview" aria-label="Comparison coverage"><span><b>{groups.length}</b>Hypothesis skills</span><span><b>{filtered.length}</b>Evaluations in view</span><span><b>{runs}</b>Execution attempts</span><span className={finite<filtered.length?'hmc-coverage-warning':''}><b>{finite} / {filtered.length}</b>Calculable for this metric</span></div>
   <div className="hmc-controls">
    <label>Metric<select aria-label="Performance metric" value={metric.id} onChange={event=>setMetricId(event.target.value)}>{[...new Set(confusionMetrics.map(item=>item.category))].map(category=><optgroup label={category} key={category}>{confusionMetrics.filter(item=>item.category===category).map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</optgroup>)}</select></label>
    <label>Model<select aria-label="Comparison model" value={currentModel} onChange={event=>setModel(event.target.value)}><option value="all">All recorded models</option>{models.map(item=><option key={item}>{item}</option>)}</select></label>
    {targets.length>1&&<label>Target<select aria-label="Comparison target" value={currentTarget} onChange={event=>setTarget(event.target.value)}>{targets.map(item=><option key={item}>{item}</option>)}</select></label>}
   </div>
   <div className="hmc-metric-presets" aria-label="Frequently used metrics">{primaryMetrics.map(([id,label])=><button key={id} type="button" aria-pressed={metric.id===id} onClick={()=>setMetricId(id)}>{label}</button>)}</div>
   <details className="hmc-options"><summary><SlidersHorizontal size={14}/>Comparison options</summary><div className="hmc-option-fields">
    <label>Skill order<select aria-label="Skill order" value={order} onChange={event=>setOrder(event.target.value)}><option value="name">Skill name</option><option value="high">Median: high to low</option><option value="low">Median: low to high</option></select></label>
    <label>F-beta weight β<input aria-label="F-beta weight" type="number" min="0.01" max="100" step="0.1" value={betaInput} onChange={event=>setBetaInput(event.target.value)} aria-invalid={!betaValid}/></label>
    <p>Beta affects custom F-beta metrics only. All other metrics keep their original definitions.</p>
   </div></details>
   {!betaValid&&<p className="hmc-notice" role="alert">Choose a finite beta greater than 0 and at most 100. Other metrics remain available.</p>}
   {!filtered.length?<p className="hmc-empty">No recorded evaluations are available for this selection yet.</p>:<>
    <p className="hmc-interaction-hint"><Info size={15}/>{onOpenResult?'Hover for details. Click any point to open and highlight its Results tile.':'Hover for details or select a point to inspect its recorded evidence.'}</p>
    <SkillMetricPlot metric={metric} groups={groups} titles={titles} onSelect={select} selectedKey={selectedKey} navigable={!!onOpenResult}/>
    <div className="hmc-summary-heading"><h4>Skill summary</h4><span>Target: {currentTarget}</span></div>
    <div className="hmc-table-scroll" tabIndex={0} role="region" aria-label="Metric coverage and skill summary"><table><caption className="sr-only">{metric.label} · {currentTarget}</caption><thead><tr>{['Hypothesis skill','Finite / total','Median','Q1–Q3','Not calculable','Infinite'].map(heading=><th key={heading} scope="col">{heading}</th>)}</tr></thead><tbody>{groups.map(group=>{
     const stats=boxSummary(group.points.flatMap(point=>point.metric.value===null?[]:[point.metric.value]));
     return <tr key={group.skill}><th scope="row" title={group.skill}><span className="hmc-skill-name"><i style={{background:comparisonColor(group.skill)}}/>{comparisonLabel(group.skill,titles)}</span></th><td>{stats?.n??0} / {group.points.length}</td><td className="hmc-median">{stats?metricValue({value:stats.median}):'—'}</td><td>{stats?`${metricValue({value:stats.q1})}–${metricValue({value:stats.q3})}`:'—'}</td><td>{group.points.filter(point=>point.metric.value===null&&!point.metric.infinite).length}</td><td>{group.points.filter(point=>point.metric.infinite).length}</td></tr>;
    })}</tbody></table></div>
    {selected&&<section className="hmc-selected" aria-label="Selected evaluation evidence"><header><div><small>Selected evaluation</small><h4>{comparisonLabel(selected.skill,titles)}</h4></div>{onOpenResult&&<button type="button" onClick={()=>onOpenResult(selected)}>View result<ArrowUpRight size={15}/></button>}</header>
     <p>Pipeline {selected.pipeline??'not recorded'} · Result {selected.resultId??'not recorded'} · Fit {selected.replicate}</p>
     <dl><div><dt>{metric.label}</dt><dd>{metricValue(calculateMetric(metric,selected.matrix,metricBeta,selected.error))}</dd></div><div><dt>Model</dt><dd>{selected.model}</dd></div><div><dt>Seed / threshold</dt><dd>{selected.seed??'Not recorded'} / {selected.threshold??'Not recorded'}</dd></div><div><dt>TN / FP / FN / TP</dt><dd>{[selected.matrix.tn,selected.matrix.fp,selected.matrix.fn,selected.matrix.tp].map(number=>Number.isFinite(number)?number:'Not recorded').join(' / ')}</dd></div><div><dt>Original execution</dt><dd>{selected.runTag||'Not recorded'}</dd></div></dl>
     {calculateMetric(metric,selected.matrix,metricBeta,selected.error).reason&&<p>{calculateMetric(metric,selected.matrix,metricBeta,selected.error).reason}</p>}
    </section>}
    <details className="hmc-details"><summary>Recorded values and calculation reasons</summary><div className="hmc-table-scroll" tabIndex={0}><table><thead><tr>{['Skill','Pipeline / result','Model / fit','Threshold','TN / FP / FN / TP','Value','Status / reason','Original execution'].map(heading=><th key={heading}>{heading}</th>)}</tr></thead><tbody>{groups.flatMap(group=>group.points).map(point=><tr key={point.observation.key}><th scope="row" title={point.observation.skill}>{comparisonLabel(point.observation.skill,titles)}</th><td><button type="button" onClick={()=>select(point.observation)}>{point.observation.pipeline??'—'} / {point.observation.resultId??'—'}</button></td><td>{point.observation.model} / {point.observation.replicate}</td><td>{point.observation.threshold??'Not recorded'}</td><td>{Object.values(point.observation.matrix).map(number=>Number.isFinite(number)?number:'—').join(' / ')}</td><td>{metricValue(point.metric)}</td><td>{point.metric.reason??'Finite'}</td><td>{point.observation.runTag}</td></tr>)}</tbody></table></div></details>
    <button type="button" className="hmc-gallery-toggle" aria-expanded={gallery} onClick={()=>setGallery(value=>!value)}><BarChart3 size={15}/>{gallery?'Hide all metric charts':`Show all ${confusionMetrics.length} metric charts`}<ChevronDown size={15} style={{transform:gallery?'rotate(180deg)':undefined}}/></button>
    {gallery&&<div className="hmc-gallery">{confusionMetrics.filter(item=>item.id!==metric.id).map(item=><SkillMetricPlot key={item.id} compact metric={item} groups={groupsFor(filtered,item,item.id.includes('fbeta')&&!betaValid?NaN:betaValid?beta:1,groups.map(group=>group.skill))} titles={titles} selectedKey={selectedKey} navigable={!!onOpenResult} onSelect={observation=>{setMetricId(item.id);select(observation);}}/>)}</div>}
   </>}
   <details className="hmc-details hmc-methods"><summary>How to read these comparisons</summary>
    <p>Each point is one recorded held-out model evaluation, including retained evaluations from continued executions. Nearby points are spread horizontally so they remain selectable; their vertical metric values are unchanged. Boxes span the 25th–75th percentiles with the median; whiskers end at observed values within 1.5×IQR. Quartiles use linear interpolation. All finite values, including outliers, are shown. A single evaluation is shown as a point. A box is a distribution, not a confidence interval.</p>
    <p>Models, feature sets, thresholds and split allocations can affect these distributions. Use the model filter and inspect individual results. Reused subjects and repeated fits need not be independent; these plots do not isolate the effect of the hypothesis skill. Multiple skills used together remain one combined condition. Scheduled skills with no matching evaluations show an empty group, not a zero score.</p>
    <p>No new model calls are made. AUROC, PR-AUC, average precision, probability Brier score and log loss cannot be recovered from one confusion matrix. Undefined and infinite values are excluded from boxes and listed with reasons under Recorded values and calculation reasons. No zero filling or continuity correction is applied.</p>
   </details>
   <details className="hmc-details"><summary>Metric definitions and formulas ({confusionMetrics.length})</summary><p>N = TN + FP + FN + TP. Positive means the recorded encoded class 1 for target {currentTarget||'not recorded'}. Definitions use the original recorded threshold.</p><div className="hmc-table-scroll" tabIndex={0}><table><thead><tr><th>Metric</th><th>Formula</th><th>Meaning</th></tr></thead><tbody>{confusionMetrics.map(item=><tr key={item.id}><th scope="row">{item.label}</th><td>{item.formula}</td><td>{item.description}</td></tr>)}</tbody></table></div>
    <p>References: <a href="https://scikit-learn.org/stable/modules/model_evaluation.html" target="_blank" rel="noreferrer">scikit-learn metrics</a> · <a href="https://www.ncbi.nlm.nih.gov/sites/books/NBK98249/table/appendix.t1/" target="_blank" rel="noreferrer">AHRQ diagnostic measures</a>.</p>
   </details>
   </>}
  </div>
 </section>;
}
