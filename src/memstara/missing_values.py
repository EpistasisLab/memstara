"""Explicit missing-value consent and training-fitted transformations.

Review boundaries:
* resolve_policy reads frozen consent; it never guesses consent from the data.
* TrainingImputer.fit sees only the rows supplied by sklearn's training/CV fit.
* transform reuses those values without modifying its input or learning from it.
"""
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

TRAINING_IMPUTATION = 'impute_train_v1'
# Stable identifier used in previously recorded configuration and artifacts.
POLICY = TRAINING_IMPUTATION


def resolve_policy(snapshot: dict[str, Any] | None = None) -> str:
    """Resolve registered consent before the legacy run-level fallback."""
    if snapshot is None:
        from memstara.evaluation import active_plan
        snapshot = active_plan() or {}
    configuration = snapshot.get('research_profile', {}).get('configuration', {})
    return configuration.get('missing_policy') or snapshot.get('missing_value_policy', 'reject')


def imputation_record(model: Any, policy_name: str, *, fit_scope: str = "training_partition") -> dict[str, Any] | None:
    """Record the fitted training values, rather than recomputing statistics."""
    imputer = model.named_steps.get('impute')
    if imputer is None:
        return None
    return {
        'policy': policy_name,
        'fit_scope': fit_scope,
        'strategies': imputer.strategies_,
        'fill_values': imputer.fill_values_,
    }


class TrainingImputer(TransformerMixin, BaseEstimator):
    """Fill continuous values with means and declared categories with modes.

    Text and observed 0/1 values use modes automatically. Numeric category codes
    other than 0/1 must be declared by the user; cardinality is not a safe proxy
    for clinical meaning. Empty training columns fail rather than inventing a
    value or removing a feature. sklearn.clone creates a fresh fit for each CV
    fold and replicate, so neither test nor validation rows determine statistics.
    """

    def __init__(self, categorical_columns=()):
        self.categorical_columns = categorical_columns

    def fit(self, X: pd.DataFrame, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        self.fill_values_: dict[str, Any] = {}
        self.strategies_: dict[str, str] = {}
        for column in X:
            observed = X[column].dropna()
            if observed.empty:
                raise ValueError(
                    f'No observed training values for predictor {column}; '
                    'exclude it or supply complete data'
                )
            numeric = pd.api.types.is_numeric_dtype(observed)
            binary = numeric and set(observed.unique()).issubset({0, 1})
            categorical = not numeric or binary or column in self.categorical_columns
            strategy = 'most_frequent' if categorical else 'mean'
            value = observed.mode().iloc[0] if categorical else observed.mean()
            self.fill_values_[column] = value.item() if isinstance(value, np.generic) else value
            self.strategies_[column] = strategy
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if list(X.columns) != list(self.feature_names_in_):
            raise ValueError('Imputation feature order differs from the fitted schema')
        return X.copy().fillna(self.fill_values_)

    def get_feature_names_out(self, input_features=None):
        return self.feature_names_in_
