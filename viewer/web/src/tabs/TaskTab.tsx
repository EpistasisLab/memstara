import ContentOrigin from "../components/ContentOrigin";
import { useLoopLabel } from '../lib/useLoopLabel';
import { lazy, Suspense } from "react";
const ReportBody = lazy(() => import("../components/ReportBody"));
import { agentDisplayName } from "../lib/telemetry";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, Hand, Inbox, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { useViewer } from "../store/viewer";
import { STAGE_COLOR } from "../lib/stage";
import type { StageId, Task } from "../types";

/**
 * One task's life, and which agent run handled each stage.
 *
 * The board carries no run ids. The trail is rebuilt on the server from the board
 * windows — create_task / claim_task / submit_result each carry the task id in their
 * payload — so this is the only place the two databases are stitched together.
 */

interface Trail {
  agent: string;
  agent_label: string;
  tool: string;
  run_id: string;
  at: string;
}

const TOOL_LABEL: Record<string, string> = {
  create_task: "put it on the board",
  claim_task: "picked it up",
  submit_result: "wrote it up and passed it on",
};

const TOOL_ICON = { create_task: Inbox, claim_task: Hand, submit_result: Send } as const;

export default function TaskTab({ taskId: scopedTaskId }: { taskId?: number | null } = {}) {
  const labelLoop = useLoopLabel();
  const selectedTask = useViewer((s) => s.selectedTask);
  const taskId = scopedTaskId === undefined ? selectedTask : scopedTaskId;
  const [data, setData] = useState<{ task: Task; trail: Trail[] } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    setUpdatedAt(null);
    if (taskId === null) return;
    let active = true;
    let next: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    const poll = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 7000);
      try {
        const response = await fetch(`/api/task/${taskId}`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        const value = await response.json();
        if (active) { setData(value); setError(null); setUpdatedAt(Date.now()); }
      } catch (e) {
        if (active) setError(e instanceof Error && e.name === 'AbortError'
          ? 'The request timed out. Retrying automatically.' : 'Task details are temporarily unavailable. Retrying automatically.');
      } finally {
        clearTimeout(timeout);
        if (active) next = setTimeout(poll, 3000);
      }
    };
    void poll();
    return () => { active = false; clearTimeout(next); controller?.abort(); };
  }, [taskId, refresh]);

  if (taskId === null)
    return <div className="p-8 text-ink-faint">Select a task above, or choose a task in the Board view.</div>;
  if (error && !data) return <div role="alert" className="p-8 text-ink-soft">{error} <button className="underline" onClick={() => setRefresh(r => r + 1)}>Retry now</button></div>;
  if (!data) return <div className="p-8 text-ink-faint">Loading…</div>;

  const { task, trail } = data;
  const importance = Object.entries(task.importance).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 p-4">
      <div className="xl:col-span-2 text-sm text-ink-soft">{error ? <span role="alert">{error} Showing the last available task details.</span> : <>Updates every 3 seconds · Last updated {updatedAt ? new Date(updatedAt).toLocaleTimeString() : "—"} (local time)</>}</div>
      <section>
        <h2 className="text-sm font-bold">Task #{task.task_id} — {labelLoop(task)}</h2>
        <p className="mt-1 text-xs text-ink-soft">{task.perspective}</p>
        <ContentOrigin kind="proposal"/><p className="mt-3 text-sm">{task.hypothesis}</p>

        <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-ink-faint">Status</dt><dd>{task.status} · {task.task_type}</dd>
          <dt className="text-ink-faint">AUC</dt><dd className="font-bold">{task.auc?.toFixed(4) ?? "—"}</dd>
          <dt className="text-ink-faint">Times claimed</dt>
          <dd>{task.attempts}{task.retried > 0 && <span className="ml-2 text-amber-700">retried {task.retried}×</span>}</dd>
          <dt className="text-ink-faint">Missing columns</dt>
          <dd>{task.columns_missing.length === 0 ? "None" : task.columns_missing.join(" | ")}</dd>
        </dl>

        {importance.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-1 text-sm font-bold">Importance</h3>
            <p className="mb-2 text-xs text-ink-faint">
              Importance describes the fitted model, not causation. Negative permutation importance means shuffling improved the score; a negative SHAP value indicates direction. Interpret values using the recorded method.
            </p>
            <ResponsiveContainer width="100%" height={Math.max(140, importance.length * 26)}>
              <BarChart data={importance.map(([col, v]) => ({ col, v }))} layout="vertical"
                        margin={{ left: 12, right: 24 }}>
                <XAxis type="number" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="col" width={96} tick={{ fontSize: 12 }}
                       axisLine={false} tickLine={false} />
                <Tooltip formatter={(v) => [Number(v).toFixed(5), "importance"]} />
                <Bar dataKey="v" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                  {importance.map(([col, v]) => (
                    <Cell key={col} fill={v < 0 ? "#c0392b" : "#2a5f8f"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-bold">Task handoffs</h2>
        <ol className="mt-3 space-y-3">
          {trail.map((t, i) => {
            const Icon = TOOL_ICON[t.tool as keyof typeof TOOL_ICON] ?? ArrowRight;
            const color = STAGE_COLOR[t.agent as StageId] ?? "#8a8880";
            return (
              <li key={`${t.run_id}-${t.tool}-${i}`} className="flex gap-3">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                      style={{ backgroundColor: color + "1a", color }}>
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <div>
                  <div className="text-sm font-bold">
                    {agentDisplayName(t.agent_label)}
                    <span className="ml-2 font-normal text-ink-soft">{TOOL_LABEL[t.tool] ?? t.tool}</span>
                  </div>
                  <div className="font-mono text-[12px] text-ink-faint">
                    {t.at ? new Date(t.at).toLocaleTimeString() : "—"} local · run {t.run_id.slice(0, 8)}
                  </div>
                </div>
              </li>
            );
          })}
          {trail.length === 0 && (
            <li className="text-sm text-ink-faint">
              core holds no record of anyone touching this task (core DB down, or an older run).
            </li>
          )}
        </ol>

        {task.interpretation && (
          <div className="mt-6">
            <h3 className="text-sm font-bold">Interpretation</h3>
            <Suspense fallback={<p>Loading formatted explanation…</p>}><ReportBody origin="llm" text={task.interpretation} /></Suspense>
          </div>
        )}
      </section>
    </div>
  );
}
