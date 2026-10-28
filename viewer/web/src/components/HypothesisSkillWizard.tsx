import { useEffect, useId, useRef, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { useControl, type SkillInfo } from '../store/control';
import './hypothesis-skill-wizard.css';

type Stage = 'hypothesis' | 'data' | 'ml' | 'interpreter' | 'report';
const roleNames: Record<Stage, string> = {hypothesis:'Hypothesis', data:'Data', ml:'Machine Learning', interpreter:'Interpretation', report:'Explanation'};
const roleQuestions: Record<Stage, [string, string]> = {
 hypothesis: ['What clinical features do you think will be most predictive of the outcome variable?', 'Are there any variables, topics, assumptions, or types of hypotheses the agent should include or exclude?'],
 data: ['Which feature concepts and column-mapping checks should the agent focus on?', 'Which extraction constraints or mapping ambiguities should the agent report?'],
 ml: ['Which model-evaluation metrics and scientific checks should the agent emphasize?', 'Which evaluation requirements or limitations should be highlighted within the configured settings?'],
 interpreter: ['Which measured results should the agent explain to clinicians?', 'Which uncertainty, limitations, and unsupported interpretations must it clearly identify?'],
 report: ['Which clinical or biological meanings and possible next research steps should it explain?', 'Which boundaries and further-validation labels should guide its explanations and suggestions?'],
};
type Props = { modelConnectionId?: string; stage?: Stage; disabled?: boolean; multiple?: boolean; onSelect: (skill: SkillInfo) => void; onBusy: (busy: boolean) => void };
const questions = [
  ['domain', 'What is your clinical domain of expertise?', 'e.g. Addiction medicine'],
  ['population', 'What patient population or clinical setting do you want to study?', 'e.g. Adults receiving outpatient HIV care'],
  ['features', 'What clinical features do you think will be most predictive of the outcome variable?', 'Describe candidate features; these are hypotheses, not established predictors.'],
  ['constraints', 'Are there any variables, topics, assumptions, or types of hypotheses the agent should include or exclude?', 'Describe your preferences, or enter None.'],
] as const;

async function request(url: string, body?: object) {
  const response = await fetch(url, { ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(10000) });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Request failed. Please retry.');
  return data;
}

export default function HypothesisSkillWizard({ stage = 'hypothesis', modelConnectionId, disabled, multiple, onSelect, onBusy }: Props) {
  const role = roleNames[stage];
  const modelListId = useId();
  const prompts = questions.map(([key, label, placeholder]) => [key, key==='features' ? roleQuestions[stage][0] : key==='constraints' ? roleQuestions[stage][1] : label, stage!=='hypothesis' && key==='features' ? 'Describe your priorities for this agent.' : placeholder]);
  const [open, setOpen] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({domain:'', population:'', features:'', constraints:''});
  const [connectionId, setConnectionId] = useState('');
  const [baseSkill, setBaseSkill] = useState(stage === 'data' ? 'data_training_heavy' : stage === 'ml' ? 'ml_logistic_regression' : '');
  const [model, setModel] = useState('');
  const [provider, setProvider] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [name, setName] = useState('');
  const [job, setJob] = useState('');
  const [origin, setOrigin] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function loadModels() {
    setError(''); setLoadingModels(true); setProvider(''); setModel('');
    try {
      const data = await request('/control/skill-drafts/models' + (modelConnectionId ? `?model_connection_id=${encodeURIComponent(modelConnectionId)}` : ''));
      if (!mounted.current) return;
      setConnectionId(data.model_connection_id || '');
      const role = stage === 'interpreter' ? 'interpretation' : stage === 'report' ? 'explanation' : stage;
      const profile = data.agents?.[role];
      if (!profile?.model || !profile?.provider) throw Error('Agent model is not configured.');
      setProvider(profile.provider); setModels([profile.model]); setModel(profile.model);
    }
    catch { setError('Could not load the model connection. Reopen this assistant to retry.'); }
    finally { if (mounted.current) setLoadingModels(false); }
  }
  async function generate(resume = false) {
    setBusy(true); onBusy(true); setError(''); setSaved(false);
    try {
      const id = resume ? job : (await request('/control/skill-drafts', {stage, ...answers, model, model_connection_id: connectionId, ...(baseSkill ? {base_skill: baseSkill} : {})})).id;
      setJob(id);
      const deadline = Date.now() + 165000;
      while (mounted.current && Date.now() < deadline) {
        const data = await request(`/control/skill-drafts/${id}`);
        if (data.status === 'failed') { setJob(''); throw Error(data.error); }
        if (data.status === 'ready') {
          setDraft(data.content); setOrigin(`${data.provider} · ${data.model}`); setReviewed(false); setJob('');
          if (!name) setName(`${stage}-${Date.now().toString(36)}`);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
      throw Error('Still waiting for the draft. Check generation status to retrieve it without another model call.');
    } catch(e) { if (mounted.current) setError(e instanceof Error ? e.message : 'Generation failed. Please retry.'); }
    finally { if (mounted.current) { setBusy(false); onBusy(false); } }
  }
  async function save() {
    setBusy(true); onBusy(true); setError('');
    try {
      const skill: SkillInfo = await request('/control/playbooks', {stage, name:name.trim(), content:draft, ...(baseSkill ? {base_skill: baseSkill} : {})});
      if (!skill.id || skill.stage !== stage) throw Error('The saved skill could not be verified.');
      useControl.setState(s => ({catalog:[...s.catalog.filter(c => c.id !== skill.id), skill], playbooks:[...new Set([...(s.playbooks ?? []), skill.id])]}));
      onSelect(skill); setSaved(true);
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not save the skill.'); }
    finally { setBusy(false); onBusy(false); }
  }
  const locked = busy || loadingModels || !!disabled;
  return <section className="hypothesis-skill-wizard" aria-label={`AI ${role} skill assistant`}>
    <button type="button" className="skill-assistant-trigger" aria-expanded={open} disabled={locked} onClick={() => {setOpen(!open); if (!open) void loadModels();}}><Sparkles size={17} aria-hidden="true"/> Create a skill with AI</button>
    {open && <div className="skill-assistant-body">
      <p>Turn your clinical expertise into {role} Agent instructions. {multiple ? 'Save a skill, then create another to add different perspectives to your combinations.' : `The saved skill replaces the ${role} skill selected for this pipeline draft.`}</p>
      <p className="text-xs text-ink-muted">Use general research context, not patient details. Generation uses model tokens. It does not run a pipeline.</p>
      {loadingModels && <p role="status">Loading the model connection…</p>}
      <fieldset disabled={locked}>
        <legend>1. Describe your research perspective</legend>
        {baseSkill && <label>{stage === 'data' ? 'Data split for this skill' : 'ML algorithm for this skill'}<select value={baseSkill} disabled={!!job} onChange={e => {setBaseSkill(e.target.value);setDraft('');setReviewed(false);setSaved(false);}}>
          {stage === 'data' ? <><option value="data_training_heavy">70% training / 30% test</option><option value="data_balanced_stratified">50% training / 50% test</option></> : <><option value="ml_logistic_regression">Logistic regression</option><option value="ml_xgboost">XGBoost</option></>}
        </select><span className="text-xs text-ink-muted">Saved with the skill and applied when the pipeline runs.</span></label>}
        {prompts.map(([key, label, placeholder]) => <label key={key}>{label}<textarea rows={2} maxLength={4000} value={answers[key]} placeholder={placeholder} onChange={e => setAnswers(a => ({...a, [key]:e.target.value}))}/></label>)}
        <label>Generation model / deployment<input list={modelListId} value={model} readOnly maxLength={160}/></label>
        <datalist id={modelListId}>{models.map(m => <option key={m} value={m}/>)}</datalist>
        <p className="text-xs text-ink-muted">Connection: {provider || 'Not loaded'}. Uses the model selected for this experiment, or your saved model defaults.</p>
      </fieldset>
      {job ? <button type="button" disabled={locked} onClick={() => void generate(true)}>Check generation status</button> : <button type="button" disabled={locked || !provider || !model.trim() || questions.some(([key]) => !answers[key].trim())} onClick={() => void generate()}>{draft ? 'Generate a new draft' : 'Generate skill draft'}</button>}
      {busy && <p role="status">Working… Your answers and existing draft are retained.</p>}
      {draft && <fieldset disabled={locked}>
        <legend>2. Review and edit before saving</legend>
        <p className="text-xs text-ink-muted">AI-generated draft · {origin}. Review clinical scope, assumptions, and exclusions. No skill is applied until you save.</p>
        <label>Generated skill name<input value={name} maxLength={60} onChange={e => {setName(e.target.value);setSaved(false);}}/></label>
        <label>Generated Markdown skill<textarea rows={12} value={draft} onChange={e => {setDraft(e.target.value);setReviewed(false);setSaved(false);}}/></label>
        <label className="skill-review-check"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)}/>I reviewed these instructions and want to use this skill.</label>
        <button type="button" disabled={!reviewed || !/^[A-Za-z0-9_-]{1,60}$/.test(name.trim()) || !draft.trim() || saved} onClick={() => void save()}>{multiple ? 'Save and add to combinations' : 'Save and select for this pipeline'}</button>
      </fieldset>}
      {saved && <div role="status"><p>Saved and selected. Finish the pipeline review when ready.</p>{multiple && <button type="button" onClick={() => {setDraft('');setName('');setSaved(false);setReviewed(false);}}>Create another {role} skill</button>}</div>}
      {error && <p role="alert">{error}</p>}
    </div>}
  </section>;
}
