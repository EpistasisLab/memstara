"""Input failures must not create paid runs or silently change source data."""

import pandas as pd
import pytest

from memstara.evaluation import DataQualityError, preflight, validate_clean_dataset


def test_missing_diagnostic_is_aggregate_only_and_preserves_source(tmp_path):
    path = tmp_path / 'private-file.csv'
    path.write_text('private_feature,outcome\n,0\n2,0\n3,1\n4,1\n')
    original = path.read_bytes()
    with pytest.raises(DataQualityError, match='1 missing predictor values across 1 columns') as error:
        preflight(path, 'outcome', {'engine': 'logistic_regression'})
    assert 'private_feature' not in str(error.value)
    assert 'private-file' not in str(error.value)
    assert original == path.read_bytes()


@pytest.mark.parametrize('header', ['x,x,outcome', 'x,,outcome'])
def test_ambiguous_headers_are_rejected_before_pandas_renames_them(tmp_path, header):
    path = tmp_path / 'data.csv'
    path.write_text(header + '\n1,2,0\n2,3,1\n')
    with pytest.raises(DataQualityError, match='unique names'):
        validate_clean_dataset(path, 'outcome')


def test_unrepresentative_holdout_is_rejected_before_training(tmp_path):
    path = tmp_path / 'data.csv'
    pd.DataFrame({'x': range(100), 'outcome': [0] * 98 + [1] * 2}).to_csv(path, index=False)
    with pytest.raises(DataQualityError, match='represent both classes'):
        preflight(path, 'outcome', {'test_size': .1})


def test_invalid_input_does_not_create_a_run_or_spawn_process(tmp_path, monkeypatch):
    from memstara.control import service
    path = tmp_path / 'data.csv'
    path.write_text('x,outcome\n,0\n2,0\n3,1\n4,1\n')
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(path))
    monkeypatch.setattr(service, 'skills', lambda: [])
    monkeypatch.setattr(service, 'playbooks', lambda: {'playbooks': [], 'stages': []})
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid input must not create run artifacts or spawn a process')
    monkeypatch.setattr(service, 'new_run_dir', forbidden)
    monkeypatch.setattr(service.RUNS, 'start', forbidden)
    responses = []
    handler = object.__new__(service.Handler)
    handler._send = lambda status, body: responses.append((status, body))
    service.Handler._start(handler, {'y_column': 'outcome', 'evaluation': {'engine': 'logistic_regression'}})
    assert responses[0][0] == 422
    assert responses[0][1]['code'] == 'input_validation_failed'
    assert responses[0][1]['error'].startswith('Run not started.')


def test_native_xgboost_missing_values_survive_fit_cv_and_shap(tmp_path):
    import json
    import numpy as np
    from memstara.evaluation import score
    rng = np.random.default_rng(5)
    frame = pd.DataFrame({'x': rng.normal(size=100), 'kind': ['a', 'b'] * 50,
                          'empty': np.nan, 'outcome': [0, 1] * 50})
    frame.loc[::3, 'x'] = np.nan
    frame.loc[::4, 'kind'] = np.nan
    path = tmp_path / 'data.csv'
    frame.to_csv(path, index=False)
    original = path.read_bytes()
    preflight(path, 'outcome', {'engine': 'xgboost'})
    result = score(path, 'outcome', {'engine': 'xgboost', 'folds': 2, 'search_trials': 2, 'replicates': 2})
    assert path.read_bytes() == original
    assert result['data_quality']['missing_predictor_cells'] == int(frame.drop(columns='outcome').isna().sum().sum())
    assert result['data_quality']['missing_value_policy'] == 'native_xgboost'
    assert result['explanation']['shap']['method'] == 'XGBoost TreeSHAP'
    assert all(r['n_train'] + r['n_test'] == len(frame) for r in result['evaluation']['replicates'])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('bad_value', [float('inf'), float('-inf')])
def test_native_policy_still_rejects_infinity(tmp_path, bad_value):
    path = tmp_path / 'data.csv'
    pd.DataFrame({'x': [bad_value, 2, 3, 4], 'outcome': [0, 0, 1, 1]}).to_csv(path, index=False)
    with pytest.raises(DataQualityError, match='non-finite'):
        preflight(path, 'outcome', {'engine': 'xgboost'})
