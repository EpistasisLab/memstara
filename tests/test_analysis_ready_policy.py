"""Real sklearn/XGBoost fits for the new input contract; no provider calls."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from memstara import evaluation, ml_configuration
from memstara.preprocessing_policy import VERSION, analysis_ready
from memstara.reproducibility import replay


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {'preprocessing_policy': VERSION})
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'outputs'))
    rng = np.random.default_rng(7)
    frame = pd.DataFrame({'x': rng.normal(100, 20, 80), 'z': rng.normal(size=80), 'y': [0, 1]*40})
    path = tmp_path / 'input.csv'
    frame.to_csv(path, index=False)
    return path


def test_policy_preserves_historical_snapshots():
    assert analysis_ready({})
    assert not analysis_ready({'run_tag': 'historical'})
    assert analysis_ready({'preprocessing_policy': VERSION})
    with pytest.raises(ValueError):
        analysis_ready({'preprocessing_policy': 'unknown'})


@pytest.mark.parametrize('engine', ['logistic_regression', 'xgboost'])
def test_numeric_values_order_and_replay_are_unchanged(prepared, engine):
    original = prepared.read_bytes()
    result = evaluation.score(prepared, 'y', {'engine': engine}, explain=False)
    directory = Path(result['evaluation']['reproducibility']['bundle_path'])
    model = joblib.load(directory / 'model-0.joblib')
    frame = pd.read_csv(prepared).drop(columns='y')
    np.testing.assert_array_equal(model.named_steps['encode'].transform(frame), frame.to_numpy())
    assert list(model.named_steps['encode'].get_feature_names_out()) == list(frame.columns)
    assert result['data_quality']['preprocessing_policy'] == VERSION
    assert replay(directory)['status'] == 'verified'
    assert prepared.read_bytes() == original
    from memstara.specialist_xai import _mapping, _shap
    assert _mapping(model.named_steps['encode'], list(frame.columns)) == (list(frame.columns), list(frame.columns))
    splits = np.load(directory / 'split-0.npz')
    evidence = _shap(model, frame, splits['train'], splits['test'][:2], splits['train'][:8], 42, engine)
    assert evidence['max_additivity_error'] < 1e-4


def test_strings_rejected_without_exposing_values(prepared):
    frame = pd.read_csv(prepared)
    frame['z'] = 'private-value'
    frame.to_csv(prepared, index=False)
    with pytest.raises(evaluation.DataQualityError, match='Encode or exclude columns: z') as exc:
        evaluation.score(prepared, 'y', {}, explain=False)
    assert 'private-value' not in str(exc.value)


def test_scaling_proposal_rejected_before_fit(prepared):
    with pytest.raises(evaluation.DataQualityError, match='scale_numeric must be false'):
        evaluation.score(prepared, 'y', {}, configuration={'scale_numeric': True})


def test_context_disallows_scaling():
    snapshot = {'preprocessing_policy': VERSION, '_selected_ml_primary': 'logistic_regression'}
    context = ml_configuration.context(snapshot, evaluation.validate({}))
    assert context['editable_common_settings']['scale_numeric'] == [False]
    assert context['proposal_template']['models']['logistic_regression']['scale_numeric'] is False


def test_agent_cannot_reenable_scaling():
    snapshot = {'preprocessing_policy': VERSION, '_selected_ml_primary': 'logistic_regression'}
    plan = evaluation.validate({})
    proposal = ml_configuration.context(snapshot, plan)['proposal_template']
    proposal['rationale'] = 'Synthetic configuration'
    proposal['models']['logistic_regression']['scale_numeric'] = True
    with pytest.raises(ValueError, match='scale_numeric must be false'):
        ml_configuration.validate(proposal, snapshot, plan)


def test_user_override_cannot_reenable_scaling():
    snapshot = {'preprocessing_policy': VERSION, '_selected_ml_primary': 'logistic_regression',
                'ml_overrides': {'version': 1, 'models': {'logistic_regression': {'scale_numeric': True}}}}
    with pytest.raises(ValueError, match='remove scale_numeric overrides'):
        ml_configuration.context(snapshot, evaluation.validate({}))


@pytest.mark.parametrize('engine', ['logistic_regression', 'xgboost'])
@pytest.mark.parametrize('policy', ['reject', 'impute_train_v1'])
def test_missing_values_never_reach_training(prepared, engine, policy):
    frame = pd.read_csv(prepared)
    frame.loc[0, 'x'] = np.nan
    frame.to_csv(prepared, index=False)
    original = prepared.read_bytes()
    with pytest.raises(evaluation.DataQualityError):
        evaluation.score(prepared, 'y', {'engine': engine}, missing_policy=policy, explain=False)
    assert prepared.read_bytes() == original


@pytest.mark.parametrize('policy', ['reject', 'impute_train_v1'])
def test_native_missing_and_imputation_flags_cannot_bypass_validation(prepared, policy):
    frame = pd.read_csv(prepared)
    frame.loc[0, 'z'] = np.nan
    frame.to_csv(prepared, index=False)
    with pytest.raises(evaluation.DataQualityError, match='Correct the CSV'):
        evaluation.validate_clean_dataset(prepared, 'y', allow_missing=True, missing_policy=policy)
