import {researchSkillProfile} from './researchSkills.ts';
import type {RunRequest, SkillInfo} from '../store/control';

/** Fresh one-loop design: never inherit a previous experiment's overrides. */
export function quickResearchConfiguration(base:RunRequest, study:{id:string;configuration:{knowledge_mode?:'okf'|'llm_only';data_mode?:'dataset'|'proposal';target:{column:string;description:string}}}, catalog:SkillInfo[]):RunRequest {
 const configuration=study.configuration;
 const scope={research_input_id:study.id,knowledge_mode:configuration.knowledge_mode??'okf',data_mode:configuration.data_mode??'dataset'};
 const profile=researchSkillProfile(scope);
 const hypothesis=profile.hypothesis.find(id=>id!=='random_features');
 const choices={hypothesis: hypothesis??'',data:'data_training_heavy',ml:'ml_logistic_regression',interpreter:'shared-anil-shap',report:profile.report[0]??''};
 for(const [stage,id] of Object.entries(choices))if(!catalog.some(skill=>skill.stage===stage&&skill.id===id))throw Error(`The default ${stage} skill is unavailable. Reload the skills or use advanced setup.`);
 return {...base,...scope,provider:'',model:'',stage_models:undefined,question:'',skill:'',
  y_column:configuration.target.column,research_objective:configuration.target.description,
  playbook_hypothesis:choices.hypothesis,playbook_data:choices.data,playbook_ml:choices.ml,
  playbook_interpreter:choices.interpreter,playbook_explanation:choices.report,
  combination_skills:Object.fromEntries(Object.entries(choices).map(([stage,id])=>[stage,[id]])),
  combination_max_loops:1,combination_repetitions:1,combination_random_start:false,
  baseline_columns:[],ml_overrides:{},continuous:false,waves:1,trials:1,hypothesis_agents:1,interpret_agents:1,
  evaluation:{...base.evaluation,engine:'logistic_regression',replicates:1,search_trials:1}};
}
