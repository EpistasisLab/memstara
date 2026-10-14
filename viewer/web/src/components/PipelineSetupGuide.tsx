import { ArrowDown, Check, ChevronRight } from 'lucide-react';
import { usePipelines } from '../store/pipelines';
import { useControl } from '../store/control';
import { setupStages, skillSignature, usePipelineSetup } from '../store/pipelineSetup';
import { STAGE_ICON } from '../lib/icons';
import { STAGE_COLOR } from '../lib/stage';

const names = { hypothesis: 'Hypothesis', ml: 'Machine learning', interpreter: 'Interpreter', report: 'Explanation' };
const descriptions = {
  hypothesis: 'Choose how this agent uses knowledge to propose promising hypotheses and select features.',
  ml: 'Review model training, validation and reproducibility instructions, together with the evaluation settings.',
  interpreter: 'Choose SHAP or LIME to describe measured model behavior, attributions and technical limitations.',
  report: 'Choose how the agent explains the Interpretation output using the selected knowledge sources, with follow-up questions and limitations.',
};
export default function PipelineSetupGuide() {
  const { items, selected, busy, error } = usePipelines();
  const { reviews, start, pause, confirm } = usePipelineSetup();
  const catalog = useControl(s => s.catalog);
  const pipeline = items.find(p => p.id === selected);
  if (!pipeline) return null;
  const review = reviews[pipeline.id];
  if (!review) return <div className="px-4 pb-3"><button className="text-sm text-ink-soft underline underline-offset-4" disabled={!!pipeline.running||busy}
    onClick={() => { start(pipeline.id); usePipelines.getState().focus(pipeline.id); }}>Review this pipeline's four agent skills</button></div>;
  const confirmed = setupStages.filter(stage => review.confirmed?.[stage] === skillSignature(pipeline.configuration, stage));
  const stage = setupStages.find(s => !confirmed.includes(s));
  if (!stage) return <section className="floor-setup-guide" aria-label="Pipeline skill setup"><Check size={20} aria-hidden="true"/>
    <div><strong>{pipeline.name} · Skills reviewed 4/4</strong><p>All four agent skills are confirmed. Use Play when you are ready.</p></div>
    <button onClick={() => { start(pipeline.id); usePipelines.getState().focus(pipeline.id); }} disabled={!!pipeline.running||busy}>Review again</button></section>;
  if (review.paused) return <section className="floor-setup-guide" aria-label="Pipeline skill setup">
    <div><strong>{pipeline.name} · Setup unfinished {confirmed.length}/4</strong><p>Your confirmed steps are saved in this browser.</p></div>
    <button disabled={!!pipeline.running||busy} onClick={() => { pause(pipeline.id, false); usePipelines.getState().focus(pipeline.id); }}>Resume setup</button></section>;
  const Icon = STAGE_ICON[stage];
  const skill = catalog.find(s => s.id === pipeline.configuration[`playbook_${stage === "report" ? "explanation" : stage}`]);
  return <section className="floor-setup-guide" aria-label="Pipeline skill setup">
    <div className="floor-setup-heading"><Icon size={26} color={STAGE_COLOR[stage]} aria-hidden="true"/>
      <div aria-live="polite"><strong>{pipeline.name} · {names[stage]} · {confirmed.length}/4 confirmed</strong><p>{descriptions[stage]}</p></div>
      <button onClick={() => pause(pipeline.id, true)}>Later</button></div>
    <ol className="floor-setup-steps" aria-label="Skill review steps">{setupStages.map(s => {
      const StageIcon = STAGE_ICON[s];
      return <li key={s} aria-current={s===stage?'step':undefined} data-done={confirmed.includes(s)}>
        {confirmed.includes(s)?<Check size={15}/>:<StageIcon size={15}/>} {names[s]}</li>;
    })}</ol>
    <div className="floor-setup-actions"><span>Selected skill: <strong>{skill?.title || pipeline.configuration[`playbook_${stage === "report" ? "explanation" : stage}`] || 'Not selected'}</strong></span>
      <div className="floor-skill-entry" key={stage}>
        {!pipeline.running&&!busy&&<div id="floor-skill-entry-hint" className="floor-skill-entry-hint">
          <span>Review this skill here</span><ArrowDown size={14} aria-hidden="true"/>
        </div>}
        <button className="floor-skill-entry-button" aria-describedby={!pipeline.running&&!busy?'floor-skill-entry-hint':undefined}
          disabled={!!pipeline.running||busy} onClick={() => { usePipelines.getState().select(pipeline.id); useControl.getState().openEditor(stage); }}>View / change skill</button>
      <button className="floor-setup-next" disabled={!!pipeline.running||busy||!!error||!skill}
        onClick={() => confirm(pipeline.id,stage,skillSignature(pipeline.configuration,stage))}>
        {confirmed.length===3?'Confirm · finish':'Confirm · next'}<ChevronRight size={15}/></button></div></div>
    {pipeline.running&&<p>Stop this pipeline to review or change its configuration.</p>}
  </section>;
}
