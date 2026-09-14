import { lazy, Suspense, useState } from "react";
import { Download, FileText } from "lucide-react";
import { useViewer } from "../store/viewer";

const ReportBody = lazy(() => import("./ReportBody"));

export default function FinalReport() {
  const report = useViewer(s => s.snapshot?.report);
  const tag = useViewer(s => s.snapshot?.run_tag ?? "run");
  const [expanded, setExpanded] = useState(false);
  if (!report) return null;
  const download = () => {
    if (!report.text) return;
    const url = URL.createObjectURL(new Blob([report.text], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${tag}_report.md`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section data-testid="final-report" className="m-4 rounded-xl border border-paper-line bg-white">
    <div className="flex items-center gap-2 p-3">
      <FileText size={16} className="text-ink-soft" />
      <button className="flex-1 text-left text-sm font-bold" aria-expanded={expanded}
        onClick={() => setExpanded(v => !v)}>Final report <span className="ml-2 text-xs font-normal text-ink-soft">{report.status}</span></button>
      {report.text && <button aria-label="Download final report" onClick={download} className="rounded p-1.5 hover:bg-paper"><Download size={15} /></button>}
    </div>
    <p className="px-3 pb-2 text-[12px] text-ink-faint">{tag}</p>
    {report.error && <p role="status" className="px-3 pb-3 text-sm text-amber-800">{report.error}</p>}
    {expanded && <div className="border-t border-paper-line p-4">
      {report.text ? <Suspense fallback={<p>Loading report…</p>}><div data-final-report-content><ReportBody text={report.text} /></div></Suspense>
        : <p className="text-sm text-ink-soft">No completed report is available for this run.</p>}
    </div>}
  </section>;
}
