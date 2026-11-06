import { Download, ChevronDown, Table2 } from 'lucide-react';
import { useId, useState, useRef, useEffect } from 'react';
import './hypothesis-results-table.css';
import { hypothesisSummaryRows } from '../lib/hypothesisSummary';
import {prepareLinkedDownload,type ExportKind,type ExportProgress} from '../lib/linkedDownload';
import HypothesisMetricComparison from './HypothesisMetricComparison';
import type {Observation} from '../lib/confusionMetrics';

const shown = (value: number | null, digits = 3) => value === null ? '—' : value.toFixed(digits);
const sizeLabel=(bytes:number)=>bytes<1024?`${bytes} B`:bytes<1048576?`${(bytes/1024).toFixed(1)} KiB`:`${(bytes/1048576).toFixed(1)} MiB`;
const exportDescriptions:Record<ExportKind,string>={
  table:'Summary CSV with one row per evaluation: hypothesis skill, execution and result IDs, seed, model parameters, performance metrics, confusion matrix, hypothesis, and linked Interpretation/Explanation output IDs. Includes continued executions. Best for comparing performance.',
  complete:'Detailed CSV of registered execution settings, prompts, agent records, results, costs, and artifact metadata. Nested data is stored as JSON inside cells. Includes continued executions and may be very large. Best for auditing recorded evidence.',
  zip:'ZIP containing the results table CSV, results JSON, complete evidence CSV and JSON, original Interpretation and Explanation text in separate JSON files, a link manifest, and a README. Output IDs connect each result to its agent outputs. Includes continued executions. Best for analyzing results alongside agent explanations.',
};

export default function HypothesisResultsTable({results, runTag, plannedSkills, skillTitles, onOpenResult}:{results:readonly unknown[];runTag?:string|null;plannedSkills?:readonly string[];skillTitles?:Record<string,string>;onOpenResult?:(observation:Observation)=>void}) {
  const rows = hypothesisSummaryRows(results);
  const [expanded,setExpanded]=useState(false);
  const panelId=useId();
  const [exportBusy,setExportBusy]=useState<'table'|'complete'|'zip'|null>(null),[exportError,setExportError]=useState('');
  const [exportNotice,setExportNotice]=useState('');
  const [exportProgress,setExportProgress]=useState('');
  const [exportTransfer,setExportTransfer]=useState<ExportProgress>({phase:'preparing'});
  const [exportElapsed,setExportElapsed]=useState(0);
  const exportController=useRef<AbortController|null>(null);
  useEffect(()=>{
    if(!exportBusy)return;
    const start=performance.now();
    const timer=setInterval(()=>setExportElapsed(Math.floor((performance.now()-start)/1000)),1000);
    return ()=>clearInterval(timer);
  },[exportBusy]);
  useEffect(()=>()=>{const controller=exportController.current;exportController.current=null;controller?.abort();},[]);
  const tags=runTag?[runTag]:[...new Set(rows.map(row=>row.runTag).filter(Boolean))];
  const save=(blob:Blob,filename:string)=>{
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
  };
  const download=async(kind:ExportKind)=>{
    if(exportController.current||!tags.length)return;
    const controller=new AbortController();exportController.current=controller;
    setExportBusy(kind);setExportError('');setExportNotice('');setExportProgress('Starting export…');
    setExportElapsed(0);setExportTransfer({phase:'preparing'});
    try{
      const prepared=await prepareLinkedDownload(tags,kind,{signal:controller.signal,onProgress:(message,progress)=>{
        if(exportController.current===controller){setExportProgress(message);setExportTransfer(progress??{phase:'preparing'});}
      }});
      if(controller.signal.aborted||exportController.current!==controller)return;
      const prefix=runTag||'pipeline-results';
      if(kind==='zip')save(prepared.blob,`${prefix}-linked-results.zip`);
      else save(prepared.blob,
        `${prefix}-${kind==='table'?'hypothesis-skill-table':'complete-evidence'}.csv`);
      setExportNotice(`${prepared.results} saved results from ${prepared.executions} execution(s) exported.`+
        (prepared.warnings?` ${prepared.warnings} evidence warning(s); see the linked ZIP manifest.`:''));
    }catch(error){
      if(exportController.current===controller){
        if(controller.signal.aborted)setExportNotice('Export cancelled. Saved results are unchanged.');
        else setExportError(error instanceof Error?error.message:'Linked evidence is unavailable.');
      }
    }finally{
      if(exportController.current===controller){exportController.current=null;setExportBusy(null);setExportProgress('');}
    }
  };
  const transferPercent=exportTransfer.phase==='downloading'&&exportTransfer.totalBytes!==undefined?
    Math.min(100,Math.floor((exportTransfer.receivedBytes??0)/exportTransfer.totalBytes*100)):undefined;
  const preparationPercent=exportTransfer.phase==='preparing'&&exportTransfer.totalUnits!==undefined?
    Math.floor((exportTransfer.completedUnits??0)/exportTransfer.totalUnits*100):undefined;
  const preparationLabel=preparationPercent===undefined?'Waiting for server progress.':
    `Current stage: ${exportTransfer.completedUnits} / ${exportTransfer.totalUnits} · ${preparationPercent}% (not overall completion)`;
  const transferLabel=exportTransfer.phase==='downloading'?
    `${sizeLabel(exportTransfer.receivedBytes??0)}${exportTransfer.totalBytes!==undefined?` / ${sizeLabel(exportTransfer.totalBytes)}`:' received — total size unavailable'}${transferPercent!==undefined?` · ${transferPercent}%`:''}`:null;
  return <><section className="hypothesis-comparison" aria-label="Hypothesis skill results table">
    <button type="button" className="hypothesis-comparison-toggle" aria-expanded={expanded} aria-controls={panelId} onClick={()=>setExpanded(value=>!value)}>
      <Table2 size={18} aria-hidden="true"/><span><strong>Compare hypothesis results</strong><small>View the table and download CSV</small></span>
      <span className="hypothesis-comparison-count">{rows.length} rows</span><ChevronDown size={17} aria-hidden="true" style={{transform:expanded?'rotate(180deg)':undefined}}/>
    </button>
    <div id={panelId} hidden={!expanded} className="hypothesis-comparison-body">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-paper-line p-3">
      <div><h3 className="font-semibold">Hypothesis comparison</h3><p className="text-xs text-ink-soft">Each row is one evaluation.</p></div>
      <div className="flex flex-wrap gap-2">{(['table','complete','zip'] as const).map(kind=><button key={kind} type="button" title={exportDescriptions[kind]} aria-description={exportDescriptions[kind]} disabled={!!exportBusy||!tags.length} onClick={()=>void download(kind)} className="flex items-center gap-2 rounded border border-paper-line px-3 py-2 text-sm font-semibold disabled:opacity-50"><Download size={15}/>{exportBusy===kind?(exportTransfer.phase==='downloading'?'Downloading…':exportTransfer.phase==='verifying'?'Checking file…':'Preparing export…'):kind==='table'?'Download table CSV':kind==='complete'?'Download complete evidence CSV':'Download linked results ZIP'}</button>)}</div>
    </header>
    {exportBusy&&<div className="hypothesis-export-progress">
      <div className="hypothesis-export-meter">
        <strong role="status">{exportProgress}</strong>
        <div className="hypothesis-export-details"><span>{transferLabel??(exportTransfer.phase==='preparing'?preparationLabel:'File received; checking before saving.')}</span><span>Elapsed {Math.floor(exportElapsed/60)}:{String(exportElapsed%60).padStart(2,'0')}</span></div>
        <progress max={100} value={transferPercent??preparationPercent} aria-label={exportTransfer.phase==='downloading'?'Export download progress':exportTransfer.phase==='verifying'?'Export file verification':'Export preparation progress'} aria-valuetext={transferLabel??preparationLabel}/>
        <small>{exportTransfer.phase==='preparing'?'The server is collecting saved evidence and preparing the file. Large exports can take a few minutes. ':'Downloading and checking the prepared file. '}You can keep using this page.</small>
        {exportElapsed>=60&&exportTransfer.phase==='preparing'&&<small>Waiting for the prepared file. Updates above show the latest information received from the server.</small>}
      </div><button type="button" onClick={()=>exportController.current?.abort()}>Cancel export</button>
    </div>}
    {exportError&&<p role="alert" className="border-b border-paper-line p-3 text-sm text-amber-800">{exportError}</p>}
    {exportNotice&&<p role="status" className="border-b border-paper-line p-3 text-xs">{exportNotice}</p>}
    {!rows.length && <p className="hypothesis-comparison-empty">No recorded evaluations yet.</p>}
    <div className="hypothesis-comparison-scroll" tabIndex={0} role="region" aria-label="Scrollable hypothesis comparison"><table><thead><tr>{['Hypothesis skill','Pipeline / run','Seed','Model','AUROC','TN','FP','FN','TP'].map(label=><th key={label} scope="col" className={label==='Model'?'hypothesis-model':undefined}>{label}</th>)}</tr></thead>
      <tbody>{rows.map((row,index)=><tr key={`${row.runTag}:${row.resultId}:${row.evaluationReplicate}:${index}`} className="border-t border-paper-line">
        <td title={row.hypothesisSkill}>{row.hypothesisSkill.replaceAll('-',' ')}</td><td title={row.pipeline}><span className="hypothesis-run-label">{row.pipeline}</span></td>
        <td className="p-2 tabular-nums">{row.seed??'—'}</td><td className="hypothesis-model">{row.model||'—'}</td><td className="hypothesis-auroc tabular-nums">{shown(row.auroc)}</td>
        <td className="p-2 tabular-nums">{row.trueNegative??'—'}</td><td className="p-2 tabular-nums">{row.falsePositive??'—'}</td>
        <td className="p-2 tabular-nums">{row.falseNegative??'—'}</td><td className="p-2 tabular-nums">{row.truePositive??'—'}</td>
      </tr>)}</tbody></table></div>
    <p className="hypothesis-comparison-footnote">— means not recorded. CSV preserves full identifiers and numerical precision. Result rows link to Interpretation and Explanation by output ID arrays. Download the linked ZIP for original agent text in separate JSON files, including continued executions.</p>
    </div>
  </section><HypothesisMetricComparison results={results} runTag={runTag} plannedSkills={plannedSkills} skillTitles={skillTitles} onOpenResult={onOpenResult}/></>;
}
