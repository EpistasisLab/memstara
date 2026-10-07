export type ModelIdentity = {provider: string; model: string};
export type StageProfiles = {qwen: ModelIdentity; sonnet: ModelIdentity};
export type ModelConfiguration = {provider?: string; model?: string; stage_models?: StageProfiles};

const roles = ['Question generation', 'Hypothesis', 'Data', 'ML', 'Interpretation', 'Explanation'];
export function stageModelRows(configuration?: ModelConfiguration) {
  const profiles = configuration?.stage_models;
  return roles.map((stage, index) => {
    const identity = profiles && Object.keys(profiles).length
      ? (index === 5 ? profiles.sonnet : profiles.qwen) : configuration;
    return {stage, model: identity?.model || 'Not recorded', provider: identity?.provider || 'Not recorded'};
  });
}
