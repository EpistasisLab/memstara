"""Regression coverage for sparse predictors and supplementary explanation failures."""
import json

import numpy as np
import pandas as pd
import pytest

from memstara import evaluation


@pytest.fixture
def sparse_dataset(tmp_path):
    n = 400
    rare = np.zeros(n)
    rare[:4] = 1
    sparse_continuous = np.zeros(n)
    sparse_continuous[:12] = np.arange(1, 13)
    path = tmp_path / 'sparse.csv'
    pd.DataFrame({'rare': rare, 'sparse_continuous': sparse_continuous,
                  'constant': np.zeros(n), 'target': np.arange(n) % 2}).to_csv(path, index=False)
    return path


def test_sparse_predictors_keep_metrics_and_honest_explanations(sparse_dataset):
    result = evaluation.score(sparse_dataset, 'target', {'engine': 'xgboost'})
    assert np.isfinite(result['auc'])
    explanation = result['explanation']
    curves = {c['feature']: c for c in explanation['partial_dependence']}
    assert curves['rare']['values'] == [0.0, 1.0]
    assert 'constant' not in curves
    assert 'sparse_continuous' not in curves
    skipped = {c['feature'] for c in explanation['skipped_response_curves']}
    assert skipped == {'constant', 'sparse_continuous'}
    assert explanation['status'] == 'partial'
    assert explanation['shap']['method'] == 'XGBoost TreeSHAP'
    assert all(len(c['values']) >= 2 for c in curves.values())
    json.dumps(result, allow_nan=False)


def test_optional_explanation_failure_preserves_measured_metrics(sparse_dataset, monkeypatch):
    baseline = evaluation.score(sparse_dataset, 'target', {'engine': 'xgboost'})

    def fail(*args, **kwargs):
        raise ValueError('sensitive patient value must never be returned')

    monkeypatch.setattr(evaluation, '_explain', fail)
    result = evaluation.score(sparse_dataset, 'target', {'engine': 'xgboost'})
    assert result['auc'] == baseline['auc']
    assert result['evaluation']['replicates'] == baseline['evaluation']['replicates']
    assert result['explanation']['status'] == 'failed'
    assert result['feature_importance'] == {}
    assert 'sensitive patient' not in json.dumps(result)
    assert result['data_quality']['warnings']
    json.dumps(result, allow_nan=False)


def test_shap_failure_preserves_other_explanations(sparse_dataset, monkeypatch):
    import xgboost
    predict = xgboost.Booster.predict

    def fail_contributions(self, *args, **kwargs):
        if kwargs.get('pred_contribs'):
            raise ValueError('private data')
        return predict(self, *args, **kwargs)

    monkeypatch.setattr(xgboost.Booster, 'predict', fail_contributions)
    result = evaluation.score(sparse_dataset, 'target', {'engine': 'xgboost'})
    assert np.isfinite(result['auc'])
    assert result['feature_importance']
    assert result['explanation']['partial_dependence']
    assert result['explanation']['shap']['status'] == 'not_available'
    assert result['explanation']['status'] == 'partial'
    assert 'private data' not in json.dumps(result)


def test_training_failure_is_not_misreported_as_success(sparse_dataset, monkeypatch):
    from sklearn.pipeline import Pipeline

    def fail(*args, **kwargs):
        raise ValueError('training failed')

    monkeypatch.setattr(Pipeline, 'fit', fail)
    with pytest.raises(ValueError, match='training failed'):
        evaluation.score(sparse_dataset, 'target', {'engine': 'xgboost'})


def test_mcp_persists_metrics_and_explanation_failure(sparse_dataset, monkeypatch):
    from memstara.mcp_servers.ml import train_and_score

    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(sparse_dataset.parent))

    def fail(*args, **kwargs):
        raise ValueError('private diagnostic')

    monkeypatch.setattr(evaluation, '_explain', fail)
    result = json.loads(train_and_score(str(sparse_dataset), 'target', engine='xgboost'))
    artifact = json.loads(sparse_dataset.with_suffix('.evaluation.json').read_text())
    assert artifact == result
    assert result.get('status') != 'failed'
    assert np.isfinite(result['auc'])
    assert result['explanation']['status'] == 'failed'
    assert 'private diagnostic' not in json.dumps(result)
