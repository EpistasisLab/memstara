"""Explicit-only baseline comparisons; default models use hypothesis predictors."""
from memstara.comparisons import validate_baseline

TIMING_WARNING = ('Predictor measurement/prescription timing has not been verified against the prediction '
                  'time. This is an exploratory comparison, not validated prospective prediction. '
                  'Incremental AUC is not evidence of causality or clinical benefit.')


def resolve_comparison(requested, target, dataset):
    baseline = validate_baseline(requested, target, dataset)
    # Baselines are opt-in. Never infer predictors from a local policy file.
    source = 'explicit_columns' if baseline else 'prevalence_reference'
    return {'version': 'paired_groups_v1', 'baseline_columns': baseline, 'baseline_source': source,
            'timing_status': 'unverified', 'interpretation_limit': TIMING_WARNING}
