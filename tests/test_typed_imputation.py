"""Typed uploads retain train-only imputation and encoding throughout execution."""
import json
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest

from memstara.dataset_upload import inspect_csv
from memstara.research_inputs import inspect, register, prepare
from memstara.evaluation import score
from memstara.preprocessing_policy import TYPED
from memstara.missing_values import TrainingImputer

@pytest.fixture
def typed_data(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path/'registry'))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path/'outputs'))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {})
    frame = pd.DataFrame({'measurement': np.linspace(1., 100., 120),
        'stage': [1., 2., 3., 2.]*30, 'binary12': [1., 2., 2., 2.]*30,
        'group': ['red', 'blue', 'blue', 'green']*30, 'target': [0, 1]*60})
    for c in frame.columns[:-1]:
        frame.loc[[7, 24, 53], c] = np.nan
    path=tmp_path/'data.csv';frame.to_csv(path,index=False)
    return {'name':'Typed data', 'dataset_path':str(path), 'knowledge_mode':'llm_only',
        'target':{'column':'target','positive_label':'1','negative_label':'0'},
        'missing_policy':'impute_train_v1', 'predictor_types':{}}

def test_schema_reports_ambiguity_and_registration_blocks_guessing(typed_data):
    metadata=inspect_csv(Path(typed_data['dataset_path']).read_bytes())
    assert metadata['column_kinds']['binary12']=='categorical'
    assert metadata['column_kinds']['group']=='categorical'
    assert set(metadata['type_confirmation_columns'])=={'measurement'}
    pending=inspect(typed_data)
    assert not pending['input_checks_passed']
    assert sum(x['code']=='predictor_type_required' for x in pending['issues'])==1
    assert 'nonnumeric_predictors' not in [x['code'] for x in pending['issues']]
    assert not register(typed_data)['input_checks_passed']


def test_semantic_suggestions_require_compatible_values_and_allow_override(typed_data):
    path = Path(typed_data['dataset_path'])
    frame = pd.read_csv(path).rename(columns={'measurement':'age_years', 'stage':'essential_hypertension_stage',
                                             'binary12':'previous_myocardial_infarctions_count'})
    frame.to_csv(path,index=False)
    metadata = inspect_csv(path.read_bytes())
    assert metadata['type_confirmation_columns'] == []
    assert metadata['suggested_predictor_types']['age_years'] == 'continuous'
    assert metadata['suggested_predictor_types']['previous_myocardial_infarctions_count'] == 'continuous'
    assert metadata['suggested_predictor_types']['essential_hypertension_stage'] == 'categorical'
    saved = register(typed_data)
    assert saved['input_checks_passed']
    assert saved['configuration']['predictor_types']['age_years'] == 'continuous'
    overridden = inspect({**typed_data, 'predictor_types':{'age_years':'categorical'}})
    assert overridden['configuration']['predictor_types']['age_years'] == 'categorical'
    frame['age_years'] *= 100
    frame['essential_hypertension_stage'] += .5
    frame.to_csv(path,index=False)
    assert set(inspect_csv(path.read_bytes())['type_confirmation_columns']) == {'age_years','essential_hypertension_stage'}

@pytest.mark.parametrize('engine',['logistic_regression','xgboost'])
def test_registered_types_drive_real_fits_and_train_only_statistics(typed_data,engine):
    source=Path(typed_data['dataset_path']).read_bytes()
    saved=register({**typed_data,'predictor_types':{'measurement':'continuous','stage':'categorical'}})
    assert saved['input_checks_passed']
    types=saved['configuration']['predictor_types']
    assert types=={'measurement':'continuous','stage':'categorical','binary12':'categorical','group':'categorical'}
    profile=prepare(saved['id'])
    path=Path(profile['root'])/'dataset.csv'
    observed=[];original=TrainingImputer.fit
    from unittest.mock import patch
    def record_fit(self,X,y=None):
        observed.append(set(X.index))
        return original(self,X,y)
    with patch.object(TrainingImputer,'fit',record_fit):
        result=score(path,'target',{'engine':engine,'folds':3,'seed':31},
                     missing_policy='impute_train_v1',preprocessing_policy=TYPED,
                     predictor_types=types,explain=False)
    bundle=Path(result['evaluation']['reproducibility']['bundle_path'])
    split=np.load(bundle/'split-0.npz');train=split['train'];test=split['test']
    assert all(not rows.intersection(test) for rows in observed)
    assert any(len(rows)<len(train) for rows in observed)
    frame=pd.read_csv(path);imputation=result['evaluation']['replicates'][0]['imputation']
    assert imputation['strategies']=={'measurement':'mean','stage':'most_frequent','binary12':'most_frequent','group':'most_frequent'}
    assert imputation['fill_values']['measurement']==pytest.approx(frame.iloc[train].measurement.mean())
    for column in ['stage','binary12','group']:
        assert imputation['fill_values'][column]==frame.iloc[train][column].mode().iloc[0]
    model=joblib.load(bundle/'model-0.joblib')
    raw=frame.iloc[train][['measurement']].fillna(imputation['fill_values']['measurement'])
    np.testing.assert_array_equal(model.named_steps['encode'].named_transformers_['numeric'].transform(raw), raw)
    assert np.isfinite(model.predict_proba(frame.drop(columns='target'))).all()
    assert Path(typed_data['dataset_path']).read_bytes()==source
    from memstara.reproducibility import replay
    assert replay(bundle)['status']=='verified'
    # Both explainers use the same typed, fitted model.
    from memstara.specialist_xai import calculate
    policy={'max_original_features':64,'explained_rows':2,'background_rows':8,'lime_samples':100}
    for method in ['shap','lime']:
        evidence=calculate(model,frame.drop(columns='target'),train,test,31,engine,method,policy)
        assert np.isfinite(evidence['values_original']).all()


def test_continuous_override_is_respected_even_with_two_training_values():
    frame=pd.DataFrame({'measurement':[2.,6.,np.nan], 'binary12':[1.,2.,2.]})
    imputer=TrainingImputer(categorical_columns=('binary12',),continuous_columns=('measurement',)).fit(frame)
    assert imputer.fill_values_=={'measurement':4.,'binary12':2.}


def test_schema_is_frozen_and_informs_the_ml_agent(typed_data,tmp_path,monkeypatch):
    saved=register({**typed_data,'predictor_types':{'measurement':'continuous','stage':'categorical'}})
    profile=prepare(saved['id'])
    from memstara.research_inputs import activate
    from memstara.pipeline.snapshot import freeze
    from memstara.ml_configuration import context
    monkeypatch.setattr('os.environ',dict(__import__('os').environ))
    activate(profile)
    run=tmp_path/'run';run.mkdir()
    args=SimpleNamespace(evaluation='{}',y_column='target',baseline_columns='[]',run_tag='typed-test',
        question='',hypothesis_agents=1,trials=1,waves=1,research_profile=profile)
    frozen=freeze(args,run,{'ml':['ml_logistic_regression']})
    assert frozen['preprocessing_policy']==TYPED
    assert frozen['hypothesis_policy']['version']=='knowledge_only_v1'
    assert frozen['hypothesis_policy']['prior_ml_feedback'] is False
    assert frozen['pause_policy']=='fresh_request_and_ml_restart_v2'
    assert frozen['research_profile']['configuration']['predictor_types']==saved['configuration']['predictor_types']
    assert 'encoding inside each training' in context(frozen,frozen['evaluation'])['preprocessing_contract']
