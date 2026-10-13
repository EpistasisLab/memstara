import type { RunRequest } from '../store/control';

export type NewPipelineConfiguration = Omit<RunRequest, 'provider' | 'model' | 'stage_models'>;

/** Only research settings enter creation; model assignments are not serialized. */
export function newPipelineRequest(configuration: RunRequest): NewPipelineConfiguration {
  const research = Object.fromEntries(Object.entries(configuration)
    .filter(([key]) => !['provider', 'model', 'stage_models'].includes(key)));
  return structuredClone(research) as NewPipelineConfiguration;
}

/** Editor placeholders are separate from the model-free creation request. */
export function newPipelineConfiguration(configuration: RunRequest): RunRequest {
  return {...newPipelineRequest(configuration), provider: '', model: ''};
}
