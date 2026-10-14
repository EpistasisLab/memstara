import {useEffect,useState} from 'react';
import {usePipelines,type PipelineDefinition} from '../store/pipelines';
import {useControl} from '../store/control';
import FloorDetailDialog from './FloorDetailDialog';
import EvaluationSettings from './EvaluationSettings';
import MLAdvancedSettings from './MLAdvancedSettings';
import {evaluationPlanError} from '../lib/evaluationPlan';
import {mlOverridesError,overridesForSkills} from '../lib/mlOverrides';
export default function PipelineMLSettings({pipeline,close}:{pipeline:PipelineDefinition;close:()=>void}){
 const busy=usePipelines(s=>s.busy),error=usePipelines(s=>s.error);
 useControl(s=>s.catalog);
 const [evaluation,setEvaluation]=useState({...pipeline.configuration.evaluation});
 const [overrides,setOverrides]=useState(structuredClone(pipeline.configuration.ml_overrides??{}));
 useEffect(()=>{void useControl.getState().loadPlaybooks();},[]);
 const combined=!!Object.keys(pipeline.configuration.combination_skills??{}).length;
 const skills=combined?pipeline.configuration.combination_skills?.ml??[]:[pipeline.configuration.playbook_ml];
 const invalid=evaluationPlanError(evaluation)||mlOverridesError(overrides,skills,evaluation.replicates);
 const locked=busy||!!pipeline.running;
 return <FloorDetailDialog title={`${pipeline.name} · ML evaluation and advanced settings`} close={close}>
  <p className="mb-3 text-sm">Changes apply to future executions. Existing runs and saved results keep their original frozen settings.</p>
  <MLAdvancedSettings skills={skills} value={overrides} onChange={setOverrides} replicates={evaluation.replicates} proposal={pipeline.configuration.data_mode==='proposal'} disabled={locked}/>
  <EvaluationSettings value={evaluation} onChange={setEvaluation} paired dataSkill={combined?'combinations':pipeline.configuration.playbook_data} proposal={pipeline.configuration.data_mode==='proposal'} disabled={locked}/>
  {locked&&<p className="mt-3 text-sm">End the active execution before changing its ML settings.</p>}
  {(invalid||error)&&<p role="alert" className="mt-3 text-sm text-red-700">{invalid||error}</p>}
  <div className="mt-4 flex gap-3"><button type="button" onClick={close}>Cancel</button><button type="button" disabled={locked||!!invalid} onClick={async()=>{const saved=await usePipelines.getState().save(pipeline.id,{...pipeline.configuration,evaluation,ml_overrides:overridesForSkills(overrides,skills)});if(saved)close();}}>Save ML settings</button></div>
 </FloorDetailDialog>;
}
