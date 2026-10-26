"""Real offline refits; no LLM calls or clinical data."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from memstara.evaluation import DataQualityError, discovery_partition, score
from memstara.reproducibility import replay


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'outputs'))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    # Historical encoded artifacts must remain replayable under their frozen policy.
    from memstara import evaluation
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {'run_tag': 'historical-encoding'})
    rng = np.random.default_rng(8)
    path = tmp_path / 'synthetic.csv'
    pd.DataFrame({'a': rng.normal(size=80), 'category': ['a', 'b', 'c', 'a'] * 20,
                  'target': [0, 1] * 40}).to_csv(path, index=False)
    return path


def test_missing_evaluation_splits_fail_before_persisting_results(cohort, monkeypatch):
    from memstara import evaluation

    monkeypatch.setattr(evaluation, 'evaluation_splits', lambda *args, **kwargs: iter(()))
    with pytest.raises(DataQualityError, match='at least one train/test split'):
        score(cohort, 'target', {'engine': 'logistic_regression'}, explain=False)
    assert not (cohort.parent / 'outputs').exists()


@pytest.mark.parametrize('engine', ['xgboost', 'random_forest', 'logistic_regression'])
def test_all_engines_replay_saved_input_after_original_removed(cohort, engine):
    partition = discovery_partition(pd.read_csv(cohort)['target'], 42)
    result = score(cohort, 'target', {'engine': engine, 'replicates': 2, 'search_trials': 2},
                   partition=partition, explain=False)
    evidence = result['evaluation']['reproducibility']
    assert evidence['status'] == 'verified'
    directory = Path(evidence['bundle_path'])
    manifest = json.loads((directory / 'manifest.json').read_text())
    split = np.load(directory / 'split-0.npz')
    assert set(split['train']) | set(split['test']) == set(partition['exploration_rows'])
    assert manifest['target'] == 'target'
    assert manifest['predictors'] == ['a', 'category']
    cohort.unlink()
    assert replay(directory)['status'] == 'verified'
    assert (directory.stat().st_mode & 0o777) == 0o700


def test_tampered_input_is_rejected(cohort):
    result = score(cohort, 'target', {'engine': 'logistic_regression'}, explain=False)
    directory = Path(result['evaluation']['reproducibility']['bundle_path'])
    (directory / 'input.csv').write_text('corrupted')
    assert replay(directory)['status'] == 'integrity_mismatch'


def test_explained_result_replays_in_a_new_process(cohort):
    result = score(cohort, 'target', {'engine': 'xgboost'})
    process = subprocess.run([sys.executable, '-m', 'memstara.reproducibility',
                              result['evaluation']['reproducibility']['bundle_path']],
                             capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stdout
    assert json.loads(process.stdout)['status'] == 'verified'


def test_environment_change_is_not_silently_accepted(cohort, monkeypatch):
    result = score(cohort, 'target', {'engine': 'logistic_regression'}, explain=False)
    monkeypatch.setenv('OMP_NUM_THREADS', '7')
    assert replay(Path(result['evaluation']['reproducibility']['bundle_path']))['status'] == 'environment_mismatch'


def test_refit_failure_never_claims_verified(cohort, monkeypatch):
    import sklearn.base
    from sklearn.pipeline import Pipeline
    original = sklearn.base.clone
    def fail(*args, **kwargs):
        if isinstance(args[0], Pipeline):
            raise RuntimeError('sensitive value')
        return original(*args, **kwargs)
    monkeypatch.setattr(sklearn.base, 'clone', fail)
    result = score(cohort, 'target', {'engine': 'logistic_regression'}, explain=False)
    evidence = result['evaluation']['reproducibility']
    assert evidence['status'] == 'not_verified'
    assert 'sensitive value' not in json.dumps(evidence)
