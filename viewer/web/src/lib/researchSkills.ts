import type {RunRequest} from '../store/control';

type Profile={label:string;hypothesis:string[];report:string[]};
type Bindings={profiles:Record<string,Profile>;default:string;research:Record<string,string>};
const general:Profile={label:'General research',hypothesis:['hypothesis_general','random_features'],report:['report_general']};
let bindings:Bindings={profiles:{general},default:'legacy',research:{}};

/** The server binds actual corpus fingerprints; names/targets are never guessed. */
export function setCorpusSkillBindings(value?:Bindings):void {
  bindings=value??{profiles:{general},default:'legacy',research:{}};
}
export function setResearchCorpusProfile(id:string,profile:string):void {
  bindings.research[id]=profile;
}
export function researchSkillProfile(form:Partial<RunRequest>):Profile {
  const key=form.knowledge_mode==='llm_only'?'general':form.research_input_id
    ?bindings.research[form.research_input_id]??'general':bindings.default;
  return bindings.profiles[key]??general;
}
export function compatibleResearchSkill(skill:{id:string;stage:string},form:Partial<RunRequest>):boolean {
  const id=skill.id??'';
  if(skill.stage!=='hypothesis'&&skill.stage!=='report')return true;
  if(bindings.default==='legacy'&&!form.research_input_id&&form.knowledge_mode!=='llm_only'&&form.data_mode!=='proposal')return !id.startsWith('heart-failure-');
  const profile=researchSkillProfile(form);
  return profile[skill.stage].includes(id) ||
    (profile===general||profile===bindings.profiles.general)&&id.startsWith(`user-${skill.stage}-`);
}
export function resetResearchSkills(current?:Partial<RunRequest>,next?:Partial<RunRequest>):Partial<RunRequest> {
  const target={...current,...next};
  const profile=researchSkillProfile(target);
  const reset:Partial<RunRequest>={skill:'',baseline_columns:[],combination_skills:{},
    playbook_hypothesis:current?.playbook_hypothesis&&compatibleResearchSkill({id:current.playbook_hypothesis,stage:'hypothesis'},target)?current.playbook_hypothesis:profile.hypothesis[0],
    playbook_explanation:current?.playbook_explanation&&compatibleResearchSkill({id:current.playbook_explanation,stage:'report'},target)?current.playbook_explanation:profile.report[0]};
  if(Object.keys(current?.combination_skills??{}).length){
    const combinations=structuredClone(current?.combination_skills??{});
    for(const stage of ['hypothesis','report'] as const){
      const choices=combinations[stage]??[];
      const retained=choices.filter(id=>compatibleResearchSkill({id,stage},target));
      // A source switch keeps compatible choices (including Random); replace
      // incompatible expertise with the destination corpus' specialist set.
      combinations[stage]=retained.length===choices.length&&retained.length?retained:
        [...new Set([...profile[stage].filter(id=>id!=='random_features'),...retained])];
    }
    reset.combination_skills=combinations;
  }
  return reset;
}
