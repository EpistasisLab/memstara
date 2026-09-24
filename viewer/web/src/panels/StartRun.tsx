import { pipelineLoopLabel } from "../lib/pipelineProgress";
import { usePipelines } from "../store/pipelines";
import ControlAgentSettings from "../components/ControlAgentSettings";
import KnowledgeSelect from "../components/KnowledgeSelect";
import Help from "../components/Help";
import { Play, Square } from "lucide-react";
import { useEffect } from "react";
import { useControl, type RunRequest } from "../store/control";
import { POLL_MS, useViewer } from "../store/viewer";
import { useRunForm } from "../lib/useRunForm";

/** Knowledge selection, shared agent settings, and exploration controls. */
function Text_({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-[12px] font-bold uppercase tracking-wider text-ink-faint">{label} <Help topic={label} /></span>
      <input
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-paper-line bg-white px-2 py-1
                   font-mono text-xs focus:border-ink focus:outline-none"
      />
    </label>
  );
}

export default function StartRun() {
  const up = useControl((s) => s.up);
  const running = useControl((s) => s.running);
  const busy = useControl((s) => s.busy);
  const error = useControl((s) => s.error);
  const pipeline = usePipelines(s => s.items.find(p => p.id === s.selected));
  const workspaceBusy = usePipelines(s => s.busy);
  const stopRun = () => pipeline ? usePipelines.getState().stop(pipeline.id) : useControl.getState().stopRun();
  const snapshot = useViewer(s => s.snapshot);
  const skills = useControl(s => s.skills);
  const currentSnapshot = running && snapshot?.run_tag === running.run_tag ? snapshot : null;
  const completed = currentSnapshot ? new Set(currentSnapshot.results.map(r => r.trial)).size : null;
  const form = useRunForm();
  const setForm = useControl((s) => s.setForm);
  const set = <K extends keyof RunRequest>(k: K, v: RunRequest[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  // Its own poll, on the same cadence and with the same courtesy to a hidden tab as the
  // viewer's. Not folded into that one: it is a different service, and a request to it
  // failing must not make the viewer look broken.
  useEffect(() => {
    const tick = () => {
      if (!document.hidden) void useControl.getState().poll();
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  if (!pipeline) return <div className="space-y-3 text-sm text-ink-soft">
    <p>Add or select a pipeline in Floor Plan to configure its agents.</p>
    <button className="rounded-lg border border-paper-line px-3 py-2 font-bold text-ink" onClick={()=>useViewer.getState().setView("scene")}>Open Floor Plan</button>
  </div>;

  if (up === false) {
    return (
      <div className="text-[12px] text-ink-faint">
        <span className="font-bold uppercase tracking-wider">Hypothesis exploration</span>
        <p className="mt-1 leading-snug">
          The control service is not running. Start it on the host:
        </p>
        <code className="mt-1 block break-all font-mono text-[12px]">
          python -m memstara.control
        </code>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <span className="text-[12px] font-bold uppercase tracking-wider text-ink-faint">
        {pipeline.name} · {pipelineLoopLabel(pipeline)}
      </span>

      {running ? (
        <div className="space-y-2">
          <div className="rounded-lg border border-paper-line bg-paper p-3 text-sm">
            <p className="font-bold text-ink">{running.pause_requested ? (running.execution_state === "paused" ? "Stopped · ready to resume" : "Stopping · finishing current work") : running.waiting_for_questions ? "Waiting to explore again" : "Exploration running"}</p>
            <p className="mt-1 break-words leading-relaxed text-ink-soft">{skills.find(s => s.skill === running.skill)?.label || running.skill || "All available knowledge"}</p>
            <p className="mt-2 text-ink-soft">Hypotheses with results: <strong>{completed ?? "—"}</strong></p>
            {!currentSnapshot && <p className="mt-1 text-xs text-ink-faint">Open the active exploration to view its progress.</p>}
            <button type="button" className="mt-2 underline text-ink-soft"
              onClick={() => useViewer.getState().setRunTag(running.run_tag)}>View active exploration</button>
          </div>
          {running.pause_requested && <button type="button" disabled={busy}
            onClick={() => void useControl.getState().pauseRun(false)}
            className="w-full rounded-md bg-accent px-3 py-2 font-bold text-accent-contrast">Play — Resume</button>}
          <Help topic="Stop"><button
            type="button"
            onClick={() => void stopRun()}
            disabled={busy}
            className="flex w-full items-center justify-center gap-1.5 rounded-md bg-red-700
                       px-2 py-1.5 text-xs font-bold text-white hover:bg-red-800
                       disabled:opacity-50"
          >
            <Square className="h-3.5 w-3.5" /> Stop
          </button></Help>
          <ControlAgentSettings form={form} />
        </div>
      ) : (
        <>
          <KnowledgeSelect value={form.skill} onChange={(v) => set("skill", v)} />
          <p className="text-sm leading-relaxed text-ink-soft">
            Agents generate hypotheses from your knowledge sources, evaluate them through the pipeline, and identify promising findings.
          </p>
          <ControlAgentSettings form={form} />

          <details className="text-[12px]">
            <summary className="cursor-pointer text-ink-faint">Advanced settings <Help topic="Model and target" /></summary>
            <div className="mt-2 space-y-2">
              <Text_ label="Y column" value={form.y_column} onChange={(v) => set("y_column", v)} />
              <Text_ label="Provider" value={form.provider} onChange={(v) => set("provider", v)} />
              <Text_ label="LLM model" value={form.model} onChange={(v) => set("model", v)} />
            </div>
          </details>

          <button
            type="button"
            onClick={() => void usePipelines.getState().play(pipeline.id)}
            disabled={busy || workspaceBusy || up !== true}
            className="flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-2
                       py-1.5 text-xs font-bold text-accent-contrast hover:bg-accent/90 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" /> Play
          </button>
          <p className="text-xs leading-relaxed text-ink-faint">Play starts an execution with a finite Loop limit. Stop pauses before the next agent call; Resume preserves progress. Calls already in flight may still incur cost.</p>
        </>
      )}

      {/* The service's own sentence, not a status code. It is the only thing that says
          which field was wrong. */}
      {error && <p className="text-[12px] leading-snug text-red-700">{error}</p>}
    </div>
  );
}
