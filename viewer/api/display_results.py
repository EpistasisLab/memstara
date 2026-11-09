"""Display evidence without row-level payloads; detail/export APIs remain complete.

Every result and fitted replicate is retained, with its recorded metrics,
parameters, identities and agent documents. Polling does not need predictions
per subject, split membership, model artifacts or diagnostic matrices.
"""


def pick(value, fields):
    if not isinstance(value, dict):
        return value
    return {key: value[key] for key in fields if key in value}


def fits(value):
    if not isinstance(value, dict):
        return value
    result = pick(value, (
        'plan', 'duration_seconds', 'score_scope', 'validation_reserve',
        'replicate_seeds', 'reproducibility', 'status', 'method', 'scope',
    ))
    if isinstance(value.get('replicates'), list):
        result['replicates'] = []
        for fit in value['replicates']:
            item = pick(fit, (
                'replicate', 'seed', 'split_id', 'n_train', 'n_test', 'cv_folds',
                'auc', 'average_precision', 'f1', 'parameters', 'operating_point',
                'status', 'error', 'duration_seconds',
            ))
            if isinstance(fit, dict) and isinstance(fit.get('performance'), dict):
                item['performance'] = {
                    split: pick(metrics, ('n', 'threshold', 'metrics', 'confusion_matrix', 'status'))
                    for split, metrics in fit['performance'].items()
                }
            result['replicates'].append(item)
    return result


def evaluation(value):
    if not isinstance(value, dict):
        return value
    result = pick(value, (
        'auc', 'auc_std', 'seed', 'model', 'test_size', 'n_train', 'n_test',
        'config_hash', 'y_column', 'skills', 'paired_models', 'ml_configuration',
        'data_quality', 'feature_selection', 'hypothesis_policy', 'question_contract',
        'interpretations_complete', 'interpretations', 'interpretation_limitations',
        'interpreter', 'explanation', 'specialist_xai', 'knowledge_provenance',
    ))
    if 'evaluation' in value:
        result['evaluation'] = fits(value['evaluation'])
    if isinstance(value.get('model_results'), dict):
        result['model_results'] = {
            model: evaluation(measured) for model, measured in value['model_results'].items()
        }
    if isinstance(value.get('comparison'), dict):
        comparison = value['comparison']
        result['comparison'] = pick(comparison, (
            'timing_status', 'interpretation_limit', 'baseline_source', 'study_policy_sha256',
            'status', 'baseline_configured', 'baseline_columns', 'scope', 'parameters_policy', 'group_policy',
        ))
        if isinstance(comparison.get('variants'), list):
            result['comparison']['variants'] = [pick(variant, (
                'id', 'label', 'features', 'removed_features', 'status', 'auc',
                'delta_from_full', 'delta_from_baseline', 'error_type', 'reason',
            )) for variant in comparison['variants']]
    if isinstance(value.get('data_allocation'), dict):
        allocation = value['data_allocation']
        result['data_allocation'] = pick(allocation, (
            'request', 'agent_plan', 'validation_partition', 'exploration_count', 'reserved_count',
        ))
        if isinstance(allocation.get('replicates'), list):
            result['data_allocation']['replicates'] = [pick(fit, (
                'seed', 'n_train', 'n_test', 'train_class_counts', 'test_class_counts',
            )) for fit in allocation['replicates']]
    return result


def results(rows):
    return [{**row, **({'evaluation': evaluation(row['evaluation'])} if 'evaluation' in row else {})}
            for row in rows]
