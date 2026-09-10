import Help from "../components/Help";
import { Play, Square } from "lucide-react";
import { useEffect } from "react";
import { asSlots, MAX_HYPOTHESIS_AGENTS } from "../lib/planned";
import { useControl, type RunRequest } from "../store/control";
import { POLL_MS } from "../store/viewer";
import { useRunForm } from "../lib/useRunForm";

/**
 * The only control on this screen that starts something.
 *
 * It lives in its own file rather than inside `ControlPanel` for the reason the root

 * is being looked at, which view is showing). A form that launches a process is not a
 * navigation control and does not belong in the same component.
 *
 * Three things it is deliberately not:
 *
 *  - **Not a full command line.** Twelve fields, the same twelve the service accepts, and
 *    eight of them behind two disclosures because nobody changes the provider twice a day
 *    and most runs attach no playbook at all.
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
function KnowledgeSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const skills = useControl((s) => s.skills);
  const documents = useControl((s) => s.bundle?.documents);

  return (
    <label className="block">
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">Knowledge sources <Help topic="Skill" /></span>
      <select
        aria-label="Knowledge sources"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-paper-line bg-white px-2 py-1
                   text-xs focus:border-ink focus:outline-none"
      >
        <option value="">All available knowledge{documents != null ? ` · ${documents} documents` : ""}</option>
        {skills.map((s) => (
          <option key={s.skill} value={s.skill}>
            {s.label} · {s.documents} documents
          </option>
        ))}
      </select>
      <span className="mt-1 block text-[11px] font-normal leading-relaxed text-ink-faint">Choose the evidence available to this analysis. Agent instructions below control how it is used.</span>
    </label>
  );
}

/** A compact overview; editing uses the same panel as the pipeline cards. */
function PlaybookSelects({ form }: { form: RunRequest }) {
  const stages = useControl(s => s.playbookStages);
  const catalog = useControl(s => s.catalog);
  const open = useControl(s => s.openEditor);
  const labels: Record<string, string> = { hypothesis: "Hypothesis", ml: "Machine learning", interpreter: "Interpretation", report: "Report" };
  return <details className="rounded-lg border border-paper-line bg-white p-2 text-xs" open>
    <summary className="cursor-pointer font-bold text-ink-soft">Agent settings summary <Help topic="Agent skills" /></summary>
    <p className="my-2 text-[11px] leading-relaxed text-ink-faint">How each agent analyzes the evidence. Select an agent to change its instructions.</p>
    <div className="space-y-2">{stages.filter(s => s !== "data").map(stage => {
      const slots = stage === "hypothesis" ? asSlots(form.playbook_hypothesis, form.hypothesis_agents) : stage === "interpreter" ? asSlots(form.playbook_interpreter, form.interpret_agents) : [form[`playbook_${stage}`]];
      return slots.map((book, i) => {
        const skill = catalog.find(item => item.id === book);
        const agent = `${labels[stage] || stage}${slots.length > 1 ? ` ${i + 1}` : ""}`;
        return <button key={`${stage}-${i}`} type="button" onClick={() => open(stage, i)}
          aria-label={`Change instructions for ${agent}`}
          className="block w-full rounded-md border border-paper-line px-2 py-2 text-left hover:bg-paper focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink">
          <span className="flex items-center justify-between gap-2"><span className="font-bold text-ink-soft">{agent}</span><span className="text-[10px] text-ink-faint">Edit</span></span>
          <span className="mt-1 block break-words text-[11px] leading-relaxed text-ink-soft">{skill?.title || (book ? "Saved instructions · view details" : "Default agent instructions")}</span>
        </button>;
      });
    })}</div>
  </details>;
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
    <label className="block min-w-0 flex-1">
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">{label} <Help topic={label} /></span>
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
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">{label} <Help topic={label} /></span>
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
  // In the store rather than in this component since 2026-09-09. The two pipeline drawings
  // pad themselves to `form.hypothesis_agents`, so the form stopped being this panel's
  // private business the moment something else on the screen answered to it. Nothing about
  // how the form behaves changed — both writers below already computed the next form from
  // the current one, which is exactly what `setForm` takes.
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
        Start a run <Help topic="Start a run" />
      </span>

      {running ? (
        <div className="space-y-2">
          <div className="font-mono text-[11px] leading-snug">
            <div className="font-bold">{running.run_tag}</div>
            <div className="text-ink-faint">{running.skill || "All available knowledge"}</div>
          </div>
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
        </div>
      ) : (
        <>
          <label className="block text-[11px] font-bold">Research question <Help topic="Research question" />
            <textarea value={form.question} onChange={e => set("question", e.target.value)} rows={3}
              className="mt-1 w-full rounded border border-paper-line bg-white p-2 font-normal" />
          </label>
          <KnowledgeSelect value={form.skill} onChange={(v) => set("skill", v)} />
          <div className="grid grid-cols-2 gap-2">
            <Number_ label="Trials" value={form.trials} onChange={(v) => set("trials", v)} />
            <Number_ label="Waves" value={form.waves} onChange={(v) => set("waves", v)} />
            {/* The one stage count on this form, and the reason it is here at all: until
                this field existed, "expandable to three hypothesis agents" was true of the
                drawing and false of the button — a browser could only ever start one, and
                two meant going to the command line. The other three stages were fixed at
                one each by the same meeting and are deliberately not offered. */}
            {/* The standards move with the count, because they are paired by position and
                a name past the last agent is one the service refuses and the form no
                longer shows. Growing pads with "prompt as written"; shrinking drops the
                tail, which is the one the disappearing select was showing. */}
            <div className="col-span-2 flex items-center gap-1"><button type="button" className="flex-1 rounded border border-paper-line px-2 py-1 text-xs"
              disabled={form.hypothesis_agents >= MAX_HYPOTHESIS_AGENTS}
              onClick={() => useControl.getState().openEditor("hypothesis", form.hypothesis_agents, true)}>
              + Hypothesis ({form.hypothesis_agents}/{MAX_HYPOTHESIS_AGENTS})
            </button><Help topic="Add hypothesis" /></div>
            <button type="button" className="col-span-2 rounded border border-paper-line px-2 py-1 text-xs"
              disabled={form.interpret_agents >= 4}
              onClick={() => useControl.getState().openEditor("interpreter", form.interpret_agents, true)}>
              + Interpreter ({form.interpret_agents}/4)
            </button>
            <p className="col-span-2 text-[10px] text-ink-faint">Each hypothesis is interpreted once by an available interpreter. Different skills can produce different perspectives across hypotheses.</p>
          </div>

          <PlaybookSelects form={form} />

          <details className="text-[11px]">
            <summary className="cursor-pointer text-ink-faint">Model and target <Help topic="Model and target" /></summary>
            <div className="mt-2 space-y-2">
              <Text_ label="Y column" value={form.y_column} onChange={(v) => set("y_column", v)} />
              <Text_ label="Provider" value={form.provider} onChange={(v) => set("provider", v)} />
              <Text_ label="LLM model" value={form.model} onChange={(v) => set("model", v)} />
            </div>
          </details>

          <Help topic="Start run"><button
            type="button"
            onClick={() => void startRun(form)}
            disabled={busy}
            className="flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-2
                       py-1.5 text-xs font-bold text-accent-contrast hover:bg-accent/90 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" /> Start run
          </button></Help>
        </>
      )}

      {/* The service's own sentence, not a status code. It is the only thing that says
          which field was wrong. */}
      {error && <p className="text-[11px] leading-snug text-red-700">{error}</p>}
    </div>
  );
}
