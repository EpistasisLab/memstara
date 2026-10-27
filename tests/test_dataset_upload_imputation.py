"""Optional training-only imputation requires explicit consent."""
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


def test_consent_allows_predictor_missing_and_preserves_source(registered):
    original = Path(registered['dataset_path']).read_bytes()
    assert not inspect(registered)['input_checks_passed']
    saved = register({**registered, 'missing_policy': POLICY})
    assert saved['input_checks_passed']
    profile = prepare(saved['id'])
    assert profile['configuration']['missing_policy'] == POLICY
    assert Path(registered['dataset_path']).read_bytes() == original


@pytest.mark.parametrize('engine', ['logistic_regression', 'xgboost'])
def test_missing_values_block_every_classifier(registered, engine):
    path = Path(registered['dataset_path'])
    with pytest.raises(DataQualityError, match='missing predictor'):
        score(path, 'target', {'engine': engine}, explain=False)
    result = score(path, 'target', {'engine': engine}, missing_policy=POLICY, explain=False, persist=False)
    assert result['data_quality']['missing_value_policy'] == POLICY


def test_target_missing_blocks_input_checks(registered):
    path = Path(registered['dataset_path'])
    frame = pd.read_csv(path)
    frame.loc[0, 'target'] = np.nan
    frame.to_csv(path, index=False)
    assert not inspect(registered)['input_checks_passed']
    with pytest.raises(DataQualityError, match='Target labels'):
        score(path, 'target', {}, explain=False)


def test_excluded_predictors_do_not_require_imputation(registered):
    registered['excluded_columns'] = ['a']
    problems = inspect(registered)['issues']
    assert not any(p['code'] == 'missing_values' for p in problems)


def test_consent_does_not_allow_empty_predictor_or_target(registered):
    path = Path(registered['dataset_path'])
    frame = pd.read_csv(path)
    frame['a'] = np.nan
    frame.to_csv(path, index=False)
    assert any(p['code'] == 'empty_predictors' for p in inspect({**registered, 'missing_policy': POLICY})['issues'])
    with pytest.raises(DataQualityError, match='no observed values'):
        score(path, 'target', {}, missing_policy=POLICY, explain=False)
    frame['a'] = 5.
    frame.loc[0, 'target'] = np.nan
    frame.to_csv(path, index=False)
    assert not inspect({**registered, 'missing_policy': POLICY})['input_checks_passed']
    with pytest.raises(DataQualityError, match='Target labels'):
        score(path, 'target', {}, missing_policy=POLICY, explain=False)


def test_imputer_is_fitted_inside_each_cv_fold(registered, monkeypatch):
    from memstara.evaluation import validate, evaluation_splits
    frame = pd.read_csv(registered['dataset_path'])
    seen = []
    original = TrainingImputer.fit
    def fit(self, X, y=None):
        seen.append(set(X.index))
        return original(self, X, y)
    monkeypatch.setattr(TrainingImputer, 'fit', fit)
    plan = validate({'engine': 'logistic_regression', 'replicates': 1, 'folds': 3})
    _, train, test = evaluation_splits(frame.target, plan)[0]
    score(Path(registered['dataset_path']), 'target', plan, missing_policy=POLICY, explain=False, persist=False)
    assert seen
    assert all(indices <= set(train) and not indices.intersection(test) for indices in seen)
    assert any(len(indices) < len(train) for indices in seen)
    assert any(indices == set(train) for indices in seen)


def test_consent_preserves_incomplete_predictors_in_catalog(registered):
    from memstara.pipeline.feature_context import freeze_feature_context
    context = freeze_feature_context(Path(registered['dataset_path']), 'target', require_complete=True, missing_policy=POLICY)
    assert 'a' in [f['column'] for f in context['features']]
    assert context['eligibility']['excluded_columns'] == []


def test_whitespace_and_case_insensitive_missing_tokens(registered):
    from memstara.evaluation import validate_clean_dataset
    path = Path(registered['dataset_path'])
    frame = pd.read_csv(path).astype({'a': 'object'})
    frame.loc[0, 'a'] = '   '
    frame.loc[1, 'a'] = ' NaN '
    frame.to_csv(path, index=False)
    assert inspect({**registered, 'missing_policy': POLICY})['input_checks_passed']
    result = validate_clean_dataset(path, 'target', missing_policy=POLICY, require_numeric=True)
    assert result.a.iloc[:2].isna().all()


def test_consented_study_freezes_and_informs_ml_agent(registered, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from memstara.research_inputs import activate
    from memstara.pipeline.snapshot import freeze
    from memstara.ml_configuration import context, validate as validate_ml
    saved = register({**registered, 'missing_policy': POLICY})
    profile = prepare(saved['id'])
    monkeypatch.setattr('os.environ', dict(__import__('os').environ))
    activate(profile)
    run = tmp_path / 'run'
    run.mkdir()
    args = SimpleNamespace(evaluation='{}', y_column='target', baseline_columns='[]',
                           run_tag='consent-test', question='', hypothesis_agents=1,
                           trials=1, waves=1, research_profile=profile)
    frozen = freeze(args, run, {'ml': ['ml_logistic_regression']})
    assert frozen['missing_value_policy'] == POLICY
    assert 'a' in [f['column'] for f in frozen['feature_context']['features']]
    specification = context(frozen, frozen['evaluation'])
    assert 'User approved imputation' in specification['preprocessing_contract']
    proposal = {**specification['proposal_template'], 'rationale': 'Verify consented training-only imputation'}
    validate_ml(proposal, frozen, frozen['evaluation'])
