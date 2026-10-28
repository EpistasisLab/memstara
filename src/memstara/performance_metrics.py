"""Partition-labelled metrics from predictions; never fit on evaluation rows."""
from __future__ import annotations

VERSION = 'partition_metrics_v1'
LEGACY = 'legacy_auc_only'
BOOTSTRAP_SAMPLES = 1000


def binary_metrics(labels, probability, threshold):
    import numpy as np
    from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve, auc
    y, p = np.asarray(labels), np.asarray(probability, dtype=float)
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Decision threshold must be between zero and one')
    if (y.ndim != 1 or p.shape != y.shape or not len(y) or not np.isin(y, [0, 1]).all()
            or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any()):
        raise ValueError('Metrics require matching finite binary labels and probabilities')
    predicted = p >= threshold
    tp = int(np.sum((y == 1) & predicted))
    tn = int(np.sum((y == 0) & ~predicted))
    fp = int(np.sum((y == 0) & predicted))
    fn = int(np.sum((y == 1) & ~predicted))
    positive, negative = tp + fn, tn + fp
    both = bool(positive and negative)
    precision, recall, _ = precision_recall_curve(y, p) if positive else (None, None, None)
    sensitivity = tp / positive if positive else None
    specificity = tn / negative if negative else None
    clipped = np.clip(p, np.finfo(float).eps, 1 - np.finfo(float).eps)
    values = {
        'auroc': float(roc_auc_score(y, p)) if both else None,
        'average_precision': float(average_precision_score(y, p)) if positive else None,
        'pr_auc': float(auc(recall, precision)) if positive else None,
        'accuracy': (tp + tn) / len(y),
        'sensitivity': sensitivity, 'specificity': specificity,
        'precision': tp / (tp + fp) if tp + fp else None,
        'negative_predictive_value': tn / (tn + fn) if tn + fn else None,
        'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        'balanced_accuracy': (sensitivity + specificity) / 2 if both else None,
        'brier_score': float(np.mean((p - y) ** 2)),
        'log_loss': float(-np.mean(y * np.log(clipped) + (1 - y) * np.log1p(-clipped))),
    }
    reasons = {
        'auroc': 'Both outcome classes are required.',
        'average_precision': 'No positive labels.', 'pr_auc': 'No positive labels.',
        'sensitivity': 'No positive labels.', 'specificity': 'No negative labels.',
        'precision': 'No predicted positives.', 'negative_predictive_value': 'No predicted negatives.',
        'f1': 'No actual or predicted positives.', 'balanced_accuracy': 'Both outcome classes are required.',
    }
    return {'n': len(y), 'threshold': threshold, 'metrics': values,
            'undefined_reasons': {key: reasons[key] for key, value in values.items() if value is None},
            'confusion_matrix': {'labels': [0, 1], 'rows': 'actual', 'columns': 'predicted',
                                 'matrix': [[tn, fp], [fn, tp]],
                                 'tn': tn, 'fp': fp, 'fn': fn, 'tp': tp},
            'metric_definitions': {'pr_auc': 'Trapezoidal area under the precision-recall curve',
                                   'average_precision': 'Recall-increment weighted precision; not trapezoidal PR-AUC',
                                   'threshold_metrics': 'All classification metrics use the recorded threshold'}}


def summarize_folds(folds):
    import numpy as np
    summary = {}
    for name in folds[0]['metrics']:
        values = [fold['metrics'][name] for fold in folds if fold['metrics'][name] is not None]
        summary[name] = {'mean': float(np.mean(values)) if values else None,
                         'std': float(np.std(values, ddof=1)) if len(values) > 1 else None,
                         'valid_folds': len(values), 'total_folds': len(folds)}
    return summary


def cross_validation(pipe, X, y, cv, threshold, missing_policy):
    import numpy as np
    from sklearn.base import clone
    from memstara.missing_values import imputation_record
    folds, evidence = [], {}
    oof = np.empty(len(y), dtype=float)
    for number, (fit_rows, validation_rows) in enumerate(cv.split(X, y), 1):
        model = clone(pipe).fit(X.iloc[fit_rows], y.iloc[fit_rows])
        probabilities = model.predict_proba(X.iloc[validation_rows])[:, 1]
        oof[validation_rows] = probabilities
        record = binary_metrics(y.iloc[validation_rows], probabilities, threshold)
        record.update(fold=number, n_train=len(fit_rows), n_validation=len(validation_rows),
                      scope='training_partition_validation_fold',
                      imputation=imputation_record(model, missing_policy, fit_scope='training_fold_only'))
        folds.append(record)
        evidence[f'fold_{number}_fit'] = fit_rows
        evidence[f'fold_{number}_validation'] = validation_rows
    evidence.update(oof_probability=oof, labels=y.to_numpy())
    return {'status': 'completed', 'scope': 'training_rows_only', 'n': len(y), 'fold_count': len(folds),
            'folds': folds, 'summary': summarize_folds(folds),
            'summary_method': 'Unweighted fold means and sample SD (ddof=1); SD is not a confidence interval.',
            'selection_note': 'If CV selects a model candidate, these are selection scores, not nested-CV estimates.',
            'out_of_fold': binary_metrics(y, oof, threshold),
            'out_of_fold_note': 'Pooled validation predictions, one per training row; '
                                'metrics may differ from fold means.'}, evidence


def bootstrap_intervals(labels, probability, threshold, seed, *, samples=BOOTSTRAP_SAMPLES):
    """Stratified paired row bootstrap, conditional on this model and class counts."""
    import numpy as np
    y, p = np.asarray(labels), np.asarray(probability)
    groups = [np.flatnonzero(y == c) for c in [0, 1]]
    if any(len(group) < 2 for group in groups):
        return {'status': 'unavailable', 'reason': 'At least two observations in each class are required.'}
    if samples < 2:
        raise ValueError('Bootstrap requires at least two resamples')
    rng = np.random.default_rng(seed)
    distributions = {name: [] for name in binary_metrics(y, p, threshold)['metrics']}
    for _ in range(samples):
        rows = np.concatenate([rng.choice(group, len(group), replace=True) for group in groups])
        values = binary_metrics(y[rows], p[rows], threshold)['metrics']
        for name, value in values.items():
            if value is not None:
                distributions[name].append(value)
    intervals = {}
    for name, values in distributions.items():
        valid = len(values)
        complete = valid == samples
        bounds = np.quantile(values, [.025, .975]) if complete else [None, None]
        intervals[name] = {'lower': float(bounds[0]) if complete else None,
                           'upper': float(bounds[1]) if complete else None,
                           'valid_resamples': valid,
                           'status': 'estimated' if complete else 'undefined_in_resamples'}
    return {'status': 'completed', 'method': 'stratified_paired_percentile_bootstrap',
            'confidence_level': .95, 'resamples': samples, 'seed': seed, 'intervals': intervals,
            'scope': 'Held-out Test rows, fixed fitted model and threshold; class counts held fixed.',
            'limitations': 'Approximate intervals assuming independent rows. They exclude training, '
                          'model-selection and prevalence uncertainty and do not establish external validity.'}
