import {lazy, Suspense, useEffect, useRef, useState} from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import {useControl, type SkillInfo} from '../store/control';
import {skillLabel} from '../lib/displayText';
import {tileSkillStages, type SkillConfiguration, type TileSkill} from '../lib/tileSkills';
import type {Result} from '../types';
import './output-skill-flow.css';

const SkillMarkdown = lazy(() => import('./SkillMarkdown'));
type SavedInstructions = {run_tag: string; stage: string; id: string; hash?: string; content: string};
const savedCache = new Map<string, SavedInstructions>();

function SkillDescription({skill, stage, runTag, current, issue}: {
  skill: TileSkill; stage: string; runTag: string; current?: SkillInfo; issue: string;
}) {
  const key = JSON.stringify([runTag, stage, skill.id, skill.hash]);
  const matching = !issue && !!skill.hash && current?.hash === skill.hash && current.stage === stage;
  const [saved, setSaved] = useState<SavedInstructions | undefined>(() => savedCache.get(key));
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (matching || issue || saved) return;
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => controller.abort(), 10000);
    const query = new URLSearchParams({stage, skill: skill.id, ...(skill.hash ? {hash: skill.hash} : {})});
    void (async () => {
      try {
        const response = await fetch(`/control/runs/${encodeURIComponent(runTag)}/skill-instructions?${query}`, {signal: controller.signal});
        if (!response.ok) throw Error('Recorded skill instructions are unavailable. Current instructions have not been substituted.');
        const data: SavedInstructions = await response.json();
        if (data.run_tag !== runTag || data.stage !== stage || data.id !== skill.id
            || (skill.hash && data.hash !== skill.hash) || typeof data.content !== 'string' || !data.content.trim()) {
          throw Error('The returned instructions do not match this recorded skill.');
        }
        if (active) {
          savedCache.set(key, data);
          while (savedCache.size > 32) savedCache.delete(savedCache.keys().next().value!);
          setSaved(data);
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error && cause.name === 'AbortError'
          ? 'Recorded instructions did not respond in time.' : cause instanceof Error ? cause.message : 'Could not read recorded instructions.');
      } finally {clearTimeout(timer);}
    })();
    return () => {active = false; clearTimeout(timer); controller.abort();};
  }, [key, matching, issue, saved, runTag, stage, skill.id, skill.hash, attempt]);
  if (issue) return <p role="status">{issue} Current instructions have not been substituted.</p>;
  if (matching) return <>
    <p className="output-skill-description">{current.description || 'No short description was recorded.'}</p>
    <p className="output-skill-source">Library content matches the recorded version hash.</p>
    <details><summary>Read full skill instructions</summary><Suspense fallback={<p>Loading instructions…</p>}><SkillMarkdown content={current.content}/></Suspense></details>
  </>;
  if (saved) return <>
    <p className="output-skill-source">Saved skill and surrounding agent instructions for this execution.</p>
    <Suspense fallback={<p>Loading instructions…</p>}><SkillMarkdown content={saved.content}/></Suspense>
  </>;
  return error ? <p role="status">{error} <button type="button" onClick={() => {setError(''); setAttempt(n => n + 1);}}>Retry</button></p>
    : <p role="status">Loading recorded skill instructions…</p>;
}

function SelectedSkill({skill, stage, runTag, provenance, current, issue}: {
  skill: TileSkill; stage: ReturnType<typeof tileSkillStages>[number]; runTag: string;
  provenance: string; current?: SkillInfo; issue: string;
}) {
  const [open, setOpen] = useState(false);
  const focusFrame = useRef<number | undefined>(undefined);
  const trigger = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  useEffect(() => () => {if (focusFrame.current !== undefined) cancelAnimationFrame(focusFrame.current);}, []);
  const label = skillLabel(skill.id, skill.title);
  return <Tooltip.Root open={open} onOpenChange={setOpen} delayDuration={180} disableHoverableContent={false}>
    <Tooltip.Trigger asChild>
      <button ref={trigger} type="button" className="output-skill-dot is-selected" data-context-help-managed
        aria-label={`${stage.label}: ${label}. Selected skill. Show instructions.`}
        onFocus={event => {
          // Let keyboard focus finish scrolling the card into view before opening;
          // Radix dismisses tooltips when an ancestor scrolls.
          event.preventDefault();
          const target = event.currentTarget;
          focusFrame.current = requestAnimationFrame(() => {
            if (document.activeElement === target) setOpen(true);
          });
        }}
        onBlur={event => {
          if (focusFrame.current !== undefined) cancelAnimationFrame(focusFrame.current);
          if (event.relatedTarget instanceof Node && popup.current?.contains(event.relatedTarget)) event.preventDefault();
        }}
        onClick={event => {event.preventDefault(); event.stopPropagation(); setOpen(value => !value);}}>
        <span aria-hidden="true"/>
      </button>
    </Tooltip.Trigger>
    <Tooltip.Portal>
      <Tooltip.Content ref={popup} className="output-skill-popup" side="bottom" align="start" sideOffset={8}
        collisionPadding={12} hideWhenDetached onClick={event => event.stopPropagation()}
        onBlur={event => {
          if (!event.currentTarget.contains(event.relatedTarget) && event.relatedTarget !== trigger.current) setOpen(false);
        }}>
        <header><span>{stage.label} agent · Selected skill</span><strong>{label}</strong></header>
        <p className="output-skill-source">{provenance}</p>
        {open && <SkillDescription key={JSON.stringify([runTag, stage.id, skill.id, skill.hash])}
          skill={skill} stage={stage.id} runTag={runTag} current={current} issue={issue}/>}
        <footer>Skill ID: {skill.id}{skill.hash && <><br/>Version: {skill.hash}</>}</footer>
      </Tooltip.Content>
    </Tooltip.Portal>
  </Tooltip.Root>;
}

function AgentRole({stage}: {stage: ReturnType<typeof tileSkillStages>[number]}) {
  const [open, setOpen] = useState(false);
  const focusFrame = useRef<number | undefined>(undefined);
  useEffect(() => () => {if (focusFrame.current !== undefined) cancelAnimationFrame(focusFrame.current);}, []);
  return <Tooltip.Root open={open} onOpenChange={setOpen} delayDuration={180}>
    <Tooltip.Trigger asChild>
      <button type="button" className="output-skill-stage-label" data-context-help-managed
        aria-label={`${stage.label} agent. Show role description.`}
        onFocus={event => {
          event.preventDefault();
          const target = event.currentTarget;
          focusFrame.current = requestAnimationFrame(() => {
            if (document.activeElement === target) setOpen(true);
          });
        }}
        onBlur={() => {if (focusFrame.current !== undefined) cancelAnimationFrame(focusFrame.current); setOpen(false);}}
        onClick={event => {event.stopPropagation(); setOpen(value => !value);}}>{stage.short}</button>
    </Tooltip.Trigger>
    <Tooltip.Portal>
      <Tooltip.Content className="output-agent-role-popup" side="bottom" sideOffset={6} collisionPadding={12}
        onClick={event => event.stopPropagation()}>
        <strong>{stage.label} agent</strong><p>{stage.description}</p>
      </Tooltip.Content>
    </Tooltip.Portal>
  </Tooltip.Root>;
}

export default function OutputSkillFlow({config, loop, results, runTag}: {
  config?: SkillConfiguration; loop: number; results: Result[]; runTag: string;
}) {
  const catalog = useControl(state => state.catalog);
  const stages = tileSkillStages(config, loop, results);
  return <section className="output-skill-flow" aria-label="Recorded agent skill selection">
    <div className="output-skill-stages">
      {stages.map(stage => <div className="output-skill-stage" key={stage.id}>
        <div className="output-skill-options">
          {stage.options.map((skill, index) => stage.selected?.id === skill.id
            ? <SelectedSkill key={`${skill.id}:${skill.hash}`} skill={stage.selected} stage={stage} runTag={runTag}
                provenance={stage.provenance} issue={stage.issue} current={catalog.find(item => item.id === skill.id)}/>
            : <span key={`${skill.id}:${index}`} className="output-skill-dot" role="img"
                aria-label={`${stage.label}: ${skillLabel(skill.id, skill.title)}. Not selected.`}
                title={skillLabel(skill.id, skill.title)}><span/></span>)}
          {!stage.selected && <span className="output-skill-unknown" title={stage.issue || 'Skill selection not recorded'}
            aria-label={`${stage.label}: ${stage.issue || 'Skill selection not recorded'}`}>?</span>}
        </div>
        <AgentRole stage={stage}/>
      </div>)}
    </div>
  </section>;
}
