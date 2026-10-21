import MLAdvancedSettings from '../components/MLAdvancedSettings';
import {mlOverridesError,overridesForSkills,type MlOverrides} from '../lib/mlOverrides';
import EvaluationSettings from '../components/EvaluationSettings';
import {evaluationPlanError} from '../lib/evaluationPlan';
import {compatibleResearchSkill} from '../lib/researchSkills';
import CreateCustomSkill from '../components/CreateCustomSkill';
import { agentStageLabel } from "../lib/stage";
import AgentReferenceKnowledge from '../components/AgentReferenceKnowledge';
import BaselineSettings from '../components/BaselineSettings';
import { usePipelines } from "../store/pipelines";
import { useRunForm } from "../lib/useRunForm";
import Help from "../components/Help";
import { useEffect, useRef, useState } from "react";
import { X, ArrowDown, Upload, FileText } from "lucide-react";
import { STAGE_ICON } from "../lib/icons";
import { STAGE_COLOR } from "../lib/stage";
import { useControl, type RunRequest, type EvaluationPlan } from "../store/control";
import { asSlots, fromSlots, withPlaybookAt, withoutSlot, withoutInterpreterSlot } from "../lib/planned";

const descriptions: Record<string, string> = {
  data: "Extract the selected predictors and choose training-heavy or balanced stratified allocation. CSV and target definitions are configured in Knowledge sources / Data & target.",
  hypothesis: "Generate a knowledge-grounded hypothesis and choose features for the fixed target. Each hypothesis uses a different skill.",
  ml: "Choose LR or XGBoost. Only the selected model is trained in each Loop; the Data skill determines that Loop's allocation.",
  interpreter: "Describe measured performance and SHAP or LIME attributions for the selected ML model. Clinical interpretation belongs in Explanation.",
  report: "Use the Interpretation output and selected knowledge sources to explain meaning, follow-up questions and limitations. Distinguish measured findings from unverified clinical claims.",
};
const field = "w-full rounded border border-paper-line bg-white px-2 py-1.5 text-sm focus:border-ink focus:outline-hidden";

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
  const uploadInput = useRef<HTMLInputElement>(null);
  const [uploadedName, setUploadedName] = useState("");
  const saveTarget=useRef<HTMLButtonElement>(null);
  const [coach,setCoach]=useState<1|2|3>(1);
  const form = useRunForm();
  const { editor, catalog, setForm, loadPlaybooks, running, busy } = useControl();
  const [choice, setChoice] = useState(editor?.add ? "" :
    editor?.stage === "hypothesis" ? asSlots(form.playbook_hypothesis, form.hypothesis_agents)[editor.slot] :
    editor?.stage === "interpreter" ? asSlots(form.playbook_interpreter, form.interpret_agents)[editor.slot] :
      form[`playbook_${editor!.stage === "report" ? "explanation" : editor!.stage}`]);
  const [plan, setPlan] = useState<EvaluationPlan>({ ...form.evaluation });
  const [overrides,setOverrides]=useState<MlOverrides>(structuredClone(form.ml_overrides??{}));
  const [baseline, setBaseline] = useState(form.baseline_columns ?? []);
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
  const selected = catalog.find(x => x.id === choice && x.stage === stage && compatibleResearchSkill(x, form));
  const used = asSlots(form[`playbook_${stage === "report" ? "explanation" : stage}`], count)
    .filter((_, i) => add || i !== slot).map(id => catalog.find(x => x.id === id)?.hash).filter(Boolean);
  const duplicate = multiple && selected && used.includes(selected.hash);
  const advancedError=stage==='ml'?mlOverridesError(overrides,[choice],plan.replicates):null;
  const invalidPlan = stage === 'ml' && (!!evaluationPlanError(plan)||!!advancedError);
  const commit = async () => {
    if (!selected || duplicate || invalidPlan || saving || running || busy) return;
    if (add && count >= maximum) { setError(`At most ${maximum} ${agentStageLabel(stage)} agents are supported.`); return; }
    const update = (f: RunRequest): RunRequest => {
      if (add && stage === "interpreter") return { ...f, interpret_agents: f.interpret_agents + 1,
        playbook_interpreter: fromSlots([...asSlots(f.playbook_interpreter, f.interpret_agents), choice]) };
      if (add) return { ...f, hypothesis_agents: f.hypothesis_agents + 1,
        trials: Math.max(f.trials, f.hypothesis_agents + 1),
        playbook_hypothesis: fromSlots([...asSlots(f.playbook_hypothesis, f.hypothesis_agents), choice]) };
      return { ...withPlaybookAt(f, stage, slot, choice), baseline_columns: stage === "ml" ? baseline : f.baseline_columns, ml_overrides:stage==="ml"?overridesForSkills(overrides,[choice]):f.ml_overrides, evaluation: stage === "ml" ? plan : f.evaluation };
    };
    const pipeline = usePipelines.getState().items.find(p=>p.id===usePipelines.getState().selected);
    if (pipeline) {
      setSaving(true);
      const saved=await usePipelines.getState().save(pipeline.id,update(pipeline.configuration));
      setSaving(false);
      if (!saved) {setError(usePipelines.getState().error||'Settings could not be saved. Retry.');return;}
    } else setForm(update);
    close();
  };
  const upload = async (file?: File) => {
    if (!file || saving || running || busy) return;
    setError(""); setUploadedName(""); setSaving(true);
    try {
      if (!/\.md$/i.test(file.name)) throw new Error("Choose a Markdown (.md) file.");
      if (!file.size) throw new Error("This file is empty. Choose a skill with instructions.");
      if (file.size > 48000) throw new Error("Choose a Markdown file smaller than 48 kB.");
      const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (!content.trim() || content.includes("\0")) throw new Error("Choose a UTF-8 Markdown file containing instructions.");
      const res = await fetch("/control/playbooks", { method: "POST", signal: AbortSignal.timeout(15000), headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: file.name.replace(/\.md$/i, "").replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 60),
          stage, content }) });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "The skill could not be uploaded. Please try again.");
      // Registration remains usable even if the subsequent catalog refresh fails.
      useControl.setState(s => ({ catalog: [...s.catalog.filter(x => x.id !== body.id), body],
        playbooks: [...new Set([...(s.playbooks ?? []), body.id])] }));
      setChoice(body.id); setOverrides(v=>overridesForSkills(v,[body.id])); setUploadedName(file.name); setCoach(2);
      void loadPlaybooks();
      if (body.evaluation) setPlan(p => ({ ...p, ...body.evaluation }));
    } catch (e) { setError(String(e)); } finally { setSaving(false); if (uploadInput.current) uploadInput.current.value = ""; }
  };
  return <dialog ref={dialog} onCancel={close} aria-labelledby="agent-config-title"
    className="agent-settings-dialog m-auto w-[min(34rem,94vw)] max-h-[90vh] overflow-auto rounded-xl border border-paper-line bg-white p-5 text-ink shadow-xl backdrop:bg-ink/30">
    <div className="flex items-center justify-between gap-3">
      <h2 id="agent-config-title" className="flex items-center gap-2 text-lg font-bold capitalize"><StageIcon size={22} color={STAGE_COLOR[stage]} aria-hidden="true" />{add ? `Add ${agentStageLabel(stage)}` : `${agentStageLabel(stage)} settings`}</h2>
      <button onClick={close} aria-label="Close settings" className="rounded p-1 hover:bg-paper"><X size={18} /></button>
    </div>
    {pipelineName&&<p className="mt-2 text-sm font-semibold text-ink-soft">{pipelineName}</p>}
    <p className="my-3 text-sm leading-relaxed text-ink-soft">{descriptions[stage]} <Help topic={stage} /></p>
    <div className="agent-skill-choice">
    <label className="block text-sm font-semibold" htmlFor="agent-skill-select"><span className="agent-config-step">1</span>Choose a skill <Help topic="Agent skills" /></label>
      <p id="agent-skill-hint" className="my-2 text-xs leading-relaxed text-ink-soft">Start here: open the list below to choose this agent's instructions. You can keep the current skill.</p>
      {coach===1&&<p className="agent-click-hint" role="status"><ArrowDown size={17} aria-hidden="true"/>Click this list to select a skill.</p>}
      <select id="agent-skill-select" aria-describedby="agent-skill-hint" autoFocus className={`${field} agent-skill-select mt-1 ${coach===1?'agent-click-target':''}`} value={choice} onChange={e => {
        setChoice(e.target.value);setUploadedName("");setCoach(e.target.value?2:1);
        setOverrides(v=>overridesForSkills(v,[e.target.value]));
        const defaults = catalog.find(x => x.id === e.target.value)?.evaluation;
        if (defaults) setPlan(p => ({ ...p, ...defaults }));
      }}>
        <option value="">Choose analysis instructions</option>
        {catalog.filter(x => x.stage === stage && compatibleResearchSkill(x, form)).map(x => <option key={x.id} value={x.id}
          disabled={multiple && used.includes(x.hash)}>{x.title}{multiple && used.includes(x.hash) ? " · already used" : ""}</option>)}
      </select>
    {stage==='ml'&&<MLAdvancedSettings skills={[choice]} value={overrides} replicates={plan.replicates} proposal={form.data_mode==='proposal'} disabled={saving||!!running||busy} onChange={setOverrides}/>}
      {coach===1&&selected&&<button type="button" className="mt-3 rounded border border-paper-line px-3 py-2 text-xs font-semibold text-ink" onClick={()=>setCoach(2)}>Keep this skill · review next</button>}

    <section className="mt-4 border-t border-paper-line pt-3" aria-label="Upload a custom skill" aria-busy={saving}>
      <h3 className="text-sm font-semibold">Use your own instructions</h3>
      <p id="custom-skill-help" className="mt-1 text-xs leading-relaxed text-ink-soft">
        Upload a Markdown file for this {agentStageLabel(stage)} agent. Review it below, then save to apply it.
        <span className="mt-1 block">UTF-8 · .md · up to 48 kB</span>
      </p>
      <input ref={uploadInput} className="hidden" type="file" accept=".md" aria-label="Custom skill Markdown file"
        disabled={saving || !!running || busy} onChange={e => void upload(e.target.files?.[0])} />
      <button type="button" aria-describedby="custom-skill-help"
        className="mt-3 inline-flex max-w-full items-center gap-2 rounded-lg border border-paper-line bg-white px-3 py-2 text-sm font-semibold hover:bg-paper focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
        disabled={saving || !!running || busy} onClick={() => uploadInput.current?.click()}>
        <Upload size={17} className="shrink-0" aria-hidden="true" />{saving ? "Uploading…" : "Upload skill (.md)"}
      </button>
      <div aria-live="polite" className="mt-2 text-xs leading-relaxed text-ink-soft">
        {uploadedName && <p className="flex items-start gap-2"><FileText size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{uploadedName} · Uploaded and selected. Save settings to apply.</span></p>}
        {(running || busy) && <p>Stop the pipeline before changing its agent skills.</p>}
      </div>
    </section>
    </div>
    {stage !== "data" && <CreateCustomSkill key={stage} stage={stage} disabled={!!running || busy || saving} onBusy={setSaving}
      onSelect={skill=>{setChoice(skill.id);setOverrides(v=>overridesForSkills(v,[skill.id]));setCoach(2);if(skill.evaluation)setPlan(p=>({...p,...skill.evaluation}));}} />}
    <section ref={reviewTarget} aria-label="Review selected skill" className="mt-3 rounded-lg border border-paper-line bg-paper/40 p-3">
      <h3 className="mb-3 text-sm font-semibold"><span className="agent-config-step">2</span>Review what it does</h3>
    {selected ? <div aria-live="polite">
      <h3 className="text-sm font-bold">{selected.title}</h3>
      <p className="mt-2 text-sm leading-relaxed">{selected.description}</p>
      {coach===2&&<p className="agent-click-hint" role="status"><ArrowDown size={17} aria-hidden="true"/>Click here to read this skill's instructions.</p>}
      <details className="mt-2 text-xs"><summary className={`cursor-pointer rounded p-2 font-bold ${coach===2?'agent-click-target':''}`}>Read full instructions and source</summary>
        <p className="mt-2 text-ink-faint">{selected.source} · version {selected.hash.slice(0, 12)}</p>
        <pre className="mt-2 whitespace-pre-wrap break-words [overflow-wrap:anywhere] font-sans leading-relaxed">{selected.content}</pre>
      </details>
      {coach===2&&<button type="button" className="mt-3 rounded border border-paper-line px-3 py-2 text-xs font-semibold text-ink" onClick={()=>setCoach(3)}>Reviewed · show save button</button>}
    </div>:<p className="text-xs text-ink-soft">Choose a skill in step 1 to see its purpose and full instructions here.</p>}
    </section>
    {stage === "ml" && <AgentReferenceKnowledge />}
    {choice && !selected && <p role="alert" className="mt-3 text-sm">This saved selection is not a skill for this agent. ML Results Presenter belongs to Explanation; ML Knowledge is reference material. Choose an appropriate skill and save.</p>}
    {stage === "ml" && <div className="mt-4 space-y-3">
      <BaselineSettings value={baseline} onChange={setBaseline}/>
      <EvaluationSettings proposal={form.data_mode==='proposal'} value={plan} onChange={setPlan} disabled={saving||!!running||busy}
        paired={!!form.combination_max_loops||['ml_logistic_regression','ml_xgboost'].includes(choice)}
        dataSkill={form.combination_max_loops?'combinations':form.playbook_data}/>
      <p className="text-xs text-ink-faint">The selected model is fitted using the recorded predictors. Missing labels and non-finite values are rejected before training.</p>
    </div>}
    {(error || duplicate || invalidPlan) && <p role="alert" className="mt-3 text-sm text-red-700">{error || advancedError || (invalidPlan ? "Check evaluation ranges. CV folds must be 0 or 2–10." : "Choose a different skill for this agent.")}</p>}
    {!add && multiple && count === 1 && <p className="mt-3 text-xs text-ink-faint">At least one {agentStageLabel(stage)} agent is required.</p>}
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
        disabled={!selected || !!duplicate || invalidPlan || saving || !!running || busy}>{add ? `Add ${agentStageLabel(stage)}` : "Save settings"}</button>
      </div>
    </div>
  </dialog>;
}
