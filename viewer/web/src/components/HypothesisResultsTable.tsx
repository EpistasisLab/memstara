import { Download, ChevronDown, Table2 } from 'lucide-react';
import { useId, useState } from 'react';
import './hypothesis-results-table.css';
import { evidenceToCsv } from '../lib/evidenceCsv';
import { hypothesisSummaryCsv, hypothesisSummaryRows } from '../lib/hypothesisSummary';

const shown = (value: number | null, digits = 3) => value === null ? '—' : value.toFixed(digits);

export default function HypothesisResultsTable({results, runTag}:{results:readonly unknown[];runTag?:string|null}) {
  const rows = hypothesisSummaryRows(results);
  const [expanded,setExpanded]=useState(false);
  const panelId=useId();
  const [completeBusy,setCompleteBusy]=useState(false),[completeError,setCompleteError]=useState('');
  const save=(content:string,filename:string)=>{
    const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  const download = () => {
    save(hypothesisSummaryCsv(rows),`${runTag||'pipeline-results'}-hypothesis-skill-table.csv`);
  };
  const downloadComplete=async()=>{if(!runTag||completeBusy)return;setCompleteBusy(true);setCompleteError('');try{
    const response=await fetch(`/api/experiments/execution?run_tag=${encodeURIComponent(runTag)}`);const body=await response.json();
    if(!response.ok)throw Error(body.detail||'Complete evidence is unavailable.');save(evidenceToCsv(body),`${runTag}-complete-evidence.csv`);
  }catch(error){setCompleteError(error instanceof Error?error.message:'Complete evidence is unavailable.');}finally{setCompleteBusy(false);}};
  return <section className="hypothesis-comparison" aria-label="Hypothesis skill results table">
    <button type="button" className="hypothesis-comparison-toggle" aria-expanded={expanded} aria-controls={panelId} onClick={()=>setExpanded(value=>!value)}>
      <Table2 size={18} aria-hidden="true"/><span><strong>Compare hypothesis results</strong><small>View the table and download CSV</small></span>
      <span className="hypothesis-comparison-count">{rows.length} rows</span><ChevronDown size={17} aria-hidden="true" style={{transform:expanded?'rotate(180deg)':undefined}}/>
    </button>
    <div id={panelId} hidden={!expanded} className="hypothesis-comparison-body">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-paper-line p-3">
      <div><h3 className="font-semibold">Hypothesis comparison</h3><p className="text-xs text-ink-soft">Each row is one evaluation. Subjects = training + test rows.</p></div>
      <div className="flex flex-wrap gap-2"><button type="button" onClick={download} className="flex items-center gap-2 rounded border border-paper-line px-3 py-2 text-sm font-semibold"><Download size={15}/>Download table CSV</button>{runTag&&<button type="button" disabled={completeBusy} onClick={()=>void downloadComplete()} className="flex items-center gap-2 rounded border border-paper-line px-3 py-2 text-sm font-semibold disabled:opacity-50"><Download size={15}/>{completeBusy?'Preparing complete CSV…':'Download complete evidence CSV'}</button>}</div>
    </header>
    {completeError&&<p role="alert" className="border-b border-paper-line p-3 text-sm text-amber-800">{completeError}</p>}
    {!rows.length && <p className="hypothesis-comparison-empty">No recorded evaluations yet.</p>}
    <div className="hypothesis-comparison-scroll" tabIndex={0} role="region" aria-label="Scrollable hypothesis comparison"><table><thead><tr>{['Hypothesis skill','Pipeline / run','Run / split','Subjects','Seed','Model','AUROC','TN','FP','FN','TP'].map(label=><th key={label}>{label}</th>)}</tr></thead>
      <tbody>{rows.map((row,index)=><tr key={`${row.runTag}:${row.resultId}:${row.evaluationReplicate}:${index}`} className="border-t border-paper-line">
        <td title={row.hypothesisSkill}>{row.hypothesisSkill.replaceAll('-',' ')}</td><td title={row.pipeline}><span className="hypothesis-run-label">{row.pipeline}</span></td>
        <td className="p-2">{row.scheduledReplicate??'—'} / {row.evaluationReplicate}</td><td className="p-2">{row.subjects??'—'}</td>
        <td className="p-2 tabular-nums">{row.seed??'—'}</td><td className="p-2">{row.model||'—'}</td><td className="p-2 tabular-nums">{shown(row.auroc)}</td>
        <td className="p-2 tabular-nums">{row.trueNegative??'—'}</td><td className="p-2 tabular-nums">{row.falsePositive??'—'}</td>
        <td className="p-2 tabular-nums">{row.falseNegative??'—'}</td><td className="p-2 tabular-nums">{row.truePositive??'—'}</td>
      </tr>)}</tbody></table></div>
    <p className="hypothesis-comparison-footnote">Run / split identifies the scheduled replicate and evaluation split. — means not recorded. CSV preserves full identifiers and numerical precision.</p>
    </div>
  </section>;
}
