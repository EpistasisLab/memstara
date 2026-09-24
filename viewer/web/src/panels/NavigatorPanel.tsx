import { useLoopLabel } from '../lib/useLoopLabel';
import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Compass } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Panel from "../components/Panel";
import { cn } from "../lib/cn";
import { STAGE_ICON } from "../lib/icons";
import { STAGE_COLOR } from "../lib/stage";
import { useBoard, useResults, useViewer } from "../store/viewer";
import type { Result, StageId, Task } from "../types";



/** The board's four task types, in the order a lap works through them, mapped onto the
 *  stage vocabulary the rest of the screen uses. `interpret` -> `interpreter` is the same
 *  aliasing `lib/agentlog.ts:workerStage` does for the console's worker names, and the same
 *  table `tabs/BoardTab.tsx:16` already carries. */
const STAGE_OF: Record<Task["task_type"], StageId> = {
  hypothesis: "hypothesis",
  data: "data",
  ml: "ml",
  interpret: "interpreter",
};

const TYPE_ORDER: Task["task_type"][] = ["hypothesis", "data", "ml", "interpret"];

/** Status is drawn as a word, never as colour alone — the same rule the chain cards follow.
 *  `ready` is deliberately the quietest: a queued row is the ordinary state of a board and
 *  should not compete with the one row that failed. */
const STATUS_CLASS: Record<Task["status"], string> = {
  done: "text-emerald-700",
  in_progress: "font-bold text-sky-700",
  ready: "text-ink-faint",
  failed: "font-bold text-red-700",
};

function TaskRow({
  task,
  result,
  selected,
  onSelect,
}: {
  task: Task;
  result: Result | undefined;
  selected: boolean;
  onSelect: () => void;
}) {
  const stage = STAGE_OF[task.task_type];
  const Icon = STAGE_ICON[stage];

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected ? "true" : undefined}
        className={cn(
          "flex w-full items-start gap-2 rounded-md py-1 pl-6 pr-2 text-left text-xs transition",
          selected ? "bg-accent text-accent-contrast" : "hover:bg-paper",
        )}
      >
        <Icon
          className="mt-0.5 h-3.5 w-3.5 shrink-0"
          style={{ color: selected ? "rgb(var(--accent-contrast))" : STAGE_COLOR[stage] }}
          strokeWidth={2.2}
        />

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5">
            <span className="font-bold">{task.task_type}</span>
            <span
              className={cn(
                "truncate font-mono text-[12px]",
                selected ? "text-white/60" : "text-ink-faint",
              )}
            >
              #{task.task_id}
            </span>
            {/* A real retry, not the normal hand-off between stages — the API separates
                the two for us (`viewer/api/scene.py:146-158`). */}
            {task.retried > 0 && (
              <span
                className={cn(
                  "shrink-0 rounded px-1 text-[12px] font-bold",
                  selected ? "bg-white/20" : "bg-amber-100 text-amber-800",
                )}
                title={`${task.attempts} claims, ${task.retried} beyond the stages it passed`}
              >
                ↻{task.retried}
              </span>
            )}
          </span>

          {task.perspective && (
            <span
              className={cn("block truncate", selected ? "text-white/70" : "text-ink-soft")}
              title={task.perspective}
            >
              {task.perspective}
            </span>
          )}

          <span className="flex items-baseline gap-2">
            <span className={cn(selected ? "text-white/70" : STATUS_CLASS[task.status])}>
              {task.status}
            </span>
            {/* The result is shown here rather than only in the results table because this
                is where somebody asks "did that one work". */}
            {result?.auc != null && (
              <span
                className={cn(
                  "font-mono tabular-nums",
                  selected ? "text-white" : "font-bold text-ink",
                )}
              >
                AUC {result.auc.toFixed(3)}
              </span>
            )}
          </span>
        </span>
      </button>
    </li>
  );
}

export default function NavigatorPanel() {
  const labelLoop = useLoopLabel();
  const board = useBoard();
  const results = useResults();
  const runTag = useViewer((s) => s.snapshot?.run_tag ?? null);
  const runs = useViewer((s) => s.snapshot?.runs ?? null);
  const selectedTask = useViewer((s) => s.selectedTask);
  const selectTask = useViewer((s) => s.selectTask);

  /** Which trials are folded away. Empty means everything is open, which is the right
   *  default for a run of two or three trials — folding is for the long ones. */
  const [folded, setFolded] = useState<ReadonlySet<string>>(new Set());

  const tasks = board?.tasks ?? [];

  /** Grouped once per snapshot rather than per render: the board can carry a few hundred
   *  rows and this runs every two seconds behind the poll. */
  const trials = useMemo(() => {
    const byTrial = new Map<string, Task[]>();
    for (const task of [...tasks].sort((a,b) => a.trial-b.trial)) {
      const label = labelLoop(task);
      const key = label === 'Loop —' ? `Loop unknown · analysis ID ${task.trial}` : label;
      const list = byTrial.get(key);
      if (list) list.push(task);
      else byTrial.set(key, [task]);
    }

    return [...byTrial.entries()]
      .map(([trial, rows]) => ({
        trial,
        rows: [...rows].sort(
          (a, b) =>
            TYPE_ORDER.indexOf(a.task_type) - TYPE_ORDER.indexOf(b.task_type) ||
            a.task_id - b.task_id,
        ),
        done: rows.filter((t) => t.status === "done").length,
      }));
  }, [tasks, labelLoop]);

  const resultOf = useMemo(() => {
    const map = new Map<number, Result>();
    for (const r of results ?? []) if (r.task_id !== null) map.set(r.task_id, r);
    return map;
  }, [results]);

  const summary = runs?.find((r) => r.run_tag === runTag);

  return (
    <Panel
      icon={Compass}
      title="Navigator"

      status={summary ? <span>{summary.done} done</span> : undefined}
      bodyClassName="p-0"
    >
      <p className="px-3 py-2 text-xs text-ink-soft">Question text is an agent proposal; progress and status come from execution records.</p>
      {!board ? (
        <EmptyState what="the run" className="p-6 text-xs" />
      ) : tasks.length === 0 ? (
        <div className="p-6 text-xs text-ink-faint">
          <p className="font-bold text-ink">This run has no board rows yet.</p>
          <p className="mt-1 leading-snug">
            Questions are proposed first, and rows appear only once the first instruction is
            pinned to the board. Both steps belong to the character drawn as
            &ldquo;Hypothesis&rdquo;, so an empty list here usually means it is still on the
            first of the two, not that nothing is happening.
          </p>
        </div>
      ) : (
        <div className="px-2 py-2">
          <div className="truncate px-2 pb-2 font-mono text-[12px] text-ink-faint" title={runTag ?? ""}>
            {runTag}
          </div>

          {trials.map(({ trial, rows, done }) => {
            const open = !folded.has(trial);
            return (
              <section key={trial}>
                <button
                  type="button"
                  onClick={() =>
                    setFolded((prev) => {
                      const next = new Set(prev);
                      if (!next.delete(trial)) next.add(trial);
                      return next;
                    })
                  }
                  aria-expanded={open}
                  className="flex w-full items-center gap-1 rounded-md px-1 py-1 text-left
                             text-xs font-bold hover:bg-paper"
                >
                  {open ? (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                  )}
                  <span className="truncate">{trial}</span>
                  <span className="ml-auto shrink-0 font-mono text-[12px] font-normal text-ink-faint">
                    {done}/{rows.length}
                  </span>
                </button>

                {open && (
                  <ul className="mb-1 space-y-0.5">
                    {rows.map((task) => (
                      <TaskRow
                        key={task.task_id}
                        task={task}
                        result={resultOf.get(task.task_id)}
                        selected={selectedTask === task.task_id}
                        onSelect={() => selectTask(task.task_id)}
                      />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
