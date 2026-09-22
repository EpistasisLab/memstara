import Help from "../components/Help";
import ContentOrigin from "../components/ContentOrigin";
import { transparentReportMarkdown } from "../lib/reportTransparency";
import { useLoopLabel } from '../lib/useLoopLabel';
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BookOpen, Download, Search, Stethoscope, Microscope, ClipboardCheck, ChevronDown } from "lucide-react";
import { usePipelines } from "../store/pipelines";
import { pipelineLabel } from "../lib/pipelineLabel";
import { useLiveOutputs } from "../store/liveOutputs";
import { useViewer } from "../store/viewer";
import ScientificProvenance from "../components/ScientificProvenance";
import ExplanationEvidence from "../components/ExplanationEvidence";
import type { Result } from "../types";

import "./clinician.css";

const ReportBody = lazy(() => import("../components/ReportBody"));
const section = "rounded-2xl border border-paper-line bg-white p-5 sm:p-6";

function Evidence({ result }: { result: Result }) {
  const labelLoop = useLoopLabel();
  const importance = Object.entries(result.importance ?? {}).filter(([, value]) => Number.isFinite(value))
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 8);
  const maximum = Math.max(...importance.map(([, value]) => Math.abs(value)), .000001);
  return <article className="clinical-reading-card" aria-label="Selected hypothesis evidence">
    <div className="clinical-reading-heading"><span className="clinical-eyebrow">The research finding</span><ContentOrigin kind="proposal" compact/></div>
    <h2>{result.hypothesis || result.perspective || "Hypothesis text not recorded"}</h2>
    <p className="clinical-context">{labelLoop(result)} · Outcome studied: <strong>{result.y_column || 'Not recorded'}</strong></p>
    <section className="clinical-meaning">
      <div className="clinical-section-title"><Stethoscope size={21}/><h3>What could this mean?</h3></div>
      <p className="clinical-caption">AI-written interpretation of this analysis. It needs review by the research team.</p>
      {result.interpretation ? <Suspense fallback={<p>Loading interpretation…</p>}><ReportBody origin="llm" text={result.interpretation} /></Suspense>
        : <p className="clinical-empty">An interpretation has not arrived yet. We will show it here when it is recorded.</p>}
    </section>
    <section className="clinical-next-step">
      <div className="clinical-section-title"><ClipboardCheck size={21}/><h3>What should I do with this?</h3></div>
      <p>Use this finding to guide a discussion with your research team. It does not yet establish a cause, a treatment recommendation, or a clinical cutoff.</p>
      <ol><li>Check whether the study population and measurements match your research question.</li><li>Review missing information and alternative explanations.</li><li>Agree on independent validation before considering a change in care.</li></ol>
      {!!result.columns_missing?.length && <p className="clinical-warning">Some requested measurements were unavailable: {result.columns_missing.join(', ')}.</p>}
      {result.evaluation?.data_quality?.warnings?.map((warning, i) => <p className="clinical-warning" key={i}>{warning}</p>)}
    </section>
    <details className="clinical-disclosure">
      <summary><Microscope size={20}/><span><strong>Explore the supporting evidence</strong><small>Measurements used, model performance and checks</small></span><ChevronDown size={18}/></summary>
      <div className="clinical-disclosure-body">
        <h3>Which measurements were studied?</h3>
        <p className="clinical-caption">These are the recorded dataset column names. Their exact clinical definitions should be confirmed with the study team.</p>
        <div className="clinical-feature-list">{result.columns_used?.length ? result.columns_used.map(feature => <span key={feature}>{feature}</span>) : <p>No measurements were recorded.</p>}</div>
        <div className="clinical-measurement"><div><span>Ability to distinguish outcomes</span><strong>{result.auc == null ? "Not recorded" : result.auc.toFixed(3)} <small>AUC</small></strong></div><p>AUC measures how well the model ranks people with and without the studied outcome. 0.5 represents chance-level ranking; 1.0 is perfect ranking. It is not the percentage of correct predictions or proof of clinical benefit.</p></div>
        {importance.length > 0 && <section className="clinical-contributions"><h3>What influenced the model?</h3><p className="clinical-caption">The eight largest recorded contributions, at most. A larger bar is not evidence of a larger biological or causal effect. {result.evaluation?.explanation?.method === "holdout_permutation_auc" ? "Values show the change in held-out AUC when a measurement is shuffled. A negative value means shuffling improved the measured score." : "Values use the fitted model’s recorded importance measure."}</p>
          {importance.map(([feature, value]) => <div key={feature} className="clinical-contribution"><div><span>{feature}</span><strong>{value.toPrecision(3)}</strong></div><div className="clinical-bar"><span style={{width:`${Math.abs(value) / maximum * 100}%`,background:value < 0 ? 'var(--clinical-negative)' : 'var(--clinical-accent)'}} /></div></div>)}
        </section>}
        <ExplanationEvidence result={result} />
      </div>
    </details>
    <details className="clinical-disclosure">
      <summary><BookOpen size={20}/><span><strong>Sources and analysis details</strong><small>Where this finding came from and how it was tested</small></span><ChevronDown size={18}/></summary>
      <div className="clinical-disclosure-body"><ScientificProvenance result={result}/>
        <dl className="clinical-source-grid"><div><dt>Outcome studied</dt><dd>{result.y_column || 'Not recorded'}</dd></div><div><dt>Model</dt><dd>{result.model || 'Not recorded'}</dd></div><div><dt>Random seed</dt><dd>{result.evaluation?.seed ?? 'Not recorded'}</dd></div><div><dt>Data held back for testing</dt><dd>{result.evaluation?.test_size == null ? 'Not recorded' : `${(result.evaluation.test_size * 100).toFixed(0)}%`}</dd></div></dl>
        <p>Knowledge reference IDs: {result.okf_concept_ids?.join(', ') || 'Not recorded'}</p>
        <details className="mt-4"><summary>Technical evaluation plan</summary><pre className="mt-2 overflow-auto rounded-lg bg-paper p-3 text-xs">{JSON.stringify(result.evaluation?.evaluation?.plan ?? {}, null, 2)}</pre></details>
      </div>
    </details>
  </article>;

}

export default function ClinicianPanel() {
  const labelLoop = useLoopLabel();
  const { snapshot, knownRuns, runTag, setRunTag } = useViewer();
  const live=useLiveOutputs();
  const pipelines=usePipelines(s=>s.items);
  const [mode,setMode]=useState<'live'|'archive'>('live');
  const [query,setQuery]=useState('');
  const [selected,setSelected]=useState<number|null>(null);
  const [seenResult,setSeenResult]=useState<number|null>(null);
  const newestResult=live.results.reduce((latest,result)=>Math.max(latest,result.result_id),0);
  useEffect(()=>{if(seenResult===null&&newestResult)setSeenResult(newestResult);},[newestResult,seenResult]);
  const hasNewFindings=seenResult!==null&&newestResult>seenResult;
  const results=mode==='live'?live.results:snapshot?.results??[];
  const matches=useMemo(()=>results.filter(r=>`${r.hypothesis} ${r.perspective} ${r.columns_used?.join(' ')} ${r.pipeline_name||''}`.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>mode==='live'?b.result_id-a.result_id:a.trial-b.trial),[results,query,mode]);
  // Pin the first finding after load. New arrivals must not replace the item being read.
  useEffect(()=>{if(selected===null&&matches.length)setSelected(matches[0].result_id);},[matches,selected]);
  const active=results.find(r=>r.result_id===selected);
  const activeRun=mode==='live'?(active?.run_tag||Object.keys(live.reports).at(-1)):runTag;
  const report=mode==='live'?(activeRun?live.reports[activeRun]:null):snapshot?.report;
  const analysesPerLoop = activeRun === snapshot?.run_tag ? snapshot?.run_configuration?.trials : undefined;
  const recommendation=report?.text?.match(/^##\s+Executive recommendation\s*\n([\s\S]*?)(?=^##\s|$(?![\s\S]))/im)?.[1]?.trim();
  const runs=snapshot?.runs??knownRuns;
  const download=()=>{
    if(!report?.text)return;
    const url=URL.createObjectURL(new Blob([transparentReportMarkdown(report.text, analysesPerLoop)],{type:'text/markdown;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`${activeRun||'analysis'}_report.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  const switchMode=(next:'live'|'archive')=>{setMode(next);setSelected(null);setQuery('');};
  const showNewFindings=()=>{setMode('live');setQuery('');setSelected(newestResult);setSeenResult(newestResult);};
  return <main className="clinical-view h-full overflow-auto bg-paper text-ink" data-testid="clinician-view">
    <div className="mx-auto max-w-[1440px] space-y-5 px-5 py-6 sm:px-8">
      <section className="clinical-hero clinical-hero-simple"><div><p className="clinical-eyebrow">Memstara · Clinical insights</p><h1 className="mt-2 font-semibold">What is your research finding?</h1><p className="mt-3 text-ink-soft">Choose a finding to understand its meaning and what to check next.</p></div></section>
      <details className="clinical-history clinical-disclosure">
        <summary><BookOpen size={18}/><span><strong>Past analyses</strong></span><ChevronDown size={18}/></summary>
        <div className="clinical-disclosure-body"><p className="clinical-caption">Review results from one saved execution. Otherwise, this page shows the latest findings across your pipelines.</p>
          <label className="block text-sm">Choose an analysis<select aria-label="Clinical analysis" className="mt-2 block w-full rounded-lg border border-paper-line bg-white p-3 text-sm" value={mode==='archive' ? runTag??'' : ''} onChange={e=>{if(e.target.value){switchMode('archive');setRunTag(e.target.value);}else switchMode('live');}}><option value="">Latest findings across pipelines</option>{runs.map(run=><option key={run.run_tag} value={run.run_tag}>{run.first_seen?new Date(run.first_seen).toLocaleString():run.run_tag} · {run.run_tag}</option>)}</select></label>
        </div>
      </details>
      {mode==='archive'&&<div className="clinical-update"><span>Viewing a saved analysis</span><Help topic="Return to latest findings" description="Show the latest findings across your pipelines again. Your saved analysis stays available under Past analyses."><button onClick={()=>switchMode('live')}>Return to latest findings</button></Help></div>}
      {mode==='live'&&hasNewFindings&&<div className="clinical-update" role="status"><span>New findings are available.</span><button onClick={showNewFindings}>View new findings<ArrowUpRight size={16}/></button></div>}
      {(mode==='live'?live.error:snapshot?.stale)&&<p role="status" className="clinical-warning">Updates are temporarily unavailable. You can keep reading the last available findings.</p>}
      <div className="clinical-findings-layout"><aside className={`${section} min-w-0`}><h2 className="text-lg font-semibold">Explore findings</h2><p className="clinical-caption">{mode==='live'?'Newest first':'From your selected analysis'}</p><label className="my-4 flex items-center gap-2 rounded-lg border border-paper-line px-3"><Search size={16}/><input aria-label="Search clinical findings" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search findings or measurements" className="min-w-0 flex-1 bg-transparent py-2.5 text-sm outline-none"/></label><div className="max-h-[720px] space-y-2 overflow-auto">{matches.map(result=><button data-help="Inspect this finding" data-help-description="Select this hypothesis to read its model evidence, interpretation, limitations and linked report. The selection stays pinned while new findings arrive." key={result.result_id} aria-pressed={active?.result_id===result.result_id} onClick={()=>{setSelected(result.result_id);}} className={`w-full rounded-xl border p-3 text-left transition ${active?.result_id===result.result_id?'border-[#71ae9e] bg-stage-hypothesis/5':'border-paper-line hover:bg-paper'}`}><span className="flex justify-between gap-2 text-xs text-ink-faint">{pipelineLabel(result,pipelines)} · {labelLoop(result)}<ArrowUpRight size={14}/></span><span className="mt-2 line-clamp-4 text-sm font-medium leading-relaxed">{result.hypothesis||result.perspective||'Untitled finding'}</span><span className="mt-2 block text-xs text-ink-soft">{result.interpretation?'Interpretation available':'Awaiting interpretation'}</span></button>)}{!matches.length&&<p className="py-5 text-sm text-ink-soft">{query?'No matching findings.':'As analyses produce findings, they will appear here automatically.'}</p>}</div></aside>
      {active?<div className="min-w-0"><p className="mb-3 text-xs text-ink-faint">Reading: {pipelineLabel(active,pipelines)} · {labelLoop(active)}</p><Evidence key={active.result_id} result={active}/></div>:<section className={`${section} py-16 text-center`}><BookOpen className="mx-auto mb-4 text-ink-faint"/><h2 className="font-semibold">The next finding will appear here.</h2><p className="mt-3 text-sm text-ink-soft">Questions and hypotheses may already be in progress. Clinical evidence appears when the pipeline records analysis results.</p></section>}</div>
      <details className="clinical-disclosure" aria-label="Research report"><summary><BookOpen size={20}/><span><strong>Read the research report</strong><small>Summary, full report and download</small></span><ChevronDown size={18}/></summary><div className="clinical-disclosure-body"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-wider text-stage-hypothesis">The bigger picture</p><h2 className="mt-1 text-lg font-semibold">Research team briefing</h2></div><button onClick={download} disabled={!report?.text} className="flex items-center gap-2 rounded-lg border border-paper-line px-3 py-2 text-xs disabled:opacity-40"><Download size={14}/>Download report (.md)</button></div><p className="mt-2 break-words text-xs text-ink-faint">{activeRun||'No linked report yet'} · {report?.status||'Awaiting report'}</p>{recommendation?<Suspense fallback={<p>Loading recommendation…</p>}><ReportBody report analysesPerLoop={analysesPerLoop} text={recommendation}/></Suspense>:<p className="mt-3 text-sm text-ink-soft">{report?.text?'Read the original report below; no separate executive recommendation was recorded.':'The run report will appear here when it is recorded.'}</p>}{report?.error&&<p className="mt-2 text-sm">{report.error}</p>}{report?.text&&<details className="mt-4 border-t border-paper-line pt-3"><summary className="cursor-pointer text-sm font-semibold">Read the complete report</summary><Suspense fallback={<p>Loading report…</p>}><ReportBody report analysesPerLoop={analysesPerLoop} text={report.text}/></Suspense></details>}</div></details>
      <footer className="pb-5 text-xs text-ink-faint">Research findings for review with your study team. Not a treatment recommendation.</footer>
    </div>
  </main>;
}
