import {useMemo,useState,useId} from 'react';
import {BarChart3,ChevronDown,Download} from 'lucide-react';
import {boxSummary,calculateMetric,confusionMetrics,confusionObservations,metricCsv,type Metric,type Observation,type MetricValue} from '../lib/confusionMetrics';
import './hypothesis-metric-comparison.css';

const colors=['#2563eb','#059669','#9333ea','#d97706','#0891b2','#db2777'];
const shown=(v:MetricValue)=>v.value===null?v.infinite?'∞':'Not calculable':v.value.toLocaleString(undefined,{maximumFractionDigits:5});
type Point={observation:Observation;metric:MetricValue};
type Group={skill:string;points:Point[]};
function groupsFor(observations:Observation[],metric:Metric,beta:number,plannedSkills:readonly string[]=[]):Group[]{
 const groups=new Map<string,Point[]>(plannedSkills.map(skill=>[skill,[]]));
 for(const observation of observations){
  const points=groups.get(observation.skill)??[];
  points.push({observation,metric:calculateMetric(metric,observation.matrix,beta,observation.error)});
  groups.set(observation.skill,points);
 }
 return [...groups].sort(([a],[b])=>a.localeCompare(b)).map(([skill,points])=>({skill,points}));
}
const jitter=(key:string)=>{let n=0;for(const c of key)n=(n*31+c.charCodeAt(0))|0;return ((n>>>0)%101/100-.5)*40;};
const pointLabel=(p:Point)=>`${p.observation.skill}; pipeline ${p.observation.pipeline??'not recorded'}; result ${p.observation.resultId??'not recorded'}; fit ${p.observation.replicate}; ${p.observation.model}; ${shown(p.metric)}; ${p.observation.runTag}`;

function MetricPlot({metric,groups,onSelect,compact=false}:{metric:Metric;groups:Group[];onSelect:(o:Observation)=>void;compact?:boolean}){
 const id=useId();
 const values=groups.flatMap(g=>g.points.flatMap(p=>p.metric.value===null?[]:[p.metric.value]));
 let min=metric.domain?.[0]??Math.min(0,...values),max=metric.domain?.[1]??Math.max(0,...values);
 if(min===max)max=min+1;
 const width=Math.max(compact?420:620,groups.length*155+80),height=360,left=65,right=20,top=25,bottom=100;
 const y=(value:number)=>top+(max-value)/(max-min)*(height-top-bottom);
 const x=(i:number)=>left+(i+.5)*(width-left-right)/Math.max(1,groups.length);
 return <article className="hmc-plot" aria-label={`${metric.label} distribution`}>
  <h4>{metric.label}</h4><p className="hmc-formula">{metric.formula}</p>
  <p>{metric.description} {metric.direction==='higher'?'Higher is better.':metric.direction==='lower'?'Lower is better.':'Descriptive; higher is not necessarily better.'}</p>
  {!values.length&&<p className="hmc-empty" role="status">No finite values for this metric. See coverage and reasons below.</p>}
  <div className="hmc-chart-scroll" role="region" aria-label={`${metric.label} chart; scroll horizontally if needed`} tabIndex={0}>
   <svg viewBox={`0 0 ${width} ${height}`} style={{minWidth:width}} role="img" aria-labelledby={`${id}-title ${id}-description`}>
    <title id={`${id}-title`}>{metric.label} by hypothesis skill</title>
    <desc id={`${id}-description`}>Horizontal axis: recorded hypothesis skill. Vertical axis: {metric.label}. Boxes show quartiles, the line is the median, and whiskers end at observed values within 1.5 interquartile ranges. Every finite evaluation is a selectable point. Non-finite values are excluded and counted separately.</desc>
    {Array.from({length:5},(_,i)=>min+(max-min)*i/4).map(tick=><g key={tick}>
     <line x1={left} x2={width-right} y1={y(tick)} y2={y(tick)} className="hmc-grid"/>
     <text x={left-10} y={y(tick)+4} textAnchor="end" className="hmc-tick">{tick.toLocaleString(undefined,{maximumFractionDigits:3,notation:Math.abs(tick)>=10000?'compact':'standard'})}</text>
    </g>)}
    {groups.map((g,i)=>{
     const summary=boxSummary(g.points.flatMap(p=>p.metric.value===null?[]:[p.metric.value]));
     const center=x(i),color=colors[i%colors.length],chunks=g.skill.match(/.{1,23}/g)??[g.skill];
     return <g key={g.skill}>
      {summary&&summary.n>1&&<g style={{color}}>
       <title>{`${g.skill}: n=${summary.n}; Q1=${summary.q1}; median=${summary.median}; Q3=${summary.q3}; whiskers=${summary.low} to ${summary.high}`}</title>
       <line x1={center} x2={center} y1={y(summary.low)} y2={y(summary.high)} stroke="currentColor"/>
       {[summary.low,summary.high].map((v,j)=><line key={j} x1={center-17} x2={center+17} y1={y(v)} y2={y(v)} stroke="currentColor"/>) }
       <rect x={center-29} y={y(summary.q3)} width={58} height={Math.max(1,y(summary.q1)-y(summary.q3))} fill={color} fillOpacity={.13} stroke={color}/>
       <line x1={center-29} x2={center+29} y1={y(summary.median)} y2={y(summary.median)} stroke={color} strokeWidth={3}/>
      </g>}
      {g.points.map(p=>p.metric.value===null?null:<g key={p.observation.key} role="button" tabIndex={0} aria-label={pointLabel(p)}
       onClick={()=>onSelect(p.observation)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(p.observation);}}} className="hmc-point">
       <title>{pointLabel(p)}</title><circle cx={center+jitter(p.observation.key)} cy={y(p.metric.value)} r={9} fill="transparent"/>
       <circle cx={center+jitter(p.observation.key)} cy={y(p.metric.value)} r={3.5} fill={color} fillOpacity={.65}/>
      </g>)}
      <text x={center} y={height-bottom+21} textAnchor="middle" className="hmc-skill-label"><title>{g.skill}</title>{chunks.slice(0,3).map((chunk,j)=><tspan key={j} x={center} dy={j?14:0}>{j===2&&chunks.length>3?chunk+'…':chunk}</tspan>)}</text>
      <text x={center} y={height-17} textAnchor="middle" className="hmc-tick">{summary?.n??0} finite / {g.points.length} evaluations</text>
     </g>;
    })}
   </svg>
  </div>
 </article>;
}

export default function HypothesisMetricComparison({results,runTag,plannedSkills}:{results:readonly unknown[];runTag?:string|null;plannedSkills?:readonly string[]}){
 const observations=useMemo(()=>confusionObservations(results),[results]);
 const [metricId,setMetricId]=useState('balanced_accuracy'),[model,setModel]=useState('all');
 const [target,setTarget]=useState(''),[betaInput,setBetaInput]=useState('1'),[gallery,setGallery]=useState(false);
 const [expanded,setExpanded]=useState(true),[selectedKey,setSelectedKey]=useState<string|null>(null);
 const panel=useId(),beta=Number(betaInput),betaValid=betaInput.trim()!==''&&Number.isFinite(beta)&&beta>0&&beta<=100;
 const targets=[...new Set(observations.map(o=>o.target))].sort(),models=[...new Set(observations.map(o=>o.model))].sort();
 const currentTarget=targets.includes(target)?target:targets[0]??'';
 const currentModel=models.includes(model)?model:'all';
 const filtered=useMemo(()=>observations.filter(o=>o.target===currentTarget&&(currentModel==='all'||o.model===currentModel)),[observations,currentTarget,currentModel]);
 const metric=confusionMetrics.find(m=>m.id===metricId)??confusionMetrics[0];
 const groups=useMemo(()=>groupsFor(filtered,metric,metric.id.includes('fbeta')&&!betaValid?NaN:betaValid?beta:1,plannedSkills),[filtered,metric,beta,betaValid,plannedSkills]);
 const selected=filtered.find(o=>o.key===selectedKey);
 const select=(o:Observation)=>setSelectedKey(o.key);
 const download=()=>{
  const url=URL.createObjectURL(new Blob([metricCsv(filtered,confusionMetrics,betaValid?beta:NaN)],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=`${runTag||'experiment'}-confusion-metrics.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 const exportEnabled=filtered.length>0&&betaValid;
 return <section className="hypothesis-metric-comparison" aria-label="Hypothesis skill performance distributions">
  <button type="button" className="hmc-toggle" onClick={()=>setExpanded(v=>!v)} aria-expanded={expanded} aria-controls={panel}>
   <BarChart3 size={19} aria-hidden="true"/><span><strong>Compare performance by hypothesis skill</strong><small>Confusion-matrix metrics · box plots and recorded evaluations</small></span><ChevronDown size={17} style={{transform:expanded?'rotate(180deg)':undefined}}/>
  </button>
  <div id={panel} hidden={!expanded} className="hmc-body">
   <p>Each point is one recorded held-out model evaluation, including retained evaluations from continued executions. Boxes summarize evaluations within each recorded hypothesis skill. Multiple skills used together remain one combined condition. Scheduled skills with no matching evaluations show an empty group, not a zero score.</p>
   <div className="hmc-controls">
    <label>Metric<select aria-label="Performance metric" value={metric.id} onChange={e=>setMetricId(e.target.value)}>{[...new Set(confusionMetrics.map(m=>m.category))].map(category=><optgroup label={category} key={category}>{confusionMetrics.filter(m=>m.category===category).map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</optgroup>)}</select></label>
    <label>Model<select aria-label="Comparison model" value={currentModel} onChange={e=>setModel(e.target.value)}><option value="all">All recorded models</option>{models.map(m=><option key={m}>{m}</option>)}</select></label>
    {targets.length>1&&<label>Target<select aria-label="Comparison target" value={currentTarget} onChange={e=>setTarget(e.target.value)}>{targets.map(t=><option key={t}>{t}</option>)}</select></label>}
    <label>F-beta weight β<input aria-label="F-beta weight" type="number" min="0.01" max="100" step="0.1" value={betaInput} onChange={e=>setBetaInput(e.target.value)} aria-invalid={!betaValid}/></label>
    <button type="button" onClick={download} disabled={!exportEnabled}><Download size={15}/>Download all metrics CSV</button>
   </div>
   {!betaValid&&<p role="alert">Choose a finite beta greater than 0 and at most 100. Other metrics remain available.</p>}
   {!filtered.length?<p className="hmc-empty">No recorded evaluations are available for this selection yet.</p>:<>
    <MetricPlot metric={metric} groups={groups} onSelect={select}/>
    <p className="hmc-method">Boxes: 25th–75th percentiles with the median; whiskers: observed values within 1.5×IQR. Quartiles use linear interpolation. Every finite value is shown, including outliers. One value is shown as a point. A box is a distribution, not a confidence interval.</p>
    <div className="hmc-table-scroll" tabIndex={0} role="region" aria-label="Metric coverage and skill summary"><table><caption>{metric.label} · {currentTarget}</caption><thead><tr>{['Hypothesis skill','Finite / total','Median','Q1–Q3','Not calculable','Infinite'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{groups.map(g=>{
     const stats=boxSummary(g.points.flatMap(p=>p.metric.value===null?[]:[p.metric.value]));
     return <tr key={g.skill}><th scope="row">{g.skill}</th><td>{stats?.n??0} / {g.points.length}</td><td>{stats?shown({value:stats.median}):'—'}</td><td>{stats?`${shown({value:stats.q1})}–${shown({value:stats.q3})}`:'—'}</td><td>{g.points.filter(p=>p.metric.value===null&&!p.metric.infinite).length}</td><td>{g.points.filter(p=>p.metric.infinite).length}</td></tr>;
    })}</tbody></table></div>
    {selected&&<section className="hmc-selected" aria-label="Selected evaluation evidence"><h4>Selected evaluation</h4><p>{selected.skill} · Pipeline {selected.pipeline??'not recorded'} · Result {selected.resultId??'not recorded'} · Fit {selected.replicate}</p>
     <dl><div><dt>Original execution</dt><dd>{selected.runTag||'Not recorded'}</dd></div><div><dt>Model</dt><dd>{selected.model}</dd></div><div><dt>Seed / threshold</dt><dd>{selected.seed??'Not recorded'} / {selected.threshold??'Not recorded'}</dd></div><div><dt>TN / FP / FN / TP</dt><dd>{[selected.matrix.tn,selected.matrix.fp,selected.matrix.fn,selected.matrix.tp].map(n=>Number.isFinite(n)?n:'Not recorded').join(' / ')}</dd></div><div><dt>{metric.label}</dt><dd>{shown(calculateMetric(metric,selected.matrix,betaValid?beta:metric.id.includes('fbeta')?NaN:1,selected.error))}</dd></div></dl>
     <p>{calculateMetric(metric,selected.matrix,betaValid?beta:metric.id.includes('fbeta')?NaN:1,selected.error).reason}</p></section>}
    <details className="hmc-details"><summary>Recorded values and calculation reasons</summary><div className="hmc-table-scroll" tabIndex={0}><table><thead><tr>{['Skill','Pipeline / result','Model / fit','Threshold','TN / FP / FN / TP','Value','Status / reason','Original execution'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{groups.flatMap(g=>g.points).map(p=><tr key={p.observation.key}><th scope="row">{p.observation.skill}</th><td><button type="button" onClick={()=>select(p.observation)}>{p.observation.pipeline??'—'} / {p.observation.resultId??'—'}</button></td><td>{p.observation.model} / {p.observation.replicate}</td><td>{p.observation.threshold??'Not recorded'}</td><td>{Object.values(p.observation.matrix).map(n=>Number.isFinite(n)?n:'—').join(' / ')}</td><td>{shown(p.metric)}</td><td>{p.metric.reason??'Finite'}</td><td>{p.observation.runTag}</td></tr>)}</tbody></table></div></details>
    <button type="button" className="hmc-gallery-toggle" aria-expanded={gallery} onClick={()=>setGallery(v=>!v)}>{gallery?'Hide all metric charts':`Show all ${confusionMetrics.length} metric charts`}</button>
    {gallery&&<div className="hmc-gallery">{confusionMetrics.filter(m=>m.id!==metric.id).map(m=><MetricPlot key={m.id} compact metric={m} groups={groupsFor(filtered,m,m.id.includes('fbeta')&&!betaValid?NaN:betaValid?beta:1,plannedSkills)} onSelect={o=>{setMetricId(m.id);select(o);}}/>)}</div>}
   </>}
   <details className="hmc-details"><summary>Metric definitions, formulas and interpretation ({confusionMetrics.length})</summary><p>N = TN + FP + FN + TP. Positive means the recorded encoded class 1 for target {currentTarget||'not recorded'}. Definitions use the original recorded threshold. Identical aliases share a metric; class-average variants are labelled explicitly.</p><div className="hmc-table-scroll" tabIndex={0}><table><thead><tr><th>Metric</th><th>Formula</th><th>Meaning</th></tr></thead><tbody>{confusionMetrics.map(m=><tr key={m.id}><th scope="row">{m.label}</th><td>{m.formula}</td><td>{m.description}</td></tr>)}</tbody></table></div></details>
   <p className="hmc-method">No probabilities or new model calls are used. AUROC, PR-AUC, average precision, probability Brier score and log loss cannot be recovered from one confusion matrix. Undefined and infinite values are excluded from boxes, counted above and preserved with reasons in CSV. No zero filling or continuity correction is applied.</p>
   <p className="hmc-method">Different models, feature sets, thresholds and split allocations can affect these distributions; use the model filter and inspect individual evaluations. Reused subjects and repeated fits need not be independent. These plots do not isolate the effect of the hypothesis skill.</p>
   <p className="hmc-method">Definitions: <a href="https://scikit-learn.org/stable/modules/model_evaluation.html" target="_blank" rel="noreferrer">scikit-learn metrics</a> · <a href="https://www.ncbi.nlm.nih.gov/sites/books/NBK98249/table/appendix.t1/" target="_blank" rel="noreferrer">AHRQ diagnostic measures</a>.</p>
  </div>
 </section>;
}
