"""Deterministic binary-classification evaluation, shared by the MCP tool and controls."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

MODELS = ('xgboost', 'random_forest', 'logistic_regression')
DEFAULTS = {'engine': 'xgboost', 'seed': 42, 'test_size': 0.25, 'folds': 0, 'replicates': 1, 'search_trials': 1}


class DataQualityError(ValueError):
    """A safe, aggregate-only diagnostic for input that cannot be evaluated."""


def validate(plan: dict) -> dict:
    unknown = set(plan) - set(DEFAULTS)
    if unknown:
        raise ValueError(f'Unknown evaluation options: {sorted(unknown)}')
    out = {**DEFAULTS, **plan}
    if out['engine'] not in MODELS:
        raise ValueError(f"Unknown model {out['engine']!r}; model must be one of {MODELS}")
    for key, lo, hi in [('seed', 0, 2147483647), ('folds', 0, 10), ('replicates', 1, 10), ('search_trials', 1, 10)]:
        if type(out[key]) is not int or not lo <= out[key] <= hi:
            raise ValueError(f'{key} must be an integer in [{lo}, {hi}]')
    if out['folds'] == 1:
        raise ValueError('Cross-validation needs at least 2 folds (0 disables it)')
    if type(out['test_size']) not in (int, float) or not 0.1 <= out['test_size'] <= 0.5:
        raise ValueError('Hold-out fraction must be between 0.1 and 0.5')
    return out


def active_plan() -> dict | None:
    source = os.environ.get('MEMSTARA_RUN_CONFIG', '')
    return json.loads(Path(source).read_text()) if source else None


def model_for(engine: str, seed: int, trial: int = 0):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    if engine == 'xgboost':
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=200 + 100 * (trial // 4), max_depth=(4, 3, 5, 6)[trial % 4],
                             eval_metric='logloss', random_state=seed, n_jobs=1)
    if engine == 'random_forest':
        return RandomForestClassifier(n_estimators=200 + 100 * (trial // 4), max_depth=(None, 4, 8, 12)[trial % 4],
                                      random_state=seed, n_jobs=1)
    if engine == 'logistic_regression':
        return LogisticRegression(C=(1., .1, 10., .01, 100., .001, 1000., .0001, 10000., .00001)[trial % 10],
                                  max_iter=2000, random_state=seed)
    raise ValueError(f'Unsupported model: {engine}')


def validate_clean_dataset(path: Path, target: str, *, allow_missing: bool = False):
    """Validate the MVP input contract without repairing or dropping any values."""
    import numpy as np
    import pandas as pd
    import csv
    try:
        with path.open(newline='', encoding='utf-8-sig') as stream:
            headers = next(csv.reader(stream), [])
        if not headers or any(not c.strip() for c in headers) or len(set(headers)) != len(headers):
            raise DataQualityError('Dataset columns must have non-empty, unique names.')
        df = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataQualityError('Cannot read the configured dataset as CSV. Check the file and its format.') from exc
    if target not in df:
        raise DataQualityError('The selected target is not a column in the configured dataset.')
    if df[target].isna().any():
        raise DataQualityError('Target labels are missing; labels cannot be imputed')
    if set(df[target].unique()) != {0, 1}:
        raise DataQualityError('The target must contain both binary classes 0 and 1')
    if len(df.columns) < 2:
        raise DataQualityError('No predictor features are available')
    missing = df.drop(columns=[target]).isna()
    if missing.any().any() and not allow_missing:
        raise DataQualityError(
            f'AI-ready input required: {int(missing.sum().sum()):,} missing predictor values '
            f'across {int(missing.any().sum()):,} columns. '
            'The current policy rejects missing values and does not clean or impute data. '
            'Choose XGBoost for native missing-value handling or provide a complete dataset; '
            'no values or rows were changed.')
    numeric = df.select_dtypes(include='number')
    if np.isinf(numeric.to_numpy(dtype=float)).any():
        raise DataQualityError('AI-ready input required: non-finite values must be resolved before upload. '
                               'The MVP does not clean or impute data.')
    return df


def discovery_partition(y, seed):
    """Reserve 20% before adaptive exploration; this module never evaluates that reserve."""
    import numpy as np
    from sklearn.model_selection import train_test_split
    if y.value_counts().min() < 4:
        raise DataQualityError('Iterative discovery needs at least four samples in each target class '
                               'to reserve validation data.')
    exploration, reserved = train_test_split(np.arange(len(y)), test_size=.2, random_state=seed, stratify=y)
    return {'version': 'reserved_validation_v1', 'row_count': len(y),
            'exploration_rows': sorted(exploration.tolist()), 'reserved_count': len(reserved),
            'reserved_split_id': hashlib.sha256(np.sort(reserved).tobytes()).hexdigest(),
            'status': 'reserved_not_evaluated', 'fraction': .2}


def evaluation_splits(y, plan: dict, partition=None):
    """Check every requested hold-out before fitting or provisioning paid agents."""
    import numpy as np
    from sklearn.model_selection import train_test_split
    if y.value_counts().min() < 2:
        raise DataQualityError('Each target class needs at least two samples for a stratified hold-out')
    if partition is None:
        snapshot = active_plan() or {}
        partition = snapshot.get('validation_partition')
        if snapshot.get('hypothesis_policy', {}).get('version') == 'iterative_discovery_v1' and not partition:
            raise DataQualityError('Iterative discovery requires a reserved validation partition')
    indices = np.arange(len(y))
    if partition:
        rows = partition.get('exploration_rows', [])
        if (partition.get('row_count') != len(y) or not rows or
                any(type(i) is not int or i < 0 or i >= len(y) for i in rows) or
                len(set(rows)) != len(rows) or len(rows) + partition.get('reserved_count', 0) != len(y)):
            raise DataQualityError('Dataset rows do not match the reserved validation partition')
        indices = np.asarray(rows)
    labels = y.iloc[indices]
    if labels.nunique() != 2 or labels.value_counts().min() < 2:
        raise DataQualityError('Exploration partition needs both classes and at least two samples per class')
    n_test = max(2, min(len(indices) - 2, int(np.ceil(len(indices) * plan['test_size']))))
    splits = []
    for rep in range(plan['replicates']):
        seed = plan['seed'] + rep
        if seed > 2147483647:
            raise DataQualityError('Seed plus replicate index exceeds the supported random-state range.')
        train, test = train_test_split(indices, test_size=n_test, random_state=seed, stratify=labels)
        if y.iloc[train].nunique() < 2 or y.iloc[test].nunique() < 2:
            raise DataQualityError('Stratified hold-out cannot represent both classes; '
                                   'more minority samples or a different hold-out fraction are required')
        splits.append((seed, train, test))
    return splits


def preflight(path: Path, target: str, plan: dict, *, reserve_validation: bool = False) -> None:
    plan = validate(plan)
    frame = validate_clean_dataset(path, target, allow_missing=plan['engine'] == 'xgboost')
    partition = discovery_partition(frame[target], plan["seed"]) if reserve_validation else None
    evaluation_splits(frame[target], plan, partition=partition)


def score(path: Path, target: str, plan: dict, *, predictors=None, fixed_trials=None, explain=True,
          persist=True, partition=None) -> dict:
    import numpy as np
    import sklearn
    from sklearn.metrics import roc_auc_score, average_precision_score, balanced_accuracy_score, confusion_matrix
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    began = time.time()
    source_bytes = path.read_bytes()
    if partition is None:
        snapshot = active_plan() or {}
        partition = snapshot.get('validation_partition') or {}
        if snapshot.get('hypothesis_policy', {}).get('version') == 'iterative_discovery_v1' and not partition:
            raise DataQualityError('Iterative discovery requires a reserved validation partition')
    plan = validate(plan)
    df = validate_clean_dataset(path, target, allow_missing=plan['engine'] == 'xgboost')
    X, y = df.drop(columns=[target]), df[target]
    if predictors is not None:
        if target in predictors or any(c not in X for c in predictors):
            raise DataQualityError("Invalid comparison predictors")
        X = X[list(dict.fromkeys(predictors))]
    if X.empty:
        raise DataQualityError('No predictor features are available')
    if y.isna().any():
        raise DataQualityError('Target labels are missing; labels cannot be imputed')
    counts = y.value_counts()
    if counts.min() < 2:
        raise DataQualityError('Each target class needs at least two samples for a stratified hold-out')
    warnings = []
    if counts.min() / len(y) < .1:
        warnings.append('Rare positive or negative class: inspect average precision and class counts; '
                        'AUC alone is insufficient.')
    numeric = X.select_dtypes(include='number').columns.tolist()
    categorical = [c for c in X if c not in numeric]
    missing_cells = int(X.isna().sum().sum())
    if missing_cells:
        warnings.append('Missing numeric predictors are retained as NaN for XGBoost tree routing; '
                        'categorical missingness is encoded as a category when observed in training. '
                        'Missingness may reflect measurement practices; review before clinical interpretation.')
    if (X.nunique(dropna=True) <= 1).any():
        warnings.append('Some predictors are constant or entirely missing and provide little or no information.')
    runs = []
    artifacts = []
    last = None
    # Replicates share their split across hypotheses; only feature sets change.
    for seed, train, test in evaluation_splits(y, plan, partition=partition):
        pre = ColumnTransformer([
            ('numeric', 'passthrough' if plan['engine'] == 'xgboost' else StandardScaler(), numeric),
            ('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical),
        ], verbose_feature_names_out=False)
        best, best_cv, best_params, selected_trial = None, None, None, 0
        fold_count = plan['folds'] or (3 if plan['search_trials'] > 1 else 0)
        requested_folds = fold_count
        fold_count = min(fold_count, int(y.iloc[train].value_counts().min()))
        if fold_count < 2:
            fold_count = 0
        if fold_count != requested_folds:
            warnings.append('CV folds reduced to match training minority count; '
                            'search is disabled when CV is unavailable.')
        candidates = ([fixed_trials[len(runs)]] if fixed_trials is not None
                      else range(plan['search_trials'] if fold_count else 1))
        for trial in candidates:
            model = model_for(plan['engine'], seed, trial)
            pipe = Pipeline([('encode', pre), ('model', model)])
            cv_scores = None
            if fold_count:
                cv = StratifiedKFold(n_splits=fold_count, shuffle=True, random_state=seed)
                cv_scores = cross_val_score(pipe, X.iloc[train], y.iloc[train], cv=cv, scoring='roc_auc',
                                            n_jobs=1, error_score='raise')
            avg = float(np.mean(cv_scores)) if cv_scores is not None else 0.0
            if best is None or avg > best_cv:
                best, best_cv, selected_trial = pipe, avg, trial
                # XGBoost's missing-value sentinel is NaN. Persist it symbolically;
                # PostgreSQL JSONB and browser JSON require finite JSON numbers.
                best_params = json.loads(json.dumps(model.get_params(), default=str), parse_constant=str)
        best.fit(X.iloc[train], y.iloc[train])
        probability = best.predict_proba(X.iloc[test])[:, 1]
        artifacts.append((best, train.copy(), test.copy(), probability.copy()))
        auc = float(roc_auc_score(y.iloc[test], probability))
        tn, fp, fn, tp = (int(n) for n in confusion_matrix(y.iloc[test], probability >= .5, labels=[0, 1]).ravel())
        operating_point = {
            'probability_cutoff': .5, 'selection': 'fixed before evaluation; not optimized on hold-out',
            'sensitivity': tp / (tp + fn), 'specificity': tn / (tn + fp),
            'precision': tp / (tp + fp) if tp + fp else None,
            'precision_reason': ('No positive predictions at the fixed cutoff: TP + FP = 0, '
                                 'so precision is undefined (0/0).') if tp + fp == 0 else None,
            'negative_predictive_value': tn / (tn + fn) if tn + fn else None,
            'true_positive': tp, 'false_positive': fp, 'true_negative': tn, 'false_negative': fn,
            'status': 'model operating point; not a validated clinical intervention threshold',
        }
        runs.append({'seed': seed, 'auc': auc, 'split_id': hashlib.sha256(test.tobytes()).hexdigest(),
                     'train_split_id': hashlib.sha256(train.tobytes()).hexdigest(),
                     'prediction_sha256': hashlib.sha256(probability.tobytes()).hexdigest(),
                     'selected_trial': selected_trial, 'operating_point': operating_point,
                     'n_train': len(train), 'n_test': len(test), 'parameters': best_params,
                     'average_precision': float(average_precision_score(y.iloc[test], probability)),
                     'balanced_accuracy_at_0_5': float(balanced_accuracy_score(y.iloc[test], probability >= .5)),
                     'train_class_counts': {str(k): int(v) for k, v in y.iloc[train].value_counts().items()},
                     'test_class_counts': {str(k): int(v) for k, v in y.iloc[test].value_counts().items()},
                     'cv_auc': best_cv if fold_count else None, 'cv_folds': fold_count})
        last = (best, train, test)
    best, train, test = last
    try:
        importance, explanation = (_explain(best, X, y, train, test, numeric, plan, runs) if explain else
                                   ({}, {'status': 'completed', 'scope': 'Auxiliary comparison only'}))
    except Exception as exc:
        # Library messages may contain data values. Persist only safe exception metadata.
        importance = {}
        explanation = {
            'status': 'failed', 'error_type': type(exc).__name__,
            'reason': 'Supplementary explanation failed; model evaluation metrics are retained.',
            'partial_dependence': [], 'feature_effects': [], 'exploratory_transitions': [],
            'shap': {'status': 'not_available'},
            'operating_point': runs[-1]['operating_point'],
            'clinical_threshold': None,
            'actionability': 'Explanation unavailable. Do not infer feature effects or clinical actionability.',
        }
    if explanation['status'] != 'completed':
        warnings.append('Explanation is incomplete; inspect explanation status before interpreting feature effects.')
    reserve = partition
    result = {'auc': float(np.mean([r['auc'] for r in runs])),
              'auc_std': float(np.std([r['auc'] for r in runs])), 'features': list(X.columns),
              'feature_importance': importance, 'model': plan['engine'], 'seed': plan['seed'],
              'test_size': plan['test_size'], 'n_train': len(train), 'n_test': len(test),
              'data_quality': {'missing_predictor_cells': missing_cells,
                               'missing_value_policy': 'native_xgboost' if plan['engine'] == 'xgboost' else 'reject',
                               'warnings': list(dict.fromkeys(warnings)),
                               'preprocessing': 'No cleaning or imputation. '
                                                'Training-fold one-hot encoding; numeric passthrough for XGBoost, '
                                                'training-fold scaling for other models.',
                               'source_preserved': True, 'target_imputed': False},
              'evaluation': {'plan': plan, 'replicates': runs, 'sklearn_version': sklearn.__version__,
                             'dataset_sha256': hashlib.sha256(source_bytes).hexdigest(),
                             'started_at': began, 'duration_seconds': time.time() - began,
                             'score_scope': 'adaptive_exploration' if reserve else 'exploratory_holdout',
                             'validation_reserve': {k:v for k,v in reserve.items()
                                                    if k != 'exploration_rows'}},
              'explanation': explanation}
    if path.read_bytes() != source_bytes:
        raise DataQualityError('Input changed during evaluation; results cannot be reproduced.')
    if persist:
        from memstara.reproducibility import save_bundle
        result['evaluation']['reproducibility'] = save_bundle(
            source_bytes, target, plan, list(X.columns), fixed_trials, partition, artifacts, result)
    return result


def _explain(best, X, y, train, test, numeric, plan, runs):
    """Compute supplementary explanation without changing the fitted model or split."""
    import numpy as np
    from sklearn.inspection import permutation_importance

    # Consistent importance units across all selectable engines, measured on hold-out.
    imp = permutation_importance(best, X.iloc[test], y.iloc[test], n_repeats=3,
                                 random_state=plan['seed'], scoring='roc_auc', n_jobs=1)
    importance = {str(c): float(v) for c, v in zip(X.columns, imp.importances_mean, strict=True)}
    curves = []
    skipped = []
    for c in sorted(numeric, key=lambda c: -abs(importance[c]))[:5]:
        # Build the grid from observed TRAINING values, never from held-out values.
        observed = X.iloc[train][c].dropna()
        if observed.nunique() < 2:
            skipped.append({'feature': c, 'reason': 'Fewer than two observed training values'})
            continue
        unique = np.sort(observed.unique())
        # Enumerate low-cardinality predictors so rare binary indicators retain both states.
        grid = unique if len(unique) <= 8 else np.unique(np.quantile(observed, np.linspace(.05, .95, 8)))
        if len(grid) < 2:
            skipped.append({'feature': c, 'reason': 'Training percentile grid has fewer than two distinct values'})
            continue
        probabilities = []
        for value in grid:
            reference = X.iloc[train].copy()
            reference[c] = value
            probabilities.append(float(best.predict_proba(reference)[:, 1].mean()))
        pdp = {'grid_values': [grid], 'average': [np.asarray(probabilities)]}
        curves.append({'feature': c, 'values': pdp['grid_values'][0].tolist(),
                       'predicted_probability': pdp['average'][0].tolist()})
    explanation = {'status': 'partial' if skipped else 'completed', 'skipped_response_curves': skipped,
                   'method': 'holdout_permutation_auc', 'partial_dependence': curves,
                   'operating_point': runs[-1]['operating_point'],
                   'scope': 'Explanation of the final replicate; AUC summary spans all replicates.',
                   'clinical_threshold': None,
                   'review_status': 'Review required — provisional implementation, not independently reviewed',
                   'actionability': 'Exploratory model associations only. Clinical thresholds and interventions '
                                    'require domain review and independent validation.'}
    explanation['exploratory_transitions'] = [
        {'feature': c['feature'], 'value': float(c['values'][int(np.argmax(
             np.abs(np.diff(c['predicted_probability']))))]),
         'status': 'largest model-response step on training grid; not a validated clinical cutoff'}
        for c in curves if len(c['values']) > 1
    ]
    explanation['feature_effects'] = []
    for curve in curves:
        if len(curve['values']) < 2:
            continue
        delta = np.diff(curve['predicted_probability'])
        index = int(np.argmax(np.abs(delta)))
        explanation['feature_effects'].append({
            'feature': curve['feature'],
            'range_start': curve['values'][index], 'range_end': curve['values'][index + 1],
            'probability_before': curve['predicted_probability'][index],
            'probability_after': curve['predicted_probability'][index + 1],
            'direction': 'increase' if delta[index] > 0 else 'decrease' if delta[index] < 0 else 'unchanged',
            'probability_change': float(delta[index]),
            'evidence': 'largest adjacent response change on the training-data grid; conditional model experiment',
            'validation_needed': 'Confirm feature meaning and units, correlated-feature effects, external validity '
                                 'and whether changing this feature is feasible. '
                                 'This is not a treatment recommendation.',
        })
    if plan['engine'] == 'xgboost':
        try:
            import xgboost as xgb
            encoded = best.named_steps['encode'].transform(X.iloc[test])
            contributions = best.named_steps['model'].get_booster().predict(xgb.DMatrix(encoded), pred_contribs=True)
            names = best.named_steps['encode'].get_feature_names_out()
            explanation['shap'] = {'method': 'XGBoost TreeSHAP', 'units': 'log-odds',
                                   'mean_absolute': dict(zip(names, np.abs(contributions[:, :-1]).mean(axis=0).tolist(),
                                                             strict=True)),
                                   'mean_signed': dict(zip(names, contributions[:, :-1].mean(axis=0).tolist(),
                                                           strict=True))}
        except Exception as exc:
            explanation['status'] = 'partial'
            explanation['shap'] = {'status': 'not_available', 'error_type': type(exc).__name__,
                                   'reason': 'TreeSHAP calculation failed; no SHAP evidence is available.'}
    else:
        explanation['shap'] = {'status': 'not_available', 'reason': 'Use permutation importance and response curves.'}
    return importance, explanation
