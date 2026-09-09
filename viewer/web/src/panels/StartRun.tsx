import { Play, Square } from "lucide-react";
import { useEffect } from "react";
import { asSlots, fromSlots, withPlaybookAt } from "../lib/planned";
import { useControl, type PlaybookStage, type RunRequest } from "../store/control";
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

/**
 * One select per stage that can be handed a behavioural standard — and for the hypothesis
 * stage, one per agent.
 *
 * **Both lists come from the service and neither is written here.** Which playbooks exist
 * is a directory; which stages can take one is read off the prompt files, because a
 * playbook only reaches a model through a prompt carrying a `{{playbook}}` line and the
 * driver refuses the pair otherwise. Offering a row for a stage without the marker would
 * be a form that lies about what it can start — the run would be refused after the button
 * was pressed, which is the one place a form is not allowed to be wrong.
 *
 * The consequence worth knowing: marking a third prompt is one line in one `.md` file and
 * a third row appears here. There is no list in this component to add it to.
 *
 * **The hypothesis row is the only one that grows, and that is not a layout choice.** Its
 * workers set out independently and one agent is provisioned per standard (`A-32`), so
 * three standards mean three agents whose agreement is worth something. Every other stage
 * runs a single agent however many workers claim from the board, so a second select there
 * would offer a standard that is accepted and never read. Which stage this is comes from
 * `MULTI_PLAYBOOK_STAGES` in `src/memstara/control/request.py`, restated here as a
 * comparison against the one name rather than copied as a list, because a second list is
 * a second answer to keep in step.
 *
 * Renders nothing at all when there are no playbooks or no marked stages. An empty
 * disclosure is a promise of a feature this checkout does not have.
 *
 * **It is no longer the only way to set one.** Since `A-44` each card in the Pipeline view
 * carries the same choice, which is what the 2026-08-26 figure asked for — a skill shown
 * and chosen on the agent it belongs to

 * `withPlaybookAt`, so this disclosure stays the place to see all five stages at once and
 * neither control can produce a field value the other would not.
 */
function PlaybookSelects({
  form,
  onChange,
}: {
  form: RunRequest;
  onChange: (stage: PlaybookStage, slot: number, book: string) => void;
}) {
  const playbooks = useControl((s) => s.playbooks);
  const stages = useControl((s) => s.playbookStages);

  if (!playbooks?.length || !stages.length) return null;

  return (
    <details className="text-[11px]">
      <summary className="cursor-pointer text-ink-faint">Playbooks</summary>
      <div className="mt-2 space-y-2">
        {stages.map((stage) => {
          // One slot for every stage; the hypothesis stage is the one where that number
          // can exceed 1, and it follows the agent count above rather than a control of
          // its own. Two numbers meaning "how many hypothesis standards" would be two
          // numbers to keep equal, and the service refuses the pair when they are not.
          const slots =
            stage === "hypothesis"
              ? asSlots(form.playbook_hypothesis, form.hypothesis_agents)
              : [form[`playbook_${stage}`]];
          return (
            <div key={stage} className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">
                {stage}
              </span>
              <div className="mt-1 space-y-1">
                {slots.map((book, i) => (
                  <select
                    key={i}
                    value={book}
                    onChange={(e) => onChange(stage, i, e.target.value)}
                    className="w-full rounded-md border border-paper-line bg-white px-2 py-1
                               font-mono text-xs focus:border-ink focus:outline-none"
                  >
                    {/* Named rather than blank. "none" would read as a missing setting;
                        this says what the run is, and it is what every run before
                        playbooks was. The agent number is on the option rather than on a
                        label, so a stage with one agent looks exactly as it did. */}
                    <option value="">
                      prompt as written{slots.length > 1 ? ` — agent ${i + 1}` : ""}
                    </option>
                    {playbooks.map((b) => (
                      <option key={b} value={b}>
                        {b}
                      </option>
                    ))}
                  </select>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </details>
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
  // In the store rather than in this component since 2026-09-09. The two pipeline drawings
  // pad themselves to `form.hypothesis_agents`, so the form stopped being this panel's
  // private business the moment something else on the screen answered to it. Nothing about
  // how the form behaves changed — both writers below already computed the next form from
  // the current one, which is exactly what `setForm` takes.
  const form = useControl((s) => s.form);
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
            {/* The one stage count on this form, and the reason it is here at all: until
                this field existed, "expandable to three hypothesis agents" was true of the
                drawing and false of the button — a browser could only ever start one, and
                two meant going to the command line. The other three stages were fixed at
                one each by the same meeting and are deliberately not offered. */}
            {/* The standards move with the count, because they are paired by position and
                a name past the last agent is one the service refuses and the form no
                longer shows. Growing pads with "prompt as written"; shrinking drops the
                tail, which is the one the disappearing select was showing. */}
            <Number_
              label="Hypothesis"
              value={form.hypothesis_agents}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  hypothesis_agents: v,
                  playbook_hypothesis: fromSlots(asSlots(f.playbook_hypothesis, v)),
                }))
              }
            />
          </div>

          <PlaybookSelects
            form={form}
            onChange={(stage, slot, book) =>
              setForm((f) => withPlaybookAt(f, stage, slot, book))
            }
          />

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
