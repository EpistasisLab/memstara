import {overridesForSkills} from './mlOverrides.ts';
import {compatibleResearchSkill,researchSkillProfile} from './researchSkills.ts';
import type { RunRequest } from '../store/control';

export type NewPipelineConfiguration = Omit<RunRequest, 'provider' | 'model' | 'stage_models'>;

/** Persist the explicitly checked connection ID, never keys or stale model profiles. */
export function newPipelineRequest(configuration: RunRequest): NewPipelineConfiguration {
  const research = Object.fromEntries(Object.entries(configuration)
    .filter(([key]) => !['provider', 'model', 'stage_models'].includes(key)));
  return structuredClone(research) as NewPipelineConfiguration;
}

/** Editor placeholders are separate from the model-free creation request. */
export function newPipelineConfiguration(configuration: RunRequest): RunRequest {
  const draft = {...newPipelineRequest(configuration), provider: '', model: '', model_connection_id: ''};
  if (['hypothesis_research','comorbidity','drug-class-effect','shared-anatomy',
    'shared-pharmacology','symptom-bridge','taxonomic','treatment-toxicity'].includes(draft.playbook_hypothesis)) {
    draft.playbook_hypothesis = 'hypothesis_general';
  }
  if (draft.playbook_data === 'data_exact_features') draft.playbook_data = 'data_training_heavy';
  if (['ml_governance','ml_pilot_lr_focus','ml_reporting','ml_results_presenter','ml_scikit_knowledge'].includes(draft.playbook_ml)) draft.playbook_ml = 'ml_logistic_regression';
  if (draft.playbook_ml === 'ml_pilot_xgb_focus') draft.playbook_ml = 'ml_xgboost';
  if (['interpreter_actionability','interpreter_attribution','interpreter_clinical',
    'interpreter_factual_observations','interpreter_review_pending','interpreter_robustness'].includes(draft.playbook_interpreter)) {
    draft.playbook_interpreter = 'shared-shap';
  }
  if (['shared-ml-results','report_clinical_explanations','report_clinician_summary',
    'report_evidence','report_loop_learning','report_ml_results','report_research_priority',
    'report_team_briefing','report_validation_audit'].includes(draft.playbook_explanation)) {
    draft.playbook_explanation = 'shared-addiction';
  }
  if (!compatibleResearchSkill({id:draft.playbook_hypothesis,stage:'hypothesis'},draft)) draft.playbook_hypothesis=researchSkillProfile(draft).hypothesis[0];
  if (!compatibleResearchSkill({id:draft.playbook_explanation,stage:'report'},draft)) draft.playbook_explanation=researchSkillProfile(draft).report[0];
  if (!compatibleResearchSkill({id:draft.playbook_interpreter,stage:'interpreter'},draft)) draft.playbook_interpreter='shared-shap';
  draft.ml_overrides=overridesForSkills(draft.ml_overrides,Object.keys(draft.combination_skills??{}).length?draft.combination_skills?.ml??[]:[draft.playbook_ml]);
  return draft;
}
