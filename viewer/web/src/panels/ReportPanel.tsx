import { lazy, Suspense } from "react";
import { Download, FileText } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Help from "../components/Help";
import ExplanationEvidence from "../components/ExplanationEvidence";
import { useViewer } from "../store/viewer";

const ReportBody = lazy(() => import("../components/ReportBody"));

function recommendationLead(text: string): string | null {
  const section = text.match(/##\s+Executive recommendation\s*([\s\S]*?)(?=\n##\s|$)/i)?.[1] ?? "";
  const first = section.split(/\n\s*\n/).map(s => s.replace(/^[-*]\s+/, "").trim()).find(Boolean);
  return first ? first.replace(/[#*_`]/g, "").trim() : null;
}

/**
 * A reading view for the report agent's final artifact. Results keeps the report beside
 * trial metrics; this view gives the report the whole workspace so a clinician or reviewer
 * can read it without competing with charts and task details.
 */
export default function ReportPanel() {
  const snapshot = useViewer((s) => s.snapshot);
  const report = snapshot?.report;
  const tag = snapshot?.run_tag ?? "run";
  const configuration = snapshot?.run_configuration;
  const lead = report?.text ? recommendationLead(report.text) : null;

  const download = () => {
    if (!report?.text) return;
    const url = URL.createObjectURL(new Blob([report.text], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${tag}_report.md`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  if (!snapshot) return <EmptyState what="the final report" />;

  return (
    <div data-testid="report-page" className="flex h-full min-h-0 flex-col bg-white">
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-paper-line px-5 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-ink-soft">
            <FileText className="h-4 w-4" />
            <span className="text-[10px] font-bold uppercase tracking-[.16em]">Report agent output</span>
            <Help topic="report" />
          </div>
          <h2 className="mt-1 truncate font-mono text-sm font-bold text-ink" title={tag}>{tag}</h2>
          <p className="mt-1 text-xs text-ink-faint">
            {report?.status === "completed" ? "Completed final report" : `Report status: ${report?.status ?? "unavailable"}`}
            {snapshot.pipeline?.status ? ` · Pipeline ${snapshot.pipeline.status}` : ""}
          </p>
        </div>
        <button type="button" onClick={download} disabled={!report?.text}
          className="flex shrink-0 items-center gap-1.5 rounded-md border border-paper-line px-2.5 py-1.5 text-xs font-bold text-ink-soft hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40">
          <Download className="h-3.5 w-3.5" /> Download Markdown
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-5 py-5">
          <div className="mb-5 grid gap-2 rounded-lg border border-paper-line bg-paper-panel p-3 text-xs sm:grid-cols-4">
            <div><span className="block text-[10px] uppercase tracking-wider text-ink-faint">Status</span><strong>{report?.status ?? "unavailable"}</strong></div>
            <div><span className="block text-[10px] uppercase tracking-wider text-ink-faint">Target</span><strong className="font-mono">{configuration?.y_column ?? "—"}</strong></div>
            <div><span className="block text-[10px] uppercase tracking-wider text-ink-faint">Hypotheses</span><strong>{configuration?.hypotheses ?? "—"}</strong></div>
            <div><span className="block text-[10px] uppercase tracking-wider text-ink-faint">Trials</span><strong>{configuration?.trials ?? "—"}</strong></div>
          </div>

          <section className="mb-5 rounded-xl border border-[#b8d4c0] bg-[#f3f8f4] p-4" aria-label="Recommendation summary">
            <div className="text-[10px] font-bold uppercase tracking-[.16em] text-[#477258]">Research recommendation</div>
            <p className="mt-1 text-sm font-medium leading-relaxed text-ink">
              {lead ?? "The report agent will identify and rank the most promising hypotheses here after a completed report is available."}
            </p>
            <p className="mt-2 text-[11px] text-ink-faint">Rankings weigh evidence, predictive support, reproducibility, actionability, novelty, and uncertainty together.</p>
          </section>

          {report?.error && <p role="status" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{report.error}</p>}
          {snapshot.results.filter(result => result.evaluation?.explanation?.review_status).map(result =>
            <details key={result.result_id} className="mb-3 rounded-lg border border-paper-line p-3">
              <summary className="cursor-pointer text-sm font-bold">Trial {result.trial} · Measured explanation · reviewer original required</summary>
              <ExplanationEvidence result={result} />
            </details>)}
          {report?.text ? (
            <Suspense fallback={<p className="text-sm text-ink-soft">Loading report…</p>}>
              <div data-report-content><ReportBody text={report.text} /></div>
            </Suspense>
          ) : (
            <div className="rounded-lg border border-dashed border-paper-line p-8 text-center text-sm text-ink-soft">
              No completed report is available for this run.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
