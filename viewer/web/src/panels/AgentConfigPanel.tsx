import { usePipelines } from "../store/pipelines";
import { useRunForm } from "../lib/useRunForm";
import Help from "../components/Help";
import { useEffect, useRef, useState } from "react";
import { X, ArrowDown } from "lucide-react";
import { STAGE_ICON } from "../lib/icons";
import { STAGE_COLOR } from "../lib/stage";
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
  const pipelineName=usePipelines(s=>s.items.find(p=>p.id===s.selected)?.name);
  const dialog = useRef<HTMLDialogElement>(null);
  const reviewTarget=useRef<HTMLElement>(null);
  const saveTarget=useRef<HTMLButtonElement>(null);
  const [coach,setCoach]=useState<1|2|3>(1);
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
  useEffect(()=>{
    const target=coach===2?reviewTarget.current:coach===3?saveTarget.current:null;
    target?.scrollIntoView({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    if(coach===3)saveTarget.current?.focus({preventScroll:true});
  },[coach]);
  if (!editor) return null;
  const { stage, slot, add } = editor;
  const StageIcon=STAGE_ICON[stage];
  const multiple = stage === "hypothesis" || stage === "interpreter";
  const count = stage === "interpreter" ? form.interpret_agents : form.hypothesis_agents;
  const maximum = usePipelines.getState().selected ? 1 : 4;
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
      await loadPlaybooks(); setChoice(body.id); setCoach(2);
      if (body.evaluation) setPlan(p => ({ ...p, ...body.evaluation }));
    } catch (e) { setError(String(e)); } finally { setSaving(false); }
  };
  return <dialog ref={dialog} onCancel={close} aria-labelledby="agent-config-title"
    className="agent-settings-dialog m-auto w-[min(34rem,94vw)] max-h-[90vh] overflow-auto rounded-xl border border-paper-line bg-white p-5 text-ink shadow-xl backdrop:bg-ink/30">
    <div className="flex items-center justify-between gap-3">
      <h2 id="agent-config-title" className="flex items-center gap-2 text-lg font-bold capitalize"><StageIcon size={22} color={STAGE_COLOR[stage]} aria-hidden="true" />{add ? `Add ${stage}` : `${stage} settings`}</h2>
      <button onClick={close} aria-label="Close settings" className="rounded p-1 hover:bg-paper"><X size={18} /></button>
    </div>
    {pipelineName&&<p className="mt-2 text-sm font-semibold text-ink-soft">{pipelineName}</p>}
    <p className="my-3 text-sm leading-relaxed text-ink-soft">{descriptions[stage]} <Help topic={stage} /></p>
    <div className="agent-skill-choice">
    <label className="block text-sm font-semibold" htmlFor="agent-skill-select"><span className="agent-config-step">1</span>Choose a skill <Help topic="Agent skills" /></label>
      <p id="agent-skill-hint" className="my-2 text-xs leading-relaxed text-ink-soft">Start here: open the list below to choose this agent's instructions. You can keep the current skill.</p>
      {coach===1&&<p className="agent-click-hint" role="status"><ArrowDown size={17} aria-hidden="true"/>Click this list to select a skill.</p>}
      <select id="agent-skill-select" aria-describedby="agent-skill-hint" autoFocus className={`${field} agent-skill-select mt-1 ${coach===1?'agent-click-target':''}`} value={choice} onChange={e => {
        setChoice(e.target.value);setCoach(e.target.value?2:1);
        const defaults = catalog.find(x => x.id === e.target.value)?.evaluation;
        if (defaults) setPlan(p => ({ ...p, ...defaults }));
      }}>
        <option value="">Choose analysis instructions</option>
        {catalog.filter(x => x.stage === stage).map(x => <option key={x.id} value={x.id}
          disabled={multiple && used.includes(x.hash)}>{x.title}{multiple && used.includes(x.hash) ? " · already used" : ""}</option>)}
      </select>
      {coach===1&&selected&&<button type="button" className="mt-3 rounded border border-paper-line px-3 py-2 text-xs font-semibold text-ink" onClick={()=>setCoach(2)}>Keep this skill · review next</button>}

    <details className="mt-3 text-xs text-ink-soft"><summary className="cursor-pointer font-semibold">Or upload your own skill (.md)</summary>
      <label className="mt-2 block">Choose a Markdown file instead of a skill from the list. <Help topic="Use your own skill (.md)" />
        <input className="mt-2 block w-full text-xs font-normal" type="file" accept=".md,text/markdown,text/plain"
          disabled={saving} onChange={e => void upload(e.target.files?.[0])} />
      </label>
    </details>
    </div>
    <section ref={reviewTarget} aria-label="Review selected skill" className="mt-3 rounded-lg border border-paper-line bg-paper/40 p-3">
      <h3 className="mb-3 text-sm font-semibold"><span className="agent-config-step">2</span>Review what it does</h3>
    {selected ? <div aria-live="polite">
      <h3 className="text-sm font-bold">{selected.title}</h3>
      <p className="mt-2 text-sm leading-relaxed">{selected.description}</p>
      {coach===2&&<p className="agent-click-hint" role="status"><ArrowDown size={17} aria-hidden="true"/>Click here to read this skill's instructions.</p>}
      <details className="mt-2 text-xs"><summary className={`cursor-pointer rounded p-2 font-bold ${coach===2?'agent-click-target':''}`}>Read full instructions and source</summary>
        <p className="mt-2 text-ink-faint">{selected.source} · version {selected.hash.slice(0, 12)}</p>
        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-sans leading-relaxed">{selected.content}</pre>
      </details>
      {coach===2&&<button type="button" className="mt-3 rounded border border-paper-line px-3 py-2 text-xs font-semibold text-ink" onClick={()=>setCoach(3)}>Reviewed · show save button</button>}
    </div>:<p className="text-xs text-ink-soft">Choose a skill in step 1 to see its purpose and full instructions here.</p>}
    </section>
    {stage === "ml" && <fieldset className="mt-4 space-y-2 border-t border-paper-line pt-3">
      <legend className="text-xs font-bold">Predictive model and evaluation <Help topic="Predictive model" /></legend>
      <select aria-label="Predictive model" className={field} value={plan.engine} onChange={e => setPlan({ ...plan, engine: e.target.value })}>
        <option value="xgboost">XGBoost</option><option value="random_forest">Random forest (scikit-learn)</option>
        <option value="logistic_regression">Logistic regression (scikit-learn)</option>
      </select>
      <p className="text-xs text-ink-faint" role="note">{plan.engine === "xgboost"
        ? "Missing values supported: numeric gaps use XGBoost's native tree routing; categorical gaps are encoded when seen in training. No imputation or row deletion."
        : "This model requires complete predictors. Choose XGBoost to retain missing values without imputation."}
        {" Missing target labels and infinite values are always rejected before a run starts."}</p>
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
    <div className="agent-settings-footer mt-5 flex flex-wrap justify-end gap-2">
      <div className="w-full"><p className="text-sm font-semibold"><span className="agent-config-step">3</span>Apply to this agent</p>
        <p className="mt-1 text-xs text-ink-soft">{!selected?'Choose a skill above to enable saving.':invalidPlan?'Correct the evaluation settings above before saving.':saving?'Uploading your skill…':'Click the highlighted button below to save. Then continue the pipeline setup guide.'}</p></div>
      {!add && multiple && count > 1 && <button className="mr-auto rounded border border-red-200 px-3 py-2 text-sm text-red-700 disabled:opacity-40"
        disabled={saving || !!running || busy} onClick={() => {
          if (running || busy || saving) return;
          setForm(f => stage === "interpreter" ? withoutInterpreterSlot(f, slot) : withoutSlot(f, slot));
          close();
        }}>Remove agent</button>}
      <button className="rounded border border-paper-line px-3 py-2 text-sm" onClick={close}>Cancel</button>
      <div className="agent-save-target">
      {coach===3&&<p className="agent-click-hint" role="status"><ArrowDown size={17} aria-hidden="true"/>{invalidPlan?'Fix the evaluation values above first.':duplicate?'Choose a different skill above first.':saving||busy?'Wait for the current operation to finish.':'Click here to apply your settings.'}</p>}
      <button ref={saveTarget} className={`rounded bg-accent px-3 py-2 text-sm font-bold text-accent-contrast disabled:opacity-40 ${coach===3?'agent-click-target':''}`} onClick={commit}
        disabled={!selected || !!duplicate || invalidPlan || saving || !!running || busy}>{add ? `Add ${stage}` : "Save settings"}</button>
      </div>
    </div>
  </dialog>;
}
