import { useBoard, useViewer } from "../store/viewer";
import { useRunForm } from "../lib/useRunForm";

const stages = ["hypothesis", "data", "ml", "interpret"] as const;
const labels = ["Hypothesis", "Data", "ML", "Interpretation"];

/** Task identity follows a hypothesis through handoffs; timing comes from the board. */
export default function PathProgress() {
  const tasks = useBoard()?.tasks ?? [];
  const select = useViewer(s => s.selectTask);
  const report = useViewer(s => s.snapshot?.report);
  const form = useRunForm();
  if (!tasks.length) return null;
  return <section aria-label="Hypothesis progress" className="max-h-40 shrink-0 overflow-auto border-t border-paper-line bg-paper-panel px-3 py-2">
    <div className="mb-2 flex justify-between text-[12px] text-ink-faint">
      <strong>Hypothesis progress</strong><span>Shared report: {report?.status ?? "waiting for analyses"}</span>
    </div>
    {tasks.map(task => {
      const at = stages.indexOf(task.task_type);
      return <button key={task.task_id} onClick={() => select(task.task_id)}
        className="mb-1 flex w-full items-center gap-2 rounded px-1 py-1 text-left text-[12px] hover:bg-paper"
        title={task.error || task.hypothesis || task.perspective}>
        <span className="w-40 shrink-0 truncate">Wave {Math.floor(task.trial / Math.max(1, form.trials)) + 1} · Trial {task.trial} · {task.hypothesis || task.perspective}</span>
        <span className="flex flex-wrap gap-1">{stages.map((stage, index) => {
          const state = index < at || task.status === "done" ? "done" : index === at ? task.status : "waiting";
          const tone = state === "done" ? "bg-emerald-50 text-emerald-800" : state === "in_progress" ? "bg-sky-50 text-sky-800" : state === "failed" ? "bg-red-50 text-red-800" : "bg-paper text-ink-faint";
          return <span key={stage} className={`rounded px-1.5 py-0.5 ${tone}`}>{labels[index]}: {state === "in_progress" ? "running" : state}</span>;
        })}</span>
      </button>;
    })}
    <p className="mt-1 text-[12px] text-ink-faint">Each trial advances independently. One interpreter handles each hypothesis; the report combines completed analyses.</p>
  </section>;
}
