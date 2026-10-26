"""Reject incomplete uploads; preserve the reader for historical model artifacts."""
import base64
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from memstara.dataset_upload import upload
from memstara.missing_values import TrainingImputer, POLICY
from memstara.research_inputs import inspect, register, prepare
from memstara.evaluation import score, DataQualityError
from memstara.reproducibility import replay


def payload(raw):
    return {'filename': '../../input.csv', 'content_base64': base64.b64encode(raw).decode()}


def test_upload_preserves_bytes_and_returns_no_patient_rows(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path))
    raw = b'a,b,target\n1,,private-label\n2,3,other\n'
    result = upload(payload(raw))
    assert Path(result['dataset_path']).read_bytes() == raw
    assert Path(result['dataset_path']).is_relative_to(tmp_path)
    assert result['columns_with_missing'] == {'b': 1}
    assert 'private-label' not in json.dumps(result)
    assert not (Path(result['dataset_path']).stat().st_mode & 0o077)


@pytest.mark.parametrize('raw', [b'', b'a,a\n1,2\n', b'a,b\n1\n', b'a,b\n', b'a,b\n1,\x00\n'])
def test_bad_csv_never_published(tmp_path, monkeypatch, raw):
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path))
    with pytest.raises(ValueError):
        upload(payload(raw))
    assert not (tmp_path / 'uploads').exists()


def test_training_values_only_and_explicit_numeric_categories():
    train = pd.DataFrame({'continuous': [2., 6., np.nan], 'binary': [1., 1., np.nan],
                          'code': [2., 3., 3.], 'text': ['a', 'b', None]})
    original = train.copy(deep=True)
    imputer = TrainingImputer(categorical_columns=('code',)).fit(train)
    assert imputer.fill_values_ == {'continuous': 4., 'binary': 1., 'code': 3., 'text': 'a'}
    test = pd.DataFrame({'continuous': [1000000., np.nan], 'binary': [0., np.nan],
                         'code': [2., np.nan], 'text': ['b', None]})
    filled = imputer.transform(test)
    assert filled.loc[1].tolist() == [4., 1., 3., 'a']
    pd.testing.assert_frame_equal(train, original)
    assert pd.isna(test.loc[1, 'continuous'])
    with pytest.raises(ValueError, match='No observed training'):
        TrainingImputer().fit(pd.DataFrame({'a': [np.nan, np.nan]}))


@pytest.fixture
def registered(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'outputs'))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    rng = np.random.default_rng(14)
    frame = pd.DataFrame({'a': rng.normal(size=80), 'b': rng.normal(size=80),
                          'c': [0, 1]*40, 'd': [2, 3, 4, 5]*20, 'target': [0, 1]*40})
    frame.loc[[2, 12, 21, 35], 'a'] = np.nan
    path = tmp_path / 'data.csv'
    frame.to_csv(path, index=False)
    return {'name': 'Synthetic upload', 'dataset_path': str(path), 'knowledge_mode': 'llm_only',
            'target': {'column': 'target', 'description': 'Example', 'positive_label': '1',
                       'negative_label': '0', 'prediction_time': 'Baseline'}, 'excluded_columns': []}


def test_old_consent_cannot_bypass_input_checks(registered):
    original = Path(registered['dataset_path']).read_bytes()
    assert not inspect(registered)['input_checks_passed']
    with pytest.raises(ValueError, match='Imputation is disabled'):
        register({**registered, 'missing_policy': POLICY})
    assert Path(registered['dataset_path']).read_bytes() == original


@pytest.mark.parametrize('engine', ['logistic_regression', 'xgboost'])
def test_missing_values_block_every_classifier(registered, engine):
    path = Path(registered['dataset_path'])
    with pytest.raises(DataQualityError, match='missing predictor'):
        score(path, 'target', {'engine': engine}, explain=False)
    with pytest.raises(DataQualityError, match='Imputation is disabled'):
        score(path, 'target', {'engine': engine}, missing_policy=POLICY, explain=False)


def test_target_missing_blocks_input_checks(registered):
    path = Path(registered['dataset_path'])
    frame = pd.read_csv(path)
    frame.loc[0, 'target'] = np.nan
    frame.to_csv(path, index=False)
    assert not inspect(registered)['input_checks_passed']
    with pytest.raises(DataQualityError, match='Target labels'):
        score(path, 'target', {}, explain=False)


def test_excluding_column_does_not_hide_missing_csv_values(registered):
    registered['excluded_columns'] = ['a']
    problems = inspect(registered)['issues']
    assert any(p['code'] == 'missing_values' for p in problems)
