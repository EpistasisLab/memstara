import { Play, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { DEFAULT_REQUEST, useControl, type RunRequest } from "../store/control";
import { POLL_MS } from "../store/viewer";

/**
 * The only control on this screen that starts something.
 *
 * It lives in its own file rather than inside `ControlPanel` for the reason the root

 * is being looked at, which view is showing). A form that launches a process is not a
 * navigation control and does not belong in the same component.
 *
 * Three things it is deliberately not:
 *
 *  - **Not a full command line.** Six fields, the same six the service accepts, and
 *    three of them behind a disclosure because nobody changes the provider twice a day.
 *    Everything else `board.py` takes is still there for whoever runs it by hand.
 *  - **Not a validator.** The service refuses a bad request and says why in words; this
 *    shows that sentence. Two places deciding what a legal request is means one of them
 *    is eventually wrong, and it would be this one.
 *  - **Not a progress display.** Once a run starts, the run selector points at it and
 *    the existing 2-second poll fills the rest of the screen in. All this keeps is the
 *    tag and a Stop button.
 */

/** The branch list is one read of the bundle; a run confined to nothing is not offered,
 *  so "whole bundle" is the only entry with no filter behind it. */
function SkillSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const skills = useControl((s) => s.skills);
  const documents = useControl((s) => s.bundle?.documents);

  return (
    <label className="block">
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">Skill</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-paper-line bg-white px-2 py-1
                   font-mono text-xs focus:border-ink focus:outline-none"
      >
        <option value="">whole bundle{documents ? ` — ${documents}` : ""}</option>
        {skills.map((s) => (
          <option key={s.skill} value={s.skill}>
            {s.label} — {s.documents}
          </option>
        ))}
      </select>
    </label>
  );
}

function Number_({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block flex-1">
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.valueAsNumber)}
        className="mt-1 w-full rounded-md border border-paper-line bg-white px-2 py-1
                   font-mono text-xs focus:border-ink focus:outline-none"
      />
    </label>
  );
}

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
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">{label}</span>
      <input
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
  const startRun = useControl((s) => s.startRun);
  const stopRun = useControl((s) => s.stopRun);
  const [form, setForm] = useState<RunRequest>(DEFAULT_REQUEST);
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

  if (up === false) {
    return (
      <div className="text-[11px] text-ink-faint">
        <span className="font-bold uppercase tracking-wider">Start a run</span>
        <p className="mt-1 leading-snug">
          The control service is not running. Start it on the host:
        </p>
        <code className="mt-1 block break-all font-mono text-[10px]">
          python -m memstara.control
        </code>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">
        Start a run
      </span>

      {running ? (
        <div className="space-y-2">
          <div className="font-mono text-[11px] leading-snug">
            <div className="font-bold">{running.run_tag}</div>
            <div className="text-ink-faint">{running.skill || "whole bundle"}</div>
          </div>
          <button
            type="button"
            onClick={() => void stopRun()}
            disabled={busy}
            className="flex w-full items-center justify-center gap-1.5 rounded-md bg-red-700
                       px-2 py-1.5 text-xs font-bold text-white hover:bg-red-800
                       disabled:opacity-50"
          >
            <Square className="h-3.5 w-3.5" /> Stop
          </button>
        </div>
      ) : (
        <>
          <SkillSelect value={form.skill} onChange={(v) => set("skill", v)} />
          <div className="flex gap-2">
            <Number_ label="Trials" value={form.trials} onChange={(v) => set("trials", v)} />
            <Number_ label="Waves" value={form.waves} onChange={(v) => set("waves", v)} />
          </div>

          <details className="text-[11px]">
            <summary className="cursor-pointer text-ink-faint">Model and target</summary>
            <div className="mt-2 space-y-2">
              <Text_ label="Y column" value={form.y_column} onChange={(v) => set("y_column", v)} />
              <Text_ label="Provider" value={form.provider} onChange={(v) => set("provider", v)} />
              <Text_ label="Model" value={form.model} onChange={(v) => set("model", v)} />
            </div>
          </details>

          <button
            type="button"
            onClick={() => void startRun(form)}
            disabled={busy}
            className="flex w-full items-center justify-center gap-1.5 rounded-md bg-ink px-2
                       py-1.5 text-xs font-bold text-white hover:bg-ink/90 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" /> Start run
          </button>
        </>
      )}

      {/* The service's own sentence, not a status code. It is the only thing that says
          which field was wrong. */}
      {error && <p className="text-[11px] leading-snug text-red-700">{error}</p>}
    </div>
  );
}
