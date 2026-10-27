"""Real fits verify split/model seed equality and preserve historical behavior."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from memstara import evaluation
from memstara.reproducibility import replay


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {})
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'outputs'))
    rng = np.random.default_rng(12)
    path = tmp_path / 'numeric.csv'
    pd.DataFrame({'x': rng.normal(size=100), 'z': rng.normal(size=100),
                  'target': [0, 1] * 50}).to_csv(path, index=False)
    return path


@pytest.mark.parametrize('engine', ['logistic_regression', 'random_forest', 'xgboost'])
@pytest.mark.parametrize('configured', [False, True])
def test_each_replicate_classifier_uses_its_split_seed(dataset, engine, configured):
    configuration = {'parameters': {'random_state': 999}, 'scale_numeric': False,
                     'threshold': .5} if configured else None
    result = evaluation.score(dataset, 'target', {'engine': engine, 'seed': 123, 'replicates': 2},
                              configuration=configuration, explain=False)
    assert result['evaluation']['replicate_seeds'] == [123, 124]
    directory = Path(result['evaluation']['reproducibility']['bundle_path'])
    manifest = json.loads((directory / 'manifest.json').read_text())
    assert manifest['classifier_seed_policy'] == 'split_seed_v1'
    for index, record in enumerate(result['evaluation']['replicates']):
        expected = 123 + index
        assert record['seed'] == record['parameters']['random_state'] == record['effective_random_state'] == expected
        assert record['requested_random_state'] == (999 if configured else expected)
        model = joblib.load(directory / f'model-{index}.joblib')
        assert model.named_steps['model'].random_state == expected
    if configured:
        assert configuration['parameters']['random_state'] == 999
    assert replay(directory)['status'] == 'verified'


def test_historical_configured_seed_is_preserved(dataset, monkeypatch):
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {'run_tag': 'historical'})
    result = evaluation.score(dataset, 'target', {'engine': 'logistic_regression', 'seed': 123},
        configuration={'parameters': {'random_state': 999}, 'scale_numeric': False, 'threshold': .5},
        explain=False)
    record = result['evaluation']['replicates'][0]
    assert record['seed'] == 123 and record['effective_random_state'] == 999
    assert record['classifier_seed_policy'] == 'configured_seed_v1'
    assert replay(Path(result['evaluation']['reproducibility']['bundle_path']))['status'] == 'verified'


def test_frozen_policy_does_not_depend_on_current_defaults():
    assert evaluation.classifier_seed_policy({'run_tag': 'old'}) == 'configured_seed_v1'
    assert evaluation.classifier_seed_policy({'classifier_seed_policy': 'split_seed_v1'}) == 'split_seed_v1'
