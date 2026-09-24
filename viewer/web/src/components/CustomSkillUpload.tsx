import HypothesisSkillWizard from './HypothesisSkillWizard';
import CreateCustomSkill from './CreateCustomSkill';
import { useRef, useState } from 'react';
import { Upload, FileText } from 'lucide-react';
import { useControl, type SkillInfo } from '../store/control';

type Props = {
  stage: 'hypothesis' | 'data' | 'ml' | 'interpreter' | 'report';
  disabled?: boolean;
  multiple?: boolean;
  onSelect: (skill: SkillInfo) => void;
  onBusy: (busy: boolean) => void;
};

/** Register a role-scoped skill; the parent owns its uncommitted selection. */
export default function CustomSkillUpload({ stage, disabled, multiple = false, onSelect, onBusy }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [writing, setWriting] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [filename, setFilename] = useState('');
  const [error, setError] = useState('');
  const upload = async (files: File[]) => {
    if (!files.length || uploading || writing || drafting || disabled) return;
    setUploading(true); onBusy(true); setError(''); setFilename('');
    const uploaded: string[] = [];
    const failures: string[] = [];
    try {
     for (const file of multiple ? files : files.slice(0, 1)) {
      try {
      if (!/\.md$/i.test(file.name)) throw new Error('Choose a Markdown (.md) file.');
      if (!file.size || file.size > 48000) throw new Error('Choose a non-empty Markdown file up to 48 kB.');
      let content: string;
      try { content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); }
      catch { throw new Error('Save your Markdown file as UTF-8 and try again.'); }
      if (!content.trim() || content.includes('\0')) throw new Error('The file must contain Markdown instructions.');
      const response = await fetch('/control/playbooks', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(15000),
        body: JSON.stringify({ stage, content,
          name: file.name.replace(/\.md$/i, '').replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 60) || 'custom-skill' }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || 'Upload failed. Please try again.');
      }
      const skill: SkillInfo = await response.json();
      if (!skill.id || skill.stage !== stage) throw new Error('The uploaded skill could not be verified. Please try again.');
      useControl.setState(s => ({ catalog: [...s.catalog.filter(c => c.id !== skill.id), skill],
        playbooks: [...new Set([...(s.playbooks ?? []), skill.id])] }));
      onSelect(skill); uploaded.push(file.name);
      } catch (e) {
        failures.push(`${file.name}: ${e instanceof Error ? e.message : 'Upload failed. Please try again.'}`);
      }
     }
     setFilename(uploaded.join(', '));
     setError(failures.join(' '));
    } finally {
      setUploading(false); onBusy(false);
      if (input.current) input.current.value = '';
    }
  };
  return <section className="rounded-lg border border-paper-line p-3 text-sm" aria-label="Upload a custom skill" aria-busy={uploading || writing || drafting}>
    <h4 className="font-medium">Or use your own skill</h4>
    <p className="mt-1 text-xs leading-relaxed text-ink-muted">{multiple ? 'Select one or more skill files for this agent. Each successful upload is added to the combination set. ' : 'Upload instructions for this agent, then review them below. '}UTF-8 Markdown (.md), up to 48 kB per file.</p>
    <input ref={input} type="file" accept=".md" multiple={multiple} className="hidden" aria-label="Custom skill Markdown file"
      disabled={disabled || uploading || writing || drafting} onChange={event => void upload(Array.from(event.target.files ?? []))} />
    <button type="button" disabled={disabled || uploading || writing || drafting} onClick={() => input.current?.click()}
      className="mt-3 inline-flex max-w-full items-center gap-2 rounded-lg border border-paper-line bg-white px-3 py-2 font-medium hover:bg-paper-panel focus-visible:outline focus-visible:outline-2 disabled:opacity-40">
      <Upload size={16} className="shrink-0" aria-hidden="true" />{uploading ? 'Uploading…' : multiple ? 'Upload skills (.md)' : 'Upload skill (.md)'}
    </button>
    <div aria-live="polite">{filename && <p className="mt-2 flex items-start gap-2 text-xs text-ink-muted">
      <FileText size={16} className="shrink-0" aria-hidden="true" /><span className="min-w-0 break-words">{filename} · Uploaded to your skill library.</span>
    </p>}</div>
    <p className="mt-2 text-xs text-ink-muted">The file is saved in your skill library. This pipeline is created only after you finish the review.</p>
    <CreateCustomSkill stage={stage} disabled={disabled || uploading || writing || drafting} onSelect={onSelect} onBusy={value=>{setWriting(value);onBusy(value);}} />
    {stage === 'hypothesis' && <HypothesisSkillWizard disabled={disabled || uploading || writing} multiple={multiple} onSelect={onSelect} onBusy={value=>{setDrafting(value);onBusy(value);}} />}
    {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
  </section>;
}
