export type ModelIdentity = {provider: string; model: string};
// Historical/incomplete snapshots remain displayable; the backend validates launches.
export type StageProfiles = Partial<Record<'question' | 'hypothesis' | 'data' | 'ml' | 'interpretation' | 'non_explanation_agents' | 'explanation_agent' | 'analysis' | 'explanation' | 'qwen' | 'sonnet', ModelIdentity>>;
export type ModelConfiguration = {provider?: string; model?: string; stage_models?: StageProfiles};

const agentKeys = ['question', 'hypothesis', 'data', 'ml', 'interpretation', 'explanation'] as const;
const roles = ['Question generation', 'Hypothesis', 'Data', 'ML', 'Interpretation', 'Explanation'];
export function stageModelRows(configuration?: ModelConfiguration) {
  const profiles = configuration?.stage_models;
  return roles.map((stage, index) => {
    const identity = profiles && Object.keys(profiles).length
      ? ('question' in profiles || 'hypothesis' in profiles
        ? profiles[agentKeys[index]]
        : 'non_explanation_agents' in profiles || 'explanation_agent' in profiles
        ? (index === 5 ? profiles.explanation_agent : profiles.non_explanation_agents)
        : 'analysis' in profiles || 'explanation' in profiles
        ? (index === 5 ? profiles.explanation : profiles.analysis)
        : (index === 5 ? profiles.sonnet : profiles.qwen)) : configuration;
    return {stage, model: identity?.model || 'Not recorded', provider: identity?.provider || 'Not recorded'};
  });
}
