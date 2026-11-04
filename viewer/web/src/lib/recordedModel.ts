type ObjectRecord = Record<string, unknown>;
const object = (value: unknown): ObjectRecord => value && typeof value === 'object' && !Array.isArray(value) ? value as ObjectRecord : {};
const present = (value: unknown) => value !== undefined;
export function parameterText(parameters: ObjectRecord): string {
  return Object.entries(parameters).sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`).join(' · ');
}

/** Read saved evidence only. Never infer fitted parameters from a model label. */
export function recordedModels(result: {model?: string; evaluation?: unknown}) {
  const evaluation = object(result.evaluation);
  const effective = object(object(evaluation.ml_configuration).effective);
  const models = object(evaluation.model_results);
  const primary = object(evaluation.paired_models).primary_model ?? effective.primary_model;
  const entries = Object.entries(models);
  const sources = entries.length ? entries : [[typeof primary === 'string' ? primary : result.model || 'Not recorded', {evaluation}]] as [string, unknown][];
  return sources.map(([family, source]) => {
    const saved = object(object(source).evaluation);
    const replicates = Array.isArray(saved.replicates) ? saved.replicates : [];
    const fits = replicates.map((value, index) => {
      const fit = object(value);
      return {index: index + 1, parameters: parameterText(object(fit.parameters)),
        seed: present(fit.seed) ? JSON.stringify(fit.seed) : undefined,
        threshold: present(object(fit.operating_point).probability_cutoff) ? JSON.stringify(object(fit.operating_point).probability_cutoff) : undefined};
    });
    const configured = parameterText(object(object(object(effective.models)[family]).parameters));
    return {family, primary: family === primary, fits, configured};
  });
}
