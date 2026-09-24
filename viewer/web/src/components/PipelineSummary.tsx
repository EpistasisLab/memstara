import { useBoard, useViewer } from "../store/viewer";

export default function PipelineSummary() {
  const tasks = useBoard()?.tasks ?? [];
  const preview = useViewer(state => state.newRunMode);
  const report = useViewer(state => state.snapshot?.report?.status);
  const counts = [
    { label: "Complete", count: tasks.filter(t => t.status === "done").length, color: "#2f6b47" },
    { label: "Running", count: tasks.filter(t => t.status === "in_progress").length, color: "#2a5f8f" },
    { label: "Queued", count: tasks.filter(t => t.status === "ready").length, color: "#8a5f12" },
    { label: "Failed", count: tasks.filter(t => t.status === "failed").length, color: "#8f2f4f" },
  ];
  return <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-paper-line bg-white px-4 py-2.5 text-xs">
    <span className="font-bold text-ink">{preview ? "Plan your analysis" : "Analysis progress"}</span>
    {preview ? <span className="text-ink-soft">Configure skills on each agent · No analysis started</span> : <>
      {counts.map(item => <span key={item.label} className="flex items-center gap-1.5" style={{ color: item.color }}>
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} /><strong>{item.count}</strong>{item.label}
      </span>)}
      <span className="ml-auto text-ink-faint">Report: {report ?? "not available"}</span>
    </>}
  </div>;
}
