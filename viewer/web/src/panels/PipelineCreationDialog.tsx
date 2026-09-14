import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, X } from 'lucide-react';
import { useControl, type RunRequest } from '../store/control';
import { usePipelines } from '../store/pipelines';
import { setupStages } from '../store/pipelineSetup';

const labels = ['Name', 'Hypothesis', 'Machine learning', 'Interpretation', 'Report', 'Review'];
const guidance = {
  hypothesis: 'Choose how this agent uses knowledge to generate hypotheses and select features.',
  ml: 'Choose the model and the skill that guides how experiments are evaluated.',
  interpreter: 'Choose how measured results are explained, including clinical meaning and limitations.',
  report: 'Choose how findings are compared and useful hypotheses are recommended.',
};
const field = 'w-full rounded-lg border border-paper-line bg-white px-3 py-2 text-sm text-ink';

export default function PipelineCreationDialog() {
  const open = usePipelines(s => s.creationOpen);
  return open ? <CreationWizard /> : null;
}

function CreationWizard() {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [draft, setDraft] = useState<RunRequest>(() => {
    const form = structuredClone(useControl.getState().form);
    return { ...form, question: '', hypothesis_agents: 1, interpret_agents: 1,
      trials: 1, waves: 1, continuous: true,
      playbook_hypothesis: form.playbook_hypothesis.split(',')[0],
      playbook_interpreter: form.playbook_interpreter.split(',')[0] };
  });
  const catalog = useControl(s => s.catalog);
  const { busy, error, closeCreation, create, items } = usePipelines();
  const [loading, setLoading] = useState(true);
  const reload = async () => {
    setLoading(true);
    await useControl.getState().loadPlaybooks();
    setLoading(false);
  };
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    let mounted = true;
    void useControl.getState().loadPlaybooks().then(() => { if(mounted)setLoading(false); });
    return () => { mounted = false; element?.close(); };
  }, []);
  useEffect(() => { if(step > 0) heading.current?.focus(); }, [step]);
  const stage = step > 0 && step < 5 ? setupStages[step - 1] : null;
  const skill = stage ? catalog.find(s => s.stage === stage && s.id === draft[`playbook_${stage}`]) : null;
  const complete = setupStages.every(s => catalog.some(c => c.stage === s && c.id === draft[`playbook_${s}`]));
  const validName = Boolean(name.trim()) && name.length <= 80;
  const validModel = ['xgboost', 'random_forest', 'logistic_regression'].includes(draft.evaluation.engine);
  const valid = step === 0 ? validName : step === 5 ? validName && complete && validModel : Boolean(skill) && (stage !== 'ml' || validModel);
  return <dialog ref={dialog} aria-labelledby="pipeline-create-title" aria-describedby="pipeline-create-description"
    onCancel={event => { event.preventDefault(); closeCreation(); }}
    onKeyDown={event => {
      if(event.key !== 'Tab') return;
      const targets = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]')]
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
        <p id="pipeline-create-description" className="mt-1 text-sm text-ink-muted">Set up each agent here, then review and create.</p></div>
      <button type="button" aria-label="Cancel pipeline setup" disabled={busy} onClick={closeCreation} className="rounded p-2 hover:bg-paper-panel disabled:opacity-40"><X size={20} /></button>
    </header>
    <ol aria-label="Setup progress" className="pipeline-creation-progress">
      {labels.map((label, index) => <li key={label} aria-current={index === step ? 'step' : undefined} title={label}
        className={index <= step ? 'is-reached' : ''}><span className="pipeline-creation-step-number">{index < step ? <Check size={14} aria-label="Completed"/> : index + 1}</span><span>{label}</span></li>)}
    </ol>
    <form className="pipeline-creation-form" onSubmit={async event => { event.preventDefault(); if(!valid || busy || loading)return; if(step < 5)setStep(step + 1); else await create(name.trim(), draft); }}>
      <div className="pipeline-creation-body space-y-4">
        <h3 ref={heading} tabIndex={-1} className="text-lg font-semibold">{step + 1}. {labels[step]} <span className="text-xs font-normal text-ink-muted">· Step {step + 1} of 6</span></h3>
        {step === 0 && <><p className="text-sm text-ink-muted">Give this pipeline a recognizable name. Next, review the skill for each agent before creating it.</p>
          <label className="block space-y-2 text-sm font-medium">Pipeline name
            <input autoFocus required maxLength={80} className={field} placeholder="e.g. Treatment-related effects" value={name} onChange={e => setName(e.target.value)} /></label>
          <p className="text-xs text-ink-muted">Settings remain a draft until you choose Create pipeline.</p></>}
        {stage && <><p className="text-sm text-ink-muted">{guidance[stage]}</p>
          <label className="block space-y-2 text-sm font-medium">{labels[step]} skill
            <select aria-label={`${labels[step]} skill`} required className={field} value={skill?.id ?? ''} disabled={loading || busy} onChange={e => {
              const chosen = catalog.find(c => c.stage === stage && c.id === e.target.value);
              setDraft(d => ({ ...d, [`playbook_${stage}`]: e.target.value,
                evaluation: stage === 'ml' ? { ...d.evaluation, ...chosen?.evaluation } : d.evaluation }));
            }}><option value="" disabled>{loading ? 'Loading skills…' : 'Select a skill'}</option>
              {catalog.filter(s => s.stage === stage).map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
            </select></label>
          {!loading && !catalog.some(s => s.stage === stage) && <div role="alert" className="text-sm">Skills are unavailable. <button type="button" onClick={() => void reload()} className="underline">Try again</button></div>}
          {skill && <div className="rounded-lg border border-paper-line bg-paper-panel p-4 text-sm"><p className="font-medium">{skill.title}</p><p className="mt-2 text-ink-muted">{skill.description}</p>
            <details className="mt-3"><summary className="cursor-pointer">Read skill instructions</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-sans text-xs">{skill.content}</pre></details></div>}
          {stage === 'ml' && <><label className="block space-y-2 text-sm font-medium">ML model<select aria-label="ML model" className={field} value={draft.evaluation.engine} onChange={e => setDraft(d => ({...d, evaluation: {...d.evaluation, engine: e.target.value}}))}>
            <option value="xgboost">XGBoost</option><option value="random_forest">Random forest</option><option value="logistic_regression">Logistic regression</option></select></label>
            <p className="text-xs text-ink-muted">Evaluation settings: seed {draft.evaluation.seed} · {Math.round(draft.evaluation.test_size * 100)}% test data · {draft.evaluation.folds || 'No'} cross-validation folds · {draft.evaluation.replicates} replicate(s) · {draft.evaluation.search_trials} search trial(s). Selected skill defaults are applied.</p></>}
        </>}
        {step === 5 && <><p className="text-sm text-ink-muted">Review your pipeline. After creation, press Play when you are ready to begin.</p>
          <dl className="divide-y divide-paper-line rounded-lg border border-paper-line px-4">
            <div className="py-3"><dt className="text-xs text-ink-muted">Pipeline name</dt><dd className="font-medium">{name.trim()}</dd></div>
            {setupStages.map((s, index) => <div key={s} className="flex items-start justify-between gap-3 py-3"><div className="min-w-0"><dt className="text-xs text-ink-muted">{labels[index + 1]}</dt><dd className="text-sm">{catalog.find(c => c.stage === s && c.id === draft[`playbook_${s}`])?.title || 'Select a skill'}{s === 'ml' && ` · ${draft.evaluation.engine}`}</dd></div><button type="button" className="shrink-0 text-sm underline" onClick={() => setStep(index + 1)}>Edit</button></div>)}
          </dl><p className="text-xs text-ink-muted">Knowledge sources and dataset settings are carried over from the current configuration. Data extraction uses the existing data agent settings. Each pipeline has one agent per stage.</p></>}
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        {items.length >= 3 && <p role="alert" className="text-sm">Three pipelines already exist. Close setup and remove a pipeline before adding another.</p>}
      </div>
      <footer className="pipeline-creation-footer flex flex-wrap items-center justify-between gap-3 border-t border-paper-line">
        <button type="button" disabled={busy} onClick={closeCreation} className="rounded-lg px-3 py-2 text-sm disabled:opacity-40">Cancel</button>
        <div className="flex gap-2">{step > 0 && <button type="button" disabled={busy} onClick={() => setStep(step - 1)} className="flex items-center gap-1 rounded-lg border border-paper-line px-3 py-2 text-sm"><ArrowLeft size={16}/>Back</button>}
          <button type="submit" disabled={!valid || busy || loading || items.length >= 3} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-contrast disabled:opacity-40">{busy ? 'Creating…' : step === 5 ? 'Create pipeline' : 'Next'}{step === 5 ? <Check size={16}/> : <ArrowRight size={16}/>}</button></div>
      </footer>
    </form>
  </dialog>;
}
