"""Real numerical component checks on synthetic data, without any model API calls."""
import json

import numpy as np
import pandas as pd
import pytest

from memstara.pilot_ml import fit_pair, parameter_context, validate_ml_plan


def plan():
    models = parameter_context()
    models['logistic_regression'].update(random_state=7, max_iter=200)
    models['xgboost'].update(random_state=7, n_estimators=5, max_depth=2, n_jobs=1)
    return {'models': models, 'scale_numeric': True, 'threshold': .5,
            'xai_rows': 2, 'lime_samples': 100, 'seed': 7}


def test_real_lr_and_xgb_shap_lime_use_one_held_out_split(tmp_path):
    pytest.importorskip('shap')
    pytest.importorskip('lime')
    rng = np.random.default_rng(9)
    frame = pd.DataFrame(rng.normal(size=(80, 4)), columns=['a', 'b', 'c', 'd'])
    frame['outcome'] = (frame.a + frame.b > 0).astype(int)
    dataset = tmp_path / 'synthetic.csv'
    frame.to_csv(dataset, index=False)
    scope = {'run_id': 'synthetic', 'combination_id': 1, 'question_id': 'synthetic:1'}
    output = tmp_path / 'pair'
    rows = fit_pair(dataset, 'outcome', ['a', 'b', 'c', 'd'],
                    {'test_size': .25, 'seed': 7, 'stratify': True}, plan(), scope, output)
    assert {row['model'] for row in rows} == {'logistic_regression', 'xgboost'}
    assert rows[0]['split_id'] == rows[1]['split_id']
    split = json.loads((output / 'split.json').read_text())
    assert set(split['train_rows']).isdisjoint(split['test_rows'])
    assert len(split['test_rows']) == 20
    for row in rows:
        assert sum(sum(values) for values in row['metrics']['confusion_matrix']['values']) == 20
        assert {'brier', 'f1', 'auroc', 'average_precision'} <= set(row['metrics'])
        shap = row['attributions']['shap']
        lime = row['attributions']['lime']
        assert shap['status'] == lime['status'] == 'completed'
        assert np.asarray(shap['values']).shape == (2, 4)
        assert len(lime['rows']) == 2
        assert shap['background_source'] == 'training only'
        assert row['settings']['parameters']['random_state'] == 7
        predictions = pd.read_csv(output / f"{row['model']}.predictions.csv")
        assert predictions.row_position.tolist() == split['test_rows']
        logits = np.asarray(shap['values']).sum(axis=1) + np.asarray(shap['expected_value'])
        reconstructed = 1 / (1 + np.exp(-logits))
        assert np.allclose(reconstructed, predictions.probability.iloc[shap['held_out_positions']], atol=1e-5)
        assert (output / f"{row['model']}.joblib").is_file()


def test_ml_parameters_are_not_replaced_by_frozen_defaults():
    decision = plan()
    decision['models']['logistic_regression']['C'] = .123
    decision['models']['xgboost']['max_depth'] = 3
    assert validate_ml_plan(decision) == decision
    del decision['models']['logistic_regression']['C']
    with pytest.raises(ValueError, match='every disclosed'):
        validate_ml_plan(decision)
