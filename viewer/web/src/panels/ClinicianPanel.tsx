import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowUpRight, BookOpen, Download, Search, Stethoscope } from "lucide-react";
import { useViewer } from "../store/viewer";
import ExplanationEvidence from "../components/ExplanationEvidence";
import type { Result } from "../types";

const ReportBody = lazy(() => import("../components/ReportBody"));
const section = "rounded-2xl border border-paper-line bg-white p-5 sm:p-6";

function Evidence({ result }: { result: Result }) {
  const importance = Object.entries(result.importance ?? {}).filter(([, value]) => Number.isFinite(value))
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 8);
  const maximum = Math.max(...importance.map(([, value]) => Math.abs(value)), .000001);
  return <article className={`${section} min-w-0`} aria-label="Selected hypothesis evidence">
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
      <span>Hypothesis · Trial {result.trial}</span><span>AI-generated interpretation · research evidence</span>
    </div>
    <h2 className="mt-3 text-xl font-semibold leading-snug text-ink">{result.hypothesis || result.perspective || "Hypothesis text not recorded"}</h2>
    <div className="mt-5 rounded-xl bg-[#f3f8f4] p-4">
      <h3 className="text-sm font-bold text-[#2f6b47]">What this may mean</h3>
      {result.interpretation ? <Suspense fallback={<p>Loading interpretation…</p>}><ReportBody text={result.interpretation} /></Suspense>
        : <p className="mt-2 text-sm text-ink-soft">A clinical interpretation has not been recorded. Review the measured evidence before drawing conclusions.</p>}
    </div>
    <div className="my-5 grid gap-3 sm:grid-cols-3">
      <div className="rounded-xl border border-paper-line p-3"><p className="text-xs text-ink-soft">Discrimination · AUC</p><p className="mt-1 text-2xl font-semibold">{result.auc == null ? "Not available" : result.auc.toFixed(3)}</p><p className="mt-1 text-xs text-ink-faint">Ranks outcomes; not accuracy or clinical benefit.</p></div>
      <div className="rounded-xl border border-paper-line p-3"><p className="text-xs text-ink-soft">Features evaluated</p><p className="mt-1 text-2xl font-semibold">{result.columns_used?.length ?? 0}</p><p className="mt-1 text-xs text-ink-faint">Selected from the supplied dataset.</p></div>
      <div className="rounded-xl border border-paper-line p-3"><p className="text-xs text-ink-soft">Knowledge references</p><p className="mt-1 text-2xl font-semibold">{result.okf_concept_ids?.length ?? 0}</p><p className="mt-1 text-xs text-ink-faint">Recorded sources, not a quality score.</p></div>
    </div>
    <h3 className="text-sm font-bold">What informed the prediction</h3>
    <div className="my-3 flex flex-wrap gap-2">{result.columns_used?.map(feature => <span key={feature} className="max-w-full break-words rounded-lg bg-paper px-2 py-1 text-xs">{feature}</span>)}</div>
    {importance.length > 0 && <details className="my-4 rounded-xl border border-paper-line p-3">
      <summary className="cursor-pointer text-sm font-medium">Feature contributions</summary>
      <p className="my-2 text-xs text-ink-faint">{result.evaluation?.explanation?.method === "holdout_permutation_auc" ? "Change in held-out AUC under feature permutation. Negative values mean permutation improved the measured score." : `Recorded importance from ${result.model || "the fitted model"}; importance is not a causal effect.`} Bar lengths show absolute magnitude.</p>
      {importance.map(([feature, value]) => <div key={feature} className="mt-3"><div className="flex justify-between gap-3 text-xs"><span className="break-words">{feature}</span><span>{value.toPrecision(3)}</span></div><div className="mt-1 h-1.5 rounded-full bg-paper"><div className="h-full rounded-full" style={{width:`${Math.abs(value) / maximum * 100}%`,background:value < 0 ? '#8f2f4f' : '#2f6b47'}} /></div></div>)}
    </details>}
    <ExplanationEvidence result={result} />
    <section className="mt-5 rounded-xl border border-[#e5dcc5] bg-[#fcfaf4] p-4" aria-label="Evidence limitations">
      <h3 className="text-sm font-bold">Before applying this finding</h3>
      <p className="mt-2 text-sm leading-relaxed">These are exploratory associations. This view does not establish causality, a validated treatment threshold or readiness for a clinical intervention.</p>
      {result.columns_missing?.length > 0 && <p className="mt-2 text-sm">Requested features not available: {result.columns_missing.join(', ')}.</p>}
      {result.evaluation?.data_quality?.warnings?.map((warning, i) => <p key={i} className="mt-2 text-sm">{warning}</p>)}
      <p className="mt-2 text-sm">Next review: confirm the population, feature definitions and timing; assess independent validation and clinical relevance with the study team.</p>
    </section>
    <details className="mt-4 text-sm"><summary className="cursor-pointer font-medium">Sources and reproducibility</summary>
      <p className="mt-2">Target: {result.y_column || 'Not recorded'} · Model: {result.model || 'Not recorded'}</p>
      <p className="mt-2">Seed: {result.evaluation?.seed ?? 'Not recorded'} · Hold-out fraction: {result.evaluation?.test_size ?? 'Not recorded'}</p>
      <p className="mt-2 break-words">Knowledge reference IDs: {result.okf_concept_ids?.join(', ') || 'Not recorded'}</p>
      <pre className="mt-2 overflow-auto rounded-lg bg-paper p-3 text-xs">{JSON.stringify(result.evaluation?.evaluation?.plan ?? {}, null, 2)}</pre>
    </details>
  </article>;
}

export default function ClinicianPanel() {
  const { snapshot, knownRuns, runTag, newRunMode, loading, error, setRunTag, setView } = useViewer();
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => { setQuery(''); setSelected(null); }, [runTag]);
  const results = snapshot?.results ?? [];
  const matches = useMemo(() => results.filter(result => `${result.hypothesis} ${result.perspective} ${result.columns_used?.join(' ')}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => a.trial - b.trial), [results, query]);
  const active = matches.find(result => result.result_id === selected) ?? matches[0];
  const report = snapshot?.report;
  const recommendation = report?.text?.match(/^##\s+Executive recommendation\s*\n([\s\S]*?)(?=^##\s|$(?![\s\S]))/im)?.[1]?.trim();
  const runs = snapshot?.runs ?? knownRuns;
  const pendingreviewer = results.some(result => result.evaluation?.explanation?.review_status) || snapshot?.run_configuration?.books.interpreter?.includes('interpreter_review_pending');
  const download = () => {
    if (!report?.text) return;
    const url = URL.createObjectURL(new Blob([report.text], {type:'text/markdown;charset=utf-8'}));
    const anchor=document.createElement('a'); anchor.href=url; anchor.download=`${runTag}_report.md`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  return <main className="h-full overflow-auto bg-paper text-ink" data-testid="clinician-view">
    <header className="sticky top-0 z-20 border-b border-paper-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-8">
        <div className="flex items-center gap-3"><span className="rounded-xl bg-[#edf4ee] p-2 text-[#2f6b47]"><Stethoscope size={23} /></span><div><p className="text-lg font-semibold">Memstara <span className="font-normal text-ink-soft">Clinical insights</span></p><p className="text-xs text-ink-faint">Hypothesis review workspace</p></div></div>
        <button className="flex items-center gap-2 rounded-lg border border-paper-line px-3 py-2 text-sm hover:bg-paper" onClick={() => setView('chain')}><ArrowLeft size={15} />Research workspace</button>
      </div>
    </header>
    <div className="mx-auto max-w-[1440px] space-y-5 px-5 py-6 sm:px-8">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-xs font-bold uppercase tracking-widest text-[#2f6b47]">Review the evidence</p><h1 className="mt-2 text-2xl font-semibold sm:text-3xl">Which hypotheses deserve closer attention?</h1><p className="mt-2 max-w-2xl text-sm text-ink-soft">Understand the finding, examine its support, and identify what still needs validation.</p></div>
        <label className="block max-w-full text-xs font-medium">Analysis<select aria-label="Clinical analysis" className="mt-1 block w-80 max-w-full rounded-lg border border-paper-line bg-white p-2.5 text-sm" value={runTag ?? ''} onChange={event => setRunTag(event.target.value || null)}><option value="">Choose a saved analysis</option>{runTag && !runs.some(run => run.run_tag === runTag) && <option value={runTag}>{runTag} · Loading details…</option>}{runs.map(run => <option key={run.run_tag} value={run.run_tag}>{run.first_seen ? new Date(run.first_seen).toLocaleString() : run.run_tag} · {run.question || run.run_tag} · {run.status || `${run.done} completed`}</option>)}</select></label>
      </section>
      {(error || snapshot?.stale) && <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm">Updates interrupted. Any results below are the last available results, not a newly completed analysis.</p>}
      {newRunMode || !snapshot ? <section className={`${section} py-14 text-center`}><BookOpen className="mx-auto mb-3 text-ink-faint" /><h2 className="font-semibold">{loading && !newRunMode ? 'Loading analysis…' : 'Choose an analysis to review'}</h2><p className="mt-2 text-sm text-ink-soft">Completed findings and their evidence will appear here. Use the research workspace to configure or start an analysis.</p></section> : <>
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-soft"><span>Outcome: <strong>{snapshot.run_configuration?.y_column || results[0]?.y_column || 'Not recorded'}</strong></span><span>{results.length} recorded findings</span><span>Analysis: {snapshot.pipeline?.status ?? 'Status not recorded'}</span><span>Updated: {new Date(snapshot.generated_at).toLocaleString()}</span></div>
        {pendingreviewer && <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">reviewer original required: the explainability specification is provisional and must be replaced with reviewer’s original material.</p>}
        <section className={`${section} border-l-4 border-l-[#2f6b47]`} aria-label="Report recommendation">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-wider text-[#2f6b47]">From the report</p><h2 className="mt-1 text-lg font-semibold">Research recommendation</h2></div><button onClick={download} disabled={!report?.text} className="flex items-center gap-2 rounded-lg border border-paper-line px-3 py-2 text-xs disabled:opacity-40"><Download size={14} />Download report (.md)</button></div>
          {recommendation ? <Suspense fallback={<p>Loading recommendation…</p>}><ReportBody text={recommendation} /></Suspense> : <p className="mt-3 text-sm text-ink-soft">{report?.text ? 'A separate executive recommendation was not recorded. Open the full report for the original assessment.' : 'No report recommendation is available yet. Available findings can still be reviewed below.'}</p>}
          <p className="mt-3 text-xs text-ink-faint">AI-generated research recommendation. Findings below are in trial order, not ranked by AUC.</p>
          {report?.error && <p className="mt-2 text-sm text-amber-800">{report.error}</p>}
          {report?.text && <details className="mt-3 border-t border-paper-line pt-3"><summary className="cursor-pointer text-sm font-semibold">Read the complete report</summary><Suspense fallback={<p>Loading report…</p>}><ReportBody text={report.text} /></Suspense></details>}
        </section>
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(260px,340px)_minmax(0,1fr)]">
          <aside className={`${section} min-w-0`}><h2 className="text-lg font-semibold">Explore hypotheses</h2><label className="my-4 flex items-center gap-2 rounded-lg border border-paper-line px-3"><Search size={16} className="text-ink-faint" /><input aria-label="Search clinical findings" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search a finding or feature" className="min-w-0 flex-1 bg-transparent py-2.5 text-sm outline-none focus:ring-1 focus:ring-[#2f6b47]" /></label>
            <div className="space-y-2">{matches.map(result => <button key={result.result_id} aria-pressed={active?.result_id === result.result_id} onClick={() => setSelected(result.result_id)} className={`w-full rounded-xl border p-3 text-left transition ${active?.result_id === result.result_id ? 'border-[#2f6b47] bg-[#f3f8f4]' : 'border-paper-line hover:bg-paper'}`}><span className="flex justify-between text-xs text-ink-faint">Trial {result.trial}<ArrowUpRight size={14} /></span><span className="mt-2 line-clamp-4 text-sm font-medium leading-relaxed">{result.hypothesis || result.perspective || 'Untitled finding'}</span><span className="mt-2 block text-xs text-ink-soft">{result.auc == null ? 'Performance not recorded' : `AUC ${result.auc.toFixed(3)}`} · {result.columns_used?.length ?? 0} features</span></button>)}{!matches.length && <p className="py-5 text-sm text-ink-soft">{query ? 'No findings match your search.' : 'No completed findings are available for this analysis yet.'}</p>}</div>
          </aside>
          {active ? <Evidence result={active} /> : <section className={`${section} text-sm text-ink-soft`}>Select an available hypothesis to inspect its interpretation and measured evidence.</section>}
        </div>
      </>}
      <footer className="pb-5 text-xs text-ink-faint">Research decision support · No patient-specific treatment recommendation is made by this view.</footer>
    </div>
  </main>;
}
