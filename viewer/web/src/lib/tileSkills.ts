import {scheduleIdentity} from './replicateIdentity.ts';
import type {RunConfiguration, Result, Snapshot} from '../types.ts';

export const tileStages = [
  {id: 'hypothesis', label: 'Hypothesis', short: 'H', description: 'Generates a testable research hypothesis.'},
  {id: 'data', label: 'Data', short: 'D', description: 'Selects and prepares predictors for evaluation.'},
  {id: 'ml', label: 'Machine learning', short: 'ML', description: 'Trains and evaluates predictive models.'},
  {id: 'interpreter', label: 'Interpretation', short: 'I', description: 'Interprets model results and feature contributions.'},
  {id: 'report', label: 'Explanation', short: 'E', description: 'Explains findings in the study context.'},
] as const;
export type TileSkill = {id: string; title?: string; hash?: string};
export type SkillConfiguration = Pick<RunConfiguration, 'combination_plan' | 'books'>;

export function tileSkillConfiguration(snapshot: Snapshot, source: string): SkillConfiguration | undefined {
  // The head's current plan is never a fallback for a retained execution.
  return snapshot.skill_configurations?.[source]
    ?? (source === snapshot.run_tag ? snapshot.run_configuration ?? undefined : undefined);
}

/** Decode the saved Cartesian schedule in the same order as combinations.loop_flavors. */
export function tileSkillStages(config: SkillConfiguration | undefined, loop: number, results: Result[]) {
  const plan = config?.combination_plan;
  const lists = tileStages.map(stage => plan?.skills?.[stage.id] ?? []);
  const count = lists.reduce((n, list) => n * list.length, 1);
  const identity = scheduleIdentity(loop, plan);
  let index = count > 0 && count === plan?.combinations && identity.pipeline_number
    ? identity.pipeline_number - 1 : -1;
  const choices: (TileSkill | undefined)[] = Array(tileStages.length);
  if (index >= 0) for (let i = lists.length - 1; i >= 0; i--) {
    choices[i] = lists[i][index % lists[i].length];
    index = Math.floor(index / lists[i].length);
  }
  return tileStages.map((stage, i) => {
    const observed = [...new Set(results.flatMap(result => result.evaluation?.skills?.[stage.id] ?? []))];
    const options: TileSkill[] = lists[i].length ? [...lists[i]]
      : (config?.books?.[stage.id] ?? []).map(id => ({id}));
    let selected: TileSkill | undefined;
    let issue = '';
    if (observed.length > 1) issue = 'Multiple skills were recorded for this stage; no single selection is shown.';
    else if (observed.length === 1) {
      selected = options.find(skill => skill.id === observed[0]) ?? {id: observed[0]};
      if (choices[i] && choices[i]?.id !== selected.id) {
        // Keep the actual result's ID, but do not attach an unrelated scheduled version.
        selected = {id: observed[0]};
        issue = 'The result records a different skill from the saved schedule. Its version is not verified.';
      }
    } else selected = choices[i] ?? (!plan && options.length === 1 ? options[0] : undefined);
    if (selected && !options.some(skill => skill.id === selected.id)) options.push(selected);
    return {...stage, options, selected, issue,
      provenance: observed.length === 1 ? 'Recorded result' : selected ? 'Saved execution configuration' : 'Selection not recorded'};
  });
}
