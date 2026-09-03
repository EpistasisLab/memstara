import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Compass } from "lucide-react";
import Panel from "../components/Panel";
import { cn } from "../lib/cn";
import { STAGE_ICON } from "../lib/icons";
import { STAGE_COLOR } from "../lib/stage";
import { useBoard, useResults, useViewer } from "../store/viewer";
import type { Result, StageId, Task } from "../types";

/**
 * The run's shape, as a tree you can move around in.
 *
 * Every other panel is a flat list of one kind of thing — tasks, tool calls, agents, rows
 * of an access map. None of them shows how the run is *built*: that a run holds trials,
 * that a trial holds one task per stage, and that a finished task has a result hanging off
 * it. Finding the three rows belonging to trial 2 currently means reading the board table
 * and doing the grouping in your head.
 *
 * So this panel is not a seventh way to list tasks. It is the run's structure, and its job
 * is to be clicked: a task row selects that task, which is what `Task life` already draws.
 *
 *     Run   2026-09-02T140628_board_2trials          24 tasks · 18 done
 *       ▾ Trial 1                                            6 · 4 done
 *           ▥  data        alcohol-related thrombocytopenia    done   AUC 0.712
 *           ▤  ml          alcohol-related thrombocytopenia    ready
 *       ▸ Trial 2
 *
 * **The grouping is the board's own, not one invented here.** `trial` and `task_type` are
 * columns on the task (`viewer/api/queries.py`, `Task` in `types.ts`), so a trial with a
 * missing stage shows a gap rather than a placeholder. A gap is information — it means the
 * lap that would have created that row has not run.
 *
 * The result under a task is matched by `task_id`. A result whose task row has since been
 * cleaned up carries `task_id: null` (`types.ts:122-125`) and simply does not appear here;
 * it is still in `ResultsPanel`, which is always on screen. This panel does not pretend to
 * be the whole record of the run.
 */

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
          selected ? "bg-ink text-white" : "hover:bg-paper",
        )}
      >
        <Icon
          className="mt-0.5 h-3.5 w-3.5 shrink-0"
          style={{ color: selected ? "#fff" : STAGE_COLOR[stage] }}
          strokeWidth={2.2}
        />

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5">
            <span className="font-bold">{task.task_type}</span>
            <span
              className={cn(
                "truncate font-mono text-[10px]",
                selected ? "text-white/60" : "text-ink-faint",
              )}
            >
              #{task.task_id}
            </span>
            {/* A real retry, not the normal hand-off between stages — the API separates
                the two for us (`viewer/api/scene.py:106-118`). */}
            {task.retried > 0 && (
              <span
                className={cn(
                  "shrink-0 rounded px-1 text-[10px] font-bold",
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
  const board = useBoard();
  const results = useResults();
  const runTag = useViewer((s) => s.snapshot?.run_tag ?? null);
  const runs = useViewer((s) => s.snapshot?.runs ?? null);
  const selectedTask = useViewer((s) => s.selectedTask);
  const selectTask = useViewer((s) => s.selectTask);

  /** Which trials are folded away. Empty means everything is open, which is the right
   *  default for a run of two or three trials — folding is for the long ones. */
  const [folded, setFolded] = useState<ReadonlySet<number>>(new Set());

  const tasks = board?.tasks ?? [];

  /** Grouped once per snapshot rather than per render: the board can carry a few hundred
   *  rows and this runs every two seconds behind the poll. */
  const trials = useMemo(() => {
    const byTrial = new Map<number, Task[]>();
    for (const task of tasks) {
      const list = byTrial.get(task.trial);
      if (list) list.push(task);
      else byTrial.set(task.trial, [task]);
    }

    return [...byTrial.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([trial, rows]) => ({
        trial,
        rows: [...rows].sort(
          (a, b) =>
            TYPE_ORDER.indexOf(a.task_type) - TYPE_ORDER.indexOf(b.task_type) ||
            a.task_id - b.task_id,
        ),
        done: rows.filter((t) => t.status === "done").length,
      }));
  }, [tasks]);

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
      count={tasks.length || undefined}
      status={summary ? <span>{summary.done} done</span> : undefined}
      bodyClassName="p-0"
    >
      {!board ? (
        <div className="p-6 text-xs text-ink-faint">Loading the run…</div>
      ) : tasks.length === 0 ? (
        <div className="p-6 text-xs text-ink-faint">
          <p className="font-bold text-ink">This run has no board rows yet.</p>
          <p className="mt-1 leading-snug">
            The curator proposes questions first; rows appear once the hypothesis stage pins
            the first instruction to the board.
          </p>
        </div>
      ) : (
        <div className="px-2 py-2">
          <div className="truncate px-2 pb-2 font-mono text-[11px] text-ink-faint" title={runTag ?? ""}>
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
                  <span className="truncate">Trial {trial}</span>
                  <span className="ml-auto shrink-0 font-mono text-[10px] font-normal text-ink-faint">
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
