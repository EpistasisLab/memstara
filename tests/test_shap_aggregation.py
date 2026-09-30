"""Verify SHAP magnitude and direction against actual synthetic TreeSHAP output."""
import numpy as np
import pandas as pd
import xgboost

from memstara import evaluation


def test_tree_shap_keeps_bias_separate_and_aggregates_before_ranking(tmp_path, monkeypatch):
    x = np.linspace(-2, 2, 180)
    path = tmp_path / 'synthetic.csv'
    pd.DataFrame({'predictor': x, 'target': (x > 0).astype(int)}).to_csv(path, index=False)
    original = xgboost.Booster.predict
    captured = {}

    def observe(self, *args, **kwargs):
        values = original(self, *args, **kwargs)
        if kwargs.get('pred_contribs'):
            captured['values'] = values
            captured['margins'] = original(self, args[0], output_margin=True)
        return values

    monkeypatch.setattr(xgboost.Booster, 'predict', observe)
    result = evaluation.score(path, 'target', {'engine': 'xgboost'})
    values = captured['values']
    shap = result['explanation']['shap']
    assert shap['method'] == 'XGBoost TreeSHAP'
    assert shap['units'] == 'log-odds'
    assert len(shap['mean_absolute']) == len(shap['mean_signed']) == values.shape[1] - 1
    # Float32 tree accumulation differs slightly between SHAP and margin prediction.
    np.testing.assert_allclose(values.sum(axis=1), captured['margins'], atol=1e-4, rtol=1e-5)
    np.testing.assert_allclose(list(shap['mean_absolute'].values()), np.abs(values[:, :-1]).mean(axis=0))
    np.testing.assert_allclose(list(shap['mean_signed'].values()), values[:, :-1].mean(axis=0))
    # Opposite effects cancel in the signed mean, but must remain in global importance.
    assert np.any(np.abs(values[:, :-1]).mean(axis=0) > np.abs(values[:, :-1].mean(axis=0)) + .01)
