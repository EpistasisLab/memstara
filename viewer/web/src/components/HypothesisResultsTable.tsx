import { Download, ChevronDown, Table2 } from 'lucide-react';
import { useId, useState, useRef, useEffect } from 'react';
import './hypothesis-results-table.css';
import { hypothesisSummaryRows } from '../lib/hypothesisSummary';
import {prepareLinkedDownload,type ExportKind} from '../lib/linkedDownload';
import HypothesisMetricComparison from './HypothesisMetricComparison';
import type {Observation} from '../lib/confusionMetrics';

const shown = (value: number | null, digits = 3) => value === null ? '—' : value.toFixed(digits);

export default function HypothesisResultsTable({results, runTag, plannedSkills, skillTitles, onOpenResult}:{results:readonly unknown[];runTag?:string|null;plannedSkills?:readonly string[];skillTitles?:Record<string,string>;onOpenResult?:(observation:Observation)=>void}) {
  const rows = hypothesisSummaryRows(results);
  const [expanded,setExpanded]=useState(false);
  const panelId=useId();
  const [exportBusy,setExportBusy]=useState<'table'|'complete'|'zip'|null>(null),[exportError,setExportError]=useState('');
  const [exportNotice,setExportNotice]=useState('');
  const [exportProgress,setExportProgress]=useState('');
  const exportController=useRef<AbortController|null>(null);
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
    try{
      const prepared=await prepareLinkedDownload(tags,kind,{signal:controller.signal,onProgress:message=>{
        if(exportController.current===controller)setExportProgress(message);
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
  return <><section className="hypothesis-comparison" aria-label="Hypothesis skill results table">
    <button type="button" className="hypothesis-comparison-toggle" aria-expanded={expanded} aria-controls={panelId} onClick={()=>setExpanded(value=>!value)}>
      <Table2 size={18} aria-hidden="true"/><span><strong>Compare hypothesis results</strong><small>View the table and download CSV</small></span>
      <span className="hypothesis-comparison-count">{rows.length} rows</span><ChevronDown size={17} aria-hidden="true" style={{transform:expanded?'rotate(180deg)':undefined}}/>
    </button>
    <div id={panelId} hidden={!expanded} className="hypothesis-comparison-body">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-paper-line p-3">
      <div><h3 className="font-semibold">Hypothesis comparison</h3><p className="text-xs text-ink-soft">Each row is one evaluation.</p></div>
      <div className="flex flex-wrap gap-2">{(['table','complete','zip'] as const).map(kind=><button key={kind} type="button" disabled={!!exportBusy||!tags.length} onClick={()=>void download(kind)} className="flex items-center gap-2 rounded border border-paper-line px-3 py-2 text-sm font-semibold disabled:opacity-50"><Download size={15}/>{exportBusy===kind?'Preparing export…':kind==='table'?'Download table CSV':kind==='complete'?'Download complete evidence CSV':'Download linked results ZIP'}</button>)}</div>
    </header>
    {exportBusy&&<div className="hypothesis-export-progress" role="status"><span>{exportProgress}<small>Preparing the file in the background. You can keep using this page.</small></span><button type="button" onClick={()=>exportController.current?.abort()}>Cancel export</button></div>}
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
