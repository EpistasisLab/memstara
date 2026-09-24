import { useEffect, useRef, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { useControl, type SkillInfo } from '../store/control';
import './hypothesis-skill-wizard.css';

type Props = { disabled?: boolean; multiple?: boolean; onSelect: (skill: SkillInfo) => void; onBusy: (busy: boolean) => void };
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

export default function HypothesisSkillWizard({ disabled, multiple, onSelect, onBusy }: Props) {
  const [open, setOpen] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({domain:'', population:'', features:'', constraints:''});
  const [model, setModel] = useState('');
  const [provider, setProvider] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [name, setName] = useState('');
  const [job, setJob] = useState('');
  const [origin, setOrigin] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function loadModels() {
    setError('');
    try { const data = await request('/control/skill-drafts/models'); setProvider(data.provider); setModels(data.models); setModel(data.default_model); }
    catch { setError('Could not load the model connection. Reopen this assistant to retry.'); }
  }
  async function generate(resume = false) {
    setBusy(true); onBusy(true); setError(''); setSaved(false);
    try {
      const id = resume ? job : (await request('/control/skill-drafts', {stage:'hypothesis', ...answers, model})).id;
      setJob(id);
      const deadline = Date.now() + 165000;
      while (mounted.current && Date.now() < deadline) {
        const data = await request(`/control/skill-drafts/${id}`);
        if (data.status === 'failed') { setJob(''); throw Error(data.error); }
        if (data.status === 'ready') {
          setDraft(data.content); setOrigin(`${data.provider} · ${data.model}`); setReviewed(false); setJob('');
          if (!name) setName(`hypothesis-${Date.now().toString(36)}`);
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
      const skill: SkillInfo = await request('/control/playbooks', {stage:'hypothesis', name:name.trim(), content:draft});
      if (!skill.id || skill.stage !== 'hypothesis') throw Error('The saved skill could not be verified.');
      useControl.setState(s => ({catalog:[...s.catalog.filter(c => c.id !== skill.id), skill], playbooks:[...new Set([...(s.playbooks ?? []), skill.id])]}));
      onSelect(skill); setSaved(true);
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not save the skill.'); }
    finally { setBusy(false); onBusy(false); }
  }
  const locked = busy || !!disabled;
  return <section className="hypothesis-skill-wizard" aria-label="AI Hypothesis skill assistant">
    <button type="button" className="skill-assistant-trigger" aria-expanded={open} disabled={locked} onClick={() => {setOpen(!open); if (!open) void loadModels();}}><Sparkles size={17} aria-hidden="true"/> Create a skill with AI</button>
    {open && <div className="skill-assistant-body">
      <p>Turn your clinical expertise into Hypothesis Agent instructions. {multiple ? 'Save a skill, then create another to add different perspectives to your combinations.' : 'The saved skill replaces the Hypothesis skill selected for this pipeline draft.'}</p>
      <p className="text-xs text-ink-muted">Use general research context, not patient details. Generation uses model tokens. It does not run a pipeline.</p>
      <fieldset disabled={locked}>
        <legend>1. Describe your research perspective</legend>
        {questions.map(([key, label, placeholder]) => <label key={key}>{label}<textarea rows={2} maxLength={4000} value={answers[key]} placeholder={placeholder} onChange={e => setAnswers(a => ({...a, [key]:e.target.value}))}/></label>)}
        <label>Generation model / deployment<input list="hypothesis-draft-models" value={model} onChange={e => setModel(e.target.value)} maxLength={160}/></label>
        <datalist id="hypothesis-draft-models">{models.map(m => <option key={m} value={m}/>)}</datalist>
        <p className="text-xs text-ink-muted">Connection: {provider || 'Not loaded'}. Select the configured model or enter another deployment available on this connection. This does not change your pipeline model.</p>
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
      {saved && <div role="status"><p>Saved and selected. Finish the pipeline review when ready.</p>{multiple && <button type="button" onClick={() => {setDraft('');setName('');setSaved(false);setReviewed(false);}}>Create another Hypothesis skill</button>}</div>}
      {error && <p role="alert">{error}</p>}
    </div>}
  </section>;
}
