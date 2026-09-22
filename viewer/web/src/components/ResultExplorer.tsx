import ContentOrigin from "./ContentOrigin";
import { loopLabel } from '../lib/loopLabel';
import { useState } from 'react';
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts';
import type { Result } from '../types';

export const resultKey = (r: Result) => `${r.run_tag || ''}:${r.result_id}`;
export const resultTitle = (r: Result) => `${r.pipeline_name || 'Analysis'} · ${loopLabel(r)}`;
export const predictorNames = (r: Result) => [...new Set(r.columns_used ?? [])].filter(c => c !== r.y_column);
export function featureLabel(column: string) {
  if(column.startsWith('DX__')) return column.split('__').slice(2).join('__') || column;
  return column.replace(/^(LAB|MED|CAT)__/, '').replaceAll('__', ' · ');
}
const colors = ['rgb(var(--accent))', '#9a88db', '#d2a35a'];

export default function ResultExplorer({results,selected,onSelect}:{results:Result[];selected:string;onSelect:(key:string)=>void}) {
  const [query,setQuery]=useState('');
  const [sort,setSort]=useState('recent');
  const [limit,setLimit]=useState(12);
  const measured=results.filter(r=>r.auc!=null&&Number.isFinite(r.auc));
  const groups=[...new Set(results.map(r=>r.pipeline_name||r.run_tag||'Analysis'))];
  const best=measured.length?Math.max(...measured.map(r=>r.auc!)):null;
  const matching=results.filter(r=>[resultTitle(r),r.hypothesis,r.perspective,...predictorNames(r)].join(' ').toLowerCase().includes(query.toLowerCase()));
  const ordered=[...matching].sort((a,b)=>sort==='auc'?(b.auc??-1)-(a.auc??-1):sort==='simple'?predictorNames(a).length-predictorNames(b).length:Date.parse(b.created_at)-Date.parse(a.created_at)||b.result_id-a.result_id);
  const points=measured.map(r=>({x:predictorNames(r).length,y:r.auc!,key:resultKey(r),title:resultTitle(r),question:r.perspective||r.hypothesis,group:r.pipeline_name||r.run_tag||'Analysis'}));
  return <section className="result-explorer" aria-label="Visual results explorer">
    <header><p className="result-eyebrow">FROM QUESTIONS TO EVIDENCE</p><h3>Explore what the pipelines found</h3><p>Compare measured results, choose a loop, and inspect the features and evidence behind it.</p><ContentOrigin kind="proposal" compact/><p>Question and hypothesis text are research proposals. AUC, counts and sorting are calculated from recorded data.</p></header>
    <div className="result-summary-grid">
      <div><span>Recorded analyses</span><strong>{results.length}</strong><small>{groups.length} pipeline{groups.length===1?'':'s'} in this view</small></div>
      <div><span>With AUC measured</span><strong>{measured.length}</strong><small>{results.length-measured.length} without a recorded AUC</small></div>
      <div><span>Highest observed AUC</span><strong>{best?.toFixed(3)??'—'}</strong><small>Descriptive maximum, not a recommendation</small></div>
    </div>
    <section className="result-chart-card">
      <h4>Predictive performance vs. number of inputs</h4><p>Each point is one analysis. Higher means better ranking of outcomes; farther right means more predictor columns. Select a point or an analysis below.</p>
      {points.length ? <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{top:20,right:20,bottom:30,left:0}}>
          <CartesianGrid stroke="rgb(var(--line))" strokeDasharray="3 4"/>
          <XAxis type="number" dataKey="x" name="Predictors" allowDecimals={false} domain={[0,'dataMax + 1']} label={{value:'Number of predictor columns',position:'insideBottom',offset:-18,fill:'rgb(var(--ink-soft))'}}/>
          <YAxis type="number" dataKey="y" name="AUC" domain={[0,1]} ticks={[0,.25,.5,.75,1]} width={45}/>
          <ReferenceLine y={.5} stroke="rgb(var(--ink-soft))" strokeDasharray="5 4" label={{value:'Chance ranking · AUC 0.5',position:'insideTopRight',fill:'rgb(var(--ink-soft))',fontSize:11}}/>
          <Tooltip content={({active,payload})=>{const p=payload?.[0]?.payload;return active&&p?<div className="result-chart-tooltip"><strong>{p.title}</strong><p>AUC {Number(p.y).toFixed(4)} · {p.x} predictors</p><p>{p.question}</p></div>:null;}}/>
          {groups.map((group,i)=><Scatter key={group} name={group} data={points.filter(p=>p.group===group)} fill={colors[i%colors.length]} isAnimationActive={false} onClick={(p)=>{if(p?.payload?.key)onSelect(p.payload.key);}}/>)}
        </ScatterChart>
      </ResponsiveContainer>:<p className="result-empty">No measured AUC is available yet. Unmeasured analyses remain in the list below.</p>}
      <div className="result-legend">{groups.map((g,i)=><span key={g}><i style={{background:colors[i%colors.length]}}/>{g}</span>)}</div>
      <p className="result-caveat">AUC measures ranking, not clinical benefit or causation. Comparisons require compatible targets, datasets and evaluation settings. Overlapping points can be selected individually in the list.</p>
    </section>
    <div className="result-explorer-controls"><label>Find an analysis<input aria-label="Search results" value={query} onChange={e=>{setQuery(e.target.value);setLimit(12);}} placeholder="Question, feature or pipeline"/></label><label>Order by<select aria-label="Sort results" value={sort} onChange={e=>setSort(e.target.value)}><option value="recent">Newest analysis</option><option value="auc">Highest observed AUC</option><option value="simple">Fewest predictors</option></select></label></div>
    <div className="result-picker" aria-label="Choose an analysis">{ordered.slice(0,limit).map(r=><button key={resultKey(r)} aria-pressed={selected===resultKey(r)} onClick={()=>onSelect(resultKey(r))}>
      <span className="result-picker-title">{resultTitle(r)}</span><span className="result-picker-question">{r.perspective||r.hypothesis}</span>
      <span className="result-picker-metrics"><strong>AUC {r.auc?.toFixed(3)??'not recorded'}</strong><span>{predictorNames(r).length} predictors · {r.model||'Model not recorded'}</span></span>
      <span className="result-auc-track" aria-hidden="true"><i style={{width:`${Math.max(0,Math.min(1,r.auc??0))*100}%`}}/><b/></span>
      <span className="result-picker-action">{selected===resultKey(r)?'Showing evidence below':'Inspect this analysis →'}</span>
    </button>)}</div>
    {!ordered.length&&<p className="result-empty">No analyses match your search. <button onClick={()=>setQuery('')}>Clear search</button></p>}
    {ordered.length>limit&&<button className="result-more" onClick={()=>setLimit(n=>n+12)}>Show 12 more ({ordered.length-limit} remaining)</button>}
    <p className="result-caveat">The AUC bars use a 0–1 scale; the center marker is chance ranking (0.5). New results appear automatically while your selected analysis stays open.</p>
  </section>;
}
