import type {RunRequest} from '../store/control';

/** A disease name alone never approves a specialist evidence binding. */
export function compatibleResearchSkill(skill: {id:string;stage:string}, form: Partial<RunRequest>): boolean {
  const id=skill.id??'';
  if (!form.research_input_id && form.knowledge_mode !== 'llm_only' && form.data_mode !== 'proposal') return true;
  if (skill.stage === 'hypothesis') return ['hypothesis_general','random_features'].includes(id) || id.startsWith('user-hypothesis-');
  if (skill.stage === 'report') return id === 'report_general' || id.startsWith('user-report-');
  return true;
}

export function resetResearchSkills(current?: Partial<RunRequest>, next?: Partial<RunRequest>): Partial<RunRequest> {
  const reset: Partial<RunRequest> = {skill:'',baseline_columns:[],combination_skills:{},
    playbook_hypothesis:'hypothesis_general',playbook_explanation:'report_general'};
  if (Object.keys(current?.combination_skills??{}).length) {
    const combinations={...current?.combination_skills};
    const target={...current,...next};
    for (const stage of ['hypothesis','report'] as const) {
      const choices=combinations[stage]??[];
      const retained=choices.filter(id=>compatibleResearchSkill({id,stage},target));
      const general=stage==='hypothesis'?'hypothesis_general':'report_general';
      combinations[stage]=retained.length===choices.length&&retained.length?retained:[...new Set([general,...retained])];
    }
    reset.combination_skills=combinations;
  }
  return reset;
}
