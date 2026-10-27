"""Bounded SHAP/LIME evidence from fitted pipelines, with local-only row artifacts."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

VERSION = 'paired_specialist_xai_v1'
SKILLS = {'shared-shap': 'shap', 'shared-lime': 'lime'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def freeze(books, prompts):
    from memstara.control.catalog import resolve, specialist_dir
    chosen = [name for name in books.get('interpreter', []) if name in SKILLS]
    if not chosen:
        return None
    skills = {}
    for name in chosen:
        item = resolve(name)
        method = SKILLS[name]
        if item.get('stage') != 'interpreter' or f'Feature Attribution ({method.upper()})' not in item['content']:
            raise ValueError(f'{name}: expected the current {method.upper()} Interpretation instructions')
        raw = (specialist_dir() / item['source_file']).read_bytes().decode('utf-8')
        if hashlib.sha256(raw.encode()).hexdigest() != item['source_hash']:
            raise ValueError('Shared skill changed while freezing its source')
        skills[name] = {'method': method, 'source_file': item['source_file'], 'source_text': raw,
                        'source_sha256': item['source_hash'], 'content_sha256': item['hash'],
                        'prompt': prompts[f'board/interpreter:{name}']}
    return {'version': VERSION, 'skills': skills, 'explained_rows': 8, 'background_rows': 32,
            'lime_samples': 512, 'max_original_features': 64,
            'versions': {name: importlib.metadata.version(name) for name in ('shap', 'lime')},
            'reference_policy': 'training rows only', 'explanation_scope': 'sampled exploration evaluation rows'}


def request(snapshot, trial):
    from memstara.combinations import task_books
    policy = (snapshot or {}).get('specialist_xai_policy')
    if not policy or policy.get('version') != VERSION:
        return None
    chosen = [name for name in task_books(snapshot, trial).get('interpreter', []) if name in SKILLS]
    if not chosen:
        return None
    if any(name not in policy['skills'] for name in chosen):
        raise ValueError('Selected Interpretation skill is not frozen in this run')
    return {'version': VERSION, 'trial': trial, 'run_tag': snapshot['run_tag'],
            'config_hash': snapshot['config_hash'], 'policy': policy,
            'methods': sorted({SKILLS[name] for name in chosen}),
            'skills': {name: policy['skills'][name] for name in chosen}}


def _mapping(pre, features):
    """Map transformed columns by fitted transformer indices, never string prefixes."""
    owners = []
    names = list(pre.get_feature_names_out())
    for name, transformer, columns in pre.transformers_:
        if name == 'remainder' or len(columns) == 0:
            continue
        if name == 'numeric':
            owners.extend(columns)
        elif name == 'categorical':
            for column, categories in zip(columns, transformer.categories_, strict=True):
                owners.extend([column] * len(categories))
    if len(owners) != len(names) or set(owners) != set(features):
        raise ValueError('Fitted feature mapping does not match the original predictors')
    return names, owners


def _shap(model, X, train, explained, background, seed, name):
    import numpy as np
    import shap
    if 'impute' in model.named_steps:
        X = model.named_steps['impute'].transform(X)
    pre, estimator = model.named_steps['encode'], model.named_steps['model']
    reference = pre.transform(X.iloc[background])
    encoded = pre.transform(X.iloc[explained])
    names, owners = _mapping(pre, list(X.columns))
    if name == 'logistic_regression':
        explainer = shap.LinearExplainer(estimator, reference)
        output = estimator.decision_function(encoded)
    else:
        import xgboost as xgb
        explainer = shap.TreeExplainer(estimator, model_output='raw',
                                       feature_perturbation='tree_path_dependent')
        output = estimator.get_booster().predict(xgb.DMatrix(encoded), output_margin=True)
    values = np.asarray(explainer.shap_values(encoded), dtype=float)
    baseline = float(np.asarray(explainer.expected_value).reshape(-1)[0])
    if values.shape != encoded.shape or not np.isfinite(values).all():
        raise ValueError('Unexpected SHAP attribution shape or non-finite values')
    residual = baseline + values.sum(axis=1) - output
    if not np.allclose(residual, 0, atol=1e-4, rtol=0):
        raise ValueError('SHAP additivity verification failed')
    grouped = np.column_stack([values[:, [i for i, owner in enumerate(owners) if owner == feature]].sum(axis=1)
                               for feature in X.columns])
    return {'method': 'shap', 'explainer': type(explainer).__name__, 'output_scale': 'positive-class log-odds',
            'baseline': baseline, 'encoded_features': names, 'encoded_to_original': owners,
            'values_encoded': values.tolist(), 'values_original': grouped.tolist(),
            'model_outputs': np.asarray(output).tolist(), 'max_additivity_error': float(abs(residual).max()),
            'feature_summary': {feature: {'mean_absolute': float(np.abs(grouped[:, i]).mean()),
                                         'mean_signed': float(grouped[:, i].mean())}
                                for i, feature in enumerate(X.columns)},
            'reference_definition': ('Independent training-background distribution' if name == 'logistic_regression'
                                     else 'Tree-path-dependent cover statistics from fitted training rows'),
            'limitation': 'LR uses an independent training background; XGBoost uses tree-path-dependent training '
                          'cover. Correlated predictors and grouped one-hot columns require caution. '
                          'Summaries describe only sampled evaluation rows; reference conventions differ by model.'}


def _lime(model, X, train, explained, background, seed, name, samples):
    import numpy as np
    import pandas as pd
    from lime.lime_tabular import LimeTabularExplainer
    if 'impute' in model.named_steps:
        X = model.named_steps['impute'].transform(X)
    features = list(X.columns)
    training = X.iloc[train]
    observed = X.iloc[explained]
    encoded_categories = {c for block, _, columns in model.named_steps['encode'].transformers_ if block == 'categorical' for c in columns}
    categorical = [i for i, c in enumerate(features) if c in encoded_categories or c not in X.select_dtypes(include='number').columns]
    categories = {i: training.iloc[:, i].drop_duplicates().tolist() for i in categorical}
    # Unseen categories map to a value absent from training; fitted OHE ignores it.
    unknown = {i: (-1.0 if pd.api.types.is_numeric_dtype(training.iloc[:, i]) else '__MEMSTARA_UNSEEN__') for i in categorical}
    for i in categorical:
        while unknown[i] in categories[i]:
            unknown[i] = unknown[i] - 1 if isinstance(unknown[i], float) else unknown[i] + '_'
    def encode(frame):
        result = np.empty((len(frame), len(features)), dtype=float)
        for i, feature in enumerate(features):
            if i in categories:
                lookup = {value: j for j, value in enumerate(categories[i])}
                result[:, i] = frame[feature].map(lookup).fillna(len(lookup)).to_numpy()
            else:
                result[:, i] = frame[feature].to_numpy(dtype=float)
        return result
    def predict(values):
        frame = pd.DataFrame(values, columns=features)
        for i in categorical:
            labels = categories[i] + [unknown[i]]
            indices = np.rint(values[:, i]).astype(int)
            if np.any(indices < 0) or np.any(indices >= len(labels)):
                raise ValueError('LIME produced an invalid category code')
            frame[features[i]] = [labels[index] for index in indices]
        return model.predict_proba(frame)
    encoded = encode(observed)
    expected = model.predict_proba(observed)[:, 1]
    if not np.allclose(predict(encoded)[:, 1], expected, atol=1e-12, rtol=0):
        raise ValueError('LIME representation changed the fitted model prediction')
    explainer = LimeTabularExplainer(encode(training), feature_names=features, mode='classification',
        categorical_features=categorical, discretize_continuous=False, random_state=seed,
        class_names=['0', '1'], feature_selection='none', sample_around_instance=False,
        kernel_width=float(np.sqrt(len(features)) * .75))
    weights, locals_ = [], []
    for row in encoded:
        local = explainer.explain_instance(row, predict, labels=(1,), num_features=len(features),
                                           num_samples=samples, distance_metric='euclidean')
        weight = np.zeros(len(features))
        for index, value in local.as_map()[1]:
            weight[index] = value
        weights.append(weight)
        locals_.append({'intercept': float(local.intercept[1]), 'fidelity_r2': float(local.score),
                        'surrogate_prediction': float(np.asarray(local.local_pred).reshape(-1)[0])})
    weight_matrix = np.asarray(weights)
    return {'method': 'lime', 'explainer': 'LimeTabularExplainer', 'output_scale': 'positive-class probability',
            'representation': 'Original predictors: numeric units standardized by training distribution; '
                              'categorical weights describe matching the explained category.',
            'reference_scope': 'all training rows', 'samples_per_row': samples,
            'kernel_width': float(np.sqrt(len(features)) * .75), 'distance_metric': 'euclidean',
            'discretize_continuous': False, 'sampling_method': 'gaussian',
            'surrogate': 'LIME default weighted Ridge(alpha=1), all original predictors',
            'values_original': weight_matrix.tolist(), 'local_diagnostics': locals_,
            'categorical_codebook': categories, 'categorical_indices': categorical,
            'numeric_center': explainer.scaler.mean_.tolist(),
            'numeric_scale': explainer.scaler.scale_.tolist(),
            'model_outputs': expected.tolist(),
            'feature_summary': {feature: {'mean_absolute': float(np.abs(weight_matrix[:, i]).mean()),
                                         'mean_signed': float(weight_matrix[:, i].mean())}
                                for i, feature in enumerate(features)},
            'fidelity_r2': {'minimum': min(v['fidelity_r2'] for v in locals_),
                            'mean': float(np.mean([v['fidelity_r2'] for v in locals_]))},
            'limitation': 'LIME is a local surrogate with sampled neighborhoods. Weights and their sampled-row '
                          'averages are not global model coefficients or causal effects; correlated inputs '
                          'can yield unrealistic perturbations. Inspect local fidelity.'}


def calculate(model, X, train, test, seed, name, method, policy):
    import numpy as np
    for library, version in policy.get('versions', {}).items():
        if importlib.metadata.version(library) != version:
            raise ValueError('Explanation library changed after the run was frozen')
    if list(model.classes_) != [0, 1] or name not in ('logistic_regression', 'xgboost'):
        raise ValueError('Specialist evidence requires the fitted binary LR/XGBoost model')
    if len(X.columns) > policy['max_original_features']:
        raise ValueError('Too many original predictors for bounded specialist explanations')
    if not 1 <= policy['explained_rows'] <= 8 or not 1 <= policy['background_rows'] <= 32:
        raise ValueError('Invalid explanation row budget')
    if not 100 <= policy['lime_samples'] <= 512:
        raise ValueError('Invalid LIME sample budget')
    rng = np.random.default_rng(seed)
    background = np.sort(rng.choice(train, min(len(train), policy['background_rows']), replace=False))
    explained = np.sort(rng.choice(test, min(len(test), policy['explained_rows']), replace=False))
    if set(train) & set(test):
        raise ValueError('Explanation reference and evaluation partitions overlap')
    if method == 'shap':
        evidence = _shap(model, X, train, explained, background, seed, name)
    elif method == 'lime':
        evidence = _lime(model, X, train, explained, background, seed, name, policy['lime_samples'])
    else:
        raise ValueError('Unsupported specialist explanation method')
    evidence.update(seed=seed, model=name, features=list(X.columns), background_rows=background.tolist()
                    if method == 'shap' and name == 'logistic_regression' else train.tolist(),
                    explained_rows=explained.tolist())
    # Canonical finite JSON is required for disk, database and browser evidence.
    json.dumps(evidence, allow_nan=False)
    return evidence


def save(directory, X, artifacts, result, specification):
    from memstara.reproducibility import digest as file_digest
    policy = specification['policy']
    model_name = result['model']
    summaries = []
    for index, (model, train, test, _) in enumerate(artifacts):
        replicate = result['evaluation']['replicates'][index]
        for method in specification['methods']:
            item = {'method': method, 'model': model_name, 'replicate': index + 1,
                    'model_sha256': file_digest(directory / f'model-{index}.joblib'),
                    'split_id': replicate['split_id'], 'train_split_id': replicate['train_split_id'],
                    'dataset_sha256': result['evaluation']['dataset_sha256'],
                    'run_tag': specification['run_tag'], 'trial': specification['trial'],
                    'config_hash': specification['config_hash'], 'seed': replicate['seed']}
            try:
                evidence = calculate(model, X, train, test, replicate['seed'], model_name, method, policy)
                filename = f'xai-{method}-{index}.json'
                document = {**item, 'evidence': evidence}
                (directory / filename).write_text(json.dumps(document, indent=2, allow_nan=False))
                item.update(status='completed', artifact_path=str(directory / filename),
                            artifact_sha256=file_digest(directory / filename),
                            explanation_id=digest(document), explainer=evidence['explainer'],
                            output_scale=evidence['output_scale'], feature_summary=evidence['feature_summary'],
                            explained_count=len(evidence['explained_rows']),
                            reference_count=len(evidence['background_rows']), limitation=evidence['limitation'])
                for key in ('baseline', 'max_additivity_error', 'fidelity_r2', 'samples_per_row',
                            'representation', 'reference_definition'):
                    if key in evidence:
                        item[key] = evidence[key]
            except Exception as exc:
                # No library error message or patient value is sent to model agents.
                import traceback
                item.update(status='failed', error_type=type(exc).__name__,
                            frames=[{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                                    for f in traceback.extract_tb(exc.__traceback__)])
            summaries.append(item)
    result['specialist_xai'] = {'version': VERSION, 'request_sha256': digest(specification),
                               'status': ('completed' if all(i['status'] == 'completed' for i in summaries)
                                          else 'failed'),
                               'items': summaries}
    (directory / 'xai-request.json').write_text(json.dumps(specification, indent=2))



def verify_artifact(model, item, index):
    from memstara.paths import output_dir
    from memstara.reproducibility import digest as file_digest
    evidence = model['evaluation']['reproducibility']
    directory = Path(evidence['bundle_path']).resolve()
    directory.relative_to(output_dir().resolve())
    if file_digest(directory / 'manifest.json') != evidence['manifest_sha256']:
        raise ValueError('Specialist bundle manifest changed')
    manifest = json.loads((directory / 'manifest.json').read_text())
    path = Path(item['artifact_path'])
    if (path.is_symlink() or path.resolve().parent != directory
            or path.name != f"xai-{item['method']}-{index}.json"
            or file_digest(path) != item['artifact_sha256']
            or manifest['files'].get(path.name) != item['artifact_sha256']
            or manifest['files'].get(f'model-{index}.joblib') != item['model_sha256']
            or file_digest(directory / f'model-{index}.joblib') != item['model_sha256']):
        raise ValueError('Specialist artifact identity/hash mismatch')
    document = json.loads(path.read_text())
    if any(document.get(k) != item[k] for k in ('model', 'method', 'replicate', 'split_id', 'dataset_sha256')):
        raise ValueError('Specialist artifact metadata differs from its handoff')
    if digest(document) != item['explanation_id']:
        raise ValueError('Specialist explanation identity changed')

def handoff(snapshot, task, worker):
    """Select one specialist's evidence for the model selected by this task."""
    from memstara.combinations import task_books
    from memstara.interpretation_fanout import metadata
    spec = request(snapshot, task['trial'])
    if not spec:
        return None
    previous = metadata(task.get('evaluation'))
    branch = previous.get('interpretation_branch', {})
    books = task_books(snapshot, task['trial']).get('interpreter') or []
    suffix = worker.rsplit('#', 1)[-1]
    slot = int(suffix) - 1 if '#' in worker and suffix.isdigit() else 0
    skill = branch.get('skill') or books[min(slot, len(books) - 1)]
    if skill not in SKILLS:
        return None
    if skill not in spec['skills']:
        raise ValueError('Interpretation skill does not belong to the scheduled task')
    method = SKILLS[skill]
    models = previous.get('model_results', {})
    from memstara.ml_configuration import MODEL_SKILLS
    selected = [MODEL_SKILLS[name] for name in (task_books(snapshot, task['trial']).get('ml') or [])
                if name in MODEL_SKILLS]
    if len(selected) != 1:
        raise ValueError('Specialist Interpretation requires exactly one selected ML model skill')
    expected_model = selected[0]
    if set(models) != {expected_model}:
        raise ValueError('Specialist Interpretation received results for a non-selected ML model')
    outputs = {}
    for name, model in models.items():
        if model['model'] != name:
            raise ValueError('Cross-model evidence identity mismatch')
        xai = model.get('specialist_xai', {})
        if xai.get('status') != 'completed' or xai.get('request_sha256') != digest(spec):
            raise ValueError('Missing or mismatched specialist evidence')
        replicas = model['evaluation']['replicates']
        items = [item for item in xai['items'] if item['method'] == method]
        if len(items) != len(replicas):
            raise ValueError('Specialist evidence must cover every evaluated split')
        for index, (item, replica) in enumerate(zip(items, replicas, strict=True)):
            if (item['status'] != 'completed' or item['model'] != name or item['replicate'] != index + 1
                    or item['config_hash'] != snapshot['config_hash'] or item['run_tag'] != snapshot['run_tag']
                    or item['trial'] != task['trial'] or item['split_id'] != replica['split_id']
                    or item['train_split_id'] != replica['train_split_id']
                    or item['dataset_sha256'] != model['evaluation']['dataset_sha256']):
                raise ValueError('Explanation artifact belongs to another model/task/split')
        for index, item in enumerate(items):
            verify_artifact(model, item, index)
        outputs[name] = {key: model[key] for key in ('model', 'auc', 'features', 'evaluation', 'data_quality')}
        outputs[name]['attributions'] = items
    source = spec['skills'][skill]
    return {'version': VERSION, 'method': method, 'skill': skill, 'skill_source_sha256': source['source_sha256'],
            'task_id': task['task_id'], 'source_task_id': branch.get('source_task_id', task['task_id']),
            'run_tag': snapshot['run_tag'], 'trial': task['trial'], 'config_hash': snapshot['config_hash'],
            'models': outputs, 'instructions': 'Interpret only the selected model using this method. '
            'Do not introduce or compare an unrun model. '
            'Raw row data and individual attribution arrays remain in local artifacts.'}


def record_io(snapshot, task, worker, value, *, interpretation=None):
    """Append immutable exact handoff/output records without a second database path."""
    from memstara.paths import output_dir
    from memstara.paired_ml import atomic
    root = output_dir().resolve()
    source = Path(task['subset_path']).resolve()
    source.relative_to(root)
    directory = source.parent / 'interpretation_io'
    directory.mkdir(mode=0o700, exist_ok=True)
    payload = {'task': json.loads(json.dumps(task, default=str)), 'handoff': value, 'worker': worker,
               'skill': snapshot['specialist_xai_policy']['skills'][value['skill']]}
    if interpretation is not None:
        payload['interpretation'] = interpretation
    checksum = digest(payload)
    phase = "output" if interpretation is not None else "input"
    path = directory / f"task-{task['task_id']}-{phase}-{checksum}.json"
    if not path.exists():
        atomic(path, payload)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'phase': 'output' if interpretation is not None else 'input',
            'method': value['method'], 'skill': value['skill'], 'worker': worker,
            'model_explanation_ids': {name: [i['explanation_id'] for i in row['attributions']]
                                      for name, row in value['models'].items()}}


def replay(directory):
    """Replay attributions from trusted local model bundles; never refit estimators."""
    import joblib
    import numpy as np
    import pandas as pd
    from threadpoolctl import threadpool_limits
    from memstara.paths import output_dir
    from memstara.reproducibility import digest as file_digest
    directory = Path(directory).resolve()
    directory.relative_to(output_dir().resolve())
    manifest = json.loads((directory / 'manifest.json').read_text())
    for filename, checksum in manifest['files'].items():
        path = directory / filename
        if (Path(filename).name != filename or path.is_symlink()
                or not path.is_file() or file_digest(path) != checksum):
            raise ValueError('XAI replay bundle integrity mismatch')
    if manifest['code'].get('specialist_xai.py') != file_digest(Path(__file__)):
        raise ValueError('XAI replay implementation differs from the recorded source')
    spec = json.loads((directory / 'xai-request.json').read_text())
    if spec['version'] != VERSION:
        raise ValueError('Unsupported XAI replay version')
    for name, version in spec['policy']['versions'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('XAI replay library version differs')
    saved_environment = json.loads((directory / 'environment.json').read_text())
    for name in ('numpy', 'pandas', 'scipy', 'scikit-learn', 'xgboost', 'joblib', 'shap', 'lime'):
        if importlib.metadata.version(name) != saved_environment['packages'].get(name):
            raise ValueError('XAI replay numerical environment differs')
    frame = pd.read_csv(directory / 'input.csv')
    X = frame[manifest['predictors']]
    expected = json.loads((directory / 'result.json').read_text())
    checks = []
    with threadpool_limits(limits=1):
        for index, run in enumerate(expected['evaluation']['replicates']):
            # These are application-owned, hash-checked local bundles, not uploaded pickles.
            model = joblib.load(directory / f'model-{index}.joblib')
            arrays = np.load(directory / f'split-{index}.npz', allow_pickle=False)
            for method in spec['methods']:
                saved = json.loads((directory / f'xai-{method}-{index}.json').read_text())['evidence']
                actual = calculate(model, X, arrays['train'], arrays['test'], run['seed'],
                                   expected['model'], method, spec['policy'])
                checks.append({'method': method, 'model': expected['model'], 'replicate': index + 1,
                               'equal': digest(actual) == digest(saved)})
    return {'status': 'verified' if all(c['equal'] for c in checks) else 'mismatch',
            'scope': 'Same saved fitted models, inputs, implementation and SHAP/LIME versions; '
                     'no model refit or LLM call.',
            'checks': checks}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        value = replay(args.bundle)
    except Exception as exc:
        value = {'status': 'verification_failed', 'error_type': type(exc).__name__}
    print(json.dumps(value))
    raise SystemExit(0 if value['status'] == 'verified' else 1)


if __name__ == '__main__':
    main()
