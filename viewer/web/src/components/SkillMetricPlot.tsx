import {useId,useState} from 'react';
import {createPortal} from 'react-dom';
import {boxSummary,type Metric,type MetricValue,type Observation} from '../lib/confusionMetrics';
import {comparisonColor,comparisonLabel,labelLines,swarmOffsets,metricValue} from '../lib/skillComparison';

export type MetricPoint={observation:Observation;metric:MetricValue};
export type MetricGroup={skill:string;points:MetricPoint[]};
const pointLabel=(p:MetricPoint)=>`${p.observation.skill}; pipeline ${p.observation.pipeline??'not recorded'}; result ${p.observation.resultId??'not recorded'}; fit ${p.observation.replicate}; ${p.observation.model}; ${metricValue(p.metric)}; ${p.observation.runTag}`;

export default function SkillMetricPlot({metric,groups,titles,onSelect,selectedKey,navigable=false,compact=false}:{
 metric:Metric;groups:MetricGroup[];titles:Record<string,string>;onSelect:(observation:Observation)=>void;
 selectedKey:string|null;navigable?:boolean;compact?:boolean;
}){
 const id=useId();
 const [hover,setHover]=useState<{point:MetricPoint;left:number;top:number;above:boolean}|null>(null);
 const values=groups.flatMap(group=>group.points.flatMap(point=>point.metric.value===null?[]:[point.metric.value]));
 let min=metric.domain?.[0]??Math.min(0,...values),max=metric.domain?.[1]??Math.max(0,...values);
 if(min===max)max=min+1;
 const height=380,left=58,right=24,top=24,bottom=105;
 const y=(value:number)=>top+(max-value)/(max-min)*(height-top-bottom);
 const offsets=groups.map(group=>swarmOffsets(group.points.flatMap(point=>point.metric.value===null?[]:[{key:point.observation.key,value:point.metric.value}]),y));
 const columnWidths=offsets.map(positions=>Math.max(175,2*Math.max(0,...[...positions.values()].map(Math.abs))+70));
 const naturalWidth=columnWidths.reduce((sum,value)=>sum+value,0)+left+right,width=Math.max(compact?440:640,naturalWidth);
 const padding=(width-naturalWidth)/Math.max(1,groups.length);
 const x=(i:number)=>left+columnWidths.slice(0,i).reduce((sum,value)=>sum+value+padding,0)+(columnWidths[i]+padding)/2;
 const show=(point:MetricPoint,element:SVGGElement)=>{
  const bounds=element.getBoundingClientRect();
  setHover({point,left:Math.max(12,Math.min(bounds.left-120,window.innerWidth-292)),
   top:bounds.top>255?bounds.top-12:bounds.bottom+12,above:bounds.top>255});
 };
 const direction=metric.direction==='higher'?'Higher is better':metric.direction==='lower'?'Lower is better':'Descriptive metric';
 return <article className="hmc-plot" aria-label={`${metric.label} distribution`}>
  <header className="hmc-plot-heading"><div><h4>{metric.label}</h4><p>{metric.description}</p></div><span className="hmc-direction">{direction}</span></header>
  {!values.length&&<p className="hmc-empty" role="status">No finite values for this metric. See coverage and reasons below.</p>}
  <div className="hmc-chart-scroll" role="region" aria-label={`${metric.label} chart; scroll horizontally if needed`} tabIndex={0} onScroll={()=>setHover(null)}>
   <svg viewBox={`0 0 ${width} ${height}`} style={{minWidth:width}} role="group" aria-roledescription="interactive chart" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}>
    <title id={`${id}-title`}>{metric.label} by hypothesis skill</title>
    <desc id={`${id}-description`}>Horizontal axis: hypothesis skill. Vertical axis: {metric.label}. Boxes show quartiles with the median. Whiskers end at observed values within 1.5 interquartile ranges. Each point is one recorded evaluation. {navigable?'Click a point or press Enter to open its Results tile.':'Select a point to inspect its recorded evidence.'} Non-finite values are counted separately.</desc>
    {Array.from({length:5},(_,i)=>min+(max-min)*i/4).map(tick=><g key={tick}>
     <line x1={left} x2={width-right} y1={y(tick)} y2={y(tick)} className="hmc-grid"/>
     <text x={left-12} y={y(tick)+4} textAnchor="end" className="hmc-tick">{tick.toLocaleString(undefined,{maximumFractionDigits:3,notation:Math.abs(tick)>=10000?'compact':'standard'})}</text>
    </g>)}
    {groups.map((group,i)=>{
     const stats=boxSummary(group.points.flatMap(point=>point.metric.value===null?[]:[point.metric.value]));
     const center=x(i),color=comparisonColor(group.skill),label=comparisonLabel(group.skill,titles);
     return <g key={group.skill}>
      {stats&&stats.n>1&&<g style={{color}}>
       <title>{`${label}: n=${stats.n}; Q1=${stats.q1}; median=${stats.median}; Q3=${stats.q3}; whiskers=${stats.low} to ${stats.high}`}</title>
       <line x1={center} x2={center} y1={y(stats.low)} y2={y(stats.high)} stroke="currentColor" strokeWidth={1.5}/>
       {[stats.low,stats.high].map((value,j)=><line key={j} x1={center-17} x2={center+17} y1={y(value)} y2={y(value)} stroke="currentColor" strokeWidth={1.5}/>)}
       <rect x={center-31} y={y(stats.q3)} width={62} height={Math.max(2,y(stats.q1)-y(stats.q3))} rx={3} fill={color} fillOpacity={.13} stroke={color} strokeWidth={1.5}/>
       <line x1={center-31} x2={center+31} y1={y(stats.median)} y2={y(stats.median)} stroke={color} strokeWidth={3}/>
      </g>}
      {group.points.map(point=>point.metric.value===null?null:<g key={point.observation.key} role="button" tabIndex={0}
       aria-label={pointLabel(point)} aria-pressed={selectedKey===point.observation.key}
       aria-describedby={hover?.point.observation.key===point.observation.key?`${id}-tooltip`:undefined}
       onMouseEnter={event=>show(point,event.currentTarget)} onMouseLeave={()=>setHover(null)}
       onFocus={event=>show(point,event.currentTarget)} onBlur={()=>setHover(null)}
       onClick={()=>{setHover(null);onSelect(point.observation);}}
       onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setHover(null);onSelect(point.observation);}else if(event.key==='Escape')setHover(null);}}
       className="hmc-point">
       <circle cx={center+offsets[i].get(point.observation.key)!} cy={y(point.metric.value)} r={8} fill="transparent"/>
       {selectedKey===point.observation.key&&<circle cx={center+offsets[i].get(point.observation.key)!} cy={y(point.metric.value)} r={8} fill="none" stroke={color} strokeWidth={2}/>}
       <circle cx={center+offsets[i].get(point.observation.key)!} cy={y(point.metric.value)} r={4} fill={color} fillOpacity={.8}/>
      </g>)}
      <text x={center} y={height-bottom+27} textAnchor="middle" className="hmc-skill-label"><title>{group.skill}</title>{labelLines(label).map((line,j)=><tspan key={j} x={center} dy={j?16:0}>{line}</tspan>)}</text>
      <text x={center} y={height-15} textAnchor="middle" className="hmc-tick">{stats?.n??0} / {group.points.length} evaluations</text>
     </g>;
    })}
   </svg>
  </div>
  <div className="hmc-chart-key"><span><i className="hmc-key-box"/>Interquartile range</span><span><i className="hmc-key-line"/>Median</span><span><i className="hmc-key-point"/>Recorded evaluation</span></div>
  {hover&&createPortal(<div id={`${id}-tooltip`} role="tooltip" className="hmc-tooltip" style={{left:hover.left,top:hover.top,transform:hover.above?'translateY(-100%)':undefined}}>
   <strong>{comparisonLabel(hover.point.observation.skill,titles)}</strong><div className="hmc-tooltip-score"><b>{metricValue(hover.point.metric)}</b><span>{metric.label}</span></div>
   <p>Pipeline {hover.point.observation.pipeline??'—'} · Result {hover.point.observation.resultId??'—'}</p>
   <p>{hover.point.observation.model} · Fit {hover.point.observation.replicate} · Seed {hover.point.observation.seed??'—'}</p>
   <small>{hover.point.observation.runTag||'Execution not recorded'}</small>
   <span className="hmc-tooltip-hint">{navigable?'Click or press Enter to view result':'Click or press Enter to inspect evidence'}</span>
  </div>,document.body)}
 </article>;
}
