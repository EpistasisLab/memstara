"""Local ML replay bundles. No credentials or patient rows are returned to agents.

Run with: python -m memstara.reproducibility /absolute/path/to/bundle
Replay retrains from CSV, never unpickles a supplied model or executes archived code.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment() -> dict:
    from threadpoolctl import threadpool_info
    # The matcher may load PyTorch into the controller. It is not used by any
    # supported ML estimator and must not make a clean replay process incompatible.
    pools = [{**{k: v for k, v in pool.items() if k != 'filepath'},
              'library_sha256': digest(Path(pool['filepath']))}
             for pool in threadpool_info() if 'torch' not in Path(pool['filepath']).parts]
    return {
        'python': platform.python_version(), 'system': platform.system(),
        'machine': platform.machine(), 'platform': platform.platform(),
        'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()
                     if d.metadata.get('Name')},
        'thread_pools': sorted(pools, key=lambda pool: json.dumps(pool, sort_keys=True)),
        'thread_settings': {k: os.environ.get(k) for k in (
            'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')},
    }


def save_bundle(source, target, plan, predictors, fixed_trials, partition, artifacts, result, *,
                feature_selection=None, data_allocation=None, configuration=None, agent_plan=None, xai_request=None,
                cv_artifacts=None):
    import joblib
    import numpy as np
    import pandas as pd
    from io import BytesIO
    from sklearn.base import clone
    from sklearn.model_selection import StratifiedKFold
    from memstara.paths import DEFAULT_OUTPUT_DIR

    root = Path(os.environ.get('MEMSTARA_OUTPUT_DIR') or DEFAULT_OUTPUT_DIR) / 'reproducibility'
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='ml-', dir=root))
    (directory / 'input.csv').write_bytes(source)
    from memstara.research_inputs import MISSING
    frame = pd.read_csv(BytesIO(source), na_values=list(MISSING))
    X, y = frame[predictors], frame[target]
    checks = []
    for index, (model, train, test, probability) in enumerate(artifacts):
        joblib.dump(model, directory / f'model-{index}.joblib')
        arrays = dict(train=train, test=test, probability=probability, labels=y.iloc[test].to_numpy())
        recorded = result['evaluation']['replicates'][index]
        if recorded['cv_folds']:
            cv = StratifiedKFold(recorded['cv_folds'], shuffle=True, random_state=recorded['seed'])
            for fold, (fit, validate) in enumerate(cv.split(X.iloc[train], y.iloc[train])):
                arrays[f'cv_{fold}_train'] = train[fit]
                arrays[f'cv_{fold}_validation'] = train[validate]
        np.savez_compressed(directory / f'split-{index}.npz', **arrays)
        if cv_artifacts and cv_artifacts[index] is not None:
            np.savez_compressed(directory / f'cv-predictions-{index}.npz',
                                training_rows=train, **cv_artifacts[index])
        # Verify fresh fitting, not merely loading the already-fitted estimator.
        try:
            repeated = clone(model).fit(X.iloc[train], y.iloc[train]).predict_proba(X.iloc[test])[:, 1]
            checks.append({'replicate': index + 1, 'status': 'verified' if np.array_equal(
                probability, repeated) else 'mismatch'})
        except Exception as exc:
            checks.append({'replicate': index + 1, 'status': 'verification_failed',
                           'error_type': type(exc).__name__})
    if xai_request:
        from memstara.specialist_xai import save
        save(directory, X, artifacts, result, xai_request)
    code = {}
    sources: tuple[str, ...] = ('evaluation.py', 'reproducibility.py', 'missing_values.py', 'preprocessing_policy.py')
    if agent_plan:
        sources += ('ml_configuration.py', 'paired_ml.py', 'comparisons.py', 'data_allocation.py')
    if result['evaluation'].get('metrics_policy'):
        sources += ('performance_metrics.py',)
    if xai_request:
        sources += ('specialist_xai.py',)
    for name in sources:
        original = Path(__file__).with_name(name)
        (directory / name).write_bytes(original.read_bytes())
        code[name] = digest(original)
    if agent_plan:
        (directory / 'ml-plan.json').write_text(json.dumps(agent_plan, indent=2))
    if data_allocation:
        (directory / 'data-allocation.json').write_text(json.dumps(data_allocation, indent=2))
    if feature_selection:
        write_selection = directory / 'feature-selection.json'
        write_selection.write_text(json.dumps(feature_selection, indent=2))
    (directory / 'environment.json').write_text(json.dumps(environment(), indent=2))
    (directory / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    manifest = {
        'version': 1, 'target': target, 'predictors': predictors, 'plan': plan,
        'fixed_trials': fixed_trials, 'partition': partition, 'code': code,
        'schema': {str(k): str(v) for k, v in frame.dtypes.items()},
        'target_classes': [0, 1], 'decision_threshold': configuration['threshold'] if configuration else .5,
        'configuration': configuration,
        'classifier_seed_policy': result['evaluation'].get('classifier_seed_policy', 'configured_seed_v1'),
        'metrics_policy': result['evaluation'].get('metrics_policy', 'legacy_auc_only'),
        'preprocessing_policy': result.get('data_quality', {}).get('preprocessing_policy', 'legacy_encoding_v1'),
        'imputation_categories': result.get('data_quality', {}).get('imputation_categories', []),
        'predictor_types': result.get('data_quality', {}).get('predictor_types', {}),
        'missing_policy': result.get('data_quality', {}).get('missing_value_policy', 'reject'),
        'files': {p.name: digest(p) for p in directory.iterdir() if p.is_file()},
        'verification': checks,
    }
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False))
    for file in directory.iterdir():
        file.chmod(0o600)
    return {
        'status': 'verified' if all(c['status'] == 'verified' for c in checks) else 'not_verified',
        'method': 'Independent refit of each selected model; exact hold-out probability comparison',
        'scope': 'Same saved input, split, preprocessing, parameters and current software/hardware environment. '
                 'This does not establish robustness across different splits or reproduce LLM text/SHAP.',
        'bundle_path': str(directory.resolve()), 'replicates': checks,
        'manifest_sha256': digest(directory / 'manifest.json'),
    }


def replay(directory: Path) -> dict:
    from memstara.evaluation import score
    directory = directory.resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('version') != 1:
        return {'status': 'unsupported_bundle'}
    for name, expected in manifest['files'].items():
        if Path(name).name != name or not (directory / name).is_file() or digest(directory / name) != expected:
            return {'status': 'integrity_mismatch'}
    for name, expected in manifest['code'].items():
        allowed = (
            "evaluation.py",
            "reproducibility.py",
            "ml_configuration.py",
            "paired_ml.py",
            "comparisons.py",
            "data_allocation.py",
            "specialist_xai.py",
            "missing_values.py",
            "preprocessing_policy.py",
            "performance_metrics.py",
        )
        if name not in allowed or digest(Path(__file__).with_name(name)) != expected:
            return {'status': 'code_mismatch'}
    # Load the evaluation libraries before recording native thread pools, as in score().
    from memstara.evaluation import model_for
    model_for(manifest['plan']['engine'], manifest['plan']['seed'])
    if environment() != json.loads((directory / 'environment.json').read_text()):
        return {'status': 'environment_mismatch'}
    expected = json.loads((directory / 'result.json').read_text())
    actual = score(directory / 'input.csv', manifest['target'], manifest['plan'],
                   missing_policy=manifest.get('missing_policy', 'reject'),
                   imputation_categories=manifest.get('imputation_categories', []),
                   predictor_types=manifest.get('predictor_types', {}),
                   predictors=manifest['predictors'], fixed_trials=manifest['fixed_trials'],
                   partition=manifest['partition'], persist=False, explain=False,
                   configuration=manifest.get('configuration'),
                   preprocessing_policy=manifest.get('preprocessing_policy', 'legacy_encoding_v1'),
                   seed_policy=manifest.get('classifier_seed_policy', 'configured_seed_v1'),
                   metrics_policy=manifest.get('metrics_policy', 'legacy_auc_only'))
    equal = (actual['evaluation']['replicates'] == expected['evaluation']['replicates']
             and actual['features'] == expected['features'] and actual['auc'] == expected['auc'])
    status = {'status': 'verified' if equal else 'mismatch',
              'method': 'Full evaluation replay, including candidate selection, splits, predictions and metrics'}
    (directory / 'replay-verification.json').write_text(json.dumps(status, indent=2))
    (directory / 'replay-verification.json').chmod(0o600)
    return status


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        result = replay(args.bundle)
    except Exception as exc:
        result = {'status': 'verification_failed', 'error_type': type(exc).__name__}
    print(json.dumps(result))
    raise SystemExit(0 if result['status'] == 'verified' else 1)


if __name__ == '__main__':
    main()
