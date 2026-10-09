import ResearchInputs from '../components/ResearchInputs';
import ResearchInputSelect from '../components/ResearchInputSelect';
import CombinationWizard from '../components/CombinationWizard';
import FloorDetailDialog from '../components/FloorDetailDialog';
import AgentReferenceKnowledge from '../components/AgentReferenceKnowledge';
import EvaluationSettings from '../components/EvaluationSettings';
import { evaluationPlanError } from '../lib/evaluationPlan';
import LoopLimitSettings from "../components/LoopLimitSettings";
import BaselineSettings from '../components/BaselineSettings';
import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, X } from 'lucide-react';
import { useControl, type RunRequest } from '../store/control';
import { usePipelines } from '../store/pipelines';
const setupStages = ['hypothesis', 'data', 'ml', 'interpreter', 'report'] as const;

import KnowledgeSelect from '../components/KnowledgeSelect';
import CustomSkillUpload from '../components/CustomSkillUpload';

const labels = ['Knowledge sources', 'Hypothesis', 'Data', 'Machine learning', 'Interpretation', 'Explanation', 'Name', 'Review'];
const guidance = {
  data: 'Choose how this agent maps requested features to available columns without cleaning the cohort.',
  hypothesis: 'Choose how this agent uses knowledge to generate hypotheses and select features.',
  ml: 'Choose the model and the skill that guides how experiments are evaluated.',
  interpreter: 'Choose how measured results are explained, including clinical meaning and limitations.',
  report: 'Choose how findings are compared and useful hypotheses are recommended.',
};
const field = 'w-full rounded-lg border border-paper-line bg-white px-3 py-2 text-sm text-ink';
const addictionSkills = new Set(['addiction-substance-use', 'addiction-sdoh', 'addiction-psychiatric']);

export default function PipelineCreationDialog() {
  const open = usePipelines(s => s.creationOpen);
  return open ? <ChooseBuildMode /> : null;
}

function ChooseBuildMode() {
  const [mode,setMode]=useState<'selected'|'all'|'research'|null>(null);
  if(mode==='research')return <FloorDetailDialog title="Prepare research inputs" close={()=>setMode(null)}><ResearchInputs/></FloorDetailDialog>;
  if(mode==='selected')return <CreationWizard/>;
  if(mode==='all')return <CombinationWizard/>;
  return <FloorDetailDialog title="Build pipelines" close={()=>usePipelines.getState().closeCreation()}>
    <div className="space-y-4 p-3">
      <button type="button" className="w-full rounded-xl border border-paper-line p-4 text-left" onClick={()=>setMode('research')}><strong>Prepare research inputs</strong><p>Inspect and register your OKF corpus, dataset and target definition before connecting a pipeline.</p></button>
      <button type="button" className="w-full rounded-xl border border-paper-line p-4 text-left" onClick={()=>setMode('selected')}><strong>Selected Pipelines</strong><p>Build one pipeline, then run it when ready. Add more separately.</p></button>
      <button type="button" className="w-full rounded-xl border border-paper-line p-4 text-left" onClick={()=>setMode('all')}><strong>All Combinations</strong><p>Select multiple skills per agent, choose a starting method and set your maximum Loops.</p></button>
    </div>
  </FloorDetailDialog>;
}

function CreationWizard() {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [uploading, setUploading] = useState(false);
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [draft, setDraft] = useState<RunRequest>(() => {
    const form = structuredClone(useControl.getState().form);
    return { ...form, combination_skills: {}, combination_repetitions: 1, combination_random_start: false, combination_max_loops: null, question: '', hypothesis_agents: 1, interpret_agents: 1,
      trials: 1, waves: 10, continuous: false,
      playbook_hypothesis: form.playbook_hypothesis.split(',')[0],
      playbook_data: form.playbook_data.split(',')[0],
      playbook_ml: form.playbook_ml.split(',')[0],
      playbook_explanation: "report_clinical_explanations",
      playbook_interpreter: "interpreter_factual_observations" };
  });
  const sources = useControl(s => s.skills);
  const [sourceReviewed, setSourceReviewed] = useState(false);
  const catalog = useControl(s => s.catalog);
  const { busy, error, closeCreation, create } = usePipelines();
  const [loading, setLoading] = useState(true);
  const reload = async () => {
    setLoading(true);
    await Promise.all([useControl.getState().loadPlaybooks(), useControl.getState().loadSkills()]);
    setLoading(false);
  };
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    let mounted = true;
    void Promise.all([useControl.getState().loadPlaybooks(), useControl.getState().loadSkills()]).then(() => { if(mounted)setLoading(false); });
    return () => { mounted = false; element?.close(); };
  }, []);
  useEffect(() => { if(step > 0) heading.current?.focus(); }, [step]);
  const stage = step > 0 && step < 6 ? setupStages[step - 1] : null;
  const skill = stage ? catalog.find(s => s.stage === stage && s.id === draft[`playbook_${stage === "report" ? "explanation" : stage}`]) : null;
  const complete = setupStages.every(s => catalog.some(c => c.stage === s && c.id === draft[`playbook_${s === "report" ? "explanation" : s}`]));
  const validName = Boolean(name.trim()) && name.length <= 80;
  const validModel = evaluationPlanError(draft.evaluation) === null;
  const validSource = sourceReviewed && (draft.skill === '' || sources.some(s => s.skill === draft.skill));
  const sourceLabel = draft.skill === '' ? 'All available knowledge' : sources.find(s => s.skill === draft.skill)?.label || 'Unavailable source';
  const valid = step === 0 ? validSource : step === 6 ? validName : step === 7 ? validSource && validName && complete && validModel && Number.isInteger(draft.waves) && draft.waves >= 1 && draft.waves <= 10 : Boolean(skill) && (stage !== 'ml' || validModel);
  return <dialog ref={dialog} aria-labelledby="pipeline-create-title" aria-describedby="pipeline-create-description"
    onCancel={event => { event.preventDefault(); if (!busy && !uploading) closeCreation(); }}
    onKeyDown={event => {
      if(event.key !== 'Tab') return;
      const targets = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]')]
        .filter(element => element.getClientRects().length > 0);
      const first = targets[0], last = targets[targets.length - 1];
      if(!first) { event.preventDefault(); return; }
      if(event.shiftKey && (document.activeElement === first || !targets.includes(document.activeElement as HTMLElement))) {
        event.preventDefault(); last.focus();
      } else if(!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }}
    className="agent-settings-dialog pipeline-creation-dialog">
    <header className="pipeline-creation-header flex items-start justify-between gap-3">
      <div className="min-w-0"><h2 id="pipeline-create-title" className="text-xl font-semibold">Create a pipeline</h2>
        <p id="pipeline-create-description" className="mt-1 text-sm text-ink-muted">Choose your knowledge sources, set up each agent, then name and review your pipeline.</p></div>
      <button type="button" aria-label="Cancel pipeline setup" disabled={busy || uploading} onClick={closeCreation} className="rounded p-2 hover:bg-paper-panel disabled:opacity-40"><X size={20} /></button>
    </header>
    <ol aria-label="Setup progress" className="pipeline-creation-progress">
      {labels.map((label, index) => <li key={label} aria-current={index === step ? 'step' : undefined} title={label}
        className={index <= step ? 'is-reached' : ''}><span className="pipeline-creation-step-number">{index < step ? <Check size={14} aria-label="Completed"/> : index + 1}</span><span>{label}</span></li>)}
    </ol>
    <form className="pipeline-creation-form" onSubmit={async event => { event.preventDefault(); if(!valid || busy || loading || uploading)return; if(step < 7)setStep(step + 1); else await create(name.trim(), draft); }}>
      <div className="pipeline-creation-body space-y-4">
        <h3 ref={heading} tabIndex={-1} className="text-lg font-semibold">{step + 1}. {labels[step]} <span className="text-xs font-normal text-ink-muted">· Step {step + 1} of {labels.length}</span></h3>
        {step === 0 && <><p className="text-sm text-ink-muted">Choose the evidence this pipeline will explore to generate research questions and hypotheses. Agent skills are configured in the following steps.</p>
          <ResearchInputSelect value={draft} onChange={patch=>{setDraft(d=>({...d,...patch}));setSourceReviewed(false);}}/>
          {!draft.research_input_id&&draft.knowledge_mode!=='llm_only'&&<KnowledgeSelect value={draft.skill} onChange={value => { setDraft(d => ({...d, skill: value})); setSourceReviewed(false); }} />}
          <label className="flex items-start gap-3 rounded-lg border border-paper-line bg-paper-panel p-3 text-sm"><input type="checkbox" checked={sourceReviewed} onChange={e => setSourceReviewed(e.target.checked)} className="mt-1"/><span>Use {sourceLabel} for this pipeline.</span></label>
          {!loading && sources.length === 0 && <p className="text-sm text-ink-muted">No source filters are listed. You can use all available knowledge, or <button type="button" className="underline" onClick={() => void reload()}>reload sources</button>.</p>}
        </>}
        {step === 6 && <><p className="text-sm text-ink-muted">Give this configured pipeline a recognizable name. Next, review the settings and create it.</p>
          <label className="block space-y-2 text-sm font-medium">Pipeline name
            <input autoFocus required maxLength={80} className={field} placeholder="e.g. Treatment-related effects" value={name} onChange={e => setName(e.target.value)} /></label>
          <p className="text-xs text-ink-muted">Settings remain a draft until you choose Create pipeline.</p></>}
        {stage && <><p className="text-sm text-ink-muted">{guidance[stage]}</p>
          {stage === 'hypothesis' && <aside className="rounded-lg border border-paper-line bg-paper-panel p-3 text-sm" aria-label="Addiction KB skill guidance">
            <p className="font-medium">Exploring Addiction KB?</p>
            <p className="mt-1 text-ink-muted">Choose a research focus below, or browse the full skill list.</p>
            <div className="mt-2 flex flex-col gap-2">
              {catalog.filter(s => s.stage === 'hypothesis' && addictionSkills.has(s.id)).map(s => <button
                key={s.id} type="button" disabled={loading || busy || uploading} aria-pressed={skill?.id === s.id}
                className="rounded-md border border-paper-line px-3 py-2 text-left font-bold text-ink hover:bg-paper disabled:opacity-40 aria-pressed:border-accent aria-pressed:bg-accent/10"
                onClick={() => setDraft(d => ({...d, playbook_hypothesis: s.id}))}>{s.title}</button>)}
            </div>
            <p className="mt-2 text-xs text-ink-muted">Use compatible Addiction KB knowledge sources selected in step 1. A skill guides the agent; it does not select a knowledge source or guarantee better AUC.</p>
          </aside>}
          <label className="block space-y-2 text-sm font-medium">{labels[step]} skill
            <select aria-label={`${labels[step]} skill`} required className={`${field} ${addictionSkills.has(skill?.id ?? '') ? 'font-bold' : 'font-normal'}`} value={skill?.id ?? ''} disabled={loading || busy || uploading} onChange={e => {
              const chosen = catalog.find(c => c.stage === stage && c.id === e.target.value);
              setDraft(d => ({ ...d, [`playbook_${stage === "report" ? "explanation" : stage}`]: e.target.value,
                evaluation: stage === 'ml' ? { ...d.evaluation, ...chosen?.evaluation } : d.evaluation }));
            }}><option value="" disabled>{loading ? 'Loading skills…' : 'Select a skill'}</option>
              {catalog.filter(s => s.stage === stage).map(s => <option key={s.id} value={s.id} className={addictionSkills.has(s.id) ? 'font-bold' : 'font-normal'}>{s.title}</option>)}
            </select></label>
          {!loading && !catalog.some(s => s.stage === stage) && <div role="alert" className="text-sm">Skills are unavailable. <button type="button" onClick={() => void reload()} className="underline">Try again</button></div>}
          <CustomSkillUpload key={stage} stage={stage} disabled={busy}
            onBusy={setUploading} onSelect={chosen => setDraft(d => ({ ...d, [`playbook_${stage === "report" ? "explanation" : stage}`]: chosen.id,
              evaluation: stage === 'ml' ? { ...d.evaluation, ...chosen.evaluation } : d.evaluation }))} />
          {skill && <div className="rounded-lg border border-paper-line bg-paper-panel p-4 text-sm"><p className={addictionSkills.has(skill.id) ? 'font-bold' : 'font-medium'}>{skill.title}</p><p className="mt-2 text-ink-muted">{skill.description}</p>
            <details className="mt-3"><summary className="cursor-pointer">Read skill instructions</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-sans text-xs">{skill.content}</pre></details></div>}
          {stage === 'ml' && <><AgentReferenceKnowledge /><EvaluationSettings value={draft.evaluation} disabled={busy || loading || uploading} onChange={evaluation=>setDraft(d=>({...d,evaluation}))}/>
            <p className="text-xs text-ink-muted">Selecting another ML skill may apply its evaluation defaults. Review these settings after changing or uploading a skill.</p>
            <BaselineSettings value={draft.baseline_columns ?? []} onChange={value=>setDraft(d=>({...d, baseline_columns:value}))}/></>}
        </>}
        {step === 7 && <><p className="text-sm text-ink-muted">Review your pipeline. Each loop builds on earlier results and interpretations. The first loop starts from knowledge. After creation, press Play when you are ready.</p>
          <div className="rounded-lg border border-paper-line bg-paper-panel p-3 text-sm" aria-label="ML settings review">
            <p className="font-semibold">ML evaluation settings</p>
            <p className="mt-1 text-ink-muted">Model: {draft.evaluation.engine} · seed: {draft.evaluation.seed} · hold-out: {Number((draft.evaluation.test_size*100).toFixed(8))}% · training CV: {draft.evaluation.folds || (draft.evaluation.search_trials > 1 ? 'automatic (3 folds requested)' : 'off')} · split evaluations: {draft.evaluation.replicates} · candidates: {draft.evaluation.search_trials}</p>
            {!validModel && <p role="alert">{evaluationPlanError(draft.evaluation)}</p>}
            <button type="button" className="mt-2 underline" onClick={()=>setStep(3)}>Edit ML settings</button>
          </div>
          <LoopLimitSettings value={draft.waves} disabled={busy} onChange={value=>setDraft(d=>({...d,waves:value,continuous:false}))}/>
          <div className="divide-y divide-paper-line rounded-lg border border-paper-line px-4">
            <div className="flex items-start justify-between gap-3 py-3"><div><p className="text-xs text-ink-muted">Knowledge sources</p><p className="text-sm">{sourceLabel}</p></div><button type="button" className="text-sm underline" onClick={() => setStep(0)}>Edit</button></div>
            <div className="py-3"><p className="text-xs text-ink-muted">Pipeline name</p><p className="font-medium">{name.trim()}</p></div>
            <p className="text-sm">Fixed clinical baseline: {draft.baseline_columns?.join(" · ") || "None — hypothesis-selected predictors only"}</p>
            {setupStages.map((s, index) => <div key={s} className="flex items-start justify-between gap-3 py-3"><div className="min-w-0"><p className="text-xs text-ink-muted">{labels[index + 1]}</p><p className="text-sm">{catalog.find(c => c.stage === s && c.id === draft[`playbook_${s === "report" ? "explanation" : s}`])?.title || 'Select a skill'}{s === 'ml' && ` · ${draft.evaluation.engine}`}</p></div><button type="button" className="shrink-0 text-sm underline" onClick={() => setStep(index + 1)}>Edit</button></div>)}
          </div><p className="text-xs text-ink-muted">This pipeline uses the knowledge sources you confirmed above. Dataset settings are carried over from the current configuration. Data extraction uses the Data skill selected above. Each pipeline has one agent per stage.</p></>}
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      </div>
      <footer className="pipeline-creation-footer flex flex-wrap items-center justify-between gap-3 border-t border-paper-line">
        <button type="button" disabled={busy || uploading} onClick={closeCreation} className="rounded-lg px-3 py-2 text-sm disabled:opacity-40">Cancel</button>
        <div className="flex gap-2">{step > 0 && <button type="button" disabled={busy || uploading} onClick={() => setStep(step - 1)} className="flex items-center gap-1 rounded-lg border border-paper-line px-3 py-2 text-sm"><ArrowLeft size={16}/>Back</button>}
          <button type="submit" disabled={!valid || busy || loading || uploading} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-contrast disabled:opacity-40">{busy ? 'Creating…' : step === 7 ? 'Create pipeline' : 'Next'}{step === 7 ? <Check size={16}/> : <ArrowRight size={16}/>}</button></div>
      </footer>
    </form>
  </dialog>;
}
