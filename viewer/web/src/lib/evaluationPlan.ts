type Plan = {engine: string; seed: number; test_size: number; folds: number; replicates: number; search_trials: number};

export function evaluationPlanError(plan: Plan): string | null {
  if (!['xgboost', 'random_forest', 'logistic_regression'].includes(plan.engine)) return 'Select a supported ML model.';
  if (!Number.isInteger(plan.seed) || plan.seed < 0 || plan.seed > 2147483647) return 'Random seed must be an integer from 0 to 2147483647.';
  if (!Number.isFinite(plan.test_size) || plan.test_size < .1 || plan.test_size > .5) return 'Hold-out percentage must be between 10% and 50%.';
  if (!Number.isInteger(plan.folds) || plan.folds < 0 || plan.folds === 1 || plan.folds > 10) return 'Training CV folds must be 0 or 2–10.';
  if (!Number.isInteger(plan.replicates) || plan.replicates < 1 || plan.replicates > 10) return 'Split evaluations must be an integer from 1 to 10.';
  if (!Number.isInteger(plan.search_trials) || plan.search_trials < 1 || plan.search_trials > 10) return 'Hyperparameter candidates must be an integer from 1 to 10.';
  if (plan.seed + plan.replicates - 1 > 2147483647) return 'Reduce the random seed so all successive split seeds stay within 2147483647.';
  return null;
}
