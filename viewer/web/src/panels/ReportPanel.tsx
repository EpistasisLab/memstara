import { lazy, Suspense, useState } from 'react';
import { Download } from 'lucide-react';
import { displayText } from '../lib/displayText';
import { findingHeading, firstFinding } from '../lib/findingHeading';
import { useViewer } from '../store/viewer';
import { usePipelines } from '../store/pipelines';
import { useExecutionContext } from '../components/ExecutionContext';
import ExpertExplanationEvidence from '../components/ExpertExplanationEvidence';
import ScientificProvenance from '../components/ScientificProvenance';
import ExplanationEvidence from '../components/ExplanationEvidence';
import { useLoopLabel } from '../lib/useLoopLabel';
import LoopUsage from '../components/LoopUsage';
import { useTelemetryTotals } from '../components/TelemetryTotals';

const ReportBody = lazy(() => import('../components/ReportBody'));

/** The saved Explanation output for one execution, with no synthesized recommendation. */
export default function ReportPanel() {
  const snapshot = useViewer(s => s.snapshot);
  const error = useViewer(s => s.error);
  const requested = useViewer(s => s.runTag);
  const items = usePipelines(s => s.items);
  const selected = usePipelines(s => s.selected);
  const context = useExecutionContext();
  const labelLoop = useLoopLabel();
  const tag = snapshot?.run_tag;
  const report = snapshot?.report;
  const [outputKey, setOutputKey] = useState('');
  const outputs = report?.explanation_outputs ?? [];
  const output = outputs.find(o => `${tag}:${o.loop}:${o.result_id}` === outputKey) ?? outputs[0];
  const usage = useTelemetryTotals();
  const execution = usage.data?.executions.find(e => e.run_tag === tag);
  const heading = tag ? findingHeading(firstFinding(
    (snapshot?.results ?? []).map(r => ({...r, run_tag: tag})), tag)?.hypothesis) : '';
  const loading = !!requested && requested !== tag;
  const download = () => {
    if (!output?.text || !tag || loading) return;
    const url = URL.createObjectURL(new Blob([
      output.text,
    ], {type: 'text/markdown;charset=utf-8'}));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${tag}_loop-${output.loop}${output.result_id == null ? "" : `_result-${output.result_id}`}_conclusions.md`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div data-testid="report-page" className="report-reading-pane h-full min-h-0 min-w-0 overflow-auto" tabIndex={0} aria-label="Conclusions contents">
    <div className="conclusions-reader">
      <header className="conclusions-toolbar">
        <label className="analysis-select-label">Experiment
          <select aria-label="Pipeline conclusions" value={selected ?? ''} onChange={e => usePipelines.getState().select(e.target.value)}>
            <option value="" disabled>{tag ? context.name : 'Choose a pipeline'}</option>
            {items.map(p => <option key={p.id} value={p.id}>Experiment {p.number} · {p.name}{p.latest ? '' : ' · not started'}</option>)}
          </select>
        </label>
        {outputs.length > 0 && <label className="analysis-select-label">Explanation
          <select aria-label="Saved Explanation" value={`${tag}:${output.loop}:${output.result_id}`} onChange={e => setOutputKey(e.target.value)}>
            {outputs.map(o => <option key={`${o.loop}:${o.result_id}`} value={`${tag}:${o.loop}:${o.result_id}`}>{labelLoop({...o,iteration:o.loop,run_tag:tag})}{o.result_id == null ? '' : ` · Result ${o.result_id}`} · {o.status}</option>)}
          </select>
        </label>}
        <button type="button" onClick={download} disabled={!output?.text || loading} className="conclusions-download">
          <Download size={16} aria-hidden="true"/>Download Markdown
        </button>
      </header>
      {loading && <p role="status" className="my-4 text-sm text-ink-soft">Loading the selected execution…</p>}
      {(error || snapshot?.stale) && <p role="status" className="my-4 text-sm text-ink-soft">Updates are unavailable. Showing the last saved records for {context.name}.</p>}
      {!loading && <>
        <header className="conclusions-heading">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Explanation agent output</p>
          <h2 className="mt-2 break-words text-xl font-semibold leading-snug">{heading || (tag ? context.name : 'No conclusions yet')}</h2>
          {heading && <p className="mt-1 text-xs text-ink-faint">Heading from the first saved AI hypothesis · {context.name}</p>}
          {tag && <p className="mt-2 text-sm text-ink-soft">{report?.status === 'completed' ? 'Completed report' : `Report status: ${report?.status ?? 'not recorded'}`} · {context.startedLabel}</p>}
        </header>
        {report?.error && <p role="status" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{displayText(report.error)}</p>}
        {output?.text ? <Suspense fallback={<p>Loading report…</p>}>
          <div data-report-content><ReportBody verbatim text={output.text}/></div>
        </Suspense> : <p className="py-8 text-sm text-ink-soft">{tag ? 'No Explanation output has been saved for this execution yet.' : 'Choose a pipeline with saved output to read its conclusions.'}</p>}
        {tag && <details className="analysis-technical-details mt-6">
          <summary>Report records and supporting evidence</summary>
          <div className="mt-4 space-y-4 text-sm">
            <p>Execution: <code className="break-all">{tag}</code></p>
            <p>Target: {snapshot?.run_configuration?.y_column ?? 'Not recorded'}</p>
            <LoopUsage execution={execution} updatedAt={usage.data?.updated_at} error={usage.error}/>
            <ExpertExplanationEvidence evidence={report?.specialist_explanation}/>
            {snapshot?.results.map(result => <details key={result.result_id}>
              <summary>{labelLoop(result)} · Supporting evidence</summary>
              <ScientificProvenance result={result}/>
              <ExplanationEvidence result={result}/>
            </details>)}
          </div>
        </details>}
      </>}
    </div>
  </div>;
}
