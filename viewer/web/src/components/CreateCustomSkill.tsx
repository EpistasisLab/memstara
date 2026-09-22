import { useState } from 'react';
import { useControl, type SkillInfo } from '../store/control';
import { agentStageLabel } from '../lib/stage';

type Props = { stage: 'hypothesis'|'data'|'ml'|'interpreter'|'report'; disabled?: boolean;
  onSelect: (skill: SkillInfo) => void; onBusy: (busy: boolean) => void };

export default function CreateCustomSkill({stage,disabled,onSelect,onBusy}: Props) {
  const [name,setName]=useState('');
  const [content,setContent]=useState('');
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState('');
  const [saved,setSaved]=useState(false);
  async function save() {
    if(saving||disabled)return;
    setSaving(true);onBusy(true);setError('');setSaved(false);
    try {
      const response=await fetch('/control/playbooks',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({stage,name:name.trim(),content}),signal:AbortSignal.timeout(15000)});
      const skill=await response.json();
      if(!response.ok)throw Error(skill.error||'Could not save this skill.');
      if(!skill.id||skill.stage!==stage)throw Error('The saved skill has an unexpected role.');
      useControl.setState(s=>({catalog:[...s.catalog.filter(c=>c.id!==skill.id),skill],
        playbooks:[...new Set([...(s.playbooks??[]),skill.id])]}));
      onSelect(skill);setSaved(true);
    }catch(e){setError(e instanceof Error?e.message:'Could not save this skill.');}
    finally{setSaving(false);onBusy(false);}
  }
  return <details className="mt-3 rounded-lg border border-paper-line p-3 text-sm">
    <summary className="cursor-pointer font-semibold">Write a custom skill</summary>
    <p className="mt-2 text-xs text-ink-muted">Create instructions for the {agentStageLabel(stage)} agent. Saved to your skill library; review and apply them in the surrounding settings.</p>
    <label className="mt-3 block">Skill name<input aria-label="New skill name" disabled={disabled||saving} value={name} onChange={e=>{setName(e.target.value);setSaved(false);}}
      placeholder="e.g. clinical-observations" maxLength={60} className="mt-1 w-full min-w-0 rounded border border-paper-line bg-paper-panel p-2"/></label>
    <p className="mt-1 text-xs text-ink-muted">Letters, numbers, hyphens and underscores only.</p>
    <label className="mt-3 block">Markdown instructions<textarea aria-label="New skill instructions" disabled={disabled||saving} value={content} onChange={e=>{setContent(e.target.value);setSaved(false);}}
      rows={8} className="mt-1 w-full min-w-0 resize-y rounded border border-paper-line bg-paper-panel p-2"/></label>
    <button type="button" onClick={()=>void save()} disabled={disabled||saving||!name.trim()||!content.trim()}
      className="mt-3 rounded border border-paper-line px-3 py-2 disabled:opacity-40">{saving?'Saving…':'Save and select skill'}</button>
    {saved&&<p role="status" className="mt-2 text-xs">Saved and selected. Apply the agent settings or finish creating the pipeline.</p>}
    {error&&<p role="alert" className="mt-2 text-sm">{error}</p>}
  </details>;
}
