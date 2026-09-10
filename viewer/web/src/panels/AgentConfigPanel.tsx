import { useRunForm } from "../lib/useRunForm";
import Help from "../components/Help";
import { useEffect, useRef, useState } from "react";
import { X, BookMarked } from "lucide-react";
import { useControl, type EvaluationPlan } from "../store/control";
import { asSlots, fromSlots, withPlaybookAt, withoutSlot, withoutInterpreterSlot } from "../lib/planned";

const descriptions: Record<string, string> = {
  hypothesis: "Generate a knowledge-grounded hypothesis and choose features for the fixed target. Each hypothesis uses a different skill.",
  ml: "Train the selected model using the saved evaluation plan. All hypotheses share the same split and evaluation conditions.",
  interpreter: "Explain the measured features and model behavior, including evidence and clinical limitations.",
  report: "Compare completed hypotheses and produce the final report, including failed or unsupported hypotheses.",
};
const field = "w-full rounded border border-paper-line bg-white px-2 py-1.5 text-sm focus:border-ink focus:outline-none";

export default function AgentConfigPanel() {
  const editor = useControl(s => s.editor);
  const close = useControl(s => s.closeEditor);
  if (!editor) return null;
  return <Editor key={`${editor.stage}-${editor.slot}-${editor.add}`} close={close} />;
}

function Editor({ close }: { close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const form = useRunForm();
  const { editor, catalog, setForm, loadPlaybooks, running, busy } = useControl();
  const [choice, setChoice] = useState(editor?.add ? "" :
    editor?.stage === "hypothesis" ? asSlots(form.playbook_hypothesis, form.hypothesis_agents)[editor.slot] :
    editor?.stage === "interpreter" ? asSlots(form.playbook_interpreter, form.interpret_agents)[editor.slot] :
      form[`playbook_${editor!.stage}`]);
  const [plan, setPlan] = useState<EvaluationPlan>({ ...form.evaluation });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { const d = dialog.current; d?.showModal(); return () => d?.close(); }, []);
  if (!editor) return null;
  const { stage, slot, add } = editor;
  const multiple = stage === "hypothesis" || stage === "interpreter";
  const count = stage === "interpreter" ? form.interpret_agents : form.hypothesis_agents;
  const maximum = 4;
  const selected = catalog.find(x => x.id === choice);
  const used = asSlots(form[`playbook_${stage}`], count)
    .filter((_, i) => add || i !== slot).map(id => catalog.find(x => x.id === id)?.hash).filter(Boolean);
  const duplicate = multiple && selected && used.includes(selected.hash);
  const invalidPlan = stage === "ml" && (
    !Number.isInteger(plan.seed) || plan.seed < 0 || plan.seed > 2147483647 ||
    !Number.isFinite(plan.test_size) || plan.test_size < .1 || plan.test_size > .5 ||
    !Number.isInteger(plan.folds) || plan.folds < 0 || plan.folds === 1 || plan.folds > 10 ||
    !Number.isInteger(plan.replicates) || plan.replicates < 1 || plan.replicates > 10 ||
    !Number.isInteger(plan.search_trials) || plan.search_trials < 1 || plan.search_trials > 10
  );
  const commit = () => {
    if (!selected || duplicate || invalidPlan || running || busy) return;
    if (add && count >= maximum) { setError(`At most ${maximum} ${stage} agents are supported.`); return; }
    setForm(f => {
      if (add && stage === "interpreter") return { ...f, interpret_agents: f.interpret_agents + 1,
        playbook_interpreter: fromSlots([...asSlots(f.playbook_interpreter, f.interpret_agents), choice]) };
      if (add) return { ...f, hypothesis_agents: f.hypothesis_agents + 1,
        trials: Math.max(f.trials, f.hypothesis_agents + 1),
        playbook_hypothesis: fromSlots([...asSlots(f.playbook_hypothesis, f.hypothesis_agents), choice]) };
      return { ...withPlaybookAt(f, stage, slot, choice), evaluation: stage === "ml" ? plan : f.evaluation };
    });
    close();
  };
  const upload = async (file?: File) => {
    if (!file) return;
    setError(""); setSaving(true);
    try {
      if (file.size > 48000) throw new Error("Choose a Markdown file smaller than 48 kB.");
      const res = await fetch("/control/playbooks", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: file.name.replace(/\.md$/i, "").replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 60),
          stage, content: await file.text() }) });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error);
      await loadPlaybooks(); setChoice(body.id);
      if (body.evaluation) setPlan(p => ({ ...p, ...body.evaluation }));
    } catch (e) { setError(String(e)); } finally { setSaving(false); }
  };
  return <dialog ref={dialog} onCancel={close} aria-labelledby="agent-config-title"
    className="m-auto w-[min(34rem,94vw)] max-h-[90vh] overflow-auto rounded-xl border border-paper-line bg-white p-5 text-ink shadow-xl backdrop:bg-ink/30">
    <div className="flex items-center justify-between gap-3">
      <h2 id="agent-config-title" className="flex items-center gap-2 text-lg font-bold capitalize"><BookMarked size={18} />{add ? `Add ${stage}` : `${stage} settings`}</h2>
      <button onClick={close} aria-label="Close settings" className="rounded p-1 hover:bg-paper"><X size={18} /></button>
    </div>
    <p className="my-3 text-sm leading-relaxed text-ink-soft">{descriptions[stage]} <Help topic={stage} /></p>
    <label className="block text-xs font-bold">Analysis instructions <Help topic="Agent skills" />
      <select autoFocus className={`${field} mt-1`} value={choice} onChange={e => {
        setChoice(e.target.value);
        const defaults = catalog.find(x => x.id === e.target.value)?.evaluation;
        if (defaults) setPlan(p => ({ ...p, ...defaults }));
      }}>
        <option value="">Choose analysis instructions</option>
        {catalog.filter(x => x.stage === stage).map(x => <option key={x.id} value={x.id}
          disabled={multiple && used.includes(x.hash)}>{x.title}{multiple && used.includes(x.hash) ? " · already used" : ""}</option>)}
      </select>
    </label>
    {selected && <div className="mt-3 rounded-lg border border-paper-line bg-paper/40 p-3">
      <h3 className="text-sm font-bold">{selected.title}</h3>
      <p className="mt-2 text-sm leading-relaxed">{selected.description}</p>
      <details className="mt-2 text-xs"><summary className="cursor-pointer font-bold">Read full instructions and source</summary>
        <p className="mt-2 text-ink-faint">{selected.source} · version {selected.hash.slice(0, 12)}</p>
        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-sans leading-relaxed">{selected.content}</pre>
      </details>
    </div>}
    <label className="mt-3 block text-xs font-bold">Upload your own instructions (.md) <Help topic="Use your own skill (.md)" />
      <input className="mt-1 block w-full text-xs font-normal" type="file" accept=".md,text/markdown,text/plain"
        disabled={saving} onChange={e => void upload(e.target.files?.[0])} />
    </label>
    {stage === "ml" && <fieldset className="mt-4 space-y-2 border-t border-paper-line pt-3">
      <legend className="text-xs font-bold">Predictive model and evaluation <Help topic="Predictive model" /></legend>
      <select aria-label="Predictive model" className={field} value={plan.engine} onChange={e => setPlan({ ...plan, engine: e.target.value })}>
        <option value="xgboost">XGBoost</option><option value="random_forest">Random forest (scikit-learn)</option>
        <option value="logistic_regression">Logistic regression (scikit-learn)</option>
      </select>
      <div className="grid grid-cols-2 gap-2">{([
        ["seed", "Seed", 0, 2147483647, 1], ["test_size", "Hold-out fraction", .1, .5, .05],
        ["folds", "CV folds (0 = off)", 0, 10, 1], ["replicates", "Replicates", 1, 10, 1],
        ["search_trials", "HP candidates", 1, 10, 1],
      ] as const).map(([key, label, min, max, step]) => <label key={key} className="text-xs">{label} <Help topic={label} />
        <input className={field} type="number" min={min} max={max} step={step} value={plan[key]}
          onChange={e => setPlan({ ...plan, [key]: e.target.valueAsNumber })} /></label>)}</div>
      <p className="text-xs text-ink-faint">Optimization uses training folds only. Hold-out results are not used to choose a model.</p>
    </fieldset>}
    {(error || duplicate || invalidPlan) && <p role="alert" className="mt-3 text-sm text-red-700">{error || (invalidPlan ? "Check evaluation ranges. CV folds must be 0 or 2–10." : "Choose a different skill for this agent.")}</p>}
    {!add && multiple && count === 1 && <p className="mt-3 text-xs text-ink-faint">At least one {stage} agent is required.</p>}
    <div className="mt-5 flex justify-end gap-2">
      {!add && multiple && count > 1 && <button className="mr-auto rounded border border-red-200 px-3 py-2 text-sm text-red-700 disabled:opacity-40"
        disabled={saving || !!running || busy} onClick={() => {
          if (running || busy || saving) return;
          setForm(f => stage === "interpreter" ? withoutInterpreterSlot(f, slot) : withoutSlot(f, slot));
          close();
        }}>Remove agent</button>}
      <button className="rounded border border-paper-line px-3 py-2 text-sm" onClick={close}>Cancel</button>
      <button className="rounded bg-accent px-3 py-2 text-sm font-bold text-accent-contrast disabled:opacity-40" onClick={commit}
        disabled={!selected || !!duplicate || invalidPlan || saving || !!running || busy}>{add ? `Add ${stage}` : "Save settings"}</button>
    </div>
  </dialog>;
}
