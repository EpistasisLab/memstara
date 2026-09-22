import { useLoopLabel } from '../lib/useLoopLabel';
import { motion, AnimatePresence } from "framer-motion";
import { RotateCcw, AlertCircle } from "lucide-react";
import EmptyState from "../components/EmptyState";
import { useBoard, useViewer } from "../store/viewer";
import { STAGE_COLOR } from "../lib/stage";
import type { Task } from "../types";

/** The board as three lanes. Cards animate between lanes as a run proceeds. */

const LANES: { key: Task["status"]; label: string }[] = [
  { key: "ready", label: "Waiting" },
  { key: "in_progress", label: "In progress" },
  { key: "done", label: "Done" },
];

const NEXT_STAGE = { hypothesis: "Hypothesis", data: "Data", ml: "Train", interpret: "Interpret" } as const;
const STAGE_OF = { data: "data", ml: "ml", interpret: "interpreter", hypothesis: "hypothesis" } as const;

function Card({ task }: { task: Task }) {
  const labelLoop = useLoopLabel();
  const select = useViewer((s) => s.selectTask);
  const color = STAGE_COLOR[STAGE_OF[task.task_type] as keyof typeof STAGE_COLOR];

  return (
    <motion.button
      layout
      layoutId={`task-${task.task_id}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ type: "spring", stiffness: 260, damping: 26 }}
      onClick={() => select(task.task_id)}
      className="w-full rounded-lg border border-paper-line bg-white p-3 text-left shadow-sm
                 transition hover:border-ink-faint hover:shadow-md"
    >
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
          <span className="font-mono text-sm font-bold">#{task.task_id}</span>
        </span>
        <span className="text-xs text-ink-faint">{labelLoop(task)}</span>
      </div>

      <div className="mt-1 flex items-center gap-2 text-xs text-ink-soft">
        <span>Next: {NEXT_STAGE[task.task_type]}</span>
        {task.y_column && (
          <span className="font-mono text-[12px] text-ink-faint">→ {task.y_column}</span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {task.columns.slice(0, 4).map((c) => (
          <span key={c} className="rounded bg-paper px-1.5 py-0.5 font-mono text-[12px] text-ink-soft">{c}</span>
        ))}
        {task.columns.length > 4 && (
          <span className="self-center text-[12px] text-ink-faint">+{task.columns.length - 4}</span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px]">
        {task.auc !== null && <span className="font-bold">AUC {task.auc.toFixed(4)}</span>}
        <span className="text-ink-faint">claimed {task.attempts}×</span>
        {/* attempts counts claims, so only extra claims are called a retry. */}
        {task.retried > 0 && (
          <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 font-bold text-amber-800">
            <RotateCcw className="h-3 w-3" /> retried {task.retried}
          </span>
        )}
        {task.columns_missing.length > 0 && (
          <span className="inline-flex items-center gap-1 rounded bg-red-100 px-1.5 py-0.5 font-bold text-red-700">
            <AlertCircle className="h-3 w-3" /> {task.columns_missing.length} missing
          </span>
        )}
      </div>
    </motion.button>
  );
}

export default function BoardTab() {
  const board = useBoard();
  if (!board) return <EmptyState what="the board" />;

  return (
    <div className="grid grid-cols-3 gap-4 p-6">
      {LANES.map((lane) => {
        const tasks = board.tasks.filter((t) => t.status === lane.key);
        return (
          <section key={lane.key}>
            <h2 className="mb-3 flex items-baseline gap-2 text-sm font-bold">
              {lane.label}
              <span className="rounded-full bg-paper px-2 py-0.5 text-xs text-ink-soft">{tasks.length}</span>
            </h2>
            <div className="min-h-24 space-y-2 rounded-lg bg-paper/50 p-2">
              <AnimatePresence mode="popLayout">
                {tasks.map((t) => <Card key={t.task_id} task={t} />)}
              </AnimatePresence>
              {tasks.length === 0 && (
                <p className="py-6 text-center text-xs text-ink-faint">Empty</p>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
