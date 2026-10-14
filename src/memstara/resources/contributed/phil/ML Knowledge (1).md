---
title: "ml-knowledge"
format: "OKF"
domain: "machine_learning"
topic: "predictive_analytics"
library: "scikit-learn"
version_scope: "scikit-learn 1.9.x concepts"
intended_agent: "AI data science / predictive analytics agent"
purpose: "Essential operational knowledge for selecting, fitting, tuning, validating, and evaluating supervised machine-learning models from the scikit-learn library and MCP tool."
---

# Practical Machine Learning with scikit-learn MCP tool

## Core workflow

For supervised predictive analytics, work from a feature matrix `X` and target `y`.

1. Define the prediction task and target before modeling.
2. Separate data used for model development from data used for final evaluation.
3. Build preprocessing and the estimator together in a `Pipeline` when possible.
4. Tune hyperparameters using cross-validation on the training data only.
5. Select the final model using a prespecified primary metric.
6. Evaluate the selected model once on an untouched test set.
7. Report predictive performance, variability, and important limitations.

Never evaluate a model on the same observations used to fit it. Avoid information leakage from preprocessing, feature selection, or hyperparameter tuning.

## Common scikit-learn estimator interface

Most supervised estimators use the same basic API:

- `model.fit(X_train, y_train)` — learn model parameters from training data.
- `model.predict(X)` — generate class labels or numeric predictions.
- `model.predict_proba(X)` — generate class probabilities when supported.
- `model.decision_function(X)` — generate decision scores for some classifiers.
- `model.get_params()` — inspect configurable hyperparameters.
- `model.set_params(...)` — change hyperparameters.

**Model parameters** are learned from data during `fit()`.  
**Hyperparameters** are choices set before fitting, such as regularization strength, tree depth, number of trees, or kernel settings.

## Practical model choices

For classification, useful starting models include:

- `LogisticRegression` — strong interpretable baseline; supports regularization.
- `RandomForestClassifier` — nonlinear ensemble; handles interactions and mixed feature behavior well.
- `HistGradientBoostingClassifier` — efficient boosted-tree model for tabular data.
- `SVC` — powerful for some small-to-medium datasets; scaling is usually important.
- `KNeighborsClassifier` — simple local method; sensitive to feature scale and dimensionality.
- `DummyClassifier` — essential baseline showing performance from trivial strategies.

For regression, useful starting models include:

- `LinearRegression` / `Ridge` / `Lasso`
- `RandomForestRegressor`
- `HistGradientBoostingRegressor`
- `SVR`
- `DummyRegressor`

Do not assume a more complex model is better. Compare against simple baselines.

## Preprocessing

Preprocessing must be learned from training data only.

Common tools:

- `SimpleImputer` — missing-value imputation.
- `StandardScaler` — standardization; important for logistic regression, SVMs, nearest-neighbor methods, and many linear models.
- `OneHotEncoder` — categorical variables.
- `ColumnTransformer` — apply different transformations to different feature subsets.
- `Pipeline` — combine preprocessing and modeling so transformations are correctly refit within each cross-validation fold.

Prefer a `Pipeline` over preprocessing the entire dataset before cross-validation because the latter can cause leakage.

## Training and test splitting

Use `train_test_split` for a simple holdout design.

For classification, use stratification when appropriate so outcome prevalence is similar across splits:

`train_test_split(X, y, stratify=y, ...)`

Use a fixed `random_state` when reproducibility is important.

Do not randomly split observations when dependence would make that inappropriate. Examples include repeated measurements from the same patient, clustered/site data, or temporal prediction. Use group-aware or time-aware splitting instead.

## Cross-validation

Cross-validation estimates generalization performance and supports model/hyperparameter selection.

Common choices:

- `KFold` — standard k-fold CV for approximately independent observations.
- `StratifiedKFold` — generally preferred for classification because class proportions are preserved.
- `GroupKFold` / related grouped splitters — keep observations from the same subject or group together.
- `TimeSeriesSplit` — preserve temporal ordering when predicting the future from the past.
- `cross_val_score` — evaluate one metric.
- `cross_validate` — evaluate multiple metrics and optionally retain timing or fitted estimators.

Five-fold CV is a common practical default, but the splitting strategy should reflect the data-generating process.

## Hyperparameter tuning

Tune hyperparameters using training data and cross-validation.

Primary scikit-learn approaches:

- `GridSearchCV` — evaluates a specified grid of combinations.
- `RandomizedSearchCV` — samples combinations from distributions or lists; often more efficient for larger search spaces.

Examples of important hyperparameters:

- Logistic regression: `C`, penalty.
- Random forest: `n_estimators`, `max_depth`, `min_samples_leaf`, `max_features`.
- Gradient boosting: learning rate, iterations/trees, leaf size, regularization.
- SVM: `C`, kernel, `gamma`.

Choose the optimization metric explicitly using `scoring=`. Hyperparameters must not be selected using the final test set.

## Classification quality metrics

Use metrics appropriate to the clinical or analytic objective and class balance.

### Accuracy
Fraction of predictions assigned to the correct class.

Useful when classes are reasonably balanced and false positives and false negatives have similar consequences. Accuracy can be misleading for rare outcomes.

### AUROC
Area under the receiver operating characteristic curve.

Measures discrimination across classification thresholds. Approximately interpretable as how well the model ranks a randomly selected positive observation above a randomly selected negative observation. Use probabilities or decision scores, not hard class predictions.

`roc_auc_score(y_true, y_score)`

### Precision
Among predicted positives, the proportion truly positive.

Important when false-positive predictions are costly.

### Recall / Sensitivity
Among actual positives, the proportion correctly identified.

Important when missing a positive case is costly.

### Specificity
Among actual negatives, the proportion correctly identified.

Can be calculated from the confusion matrix.

### F1 score
Harmonic mean of precision and recall. Useful when balancing these two quantities is important.

### Average precision / precision-recall performance
For strongly imbalanced binary outcomes, `average_precision_score` and precision-recall curves are often more informative than accuracy and can complement AUROC.

### Calibration
Discrimination does not guarantee accurate probabilities. If predicted probabilities will be interpreted as risk, assess calibration in addition to AUROC.

## Regression quality metrics

Common metrics include:

- MAE — mean absolute error; directly interpretable in outcome units.
- MSE / RMSE — penalizes large errors more heavily.
- `R²` — fraction of outcome variance explained relative to a constant baseline.

Use more than one metric when the consequences of prediction errors differ.

## Recommended evaluation practice

For a defensible predictive analysis:

- Prespecify the primary performance metric.
- Maintain a final untouched test set when feasible.
- Tune models only inside the training/development data.
- Use pipelines to prevent leakage.
- Use stratified, grouped, or temporal CV as appropriate.
- Compare multiple reasonable algorithms and a trivial baseline.
- Report cross-validation mean and variability, not only the best score.
- Evaluate the final selected model on the held-out test data.
- For imbalanced classification, report AUROC plus precision-recall-oriented metrics.
- For risk prediction, examine calibration.
- Record random seeds, preprocessing, hyperparameters, and software versions for reproducibility.

## Common failure modes

Avoid:

- fitting preprocessing on the entire dataset before cross-validation;
- tuning hyperparameters on the test set;
- reporting training-set performance as evidence of generalization;
- using accuracy alone for rare outcomes;
- allowing observations from the same patient/group into both train and test folds;
- randomly splitting temporal data in ways that leak future information;
- choosing a metric after seeing which one makes the model look best;
- interpreting association, feature importance, or predictive performance as causal evidence.

## Minimal conceptual template

`data -> split -> preprocessing pipeline -> cross-validated tuning -> model selection -> untouched test evaluation -> report metrics`

The objective is not to maximize a score at any cost. The agent should produce a reproducible model whose validation design matches the prediction problem and whose performance metrics are appropriate to the intended use.
